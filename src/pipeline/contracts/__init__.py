"""Public FV-02 contract surface.

Import durable models from this package. Abstract bases are exposed for type
constraints, but only concrete models in :data:`PUBLIC_CONTRACTS` have exported
JSON Schemas and fixtures.

Contract Philosophy:
- **Strict**: Unknown fields rejected, scalars not coerced
- **Identifiers**: Non-empty, opaque, prefix-prefixed (e.g., `run_abc123`)
- **Timestamps**: Timezone-aware, normalized to UTC, ISO 8601
- **Hashes**: Lowercase SHA-256 hex, content-addressed
- **Extensions**: Arbitrary JSON only via explicit `ExtensionObject` fields
- **Validation**: Cross-field invariants enforced by Pydantic validators

Contract Families:
- **Base**: Contract, NormalizedError, UTCDateTime, ExtensionObject
- **Vocabularies**: FailureCode, FailureCategory, Severity, GateDecision, etc.
- **Configuration**: EffectiveConfig, RunOverrides, BudgetPolicy, Profiles
- **Workflow**: StageNode, WorkflowDefinition, CardinalityPolicy
- **Execution**: WorkflowRun, StageInstance, StageAttempt, Job, Lease
- **Capabilities**: CapabilityRequest/Result, BudgetReservation, IdempotencyRecord
- **Routing**: RoutingDecision, ResourceAssignment, ResourceConstraints
- **Content**: Script, ScriptScene, SpeechManifest, VisualIntent, Claim, Evidence
- **Composition**: CompositionSpec, Scene, Shot, Layer, AudioTrack, RenderProfile
- **Artifacts**: Artifact, ArtifactDependency, ArtifactPointer, Invalidation
- **Quality**: QualityCheck, QualityEvaluation, QualityGatePolicy, RepairPlan
- **Events**: EventEnvelope, OutboxMessage, InboxReceipt
- **Editorial**: ContentPackage, Episode, Sequence, Scene, Shot, Layer, Cut
- **Review**: HumanReview, HumanReviewDecision, PublicationAttempt/Request
- **Jobs**: Job, Lease, RecoveryPolicy, RetryPolicy
- **Routing**: RoutingDecision, ResourceAssignment, ResourceConstraints
- **Profiles**: DomainProfile, ChannelProfile, SystemPolicy, BudgetPolicy

Contract Invariants:
- No unknown core fields accepted (extra='forbid')
- Cross-field references validated (artifact hashes, IDs, foreign keys)
- Pydantic models validate on construction; mutability varies by model
- Deterministic JSON serialization (sorted keys, UTC normalization)
- Fixtures for every public contract in fixtures/contracts/valid/

Schema Export:
- `python -m pipeline contracts export-schemas` writes JSON Schemas to schemas/
- Schemas are committed and checked into version control
- `python -m pipeline contracts export-schemas --check` validates CI
"""

from __future__ import annotations

