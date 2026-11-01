"""Content-stage contracts for research, script generation, visual planning, and audio.

These contracts define the canonical data structures exchanged between the
research, script_generation, visual_planning, speech_generation, tts_adapter,
asr_alignment, and audio_qc stages and their capabilities.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from pipeline.contracts.base import (
    Contract,
    ExtensionObject,
    NonEmptyStr,
    NonNegativeFloat,
    NonNegativeInt,
    OpaqueId,
    PositiveInt,
    Sha256Hex,
    UnitInterval,
    UTCDateTime,
)
from pipeline.contracts.vocabularies import SourceKind, SpeechStrategy


class SourceRef(Contract):
    """Reference to an external or internal source document."""

    schema_version: Literal["source-ref.v1"]
    source_id: OpaqueId
    kind: SourceKind
    uri: NonEmptyStr
    title: NonEmptyStr
    author: NonEmptyStr | None = None
    published_at: UTCDateTime | None = None
    retrieved_at: UTCDateTime
    content_hash: Sha256Hex
    metadata: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_source_ref(self) -> SourceRef:
        if self.published_at is not None and self.published_at > self.retrieved_at:
            raise ValueError("published_at must not be later than retrieved_at")
        return self


class SourceSnapshot(Contract):
    """Immutable snapshot of source content at retrieval time."""

    schema_version: Literal["source-snapshot.v1"]
    snapshot_id: OpaqueId
    source_ref_id: OpaqueId
    content: NonEmptyStr
    content_hash: Sha256Hex
    token_count: PositiveInt
    language: NonEmptyStr = "en"
    extracted_at: UTCDateTime
    metadata: ExtensionObject = Field(default_factory=dict)


class Evidence(Contract):
    """A piece of evidence extracted from a source snapshot supporting a claim."""

    schema_version: Literal["evidence.v1"]
    evidence_id: OpaqueId
    snapshot_id: OpaqueId
    claim_id: OpaqueId
    text_span: NonEmptyStr
    start_offset: NonNegativeInt
    end_offset: PositiveInt
    confidence: UnitInterval
    metadata: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_evidence(self) -> Evidence:
        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset must be greater than start_offset")
        return self


class Claim(Contract):
    """An atomic verifiable statement extracted from sources."""

    schema_version: Literal["claim.v1"]
    claim_id: OpaqueId
    text: NonEmptyStr
    claim_type: Literal["FACTUAL", "NUMERIC", "QUOTE", "DEFINITION", "CAUSAL"]
    source_ref_ids: list[OpaqueId] = Field(default_factory=list)
    evidence_ids: list[OpaqueId] = Field(default_factory=list)
    confidence: UnitInterval
    tags: list[NonEmptyStr] = Field(default_factory=list)
    metadata: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_claim(self) -> Claim:
        for field_name in ("source_ref_ids", "evidence_ids", "tags"):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
        return self


class VisualIntent(Contract):
    """Visual intent for a scene or shot, describing what should be shown."""

    schema_version: Literal["visual-intent.v1"]
    visual_intent_id: OpaqueId
    scene_id: OpaqueId
    description: NonEmptyStr
    purpose: Literal[
        "ESTABLISHING",
        "ILLUSTRATIVE",
        "EVIDENCE",
        "DATA_VIZ",
        "TRANSITION",
        "BRANDING",
    ]
    elements: list[NonEmptyStr] = Field(default_factory=list)
    overlays: list[NonEmptyStr] = Field(default_factory=list)
    provenance_requirements: list[NonEmptyStr] = Field(default_factory=list)
    timing_hint_seconds: NonNegativeFloat | None = None
    metadata: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_visual_intent(self) -> VisualIntent:
        for field_name in ("elements", "overlays", "provenance_requirements"):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
        return self


class DurationPolicy(Contract):
    """Policy controlling scene and script duration allocation."""

    schema_version: Literal["duration-policy.v1"]
    policy_id: OpaqueId
    target_total_seconds: PositiveInt
    min_scene_seconds: PositiveInt = 3
    max_scene_seconds: PositiveInt = 30
    words_per_minute: PositiveInt = 150
    pause_seconds_per_comma: NonNegativeFloat = 0.2
    pause_seconds_per_period: NonNegativeFloat = 0.5
    intro_outro_seconds: NonNegativeInt = 5
    metadata: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_duration_policy(self) -> DurationPolicy:
        if self.max_scene_seconds < self.min_scene_seconds:
            raise ValueError("max_scene_seconds must be >= min_scene_seconds")
        return self


class ScriptScene(Contract):
    """A single scene in a script with narration, claims, and visual intents."""

    schema_version: Literal["script-scene.v1"]
    scene_id: OpaqueId
    script_id: OpaqueId
    order_index: NonNegativeInt
    narration: NonEmptyStr
    claim_ids: list[OpaqueId] = Field(default_factory=list)
    visual_intent_ids: list[OpaqueId] = Field(default_factory=list)
    estimated_duration_seconds: PositiveInt
    metadata: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_script_scene(self) -> ScriptScene:
        for field_name in ("claim_ids", "visual_intent_ids"):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
        return self


class Script(Contract):
    """Complete script with scenes, claims, evidence, and visual intents."""

    schema_version: Literal["script.v1"]
    script_id: OpaqueId
    episode_id: OpaqueId
    title: NonEmptyStr
    outline: NonEmptyStr
    scenes: list[ScriptScene] = Field(default_factory=list)
    claim_ids: list[OpaqueId] = Field(default_factory=list)
    evidence_ids: list[OpaqueId] = Field(default_factory=list)
    source_ref_ids: list[OpaqueId] = Field(default_factory=list)
    visual_intent_ids: list[OpaqueId] = Field(default_factory=list)
    duration_policy_id: OpaqueId
    total_estimated_duration_seconds: PositiveInt
    word_count: PositiveInt
    language: NonEmptyStr = "en"
    created_at: UTCDateTime
    metadata: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_script(self) -> Script:
        for field_name in (
            "claim_ids",
            "evidence_ids",
            "source_ref_ids",
            "visual_intent_ids",
        ):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
        if len(set(s.scene_id for s in self.scenes)) != len(self.scenes):
            raise ValueError("scene_ids must be unique within script")
        if len(set(s.order_index for s in self.scenes)) != len(self.scenes):
            raise ValueError("order_index must be unique within script")
        return self


class AudioTiming(Contract):
    """Per-scene audio timing alignment for TTS generation.

    Links a speech manifest to per-scene word-level timing derived from ASR
    forced alignment. Both continuous and scene-segmented speech strategies
    resolve to the same scene-addressable timing contract.
    """

    schema_version: Literal["audio-timing.v1"]
    audio_timing_id: OpaqueId
    speech_manifest_id: OpaqueId
    script_version: NonEmptyStr
    scene_id: OpaqueId
    audio_artifact_id: OpaqueId
    narration_text_hash: Sha256Hex
    word_timestamps: list[OpaqueId] = Field(default_factory=list)
    sample_rate: PositiveInt = 24000
    metadata: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_audio_timing(self) -> AudioTiming:
        if len(set(self.word_timestamps)) != len(self.word_timestamps):
            raise ValueError("word_timestamps must not contain duplicates")
        return self


class WordTimestamp(Contract):
    """Word-level timestamp from ASR forced alignment."""

    schema_version: Literal["word-timestamp.v1"]
    word_timestamp_id: OpaqueId
    audio_timing_id: OpaqueId
    word: NonEmptyStr
    start_frames: NonNegativeInt
    end_frames: PositiveInt
    confidence: UnitInterval
    metadata: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_word_timestamp(self) -> WordTimestamp:
        if self.end_frames <= self.start_frames:
            raise ValueError("end_frames must be greater than start_frames")
        return self


class SpeechManifest(Contract):
    """Normalized speech generation output for both CONTINUOUS and
    SCENE_SEGMENTED strategies.

    Composition must reject mismatched script versions, scene IDs, and narration
    text hashes. Both strategies resolve to equivalent scene-addressable timing.
    """

    schema_version: Literal["speech-manifest.v1"]
    speech_manifest_id: OpaqueId
    script_id: OpaqueId
    script_version: NonEmptyStr
    strategy: SpeechStrategy
    master_audio_artifact_id: OpaqueId
    scene_audio_artifact_ids: list[OpaqueId] = Field(default_factory=list)
    voice_config_hash: Sha256Hex
    narration_text_hashes: dict[OpaqueId, Sha256Hex] = Field(default_factory=dict)
    alignment_artifact_id: OpaqueId | None = None
    total_duration_seconds: PositiveInt
    sample_rate: PositiveInt = 24000
    metadata: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_speech_manifest(self) -> SpeechManifest:
        if len(set(self.scene_audio_artifact_ids)) != len(
            self.scene_audio_artifact_ids
        ):
            raise ValueError("scene_audio_artifact_ids must not contain duplicates")
        if len(self.narration_text_hashes) != len(self.scene_audio_artifact_ids):
            raise ValueError(
                "narration_text_hashes must have one entry per scene_audio_artifact_id"
            )
        for scene_id in self.narration_text_hashes:
            if scene_id not in self.scene_audio_artifact_ids:
                raise ValueError(
                    f"narration_text_hashes references unknown scene_id: {scene_id}"
                )
        return self


__all__ = [
    "AudioTiming",
    "Claim",
    "DurationPolicy",
    "Evidence",
    "Script",
    "ScriptScene",
    "SourceRef",
    "SourceSnapshot",
    "SpeechManifest",
    "VisualIntent",
    "WordTimestamp",
]
