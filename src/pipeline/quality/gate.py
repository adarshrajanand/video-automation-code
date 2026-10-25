"""Quality gate evaluation and aggregation logic."""

from __future__ import annotations

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
from pipeline.ids import deterministic_id

if TYPE_CHECKING:
    from pipeline.quality.registry import QualityCheckRegistry


@dataclass(slots=True)
class CheckEvaluationResult:
    """Result of evaluating a single check within a gate."""

    check: QualityCheck
    evaluation: QualityEvaluation
    is_hard_failure: bool


def _compute_pass_threshold(
    evaluation: QualityEvaluation,
    check: QualityCheck,
    policy: QualityGatePolicy,
) -> tuple[bool, list[FailureCode]]:
    """Check if evaluation dimensions meet policy pass thresholds.

    Returns:
        Tuple of (all_pass, failure_codes_for_below_threshold)
    """
    failure_codes = []
    for dimension in evaluation.dimensions:
        threshold = policy.pass_thresholds.get(dimension.name)
        if threshold is None:
            continue
        if dimension.score is None:
            # Missing score for a required threshold dimension
            failure_codes.extend(dimension.failure_codes)
            if not failure_codes:
                failure_codes.append(FailureCode.QUALITY_GENERIC)
            continue
        if dimension.score < threshold:
            # Dimension score below pass threshold
            failure_codes.extend(dimension.failure_codes)
            if not failure_codes:
                failure_codes.append(FailureCode.QUALITY_GENERIC)
    # Check for required dimensions that are missing from evaluation
    for dim_name in policy.pass_thresholds:
        if not any(d.name == dim_name for d in evaluation.dimensions):
            failure_codes.append(FailureCode.QUALITY_GENERIC)
    return len(failure_codes) == 0, failure_codes


def _verify_artifact_hashes(
    manifest: QualityInputManifest,
    artifacts: dict[str, Any],
) -> tuple[bool, list[FailureCode]]:
    """Verify artifact hashes match manifest.

    Returns:
        Tuple of (all_match, failure_codes)
    """
    import json

    from pipeline.fingerprints import sha256_text

    failure_codes = []
    for artifact_id, expected_hash in manifest.target_hashes.items():
        artifact = artifacts.get(artifact_id)
        if artifact is None:
            failure_codes.append(FailureCode.QUALITY_SCHEMA_INVALID)
            continue
        # Compute hash of artifact content
        if isinstance(artifact, dict) and "sha256" in artifact:
            actual_hash = artifact["sha256"]
        else:
            # Fallback: compute hash from artifact content using canonical JSON
            import json

            from pipeline.fingerprints import sha256_text

            actual_hash = sha256_text(json.dumps(artifact, sort_keys=True, default=str))
        if actual_hash != expected_hash:
            failure_codes.append(FailureCode.QUALITY_PROVENANCE_MISSING)
    return len(failure_codes) == 0, failure_codes