from pipeline.contracts.artifacts import (
    Artifact,
    ArtifactDependency,
    ArtifactPointer,
    InvalidationRequest,
    InvalidationResult,
)
from pipeline.contracts.base import (
    Contract,
    ExtensionArray,
    ExtensionObject,
    MetadataContract,
    NormalizedError,
    UTCDateTime,
    UTCRecord,
)
from pipeline.contracts.capabilities import (
    BudgetReservation,
    CapabilityExecution,
    CapabilityRequest,
    CapabilityRequirements,
    CapabilityResult,
    ExecutionContext,
    IdempotencyRecord,
    UsageRecord,
)
from pipeline.contracts.capability_payloads import (
    ASRAlignmentInputPayload,
    ASRAlignmentOutputPayload,
    AssemblyInputPayload,
    AssemblyOutputPayload,
    AudioQCInputPayload,
    AudioQCOutputPayload,
    CompositionInputPayload,
    CompositionOutputPayload,
    RenderingInputPayload,
    RenderingOutputPayload,
    ResearchInputPayload,
    ResearchOutputPayload,
    ScriptGenerationInputPayload,
    ScriptGenerationOutputPayload,
    ShortDerivativeInputPayload,
    ShortDerivativeOutputPayload,
    SpeechGenerationInputPayload,
    SpeechGenerationOutputPayload,
    TTSAdapterInputPayload,
    TTSAdapterOutputPayload,
    VisualPlanningInputPayload,
    VisualPlanningOutputPayload,
)
from pipeline.contracts.composition import (
    AssemblyManifest,
    CompositionAudioTrackSpec,
    CompositionAuthoringSpec,
    CompositionLayerSpec,
    CompositionSceneSpec,
    CompositionSequenceSpec,
    CompositionShotSpec,
    CompositionSpec,
    RenderChunkManifest,
    RenderProfile,
    ResolvedArtifactRef,
    ShortSelectionManifest,
)
from pipeline.contracts.config import EffectiveConfig, RunOverrides
from pipeline.contracts.content import (
    AudioTiming,
    Claim,
    DurationPolicy,
    Evidence,
    Script,
    ScriptScene,
    SourceRef,
    SourceSnapshot,
    SpeechManifest,
    VisualIntent,
    WordTimestamp,
)
from pipeline.contracts.editorial import (
    CompositionRef,
    ContentPackage,
    Cut,
    Episode,
    LayerInstance,
    Scene,
    Sequence,
    Shot,
)
from pipeline.contracts.events import EventEnvelope, InboxReceipt, OutboxMessage
from pipeline.contracts.execution import (
    InputManifest,
    RecoveryDecision,
    RecoveryPolicy,
    RetryPolicy,
    RunCreateRequest,
    StageAttempt,
    StageInstance,
    WorkflowRun,
)
from pipeline.contracts.jobs import Job, Lease
from pipeline.contracts.profiles import (
    BudgetPolicy,
    ChannelProfile,
    DomainProfile,
    SystemPolicy,
)
from pipeline.contracts.quality import (
    EvaluationDimension,
    QualityCheck,
    QualityEvaluation,
    QualityGatePolicy,
    QualityGateResult,
    QualityInputManifest,
    RepairPlan,
)
from pipeline.contracts.registry import (
    CONTRACT_MODELS,
    PUBLIC_CONTRACTS,
    contract_schema_version,
    schema_file_name,
)
from pipeline.contracts.review import (
    HumanReview,
    HumanReviewDecision,
    PublicationAttempt,
    PublicationRequest,
)
from pipeline.contracts.routing import (
    ProviderInvocation,
    ResourceAssignment,
    ResourceConstraints,
    RoutingContext,
    RoutingDecision,
    WorkloadRequirements,
)
from pipeline.contracts.vocabularies import (
    AcceptanceStatus,
    ArtifactPointerType,
    ArtifactState,
    AttemptStatus,
    BudgetReservationStatus,
    BudgetScopeType,
    CapabilityExecutionStatus,
    CapabilityResultStatus,
    CardinalityMode,
    CheckOutcome,
    ConditionOperator,
    Confidence,
    DuplicatePolicy,
    EditorialCutKind,
    EvaluationKind,
    EventType,
    FailureCategory,
    FailureCode,
    GateDecision,
    IdempotencyStatus,
    InboxStatus,
    InputSelectorKind,
    InvalidationScope,
    JobStatus,
    LayerKind,
    OutboxStatus,
    ProviderInvocationStatus,
    PublicationStatus,
    QualityFailureAction,
    RecoveryAction,
    RepairInvalidationScope,
    RepairScope,
    RepeatedFailureAction,
    ReviewDecision,
    ReviewStatus,
    RunStatus,
    Severity,
    SourceKind,
    SpeechStrategy,
    StageExecutionStatus,
    StageName,
    UnknownOutcomeAction,
)
from pipeline.contracts.workflow import (
    CardinalityPolicy,
    ConditionExpression,
    InputSelector,
    StageNode,
    WorkflowDefinition,
)

