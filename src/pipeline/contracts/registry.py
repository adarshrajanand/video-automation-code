"""Deterministic registry of public contract models and schema versions."""

from __future__ import annotations

from typing import get_args

from pipeline.contracts.artifacts import (
    Artifact,
    ArtifactDependency,
    ArtifactPointer,
    InvalidationRequest,
    InvalidationResult,
)
from pipeline.contracts.base import Contract, NormalizedError
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
from pipeline.contracts.workflow import (
    CardinalityPolicy,
    ConditionExpression,
    InputSelector,
    StageNode,
    WorkflowDefinition,
)

# Declaration order is stable and grouped by contract family. Schema export and
# fixture tests consume this registry rather than discovering modules.
CONTRACT_MODELS: tuple[type[Contract], ...] = (
    # Common failure vocabulary
    NormalizedError,
    # Configuration
    RunOverrides,
    EffectiveConfig,
    # Workflow
    InputSelector,
    ConditionExpression,
    CardinalityPolicy,
    StageNode,
    WorkflowDefinition,
    # Run and execution
    WorkflowRun,
    RunCreateRequest,
    StageInstance,
    StageAttempt,
    InputManifest,
    RetryPolicy,
    RecoveryPolicy,
    RecoveryDecision,
    # Job and lease
    Job,
    Lease,
    # Capability and budget control
    CapabilityRequirements,
    CapabilityRequest,
    ExecutionContext,
    UsageRecord,
    CapabilityResult,
    CapabilityExecution,
    IdempotencyRecord,
    BudgetReservation,
    # Routing and providers
    RoutingContext,
    RoutingDecision,
    WorkloadRequirements,
    ResourceConstraints,
    ResourceAssignment,
    ProviderInvocation,
    # Artifacts
    Artifact,
    ArtifactDependency,
    ArtifactPointer,
    InvalidationRequest,
    InvalidationResult,
    # Quality
    EvaluationDimension,
    QualityCheck,
    QualityInputManifest,
    QualityGatePolicy,
    QualityEvaluation,
    QualityGateResult,
    RepairPlan,
    # Human review and publication boundary
    HumanReview,
    HumanReviewDecision,
    PublicationRequest,
    PublicationAttempt,
    # Events and delivery
    EventEnvelope,
    OutboxMessage,
    InboxReceipt,
    # Profiles
    BudgetPolicy,
    SystemPolicy,
    DomainProfile,
    ChannelProfile,
    # Editorial references
    ContentPackage,
    Episode,
    Cut,
    Sequence,
    Scene,
    Shot,
    LayerInstance,
    CompositionRef,
    # Composition, rendering, assembly, short derivative
    CompositionLayerSpec,
    CompositionShotSpec,
    CompositionSceneSpec,
    CompositionSequenceSpec,
    CompositionAudioTrackSpec,
    CompositionAuthoringSpec,
    CompositionSpec,
    ResolvedArtifactRef,
    RenderProfile,
    RenderChunkManifest,
    AssemblyManifest,
    ShortSelectionManifest,
    # Content stage contracts
    SourceRef,
    SourceSnapshot,
    Evidence,
    Claim,
    VisualIntent,
    DurationPolicy,
    ScriptScene,
    Script,
    AudioTiming,
    SpeechManifest,
    WordTimestamp,
    # Capability payloads
    ResearchInputPayload,
    ResearchOutputPayload,
    ScriptGenerationInputPayload,
    ScriptGenerationOutputPayload,
    VisualPlanningInputPayload,
    VisualPlanningOutputPayload,
    SpeechGenerationInputPayload,
    SpeechGenerationOutputPayload,
    TTSAdapterInputPayload,
    TTSAdapterOutputPayload,
    ASRAlignmentInputPayload,
    ASRAlignmentOutputPayload,
    AudioQCInputPayload,
    AudioQCOutputPayload,
    CompositionInputPayload,
    CompositionOutputPayload,
    RenderingInputPayload,
    RenderingOutputPayload,
    AssemblyInputPayload,
    AssemblyOutputPayload,
    ShortDerivativeInputPayload,
    ShortDerivativeOutputPayload,
)

PUBLIC_CONTRACTS: dict[str, type[Contract]] = {
    model.__name__: model for model in CONTRACT_MODELS
}


def contract_schema_version(model: type[Contract]) -> str:
    """Return the literal schema version declared by a public contract."""

    field = model.model_fields.get("schema_version")
    if field is None:
        raise ValueError(f"{model.__name__} does not declare schema_version")
    values = get_args(field.annotation)
    if len(values) != 1 or not isinstance(values[0], str):
        raise ValueError(
            f"{model.__name__}.schema_version must be a single string Literal"
        )
    return values[0]


def schema_file_name(model: type[Contract]) -> str:
    """Return the deterministic JSON Schema file name for a contract."""

    return f"{model.__name__}.schema.json"


__all__ = [
    "CONTRACT_MODELS",
    "PUBLIC_CONTRACTS",
    "contract_schema_version",
    "schema_file_name",
]
