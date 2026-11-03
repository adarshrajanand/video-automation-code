from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.contracts.vocabularies import AcceptanceStatus, StageExecutionStatus
from pipeline.execution.stages import StageFactory, derive_stage_instance_id
from pipeline.storage.repositories.execution import StageInstanceRepository
from pipeline.workflow.loader import load_workflow

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2] / "workflows" / "explainer_validation_v1.yaml"
)
WORKFLOW = load_workflow(WORKFLOW_PATH)
RESEARCH_NODE = next(node for node in WORKFLOW.nodes if node.node_id == "research")
INTAKE_NODE = next(node for node in WORKFLOW.nodes if node.node_id == "intake")


def test_two_items_in_one_node_get_distinct_ids(records, clock) -> None:
    factory = StageFactory(records.database, clock=clock)

    first = factory.create_stage(records.run, RESEARCH_NODE, "claim:01")
    second = factory.create_stage(records.run, RESEARCH_NODE, "claim:02")

    assert first.created is True
    assert second.created is True
    assert first.stage_instance.stage_instance_id != (
        second.stage_instance.stage_instance_id
    )
    assert first.stage_instance.stage_instance_id == derive_stage_instance_id(
        records.run.run_id, RESEARCH_NODE.node_id, "claim:01"
    )
    assert second.stage_instance.stage_instance_id == derive_stage_instance_id(
        records.run.run_id, RESEARCH_NODE.node_id, "claim:02"
    )
    with records.database.connection() as connection:
        stored = StageInstanceRepository(connection).list_for_run(records.run.run_id)
    assert len(stored) == 3  # seeded research stage plus two new items


def test_repeated_creation_returns_existing_stage(records, clock) -> None:
    factory = StageFactory(records.database, clock=clock)

    first = factory.create_stage(records.run, INTAKE_NODE, "episode")
    second = factory.create_stage(records.run, INTAKE_NODE, "episode")

    assert first.created is True
    assert second.created is False
    assert second.stage_instance == first.stage_instance
    with records.database.connection() as connection:
        stored = StageInstanceRepository(connection).get_by_logical_item(
            records.run.run_id, INTAKE_NODE.node_id, "episode"
        )
    assert stored is not None
    assert stored.stage_instance_id == first.stage_instance.stage_instance_id


def test_created_stage_uses_node_gate_and_ready_status(records, clock) -> None:
    factory = StageFactory(records.database, clock=clock)

    result = factory.create_stage(records.run, RESEARCH_NODE, "claim:01")

    stage = result.stage_instance
    assert stage.execution_status is StageExecutionStatus.READY
    assert stage.acceptance_status is AcceptanceStatus.PENDING
    assert stage.quality_gate_id == "research_gate_v1"
    assert stage.created_at == clock.now
    assert stage.updated_at == clock.now


def test_gateless_node_starts_without_acceptance(records, clock) -> None:
    factory = StageFactory(records.database, clock=clock)

    result = factory.create_stage(records.run, INTAKE_NODE, "episode")

    assert result.stage_instance.quality_gate_id is None
    assert result.stage_instance.acceptance_status is AcceptanceStatus.NOT_REQUIRED


def test_padded_key_normalizes_to_canonical_identity(records, clock) -> None:
    factory = StageFactory(records.database, clock=clock)

    padded = factory.create_stage(records.run, RESEARCH_NODE, " claim:01 ")
    canonical = factory.create_stage(records.run, RESEARCH_NODE, "claim:01")

    assert padded.created is True
    assert canonical.created is False
    assert canonical.stage_instance == padded.stage_instance
    assert padded.stage_instance.logical_item_key == "claim:01"
    assert padded.stage_instance.stage_instance_id == derive_stage_instance_id(
        records.run.run_id, RESEARCH_NODE.node_id, "claim:01"
    )


def test_derive_stage_instance_id_normalizes_item_key(records) -> None:
    assert derive_stage_instance_id(
        records.run.run_id, RESEARCH_NODE.node_id, " claim:01 "
    ) == derive_stage_instance_id(records.run.run_id, RESEARCH_NODE.node_id, "claim:01")


def test_blank_item_key_is_rejected(records, clock) -> None:
    factory = StageFactory(records.database, clock=clock)

    with pytest.raises(ValueError):
        factory.create_stage(records.run, RESEARCH_NODE, "   ")
