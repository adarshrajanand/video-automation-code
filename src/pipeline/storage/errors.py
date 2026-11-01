"""Storage-layer exceptions with stable, explicit failure categories.

SQLite reports every constraint problem through :class:`sqlite3.IntegrityError`.
The repository layer translates those opaque messages into a small set of typed
errors so callers can distinguish a missing record, a duplicate logical key, and
another integrity violation without parsing SQLite diagnostics.
"""

from __future__ import annotations


class StorageError(Exception):
    """Base class for local persistence failures."""


class NotFoundError(StorageError):
    """A repository lookup matched no durable record."""

    def __init__(self, entity: str, key: object) -> None:
        self.entity = entity
        self.key = key
        super().__init__(f"{entity} not found for key {key!r}")


class ConflictError(StorageError):
    """An insert or update collided with an existing unique key."""

    def __init__(self, entity: str, detail: str) -> None:
        self.entity = entity
        self.detail = detail
        super().__init__(f"{entity} conflicts with existing state: {detail}")


class IntegrityError(StorageError):
    """A non-uniqueness SQLite integrity constraint was violated."""

    def __init__(self, entity: str, detail: str) -> None:
        self.entity = entity
        self.detail = detail
        super().__init__(f"{entity} violates an integrity constraint: {detail}")


class MigrationError(StorageError):
    """The ordered migration set cannot be applied or trusted."""


class MigrationChecksumError(MigrationError):
    """An already-applied migration changed after it was recorded."""


class ArtifactStoreError(StorageError):
    """Base class for immutable artifact-store failures."""


class ArtifactUriError(ArtifactStoreError, ValueError):
    """An artifact URI is not in the opaque content-addressed namespace."""


class ArtifactNotFoundError(ArtifactStoreError):
    """The store has no bytes for the requested opaque URI."""


class ArtifactIntegrityError(ArtifactStoreError):
    """Published or expected bytes do not match their content hash."""


class ArtifactCollisionError(ArtifactIntegrityError):
    """A content-addressed destination exists but holds different bytes."""


class HashMismatchError(ArtifactStoreError):
    """Caller-declared content hash does not match the bytes to publish."""


__all__ = [
    "ArtifactCollisionError",
    "ArtifactIntegrityError",
    "ArtifactNotFoundError",
    "ArtifactStoreError",
    "ArtifactUriError",
    "ConflictError",
    "HashMismatchError",
    "IntegrityError",
    "MigrationChecksumError",
    "MigrationError",
    "NotFoundError",
    "StorageError",
]
