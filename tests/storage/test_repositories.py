from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from pipeline.contracts.vocabularies import ArtifactPointerType, RunStatus
from pipeline.fingerprints import canonical_json
from pipeline.storage import (
    ArtifactDependencyRepository,
    ArtifactPointerRepository,
    ArtifactRepository,
    BudgetReservationRepository,
    CompositionRefRepository,
    ContentPackageRepository,
    CutRepository,
    EffectiveConfigRepository,
    EpisodeRepository,
    IdempotencyRecordRepository,
    JobRepository,
    LayerInstanceRepository,
    LeaseRepository,
    NotFoundError,
    SceneRepository,
    SequenceRepository,
    ShotRepository,
    StageAttemptRepository,
    StageInstanceRepository,
    WorkflowRunRepository,
)

REPOSITORIES = {
    "effective_config": (EffectiveConfigRepository, ("effective_config_id",)),
    "run": (WorkflowRunRepository, ("run_id",)),
    "stage_instance": (StageInstanceRepository, ("stage_instance_id",)),
    "stage_attempt": (StageAttemptRepository, ("attempt_id",)),
    "job": (JobRepository, ("job_id",)),
    "lease": (LeaseRepository, ("job_id", "fencing_token")),
    "idempotency_record": (
        IdempotencyRecordRepository,
        ("idempotency_key",),
    ),
    "budget_reservation": (
        BudgetReservationRepository,
        ("reservation_id",),
    ),
    "artifact_parent": (ArtifactRepository, ("artifact_id",)),
    "artifact_child": (ArtifactRepository, ("artifact_id",)),
    "artifact_dependency": (
        ArtifactDependencyRepository,
        ("parent_artifact_id", "child_artifact_id"),
    ),
    "artifact_pointer": (ArtifactPointerRepository, ("pointer_id",)),
    "content_package": (ContentPackageRepository, ("content_package_id",)),
    "episode": (EpisodeRepository, ("episode_id",)),
    "cut": (CutRepository, ("cut_id",)),
    "sequence": (SequenceRepository, ("sequence_id",)),
    "scene": (SceneRepository, ("scene_id",)),
    "shot": (ShotRepository, ("shot_id",)),
    "layer_instance": (LayerInstanceRepository, ("layer_id",)),
    "composition_ref": (
        CompositionRefRepository,
        ("composition_artifact_id",),
    ),
}


def _insert_graph(connection, records) -> dict[str, Any]:
    graph = dict(records.graph())
    for name, record in graph.items():
        repository_class, _ = REPOSITORIES[name]
        repository_class(connection).insert(record)
    return graph


def test_every_typed_repository_round_trips(database, records) -> None:
    with database.transaction() as connection:
        graph = _insert_graph(connection, records)

    with database.connection() as connection:
        for name, record in graph.items():
            repository_class, key_fields = REPOSITORIES[name]
            key = tuple(getattr(record, field) for field in key_fields)
            loaded = repository_class(connection).get(*key)
            assert loaded == record
            assert type(loaded) is type(record)


