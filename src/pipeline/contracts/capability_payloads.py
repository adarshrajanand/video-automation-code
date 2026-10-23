"""Capability payload contracts for content stages.

These are the input/output payload schemas for the research, script_generation,
and visual_planning capabilities. They are versioned independently from the
core content contracts.
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
)
from pipeline.contracts.vocabularies import SourceKind


class ResearchInputPayload(Contract):
    """Input payload for the research capability."""

    schema_version: Literal["research-input.v1"]
    topic: NonEmptyStr
    focus_areas: list[NonEmptyStr] = Field(default_factory=list)
    source_kinds: list[SourceKind] = Field(default_factory=list)
    max_sources: PositiveInt = 10
    max_tokens_per_source: PositiveInt = 8000
    language: NonEmptyStr = "en"
    metadata: ExtensionObject = Field(default_factory=dict)


class ResearchOutputPayload(Contract):
    """Output payload for the research capability."""

    schema_version: Literal["research-output.v1"]
    source_ref_ids: list[OpaqueId] = Field(default_factory=list)
    source_snapshot_ids: list[OpaqueId] = Field(default_factory=list)
    claim_ids: list[OpaqueId] = Field(default_factory=list)
    evidence_ids: list[OpaqueId] = Field(default_factory=list)
    source_count: NonNegativeInt = 0
    claim_count: NonNegativeInt = 0
    evidence_count: NonNegativeInt = 0
    metadata: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_research_output(self) -> ResearchOutputPayload:
        fields = ("source_ref_ids", "source_snapshot_ids", "claim_ids", "evidence_ids")
        for field_name in fields:
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
        return self


class ScriptGenerationInputPayload(Contract):
    """Input payload for the script_generation capability."""

    schema_version: Literal["script-generation-input.v1"]
    topic: NonEmptyStr
    outline: NonEmptyStr
    claim_ids: list[OpaqueId] = Field(default_factory=list)
    evidence_ids: list[OpaqueId] = Field(default_factory=list)
    source_ref_ids: list[OpaqueId] = Field(default_factory=list)
    duration_policy_id: OpaqueId
    target_audience: NonEmptyStr = "general"
    tone: NonEmptyStr = "informative"
    language: NonEmptyStr = "en"
    metadata: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_script_generation_input(self) -> ScriptGenerationInputPayload:
        for field_name in ("claim_ids", "evidence_ids", "source_ref_ids"):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
        return self


class ScriptGenerationOutputPayload(Contract):
    """Output payload for the script_generation capability."""

    schema_version: Literal["script-generation-output.v1"]
    script_id: OpaqueId
    scene_ids: list[OpaqueId] = Field(default_factory=list)
    visual_intent_ids: list[OpaqueId] = Field(default_factory=list)
    total_estimated_duration_seconds: PositiveInt
    word_count: PositiveInt
    scene_count: PositiveInt
    metadata: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_script_generation_output(self) -> ScriptGenerationOutputPayload:
        for field_name in ("scene_ids", "visual_intent_ids"):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
        return self


class VisualPlanningInputPayload(Contract):
    """Input payload for the visual_planning capability."""

    schema_version: Literal["visual-planning-input.v1"]
    script_id: OpaqueId
    scene_ids: list[OpaqueId] = Field(default_factory=list)
    visual_intent_ids: list[OpaqueId] = Field(default_factory=list)
    style_guidance: NonEmptyStr = "documentary_cinematic"
    color_palette: NonEmptyStr | None = None
    metadata: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_visual_planning_input(self) -> VisualPlanningInputPayload:
        if len(set(self.scene_ids)) != len(self.scene_ids):
            raise ValueError("scene_ids must not contain duplicates")
        if len(set(self.visual_intent_ids)) != len(self.visual_intent_ids):
            raise ValueError("visual_intent_ids must not contain duplicates")
        return self


class VisualPlanningOutputPayload(Contract):
    """Output payload for the visual_planning capability."""

    schema_version: Literal["visual-planning-output.v1"]
    visual_intent_ids: list[OpaqueId] = Field(default_factory=list)
    shot_plan_ids: list[OpaqueId] = Field(default_factory=list)
    asset_requirement_ids: list[OpaqueId] = Field(default_factory=list)
    scene_count: PositiveInt
    metadata: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_visual_planning_output(self) -> VisualPlanningOutputPayload:
        fields = ("visual_intent_ids", "shot_plan_ids", "asset_requirement_ids")
        for field_name in fields:
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
        return self


__all__ = [
    "ResearchInputPayload",
    "ResearchOutputPayload",
    "ScriptGenerationInputPayload",
    "ScriptGenerationOutputPayload",
    "VisualPlanningInputPayload",
    "VisualPlanningOutputPayload",
]
