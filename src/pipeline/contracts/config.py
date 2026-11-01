"""Layered configuration contracts.

Configuration is resolved before a run starts and persisted as an immutable
``EffectiveConfig`` snapshot. The hash identifies the canonical snapshot; the
snapshot itself remains inspectable after source configuration changes.
"""

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
)
from pipeline.contracts.vocabularies import StageName


class RunOverrides(Contract):
    """Caller-supplied changes that still resolve under system policy."""

    schema_version: Literal["run-overrides.v1"]
    locale: NonEmptyStr | None = None
    target_duration_seconds: PositiveInt | None = None
    variant_count: PositiveInt | None = None
    max_cost_minor: NonNegativeInt | None = None
    enabled_optional_stages: list[StageName] = Field(default_factory=list)
    output_profile_ids: list[OpaqueId] | None = None
    quality_profile_id: NonEmptyStr | None = None

    @model_validator(mode="after")
    def _validate_unique_lists(self) -> RunOverrides:
        if len(set(self.enabled_optional_stages)) != len(self.enabled_optional_stages):
            raise ValueError("enabled_optional_stages must not contain duplicates")
        if self.output_profile_ids is not None and len(
            set(self.output_profile_ids)
        ) != len(self.output_profile_ids):
            raise ValueError("output_profile_ids must not contain duplicates")
        return self


class EffectiveConfig(Contract):
    """Immutable resolved configuration for one run."""

    schema_version: Literal["effective-config.v1"]
    effective_config_id: OpaqueId
    system_policy_version: NonEmptyStr
    domain_profile_id: OpaqueId
    domain_profile_version: NonEmptyStr
    channel_profile_id: OpaqueId
    channel_profile_version: NonEmptyStr
    workflow_id: OpaqueId
    workflow_version: NonEmptyStr
    run_overrides: RunOverrides
    resolved_values: ExtensionObject = Field(default_factory=dict)
    source_map: dict[NonEmptyStr, NonEmptyStr] = Field(default_factory=dict)
    config_hash: Sha256Hex
    snapshot_artifact_id: OpaqueId | None = None


__all__ = ["EffectiveConfig", "RunOverrides"]
