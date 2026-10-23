"""Deterministic fake capability provider for testing and local execution."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pipeline.capabilities.errors import create_normalized_error_from_exception
from pipeline.capabilities.models import (
    CapabilityExecutionInput,
    CapabilityExecutionOutput,
    ScriptedOutcome,
)
from pipeline.contracts.capabilities import (
    CapabilityExecution,
    CapabilityExecutionStatus,
    CapabilityResult,
    CapabilityResultStatus,
    UsageRecord,
)
from pipeline.contracts.routing import ProviderInvocation, ProviderInvocationStatus
from pipeline.contracts.vocabularies import FailureCode
from pipeline.ids import deterministic_id

if TYPE_CHECKING:
    from pipeline.capabilities.registry import CapabilityRegistry


@dataclass(frozen=True, slots=True)
class FakeOutcomeSpec:
    """Specification for a fake outcome, used for test parametrization."""

    name: str
    outcome: ScriptedOutcome


class FakeCapabilityProvider:
    """Deterministic fake capability provider that returns scripted outcomes.

    This provider never makes network calls, uses real credentials, or depends on
    provider SDKs. It returns pre-configured outcomes based on the request fingerprint
    or explicit outcome mapping.
    """

    def __init__(self, registry: CapabilityRegistry) -> None:
        self._registry = registry
        self._outcomes: dict[str, ScriptedOutcome] = {}
        self._default_outcome = ScriptedOutcome(
            schema_version="scripted-outcome.v1",
            status="SUCCEEDED",
            artifact_ids=[f"artifact_fake_{uuid.uuid4().hex[:8]}"],
            metadata={"fake": True},
            usage=UsageRecord(
                schema_version="usage.v1",
                provider="fake",
                model="deterministic-fixture",
                input_units=0,
                output_units=0,
                runtime_seconds=0.0,
                estimated_cost_minor=0,
                actual_cost_minor=0,
            ),
        )

    def register_outcome(
        self, request_fingerprint: str, outcome: ScriptedOutcome
    ) -> None:
        """Register a scripted outcome for a specific request fingerprint."""
        self._outcomes[request_fingerprint] = outcome

    def set_default_outcome(self, outcome: ScriptedOutcome) -> None:
        """Set the default outcome for unmatched requests."""
        self._default_outcome = outcome

    def clear(self) -> None:
        """Clear all registered outcomes."""
        self._outcomes.clear()

    def execute(
        self,
        input_data: CapabilityExecutionInput,
    ) -> CapabilityExecutionOutput:
        """Execute a capability request and return a deterministic fake result.

        This method:
        1. Computes the request fingerprint
        2. Looks up a registered scripted outcome
        3. Falls back to the default outcome
        4. Builds CapabilityExecution, ProviderInvocation,
           CapabilityResult, and UsageRecord
        """
        request = input_data.request
        fingerprint = request.payload_fingerprint

        # Get the scripted outcome for this request
        outcome = self._outcomes.get(fingerprint, self._default_outcome)

        # Create capability execution record
        execution_id = request.capability_execution_id
        started_at = __import__("datetime").datetime.now(__import__("datetime").UTC)
        finished_at = __import__("datetime").datetime.now(__import__("datetime").UTC)

        # Handle exception-raising outcomes
        if outcome.raise_exception:
            exc_type = getattr(__builtins__, outcome.exception_type, Exception)
            raise exc_type(outcome.exception_message or "Fake provider exception")

        # Build normalized error if outcome is failed/unknown
        normalized_error = None
        if outcome.status in ("FAILED", "UNKNOWN") and outcome.normalized_error_code:
            try:
                failure_code = FailureCode(outcome.normalized_error_code)
                normalized_error = create_normalized_error_from_exception(
                    Exception(outcome.normalized_error_message or "Fake failure"),
                    default_code=failure_code,
                    provider_status="fake",
                    safe_details=outcome.metadata,
                )
            except ValueError:
                # Unknown failure code
                normalized_error = create_normalized_error_from_exception(
                    Exception(outcome.normalized_error_message or "Fake failure"),
                    default_code=FailureCode.INTERNAL,
                    provider_status="fake",
                    safe_details=outcome.metadata,
                )

        # Build CapabilityExecution
        capability_execution = CapabilityExecution(
            schema_version="capability-execution.v1",
            capability_execution_id=execution_id,
            attempt_id=input_data.context.attempt_id,
            capability=request.capability,
            operation_version=request.operation_version,
            implementation_version=input_data.routing_decision.implementation_version,
            prompt_version=input_data.routing_decision.reason_codes[0]
            if input_data.routing_decision.reason_codes
            else None,
            rubric_version=None,
            settings_hash=input_data.routing_decision.provider_config_hash,
            tool_versions={},
            request_fingerprint=fingerprint,
            idempotency_key=request.idempotency_key,
            routing_decision_id=input_data.routing_decision.routing_decision_id,
            resource_assignment_id=input_data.resource_assignment.assignment_id
            if input_data.resource_assignment
            else None,
            status=CapabilityExecutionStatus(outcome.status),
            input_artifact_ids=request.input_artifact_ids,
            output_artifact_ids=outcome.artifact_ids,
            started_at=started_at,
            finished_at=finished_at,
            normalized_error=normalized_error,
        )

        # Build ProviderInvocation
        invocation_id = deterministic_id("inv", execution_id)
        provider_invocation = ProviderInvocation(
            schema_version="provider-invocation.v1",
            invocation_id=invocation_id,
            capability_execution_id=execution_id,
            provider=input_data.routing_decision.provider,
            operation_id=f"fake_op_{uuid.uuid4().hex[:12]}"
            if outcome.status != "UNKNOWN"
            else None,
            idempotency_key=request.idempotency_key,
            request_fingerprint=fingerprint,
            status=ProviderInvocationStatus(outcome.status),
            started_at=started_at,
            finished_at=finished_at if outcome.status != "UNKNOWN" else None,
        )

        # Build CapabilityResult
        usage_record = outcome.usage
        if usage_record is not None:
            # Update usage with provider from routing decision
            usage_record = UsageRecord(
                schema_version="usage.v1",
                provider=input_data.routing_decision.provider,
                model=input_data.routing_decision.model,
                input_units=usage_record.input_units,
                output_units=usage_record.output_units,
                runtime_seconds=usage_record.runtime_seconds,
                estimated_cost_minor=usage_record.estimated_cost_minor,
                actual_cost_minor=usage_record.actual_cost_minor,
                metadata=usage_record.metadata,
            )

        result = CapabilityResult(
            schema_version="capability-result.v1",
            capability_execution_id=execution_id,
            status=CapabilityResultStatus(outcome.status),
            artifact_ids=outcome.artifact_ids,
            metadata=outcome.metadata,
            usage=usage_record,
            normalized_error=normalized_error,
        )

        return CapabilityExecutionOutput(
            schema_version="capability-execution-output.v1",
            capability_execution=capability_execution,
            provider_invocation=provider_invocation,
            result=result,
            usage_record=usage_record,
        )


# Pre-defined scripted outcomes for all canonical failure categories
def create_success_outcome(
    artifact_ids: list[str] | None = None,
    usage: UsageRecord | None = None,
) -> ScriptedOutcome:
    """Create a successful outcome."""
    return ScriptedOutcome(
        schema_version="scripted-outcome.v1",
        status="SUCCEEDED",
        artifact_ids=artifact_ids or [f"artifact_fake_{uuid.uuid4().hex[:8]}"],
        metadata={"fake": True, "outcome": "success"},
        usage=usage
        or UsageRecord(
            schema_version="usage.v1",
            provider="fake",
            model="deterministic-fixture",
            input_units=10,
            output_units=20,
            runtime_seconds=0.5,
            estimated_cost_minor=100,
            actual_cost_minor=100,
        ),
    )


def create_failed_outcome(
    failure_code: FailureCode,
    message: str,
    artifact_ids: list[str] | None = None,
) -> ScriptedOutcome:
    """Create a failed outcome with a specific failure code."""
    from pipeline.capabilities.errors import category_for_code

    category = category_for_code(failure_code)
    return ScriptedOutcome(
        schema_version="scripted-outcome.v1",
        status="FAILED",
        artifact_ids=artifact_ids or [],
        metadata={
            "fake": True,
            "outcome": "failure",
            "failure_code": failure_code.value,
        },
        usage=UsageRecord(
            schema_version="usage.v1",
            provider="fake",
            model="deterministic-fixture",
            input_units=10,
            output_units=0,
            runtime_seconds=0.5,
            estimated_cost_minor=100,
            actual_cost_minor=0,
        ),
        normalized_error_code=failure_code.value,
        normalized_error_category=category.value,
        normalized_error_message=message,
        normalized_error_retryable=category
        in {
            "TRANSIENT",
            "RATE_LIMIT",
            "QUOTA",
        },
        normalized_error_reconciliation_required=failure_code
        == FailureCode.TIMEOUT_UNKNOWN,
        normalized_error_severity="MAJOR",
    )


def create_unknown_outcome(
    failure_code: FailureCode = FailureCode.TIMEOUT_UNKNOWN,
    message: str = "Provider call timed out, outcome unknown",
) -> ScriptedOutcome:
    """Create an unknown outcome (requires reconciliation)."""
    from pipeline.capabilities.errors import category_for_code

    category = category_for_code(failure_code)
    return ScriptedOutcome(
        schema_version="scripted-outcome.v1",
        status="UNKNOWN",
        artifact_ids=[],
        metadata={
            "fake": True,
            "outcome": "unknown",
            "failure_code": failure_code.value,
        },
        usage=UsageRecord(
            schema_version="usage.v1",
            provider="fake",
            model="deterministic-fixture",
            input_units=10,
            output_units=0,
            runtime_seconds=30.0,
            estimated_cost_minor=100,
            actual_cost_minor=None,
        ),
        normalized_error_code=failure_code.value,
        normalized_error_category=category.value,
        normalized_error_message=message,
        normalized_error_retryable=category
        in {
            "TRANSIENT",
            "RATE_LIMIT",
            "QUOTA",
        },
        normalized_error_reconciliation_required=True,
        normalized_error_severity="CRITICAL",
    )


# Convenience functions for all canonical failure categories
def outcome_validation_failure(
    message: str = "Input validation failed",
) -> ScriptedOutcome:
    return create_failed_outcome(FailureCode.VALIDATION, message)


def outcome_authentication_failure(
    message: str = "Authentication failed",
) -> ScriptedOutcome:
    return create_failed_outcome(FailureCode.AUTHENTICATION, message)


def outcome_authorization_failure(
    message: str = "Authorization failed",
) -> ScriptedOutcome:
    return create_failed_outcome(FailureCode.AUTHORIZATION, message)


def outcome_rate_limit(message: str = "Rate limit exceeded") -> ScriptedOutcome:
    return create_failed_outcome(FailureCode.RATE_LIMIT, message)


def outcome_quota_exceeded(message: str = "Quota exhausted") -> ScriptedOutcome:
    return create_failed_outcome(FailureCode.QUOTA, message)


def outcome_transient_provider(
    message: str = "Transient provider error",
) -> ScriptedOutcome:
    return create_failed_outcome(FailureCode.TRANSIENT_PROVIDER, message)


def outcome_permanent_provider(
    message: str = "Permanent provider rejection",
) -> ScriptedOutcome:
    return create_failed_outcome(FailureCode.PERMANENT_PROVIDER, message)


def outcome_timeout_unknown(
    message: str = "Provider call timed out, outcome unknown",
) -> ScriptedOutcome:
    return create_unknown_outcome(FailureCode.TIMEOUT_UNKNOWN, message)


def outcome_media_integrity(
    message: str = "Media integrity check failed",
) -> ScriptedOutcome:
    return create_failed_outcome(FailureCode.MEDIA_TECHNICAL_INTEGRITY, message)


def outcome_quality_failure(message: str = "Quality check failed") -> ScriptedOutcome:
    return create_failed_outcome(FailureCode.QUALITY_GENERIC, message)


def outcome_budget_exceeded(message: str = "Budget limit exceeded") -> ScriptedOutcome:
    return create_failed_outcome(FailureCode.POLICY_BUDGET_EXCEEDED, message)


def outcome_configuration(message: str = "Configuration error") -> ScriptedOutcome:
    return create_failed_outcome(FailureCode.CONFIG_UNKNOWN_STAGE, message)


def outcome_human_review(message: str = "Human review required") -> ScriptedOutcome:
    return create_failed_outcome(FailureCode.HUMAN_REVIEW_REQUIRED, message)


def outcome_policy(message: str = "Policy violation") -> ScriptedOutcome:
    return create_failed_outcome(FailureCode.POLICY_PROHIBITED_CONTENT, message)


def outcome_internal(message: str = "Internal error") -> ScriptedOutcome:
    return create_failed_outcome(FailureCode.INTERNAL, message)


# Map of outcome names to factory functions for CLI/test parametrization
FAKE_OUTCOME_FACTORIES: dict[str, tuple[str, str]] = {
    "success": (
        "create_success_outcome",
        "Successful outcome with artifacts and usage",
    ),
    "validation": (
        "outcome_validation_failure",
        "Validation failure (retryable: false)",
    ),
    "authentication": (
        "outcome_authentication_failure",
        "Authentication failure (retryable: false)",
    ),
    "authorization": (
        "outcome_authorization_failure",
        "Authorization failure (retryable: false)",
    ),
    "rate_limit": ("outcome_rate_limit", "Rate limit exceeded (retryable: true)"),
    "quota": ("outcome_quota_exceeded", "Quota exhausted (retryable: true)"),
    "transient": (
        "outcome_transient_provider",
        "Transient provider error (retryable: true)",
    ),
    "permanent": (
        "outcome_permanent_provider",
        "Permanent provider rejection (retryable: false)",
    ),
    "timeout_unknown": (
        "outcome_timeout_unknown",
        "Timeout/unknown outcome (retryable: false, reconciliation_required: true)",
    ),
    "media": ("outcome_media_integrity", "Media integrity failure (retryable: false)"),
    "quality": ("outcome_quality_failure", "Quality failure (retryable: false)"),
    "budget": ("outcome_budget_exceeded", "Budget exceeded (retryable: false)"),
    "configuration": (
        "outcome_configuration",
        "Configuration error (retryable: false)",
    ),
    "human_review": (
        "outcome_human_review",
        "Human review required (retryable: false)",
    ),
    "policy": ("outcome_policy", "Policy violation (retryable: false)"),
    "internal": ("outcome_internal", "Internal error (retryable: false)"),
}

# Export all factory functions
__all__ = [
    "FAKE_OUTCOME_FACTORIES",
    "FakeCapabilityProvider",
    "FakeOutcomeSpec",
    "create_failed_outcome",
    "create_success_outcome",
    "create_unknown_outcome",
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
]
