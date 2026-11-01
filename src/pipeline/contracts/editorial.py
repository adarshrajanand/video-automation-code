"""Minimal editorial hierarchy and composition reference contracts.

These records are references only. Full research, script, speech, composition,
render-chunk, assembly, and short-selection payloads belong to later stages and
are deliberately not defined here.
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
from pipeline.contracts.vocabularies import EditorialCutKind, LayerKind


class ContentPackage(Contract):
    """All related editorial inputs and deliverable references for one request."""

    schema_version: Literal["content-package.v1"]
    content_package_id: OpaqueId
    production_idea_id: OpaqueId
    episode_ids: list[OpaqueId] = Field(default_factory=list)
    active_episode_id: OpaqueId | None = None

    @model_validator(mode="after")
    def _validate_active_episode(self) -> ContentPackage:
        if len(set(self.episode_ids)) != len(self.episode_ids):
            raise ValueError("episode_ids must not contain duplicates")
        if (
            self.active_episode_id is not None
            and self.active_episode_id not in self.episode_ids
        ):
            raise ValueError("active_episode_id must reference a listed episode")
        return self


class Episode(Contract):
    """Canonical long-form editorial work, independent of an encoded file."""

    schema_version: Literal["episode.v1"]
    episode_id: OpaqueId
    content_package_id: OpaqueId
    script_artifact_id: OpaqueId
    sequence_ids: list[OpaqueId] = Field(default_factory=list)
    cut_ids: list[OpaqueId] = Field(default_factory=list)
    version: PositiveInt

    @model_validator(mode="after")
    def _validate_episode_lists(self) -> Episode:
        for field_name in ("sequence_ids", "cut_ids"):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
        return self


class Cut(Contract):
    """A deliverable variant selected from episode-level editorial objects."""

    schema_version: Literal["cut.v1"]
    cut_id: OpaqueId
    episode_id: OpaqueId
    kind: EditorialCutKind
    output_profile_id: OpaqueId
    sequence_ids: list[OpaqueId] = Field(default_factory=list)
    selection_manifest_id: OpaqueId | None = None

    @model_validator(mode="after")
    def _validate_cut_sequences(self) -> Cut:
        if len(set(self.sequence_ids)) != len(self.sequence_ids):
            raise ValueError("sequence_ids must not contain duplicates")
        return self


class Sequence(Contract):
    """A chapter or major section within the editorial hierarchy."""

    schema_version: Literal["sequence.v1"]
    sequence_id: OpaqueId
    episode_id: OpaqueId
    order_index: NonNegativeInt
    scene_ids: list[OpaqueId] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_sequence_scenes(self) -> Sequence:
        if len(set(self.scene_ids)) != len(self.scene_ids):
            raise ValueError("scene_ids must not contain duplicates")
        return self


class Scene(Contract):
    """A narration-centered semantic unit and preferred repair boundary."""

    schema_version: Literal["scene.v1"]
    scene_id: OpaqueId
    sequence_id: OpaqueId
    order_index: NonNegativeInt
    narration_artifact_id: OpaqueId | None = None
    claim_ids: list[OpaqueId] = Field(default_factory=list)
    shot_ids: list[OpaqueId] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_scene_lists(self) -> Scene:
        for field_name in ("claim_ids", "shot_ids"):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
        return self


class Shot(Contract):
    """A half-open frame range containing ordered visual layers."""

    schema_version: Literal["shot.v1"]
    shot_id: OpaqueId
    scene_id: OpaqueId
    order_index: NonNegativeInt
    start_frame: NonNegativeInt
    end_frame: PositiveInt
    layer_ids: list[OpaqueId] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_shot(self) -> Shot:
        if self.end_frame <= self.start_frame:
            raise ValueError("end_frame must be later than start_frame")
        if len(set(self.layer_ids)) != len(self.layer_ids):
            raise ValueError("layer_ids must not contain duplicates")
        return self


class LayerInstance(Contract):
    """One placed visual, audio, text, caption, or effect layer."""

    schema_version: Literal["layer-instance.v1"]
    layer_id: OpaqueId
    shot_id: OpaqueId
    kind: LayerKind
    start_frame: NonNegativeInt
    end_frame: PositiveInt
    asset_instance_id: OpaqueId | None = None
    payload_artifact_id: OpaqueId | None = None
    z_index: int = 0
    properties: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_layer(self) -> LayerInstance:
        if self.end_frame <= self.start_frame:
            raise ValueError("end_frame must be later than start_frame")
        return self


class CompositionRef(Contract):
    """Reference to an immutable resolved composition artifact for one cut."""

    schema_version: Literal["composition-ref.v1"]
    composition_artifact_id: OpaqueId
    cut_id: OpaqueId
    render_profile_id: OpaqueId
    render_profile_hash: Sha256Hex
    timebase: NonEmptyStr


__all__ = [
    "CompositionRef",
    "ContentPackage",
    "Cut",
    "Episode",
    "LayerInstance",
    "Scene",
    "Sequence",
    "Shot",
]