def test_list_and_lookup_helpers(database, records) -> None:
    with database.transaction() as connection:
        graph = _insert_graph(connection, records)

    run = graph["run"]
    stage = graph["stage_instance"]
    attempt = graph["stage_attempt"]
    job = graph["job"]
    lease = graph["lease"]
    parent = graph["artifact_parent"]
    child = graph["artifact_child"]
    pointer = graph["artifact_pointer"]
    episode = graph["episode"]
    cut = graph["cut"]
    sequence = graph["sequence"]
    scene = graph["scene"]
    shot = graph["shot"]

    with database.connection() as connection:
        runs = WorkflowRunRepository(connection)
        assert runs.get_by_run_key(run.run_key) == run
        assert runs.list_by_status(RunStatus.RUNNING) == [run]
        assert runs.list_by_status(RunStatus.COMPLETED) == []

        stages = StageInstanceRepository(connection)
        assert stages.list_for_run(run.run_id) == [stage]
        assert stages.get_by_logical_item(run.run_id, stage.node_id, "episode") == stage
        assert stages.get_by_logical_item(run.run_id, stage.node_id, "other") is None

        attempts = StageAttemptRepository(connection)
        assert attempts.list_for_stage_instance(stage.stage_instance_id) == [attempt]

        jobs = JobRepository(connection)
        assert jobs.get_by_idempotency_key(job.idempotency_key) == job
        assert jobs.list_by_status(job.status) == [job]

        leases = LeaseRepository(connection)
        assert leases.list_for_job(job.job_id) == [lease]
        assert leases.latest_for_job(job.job_id) == lease
        assert leases.latest_for_job("missing") is None

        artifacts = ArtifactRepository(connection)
        assert artifacts.list_for_run(run.run_id) == [parent, child]
        assert (
            artifacts.get_by_slot_version(run.run_id, parent.logical_slot, 1) == parent
        )
        assert artifacts.next_version(run.run_id, parent.logical_slot) == 2
        assert artifacts.list_by_sha256(parent.sha256) == [parent]

        dependencies = ArtifactDependencyRepository(connection)
        assert dependencies.list_for_parent(parent.artifact_id) == [
            graph["artifact_dependency"]
        ]
        assert dependencies.list_for_child(child.artifact_id) == [
            graph["artifact_dependency"]
        ]

        pointers = ArtifactPointerRepository(connection)
        assert (
            pointers.get_active(
                run.run_id, pointer.logical_slot, ArtifactPointerType.CURRENT
            )
            == pointer
        )
        assert pointers.list_active_for_run(run.run_id) == [pointer]

        assert EpisodeRepository(connection).list_for_package(
            episode.content_package_id
        ) == [episode]
        assert CutRepository(connection).list_for_episode(episode.episode_id) == [cut]
        assert SequenceRepository(connection).list_for_episode(episode.episode_id) == [
            sequence
        ]
        assert SceneRepository(connection).list_for_sequence(sequence.sequence_id) == [
            scene
        ]
        assert ShotRepository(connection).list_for_scene(scene.scene_id) == [shot]
        assert LayerInstanceRepository(connection).list_for_shot(shot.shot_id) == [
            graph["layer_instance"]
        ]
        assert CompositionRefRepository(connection).list_for_cut(cut.cut_id) == [
            graph["composition_ref"]
        ]


def test_update_persists_projection_and_payload(database, records) -> None:
    config = records.effective_config()
    run = records.run(config)
    with database.transaction() as connection:
        EffectiveConfigRepository(connection).insert(config)
        WorkflowRunRepository(connection).insert(run)

    updated = run.model_copy(
        update={
            "status": RunStatus.COMPLETED,
            "updated_at": datetime(2026, 10, 21, 11, 0, tzinfo=UTC),
        }
    )
    with database.transaction() as connection:
        WorkflowRunRepository(connection).update(updated)

    with database.connection() as connection:
        loaded = WorkflowRunRepository(connection).get(run.run_id)
        assert loaded.status is RunStatus.COMPLETED
        assert loaded == updated
        status = connection.execute(
            "SELECT status FROM workflow_runs WHERE run_id = ?", (run.run_id,)
        ).fetchone()[0]
        assert status == "COMPLETED"


def test_loaded_payload_is_revalidated(database, records) -> None:
    config = records.effective_config()
    with database.transaction() as connection:
        EffectiveConfigRepository(connection).insert(config)

    with database.transaction() as connection:
        connection.execute(
            "UPDATE effective_configs SET payload = ? WHERE effective_config_id = ?",
            ('{"schema_version": "effective-config.v1"}', config.effective_config_id),
        )

    with database.connection() as connection, pytest.raises(ValidationError):
        EffectiveConfigRepository(connection).get(config.effective_config_id)


def test_payload_is_canonical_json(database, records) -> None:
    config = records.effective_config()
    with database.transaction() as connection:
        EffectiveConfigRepository(connection).insert(config)

    with database.connection() as connection:
        payload = connection.execute(
            "SELECT payload FROM effective_configs WHERE effective_config_id = ?",
            (config.effective_config_id,),
        ).fetchone()[0]
    assert payload == canonical_json(config)


def test_missing_records_raise_not_found(database, records) -> None:
    with database.connection() as connection:
        with pytest.raises(NotFoundError):
            EffectiveConfigRepository(connection).get("missing")
        with pytest.raises(NotFoundError):
            WorkflowRunRepository(connection).get("missing")
        with pytest.raises(NotFoundError):
            LeaseRepository(connection).get("missing-job", 1)
        with pytest.raises(NotFoundError):
            ArtifactDependencyRepository(connection).get("a", "b")
        with pytest.raises(NotFoundError):
            EffectiveConfigRepository(connection).update(
                records.effective_config("missing")
            )
