"""Typed capability models for the provider-independent capability boundary."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from pipeline.contracts.base import (
    Contract,
    ExtensionObject,
    NonEmptyStr,
    NonNegativeInt,
    OpaqueId,
    PositiveInt,
    Sha256Hex,
    StrictBoolean,
)
from pipeline.contracts.capabilities import (
    CapabilityExecution,
    CapabilityRequest,
    CapabilityResult,
    ExecutionContext,
    UsageRecord,
)
from pipeline.contracts.routing import (
    ProviderInvocation,
    ResourceAssignment,
    RoutingDecision,
)


class CapabilityImplementation(Contract):
    """A registered capability implementation with its declared metadata."""

    schema_version: Literal["capability-implementation.v1"]
    implementation_id: OpaqueId
    capability: NonEmptyStr
    operation_version: NonEmptyStr
    implementation_version: NonEmptyStr
    provider: NonEmptyStr
    model: NonEmptyStr | None = None
    declared_features: list[NonEmptyStr] = Field(default_factory=list)
    supported_locales: list[NonEmptyStr] = Field(default_factory=list)
    data_classification: NonEmptyStr = "PUBLIC"
    estimated_cost_minor: NonNegativeInt = 0
    max_latency_seconds: PositiveInt | None = None
    requires_network: StrictBoolean = False
    config_hash: Sha256Hex

    @model_validator(mode="after")
    def _validate_unique(self) -> CapabilityImplementation:
        for field_name in ("declared_features", "supported_locales"):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
        return self


class CapabilityRegistration(Contract):
    """Registration key and metadata for a capability implementation."""

    schema_version: Literal["capability-registration.v1"]
    capability: NonEmptyStr
    operation_version: NonEmptyStr
    implementation: CapabilityImplementation


class ScriptedOutcome(Contract):
    """Deterministic scripted outcome for fake capability execution."""

    schema_version: Literal["scripted-outcome.v1"]
    status: Literal["SUCCEEDED", "FAILED", "UNKNOWN"]
    artifact_ids: list[OpaqueId] = Field(default_factory=list)
    metadata: ExtensionObject = Field(default_factory=dict)
    usage: UsageRecord | None = None
    normalized_error_code: NonEmptyStr | None = None
    normalized_error_category: NonEmptyStr | None = None
    normalized_error_message: NonEmptyStr | None = None
    normalized_error_retryable: bool | None = None
    normalized_error_reconciliation_required: bool | None = None
    normalized_error_severity: Literal["INFO", "MINOR", "MAJOR", "CRITICAL"] = "MAJOR"
    raise_exception: bool = False
    exception_type: NonEmptyStr | None = None
    exception_message: NonEmptyStr | None = None

    @model_validator(mode="after")
    def _validate_outcome(self) -> ScriptedOutcome:
        if self.status == "SUCCEEDED" and self.normalized_error_code is not None:
            raise ValueError("succeeded outcome must not have error fields")
        if self.status == "FAILED" and self.normalized_error_code is None:
            raise ValueError("failed outcome requires normalized_error_code")
        if self.status == "UNKNOWN" and self.normalized_error_code is None:
            raise ValueError("unknown outcome requires normalized_error_code")
        if self.raise_exception and self.exception_type is None:
            raise ValueError("raise_exception requires exception_type")
        return self


class CapabilityExecutionInput(Contract):
    """Complete input for a capability execution."""

    schema_version: Literal["capability-execution-input.v1"]
    request: CapabilityRequest
    context: ExecutionContext
    routing_decision: RoutingDecision
    resource_assignment: ResourceAssignment | None = None


class CapabilityExecutionOutput(Contract):
    """Complete output from a capability execution."""

    schema_version: Literal["capability-execution-output.v1"]
    capability_execution: CapabilityExecution
    provider_invocation: ProviderInvocation | None = None
    result: CapabilityResult
    usage_record: UsageRecord | None = None


__all__ = [
    "CapabilityExecutionInput",
    "CapabilityExecutionOutput",
    "CapabilityImplementation",
    "CapabilityRegistration",
    "ScriptedOutcome",
]
