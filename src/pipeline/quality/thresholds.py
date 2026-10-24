"""Threshold records for quality gates with pass/review thresholds,
confidence intervals, and recalibration."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pipeline.contracts.base import (
    NonEmptyStr,
    OpaqueId,
    PositiveInt,
    UTCDateTime,
)
from pipeline.contracts.vocabularies import EvaluationKind

if TYPE_CHECKING:
    from pipeline.contracts.quality import QualityEvaluation


@dataclass(frozen=True, slots=True)
class ThresholdRecord:
    """Threshold configuration for one evaluation dimension.

    Contains pass/review thresholds, false-pass targets, confidence intervals,
    blind spots, and recalibration triggers.
    """

    schema_version: str = "threshold-record.v1"
    threshold_id: str = field(default_factory=lambda: f"thr_{uuid.uuid4().hex[:12]}")
    gate_id: NonEmptyStr = ""
    check_id: OpaqueId = ""
    dimension_name: NonEmptyStr = ""
    evaluation_kind: EvaluationKind = EvaluationKind.DETERMINISTIC

    # Core thresholds
    pass_threshold: float = 0.8
    review_threshold: float = 0.65

    # Statistical properties
    false_pass_target: float = 0.05  # Target false pass rate (5%)
    false_reject_target: float = 0.10  # Target false reject rate (10%)
    confidence_interval: tuple[float, float] = (
        0.95,
        0.99,
    )  # CI for threshold estimates

    # Blind spots and limitations
    blind_spots: list[NonEmptyStr] = field(default_factory=list)
    known_limitations: list[NonEmptyStr] = field(default_factory=list)

    # Recalibration
    recalibration_trigger: NonEmptyStr | None = None
    recalibration_interval_runs: PositiveInt = 100
    min_samples_for_recalibration: PositiveInt = 50

    # Version tracking
    rubric_version: NonEmptyStr | None = None
    estimator_version: NonEmptyStr = "1.0.0"
    created_at: UTCDateTime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: UTCDateTime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not (0.0 <= self.review_threshold <= self.pass_threshold <= 1.0):
            raise ValueError(
                "Thresholds must satisfy: 0 <= review_threshold <= pass_threshold <= 1"
            )
        if not (0.0 <= self.false_pass_target <= 1.0):
            raise ValueError("false_pass_target must be in [0, 1]")
        if not (0.0 <= self.false_reject_target <= 1.0):
            raise ValueError("false_reject_target must be in [0, 1]")
        ci_low, ci_high = self.confidence_interval
        if not (0.0 <= ci_low <= ci_high <= 1.0):
            raise ValueError("confidence_interval must satisfy 0 <= low <= high <= 1")

    def should_trigger_human_review(self, score: float | None) -> bool:
        """Check if a score should trigger human review."""
        if score is None:
            return True
        return score < self.review_threshold

    def should_pass(self, score: float | None) -> bool:
        """Check if a score should pass."""
        if score is None:
            return False
        return score >= self.pass_threshold

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "schema_version": self.schema_version,
            "threshold_id": self.threshold_id,
            "gate_id": self.gate_id,
            "check_id": self.check_id,
            "dimension_name": self.dimension_name,
            "evaluation_kind": self.evaluation_kind.value,
            "pass_threshold": self.pass_threshold,
            "review_threshold": self.review_threshold,
            "false_pass_target": self.false_pass_target,
            "false_reject_target": self.false_reject_target,
            "confidence_interval": list(self.confidence_interval),
            "blind_spots": self.blind_spots,
            "known_limitations": self.known_limitations,
            "recalibration_trigger": self.recalibration_trigger,
            "recalibration_interval_runs": self.recalibration_interval_runs,
            "min_samples_for_recalibration": self.min_samples_for_recalibration,
            "rubric_version": self.rubric_version,
            "estimator_version": self.estimator_version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> ThresholdRecord:
        """Deserialize from dictionary."""
        data = data.copy()
        data["evaluation_kind"] = EvaluationKind(data["evaluation_kind"])
        data["confidence_interval"] = tuple(data["confidence_interval"])
        data["created_at"] = datetime.fromisoformat(
            data["created_at"].replace("Z", "+00:00")
        )
        data["updated_at"] = datetime.fromisoformat(
            data["updated_at"].replace("Z", "+00:00")
        )
        return cls(**data)


class ThresholdRegistry:
    """Registry of threshold records for quality gates."""

    def __init__(self) -> None:
        self._thresholds: dict[
            str, ThresholdRecord
        ] = {}  # key: f"{gate_id}:{check_id}:{dimension_name}"

    def register(self, threshold: ThresholdRecord) -> None:
        """Register a threshold record."""
        key = f"{threshold.gate_id}:{threshold.check_id}:{threshold.dimension_name}"
        if key in self._thresholds:
            raise ValueError(f"Threshold {key!r} already registered")
        self._thresholds[key] = threshold

    def get(
        self, gate_id: str, check_id: str, dimension_name: str
    ) -> ThresholdRecord | None:
        """Get a threshold record."""
        key = f"{gate_id}:{check_id}:{dimension_name}"
        return self._thresholds.get(key)

    def get_for_gate(self, gate_id: str) -> list[ThresholdRecord]:
        """Get all thresholds for a gate."""
        return [t for k, t in self._thresholds.items() if k.startswith(f"{gate_id}:")]

    def get_for_check(self, check_id: str) -> list[ThresholdRecord]:
        """Get all thresholds for a check."""
        return [t for k, t in self._thresholds.items() if f":{check_id}:" in k]

    def update_thresholds(
        self,
        gate_id: str,
        check_id: str,
        dimension_name: str,
        pass_threshold: float | None = None,
        review_threshold: float | None = None,
    ) -> ThresholdRecord:
        """Update thresholds for a dimension (for recalibration)."""
        key = f"{gate_id}:{check_id}:{dimension_name}"
        if key not in self._thresholds:
            raise KeyError(f"Threshold {key!r} not found")

        current = self._thresholds[key]
        new_pass = (
            pass_threshold if pass_threshold is not None else current.pass_threshold
        )
        new_review = (
            review_threshold
            if review_threshold is not None
            else current.review_threshold
        )

        if not (0.0 <= new_review <= new_pass <= 1.0):
            raise ValueError("Invalid threshold values")

        updated = ThresholdRecord(
            **{
                **current.__dict__,
                "pass_threshold": new_pass,
                "review_threshold": new_review,
                "updated_at": datetime.now(UTC),
            }
        )
        self._thresholds[key] = updated
        return updated

    def __contains__(self, key: str) -> bool:
        return key in self._thresholds

    def __len__(self) -> int:
        return len(self._thresholds)


_default_threshold_registry: ThresholdRegistry | None = None


def get_default_threshold_registry() -> ThresholdRegistry:
    """Get the process-global default threshold registry."""
    global _default_threshold_registry
    if _default_threshold_registry is None:
        _default_threshold_registry = ThresholdRegistry()
        _populate_default_thresholds(_default_threshold_registry)
    return _default_threshold_registry


def _populate_default_thresholds(registry: ThresholdRegistry) -> None:
    """Populate registry with default threshold records."""

    # Script gate thresholds
    registry.register(
        ThresholdRecord(
            gate_id="script_gate_v1",
            check_id="script_claim_evidence_v1",
            dimension_name="claim_support",
            evaluation_kind=EvaluationKind.SEMANTIC,
            pass_threshold=0.80,
            review_threshold=0.65,
            false_pass_target=0.05,
            false_reject_target=0.10,
            confidence_interval=(0.90, 0.95),
            blind_spots=["subjective_claims", "future_predictions"],
            known_limitations=[
                "requires_evidence_snapshots",
                "limited_to_textual_claims",
            ],
            recalibration_trigger="false_pass_rate_exceeded",
            recalibration_interval_runs=100,
            min_samples_for_recalibration=50,
            rubric_version="claim-evidence-rubric-v1",
        )
    )

    registry.register(
        ThresholdRecord(
            gate_id="script_gate_v1",
            check_id="script_editorial_clarity_v1",
            dimension_name="clarity",
            evaluation_kind=EvaluationKind.SEMANTIC,
            pass_threshold=0.80,
            review_threshold=0.65,
            false_pass_target=0.05,
            false_reject_target=0.10,
            confidence_interval=(0.90, 0.95),
            blind_spots=["domain_jargon", "creative_writing_style"],
            known_limitations=["single_rater_bias", "rubric_version_dependent"],
            recalibration_trigger="false_pass_rate_exceeded",
            recalibration_interval_runs=100,
            min_samples_for_recalibration=50,
            rubric_version="editorial-rubric-v1",
        )
    )

    registry.register(
        ThresholdRecord(
            gate_id="script_gate_v1",
            check_id="script_editorial_clarity_v1",
            dimension_name="structure",
            evaluation_kind=EvaluationKind.SEMANTIC,
            pass_threshold=0.80,
            review_threshold=0.65,
            false_pass_target=0.05,
            false_reject_target=0.10,
            confidence_interval=(0.90, 0.95),
            blind_spots=["non_linear_narratives"],
            known_limitations=["rubric_version_dependent"],
            recalibration_trigger="false_pass_rate_exceeded",
            recalibration_interval_runs=100,
            min_samples_for_recalibration=50,
            rubric_version="editorial-rubric-v1",
        )
    )

    registry.register(
        ThresholdRecord(
            gate_id="script_gate_v1",
            check_id="script_editorial_clarity_v1",
            dimension_name="tone",
            evaluation_kind=EvaluationKind.SEMANTIC,
            pass_threshold=0.80,
            review_threshold=0.65,
            false_pass_target=0.05,
            false_reject_target=0.10,
            confidence_interval=(0.90, 0.95),
            blind_spots=["sarcasm", "irony"],
            known_limitations=[
                "rubric_version_dependent",
                "cultural_context_dependent",
            ],
            recalibration_trigger="false_pass_rate_exceeded",
            recalibration_interval_runs=100,
            min_samples_for_recalibration=50,
            rubric_version="editorial-rubric-v1",
        )
    )

    # Speech gate thresholds
    registry.register(
        ThresholdRecord(
            gate_id="speech_gate_v1",
            check_id="speech_wer_cer_v1",
            dimension_name="wer",
            evaluation_kind=EvaluationKind.SPECIALIZED,
            pass_threshold=0.90,  # 1 - max_wer
            review_threshold=0.85,
            false_pass_target=0.03,
            false_reject_target=0.08,
            confidence_interval=(0.95, 0.99),
            blind_spots=["accented_speech", "rare_proper_nouns"],
            known_limitations=["asr_model_dependent", "normalization_dependent"],
            recalibration_trigger="false_pass_rate_exceeded",
            recalibration_interval_runs=50,
            min_samples_for_recalibration=30,
        )
    )

    registry.register(
        ThresholdRecord(
            gate_id="speech_gate_v1",
            check_id="speech_wer_cer_v1",
            dimension_name="cer",
            evaluation_kind=EvaluationKind.SPECIALIZED,
            pass_threshold=0.95,  # 1 - max_cer
            review_threshold=0.90,
            false_pass_target=0.03,
            false_reject_target=0.08,
            confidence_interval=(0.95, 0.99),
            blind_spots=["homophones", "character_level_errors"],
            known_limitations=["asr_model_dependent", "normalization_dependent"],
            recalibration_trigger="false_pass_rate_exceeded",
            recalibration_interval_runs=50,
            min_samples_for_recalibration=30,
        )
    )

    registry.register(
        ThresholdRecord(
            gate_id="speech_gate_v1",
            check_id="speech_critical_tokens_v1",
            dimension_name="critical_tokens",
            evaluation_kind=EvaluationKind.SPECIALIZED,
            pass_threshold=1.0,
            review_threshold=1.0,
            false_pass_target=0.01,
            false_reject_target=0.05,
            confidence_interval=(0.99, 0.999),
            blind_spots=["phonetically_similar_tokens"],
            known_limitations=["requires_explicit_critical_token_list"],
            recalibration_trigger="false_pass_rate_exceeded",
            recalibration_interval_runs=50,
            min_samples_for_recalibration=30,
        )
    )

    registry.register(
        ThresholdRecord(
            gate_id="speech_gate_v1",
            check_id="speech_forced_alignment_v1",
            dimension_name="forced_alignment",
            evaluation_kind=EvaluationKind.SPECIALIZED,
            pass_threshold=0.90,
            review_threshold=0.80,
            false_pass_target=0.05,
            false_reject_target=0.10,
            confidence_interval=(0.95, 0.99),
            blind_spots=["overlapping_speech", "background_noise"],
            known_limitations=["alignment_model_dependent"],
            recalibration_trigger="false_pass_rate_exceeded",
            recalibration_interval_runs=50,
            min_samples_for_recalibration=30,
        )
    )

    registry.register(
        ThresholdRecord(
            gate_id="speech_gate_v1",
            check_id="speech_signal_quality_v1",
            dimension_name="snr",
            evaluation_kind=EvaluationKind.SPECIALIZED,
            pass_threshold=0.50,  # 30dB / 60dB normalized
            review_threshold=0.40,
            false_pass_target=0.10,
            false_reject_target=0.15,
            confidence_interval=(0.90, 0.95),
            blind_spots=["musical_background", "non_speech_audio"],
            known_limitations=["snr_estimation_method_dependent"],
            recalibration_trigger="false_pass_rate_exceeded",
            recalibration_interval_runs=100,
            min_samples_for_recalibration=50,
        )
    )

    # Visual plan gate thresholds
    registry.register(
        ThresholdRecord(
            gate_id="visual_plan_gate_v1",
            check_id="visual_intent_coherence_v1",
            dimension_name="coherence",
            evaluation_kind=EvaluationKind.SEMANTIC,
            pass_threshold=0.80,
            review_threshold=0.65,
            false_pass_target=0.05,
            false_reject_target=0.10,
            confidence_interval=(0.90, 0.95),
            blind_spots=["abstract_concepts", "metaphorical_visuals"],
            known_limitations=["rubric_version_dependent", "evaluator_model_dependent"],
            recalibration_trigger="false_pass_rate_exceeded",
            recalibration_interval_runs=100,
            min_samples_for_recalibration=50,
            rubric_version="visual-rubric-v1",
        )
    )

    registry.register(
        ThresholdRecord(
            gate_id="visual_plan_gate_v1",
            check_id="visual_intent_coherence_v1",
            dimension_name="coverage",
            evaluation_kind=EvaluationKind.SEMANTIC,
            pass_threshold=0.80,
            review_threshold=0.65,
            false_pass_target=0.05,
            false_reject_target=0.10,
            confidence_interval=(0.90, 0.95),
            blind_spots=["implicit_visual_requirements"],
            known_limitations=["rubric_version_dependent", "evaluator_model_dependent"],
            recalibration_trigger="false_pass_rate_exceeded",
            recalibration_interval_runs=100,
            min_samples_for_recalibration=50,
            rubric_version="visual-rubric-v1",
        )
    )

    # Composition gate thresholds
    registry.register(
        ThresholdRecord(
            gate_id="composition_gate_v1",
            check_id="composition_sync_v1",
            dimension_name="av_sync",
            evaluation_kind=EvaluationKind.SPECIALIZED,
            pass_threshold=0.90,  # 1 - max_drift/threshold
            review_threshold=0.80,
            false_pass_target=0.05,
            false_reject_target=0.10,
            confidence_interval=(0.95, 0.99),
            blind_spots=["variable_frame_rate", "drift_accumulation"],
            known_limitations=["sync_detection_method_dependent"],
            recalibration_trigger="false_pass_rate_exceeded",
            recalibration_interval_runs=100,
            min_samples_for_recalibration=50,
        )
    )

    # Render gate thresholds
    registry.register(
        ThresholdRecord(
            gate_id="render_gate_v1",
            check_id="render_decode_v1",
            dimension_name="decode_success",
            evaluation_kind=EvaluationKind.SPECIALIZED,
            pass_threshold=1.0,
            review_threshold=1.0,
            false_pass_target=0.001,
            false_reject_target=0.01,
            confidence_interval=(0.999, 0.9999),
            blind_spots=["container_level_corruption"],
            known_limitations=["decode_test_depth_limited"],
            recalibration_trigger="false_pass_rate_exceeded",
            recalibration_interval_runs=200,
            min_samples_for_recalibration=100,
        )
    )

    registry.register(
        ThresholdRecord(
            gate_id="render_gate_v1",
            check_id="render_profile_v1",
            dimension_name="profile_conformance",
            evaluation_kind=EvaluationKind.SPECIALIZED,
            pass_threshold=1.0,
            review_threshold=1.0,
            false_pass_target=0.01,
            false_reject_target=0.05,
            confidence_interval=(0.99, 0.999),
            blind_spots=["metadata_only_checks"],
            known_limitations=["profile_spec_completeness_dependent"],
            recalibration_trigger="false_pass_rate_exceeded",
            recalibration_interval_runs=100,
            min_samples_for_recalibration=50,
        )
    )

    # Assembly gate thresholds
    registry.register(
        ThresholdRecord(
            gate_id="assembly_gate_v1",
            check_id="assembly_integrity_v1",
            dimension_name="assembly_integrity",
            evaluation_kind=EvaluationKind.SPECIALIZED,
            pass_threshold=1.0,
            review_threshold=1.0,
            false_pass_target=0.001,
            false_reject_target=0.01,
            confidence_interval=(0.999, 0.9999),
            blind_spots=["chunk_boundary_artifacts"],
            known_limitations=["assembly_method_dependent"],
            recalibration_trigger="false_pass_rate_exceeded",
            recalibration_interval_runs=100,
            min_samples_for_recalibration=50,
        )
    )

    registry.register(
        ThresholdRecord(
            gate_id="assembly_gate_v1",
            check_id="assembly_audio_video_drift_v1",
            dimension_name="av_drift",
            evaluation_kind=EvaluationKind.SPECIALIZED,
            pass_threshold=0.85,  # 1 - 150ms/1000ms
            review_threshold=0.75,
            false_pass_target=0.05,
            false_reject_target=0.10,
            confidence_interval=(0.95, 0.99),
            blind_spots=["gradual_drift"],
            known_limitations=["measurement_window_limited"],
            recalibration_trigger="false_pass_rate_exceeded",
            recalibration_interval_runs=100,
            min_samples_for_recalibration=50,
        )
    )

    # Short derivative gate thresholds
    registry.register(
        ThresholdRecord(
            gate_id="short_gate_v1",
            check_id="short_derivative_integrity_v1",
            dimension_name="short_integrity",
            evaluation_kind=EvaluationKind.SPECIALIZED,
            pass_threshold=1.0,
            review_threshold=0.90,
            false_pass_target=0.05,
            false_reject_target=0.10,
            confidence_interval=(0.95, 0.99),
            blind_spots=["aspect_ratio_crops", "time_compression_artifacts"],
            known_limitations=["derivative_method_dependent"],
            recalibration_trigger="false_pass_rate_exceeded",
            recalibration_interval_runs=100,
            min_samples_for_recalibration=50,
        )
    )


def evaluate_against_thresholds(
    gate_id: str,
    evaluations: tuple[QualityEvaluation, ...],
    registry: ThresholdRegistry | None = None,
) -> dict[str, dict[str, bool]]:
    """Evaluate evaluation scores against registered thresholds.

    Returns:
        Dict mapping check_id -> dimension_name -> {pass, review, needs_recalibration}
    """
    if registry is None:
        registry = get_default_threshold_registry()

    results = {}
    for evaluation in evaluations:
        check_results = {}
        for dimension in evaluation.dimensions:
            threshold = registry.get(gate_id, evaluation.check_id, dimension.name)
            if threshold is None:
                check_results[dimension.name] = {
                    "pass": True,  # Default to pass if no threshold
                    "review": False,
                    "needs_recalibration": False,
                }
                continue

            score = dimension.score
            check_results[dimension.name] = {
                "pass": threshold.should_pass(score),
                "review": threshold.should_trigger_human_review(score),
                "needs_recalibration": False,  # Would be computed from historical data
            }
        results[evaluation.check_id] = check_results
    return results
