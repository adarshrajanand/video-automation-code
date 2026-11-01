from __future__ import annotations

from pathlib import Path

from pipeline.contracts.vocabularies import (
    AcceptanceStatus,
    ArtifactState,
    CardinalityMode,
    GateDecision,
    RunStatus,
    StageExecutionStatus,
)
from pipeline.contracts.workflow import StageNode
from pipeline.workflow import (
    ReadinessReason,
    evaluate_readiness,
    load_workflow,
    plan_cardinality,
)


def reasons(result) -> set[ReadinessReason]:
    return {block.code for block in result.blocked}


def test_canonical_root_is_ready_from_empty_context(wf, canonical_path: Path) -> None:
    workflow = load_workflow(canonical_path)
    run = wf.run(workflow)

    result = evaluate_readiness(wf.context(workflow, run))

    assert result.ready_node_ids == ("intake",)
    assert result.ready_instance_ids == ()
    assert [item.node_id for item in result.planned_items] == ["intake"]
    assert [item.logical_item_key for item in result.planned_items] == ["default"]
    assert result.next_status is RunStatus.RUNNING
    assert result.accepted_node_ids == ()
    assert result.terminal_node_ids == ("human_approval",)


def test_linear_dependencies_plan_one_node_at_a_time(wf) -> None:
    workflow = wf.chain(3)
    run = wf.run(workflow)
    root = wf.accepted(run, "root")

    first = evaluate_readiness(wf.context(workflow, run, stage_instances=(root,)))

    assert first.ready_node_ids == ("node_1",)
    assert [item.node_id for item in first.planned_items] == ["node_1"]
    assert ReadinessReason.DEPENDENCY_NOT_ACCEPTED in reasons(first)

    node_one = wf.accepted(run, "node_1")
    second = evaluate_readiness(
        wf.context(workflow, run, stage_instances=(root, node_one))
    )

    assert second.ready_node_ids == ("node_2",)
    assert [item.node_id for item in second.planned_items] == ["node_2"]
    assert set(second.accepted_node_ids) == {"root", "node_1"}


def test_execution_success_without_gate_acceptance_does_not_unblock(wf) -> None:
    workflow = wf.workflow(
        [
            wf.node("root", stage_name="manual_topic"),
            wf.node("gated", depends_on=["root"], gate="research_gate_v1"),
            wf.node("downstream", depends_on=["gated"]),
        ]
    )
    run = wf.run(workflow)
    root = wf.accepted(run, "root")
    gated = wf.instance(
        run,
        "gated",
        execution=StageExecutionStatus.SUCCEEDED,
        acceptance=AcceptanceStatus.PENDING,
        gate="research_gate_v1",
        outputs=("artifact_gated",),
    )

    result = evaluate_readiness(
        wf.context(workflow, run, stage_instances=(root, gated))
    )

    assert "gated" not in result.accepted_node_ids
    assert "downstream" not in result.ready_node_ids
    assert result.planned_items == ()
    assert ReadinessReason.GATE_PENDING in reasons(result)


def test_passed_acceptance_requires_a_passing_gate_result(wf) -> None:
    workflow = wf.workflow(
        [
            wf.node("root", stage_name="manual_topic"),
            wf.node("gated", depends_on=["root"], gate="research_gate_v1"),
            wf.node("downstream", depends_on=["gated"]),
        ]
    )
    run = wf.run(workflow)
    root = wf.accepted(run, "root")
    gated = wf.instance(
        run,
        "gated",
        acceptance=AcceptanceStatus.PASSED,
        gate="research_gate_v1",
        outputs=("artifact_gated",),
    )

    without_result = evaluate_readiness(
        wf.context(workflow, run, stage_instances=(root, gated))
    )
    assert ReadinessReason.GATE_RESULT_MISSING in reasons(without_result)
    assert "downstream" not in without_result.ready_node_ids

    gate_pass = wf.gate_result(gated, "research_gate_v1")
    with_result = evaluate_readiness(
        wf.context(
            workflow,
            run,
            stage_instances=(root, gated),
            quality_gate_results=(gate_pass,),
        )
    )
    assert "gated" in with_result.accepted_node_ids
    assert with_result.ready_node_ids == ("downstream",)
    assert [item.node_id for item in with_result.planned_items] == ["downstream"]