def evaluate_gate(
    policy: QualityGatePolicy,
    manifest: QualityInputManifest,
    evaluations: tuple[QualityEvaluation, ...],
    registry: QualityCheckRegistry,
    artifacts: dict[str, Any] | None = None,
    stage_instance_id: str | None = None,
    logical_item_key: str | None = None,
    regeneration_count: int = 0,
) -> QualityGateResult:
    """Aggregate check evaluations into a gate decision.

    The aggregation follows these rules:
    1. Any evaluation with outcome ERROR → gate decision FAIL
    2. Required check FAIL with severity CRITICAL → gate decision FAIL
    3. Check with failure_code in hard_failure_codes → gate decision FAIL
    4. Artifact hash mismatch → gate decision FAIL
    5. Dimension score below policy pass_threshold → gate decision FAIL
    6. All required checks PASS → gate decision PASS
    7. Required check FAIL (non-critical), max_regenerations not exceeded → REGENERATE
    8. Max regenerations exceeded → apply after_max_regenerations
    9. Semantic check below human_review_threshold → HUMAN_REVIEW
    10. Check outcome ABSTAIN → HUMAN_REVIEW

    Args:
        policy: The quality gate policy defining required checks and thresholds.
        manifest: The input manifest for this gate evaluation.
        evaluations: Tuple of completed evaluations for each required check.
        registry: The quality check registry for check metadata lookup.
        artifacts: Optional loaded artifacts for hash verification.
        stage_instance_id: Optional stage instance ID for linking.
        logical_item_key: Optional logical item key for linking.
        regeneration_count: Current regeneration attempt number.

    Returns:
        A QualityGateResult with the aggregate decision and repair scope.
    """
    created_at = datetime.now(UTC)
    evaluation_ids = tuple(e.evaluation_id for e in evaluations)
    required_check_ids = policy.required_check_ids
    hard_failure_codes: list[FailureCode] = []

    # Validate that all evaluations belong to this manifest and gate
    for evaluation in evaluations:
        if evaluation.evaluation_input_manifest_id != manifest.manifest_id:
            return _create_gate_result(
                policy=policy,
                manifest=manifest,
                evaluation_ids=evaluation_ids,
                decision=GateDecision.FAIL,
                hard_failure_codes=[FailureCode.QUALITY_GENERIC],
                repair_scope=None,
                created_at=created_at,
                completed_at=datetime.now(UTC),
                stage_instance_id=stage_instance_id,
                logical_item_key=logical_item_key,
            )
        if evaluation.gate_id != manifest.gate_id:
            return _create_gate_result(
                policy=policy,
                manifest=manifest,
                evaluation_ids=evaluation_ids,
                decision=GateDecision.FAIL,
                hard_failure_codes=[FailureCode.QUALITY_GENERIC],
                repair_scope=None,
                created_at=created_at,
                completed_at=datetime.now(UTC),
                stage_instance_id=stage_instance_id,
                logical_item_key=logical_item_key,
            )
        if evaluation.target_artifact_ids != manifest.target_artifact_ids:
            return _create_gate_result(
                policy=policy,
                manifest=manifest,
                evaluation_ids=evaluation_ids,
                decision=GateDecision.FAIL,
                hard_failure_codes=[FailureCode.QUALITY_GENERIC],
                repair_scope=None,
                created_at=created_at,
                completed_at=datetime.now(UTC),
                stage_instance_id=stage_instance_id,
                logical_item_key=logical_item_key,
            )
        if evaluation.target_hashes != manifest.target_hashes:
            return _create_gate_result(
                policy=policy,
                manifest=manifest,
                evaluation_ids=evaluation_ids,
                decision=GateDecision.FAIL,
                hard_failure_codes=[FailureCode.QUALITY_GENERIC],
                repair_scope=None,
                created_at=created_at,
                completed_at=datetime.now(UTC),
                stage_instance_id=stage_instance_id,
                logical_item_key=logical_item_key,
            )

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
                stage_instance_id=stage_instance_id,
                logical_item_key=logical_item_key,
            )

    # Rule 4: Artifact hash verification (if artifacts provided)
    if artifacts is not None:
        hashes_match, hash_failure_codes = _verify_artifact_hashes(manifest, artifacts)
        if not hashes_match:
            hard_failure_codes.extend(hash_failure_codes)

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

        # Rule 5: Check pass thresholds
        thresholds_pass, threshold_failures = _compute_pass_threshold(
            evaluation, check, policy
        )
        if not thresholds_pass:
            hard_failure_codes.extend(threshold_failures)

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
            stage_instance_id=stage_instance_id,
            logical_item_key=logical_item_key,
        )

    # Check human review zone for ANY required check (not just when all pass)
    # Review zone: human_review_threshold <= score < pass_threshold
    needs_human_review = False
    for evaluation in evaluations:
        check = _get_check(registry, evaluation.check_id)
        if check is None or not check.required:
            continue
        for dimension in evaluation.dimensions:
            hr_threshold = policy.human_review_thresholds.get(dimension.name)
            pass_threshold = policy.pass_thresholds.get(dimension.name)
            if (
                hr_threshold is not None
                and pass_threshold is not None
                and dimension.score is not None
                and hr_threshold <= dimension.score < pass_threshold
            ):
                needs_human_review = True
                break
        if needs_human_review:
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
            stage_instance_id=stage_instance_id,
            logical_item_key=logical_item_key,
        )

    # Rule 6: All required checks PASS
    all_required_pass = all(
        _evaluation_for_check(evaluations, check_id) is not None
        and _evaluation_for_check(evaluations, check_id).outcome is CheckOutcome.PASS
        for check_id in required_check_ids
    )

    if all_required_pass:
        return _create_gate_result(
            policy=policy,
            manifest=manifest,
            evaluation_ids=evaluation_ids,
            decision=GateDecision.PASS,
            hard_failure_codes=(),
            repair_scope=None,
            created_at=created_at,
            completed_at=datetime.now(UTC),
            stage_instance_id=stage_instance_id,
            logical_item_key=logical_item_key,
        )

    # Rule 7 & 8: Some required checks FAIL - check regeneration policy
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
            stage_instance_id=stage_instance_id,
            logical_item_key=logical_item_key,
        )

    # Check max regenerations
    if regeneration_count >= policy.max_regenerations:
        # Max regenerations exceeded - apply after_max_regenerations
        after_action = policy.after_max_regenerations
        if after_action == QualityFailureAction.HUMAN_REVIEW:
            decision = GateDecision.HUMAN_REVIEW
            repair_scope = None
        elif after_action == QualityFailureAction.FAIL:
            decision = GateDecision.FAIL
            repair_scope = None
        else:  # REGENERATE (shouldn't happen if max_regenerations > 0)
            decision = GateDecision.REGENERATE
    else:
        # Within regeneration limits
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
        stage_instance_id=stage_instance_id,
        logical_item_key=logical_item_key,
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
    stage_instance_id: str | None = None,
    logical_item_key: str | None = None,
) -> QualityGateResult:
    """Create a QualityGateResult with common fields."""
    # Deterministic gate result ID from manifest + gate + version + decision + eval IDs
    eval_id_str = ",".join(sorted(evaluation_ids))
    gate_result_id = deterministic_id(
        "qgr", policy.gate_id, policy.version, decision.value, eval_id_str
    )
    return QualityGateResult(
        schema_version="quality-gate-result.v1",
        quality_gate_result_id=f"qgr_{gate_result_id}",
        gate_id=policy.gate_id,
        gate_version=policy.version,
        stage_instance_id=stage_instance_id,
        logical_item_key=logical_item_key,
        target_artifact_ids=manifest.target_artifact_ids,
        target_hashes=manifest.target_hashes,
        required_check_ids=policy.required_check_ids,
        evaluation_ids=list(evaluation_ids),
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
        stage_instance_id: str | None = None,
        logical_item_key: str | None = None,
        regeneration_count: int = 0,
    ) -> tuple[QualityGateResult, tuple[QualityEvaluation, ...]]:
        """Run all required checks and aggregate into a gate result.

        Args:
            manifest: Input manifest with target artifacts and hashes.
            artifacts: Loaded target artifacts.
            supporting_artifacts: Loaded supporting artifacts.
            stage_instance_id: Optional stage instance ID for linking.
            logical_item_key: Optional logical item key for linking.
            regeneration_count: Current regeneration attempt number.

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
            self.policy,
            manifest,
            tuple(evaluations),
            self.registry,
            artifacts=artifacts,
            stage_instance_id=stage_instance_id,
            logical_item_key=logical_item_key,
            regeneration_count=regeneration_count,
        )
        return gate_result, tuple(evaluations)
