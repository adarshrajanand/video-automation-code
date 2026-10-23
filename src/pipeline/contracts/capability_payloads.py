"""Capability payload contracts for content and audio stages.

These are the input/output payload schemas for the research, script_generation,
visual_planning, speech_generation, tts_adapter, asr_alignment, and audio_qc
capabilities. They are versioned independently from the core content contracts.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from pipeline.contracts.base import (
    Contract,
    ExtensionObject,
    FiniteFloat,
    NonEmptyStr,
    NonNegativeFloat,
    NonNegativeInt,
    OpaqueId,
    PositiveInt,
    Sha256Hex,
)
from pipeline.contracts.vocabularies import SourceKind, SpeechStrategy


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
    "ASRAlignmentInputPayload",
    "ASRAlignmentOutputPayload",
    "AudioQCInputPayload",
    "AudioQCOutputPayload",
    "ResearchInputPayload",
    "ResearchOutputPayload",
    "ScriptGenerationInputPayload",
    "ScriptGenerationOutputPayload",
    "SpeechGenerationInputPayload",
    "SpeechGenerationOutputPayload",
    "TTSAdapterInputPayload",
    "TTSAdapterOutputPayload",
    "VisualPlanningInputPayload",
    "VisualPlanningOutputPayload",
]


class SpeechGenerationInputPayload(Contract):
    """Input payload for the speech_generation capability."""

    schema_version: Literal["speech-generation-input.v1"]
    script_id: OpaqueId
    script_version: NonEmptyStr
    scene_ids: list[OpaqueId] = Field(default_factory=list)
    strategy: SpeechStrategy
    voice_config: ExtensionObject = Field(default_factory=dict)
    narration_texts: dict[OpaqueId, NonEmptyStr] = Field(default_factory=dict)
    language: NonEmptyStr = "en"
    metadata: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_speech_generation_input(self) -> SpeechGenerationInputPayload:
        if len(set(self.scene_ids)) != len(self.scene_ids):
            raise ValueError("scene_ids must not contain duplicates")
        if len(self.narration_texts) != len(self.scene_ids):
            raise ValueError("narration_texts must have one entry per scene_id")
        for scene_id in self.narration_texts:
            if scene_id not in self.scene_ids:
                raise ValueError(
                    f"narration_texts references unknown scene_id: {scene_id}"
                )
        return self


class SpeechGenerationOutputPayload(Contract):
    """Output payload for the speech_generation capability."""

    schema_version: Literal["speech-generation-output.v1"]
    speech_manifest_id: OpaqueId
    master_audio_artifact_id: OpaqueId
    scene_audio_artifact_ids: list[OpaqueId] = Field(default_factory=list)
    voice_config_hash: Sha256Hex
    narration_text_hashes: dict[OpaqueId, Sha256Hex] = Field(default_factory=dict)
    total_duration_seconds: PositiveInt
    sample_rate: PositiveInt = 24000
    scene_count: PositiveInt
    metadata: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_speech_generation_output(self) -> SpeechGenerationOutputPayload:
        if len(set(self.scene_audio_artifact_ids)) != len(
            self.scene_audio_artifact_ids
        ):
            raise ValueError("scene_audio_artifact_ids must not contain duplicates")
        if len(self.narration_text_hashes) != len(self.scene_audio_artifact_ids):
            raise ValueError(
                "narration_text_hashes must have one entry per scene_audio_artifact_id"
            )
        return self


class TTSAdapterInputPayload(Contract):
    """Input payload for the tts_adapter capability."""

    schema_version: Literal["tts-adapter-input.v1"]
    narration_text: NonEmptyStr
    voice_id: NonEmptyStr
    provider: NonEmptyStr
    model: NonEmptyStr
    voice_config: ExtensionObject = Field(default_factory=dict)
    sample_rate: PositiveInt = 24000
    metadata: ExtensionObject = Field(default_factory=dict)


class TTSAdapterOutputPayload(Contract):
    """Output payload for the tts_adapter capability."""

    schema_version: Literal["tts-adapter-output.v1"]
    audio_artifact_id: OpaqueId
    voice_id: NonEmptyStr
    provider: NonEmptyStr
    model: NonEmptyStr
    voice_config_hash: Sha256Hex
    narration_text_hash: Sha256Hex
    duration_seconds: NonNegativeFloat
    sample_rate: PositiveInt
    metadata: ExtensionObject = Field(default_factory=dict)


class ASRAlignmentInputPayload(Contract):
    """Input payload for the asr_alignment capability."""

    schema_version: Literal["asr-alignment-input.v1"]
    audio_artifact_id: OpaqueId
    narration_text: NonEmptyStr
    language: NonEmptyStr = "en"
    metadata: ExtensionObject = Field(default_factory=dict)


class ASRAlignmentOutputPayload(Contract):
    """Output payload for the asr_alignment capability."""

    schema_version: Literal["asr-alignment-output.v1"]
    alignment_artifact_id: OpaqueId
    audio_timing_ids: list[OpaqueId] = Field(default_factory=list)
    word_timestamp_ids: list[OpaqueId] = Field(default_factory=list)
    asr_transcript: NonEmptyStr
    narration_text_hash: Sha256Hex
    confidence: NonNegativeFloat
    metadata: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_asr_alignment_output(self) -> ASRAlignmentOutputPayload:
        if len(set(self.audio_timing_ids)) != len(self.audio_timing_ids):
            raise ValueError("audio_timing_ids must not contain duplicates")
        if len(set(self.word_timestamp_ids)) != len(self.word_timestamp_ids):
            raise ValueError("word_timestamp_ids must not contain duplicates")
        return self


class AudioQCInputPayload(Contract):
    """Input payload for the audio_qc capability."""

    schema_version: Literal["audio-qc-input.v1"]
    audio_artifact_id: OpaqueId
    expected_narration_text: NonEmptyStr
    target_loudness_lufs: FiniteFloat = -24.0
    target_peak_db: FiniteFloat = -1.0
    metadata: ExtensionObject = Field(default_factory=dict)


class AudioQCOutputPayload(Contract):
    """Output payload for the audio_qc capability."""

    schema_version: Literal["audio-qc-output.v1"]
    audio_artifact_id: OpaqueId
    measured_loudness_lufs: FiniteFloat
    measured_peak_db: FiniteFloat
    loudness_pass: bool
    peak_pass: bool
    fidelity_pass: bool
    narration_text_hash: Sha256Hex
    omitted_phrases: list[NonEmptyStr] = Field(default_factory=list)
    changed_phrases: list[NonEmptyStr] = Field(default_factory=list)
    metadata: ExtensionObject = Field(default_factory=dict)
