"""Provider-independent capability and budget-control contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from pipeline.contracts.base import (
    Contract,
    ExtensionObject,
    NonEmptyStr,
    NonNegativeFloat,
    NonNegativeInt,
    NormalizedError,
    OpaqueId,
    PositiveInt,
    Sha256Hex,
    UTCDateTime,
)
from pipeline.contracts.vocabularies import (
    BudgetReservationStatus,
    BudgetScopeType,
    CapabilityExecutionStatus,
    CapabilityResultStatus,
    IdempotencyStatus,
)


class CapabilityRequirements(Contract):
    """Hard eligibility requirements for one capability request."""

    schema_version: Literal["capability-requirements.v1"]
    capability: NonEmptyStr
    required_features: list[NonEmptyStr] = Field(default_factory=list)
    locale: NonEmptyStr | None = None
    quality_requirement: NonEmptyStr | None = None
    latency_requirement: NonEmptyStr | None = None
    data_classification: NonEmptyStr = "PUBLIC"
    cost_limit_minor: NonNegativeInt | None = None

    @model_validator(mode="after")
    def _validate_unique_features(self) -> CapabilityRequirements:
        if len(set(self.required_features)) != len(self.required_features):
            raise ValueError("required_features must not contain duplicates")
        return self


class CapabilityRequest(Contract):
    """Provider-neutral request for one bounded capability operation."""

    schema_version: Literal["capability-request.v1"]
    capability_execution_id: OpaqueId
    capability: NonEmptyStr
    operation_version: NonEmptyStr
    input_artifact_ids: list[OpaqueId] = Field(default_factory=list)
    payload_fingerprint: Sha256Hex
    requirements: CapabilityRequirements
    payload: ExtensionObject = Field(default_factory=dict)
    payload_schema_version: NonEmptyStr
    runtime_context: ExtensionObject = Field(default_factory=dict)
    idempotency_key: NonEmptyStr

    @model_validator(mode="after")
    def _validate_request(self) -> CapabilityRequest:
        if len(set(self.input_artifact_ids)) != len(self.input_artifact_ids):
            raise ValueError("input_artifact_ids must not contain duplicates")
        if self.requirements.capability != self.capability:
            raise ValueError(
                "requirements.capability must match the request capability"
            )
        return self


class ExecutionContext(Contract):
    """Execution scope and limits passed to a capability implementation."""

    schema_version: Literal["execution-context.v1"]
    run_id: OpaqueId
    stage_instance_id: OpaqueId
    attempt_id: OpaqueId
    effective_config_id: OpaqueId
    correlation_id: OpaqueId
    timeout_seconds: PositiveInt
    allowed_data_classification: NonEmptyStr


class UsageRecord(Contract):
    """Observed provider or local implementation usage."""

    schema_version: Literal["usage.v1"]
    provider: NonEmptyStr
    model: NonEmptyStr | None = None
    input_units: NonNegativeInt | None = None
    output_units: NonNegativeInt | None = None
    runtime_seconds: NonNegativeFloat | None = None
    estimated_cost_minor: NonNegativeInt = 0
    actual_cost_minor: NonNegativeInt | None = None
    metadata: ExtensionObject = Field(default_factory=dict)


class CapabilityResult(Contract):
    """Returned outcome of exactly one capability attempt."""

    schema_version: Literal["capability-result.v1"]
    capability_execution_id: OpaqueId
    status: CapabilityResultStatus
    artifact_ids: list[OpaqueId] = Field(default_factory=list)
    metadata: ExtensionObject = Field(default_factory=dict)
    usage: UsageRecord | None = None
    normalized_error: NormalizedError | None = None

    @model_validator(mode="after")
    def _validate_result(self) -> CapabilityResult:
        if len(set(self.artifact_ids)) != len(self.artifact_ids):
            raise ValueError("artifact_ids must not contain duplicates")
        if (
            self.status is CapabilityResultStatus.SUCCEEDED
            and self.normalized_error is not None
        ):
            raise ValueError("a succeeded result must not carry a normalized_error")
        if (
            self.status is CapabilityResultStatus.FAILED
            and self.normalized_error is None
        ):
            raise ValueError("a failed result requires a normalized_error")
        return self


class CapabilityExecution(Contract):
    """Control-plane lifecycle record for one capability execution."""

    schema_version: Literal["capability-execution.v1"]
    capability_execution_id: OpaqueId
    attempt_id: OpaqueId
    capability: NonEmptyStr
    operation_version: NonEmptyStr
    implementation_version: NonEmptyStr
    prompt_version: NonEmptyStr | None = None
    rubric_version: NonEmptyStr | None = None
    settings_hash: Sha256Hex | None = None
    tool_versions: dict[NonEmptyStr, NonEmptyStr] = Field(default_factory=dict)
    request_fingerprint: Sha256Hex
    idempotency_key: NonEmptyStr
    routing_decision_id: OpaqueId | None = None
    resource_assignment_id: OpaqueId | None = None
    status: CapabilityExecutionStatus
    input_artifact_ids: list[OpaqueId] = Field(default_factory=list)
    output_artifact_ids: list[OpaqueId] = Field(default_factory=list)
    started_at: UTCDateTime | None = None
    finished_at: UTCDateTime | None = None
    normalized_error: NormalizedError | None = None

    @model_validator(mode="after")
    def _validate_execution(self) -> CapabilityExecution:
        for field_name in ("input_artifact_ids", "output_artifact_ids"):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
        if (
            self.started_at is not None
            and self.finished_at is not None
            and self.finished_at < self.started_at
        ):
            raise ValueError("finished_at must not be earlier than started_at")
        if (
            self.status is CapabilityExecutionStatus.SUCCEEDED
            and self.normalized_error is not None
        ):
            raise ValueError(
                "a succeeded capability execution must not carry a normalized_error"
            )
        if (
            self.status is CapabilityExecutionStatus.FAILED
            and self.normalized_error is None
        ):
            raise ValueError(
                "a failed capability execution requires a normalized_error"
            )
        return self


class IdempotencyRecord(Contract):
    """Duplicate-suppression and reconciliation state for one operation key."""

    schema_version: Literal["idempotency-record.v1"]
    idempotency_key: NonEmptyStr
    capability: NonEmptyStr
    request_fingerprint: Sha256Hex
    provider: NonEmptyStr | None = None
    status: IdempotencyStatus
    capability_execution_id: OpaqueId
    provider_invocation_id: OpaqueId | None = None
    provider_operation_id: NonEmptyStr | None = None
    result_artifact_ids: list[OpaqueId] = Field(default_factory=list)
    created_at: UTCDateTime
    completed_at: UTCDateTime | None = None

    @model_validator(mode="after")
    def _validate_idempotency_record(self) -> IdempotencyRecord:
        if len(set(self.result_artifact_ids)) != len(self.result_artifact_ids):
            raise ValueError("result_artifact_ids must not contain duplicates")
        if self.completed_at is not None and self.completed_at < self.created_at:
            raise ValueError("completed_at must not be earlier than created_at")
        return self


class BudgetReservation(Contract):
    """Reserved and settled cost at one budget scope."""

    schema_version: Literal["budget-reservation.v1"]
    reservation_id: OpaqueId
    scope_type: BudgetScopeType
    scope_id: OpaqueId
    idempotency_key: NonEmptyStr
    estimated_cost_minor: NonNegativeInt
    reserved_cost_minor: NonNegativeInt
    actual_cost_minor: NonNegativeInt | None = None
    status: BudgetReservationStatus
    created_at: UTCDateTime
    settled_at: UTCDateTime | None = None

    @model_validator(mode="after")
    def _validate_reservation(self) -> BudgetReservation:
        if self.settled_at is not None and self.settled_at < self.created_at:
            raise ValueError("settled_at must not be earlier than created_at")
        if (
            self.status is BudgetReservationStatus.SETTLED
            and self.actual_cost_minor is None
        ):
            raise ValueError("a settled reservation requires actual_cost_minor")
        return self


__all__ = [
    "BudgetReservation",
    "CapabilityExecution",
    "CapabilityRequest",
    "CapabilityRequirements",
    "CapabilityResult",
    "ExecutionContext",
    "IdempotencyRecord",
    "UsageRecord",
]
