"""Quality gate evaluation and aggregation logic."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pipeline.contracts.quality import (
    QualityCheck,
    QualityEvaluation,
    QualityGatePolicy,
    QualityGateResult,
    QualityInputManifest,
)
from pipeline.contracts.vocabularies import (
    CheckOutcome,
    FailureCode,
    GateDecision,
    QualityFailureAction,
    RepairScope,
    Severity,
)

if TYPE_CHECKING:
    from pipeline.quality.registry import QualityCheckRegistry


@dataclass(slots=True)
class CheckEvaluationResult:
    """Result of evaluating a single check within a gate."""

    check: QualityCheck
    evaluation: QualityEvaluation
    is_hard_failure: bool


def evaluate_gate(
    policy: QualityGatePolicy,
    manifest: QualityInputManifest,
    evaluations: tuple[QualityEvaluation, ...],
    registry: QualityCheckRegistry,
) -> QualityGateResult:
    """Aggregate check evaluations into a gate decision.

    The aggregation follows these rules:
    1. Any evaluation with outcome ERROR → gate decision FAIL
    2. Required check FAIL with severity CRITICAL → gate decision FAIL
    3. Check with failure_code in hard_failure_codes → gate decision FAIL
    4. All required checks PASS → gate decision PASS
    5. Required check FAIL (non-critical), max_regenerations not exceeded → REGENERATE
    6. Max regenerations exceeded → apply after_max_regenerations
    7. Semantic check below human_review_threshold → HUMAN_REVIEW
    8. Check outcome ABSTAIN → HUMAN_REVIEW

    Args:
        policy: The quality gate policy defining required checks and thresholds.
        manifest: The input manifest for this gate evaluation.
        evaluations: Tuple of completed evaluations for each required check.
        registry: The quality check registry for check metadata lookup.

    Returns:
        A QualityGateResult with the aggregate decision and repair scope.
    """
    created_at = datetime.now(UTC)
    evaluation_ids = tuple(e.evaluation_id for e in evaluations)
    required_check_ids = policy.required_check_ids
    hard_failure_codes: list[FailureCode] = []

    # Rule 1: Check for ERROR outcomes
    for evaluation in evaluations:
        if evaluation.outcome is CheckOutcome.ERROR:
            return _create_gate_result(
                policy=policy,
                manifest=manifest,
                evaluation_ids=evaluation_ids,
                decision=GateDecision.FAIL,
                hard_failure_codes=[FailureCode.QUALITY_GENERIC],
                repair_scope=None,
                created_at=created_at,
                completed_at=datetime.now(UTC),
            )

    # Rule 2 & 3: Check for hard failures (CRITICAL severity or hard_failure_codes)
    for evaluation in evaluations:
        check = _get_check(registry, evaluation.check_id)
        if check is None:
            continue

        # Check for hard failure codes in this evaluation's dimensions
        for dimension in evaluation.dimensions:
            for failure_code in dimension.failure_codes:
                if (
                    failure_code in policy.hard_failure_codes
                    and failure_code not in hard_failure_codes
                ):
                    hard_failure_codes.append(failure_code)

        # Check for CRITICAL severity on required checks
        if check.required and evaluation.outcome is CheckOutcome.FAIL:
            for dimension in evaluation.dimensions:
                if (
                    dimension.severity is Severity.CRITICAL
                    and FailureCode.QUALITY_GENERIC not in hard_failure_codes
                ):
                    hard_failure_codes.append(FailureCode.QUALITY_GENERIC)

    if hard_failure_codes:
        return _create_gate_result(
            policy=policy,
            manifest=manifest,
            evaluation_ids=evaluation_ids,
            decision=GateDecision.FAIL,
            hard_failure_codes=tuple(hard_failure_codes),
            repair_scope=None,
            created_at=created_at,
            completed_at=datetime.now(UTC),
        )

    # Rule 4: All required checks PASS
    all_required_pass = all(
        _evaluation_for_check(evaluations, check_id) is not None
        and _evaluation_for_check(evaluations, check_id).outcome is CheckOutcome.PASS
        for check_id in required_check_ids
    )

    if all_required_pass:
        # Check if any dimension score is below human_review_threshold
        needs_human_review = False
        for evaluation in evaluations:
            check = _get_check(registry, evaluation.check_id)
            if check is None or check.kind.name != "SEMANTIC":
                continue
            for dimension in evaluation.dimensions:
                hr_threshold = policy.human_review_thresholds.get(dimension.name)
                if (
                    hr_threshold is not None
                    and dimension.score is not None
                    and dimension.score < hr_threshold
                ):
                    needs_human_review = True
                    break

        if needs_human_review:
            return _create_gate_result(
                policy=policy,
                manifest=manifest,
                evaluation_ids=evaluation_ids,
                decision=GateDecision.HUMAN_REVIEW,
                hard_failure_codes=(),
                repair_scope=None,
                created_at=created_at,
                completed_at=datetime.now(UTC),
            )

        return _create_gate_result(
            policy=policy,
            manifest=manifest,
            evaluation_ids=evaluation_ids,
            decision=GateDecision.PASS,
            hard_failure_codes=(),
            repair_scope=None,
            created_at=created_at,
            completed_at=datetime.now(UTC),
        )

    # Rule 5 & 6: Some required checks FAIL - check regeneration policy
    # Count failed required checks (non-hard-failure)
    failed_required = 0
    max_severity = Severity.INFO
    failure_action = QualityFailureAction.REGENERATE
    repair_scope = RepairScope.NONE

    for evaluation in evaluations:
        check = _get_check(registry, evaluation.check_id)
        if check is None or not check.required:
            continue

        if evaluation.outcome is CheckOutcome.FAIL:
            failed_required += 1
            # Determine worst severity and action
            for dimension in evaluation.dimensions:
                if _severity_order(dimension.severity) > _severity_order(max_severity):
                    max_severity = dimension.severity
            if _action_order(check.on_failure) > _action_order(failure_action):
                failure_action = check.on_failure
            if _repair_scope_order(check.repair_scope) > _repair_scope_order(
                repair_scope
            ):
                repair_scope = check.repair_scope

    # Check if any evaluation abstained
    any_abstained = any(e.outcome is CheckOutcome.ABSTAIN for e in evaluations)

    if any_abstained:
        # Human review checks abstain - escalate to human review
        return _create_gate_result(
            policy=policy,
            manifest=manifest,
            evaluation_ids=evaluation_ids,
            decision=GateDecision.HUMAN_REVIEW,
            hard_failure_codes=(),
            repair_scope=None,
            created_at=created_at,
            completed_at=datetime.now(UTC),
        )

    # Determine if we've exceeded max regenerations
    # This would be tracked externally (e.g., in the workflow state)
    # For now, we assume we're within limits and use the check's on_failure
    if failure_action is QualityFailureAction.HUMAN_REVIEW:
        decision = GateDecision.HUMAN_REVIEW
        repair_scope = None
    elif failure_action is QualityFailureAction.FAIL:
        decision = GateDecision.FAIL
        repair_scope = None
    else:  # REGENERATE
        decision = GateDecision.REGENERATE

    return _create_gate_result(
        policy=policy,
        manifest=manifest,
        evaluation_ids=evaluation_ids,
        decision=decision,
        hard_failure_codes=(),
        repair_scope=repair_scope if decision is GateDecision.REGENERATE else None,
        created_at=created_at,
        completed_at=datetime.now(UTC),
    )


def _get_check(registry: QualityCheckRegistry, check_id: str) -> QualityCheck | None:
    """Safely get a check from the registry."""
    try:
        return registry.get(check_id)
    except KeyError:
        return None


def _evaluation_for_check(
    evaluations: tuple[QualityEvaluation, ...], check_id: str
) -> QualityEvaluation | None:
    """Find evaluation for a specific check_id."""
    for e in evaluations:
        if e.check_id == check_id:
            return e
    return None


def _severity_order(severity: Severity) -> int:
    """Return numeric order for severity comparison."""
    order = {
        Severity.INFO: 0,
        Severity.MINOR: 1,
        Severity.MAJOR: 2,
        Severity.CRITICAL: 3,
    }
    return order.get(severity, 0)


def _action_order(action: QualityFailureAction) -> int:
    """Return numeric order for failure action comparison."""
    order = {
        QualityFailureAction.REGENERATE: 1,
        QualityFailureAction.HUMAN_REVIEW: 2,
        QualityFailureAction.FAIL: 3,
    }
    return order.get(action, 0)


def _repair_scope_order(scope: RepairScope) -> int:
    """Return numeric order for repair scope comparison (larger scope = higher)."""
    order = {
        RepairScope.NONE: 0,
        RepairScope.LAYER: 1,
        RepairScope.ASSET: 2,
        RepairScope.SHOT: 3,
        RepairScope.SCENE: 4,
        RepairScope.STAGE: 5,
        RepairScope.CUT: 6,
        RepairScope.SUBGRAPH: 7,
        RepairScope.WORKFLOW: 8,
    }
    return order.get(scope, 0)


def _create_gate_result(
    policy: QualityGatePolicy,
    manifest: QualityInputManifest,
    evaluation_ids: tuple[str, ...],
    decision: GateDecision,
    hard_failure_codes: tuple[FailureCode, ...],
    repair_scope: RepairScope | None,
    created_at: datetime,
    completed_at: datetime,
) -> QualityGateResult:
    """Create a QualityGateResult with common fields."""
    return QualityGateResult(
        schema_version="quality-gate-result.v1",
        quality_gate_result_id=f"qgr_{uuid.uuid4().hex[:12]}",
        gate_id=policy.gate_id,
        gate_version=policy.version,
        stage_instance_id=None,
        logical_item_key=None,
        target_artifact_ids=manifest.target_artifact_ids,
        target_hashes=manifest.target_hashes,
        required_check_ids=policy.required_check_ids,
        evaluation_ids=evaluation_ids,
        decision=decision,
        hard_failure_codes=list(hard_failure_codes),
        repair_scope=repair_scope,
        policy_version=policy.version,
        created_at=created_at,
        completed_at=completed_at,
    )


class QualityGate:
    """Orchestrates quality gate evaluation for a specific gate."""

    def __init__(
        self,
        policy: QualityGatePolicy,
        registry: QualityCheckRegistry,
    ) -> None:
        self.policy = policy
        self.registry = registry

    def evaluate(
        self,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
        supporting_artifacts: dict[str, Any],
    ) -> tuple[QualityGateResult, tuple[QualityEvaluation, ...]]:
        """Run all required checks and aggregate into a gate result.

        Args:
            manifest: Input manifest with target artifacts and hashes.
            artifacts: Loaded target artifacts.
            supporting_artifacts: Loaded supporting artifacts.

        Returns:
            Tuple of (gate_result, evaluations).
        """
        # Resolve checks in policy order
        checks = self.registry.resolve_checks_for_gate(
            tuple(self.policy.required_check_ids)
        )

        evaluations = []
        for check in checks:
            evaluator = self.registry.get_evaluator(check.check_id)
            evaluation = evaluator.evaluate(
                check, manifest, artifacts, supporting_artifacts
            )
            evaluations.append(evaluation)

        gate_result = evaluate_gate(
            self.policy, manifest, tuple(evaluations), self.registry
        )
        return gate_result, tuple(evaluations)
