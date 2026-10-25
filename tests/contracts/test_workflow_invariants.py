from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pipeline.contracts import WorkflowDefinition

FIXTURE = Path(__file__).resolve().parents[2] / (
    "fixtures/contracts/valid/workflow_definition.json"
)


def _workflow() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _node(payload: dict, node_id: str) -> dict:
    return next(node for node in payload["nodes"] if node["node_id"] == node_id)


def test_valid_workflow_fixture_is_acyclic_and_connected() -> None:
    workflow = WorkflowDefinition.model_validate(_workflow())
    by_id = {node.node_id: node for node in workflow.nodes}

    assert set(by_id) == {"intake", "script"}
    assert by_id["intake"].depends_on == []
    assert by_id["script"].depends_on == ["intake"]
    assert set(by_id["script"].input_selector.dependency_node_ids) <= set(
        by_id["script"].depends_on
    )


def test_workflow_rejects_duplicate_nodes() -> None:
    payload = _workflow()
    payload["nodes"].append(copy.deepcopy(payload["nodes"][0]))

    with pytest.raises(ValidationError, match="duplicate workflow node IDs"):
        WorkflowDefinition.model_validate(payload)


def test_workflow_rejects_missing_dependency() -> None:
    payload = _workflow()
    node = _node(payload, "script")
    node["depends_on"] = ["missing"]
    node["input_selector"]["dependency_node_ids"] = ["missing"]

    with pytest.raises(ValidationError, match="depends on missing node"):
        WorkflowDefinition.model_validate(payload)


def test_workflow_rejects_self_dependency() -> None:
    payload = _workflow()
    node = _node(payload, "script")
    node["depends_on"] = ["script"]
    node["input_selector"]["dependency_node_ids"] = ["script"]

    with pytest.raises(ValidationError, match="must not depend on itself"):
        WorkflowDefinition.model_validate(payload)


def test_workflow_rejects_cycles() -> None:
    payload = _workflow()
    node = _node(payload, "intake")
    node["depends_on"] = ["script"]

    with pytest.raises(ValidationError, match="dependency cycle"):
        WorkflowDefinition.model_validate(payload)


def test_workflow_selector_must_reference_declared_dependencies() -> None:
    payload = _workflow()
    _node(payload, "script")["input_selector"]["dependency_node_ids"] = ["intake"]
    _node(payload, "script")["depends_on"] = []

    with pytest.raises(ValidationError, match="must be declared depends_on nodes"):
        WorkflowDefinition.model_validate(payload)


@pytest.mark.parametrize(
    ("node_id", "field", "value", "message"),
    [
        ("script", "quality_gate_id", "unknown_gate_v1", "unknown quality gate"),
        (
            "script",
            "recovery_policy_id",
            "unknown_recovery_v1",
            "unknown recovery policy",
        ),
    ],
)
def test_workflow_rejects_unknown_policy_references(
    node_id: str, field: str, value: str, message: str
) -> None:
    payload = _workflow()
    _node(payload, node_id)[field] = value

    with pytest.raises(ValidationError, match=message):
        WorkflowDefinition.model_validate(payload)


def test_workflow_rejects_empty_graph() -> None:
    payload = _workflow()
    payload["nodes"] = []

    with pytest.raises(ValidationError, match="at least one node"):
        WorkflowDefinition.model_validate(payload)


def test_workflow_rejects_invalid_cardinality() -> None:
    payload = _workflow()
    _node(payload, "script")["cardinality"] = {
        "schema_version": "cardinality.v1",
        "mode": "one_to_many",
        "count": None,
        "selection_policy": None,
        "expected_manifest_id": None,
    }

    with pytest.raises(ValidationError, match="selection_policy"):
        WorkflowDefinition.model_validate(payload)
