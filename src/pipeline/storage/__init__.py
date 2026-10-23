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