def test_gate_result_for_invalidated_target_does_not_accept(wf) -> None:
    workflow = wf.workflow(
        [
            wf.node("root", stage_name="manual_topic"),
            wf.node("gated", depends_on=["root"], gate="research_gate_v1"),
            wf.node("downstream", depends_on=["gated"]),
        ]
    )
    run = wf.run(workflow)
    root = wf.accepted(run, "root")
    gated = wf.instance(
        run,
        "gated",
        acceptance=AcceptanceStatus.PASSED,
        gate="research_gate_v1",
        outputs=("artifact_gated",),
    )
    gate_pass = wf.gate_result(gated, "research_gate_v1")

    result = evaluate_readiness(
        wf.context(
            workflow,
            run,
            stage_instances=(root, gated),
            quality_gate_results=(gate_pass,),
            artifact_states={"artifact_gated": ArtifactState.INVALIDATED},
        )
    )

    assert "gated" not in result.accepted_node_ids
    assert ReadinessReason.INPUT_ARTIFACT_NOT_ACCEPTED in reasons(result)
    assert "downstream" not in result.ready_node_ids


def test_regenerate_gate_decision_does_not_accept(wf) -> None:
    workflow = wf.workflow(
        [
            wf.node("root", stage_name="manual_topic"),
            wf.node("gated", depends_on=["root"], gate="research_gate_v1"),
            wf.node("downstream", depends_on=["gated"]),
        ]
    )
    run = wf.run(workflow)
    root = wf.accepted(run, "root")
    gated = wf.instance(
        run,
        "gated",
        acceptance=AcceptanceStatus.PASSED,
        gate="research_gate_v1",
        outputs=("artifact_gated",),
    )
    gate_regenerate = wf.gate_result(
        gated, "research_gate_v1", decision=GateDecision.REGENERATE
    )

    result = evaluate_readiness(
        wf.context(
            workflow,
            run,
            stage_instances=(root, gated),
            quality_gate_results=(gate_regenerate,),
        )
    )

    assert "gated" not in result.accepted_node_ids
    assert ReadinessReason.GATE_REGENERATE in reasons(result)
    assert "downstream" not in result.ready_node_ids


def test_ungated_success_without_accepted_output_does_not_unblock(wf) -> None:
    workflow = wf.chain(2)
    run = wf.run(workflow)
    root = wf.instance(
        run,
        "root",
        execution=StageExecutionStatus.SUCCEEDED,
        acceptance=AcceptanceStatus.NOT_REQUIRED,
        outputs=(),
    )

    result = evaluate_readiness(wf.context(workflow, run, stage_instances=(root,)))

    assert "root" not in result.accepted_node_ids
    assert ReadinessReason.NO_ACCEPTED_OUTPUT in reasons(result)
    assert "node_1" not in result.ready_node_ids


def test_one_to_many_count_plans_and_requires_every_child(wf) -> None:
    workflow = wf.workflow(
        [
            wf.node("root", stage_name="manual_topic"),
            wf.node(
                "fanout",
                depends_on=["root"],
                mode="one_to_many",
                count=3,
            ),
            wf.node("downstream", depends_on=["fanout"]),
        ]
    )
    run = wf.run(workflow)
    root = wf.accepted(run, "root")

    initial = evaluate_readiness(wf.context(workflow, run, stage_instances=(root,)))
    assert initial.ready_node_ids == ("fanout",)
    assert [item.logical_item_key for item in initial.planned_items] == [
        "fanout:01",
        "fanout:02",
        "fanout:03",
    ]
    assert "downstream" not in initial.ready_node_ids

    first = wf.accepted(run, "fanout", key="fanout:01")
    second = wf.accepted(run, "fanout", key="fanout:02")
    partial = evaluate_readiness(
        wf.context(workflow, run, stage_instances=(root, first, second))
    )
    assert [item.logical_item_key for item in partial.planned_items] == ["fanout:03"]
    assert "fanout" not in partial.accepted_node_ids
    assert "downstream" not in partial.ready_node_ids

    third = wf.accepted(run, "fanout", key="fanout:03")
    complete = evaluate_readiness(
        wf.context(workflow, run, stage_instances=(root, first, second, third))
    )
    assert "fanout" in complete.accepted_node_ids
    assert complete.ready_node_ids == ("downstream",)


