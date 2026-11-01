"""Composition, rendering, assembly, and short derivative contracts.

These contracts define the canonical data structures for the composition,
rendering, assembly, and short_derivative stages and their capabilities.
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
    StrictBoolean,
    UnitInterval,
    UTCDateTime,
)
from pipeline.contracts.vocabularies import LayerKind


class CompositionLayerSpec(Contract):
    """One placed visual, audio, text, caption, or effect layer in a shot."""

    schema_version: Literal["composition-layer-spec.v1"]
    layer_id: OpaqueId
    kind: LayerKind
    start_frame: NonNegativeInt
    end_frame: PositiveInt
    asset_instance_id: OpaqueId | None = None
    payload_artifact_id: OpaqueId | None = None
    z_index: int = 0
    properties: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_layer(self) -> CompositionLayerSpec:
        if self.end_frame <= self.start_frame:
            raise ValueError("end_frame must be later than start_frame")
        return self


class CompositionShotSpec(Contract):
    """A half-open frame range containing ordered visual layers."""

    schema_version: Literal["composition-shot-spec.v1"]
    shot_id: OpaqueId
    order_index: NonNegativeInt
    start_frame: NonNegativeInt
    end_frame: PositiveInt
    layer_ids: list[OpaqueId] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_shot(self) -> CompositionShotSpec:
        if self.end_frame <= self.start_frame:
            raise ValueError("end_frame must be later than start_frame")
        if len(set(self.layer_ids)) != len(self.layer_ids):
            raise ValueError("layer_ids must not contain duplicates")
        return self


class CompositionSceneSpec(Contract):
    """A narration-centered semantic unit with shots and audio."""

    schema_version: Literal["composition-scene-spec.v1"]
    scene_id: OpaqueId
    order_index: NonNegativeInt
    narration_artifact_id: OpaqueId | None = None
    shot_ids: list[OpaqueId] = Field(default_factory=list)
    audio_track_ids: list[OpaqueId] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_scene(self) -> CompositionSceneSpec:
        for field_name in ("shot_ids", "audio_track_ids"):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
        return self


class CompositionSequenceSpec(Contract):
    """A chapter or major section within the editorial hierarchy."""

    schema_version: Literal["composition-sequence-spec.v1"]
    sequence_id: OpaqueId
    order_index: NonNegativeInt
    scene_ids: list[OpaqueId] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_sequence(self) -> CompositionSequenceSpec:
        if len(set(self.scene_ids)) != len(self.scene_ids):
            raise ValueError("scene_ids must not contain duplicates")
        return self


class CompositionAudioTrackSpec(Contract):
    """An audio track spanning a frame range with optional volume envelope."""

    schema_version: Literal["composition-audio-track-spec.v1"]
    audio_track_id: OpaqueId
    kind: Literal["VOICE", "MUSIC", "EFFECT", "AMBIENCE"]
    start_frame: NonNegativeInt
    end_frame: PositiveInt
    audio_artifact_id: OpaqueId
    volume: UnitInterval = 1.0
    fade_in_frames: NonNegativeInt = 0
    fade_out_frames: NonNegativeInt = 0

    @model_validator(mode="after")
    def _validate_audio_track(self) -> CompositionAudioTrackSpec:
        if self.end_frame <= self.start_frame:
            raise ValueError("end_frame must be later than start_frame")
        return self


class CompositionAuthoringSpec(Contract):
    """Authoring metadata and deterministic fingerprint inputs."""

    schema_version: Literal["composition-authoring-spec.v1"]
    schema_version_id: NonEmptyStr
    input_artifact_ids: list[OpaqueId] = Field(default_factory=list)
    input_artifact_hashes: dict[OpaqueId, Sha256Hex] = Field(default_factory=dict)
    effective_config_hash: Sha256Hex
    renderer_version: NonEmptyStr
    fonts_version: NonEmptyStr
    template_version: NonEmptyStr
    timebase: NonEmptyStr
    frame_rate: PositiveInt
    random_seed: NonNegativeInt

    @model_validator(mode="after")
    def _validate_authoring(self) -> CompositionAuthoringSpec:
        if len(set(self.input_artifact_ids)) != len(self.input_artifact_ids):
            raise ValueError("input_artifact_ids must not contain duplicates")
        for aid in self.input_artifact_ids:
            if aid not in self.input_artifact_hashes:
                raise ValueError(f"missing hash for input artifact: {aid}")
        return self


class CompositionSpec(Contract):
    """Immutable resolved composition manifest for one cut (render-manifest.v1)."""

    schema_version: Literal["render-manifest.v1"]
    composition_artifact_id: OpaqueId
    cut_id: OpaqueId
    render_profile_id: OpaqueId
    render_profile_hash: Sha256Hex
    timebase: NonEmptyStr
    frame_rate: PositiveInt
    width: PositiveInt
    height: PositiveInt
    duration_frames: PositiveInt
    authoring: CompositionAuthoringSpec
    sequences: list[CompositionSequenceSpec] = Field(default_factory=list)
    scenes: list[CompositionSceneSpec] = Field(default_factory=list)
    shots: list[CompositionShotSpec] = Field(default_factory=list)
    layers: list[CompositionLayerSpec] = Field(default_factory=list)
    audio_tracks: list[CompositionAudioTrackSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_composition(self) -> CompositionSpec:
        # Check unique IDs within each collection
        for field_name in ("sequences", "scenes", "shots", "layers", "audio_tracks"):
            items = getattr(self, field_name)
            ids = [getattr(item, f"{field_name[:-1]}_id") for item in items]
            if len(set(ids)) != len(ids):
                raise ValueError(f"{field_name} must not contain duplicate IDs")
        return self


class ResolvedArtifactRef(Contract):
    """Resolved reference to an immutable artifact with its hash and URI."""

    schema_version: Literal["resolved-artifact-ref.v1"]
    artifact_id: OpaqueId
    artifact_type: NonEmptyStr
    uri: NonEmptyStr
    sha256: Sha256Hex
    size_bytes: NonNegativeInt
    media_type: NonEmptyStr | None = None
    media_metadata: ExtensionObject = Field(default_factory=dict)


class RenderProfile(Contract):
    """Output profile for rendering: codec, resolution, bitrate, etc."""

    schema_version: Literal["render-profile.v1"]
    render_profile_id: OpaqueId
    name: NonEmptyStr
    width: PositiveInt
    height: PositiveInt
    frame_rate: PositiveInt
    video_codec: NonEmptyStr = "libx264"
    video_bitrate_kbps: PositiveInt = 8000
    audio_codec: NonEmptyStr = "aac"
    audio_bitrate_kbps: PositiveInt = 192
    audio_sample_rate: PositiveInt = 48000
    pixel_format: NonEmptyStr = "yuv420p"
    color_space: NonEmptyStr = "bt709"
    profile: NonEmptyStr = "high"
    level: NonEmptyStr = "4.1"
    preset: NonEmptyStr = "medium"
    crf: NonNegativeInt = 18
    metadata: ExtensionObject = Field(default_factory=dict)


class RenderChunkManifest(Contract):
    """Manifest for one rendered chunk or complete cut."""

    schema_version: Literal["render-chunk-manifest.v1"]
    chunk_id: OpaqueId
    composition_artifact_id: OpaqueId
    render_profile_id: OpaqueId
    start_frame: NonNegativeInt
    end_frame: PositiveInt
    output_artifact_id: OpaqueId
    output_uri: NonEmptyStr
    output_sha256: Sha256Hex
    output_size_bytes: NonNegativeInt
    duration_frames: PositiveInt
    frame_checksums: list[Sha256Hex] = Field(default_factory=list)
    renderer_version: NonEmptyStr
    render_started_at: UTCDateTime
    render_finished_at: UTCDateTime
    metadata: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_chunk(self) -> RenderChunkManifest:
        if self.end_frame <= self.start_frame:
            raise ValueError("end_frame must be later than start_frame")
        if self.duration_frames != self.end_frame - self.start_frame:
            raise ValueError("duration_frames must equal end_frame - start_frame")
        if self.frame_checksums and len(self.frame_checksums) != self.duration_frames:
            raise ValueError("frame_checksums length must match duration_frames")
        return self


class AssemblyManifest(Contract):
    """Assembly manifest recording ordered chunks and continuity checks."""

    schema_version: Literal["assembly-manifest.v1"]
    assembly_artifact_id: OpaqueId
    cut_id: OpaqueId
    composition_artifact_id: OpaqueId
    render_profile_id: OpaqueId
    chunk_ids: list[OpaqueId] = Field(default_factory=list)
    chunk_manifest_ids: list[OpaqueId] = Field(default_factory=list)
    total_duration_frames: PositiveInt
    continuity_checks_passed: StrictBoolean = True
    continuity_failures: list[NonEmptyStr] = Field(default_factory=list)
    output_artifact_id: OpaqueId
    output_uri: NonEmptyStr
    output_sha256: Sha256Hex
    output_size_bytes: NonNegativeInt
    assembler_version: NonEmptyStr
    assembled_at: UTCDateTime
    metadata: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_assembly(self) -> AssemblyManifest:
        if len(set(self.chunk_ids)) != len(self.chunk_ids):
            raise ValueError("chunk_ids must not contain duplicates")
        if len(set(self.chunk_manifest_ids)) != len(self.chunk_manifest_ids):
            raise ValueError("chunk_manifest_ids must not contain duplicates")
        if len(self.chunk_ids) != len(self.chunk_manifest_ids):
            raise ValueError("chunk_ids and chunk_manifest_ids must have same length")
        return self


class ShortSelectionManifest(Contract):
    """Manifest selecting scenes/shots for a short derivative."""

    schema_version: Literal["short-selection-manifest.v1"]
    selection_manifest_id: OpaqueId
    cut_id: OpaqueId
    source_composition_artifact_id: OpaqueId
    target_render_profile_id: OpaqueId
    selected_scene_ids: list[OpaqueId] = Field(default_factory=list)
    selected_shot_ids: list[OpaqueId] = Field(default_factory=list)
    safe_area: ExtensionObject = Field(default_factory=dict)
    vertical_composition: StrictBoolean = True
    target_aspect_ratio: NonEmptyStr = "9:16"
    metadata: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_short_selection(self) -> ShortSelectionManifest:
        if len(set(self.selected_scene_ids)) != len(self.selected_scene_ids):
            raise ValueError("selected_scene_ids must not contain duplicates")
        if len(set(self.selected_shot_ids)) != len(self.selected_shot_ids):
            raise ValueError("selected_shot_ids must not contain duplicates")
        return self


__all__ = [
    "AssemblyManifest",
    "CompositionAudioTrackSpec",
    "CompositionAuthoringSpec",
    "CompositionLayerSpec",
    "CompositionSceneSpec",
    "CompositionSequenceSpec",
    "CompositionShotSpec",
    "CompositionSpec",
    "RenderChunkManifest",
    "RenderProfile",
    "ResolvedArtifactRef",
    "ShortSelectionManifest",
]
