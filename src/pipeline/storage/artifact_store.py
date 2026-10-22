"""Local immutable, content-addressed artifact store.

Published bytes live under ``PIPELINE_HOME/artifacts/sha256/<prefix>/<hash>`` and
are referenced only through an opaque ``artifact://sha256/<hash>`` URI. Bytes
are staged in a temporary file, fsynced, then atomically linked into their final
content-addressed path. Existing bytes are verified on every collision and are
never overwritten by different content. Attempt-scoped temporary workspaces
live under ``PIPELINE_HOME/tmp`` and are always outside the artifact namespace.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Final

from pipeline.fingerprints import file_sha256, is_sha256_hex, sha256_bytes, sha256_text
from pipeline.paths import resolve_pipeline_home
from pipeline.storage.errors import (
    ArtifactCollisionError,
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ArtifactUriError,
    HashMismatchError,
)

ARTIFACT_URI_PREFIX: Final[str] = "artifact://sha256/"
_CONTENT_DIRECTORY: Final[str] = "sha256"
_STAGING_DIRECTORY: Final[str] = ".staging"
_READ_CHUNK_BYTES: Final[int] = 1024 * 1024
_SAFE_COMPONENT_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
)


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    """Identity of published bytes, independent of their physical path."""

    uri: str
    sha256: str
    size_bytes: int
    deduplicated: bool = False


class ArtifactStore:
    """Content-addressed local implementation of the ArtifactStore protocol."""

    def __init__(
        self,
        root: Path | str | None = None,
        *,
        pipeline_home: Path | str | None = None,
        workspace_root: Path | str | None = None,
    ) -> None:
        if root is not None and pipeline_home is not None:
            raise ValueError("pass either root or pipeline_home, not both")
        if root is None:
            home = (
                resolve_pipeline_home()
                if pipeline_home is None
                else Path(pipeline_home).expanduser().resolve()
            )
            self.root = home / "artifacts"
        else:
            self.root = Path(root).expanduser().resolve()
        if workspace_root is None:
            home = (
                Path(pipeline_home).expanduser().resolve()
                if pipeline_home is not None
                else self.root.parent
            )
            self.workspace_root = home / "tmp"
        else:
            self.workspace_root = Path(workspace_root).expanduser().resolve()

    def __repr__(self) -> str:
        return (
            f"ArtifactStore(root={str(self.root)!r}, "
            f"workspace_root={str(self.workspace_root)!r})"
        )

    # ------------------------------------------------------------------
    # Opaque URI mapping
    # ------------------------------------------------------------------
    @staticmethod
    def uri_for_sha256(sha256: str) -> str:
        """Return the opaque URI for a lowercase SHA-256 digest."""

        if not is_sha256_hex(sha256):
            raise ArtifactUriError(
                "artifact URIs require a lowercase 64-character SHA-256 digest"
            )
        return f"{ARTIFACT_URI_PREFIX}{sha256}"

    @staticmethod
    def parse_uri(uri: str) -> str:
        """Return the digest encoded by an opaque artifact URI."""

        if not isinstance(uri, str) or not uri.startswith(ARTIFACT_URI_PREFIX):
            raise ArtifactUriError(f"unsupported artifact URI: {uri!r}")
        digest = uri[len(ARTIFACT_URI_PREFIX) :]
        if "/" in digest or not is_sha256_hex(digest):
            raise ArtifactUriError(f"unsupported artifact URI: {uri!r}")
        return digest

    def path_for_sha256(self, sha256: str) -> Path:
        """Map a digest to its immutable local path without creating it."""

        if not is_sha256_hex(sha256):
            raise ArtifactUriError(
                "artifact paths require a lowercase 64-character SHA-256 digest"
            )
        return self.root / _CONTENT_DIRECTORY / sha256[:2] / sha256

    def path_for_uri(self, uri: str) -> Path:
        """Map an opaque URI to its local path without reading the bytes."""

        return self.path_for_sha256(self.parse_uri(uri))

    # ------------------------------------------------------------------
    # Publication
    # ------------------------------------------------------------------
    def publish_bytes(
        self,
        data: bytes,
        *,
        expected_sha256: str | None = None,
    ) -> StoredArtifact:
        """Publish in-memory bytes and return their content-addressed identity."""

        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("publish_bytes requires bytes")
        return self._publish_stream(_BytesReader(bytes(data)), expected_sha256)

    def publish_file(
        self,
        source: Path | str,
        *,
        expected_sha256: str | None = None,
    ) -> StoredArtifact:
        """Publish a file without consuming or mutating the source file."""

        source_path = Path(source)
        try:
            handle = source_path.open("rb")
        except FileNotFoundError as error:
            raise ArtifactNotFoundError(
                f"source file does not exist: {source_path}"
            ) from error
        with handle:
            return self._publish_stream(handle, expected_sha256)

    def _publish_stream(
        self,
        source: BinaryIO,
        expected_sha256: str | None,
    ) -> StoredArtifact:
        if expected_sha256 is not None and not is_sha256_hex(expected_sha256):
            raise ValueError(
                "expected_sha256 must be a lowercase 64-character SHA-256 digest"
            )
        staging = self.root / _STAGING_DIRECTORY
        staging.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix="publish-", suffix=".tmp", dir=staging
        )
        temporary_path = Path(temporary_name)
        hasher = hashlib.sha256()
        size_bytes = 0
        try:
            with os.fdopen(descriptor, "wb") as target:
                while True:
                    chunk = source.read(_READ_CHUNK_BYTES)
                    if not chunk:
                        break
                    hasher.update(chunk)
                    target.write(chunk)
                    size_bytes += len(chunk)
                target.flush()
                os.fsync(target.fileno())
            digest = hasher.hexdigest()
            if expected_sha256 is not None and digest != expected_sha256:
                raise HashMismatchError(
                    f"declared sha256 {expected_sha256} does not match {digest}"
                )
            if file_sha256(temporary_path) != digest:
                raise ArtifactIntegrityError(
                    "temporary bytes changed before publication"
                )
            destination = self.path_for_sha256(digest)
            destination.parent.mkdir(parents=True, exist_ok=True)
            deduplicated = False
            try:
                os.link(temporary_path, destination)
            except FileExistsError:
                self._verify_destination(destination, digest)
                deduplicated = True
            _fsync_directory(destination.parent)
            return StoredArtifact(
                uri=self.uri_for_sha256(digest),
                sha256=digest,
                size_bytes=size_bytes,
                deduplicated=deduplicated,
            )
        finally:
            temporary_path.unlink(missing_ok=True)
            _remove_empty_directory(staging)

    def _verify_destination(self, destination: Path, expected_sha256: str) -> None:
        try:
            actual = file_sha256(destination)
        except FileNotFoundError as error:
            raise ArtifactNotFoundError(
                f"content-addressed artifact disappeared: {destination}"
            ) from error
        if actual != expected_sha256:
            raise ArtifactCollisionError(
                "content-addressed destination already holds different bytes: "
                f"{destination}"
            )

    # ------------------------------------------------------------------
    # Read, hash, verify
    # ------------------------------------------------------------------
    def read(self, uri: str) -> bytes:
        """Read bytes by opaque URI and verify them against the URI digest."""

        sha256 = self.parse_uri(uri)
        path = self.path_for_sha256(sha256)
        try:
            data = path.read_bytes()
        except FileNotFoundError as error:
            raise ArtifactNotFoundError(f"artifact bytes are missing: {uri}") from error
        actual = sha256_bytes(data)
        if actual != sha256:
            raise ArtifactIntegrityError(
                f"artifact bytes for {uri} hash to {actual}, not {sha256}"
            )
        return data

    def hash(self, uri: str) -> str:
        """Return the verified SHA-256 of the bytes stored at ``uri``."""

        return self.verify(uri)

    def verify(self, uri: str, *, expected_sha256: str | None = None) -> str:
        """Verify stored bytes against the URI and an optional declared hash."""

        sha256 = self.parse_uri(uri)
        if expected_sha256 is not None and not is_sha256_hex(expected_sha256):
            raise ValueError(
                "expected_sha256 must be a lowercase 64-character SHA-256 digest"
            )
        path = self.path_for_sha256(sha256)
        try:
            actual = file_sha256(path)
        except FileNotFoundError as error:
            raise ArtifactNotFoundError(f"artifact bytes are missing: {uri}") from error
        if actual != sha256:
            raise ArtifactIntegrityError(
                f"artifact bytes for {uri} hash to {actual}, not {sha256}"
            )
        if expected_sha256 is not None and actual != expected_sha256:
            raise ArtifactIntegrityError(
                f"artifact bytes for {uri} hash to {actual}, "
                f"not the declared {expected_sha256}"
            )
        return actual

    def exists(self, uri: str) -> bool:
        """Return whether bytes exist at a syntactically valid URI."""

        return self.path_for_uri(uri).is_file()

    # ------------------------------------------------------------------
    # Attempt-scoped temporary workspaces
    # ------------------------------------------------------------------
    def create_workspace(self, attempt_id: str) -> Path:
        """Create a unique disposable workspace scoped to an attempt."""

        if not isinstance(attempt_id, str) or not attempt_id:
            raise ValueError("attempt_id must be a non-empty string")
        attempt_directory = self.workspace_root / _safe_component(attempt_id)
        attempt_directory.mkdir(parents=True, exist_ok=True)
        return Path(
            tempfile.mkdtemp(prefix="workspace-", dir=attempt_directory)
        ).resolve()

    @contextmanager
    def workspace(self, attempt_id: str) -> Iterator[Path]:
        """Yield an attempt-scoped workspace and remove it on every exit path."""

        workspace = self.create_workspace(attempt_id)
        try:
            yield workspace
        finally:
            self.cleanup_workspace(workspace)

    def cleanup_workspace(self, workspace: Path | str) -> None:
        """Remove one workspace after proving it is under the temporary root."""

        path = Path(workspace).expanduser().resolve()
        try:
            path.relative_to(self.workspace_root)
        except ValueError as error:
            raise ValueError(
                f"refusing to remove a directory outside {self.workspace_root}: {path}"
            ) from error
        shutil.rmtree(path, ignore_errors=True)
        _remove_empty_directory(path.parent)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    def list_uris(self) -> list[str]:
        """Return every published URI in lexical digest order."""

        content_root = self.root / _CONTENT_DIRECTORY
        if not content_root.is_dir():
            return []
        return [
            self.uri_for_sha256(path.name)
            for path in sorted(content_root.glob("*/*"))
            if path.is_file() and is_sha256_hex(path.name)
        ]


class _BytesReader:
    """Minimal file-like reader over bytes to share the streaming publish path."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._offset = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._data) - self._offset
        start = self._offset
        end = min(len(self._data), start + size)
        self._offset = end
        return self._data[start:end]


def _safe_component(value: str) -> str:
    if (
        _SAFE_COMPONENT_PATTERN.match(value) is not None
        and value not in {".", ".."}
        and ".." not in value
    ):
        return value
    return sha256_text(value)[:32]


def _fsync_directory(directory: Path) -> None:
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _remove_empty_directory(directory: Path) -> None:
    with suppress(OSError):
        directory.rmdir()


__all__ = ["ARTIFACT_URI_PREFIX", "ArtifactStore", "StoredArtifact"]