def test_one_to_many_manifest_children_requires_complete_manifest(wf) -> None:
    workflow = wf.workflow(
        [
            wf.node("root", stage_name="manual_topic"),
            wf.node(
                "fanout",
                depends_on=["root"],
                mode="one_to_many",
                selection_policy="manifest_children",
            ),
            wf.node("downstream", depends_on=["fanout"]),
        ]
    )
    run = wf.run(workflow)
    root = wf.accepted(run, "root")

    missing = evaluate_readiness(wf.context(workflow, run, stage_instances=(root,)))
    assert ReadinessReason.MISSING_EXPECTED_MANIFEST in reasons(missing)
    assert missing.planned_items == ()

    incomplete = wf.manifest(
        "stage_fanout_planned",
        slots=("scene_01", "scene_02"),
        resolved=("artifact_input_01",),
        expected_count=2,
        complete=False,
    )
    incomplete_result = evaluate_readiness(
        wf.context(
            workflow,
            run,
            stage_instances=(root,),
            input_manifests=(incomplete,),
        )
    )
    assert ReadinessReason.INCOMPLETE_MANIFEST in reasons(incomplete_result)

    missing_keys = wf.manifest(
        "stage_fanout_planned",
        slots=(),
        resolved=("artifact_input_01", "artifact_input_02"),
        expected_count=2,
    )
    missing_keys_result = evaluate_readiness(
        wf.context(
            workflow,
            run,
            stage_instances=(root,),
            input_manifests=(missing_keys,),
        )
    )
    assert ReadinessReason.MISSING_MANIFEST_KEYS in reasons(missing_keys_result)

    complete = wf.manifest(
        "stage_fanout_planned",
        slots=("scene_01", "scene_02"),
        resolved=("artifact_input_01", "artifact_input_02"),
        expected_count=2,
    )
    complete_result = evaluate_readiness(
        wf.context(
            workflow,
            run,
            stage_instances=(root,),
            input_manifests=(complete,),
        )
    )
    assert [item.logical_item_key for item in complete_result.planned_items] == [
        "scene_01",
        "scene_02",
    ]
    assert complete_result.ready_node_ids == ("fanout",)


def test_manifest_children_uses_declared_manifest_id_when_ambiguous(wf) -> None:
    workflow = wf.workflow(
        [
            wf.node("root", stage_name="manual_topic"),
            wf.node(
                "fanout",
                depends_on=["root"],
                mode="one_to_many",
                selection_policy="render_chunk_manifest",
                expected_manifest_id="manifest_b",
            ),
        ]
    )
    run = wf.run(workflow)
    root = wf.accepted(run, "root")
    manifest_a = wf.manifest(
        "stage_fanout_planned",
        slots=("chunk_a",),
        resolved=("artifact_a",),
        manifest_id="manifest_a",
    )
    manifest_b = wf.manifest(
        "stage_fanout_planned",
        slots=("chunk_b", "chunk_c"),
        resolved=("artifact_b", "artifact_c"),
        manifest_id="manifest_b",
    )

    result = evaluate_readiness(
        wf.context(
            workflow,
            run,
            stage_instances=(root,),
            input_manifests=(manifest_a, manifest_b),
        )
    )

    assert [item.logical_item_key for item in result.planned_items] == [
        "chunk_b",
        "chunk_c",
    ]


