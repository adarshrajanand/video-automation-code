from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.contracts.vocabularies import CardinalityMode, StageName
from pipeline.workflow import WorkflowLoadError, load_workflow, load_workflow_text


def test_canonical_fast_workflow_loads(canonical_path: Path) -> None:
    workflow = load_workflow(canonical_path)

    assert workflow.workflow_id == "explainer_validation_v1"
    assert workflow.version == "1.0"
    assert workflow.policy_ids == ["default_recovery_v1"]
    assert len(workflow.nodes) == 13

    by_id = {node.node_id: node for node in workflow.nodes}
    assert [node.node_id for node in workflow.nodes if not node.depends_on] == [
        "intake"
    ]
    assert by_id["intake"].stage_name is StageName.MANUAL_TOPIC
    assert by_id["human_approval"].depends_on == ["final_review"]
    assert by_id["assets"].cardinality.mode is CardinalityMode.ONE_TO_MANY
    assert by_id["assets"].cardinality.selection_policy == "manifest_children"
    assert (
        by_id["long_form_render"].cardinality.selection_policy
        == "render_chunk_manifest"
    )
    assert by_id["composition"].cardinality.mode is CardinalityMode.MANY_TO_ONE
    assert by_id["short_derivative"].cardinality.count == 1


def test_loader_rejects_invalid_yaml() -> None:
    with pytest.raises(WorkflowLoadError, match="invalid YAML"):
        load_workflow_text("nodes: [\n")


def test_loader_rejects_non_mapping_document() -> None:
    with pytest.raises(WorkflowLoadError, match="must be a YAML mapping"):
        load_workflow_text("- intake\n- idea\n")


def test_loader_uses_safe_yaml_loader() -> None:
    document = "!!python/object/apply:os.system ['echo unsafe']\n"

    with pytest.raises(WorkflowLoadError, match="invalid YAML"):
        load_workflow_text(document)


def test_loader_rejects_unknown_workflow_field(wf) -> None:
    payload = {
        "schema_version": "workflow-definition.v1",
        "workflow_id": "bad_workflow",
        "version": "1.0",
        "nodes": [wf.node("root", stage_name="manual_topic")],
        "not_a_field": True,
    }

    with pytest.raises(WorkflowLoadError, match="invalid workflow definition"):
        from pipeline.workflow import load_workflow_data

        load_workflow_data(payload)


def test_loader_rejects_graph_cycle(wf) -> None:
    nodes = [
        wf.node("a", depends_on=["b"]),
        wf.node("b", depends_on=["a"]),
    ]
    payload = {
        "schema_version": "workflow-definition.v1",
        "workflow_id": "cyclic",
        "version": "1.0",
        "nodes": nodes,
    }

    with pytest.raises(WorkflowLoadError, match="dependency cycle"):
        from pipeline.workflow import load_workflow_data

        load_workflow_data(payload)


def test_loader_rejects_missing_dependency(wf) -> None:
    payload = {
        "schema_version": "workflow-definition.v1",
        "workflow_id": "missing_dep",
        "version": "1.0",
        "nodes": [wf.node("root", depends_on=["absent"])],
    }

    with pytest.raises(WorkflowLoadError, match="depends on missing node"):
        from pipeline.workflow import load_workflow_data

        load_workflow_data(payload)


def test_loader_rejects_duplicate_node_ids(wf) -> None:
    payload = {
        "schema_version": "workflow-definition.v1",
        "workflow_id": "duplicate_nodes",
        "version": "1.0",
        "nodes": [wf.node("root"), wf.node("root")],
    }

    with pytest.raises(WorkflowLoadError, match="duplicate workflow node IDs"):
        from pipeline.workflow import load_workflow_data

        load_workflow_data(payload)


def test_loader_rejects_unknown_quality_gate(wf) -> None:
    payload = {
        "schema_version": "workflow-definition.v1",
        "workflow_id": "bad_gate",
        "version": "1.0",
        "nodes": [wf.node("root", gate="not_a_gate_v1")],
    }

    with pytest.raises(WorkflowLoadError, match="unknown quality gate"):
        from pipeline.workflow import load_workflow_data

        load_workflow_data(payload)


def test_loader_reports_missing_file(tmp_path: Path) -> None:
    with pytest.raises(WorkflowLoadError, match="cannot read workflow definition"):
        load_workflow(tmp_path / "absent.yaml")
