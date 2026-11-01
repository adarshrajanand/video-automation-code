"""Repair planning and invalidation logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pipeline.contracts.quality import (
    QualityGateResult,
    RepairPlan,
    RepairScope,
)
from pipeline.contracts.vocabularies import (
    GateDecision,
    RepairInvalidationScope,
)
from pipeline.ids import deterministic_id

if TYPE_CHECKING:
    from pipeline.quality.registry import QualityCheckRegistry


@dataclass(slots=True)
class RepairPlanRequest:
    """Request to create a repair plan from a gate result."""

    gate_result: QualityGateResult
    regeneration_count: int
    max_regenerations: int
    after_max_regenerations: str  # RepeatedFailureAction value


def create_repair_plan(request: RepairPlanRequest) -> RepairPlan | None:
    """Create a repair plan from a failed gate result.

    Args:
        request: The repair plan request with gate result and policy context.

    Returns:
        A RepairPlan if the gate decision allows repair, None otherwise.
    """
    decision = request.gate_result.decision

    if decision is GateDecision.PASS:
        return None

    if decision is GateDecision.FAIL:
        # Hard failure - no repair, workflow fails
        return None

    if decision is GateDecision.HUMAN_REVIEW:
        # Human review required - no automatic repair
        return None

    if decision is GateDecision.REGENERATE:
        # Check if we've exceeded max regenerations
        if request.regeneration_count >= request.max_regenerations:
            # Exceeded max regenerations - no repair plan, workflow handles escalation
            return None

        # Determine invalidation scope from repair_scope
        repair_scope = request.gate_result.repair_scope or RepairScope.SCENE
        invalidation_scope = _repair_scope_to_invalidation_scope(repair_scope)

        # Collect reason codes from failed evaluations' failure codes
        # In a real implementation, this would come from the evaluations
        # For now, use the hard_failure_codes from gate result if available,
        # or derive from the repair scope
        reason_codes = list(request.gate_result.hard_failure_codes)
        if not reason_codes:
            reason_codes = ["QUALITY.REGENERATE"]

        # Determine target artifacts and stages
        target_artifact_ids = list(request.gate_result.target_artifact_ids)
        target_stage_instance_ids = []
        if request.gate_result.stage_instance_id:
            target_stage_instance_ids.append(request.gate_result.stage_instance_id)

        # Cap max_attempts based on remaining regenerations
        remaining = request.max_regenerations - request.regeneration_count
        max_attempts = max(1, remaining)

        # Deterministic repair plan ID from source gate result + regeneration count
        rid = deterministic_id(
            "repair",
            request.gate_result.quality_gate_result_id,
            str(request.regeneration_count),
        )
        return RepairPlan(
            schema_version="repair-plan.v1",
            repair_plan_id=f"repair_{rid}",
            source_gate_result_id=request.gate_result.quality_gate_result_id,
            reason_codes=reason_codes,
            target_artifact_ids=target_artifact_ids,
            target_stage_instance_ids=target_stage_instance_ids,
            invalidation_scope=invalidation_scope,
            max_attempts=max_attempts,
            created_at=datetime.now(UTC),
        )

    return None


def _repair_scope_to_invalidation_scope(
    repair_scope: RepairScope,
) -> RepairInvalidationScope:
    """Map RepairScope to RepairInvalidationScope."""
    mapping = {
        RepairScope.NONE: RepairInvalidationScope.ARTIFACT,
        RepairScope.LAYER: RepairInvalidationScope.ARTIFACT,
        RepairScope.ASSET: RepairInvalidationScope.ARTIFACT,
        RepairScope.SHOT: RepairInvalidationScope.ARTIFACT,
        RepairScope.SCENE: RepairInvalidationScope.SCENE,
        RepairScope.STAGE: RepairInvalidationScope.SUBGRAPH,
        RepairScope.CUT: RepairInvalidationScope.SUBGRAPH,
        RepairScope.SUBGRAPH: RepairInvalidationScope.SUBGRAPH,
        RepairScope.WORKFLOW: RepairInvalidationScope.WORKFLOW,
    }
    return mapping.get(repair_scope, RepairInvalidationScope.SCENE)


class RepairPlanner:
    """Plans targeted repairs based on gate results and policy."""

    def __init__(self, registry: QualityCheckRegistry) -> None:
        self.registry = registry

    def plan_repair(
        self,
        gate_result: QualityGateResult,
        regeneration_count: int,
        max_regenerations: int,
        after_max_regenerations: str,
    ) -> RepairPlan | None:
        """Create a repair plan for a failed gate."""
        request = RepairPlanRequest(
            gate_result=gate_result,
            regeneration_count=regeneration_count,
            max_regenerations=max_regenerations,
            after_max_regenerations=after_max_regenerations,
        )
        return create_repair_plan(request)

    def compute_descendant_invalidation(
        self,
        repair_plan: RepairPlan,
        workflow_dag: dict[str, list[str]],
    ) -> list[str]:
        """Stage instance ID -> list of dependent stage_instance_ids."""
        """Compute all descendant stage instances that must be invalidated.

        Args:
            repair_plan: The repair plan with target stage instances.
            workflow_dag: Adjacency list of workflow dependencies.

        Returns:
            List of stage instance IDs to invalidate (including targets).
        """
        if repair_plan.invalidation_scope != RepairInvalidationScope.SUBGRAPH:
            return list(repair_plan.target_stage_instance_ids)

        if not workflow_dag:
            raise ValueError("workflow_dag required for SUBGRAPH invalidation")

        invalidated = set(repair_plan.target_stage_instance_ids)

        # BFS from each target to find all dependents
        queue = list(repair_plan.target_stage_instance_ids)
        while queue:
            current = queue.pop(0)
            dependents = workflow_dag.get(current, [])
            for dep in dependents:
                if dep not in invalidated:
                    invalidated.add(dep)
                    queue.append(dep)

        return list(invalidated)


def apply_repair_invalidation(
    repair_plan: RepairPlan,
    stage_instances: dict[str, dict],  # stage_instance_id -> stage instance data
    workflow_dag: dict[str, list[str]] | None = None,
) -> list[str]:
    """Apply invalidation to stage instances based on repair plan scope.

    Args:
        repair_plan: The repair plan specifying what to invalidate.
        stage_instances: Dictionary of all stage instances in the workflow.
        workflow_dag: Required for SUBGRAPH scope.
            Adjacency list of workflow dependencies.

    Returns:
        List of stage instance IDs that were invalidated.
    """
    invalidated = []

    if repair_plan.invalidation_scope is RepairInvalidationScope.ARTIFACT:
        # Only invalidate the specific artifact versions
        # Stage instances remain, but their output artifacts are marked superseded
        for stage_id in repair_plan.target_stage_instance_ids:
            if stage_id in stage_instances:
                stage_instances[stage_id]["acceptance_status"] = "REGENERATE"
                invalidated.append(stage_id)

    elif repair_plan.invalidation_scope is RepairInvalidationScope.SCENE:
        # Invalidate all stage instances for the affected scenes
        for stage_id in repair_plan.target_stage_instance_ids:
            if stage_id in stage_instances:
                stage_instances[stage_id]["acceptance_status"] = "REGENERATE"
                stage_instances[stage_id]["execution_status"] = "INVALIDATED"
                invalidated.append(stage_id)

    elif repair_plan.invalidation_scope is RepairInvalidationScope.SUBGRAPH:
        # Invalidate target stages and all downstream dependents
        if workflow_dag is None:
            raise ValueError("workflow_dag required for SUBGRAPH invalidation")
        # Use the repair planner's logic
        # For now, inline the BFS
        invalidated_set = set(repair_plan.target_stage_instance_ids)
        queue = list(repair_plan.target_stage_instance_ids)
        while queue:
            current = queue.pop(0)
            dependents = workflow_dag.get(current, [])
            for dep in dependents:
                if dep not in invalidated_set:
                    invalidated_set.add(dep)
                    queue.append(dep)
        for stage_id in invalidated_set:
            if stage_id in stage_instances:
                stage_instances[stage_id]["acceptance_status"] = "REGENERATE"
                stage_instances[stage_id]["execution_status"] = "INVALIDATED"
                invalidated.append(stage_id)

    elif repair_plan.invalidation_scope is RepairInvalidationScope.WORKFLOW:
        # Invalidate entire workflow
        for stage_id in stage_instances:
            stage_instances[stage_id]["acceptance_status"] = "REGENERATE"
            stage_instances[stage_id]["execution_status"] = "INVALIDATED"
            invalidated.append(stage_id)

    return invalidated
