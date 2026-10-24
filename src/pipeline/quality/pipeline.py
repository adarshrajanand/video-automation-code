"""Quality pipeline orchestration - runs checks in order.

Order: deterministic → specialized → semantic → human.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    from pipeline.storage.database import Database


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
    run_id: str = ""
    stage_instance_id: str | None = None
    logical_item_key: str | None = None


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
        database: Database | None = None,
    ) -> None:
        self.registry = registry
        self.gate = gate
        self.repair_planner = repair_planner
        self.human_review_manager = human_review_manager
        self._database = database

    def _persist_results(
        self,
        gate_result: QualityGateResult,
        evaluations: tuple[QualityEvaluation, ...],
        repair_plan: RepairPlan | None,
        human_review: HumanReview | None,
    ) -> None:
        """Persist quality results to database if available."""
        if self._database is None:
            return

        with self._database.transaction() as conn:
            from pipeline.storage.repositories.quality import (
                QualityEvaluationRepository,
                QualityGateResultRepository,
                RepairPlanRepository,
            )

            # Persist evaluations
            eval_repo = QualityEvaluationRepository(conn)
            for eval_record in evaluations:
                # Add run_id, stage_instance_id if available
                eval_data = eval_record.model_copy(
                    update={
                        "stage_instance_id": gate_result.stage_instance_id,
                        "logical_item_key": gate_result.logical_item_key,
                    }
                )
                eval_repo.insert(eval_data)

            # Persist gate result
            gate_repo = QualityGateResultRepository(conn)
            gate_repo.insert(gate_result)

            # Persist repair plan if any
            if repair_plan is not None:
                repair_repo = RepairPlanRepository(conn)
                repair_repo.insert(repair_plan)

            # Human review is persisted by HumanReviewManager.create_review

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
            manifest,
            artifacts,
            supporting_artifacts,
            stage_instance_id=config.stage_instance_id,
            logical_item_key=config.logical_item_key,
            regeneration_count=config.regeneration_count,
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
            if not config.run_id:
                raise ValueError("run_id required for human review")
            human_review = self.human_review_manager.create_review(
                HumanReviewRequest(
                    run_id=config.run_id,
                    stage_instance_id=gate_result.stage_instance_id,
                    gate_id=gate_result.gate_id,
                    target_artifact_ids=list(gate_result.target_artifact_ids),
                    target_hashes=dict(gate_result.target_hashes),
                    reason_codes=list(gate_result.hard_failure_codes)
                    or ["HUMAN_REVIEW_REQUIRED"],
                    requested_action="review_quality_gate",
                )
            )

        # Persist results
        self._persist_results(gate_result, evaluations, repair_plan, human_review)

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
    database: Database | None = None,
    human_review_manager: HumanReviewManager | None = None,
    run_id: str = "",
    stage_instance_id: str | None = None,
    logical_item_key: str | None = None,
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
        database: Optional database for persistence.
        human_review_manager: Optional human review manager
            (required if database provided).
        run_id: Workflow run ID (required for human review).
        stage_instance_id: Stage instance ID for linking.
        logical_item_key: Logical item key for linking.
        regeneration_count: Current regeneration attempt number.
        max_regenerations: Maximum allowed regenerations.
        after_max_regenerations: Action after max regenerations exceeded.

    Returns:
        QualityPipelineResult with all outcomes.
    """
    from pipeline.quality.gate import QualityGate
    from pipeline.quality.repair import RepairPlanner

    gate = QualityGate(gate_policy, registry)
    repair_planner = RepairPlanner(registry)

    if human_review_manager is None:
        if database is not None:
            from pipeline.quality.human_review import HumanReviewManager

            human_review_manager = HumanReviewManager(database)
        else:
            raise ValueError("human_review_manager or database must be provided")

    pipeline = QualityPipeline(
        registry, gate, repair_planner, human_review_manager, database
    )
    config = QualityPipelineConfig(
        gate_policy=gate_policy,
        run_id=run_id,
        stage_instance_id=stage_instance_id,
        logical_item_key=logical_item_key,
        regeneration_count=regeneration_count,
        max_regenerations=max_regenerations,
        after_max_regenerations=after_max_regenerations,
    )
    return pipeline.run(manifest, artifacts, supporting_artifacts, config)
