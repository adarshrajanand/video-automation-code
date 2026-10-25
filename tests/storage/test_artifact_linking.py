from __future__ import annotations

from pipeline.contracts.artifacts import Artifact
from pipeline.contracts.vocabularies import ArtifactPointerType
from pipeline.storage import (
    ArtifactDependencyRepository,
    ArtifactPointerRepository,
    ArtifactRepository,
    Database,
    EffectiveConfigRepository,
    StageAttemptRepository,
    StageInstanceRepository,
    WorkflowRunRepository,
)


def test_artifact_metadata_dependency_and_pointer_linking(
    database: Database, records, artifact_store
) -> None:
    config = records.effective_config()
    run = records.run(config)
    stage = records.stage_instance(run)
    attempt = records.stage_attempt(stage)

    first_bytes = b"script version one"
    second_bytes = b"script version two"
    first_stored = artifact_store.publish_bytes(first_bytes)
    second_stored = artifact_store.publish_bytes(second_bytes)
    first = records.artifact(
        run,
        attempt,
        "script_v1",
        logical_slot="script",
        version=1,
        content=first_bytes,
    )
    second = records.artifact(
        run,
        attempt,
        "script_v2",
        logical_slot="script",
        version=2,
        content=second_bytes,
    )
    assert first.uri == first_stored.uri
    assert first.sha256 == first_stored.sha256
    assert second.uri == second_stored.uri
    dependency = records.dependency(first, second, dependency_type="replacement")
    first_pointer = records.pointer(run, first, "01")
    second_pointer = records.pointer(run, second, "02")

    with database.transaction() as connection:
        EffectiveConfigRepository(connection).insert(config)
        WorkflowRunRepository(connection).insert(run)
        StageInstanceRepository(connection).insert(stage)
        StageAttemptRepository(connection).insert(attempt)
        artifacts = ArtifactRepository(connection)
        artifacts.insert(first)
        artifacts.insert(second)
        ArtifactDependencyRepository(connection).insert(dependency)
        ArtifactPointerRepository(connection).activate(first_pointer)

    with database.transaction() as connection:
        ArtifactPointerRepository(connection).activate(second_pointer)

    with database.connection() as connection:
        loaded_first = ArtifactRepository(connection).get(first.artifact_id)
        loaded_second = ArtifactRepository(connection).get(second.artifact_id)
        assert loaded_first.media_type == "text/markdown"
        assert loaded_first.size_bytes == len(first_bytes)
        assert loaded_second.version == 2
        assert artifact_store.read(loaded_first.uri) == first_bytes
        assert artifact_store.read(loaded_second.uri) == second_bytes
        assert (
            artifact_store.verify(loaded_first.uri, expected_sha256=loaded_first.sha256)
            == loaded_first.sha256
        )

        assert ArtifactDependencyRepository(connection).list_for_parent(
            first.artifact_id
        ) == [dependency]
        assert ArtifactDependencyRepository(connection).list_for_child(
            second.artifact_id
        ) == [dependency]

        pointer_repository = ArtifactPointerRepository(connection)
        active = pointer_repository.get_active(
            run.run_id, "script", ArtifactPointerType.CURRENT
        )
        assert active == second_pointer
        history = pointer_repository.list_for_slot(run.run_id, "script")
        assert [pointer.pointer_id for pointer in history] == [
            first_pointer.pointer_id,
            second_pointer.pointer_id,
        ]
        assert history[0].active is False
        assert history[1].active is True

        versions = ArtifactRepository(connection).list_for_run(run.run_id)
        assert [artifact.version for artifact in versions] == [1, 2]
        assert all(isinstance(artifact, Artifact) for artifact in versions)
