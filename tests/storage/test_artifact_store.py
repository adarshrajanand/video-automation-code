from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.fingerprints import sha256_bytes
from pipeline.storage import (
    ArtifactCollisionError,
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ArtifactStore,
    ArtifactUriError,
    HashMismatchError,
)


def test_publish_read_hash_and_verify_round_trip(artifact_store: ArtifactStore) -> None:
    data = b"immutable artifact bytes\n\x00\x01"

    stored = artifact_store.publish_bytes(data)

    digest = sha256_bytes(data)
    assert stored.sha256 == digest
    assert stored.uri == f"artifact://sha256/{digest}"
    assert stored.size_bytes == len(data)
    assert stored.deduplicated is False
    assert artifact_store.read(stored.uri) == data
    assert artifact_store.hash(stored.uri) == digest
    assert artifact_store.verify(stored.uri) == digest
    assert artifact_store.verify(stored.uri, expected_sha256=digest) == digest
    assert artifact_store.exists(stored.uri) is True
    path = artifact_store.path_for_uri(stored.uri)
    assert path.is_file()
    assert path == artifact_store.path_for_sha256(digest)
    assert artifact_store.root in path.parents


def test_duplicate_content_deduplicates(artifact_store: ArtifactStore) -> None:
    data = b"same bytes"

    first = artifact_store.publish_bytes(data)
    second = artifact_store.publish_bytes(data)

    assert second.uri == first.uri
    assert second.sha256 == first.sha256
    assert second.deduplicated is True
    assert artifact_store.list_uris() == [first.uri]
    assert artifact_store.read(second.uri) == data


def test_declared_hash_is_enforced(artifact_store: ArtifactStore) -> None:
    data = b"declared"
    digest = sha256_bytes(data)

    stored = artifact_store.publish_bytes(data, expected_sha256=digest)
    assert stored.sha256 == digest

    with pytest.raises(HashMismatchError):
        artifact_store.publish_bytes(b"other", expected_sha256=digest)
    assert artifact_store.list_uris() == [stored.uri]

    with pytest.raises(ValueError, match="expected_sha256"):
        artifact_store.publish_bytes(data, expected_sha256=digest.upper())


def test_existing_destination_with_different_bytes_is_a_collision(
    artifact_store: ArtifactStore,
) -> None:
    data = b"original content"
    stored = artifact_store.publish_bytes(data)
    path = artifact_store.path_for_uri(stored.uri)
    path.write_bytes(b"tampered content")

    with pytest.raises(ArtifactCollisionError):
        artifact_store.publish_bytes(data)

    assert path.read_bytes() == b"tampered content"
    with pytest.raises(ArtifactIntegrityError):
        artifact_store.read(stored.uri)


def test_missing_bytes_are_detected(artifact_store: ArtifactStore) -> None:
    stored = artifact_store.publish_bytes(b"will be removed")
    path = artifact_store.path_for_uri(stored.uri)
    path.unlink()

    with pytest.raises(ArtifactNotFoundError):
        artifact_store.read(stored.uri)
    with pytest.raises(ArtifactNotFoundError):
        artifact_store.verify(stored.uri)
    with pytest.raises(ArtifactNotFoundError):
        artifact_store.hash(stored.uri)
    assert artifact_store.exists(stored.uri) is False


def test_corrupt_bytes_are_detected(artifact_store: ArtifactStore) -> None:
    stored = artifact_store.publish_bytes(b"good bytes")
    path = artifact_store.path_for_uri(stored.uri)
    path.write_bytes(b"corrupt bytes")

    with pytest.raises(ArtifactIntegrityError):
        artifact_store.read(stored.uri)
    with pytest.raises(ArtifactIntegrityError):
        artifact_store.verify(stored.uri)
    with pytest.raises(ArtifactIntegrityError):
        artifact_store.verify(stored.uri, expected_sha256=sha256_bytes(b"good bytes"))


def test_opaque_uri_mapping(artifact_store: ArtifactStore) -> None:
    digest = sha256_bytes(b"uri")

    uri = artifact_store.uri_for_sha256(digest)
    assert artifact_store.parse_uri(uri) == digest
    assert artifact_store.path_for_uri(uri) == artifact_store.path_for_sha256(digest)

    for invalid in (
        f"artifact://sha256/{digest.upper()}",
        f"artifact://sha256/{digest}/extra",
        f"artifact://sha256/{digest[:10]}",
        f"file://{digest}",
        "artifact://sha256/",
    ):
        with pytest.raises(ArtifactUriError):
            artifact_store.parse_uri(invalid)


def test_publish_file_preserves_source_and_deduplicates(
    artifact_store: ArtifactStore,
) -> None:
    with artifact_store.workspace("attempt_publish") as workspace:
        source = workspace / "output.bin"
        data = b"file content\n" * 100
        source.write_bytes(data)
        stored = artifact_store.publish_file(source)
        assert source.read_bytes() == data
        assert stored.sha256 == sha256_bytes(data)
        assert artifact_store.read(stored.uri) == data
        duplicate = artifact_store.publish_file(source)
        assert duplicate.deduplicated is True

    assert artifact_store.list_uris() == [stored.uri]


def test_publish_missing_file_is_rejected(
    artifact_store: ArtifactStore, tmp_path: Path
) -> None:
    with pytest.raises(ArtifactNotFoundError):
        artifact_store.publish_file(tmp_path / "missing.bin")


def test_workspace_is_attempt_scoped_and_cleaned_up(
    artifact_store: ArtifactStore,
) -> None:
    with artifact_store.workspace("attempt_01") as workspace:
        assert workspace.is_dir()
        assert workspace.parent.name == "attempt_01"
        assert artifact_store.workspace_root in workspace.parents
        (workspace / "scratch.txt").write_text("temporary", encoding="utf-8")
        retained = workspace

    assert retained.exists() is False
    assert (artifact_store.workspace_root / "attempt_01").exists() is False


def test_workspace_is_cleaned_up_after_an_exception(
    artifact_store: ArtifactStore,
) -> None:
    retained: Path | None = None
    with (
        pytest.raises(RuntimeError),
        artifact_store.workspace("attempt_failure") as workspace,
    ):
        retained = workspace
        (workspace / "partial.bin").write_bytes(b"partial")
        raise RuntimeError("stage failed")

    assert retained is not None
    assert retained.exists() is False


def test_workspace_names_cannot_escape_the_temp_root(
    artifact_store: ArtifactStore,
) -> None:
    with artifact_store.workspace("../../attempt") as workspace:
        assert artifact_store.workspace_root in workspace.parents
        assert ".." not in workspace.parts

    with pytest.raises(ValueError, match="outside"):
        artifact_store.cleanup_workspace(artifact_store.workspace_root.parent)


def test_cleanup_workspace_removes_an_explicit_workspace(
    artifact_store: ArtifactStore,
) -> None:
    workspace = artifact_store.create_workspace("attempt_manual")
    (workspace / "file.txt").write_text("x", encoding="utf-8")

    artifact_store.cleanup_workspace(workspace)

    assert workspace.exists() is False


def test_empty_bytes_round_trip(artifact_store: ArtifactStore) -> None:
    stored = artifact_store.publish_bytes(b"")

    assert stored.size_bytes == 0
    assert artifact_store.read(stored.uri) == b""
    assert stored.sha256 == sha256_bytes(b"")