__all__ = [
    "CONTRACT_MODELS",
    "PUBLIC_CONTRACTS",
    "ASRAlignmentInputPayload",
    "ASRAlignmentOutputPayload",
    "AcceptanceStatus",
    "Artifact",
    "ArtifactDependency",
    "ArtifactPointer",
    "ArtifactPointerType",
    "ArtifactState",
    "AssemblyInputPayload",
    "AssemblyManifest",
    "AssemblyOutputPayload",
    "AttemptStatus",
    "AudioQCInputPayload",
    "AudioQCOutputPayload",
    "AudioTiming",
    "BudgetPolicy",
    "BudgetReservation",
    "BudgetReservationStatus",
    "BudgetScopeType",
    "CapabilityExecution",
    "CapabilityExecutionStatus",
    "CapabilityRequest",
    "CapabilityRequirements",
    "CapabilityResult",
    "CapabilityResultStatus",
    "CardinalityMode",
    "CardinalityPolicy",
    "ChannelProfile",
    "CheckOutcome",
    "Claim",
    "CompositionAudioTrackSpec",
    "CompositionAuthoringSpec",
    "CompositionInputPayload",
    "CompositionLayerSpec",
    "CompositionOutputPayload",
    "CompositionRef",
    "CompositionSceneSpec",
    "CompositionSequenceSpec",
    "CompositionShotSpec",
    "CompositionSpec",
    "ConditionExpression",
    "ConditionOperator",
    "Confidence",
    "ContentPackage",
    "Contract",
    "Cut",
    "DomainProfile",
    "DuplicatePolicy",
    "DurationPolicy",
    "EditorialCutKind",
    "EffectiveConfig",
    "Episode",
    "EvaluationDimension",
    "EvaluationKind",
    "EventEnvelope",
    "EventType",
    "Evidence",
    "ExecutionContext",
    "ExtensionArray",
    "ExtensionObject",
    "FailureCategory",
    "FailureCode",
    "GateDecision",
    "HumanReview",
    "HumanReviewDecision",
    "IdempotencyRecord",
    "IdempotencyStatus",
    "InboxReceipt",
    "InboxStatus",
    "InputManifest",
    "InputSelector",
    "InputSelectorKind",
    "InvalidationRequest",
    "InvalidationResult",
    "InvalidationScope",
    "Job",
    "JobStatus",
    "LayerInstance",
    "LayerKind",
    "Lease",
    "MetadataContract",
    "NormalizedError",
    "OutboxMessage",
    "OutboxStatus",
    "ProviderInvocation",
    "ProviderInvocationStatus",
    "PublicationAttempt",
    "PublicationRequest",
    "PublicationStatus",
    "QualityCheck",
    "QualityEvaluation",
    "QualityFailureAction",
    "QualityGatePolicy",
    "QualityGateResult",
    "QualityInputManifest",
    "RecoveryAction",
    "RecoveryDecision",
    "RecoveryPolicy",
    "RenderChunkManifest",
    "RenderProfile",
    "RenderingInputPayload",
    "RenderingOutputPayload",
    "RepairInvalidationScope",
    "RepairPlan",
    "RepairScope",
    "RepeatedFailureAction",
    "ResearchInputPayload",
    "ResearchOutputPayload",
    "ResolvedArtifactRef",
    "ResourceAssignment",
    "ResourceConstraints",
    "RetryPolicy",
    "ReviewDecision",
    "ReviewStatus",
    "RoutingContext",
    "RoutingDecision",
    "RunCreateRequest",
    "RunOverrides",
    "RunStatus",
    "Scene",
    "Script",
    "ScriptGenerationInputPayload",
    "ScriptGenerationOutputPayload",
    "ScriptScene",
    "Sequence",
    "Severity",
    "ShortDerivativeInputPayload",
    "ShortDerivativeOutputPayload",
    "ShortSelectionManifest",
    "Shot",
    "SourceKind",
    "SourceRef",
    "SourceSnapshot",
    "SpeechGenerationInputPayload",
    "SpeechGenerationOutputPayload",
    "SpeechManifest",
    "SpeechStrategy",
    "StageAttempt",
    "StageExecutionStatus",
    "StageInstance",
    "StageName",
    "StageNode",
    "SystemPolicy",
    "TTSAdapterInputPayload",
    "TTSAdapterOutputPayload",
    "UTCDateTime",
    "UTCRecord",
    "UnknownOutcomeAction",
    "UsageRecord",
    "VisualIntent",
    "VisualPlanningInputPayload",
    "VisualPlanningOutputPayload",
    "WordTimestamp",
    "WorkflowDefinition",
    "WorkflowRun",
    "WorkloadRequirements",
    "contract_schema_version",
    "schema_file_name",
]
