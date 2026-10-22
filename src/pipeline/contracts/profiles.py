"""System, budget, domain, and channel policy profile contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from pipeline.contracts.base import (
    Contract,
    NonEmptyStr,
    NonNegativeInt,
    OpaqueId,
    PositiveInt,
    StrictBoolean,
)
from pipeline.contracts.vocabularies import StageName


class BudgetPolicy(Contract):
    """Budget caps and paid-fallback authorization."""

    schema_version: Literal["budget-policy.v1"]
    policy_id: OpaqueId
    version: NonEmptyStr
    system_cap_minor: NonNegativeInt
    monthly_cap_minor: NonNegativeInt | None = None
    default_run_cap_minor: NonNegativeInt | None = None
    default_stage_cap_minor: NonNegativeInt | None = None
    evaluation_cap_minor: NonNegativeInt | None = None
    paid_fallback_enabled: StrictBoolean = False
    reservation_required: StrictBoolean = True


class SystemPolicy(Contract):
    """Non-overridable system limits and allowed providers."""

    schema_version: Literal["system-policy.v1"]
    policy_id: OpaqueId
    version: NonEmptyStr
    max_parallelism: PositiveInt
    max_retry_attempts: NonNegativeInt
    budget_policy_id: OpaqueId
    allowed_providers: list[NonEmptyStr] = Field(default_factory=list)
    non_overridable_fields: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_unique_system_lists(self) -> SystemPolicy:
        for field_name in ("allowed_providers", "non_overridable_fields"):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
        return self


class DomainProfile(Contract):
    """Domain-level content, evidence, quality, and review policy."""

    schema_version: Literal["domain-profile.v1"]
    profile_id: OpaqueId
    version: NonEmptyStr
    content_mode: NonEmptyStr
    default_locale: NonEmptyStr
    required_stages: list[StageName] = Field(min_length=1)
    optional_stages: list[StageName] = Field(default_factory=list)
    source_policy_id: OpaqueId | None = None
    claim_policy_id: OpaqueId | None = None
    quality_profile_id: OpaqueId
    human_review_policy_id: OpaqueId
    asset_policy_id: OpaqueId

    @model_validator(mode="after")
    def _validate_stage_sets(self) -> DomainProfile:
        required = set(self.required_stages)
        optional = set(self.optional_stages)
        if len(required) != len(self.required_stages):
            raise ValueError("required_stages must not contain duplicates")
        if len(optional) != len(self.optional_stages):
            raise ValueError("optional_stages must not contain duplicates")
        overlap = required & optional
        if overlap:
            raise ValueError(
                "required_stages and optional_stages must be disjoint: "
                + ", ".join(sorted(stage.value for stage in overlap))
            )
        return self


class ChannelProfile(Contract):
    """Channel-specific audience, duration, brand, and output policy."""

    schema_version: Literal["channel-profile.v1"]
    profile_id: OpaqueId
    version: NonEmptyStr
    domain_profile_id: OpaqueId
    locale: NonEmptyStr
    audience: NonEmptyStr
    target_duration_seconds: PositiveInt
    output_profile_ids: list[OpaqueId] = Field(min_length=1)
    brand_profile_id: OpaqueId
    voice_profile_id: OpaqueId | None = None
    publishing_policy_id: OpaqueId

    @model_validator(mode="after")
    def _validate_output_profiles(self) -> ChannelProfile:
        if len(set(self.output_profile_ids)) != len(self.output_profile_ids):
            raise ValueError("output_profile_ids must not contain duplicates")
        return self


__all__ = [
    "BudgetPolicy",
    "ChannelProfile",
    "DomainProfile",
    "SystemPolicy",
]
