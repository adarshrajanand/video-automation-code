"""Local durable storage: SQLite repository, migrations, and immutable bytes.

Public entry points:

- :class:`pipeline.storage.database.Database` for connections and explicit
  ``BEGIN IMMEDIATE`` transactions;
- :class:`pipeline.storage.migrations.MigrationRunner` for ordered, checksummed
  schema migrations;
- the repository classes re-exported from
  :mod:`pipeline.storage.repositories`;
- :class:`pipeline.storage.artifact_store.ArtifactStore` for immutable,
  content-addressed bytes.

Architecture:
- **Database**: Thin wrapper around sqlite3 with explicit transaction control.
  Connections enable ``PRAGMA foreign_keys=ON``, WAL mode, busy timeout.
  Transaction helper provides ``BEGIN IMMEDIATE`` with automatic rollback.
- **Migrations**: Ordered SQL files in ``storage/migrations/``. Each migration
  has a name, checksum, and application timestamp. Applied migrations are
  recorded in ``schema_migrations`` table. Checksums prevent silent corruption.
- **Repositories**: Typed SQLite repositories (SqliteRepository base).
  Each repository owns a table, stores canonical JSON in ``payload`` column,
  extracts key columns for indexing. All reads revalidate through Pydantic.
- **ArtifactStore**: Immutable content-addressed storage under
  ``PIPELINE_HOME/artifacts/``. Publish writes temp file, fsyncs, atomic link.
  Content addressed by SHA-256. Duplicate content deduplicates naturally.
  Duplicate content with different hash raises ArtifactIntegrityError.

Transaction Discipline:
- All writes use explicit ``BEGIN IMMEDIATE`` transactions via ``transaction()``
- Repositories accept caller-provided connection for multi-repo transactions
- Connection helper ``connection()`` provides a raw connection in autocommit
  mode (``isolation_level=None``); writes through it auto-commit unless
  wrapped in ``transaction()``
- ``transaction()`` ensures explicit commit/rollback; ``connection()`` does not
- Foreign keys enforced (``PRAGMA foreign_keys=ON``)

Error Hierarchy:
- StorageError (base)
  - ConflictError: Unique constraint violation
  - NotFoundError: Key not found
  - IntegrityError: Foreign key / check constraint
  - MigrationError / MigrationChecksumError
  - Artifact* errors (store, integrity, collision, uri)

Artifact Store Layout:
```
PIPELINE_HOME/
├── artifacts/
│   ├── .staging/              # transient publication files
│   └── sha256/<prefix>/<hash> # immutable content-addressed bytes
```

Repository Pattern:
- Each repo class defines: model, table, key_columns, columns, order_by
- Base ``SqliteRepository`` handles insert/get/list/update with JSON payload
- Queries use extracted columns for indexing, payload for full object
- All reads revalidate through Pydantic model
"""

from pipeline.storage.artifact_store import (
    ARTIFACT_URI_PREFIX,
    ArtifactStore,
    StoredArtifact,
)
from pipeline.storage.database import Database
from pipeline.storage.errors import (
    ArtifactCollisionError,
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ArtifactStoreError,
    ArtifactUriError,
    ConflictError,
    HashMismatchError,
    IntegrityError,
    MigrationChecksumError,
    MigrationError,
    NotFoundError,
    StorageError,
)
from pipeline.storage.migrations import (
    AppliedMigration,
    Migration,
    MigrationResult,
    MigrationRunner,
    MigrationStatus,
    discover_migrations,
)
from pipeline.storage.repositories import (
    ArtifactDependencyRepository,
    ArtifactPointerRepository,
    ArtifactRepository,
    BudgetReservationRepository,
    CompositionRefRepository,
    ContentPackageRepository,
    CutRepository,
    EffectiveConfigRepository,
    EpisodeRepository,
    IdempotencyRecordRepository,
    InboxReceiptRepository,
    JobRepository,
    LayerInstanceRepository,
    LeaseRepository,
    OutboxMessageRepository,
    RecoveryDecisionRepository,
    SceneRepository,
    SequenceRepository,
    ShotRepository,
    StageAttemptRepository,
    StageInstanceRepository,
    WorkflowEventRepository,
    WorkflowRunRepository,
    insert_event_and_outbox,
)

__all__ = [
    "ARTIFACT_URI_PREFIX",
    "AppliedMigration",
    "ArtifactCollisionError",
    "ArtifactDependencyRepository",
    "ArtifactIntegrityError",
    "ArtifactNotFoundError",
    "ArtifactPointerRepository",
    "ArtifactRepository",
    "ArtifactStore",
    "ArtifactStoreError",
    "ArtifactUriError",
    "BudgetReservationRepository",
    "CompositionRefRepository",
    "ConflictError",
    "ContentPackageRepository",
    "CutRepository",
    "Database",
    "EffectiveConfigRepository",
    "EpisodeRepository",
    "HashMismatchError",
    "IdempotencyRecordRepository",
    "InboxReceiptRepository",
    "IntegrityError",
    "JobRepository",
    "LayerInstanceRepository",
    "LeaseRepository",
    "Migration",
    "MigrationChecksumError",
    "MigrationError",
    "MigrationResult",
    "MigrationRunner",
    "MigrationStatus",
    "NotFoundError",
    "OutboxMessageRepository",
    "RecoveryDecisionRepository",
    "SceneRepository",
    "SequenceRepository",
    "ShotRepository",
    "StageAttemptRepository",
    "StageInstanceRepository",
    "StorageError",
    "StoredArtifact",
    "WorkflowEventRepository",
    "WorkflowRunRepository",
    "discover_migrations",
    "insert_event_and_outbox",
]
