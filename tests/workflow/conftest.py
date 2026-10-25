from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from pipeline.contracts.artifacts import ArtifactPointer
from pipeline.contracts.execution import InputManifest, StageInstance, WorkflowRun
from pipeline.contracts.quality import QualityGateResult
from pipeline.contracts.review import HumanReview
from pipeline.contracts.vocabularies import (
    AcceptanceStatus,
    ArtifactPointerType,
    GateDecision,
    ReviewStatus,
    RunStatus,
    StageExecutionStatus,
)
from pipeline.contracts.workflow import WorkflowDefinition
from pipeline.workflow import ReadinessContext

BASE_TIME = datetime(2026, 1, 2, 9, 0, tzinfo=UTC)


def at(minutes: int = 0) -> datetime:
    return BASE_TIME + timedelta(minutes=minutes)


class WorkflowFactory:
    """Build deterministic workflow definitions and readiness records."""

    def node(
        self,
        node_id: str,
        *,
        depends_on: Sequence[str] = (),
        stage_name: str = "research",
        gate: str | None = None,
        mode: str = "one_to_one",
        count: int | None = None,
        selection_policy: str | None = None,
        expected_manifest_id: str | None = None,
        selector_kind: str = "DEPENDENCY_OUTPUTS",
        enabled_when: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cardinality: dict[str, Any] = {
            "schema_version": "cardinality.v1",
            "mode": mode,
        }
        if count is not None:
            cardinality["count"] = count
        if selection_policy is not None:
            cardinality["selection_policy"] = selection_policy
        if expected_manifest_id is not None:
            cardinality["expected_manifest_id"] = expected_manifest_id
        return {
            "schema_version": "stage-node.v1",
            "node_id": node_id,
            "stage_name": stage_name,
            "implementation_version": f"{node_id.replace('_', '-')}.v1",
            "depends_on": list(depends_on),
            "input_selector": {
                "schema_version": "input-selector.v1",
                "kind": selector_kind,
            },
            "cardinality": cardinality,
            "quality_gate_id": gate,
            "recovery_policy_id": None,
            "enabled_when": enabled_when,
        }

    def workflow(
        self,
        nodes: Sequence[dict[str, Any]],
        *,
        workflow_id: str = "test_workflow",
        version: str = "1.0",
    ) -> WorkflowDefinition:
        return WorkflowDefinition.model_validate(
            {
                "schema_version": "workflow-definition.v1",
                "workflow_id": workflow_id,
                "version": version,
                "policy_ids": [],
                "nodes": list(nodes),
            }
        )

    def root_workflow(
        self,
        *,
        gate: str | None = None,
        workflow_id: str = "test_workflow",
    ) -> WorkflowDefinition:
        return self.workflow(
            [self.node("root", stage_name="manual_topic", gate=gate)],
            workflow_id=workflow_id,
        )

    def chain(self, length: int = 2) -> WorkflowDefinition:
        nodes = []
        for index in range(length):
            node_id = "root" if index == 0 else f"node_{index}"
            depends_on = [] if index == 0 else [nodes[-1]["node_id"]]
            nodes.append(
                self.node(
                    node_id,
                    depends_on=depends_on,
                    stage_name="manual_topic" if index == 0 else "research",
                )
            )
        return self.workflow(nodes)

    def run(
        self,
        workflow: WorkflowDefinition,
        *,
        status: RunStatus = RunStatus.RUNNING,
        run_id: str = "run_01",
    ) -> WorkflowRun:
        return WorkflowRun(
            schema_version="workflow-run.v1",
            run_id=run_id,
            run_key=f"run-key:{run_id}",
            workflow_id=workflow.workflow_id,
            workflow_version=workflow.version,
            effective_config_id="cfg_01",
            effective_config_hash="a" * 64,
            status=status,
            content_package_id="package_01",
            created_at=at(0),
            updated_at=at(0),
        )

    def instance(
        self,
        run: WorkflowRun,
        node_id: str,
        *,
        key: str = "default",
        execution: StageExecutionStatus = StageExecutionStatus.SUCCEEDED,
        acceptance: AcceptanceStatus = AcceptanceStatus.PASSED,
        outputs: Sequence[str] = (),
        gate: str | None = None,
        manifest_id: str | None = None,
        instance_id: str | None = None,
        active_attempt_id: str | None = None,
    ) -> StageInstance:
        return StageInstance(
            schema_version="stage-instance.v1",
            stage_instance_id=instance_id or f"stage_{node_id}_{key}".replace(":", "_"),
            run_id=run.run_id,
            node_id=node_id,
            logical_item_key=key,
            execution_status=execution,
            acceptance_status=acceptance,
            quality_gate_id=gate,
            quality_gate_result_id=None,
            expected_input_manifest_id=manifest_id,
            active_attempt_id=active_attempt_id,
            accepted_output_artifact_ids=list(outputs),
            created_at=at(1),
            updated_at=at(2),
        )

    def accepted(
        self,
        run: WorkflowRun,
        node_id: str,
        *,
        key: str = "default",
        output: str | None = None,
        gate: str | None = None,
        instance_id: str | None = None,
    ) -> StageInstance:
        output = output or f"artifact_{node_id}_{key}".replace(":", "_")
        acceptance = (
            AcceptanceStatus.PASSED
            if gate is not None
            else AcceptanceStatus.NOT_REQUIRED
        )
        return self.instance(
            run,
            node_id,
            key=key,
            acceptance=acceptance,
            outputs=(output,),
            gate=gate,
            instance_id=instance_id,
        )

    def manifest(
        self,
        stage_instance_id: str,
        *,
        slots: Sequence[str] = (),
        resolved: Sequence[str] = (),
        expected_count: int | None = None,
        complete: bool = True,
        manifest_id: str = "manifest_01",
    ) -> InputManifest:
        if expected_count is None:
            expected_count = len(slots) if slots else len(resolved)
        return InputManifest(
            schema_version="input-manifest.v1",
            manifest_id=manifest_id,
            stage_instance_id=stage_instance_id,
            expected_artifact_slots=list(slots),
            resolved_artifact_ids=list(resolved),
            expected_count=expected_count,
            complete=complete,
            created_at=at(3),
        )

    def gate_result(
        self,
        stage: StageInstance,
        gate_id: str,
        *,
        decision: GateDecision = GateDecision.PASS,
        targets: Sequence[str] | None = None,
        result_id: str | None = None,
        created_at: datetime | None = None,
    ) -> QualityGateResult:
        target_ids = (
            list(targets)
            if targets is not None
            else list(stage.accepted_output_artifact_ids)
        )
        if not target_ids:
            target_ids = [f"artifact_gate_{stage.stage_instance_id}"]
        return QualityGateResult(
            schema_version="quality-gate-result.v1",
            quality_gate_result_id=result_id or f"gate_{stage.stage_instance_id}",
            gate_id=gate_id,
            gate_version="1.0",
            stage_instance_id=stage.stage_instance_id,
            logical_item_key=stage.logical_item_key,
            target_artifact_ids=target_ids,
            target_hashes={artifact_id: "b" * 64 for artifact_id in target_ids},
            required_check_ids=["check_fixture_v1"],
            evaluation_ids=["evaluation_fixture_v1"],
            decision=decision,
            hard_failure_codes=[],
            repair_scope=None,
            policy_version="1.0",
            created_at=created_at or at(4),
            completed_at=created_at or at(4),
        )

    def review(
        self,
        run: WorkflowRun,
        *,
        status: ReviewStatus = ReviewStatus.OPEN,
        targets: Sequence[str] = ("artifact_review",),
        review_id: str = "review_01",
    ) -> HumanReview:
        return HumanReview(
            schema_version="human-review.v1",
            review_id=review_id,
            run_id=run.run_id,
            stage_instance_id=None,
            gate_id=None,
            target_artifact_ids=list(targets),
            target_hashes={},
            reason_codes=[],
            requested_action="approve",
            status=status,
            created_at=at(5),
            resolved_at=at(6)
            if status
            in (
                ReviewStatus.RESOLVED,
                ReviewStatus.EXPIRED,
                ReviewStatus.CANCELLED,
            )
            else None,
        )

    def pointer(
        self,
        run: WorkflowRun,
        artifact_id: str,
        *,
        pointer_type: ArtifactPointerType = ArtifactPointerType.ACCEPTED,
        active: bool = True,
        pointer_id: str = "pointer_01",
    ) -> ArtifactPointer:
        return ArtifactPointer(
            schema_version="artifact-pointer.v1",
            pointer_id=pointer_id,
            run_id=run.run_id,
            logical_slot=artifact_id,
            artifact_id=artifact_id,
            pointer_type=pointer_type,
            active=active,
            updated_at=at(5),
        )

    def context(
        self,
        workflow: WorkflowDefinition,
        run: WorkflowRun,
        **kwargs: Any,
    ) -> ReadinessContext:
        return ReadinessContext(run=run, workflow=workflow, **kwargs)


@pytest.fixture
def wf() -> WorkflowFactory:
    return WorkflowFactory()


@pytest.fixture
def canonical_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "workflows"
        / "explainer_validation_v1.yaml"
    )