def test_manifest_children_refuses_to_guess_between_manifests(wf) -> None:
    workflow = wf.workflow(
        [
            wf.node("root", stage_name="manual_topic"),
            wf.node(
                "fanout",
                depends_on=["root"],
                mode="one_to_many",
                selection_policy="manifest_children",
            ),
        ]
    )
    run = wf.run(workflow)
    root = wf.accepted(run, "root")
    manifest_a = wf.manifest(
        "stage_fanout_planned",
        slots=("a",),
        resolved=("artifact_a",),
        manifest_id="manifest_a",
    )
    manifest_b = wf.manifest(
        "stage_fanout_planned",
        slots=("b",),
        resolved=("artifact_b",),
        manifest_id="manifest_b",
    )

    result = evaluate_readiness(
        wf.context(
            workflow,
            run,
            stage_instances=(root,),
            input_manifests=(manifest_a, manifest_b),
        )
    )

    assert ReadinessReason.AMBIGUOUS_MANIFEST in reasons(result)
    assert result.planned_items == ()


def _fan_in_workflow(wf):
    workflow = wf.workflow(
        [
            wf.node("root", stage_name="manual_topic"),
            wf.node(
                "fanout",
                depends_on=["root"],
                mode="one_to_many",
                count=2,
            ),
            wf.node("fanin", depends_on=["fanout"], mode="many_to_one"),
            wf.node("downstream", depends_on=["fanin"]),
        ]
    )
    run = wf.run(workflow)
    root = wf.accepted(run, "root")
    first = wf.accepted(run, "fanout", key="fanout:01")
    second = wf.accepted(run, "fanout", key="fanout:02")
    return workflow, run, root, first, second


def test_manifest_selector_uses_declared_expected_manifest_id(wf) -> None:
    workflow = wf.workflow(
        [
            wf.node(
                "root",
                stage_name="manual_topic",
                expected_manifest_id="manifest_inputs",
                selector_kind="MANIFEST",
            )
        ]
    )
    run = wf.run(workflow)
    manifest = wf.manifest(
        "stage_root_planned",
        slots=("input_01",),
        resolved=("artifact_input",),
        expected_count=1,
        manifest_id="manifest_inputs",
    )

    result = evaluate_readiness(
        wf.context(
            workflow,
            run,
            input_manifests=(manifest,),
            accepted_artifact_ids={"artifact_input"},
        )
    )

    assert result.ready_node_ids == ("root",)
    assert len(result.planned_items) == 1
    assert result.planned_items[0].expected_input_manifest_id == "manifest_inputs"
    assert result.planned_items[0].input_artifact_ids == ("artifact_input",)
    assert ReadinessReason.MANIFEST_REQUIRED not in reasons(result)


def test_many_to_one_does_not_complete_on_empty_queue(wf) -> None:
    workflow, run, root, first, second = _fan_in_workflow(wf)
    fanout_instances = (root, first, second)

    result = evaluate_readiness(
        wf.context(workflow, run, stage_instances=fanout_instances)
    )

    assert ReadinessReason.MISSING_STAGE_INSTANCE in reasons(result)
    assert "fanin" not in result.accepted_node_ids
    assert result.next_status is RunStatus.RUNNING
    assert result.planned_items == ()


def test_many_to_one_rejects_missing_expected_manifest(wf) -> None:
    workflow, run, root, first, second = _fan_in_workflow(wf)
    fanin = wf.instance(
        run,
        "fanin",
        execution=StageExecutionStatus.READY,
        acceptance=AcceptanceStatus.NOT_REQUIRED,
    )

    result = evaluate_readiness(
        wf.context(
            workflow,
            run,
            stage_instances=(root, first, second, fanin),
        )
    )

    assert ReadinessReason.MISSING_EXPECTED_MANIFEST in reasons(result)
    assert fanin.stage_instance_id not in result.ready_instance_ids


