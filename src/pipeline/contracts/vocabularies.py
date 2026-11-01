"""Stable state, failure, stage, event, and policy vocabularies.

The values in this module come from the canonical contracts document and the
machine-readable registries under ``docs/kb/docs/registries``. They are the
only vocabularies that contract models may use for core state transitions.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class RunStatus(StrEnum):
    """Lifecycle of one workflow run."""

    CREATED = "CREATED"
    RUNNING = "RUNNING"
    WAITING_HUMAN = "WAITING_HUMAN"
    WAITING_RETRY = "WAITING_RETRY"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StageExecutionStatus(StrEnum):
    """Durable execution state of one logical stage instance."""

    PENDING = "PENDING"
    READY = "READY"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    WAITING_HUMAN = "WAITING_HUMAN"
    WAITING_RETRY = "WAITING_RETRY"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"
    INVALIDATED = "INVALIDATED"


class AttemptStatus(StrEnum):
    """Lifecycle of one claimable execution attempt."""

    CREATED = "CREATED"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    CANCELLED = "CANCELLED"


class AcceptanceStatus(StrEnum):
    """Quality-acceptance state kept separate from execution state."""

    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    PASSED = "PASSED"
    REGENERATE = "REGENERATE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    FAILED = "FAILED"


class GateDecision(StrEnum):
    """Aggregate control-plane action for one quality gate."""

    PASS = "PASS"
    REGENERATE = "REGENERATE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    FAIL = "FAIL"


class CheckOutcome(StrEnum):
    """Outcome of one quality check, distinct from a gate decision."""

    PASS = "PASS"
    FAIL = "FAIL"
    ABSTAIN = "ABSTAIN"
    ERROR = "ERROR"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ArtifactState(StrEnum):
    """Lifecycle of an immutable artifact version."""

    GENERATED = "GENERATED"
    ACCEPTED = "ACCEPTED"
    SUPERSEDED = "SUPERSEDED"
    INVALIDATED = "INVALIDATED"
    DELETED = "DELETED"


class Severity(StrEnum):
    """Severity used by normalized errors and quality evidence."""

    INFO = "INFO"
    MINOR = "MINOR"
    MAJOR = "MAJOR"
    CRITICAL = "CRITICAL"


class FailureCategory(StrEnum):
    """Stable failure categories from the canonical failure-code registry."""

    VALIDATION = "VALIDATION"
    AUTHENTICATION = "AUTHENTICATION"
    AUTHORIZATION = "AUTHORIZATION"
    RATE_LIMIT = "RATE_LIMIT"
    QUOTA = "QUOTA"
    TRANSIENT = "TRANSIENT"
    PERMANENT = "PERMANENT"
    UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"
    MEDIA = "MEDIA"
    QUALITY = "QUALITY"
    BUDGET = "BUDGET"
    CONFIGURATION = "CONFIGURATION"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    POLICY = "POLICY"
    INTERNAL = "INTERNAL"


class FailureCode(StrEnum):
    """Namespaced failure codes registered for recovery decisions."""

    VALIDATION = "EXEC.VALIDATION"
    AUTHENTICATION = "EXEC.AUTHENTICATION"
    AUTHORIZATION = "EXEC.AUTHORIZATION"
    RATE_LIMIT = "EXEC.RATE_LIMIT"
    QUOTA = "EXEC.QUOTA"
    TRANSIENT_PROVIDER = "EXEC.TRANSIENT_PROVIDER"
    PERMANENT_PROVIDER = "EXEC.PERMANENT_PROVIDER"
    INTERNAL = "EXEC.INTERNAL"
    TIMEOUT_UNKNOWN = "EXEC.TIMEOUT_UNKNOWN"
    MEDIA_DECODE_ERROR = "MEDIA.DECODE_ERROR"
    MEDIA_OUTPUT_PROFILE = "MEDIA.OUTPUT_PROFILE"
    MEDIA_TIMELINE_INVALID = "MEDIA.TIMELINE_INVALID"
    MEDIA_TECHNICAL_INTEGRITY = "MEDIA.TECHNICAL_INTEGRITY"
    QUALITY_SCHEMA_INVALID = "QUALITY.SCHEMA_INVALID"
    QUALITY_GENERIC = "QUALITY.GENERIC"
    QUALITY_UNSUPPORTED_CLAIM = "QUALITY.UNSUPPORTED_CLAIM"
    QUALITY_NUMERIC_CONTRADICTION = "QUALITY.NUMERIC_CONTRADICTION"
    QUALITY_TTS_OMISSION = "QUALITY.TTS_OMISSION"
    QUALITY_TTS_PRONUNCIATION = "QUALITY.TTS_PRONUNCIATION"
    QUALITY_VISUAL_MISMATCH = "QUALITY.VISUAL_MISMATCH"
    QUALITY_MISSING_ASSET = "QUALITY.MISSING_ASSET"
    QUALITY_PROVENANCE_MISSING = "QUALITY.PROVENANCE_MISSING"
    QUALITY_CAPTION_OVERFLOW = "QUALITY.CAPTION_OVERFLOW"
    QUALITY_AUDIO_DECODE = "QUALITY.AUDIO_DECODE"
    MEDIA_RENDER_CORRUPT = "MEDIA.RENDER_CORRUPT"
    MEDIA_AUDIO_VIDEO_DRIFT = "MEDIA.AUDIO_VIDEO_DRIFT"
    QUALITY_REPEATED_FAILURE = "QUALITY.REPEATED_FAILURE"
    RIGHTS_LICENSE_UNCERTAIN = "RIGHTS.LICENSE_UNCERTAIN"
    HUMAN_REVIEW_REQUIRED = "HUMAN.REVIEW_REQUIRED"
    POLICY_BUDGET_EXCEEDED = "POLICY.BUDGET_EXCEEDED"
    POLICY_PROHIBITED_CONTENT = "POLICY.PROHIBITED_CONTENT"
    CONFIG_UNKNOWN_STAGE = "CONFIG.UNKNOWN_STAGE"


FAILURE_CODE_CATEGORIES: Final[dict[FailureCode, FailureCategory]] = {
    FailureCode.VALIDATION: FailureCategory.VALIDATION,
    FailureCode.AUTHENTICATION: FailureCategory.AUTHENTICATION,
    FailureCode.AUTHORIZATION: FailureCategory.AUTHORIZATION,
    FailureCode.RATE_LIMIT: FailureCategory.RATE_LIMIT,
    FailureCode.QUOTA: FailureCategory.QUOTA,
    FailureCode.TRANSIENT_PROVIDER: FailureCategory.TRANSIENT,
    FailureCode.PERMANENT_PROVIDER: FailureCategory.PERMANENT,
    FailureCode.INTERNAL: FailureCategory.INTERNAL,
    FailureCode.TIMEOUT_UNKNOWN: FailureCategory.UNKNOWN_OUTCOME,
    FailureCode.MEDIA_DECODE_ERROR: FailureCategory.MEDIA,
    FailureCode.MEDIA_OUTPUT_PROFILE: FailureCategory.MEDIA,
    FailureCode.MEDIA_TIMELINE_INVALID: FailureCategory.MEDIA,
    FailureCode.MEDIA_TECHNICAL_INTEGRITY: FailureCategory.MEDIA,
    FailureCode.QUALITY_SCHEMA_INVALID: FailureCategory.QUALITY,
    FailureCode.QUALITY_GENERIC: FailureCategory.QUALITY,
    FailureCode.QUALITY_UNSUPPORTED_CLAIM: FailureCategory.QUALITY,
    FailureCode.QUALITY_NUMERIC_CONTRADICTION: FailureCategory.QUALITY,
    FailureCode.QUALITY_TTS_OMISSION: FailureCategory.QUALITY,
    FailureCode.QUALITY_TTS_PRONUNCIATION: FailureCategory.QUALITY,
    FailureCode.QUALITY_VISUAL_MISMATCH: FailureCategory.QUALITY,
    FailureCode.QUALITY_MISSING_ASSET: FailureCategory.QUALITY,
    FailureCode.QUALITY_PROVENANCE_MISSING: FailureCategory.QUALITY,
    FailureCode.QUALITY_CAPTION_OVERFLOW: FailureCategory.QUALITY,
    FailureCode.QUALITY_AUDIO_DECODE: FailureCategory.QUALITY,
    FailureCode.MEDIA_RENDER_CORRUPT: FailureCategory.MEDIA,
    FailureCode.MEDIA_AUDIO_VIDEO_DRIFT: FailureCategory.MEDIA,
    FailureCode.QUALITY_REPEATED_FAILURE: FailureCategory.QUALITY,
    FailureCode.RIGHTS_LICENSE_UNCERTAIN: FailureCategory.POLICY,
    FailureCode.HUMAN_REVIEW_REQUIRED: FailureCategory.HUMAN_REVIEW,
    FailureCode.POLICY_BUDGET_EXCEEDED: FailureCategory.BUDGET,
    FailureCode.POLICY_PROHIBITED_CONTENT: FailureCategory.POLICY,
    FailureCode.CONFIG_UNKNOWN_STAGE: FailureCategory.CONFIGURATION,
}


class StageName(StrEnum):
    """Canonical stage names from ``registries/stages.yaml``."""

    MANUAL_TOPIC = "manual_topic"
    TOPIC_DISCOVERY = "topic_discovery"
    IDEA_DEVELOPMENT = "idea_development"
    RESEARCH = "research"
    SCRIPT_GENERATION = "script_generation"
    VISUAL_PLANNING = "visual_planning"
    ASSET_ACQUISITION = "asset_acquisition"
    SPEECH_GENERATION = "speech_generation"
    COMPOSITION = "composition"
    RENDERING = "rendering"
    ASSEMBLY = "assembly"
    SHORT_DERIVATIVE = "short_derivative"
    TECHNICAL_CONTENT_REVIEW = "technical_content_review"
    HUMAN_APPROVAL = "human_approval"
    PUBLISHING = "publishing"
    ANALYTICS_LEARNING = "analytics_learning"


STAGE_NAMES: Final[frozenset[str]] = frozenset(member.value for member in StageName)

QUALITY_GATE_IDS: Final[frozenset[str]] = frozenset(
    {
        "research_gate_v1",
        "script_gate_v1",
        "visual_plan_gate_v1",
        "asset_gate_v1",
        "speech_gate_v1",
        "composition_gate_v1",
        "render_gate_v1",
        "assembly_gate_v1",
        "short_gate_v1",
        "final_gate_v1",
        "human_publication_gate_v1",
    }
)

RECOVERY_POLICY_IDS: Final[frozenset[str]] = frozenset({"default_recovery_v1"})
RETRY_POLICY_IDS: Final[frozenset[str]] = frozenset({"default_retry_v1"})


class EventType(StrEnum):
    """Canonical lowercase-dot event names from ``registries/events.yaml``."""

    WORKFLOW_CREATED = "workflow.created"
    WORKFLOW_STARTED = "workflow.started"
    STAGE_READY = "stage.ready"
    STAGE_CLAIMED = "stage.claimed"
    STAGE_STARTED = "stage.started"
    STAGE_SUCCEEDED = "stage.succeeded"
    STAGE_FAILED = "stage.failed"
    STAGE_UNKNOWN = "stage.unknown"
    ARTIFACT_CREATED = "artifact.created"
    ARTIFACT_INVALIDATED = "artifact.invalidated"
    QUALITY_REQUESTED = "quality.requested"
    QUALITY_EVALUATED = "quality.evaluated"
    REPAIR_REQUESTED = "repair.requested"
    HUMAN_REVIEW_REQUESTED = "human_review.requested"
    HUMAN_REVIEW_COMPLETED = "human_review.completed"
    WORKFLOW_PAUSED = "workflow.paused"
    WORKFLOW_RESUMED = "workflow.resumed"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    PUBLISH_REQUESTED = "publish.requested"
    PUBLISH_COMPLETED = "publish.completed"


# Every canonical event maps to exactly one registered payload schema version.
EVENT_PAYLOAD_SCHEMAS: Final[dict[EventType, str]] = {
    EventType.WORKFLOW_CREATED: "workflow-created.v1",
    EventType.WORKFLOW_STARTED: "workflow-started.v1",
    EventType.STAGE_READY: "stage-ready.v1",
    EventType.STAGE_CLAIMED: "stage-claimed.v1",
    EventType.STAGE_STARTED: "stage-started.v1",
    EventType.STAGE_SUCCEEDED: "stage-succeeded.v1",
    EventType.STAGE_FAILED: "stage-failed.v1",
    EventType.STAGE_UNKNOWN: "stage-unknown.v1",
    EventType.ARTIFACT_CREATED: "artifact-created.v1",
    EventType.ARTIFACT_INVALIDATED: "artifact-invalidated.v1",
    EventType.QUALITY_REQUESTED: "quality-requested.v1",
    EventType.QUALITY_EVALUATED: "quality-evaluated.v1",
    EventType.REPAIR_REQUESTED: "repair-requested.v1",
    EventType.HUMAN_REVIEW_REQUESTED: "human-review-requested.v1",
    EventType.HUMAN_REVIEW_COMPLETED: "human-review-completed.v1",
    EventType.WORKFLOW_PAUSED: "workflow-paused.v1",
    EventType.WORKFLOW_RESUMED: "workflow-resumed.v1",
    EventType.WORKFLOW_COMPLETED: "workflow-completed.v1",
    EventType.WORKFLOW_FAILED: "workflow-failed.v1",
    EventType.PUBLISH_REQUESTED: "publish-requested.v1",
    EventType.PUBLISH_COMPLETED: "publish-completed.v1",
}

EVENT_PAYLOAD_REQUIRED_FIELDS: Final[dict[str, frozenset[str]]] = {
    "workflow-created.v1": frozenset({"run_id", "workflow_id", "workflow_version"}),
    "workflow-started.v1": frozenset({"run_id"}),
    "stage-ready.v1": frozenset({"run_id", "stage_instance_id", "job_id"}),
    "stage-claimed.v1": frozenset(
        {"run_id", "stage_instance_id", "attempt_id", "job_id"}
    ),
    "stage-started.v1": frozenset({"run_id", "stage_instance_id", "attempt_id"}),
    "stage-succeeded.v1": frozenset(
        {"run_id", "stage_instance_id", "attempt_id", "artifact_ids"}
    ),
    "stage-failed.v1": frozenset(
        {"run_id", "stage_instance_id", "attempt_id", "failure_code"}
    ),
    "stage-unknown.v1": frozenset(
        {"run_id", "stage_instance_id", "attempt_id", "recovery_decision_id"}
    ),
    "artifact-created.v1": frozenset({"run_id", "artifact_id", "sha256"}),
    "artifact-invalidated.v1": frozenset(
        {"run_id", "artifact_id", "invalidation_request_id"}
    ),
    "quality-requested.v1": frozenset(
        {"run_id", "stage_instance_id", "quality_input_manifest_id"}
    ),
    "quality-evaluated.v1": frozenset(
        {"run_id", "stage_instance_id", "quality_gate_result_id"}
    ),
    "repair-requested.v1": frozenset({"run_id", "repair_plan_id"}),
    "human-review-requested.v1": frozenset(
        {"run_id", "review_id", "target_artifact_ids"}
    ),
    "human-review-completed.v1": frozenset({"run_id", "review_id", "decision"}),
    "workflow-paused.v1": frozenset({"run_id", "reason_codes"}),
    "workflow-resumed.v1": frozenset({"run_id"}),
    "workflow-completed.v1": frozenset({"run_id"}),
    "workflow-failed.v1": frozenset({"run_id", "reason_codes"}),
    "publish-requested.v1": frozenset({"run_id", "cut_ids", "approval_ids"}),
    "publish-completed.v1": frozenset(
        {"run_id", "publication_id", "published_artifact_ids"}
    ),
}


class JobStatus(StrEnum):
    READY = "READY"
    CLAIMED = "CLAIMED"
    ACKED = "ACKED"
    RETRY = "RETRY"
    DEAD_LETTER = "DEAD_LETTER"
    CANCELLED = "CANCELLED"


class CapabilityResultStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class CapabilityExecutionStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class IdempotencyStatus(StrEnum):
    RESERVED = "RESERVED"
    IN_FLIGHT = "IN_FLIGHT"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    RECONCILED = "RECONCILED"


class BudgetScopeType(StrEnum):
    SYSTEM = "SYSTEM"
    MONTH = "MONTH"
    RUN = "RUN"
    STAGE = "STAGE"
    CAPABILITY = "CAPABILITY"


class BudgetReservationStatus(StrEnum):
    RESERVED = "RESERVED"
    SETTLED = "SETTLED"
    RELEASED = "RELEASED"
    UNKNOWN = "UNKNOWN"


class ProviderInvocationStatus(StrEnum):
    STARTED = "STARTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class OutboxStatus(StrEnum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"


class InboxStatus(StrEnum):
    RECEIVED = "RECEIVED"
    PROCESSED = "PROCESSED"
    IGNORED = "IGNORED"
    FAILED = "FAILED"


class ReviewStatus(StrEnum):
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    RESOLVED = "RESOLVED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class ReviewDecision(StrEnum):
    APPROVE = "APPROVE"
    REGENERATE_SCENE = "REGENERATE_SCENE"
    REGENERATE_STAGE = "REGENERATE_STAGE"
    REJECT = "REJECT"


class PublicationStatus(StrEnum):
    PENDING = "PENDING"
    STARTED = "STARTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class RecoveryAction(StrEnum):
    RESUME = "RESUME"
    RETRY = "RETRY"
    RECONCILE = "RECONCILE"
    REGENERATE = "REGENERATE"
    WAIT_HUMAN = "WAIT_HUMAN"
    FAIL = "FAIL"


class UnknownOutcomeAction(StrEnum):
    RECONCILE = "RECONCILE"
    RETRY = "RETRY"
    WAIT_HUMAN = "WAIT_HUMAN"
    FAIL = "FAIL"


class QualityFailureAction(StrEnum):
    REGENERATE = "REGENERATE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    FAIL = "FAIL"


class RepeatedFailureAction(StrEnum):
    HUMAN_REVIEW = "HUMAN_REVIEW"
    FAIL = "FAIL"


class EvaluationKind(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    SPECIALIZED = "SPECIALIZED"
    SEMANTIC = "SEMANTIC"
    HUMAN = "HUMAN"


class RepairScope(StrEnum):
    NONE = "NONE"
    LAYER = "LAYER"
    ASSET = "ASSET"
    SHOT = "SHOT"
    SCENE = "SCENE"
    STAGE = "STAGE"
    CUT = "CUT"
    SUBGRAPH = "SUBGRAPH"
    WORKFLOW = "WORKFLOW"


class InvalidationScope(StrEnum):
    ARTIFACT = "artifact"
    SCENE = "scene"
    SUBGRAPH = "subgraph"
    WORKFLOW = "workflow"


class RepairInvalidationScope(StrEnum):
    ARTIFACT = "ARTIFACT"
    SCENE = "SCENE"
    SUBGRAPH = "SUBGRAPH"
    WORKFLOW = "WORKFLOW"


class Confidence(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ArtifactPointerType(StrEnum):
    CURRENT = "CURRENT"
    ACCEPTED = "ACCEPTED"
    PUBLISHED = "PUBLISHED"


class InputSelectorKind(StrEnum):
    RUN_INPUT = "RUN_INPUT"
    DEPENDENCY_OUTPUTS = "DEPENDENCY_OUTPUTS"
    MANIFEST = "MANIFEST"
    POINTERS = "POINTERS"


class ConditionOperator(StrEnum):
    ALWAYS = "ALWAYS"
    ALL = "ALL"
    ANY = "ANY"
    EQUALS = "EQUALS"
    IN = "IN"
    GREATER_THAN = "GREATER_THAN"
    EXISTS = "EXISTS"


class CardinalityMode(StrEnum):
    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    MANY_TO_MANY = "many_to_many"


class DuplicatePolicy(StrEnum):
    RETURN_EXISTING = "RETURN_EXISTING"
    REJECT = "REJECT"
    CREATE_NEW = "CREATE_NEW"


class EditorialCutKind(StrEnum):
    LONG_FORM = "LONG_FORM"
    SHORT = "SHORT"


class LayerKind(StrEnum):
    VIDEO = "VIDEO"
    IMAGE = "IMAGE"
    SHAPE = "SHAPE"
    CHART = "CHART"
    CODE = "CODE"
    TEXT = "TEXT"
    CAPTION = "CAPTION"
    AUDIO_VOICE = "AUDIO_VOICE"
    AUDIO_MUSIC = "AUDIO_MUSIC"
    AUDIO_EFFECT = "AUDIO_EFFECT"
    MASK = "MASK"
    TRANSITION = "TRANSITION"


class SourceKind(StrEnum):
    STOCK = "STOCK"
    PUBLIC_DOMAIN = "PUBLIC_DOMAIN"
    GENERATED = "GENERATED"
    PROCEDURAL = "PROCEDURAL"
    USER_SUPPLIED = "USER_SUPPLIED"


class SpeechStrategy(StrEnum):
    CONTINUOUS = "CONTINUOUS"
    SCENE_SEGMENTED = "SCENE_SEGMENTED"


def enum_values(enum_type: type[StrEnum]) -> tuple[str, ...]:
    """Return enum values in declaration order for deterministic exports."""

    return tuple(member.value for member in enum_type)


__all__ = [
    "EVENT_PAYLOAD_REQUIRED_FIELDS",
    "EVENT_PAYLOAD_SCHEMAS",
    "FAILURE_CODE_CATEGORIES",
    "QUALITY_GATE_IDS",
    "RECOVERY_POLICY_IDS",
    "RETRY_POLICY_IDS",
    "STAGE_NAMES",
    "AcceptanceStatus",
    "ArtifactPointerType",
    "ArtifactState",
    "AttemptStatus",
    "BudgetReservationStatus",
    "BudgetScopeType",
    "CapabilityExecutionStatus",
    "CapabilityResultStatus",
    "CardinalityMode",
    "CheckOutcome",
    "ConditionOperator",
    "Confidence",
    "DuplicatePolicy",
    "EditorialCutKind",
    "EvaluationKind",
    "EventType",
    "FailureCategory",
    "FailureCode",
    "GateDecision",
    "IdempotencyStatus",
    "InboxStatus",
    "InputSelectorKind",
    "InvalidationScope",
    "JobStatus",
    "LayerKind",
    "OutboxStatus",
    "ProviderInvocationStatus",
    "PublicationStatus",
    "QualityFailureAction",
    "RecoveryAction",
    "RepairInvalidationScope",
    "RepairScope",
    "RepeatedFailureAction",
    "ReviewDecision",
    "ReviewStatus",
    "RunStatus",
    "Severity",
    "SourceKind",
    "SpeechStrategy",
    "StageExecutionStatus",
    "StageName",
    "UnknownOutcomeAction",
    "enum_values",
]
