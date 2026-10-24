"""Repair planning and invalidation logic."""

from __future__ import annotations

import uuid
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
            # Exceeded - would be handled by workflow layer
            # Return a plan that indicates max exceeded
            pass

        # Determine invalidation scope from repair_scope
        repair_scope = request.gate_result.repair_scope or RepairScope.SCENE
        invalidation_scope = _repair_scope_to_invalidation_scope(repair_scope)

        # Collect reason codes from failed evaluations
        # In a real implementation, this would come from the evaluations
        reason_codes = ["QUALITY.GENERIC"]  # Placeholder

        # Determine target artifacts and stages
        target_artifact_ids = list(request.gate_result.target_artifact_ids)
        target_stage_instance_ids = []
        if request.gate_result.stage_instance_id:
            target_stage_instance_ids.append(request.gate_result.stage_instance_id)

        # Cap max_attempts based on remaining regenerations
        remaining = request.max_regenerations - request.regeneration_count
        max_attempts = max(1, remaining)

        return RepairPlan(
            schema_version="repair-plan.v1",
            repair_plan_id=f"repair_{uuid.uuid4().hex[:12]}",
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
        workflow_dag: dict[str, list[str]],  # node_id -> list of dependent node_ids
    ) -> list[str]:
        """Compute all descendant stage instances that must be invalidated.

        Args:
            repair_plan: The repair plan with target stage instances.
            workflow_dag: Adjacency list of workflow dependencies.

        Returns:
            List of stage instance IDs to invalidate (including targets).
        """
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
) -> list[str]:
    """Apply invalidation to stage instances based on repair plan scope.

    Args:
        repair_plan: The repair plan specifying what to invalidate.
        stage_instances: Dictionary of all stage instances in the workflow.

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
        # This would use the workflow DAG in a real implementation
        for stage_id in repair_plan.target_stage_instance_ids:
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