def test_many_to_one_rejects_incomplete_manifest(wf) -> None:
    workflow, run, root, first, second = _fan_in_workflow(wf)
    fanin = wf.instance(
        run,
        "fanin",
        execution=StageExecutionStatus.READY,
        acceptance=AcceptanceStatus.NOT_REQUIRED,
        manifest_id="manifest_fanin",
    )
    incomplete = wf.manifest(
        fanin.stage_instance_id,
        slots=("scene_01", "scene_02"),
        resolved=("artifact_a",),
        expected_count=2,
        complete=False,
        manifest_id="manifest_fanin",
    )

    result = evaluate_readiness(
        wf.context(
            workflow,
            run,
            stage_instances=(root, first, second, fanin),
            input_manifests=(incomplete,),
        )
    )

    assert ReadinessReason.INCOMPLETE_MANIFEST in reasons(result)
    assert fanin.stage_instance_id not in result.ready_instance_ids


def test_many_to_one_rejects_empty_manifest(wf) -> None:
    workflow, run, root, first, second = _fan_in_workflow(wf)
    fanin = wf.instance(
        run,
        "fanin",
        execution=StageExecutionStatus.READY,
        acceptance=AcceptanceStatus.NOT_REQUIRED,
        manifest_id="manifest_fanin",
    )
    empty = wf.manifest(
        fanin.stage_instance_id,
        slots=(),
        resolved=(),
        expected_count=0,
        manifest_id="manifest_fanin",
    )

    result = evaluate_readiness(
        wf.context(
            workflow,
            run,
            stage_instances=(root, first, second, fanin),
            input_manifests=(empty,),
        )
    )

    assert ReadinessReason.EMPTY_MANIFEST in reasons(result)


def test_many_to_one_complete_manifest_makes_instance_ready(wf) -> None:
    workflow, run, root, first, second = _fan_in_workflow(wf)
    fanin = wf.instance(
        run,
        "fanin",
        execution=StageExecutionStatus.READY,
        acceptance=AcceptanceStatus.NOT_REQUIRED,
        manifest_id="manifest_fanin",
    )
    complete = wf.manifest(
        fanin.stage_instance_id,
        slots=("scene_01", "scene_02"),
        resolved=("artifact_a", "artifact_b"),
        expected_count=2,
        manifest_id="manifest_fanin",
    )

    result = evaluate_readiness(
        wf.context(
            workflow,
            run,
            stage_instances=(root, first, second, fanin),
            input_manifests=(complete,),
            accepted_artifact_ids={"artifact_a", "artifact_b"},
        )
    )

    assert fanin.stage_instance_id in result.ready_instance_ids
    assert "downstream" not in result.ready_node_ids
    assert not reasons(result) & {
        ReadinessReason.INCOMPLETE_MANIFEST,
        ReadinessReason.MISSING_EXPECTED_MANIFEST,
        ReadinessReason.INPUT_ARTIFACT_NOT_ACCEPTED,
    }


def test_many_to_one_complete_manifest_requires_accepted_inputs(wf) -> None:
    workflow, run, root, first, second = _fan_in_workflow(wf)
    fanin = wf.instance(
        run,
        "fanin",
        execution=StageExecutionStatus.READY,
        acceptance=AcceptanceStatus.NOT_REQUIRED,
        manifest_id="manifest_fanin",
    )
    complete = wf.manifest(
        fanin.stage_instance_id,
        slots=("scene_01", "scene_02"),
        resolved=("artifact_a", "artifact_b"),
        expected_count=2,
        manifest_id="manifest_fanin",
    )

    result = evaluate_readiness(
        wf.context(
            workflow,
            run,
            stage_instances=(root, first, second, fanin),
            input_manifests=(complete,),
        )
    )

    assert ReadinessReason.INPUT_ARTIFACT_NOT_ACCEPTED in reasons(result)
    assert fanin.stage_instance_id not in result.ready_instance_ids


