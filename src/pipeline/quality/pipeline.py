"""Quality pipeline orchestration - runs checks in order.

Order: deterministic → specialized → semantic → human.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pipeline.contracts.quality import (
    QualityEvaluation,
    QualityGatePolicy,
    QualityGateResult,
    QualityInputManifest,
)
from pipeline.contracts.vocabularies import GateDecision

if TYPE_CHECKING:
    from pipeline.quality.gate import QualityGate
    from pipeline.quality.human_review import (
        HumanReview,
        HumanReviewManager,
        HumanReviewRequest,
    )
    from pipeline.quality.registry import QualityCheckRegistry
    from pipeline.quality.repair import RepairPlan, RepairPlanner


@dataclass(slots=True)
class QualityPipelineResult:
    """Result of running the quality pipeline for one gate."""

    gate_result: QualityGateResult
    evaluations: tuple[QualityEvaluation, ...]
    repair_plan: RepairPlan | None
    human_review: HumanReview | None


@dataclass(slots=True)
class QualityPipelineConfig:
    """Configuration for quality pipeline execution."""

    gate_policy: QualityGatePolicy
    regeneration_count: int = 0
    max_regenerations: int = 2
    after_max_regenerations: str = "HUMAN_REVIEW"


class QualityPipeline:
    """Orchestrates the quality pipeline for a single gate.

    Execution order:
    1. Deterministic checks (schema, references, timeline)
    2. Specialized checks (WER/CER, signal, media decode, sync)
    3. Semantic checks (claim/evidence, editorial, visual)
    4. Human checks (review gates)

    Within each category, checks run in policy order.
    """

    def __init__(
        self,
        registry: QualityCheckRegistry,
        gate: QualityGate,
        repair_planner: RepairPlanner,
        human_review_manager: HumanReviewManager,
    ) -> None:
        self.registry = registry
        self.gate = gate
        self.repair_planner = repair_planner
        self.human_review_manager = human_review_manager

    def run(
        self,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
        supporting_artifacts: dict[str, Any],
        config: QualityPipelineConfig,
    ) -> QualityPipelineResult:
        """Run the full quality pipeline for a gate.

        Args:
            manifest: Input manifest with target artifacts.
            artifacts: Loaded target artifacts.
            supporting_artifacts: Loaded supporting artifacts.
            config: Pipeline configuration including policy and regeneration state.

        Returns:
            QualityPipelineResult with gate result, evaluations, and
            any repair/review actions.
        """
        # Run gate evaluation (handles all check categories in order)
        gate_result, evaluations = self.gate.evaluate(
            manifest, artifacts, supporting_artifacts
        )

        repair_plan = None
        human_review = None

        if gate_result.decision is GateDecision.REGENERATE:
            repair_plan = self.repair_planner.plan_repair(
                gate_result=gate_result,
                regeneration_count=config.regeneration_count,
                max_regenerations=config.max_regenerations,
                after_max_regenerations=config.after_max_regenerations,
            )

        elif gate_result.decision is GateDecision.HUMAN_REVIEW:
            # Create human review request
            human_review = self.human_review_manager.create_review(
                HumanReviewRequest(
                    run_id="",  # Would be passed in real implementation
                    stage_instance_id=gate_result.stage_instance_id,
                    gate_id=gate_result.gate_id,
                    target_artifact_ids=list(gate_result.target_artifact_ids),
                    target_hashes=dict(gate_result.target_hashes),
                    reason_codes=list(gate_result.hard_failure_codes)
                    or ["HUMAN_REVIEW_REQUIRED"],
                    requested_action="review_quality_gate",
                )
            )

        return QualityPipelineResult(
            gate_result=gate_result,
            evaluations=evaluations,
            repair_plan=repair_plan,
            human_review=human_review,
        )


def run_quality_pipeline(
    registry: QualityCheckRegistry,
    gate_policy: QualityGatePolicy,
    manifest: QualityInputManifest,
    artifacts: dict[str, Any],
    supporting_artifacts: dict[str, Any],
    regeneration_count: int = 0,
    max_regenerations: int = 2,
    after_max_regenerations: str = "HUMAN_REVIEW",
) -> QualityPipelineResult:
    """Convenience function to run the quality pipeline.

    Args:
        registry: Quality check registry.
        gate_policy: Gate policy to evaluate.
        manifest: Input manifest.
        artifacts: Target artifacts.
        supporting_artifacts: Supporting artifacts.
        regeneration_count: Current regeneration attempt number.
        max_regenerations: Maximum allowed regenerations.
        after_max_regenerations: Action after max regenerations exceeded.

    Returns:
        QualityPipelineResult with all outcomes.
    """
    from pipeline.quality.gate import QualityGate
    from pipeline.quality.repair import RepairPlanner

    # These would be properly injected in real usage
    gate = QualityGate(gate_policy, registry)
    repair_planner = RepairPlanner(registry)

    # HumanReviewManager requires a database - use a mock for now
    class MockHumanReviewManager:
        def create_review(self, request):
            from pipeline.contracts.review import HumanReview
            from pipeline.contracts.vocabularies import ReviewStatus

            return HumanReview(
                schema_version="human-review.v1",
                review_id=f"review_{uuid.uuid4().hex[:12]}",
                run_id=request.run_id or "unknown",
                stage_instance_id=request.stage_instance_id,
                gate_id=request.gate_id,
                target_artifact_ids=request.target_artifact_ids,
                target_hashes=request.target_hashes,
                reason_codes=request.reason_codes,
                requested_action=request.requested_action,
                status=ReviewStatus.OPEN,
                created_at=datetime.now(UTC),
                resolved_at=None,
            )

    human_review_manager = MockHumanReviewManager()

    pipeline = QualityPipeline(registry, gate, repair_planner, human_review_manager)
    config = QualityPipelineConfig(
        gate_policy=gate_policy,
        regeneration_count=regeneration_count,
        max_regenerations=max_regenerations,
        after_max_regenerations=after_max_regenerations,
    )
    return pipeline.run(manifest, artifacts, supporting_artifacts, config)
