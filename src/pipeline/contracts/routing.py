"""Routing, resource-placement, and provider-invocation contracts."""

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
    UTCDateTime,
)
from pipeline.contracts.capabilities import CapabilityRequest
from pipeline.contracts.vocabularies import ProviderInvocationStatus


class RoutingContext(Contract):
    """Inputs used to select an implementation, provider, and resource."""

    schema_version: Literal["routing-context.v1"]
    capability_request: CapabilityRequest
    effective_config_hash: Sha256Hex
    provider_health: ExtensionObject = Field(default_factory=dict)
    provider_usage: ExtensionObject = Field(default_factory=dict)
    previous_results: list[ExtensionObject] = Field(default_factory=list)
    attempt: PositiveInt
    budget_remaining_minor: NonNegativeInt | None = None


class RoutingDecision(Contract):
    """Recorded selection of implementation, provider, model, and fallbacks."""

    schema_version: Literal["routing-decision.v1"]
    routing_decision_id: OpaqueId
    capability: NonEmptyStr
    implementation: NonEmptyStr
    implementation_version: NonEmptyStr
    provider: NonEmptyStr
    model: NonEmptyStr | None = None
    provider_config_hash: Sha256Hex
    fallback_chain: list[NonEmptyStr] = Field(default_factory=list)
    policy_version: NonEmptyStr
    reason_codes: list[NonEmptyStr] = Field(default_factory=list)
    candidate_exclusions: list[ExtensionObject] = Field(default_factory=list)
    budget_context: ExtensionObject = Field(default_factory=dict)
    usage_context: ExtensionObject = Field(default_factory=dict)
    attempt: PositiveInt
    data_classification: NonEmptyStr
    paid_fallback_authorized: StrictBoolean = False
    created_at: UTCDateTime

    @model_validator(mode="after")
    def _validate_unique_routing_lists(self) -> RoutingDecision:
        for field_name in ("fallback_chain", "reason_codes"):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
        return self


class WorkloadRequirements(Contract):
    """Resource shape required by one capability workload."""

    schema_version: Literal["workload-requirements.v1"]
    cpu_cores: PositiveInt | None = None
    memory_mb: PositiveInt | None = None
    vram_mb: PositiveInt | None = None
    expected_runtime_seconds: PositiveInt | None = None
    required_tools: list[NonEmptyStr] = Field(default_factory=list)
    data_classification: NonEmptyStr = "PUBLIC"

    @model_validator(mode="after")
    def _validate_tools(self) -> WorkloadRequirements:
        if len(set(self.required_tools)) != len(self.required_tools):
            raise ValueError("required_tools must not contain duplicates")
        return self


class ResourceConstraints(Contract):
    """Placement and spend limits applied to a workload."""

    schema_version: Literal["resource-constraints.v1"]
    allowed_placement_classes: list[NonEmptyStr] = Field(default_factory=list)
    max_runtime_seconds: PositiveInt | None = None
    max_cost_minor: NonNegativeInt | None = None
    network_required: StrictBoolean = False

    @model_validator(mode="after")
    def _validate_placement_classes(self) -> ResourceConstraints:
        if len(set(self.allowed_placement_classes)) != len(
            self.allowed_placement_classes
        ):
            raise ValueError("allowed_placement_classes must not contain duplicates")
        return self


class ResourceAssignment(Contract):
    """Selected placement and worker pool for one workload."""

    schema_version: Literal["resource-assignment.v1"]
    assignment_id: OpaqueId
    placement_class: NonEmptyStr
    worker_pool: NonEmptyStr
    implementation_version: NonEmptyStr
    constraints_hash: Sha256Hex
    created_at: UTCDateTime


class ProviderInvocation(Contract):
    """One external or local provider operation with its idempotency evidence."""

    schema_version: Literal["provider-invocation.v1"]
    invocation_id: OpaqueId
    capability_execution_id: OpaqueId
    provider: NonEmptyStr
    operation_id: NonEmptyStr | None = None
    idempotency_key: NonEmptyStr
    request_fingerprint: Sha256Hex
    status: ProviderInvocationStatus
    started_at: UTCDateTime
    finished_at: UTCDateTime | None = None

    @model_validator(mode="after")
    def _validate_invocation(self) -> ProviderInvocation:
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("finished_at must not be earlier than started_at")
        if (
            self.status is ProviderInvocationStatus.STARTED
            and self.finished_at is not None
        ):
            raise ValueError("a started invocation must not have finished_at")
        return self


__all__ = [
    "ProviderInvocation",
    "ResourceAssignment",
    "ResourceConstraints",
    "RoutingContext",
    "RoutingDecision",
    "WorkloadRequirements",
]