def test_many_to_one_uses_policy_expected_manifest_id(wf) -> None:
    workflow = wf.workflow(
        [
            wf.node("root", stage_name="manual_topic"),
            wf.node(
                "fanout",
                depends_on=["root"],
                mode="one_to_many",
                count=2,
            ),
            wf.node(
                "fanin",
                depends_on=["fanout"],
                mode="many_to_one",
                expected_manifest_id="manifest_fanin",
            ),
        ]
    )
    run = wf.run(workflow)
    root = wf.accepted(run, "root")
    first = wf.accepted(run, "fanout", key="fanout:01")
    second = wf.accepted(run, "fanout", key="fanout:02")
    fanin = wf.instance(
        run,
        "fanin",
        execution=StageExecutionStatus.READY,
        acceptance=AcceptanceStatus.NOT_REQUIRED,
    )
    manifest = wf.manifest(
        fanin.stage_instance_id,
        slots=("scene_01", "scene_02"),
        resolved=("artifact_a", "artifact_b"),
        expected_count=2,
        manifest_id="manifest_fanin",
    )

    result = evaluate_readiness(
        wf.context(
            workflow,
            run,
            stage_instances=(root, first, second, fanin),
            input_manifests=(manifest,),
            accepted_artifact_ids={"artifact_a", "artifact_b"},
        )
    )

    assert fanin.stage_instance_id in result.ready_instance_ids
    assert ReadinessReason.MISSING_EXPECTED_MANIFEST not in reasons(result)


def test_many_to_one_accepted_instance_unblocks_downstream(wf) -> None:
    workflow, run, root, first, second = _fan_in_workflow(wf)
    fanin = wf.instance(
        run,
        "fanin",
        acceptance=AcceptanceStatus.NOT_REQUIRED,
        outputs=("artifact_fanin",),
    )

    result = evaluate_readiness(
        wf.context(
            workflow,
            run,
            stage_instances=(root, first, second, fanin),
        )
    )

    assert "fanin" in result.accepted_node_ids
    assert result.ready_node_ids == ("downstream",)


def test_many_to_many_count_requires_every_declared_item(wf) -> None:
    workflow = wf.workflow(
        [
            wf.node("root", stage_name="manual_topic"),
            wf.node(
                "many",
                depends_on=["root"],
                mode="many_to_many",
                count=2,
            ),
            wf.node("downstream", depends_on=["many"]),
        ]
    )
    run = wf.run(workflow)
    root = wf.accepted(run, "root")

    initial = evaluate_readiness(wf.context(workflow, run, stage_instances=(root,)))
    assert [item.logical_item_key for item in initial.planned_items] == [
        "many:01",
        "many:02",
    ]
    assert "many" not in initial.accepted_node_ids
    assert initial.next_status is RunStatus.RUNNING

    first = wf.accepted(run, "many", key="many:01")
    partial = evaluate_readiness(
        wf.context(workflow, run, stage_instances=(root, first))
    )
    assert [item.logical_item_key for item in partial.planned_items] == ["many:02"]
    assert "many" not in partial.accepted_node_ids


def test_many_to_many_manifest_policy_requires_manifest(wf) -> None:
    workflow = wf.workflow(
        [
            wf.node("root", stage_name="manual_topic"),
            wf.node(
                "many",
                depends_on=["root"],
                mode="many_to_many",
                selection_policy="manifest_children",
            ),
            wf.node("downstream", depends_on=["many"]),
        ]
    )
    run = wf.run(workflow)
    root = wf.accepted(run, "root")

    missing = evaluate_readiness(wf.context(workflow, run, stage_instances=(root,)))
    assert ReadinessReason.MISSING_EXPECTED_MANIFEST in reasons(missing)
    assert "many" not in missing.ready_node_ids

    complete = wf.manifest(
        "stage_many_planned",
        slots=("item_01", "item_02"),
        resolved=("artifact_a", "artifact_b"),
        expected_count=2,
    )
    planned = evaluate_readiness(
        wf.context(
            workflow,
            run,
            stage_instances=(root,),
            input_manifests=(complete,),
        )
    )
    assert [item.logical_item_key for item in planned.planned_items] == [
        "item_01",
        "item_02",
    ]


