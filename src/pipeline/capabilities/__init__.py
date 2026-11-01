"""Provider-independent capability boundary and fake provider layer.

This module implements the capability system for FV-06, providing a
provider-independent abstraction layer for executing capabilities.

Architecture:
- **CapabilityRegistry**: Thread-safe registry mapping (capability, version)
  to implementations with provider/model/feature/locale filtering
- **CapabilityExecutor**: Executes capabilities with idempotency, budget
  enforcement, and persistence
- **FakeCapabilityProvider**: Deterministic fake provider for testing/local
  execution with scripted outcomes
- **Normalized Errors**: Standardized error taxonomy with categories,
  retryability, and reconciliation requirements

Key Components:
- **CapabilityRegistry**: Maps (capability, operation_version) to
  implementations with provider/model/feature/locale filtering
- **CapabilityExecutor**: Executes requests with idempotency, budget
  guard, and persistence (RoutingDecision, CapabilityExecution,
  ProviderInvocation, CapabilityResult, UsageRecord)
- **FakeCapabilityProvider**: Deterministic fake for testing with
  scripted outcomes for all failure categories
- **Normalized Errors**: Standardized error taxonomy with category,
  retryability, and reconciliation requirements

Provider Independence:
Stages and workflows MUST call this boundary; they MUST NOT import
provider SDKs, HTTP clients, or vendor packages directly. The executor
accepts explicit RoutingDecision/ResourceAssignment and never makes
network calls itself.

Error Taxonomy:
Errors are normalized to FailureCode with automatic category,
retryability, and reconciliation derivation from
FAILURE_CODE_CATEGORIES map.
"""

from __future__ import annotations

from pipeline.capabilities.errors import (
    RECONCILIATION_REQUIRED_CATEGORIES,
    RECONCILIATION_REQUIRED_CODES,
    RETRYABLE_CATEGORIES,
    category_for_code,
    create_normalized_error,
    create_normalized_error_from_exception,
    is_retryable_category,
    is_retryable_code,
    requires_reconciliation_category,
    requires_reconciliation_code,
)
from pipeline.capabilities.executor import (
    CapabilityExecutor,
    ExecutionError,
    ExecutionResult,
)
from pipeline.capabilities.fake import (
    FAKE_OUTCOME_FACTORIES,
    FakeCapabilityProvider,
    FakeOutcomeSpec,
    create_asr_alignment_success_outcome,
    create_audio_qc_failure_outcome,
    create_audio_qc_success_outcome,
    create_content_stage_success_outcome,
    create_failed_outcome,
    create_research_success_outcome,
    create_script_generation_success_outcome,
    create_speech_generation_success_outcome,
    create_success_outcome,
    create_tts_adapter_success_outcome,
    create_unknown_outcome,
    create_visual_planning_success_outcome,
    outcome_authentication_failure,
    outcome_authorization_failure,
    outcome_budget_exceeded,
    outcome_configuration,
    outcome_human_review,
    outcome_internal,
    outcome_media_integrity,
    outcome_permanent_provider,
    outcome_policy,
    outcome_quality_failure,
    outcome_quota_exceeded,
    outcome_rate_limit,
    outcome_timeout_unknown,
    outcome_transient_provider,
    outcome_validation_failure,
)
from pipeline.capabilities.models import (
    CapabilityExecutionInput,
    CapabilityExecutionOutput,
    CapabilityImplementation,
    CapabilityRegistration,
    ScriptedOutcome,
)
from pipeline.capabilities.registry import (
    CapabilityKey,
    CapabilityNotFoundError,
    CapabilityRegistry,
    CapabilityRequirementMismatchError,
)

__all__ = [
    "FAKE_OUTCOME_FACTORIES",
    "RECONCILIATION_REQUIRED_CATEGORIES",
    "RECONCILIATION_REQUIRED_CODES",
    "RETRYABLE_CATEGORIES",
    "CapabilityExecutionInput",
    "CapabilityExecutionOutput",
    "CapabilityExecutor",
    "CapabilityImplementation",
    "CapabilityKey",
    "CapabilityNotFoundError",
    "CapabilityRegistration",
    "CapabilityRegistry",
    "CapabilityRequirementMismatchError",
    "ExecutionError",
    "ExecutionResult",
    "FakeCapabilityProvider",
    "FakeOutcomeSpec",
    "ScriptedOutcome",
    "category_for_code",
    "create_asr_alignment_success_outcome",
    "create_audio_qc_failure_outcome",
    "create_audio_qc_success_outcome",
    "create_content_stage_success_outcome",
    "create_failed_outcome",
    "create_normalized_error",
    "create_normalized_error_from_exception",
    "create_research_success_outcome",
    "create_script_generation_success_outcome",
    "create_speech_generation_success_outcome",
    "create_success_outcome",
    "create_tts_adapter_success_outcome",
    "create_unknown_outcome",
    "create_visual_planning_success_outcome",
    "is_retryable_category",
    "is_retryable_code",
    "outcome_authentication_failure",
    "outcome_authorization_failure",
    "outcome_budget_exceeded",
    "outcome_configuration",
    "outcome_human_review",
    "outcome_internal",
    "outcome_media_integrity",
    "outcome_permanent_provider",
    "outcome_policy",
    "outcome_quality_failure",
    "outcome_quota_exceeded",
    "outcome_rate_limit",
    "outcome_timeout_unknown",
    "outcome_transient_provider",
    "outcome_validation_failure",
    "requires_reconciliation_category",
    "requires_reconciliation_code",
]