def test_many_to_many_without_count_or_manifest_is_rejected_at_runtime(wf) -> None:
    node = StageNode.model_validate(wf.node("many", mode="one_to_one"))
    invalid_cardinality = node.cardinality.model_copy(
        update={
            "mode": CardinalityMode.MANY_TO_MANY,
            "count": None,
            "selection_policy": None,
        }
    )
    invalid_node = node.model_copy(update={"cardinality": invalid_cardinality})

    plan = plan_cardinality(invalid_node, stage_instances=(), input_manifests=())

    assert ReadinessReason.MISSING_EXPECTED_MANIFEST in {
        issue.code for issue in plan.issues
    }


def test_enabled_when_disables_root_and_blocks_dependents(wf) -> None:
    condition = {
        "schema_version": "condition-expression.v1",
        "operator": "EXISTS",
        "operands": ["feature_enabled"],
    }
    workflow = wf.workflow(
        [
            wf.node(
                "root",
                stage_name="manual_topic",
                enabled_when=condition,
            ),
            wf.node("child", depends_on=["root"]),
        ]
    )
    run = wf.run(workflow)

    disabled = evaluate_readiness(wf.context(workflow, run))
    assert disabled.disabled_node_ids == ("root",)
    assert disabled.ready_node_ids == ()
    assert ReadinessReason.DEPENDENCY_DISABLED in reasons(disabled)

    enabled = evaluate_readiness(
        wf.context(workflow, run, condition_context={"feature_enabled": True})
    )
    assert enabled.disabled_node_ids == ()
    assert enabled.ready_node_ids == ("root",)


def test_one_to_one_rejects_multiple_stage_instances(wf) -> None:
    workflow = wf.root_workflow()
    run = wf.run(workflow)
    first = wf.accepted(run, "root", key="default")
    second = wf.accepted(run, "root", key="extra")

    result = evaluate_readiness(
        wf.context(workflow, run, stage_instances=(first, second))
    )

    assert ReadinessReason.CARDINALITY_MISMATCH in reasons(result)
    assert "root" not in result.accepted_node_ids


def test_ready_instance_with_active_attempt_is_blocked(wf) -> None:
    workflow = wf.root_workflow()
    run = wf.run(workflow)
    instance = wf.instance(
        run,
        "root",
        execution=StageExecutionStatus.READY,
        acceptance=AcceptanceStatus.NOT_REQUIRED,
        active_attempt_id="attempt_01",
    )

    result = evaluate_readiness(wf.context(workflow, run, stage_instances=(instance,)))

    assert result.ready_node_ids == ()
    assert result.ready_instance_ids == ()
    assert ReadinessReason.ACTIVE_ATTEMPT in reasons(result)


def test_terminal_run_has_no_ready_work(wf) -> None:
    workflow = wf.chain(2)

    for status in (
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    ):
        run = wf.run(workflow, status=status)
        result = evaluate_readiness(wf.context(workflow, run))

        assert result.next_status is status
        assert result.ready_node_ids == ()
        assert result.ready_instance_ids == ()
        assert result.planned_items == ()


def test_readiness_is_idempotent_and_does_not_mutate_inputs(wf) -> None:
    workflow = wf.workflow(
        [
            wf.node("root", stage_name="manual_topic"),
            wf.node(
                "fanout",
                depends_on=["root"],
                mode="one_to_many",
                count=2,
            ),
        ]
    )
    run = wf.run(workflow)
    root = wf.accepted(run, "root")
    context = wf.context(workflow, run, stage_instances=(root,))
    before = context.model_dump(mode="json")

    first = evaluate_readiness(context)
    second = evaluate_readiness(context)
    after = context.model_dump(mode="json")

    assert first == second
    assert before == after
