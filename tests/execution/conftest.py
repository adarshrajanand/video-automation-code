from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pipeline.contracts.config import EffectiveConfig
from pipeline.contracts.events import EventEnvelope
from pipeline.contracts.execution import StageAttempt, StageInstance, WorkflowRun
from pipeline.contracts.jobs import Job
from pipeline.contracts.vocabularies import (
    AcceptanceStatus,
    EventType,
    RunStatus,
    StageExecutionStatus,
)
from pipeline.fingerprints import sha256_text
from pipeline.storage import Database, MigrationRunner
from pipeline.storage.repositories.execution import (
    EffectiveConfigRepository,
    JobRepository,
    StageAttemptRepository,
    StageInstanceRepository,
    WorkflowRunRepository,
)

BASE_TIME = datetime(2026, 10, 23, 9, 0, tzinfo=UTC)
CONFIG_HASH = sha256_text("fv-05-config")


def at(minutes: float = 0) -> datetime:
    return BASE_TIME + timedelta(minutes=minutes)


class MutableClock:
    """Small injected clock that makes lease and backoff tests deterministic."""

    def __init__(self, now: datetime = BASE_TIME) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, *, seconds: float = 0, minutes: float = 0) -> None:
        self.now += timedelta(seconds=seconds, minutes=minutes)


@dataclass
class ExecutionRecords:
    """Seeded durable run/stage plus convenience repository reads."""

    database: Database
    config: EffectiveConfig
    run: WorkflowRun
    stage: StageInstance

    def reload_stage(self) -> StageInstance:
        with self.database.connection() as connection:
            return StageInstanceRepository(connection).get(self.stage.stage_instance_id)

    def attempts(self) -> list[StageAttempt]:
        with self.database.connection() as connection:
            return StageAttemptRepository(connection).list_for_stage_instance(
                self.stage.stage_instance_id
            )

    def jobs(self) -> list[Job]:
        with self.database.connection() as connection:
            repository = JobRepository(connection)
            jobs: list[Job] = []
            for attempt in self.attempts():
                jobs.extend(repository.list_for_attempt(attempt.attempt_id))
            return jobs

    def event(
        self,
        *,
        event_id: str = "event_ready_01",
        job_id: str = "job_pending",
        event_type: EventType = EventType.STAGE_READY,
        created_at: datetime | None = None,
    ) -> EventEnvelope:
        if event_type is not EventType.STAGE_READY:
            raise ValueError("the test fixture only builds stage.ready events")
        return EventEnvelope(
            schema_version="event-envelope.v1",
            event_id=event_id,
            event_type=event_type,
            run_id=self.run.run_id,
            stage_instance_id=self.stage.stage_instance_id,
            correlation_id="corr_fv05",
            payload_schema_version="stage-ready.v1",
            payload={
                "run_id": self.run.run_id,
                "stage_instance_id": self.stage.stage_instance_id,
                "job_id": job_id,
            },
            created_at=created_at or at(),
        )


@pytest.fixture
def clock() -> MutableClock:
    return MutableClock(at(5))


@pytest.fixture
def database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "pipeline.sqlite")
    MigrationRunner(database).migrate()
    return database


@pytest.fixture
def records(database: Database) -> ExecutionRecords:
    config = EffectiveConfig(
        schema_version="effective-config.v1",
        effective_config_id="cfg_fv05",
        system_policy_version="1.0",
        domain_profile_id="software_engineering_explainer_v1",
        domain_profile_version="1.0",
        channel_profile_id="channel_explainer_v1",
        channel_profile_version="1.0",
        workflow_id="explainer_validation_v1",
        workflow_version="1.0",
        run_overrides={"schema_version": "run-overrides.v1", "locale": "en-US"},
        resolved_values={"locale": "en-US"},
        source_map={"locale": "channel_profile:channel_explainer_v1"},
        config_hash=CONFIG_HASH,
        snapshot_artifact_id=None,
    )
    run = WorkflowRun(
        schema_version="workflow-run.v1",
        run_id="run_fv05",
        run_key="run-key:fv05",
        workflow_id=config.workflow_id,
        workflow_version=config.workflow_version,
        effective_config_id=config.effective_config_id,
        effective_config_hash=config.config_hash,
        status=RunStatus.RUNNING,
        content_package_id="package_fv05",
        created_at=at(0),
        updated_at=at(0),
    )
    stage = StageInstance(
        schema_version="stage-instance.v1",
        stage_instance_id="stage_fv05_research",
        run_id=run.run_id,
        node_id="research",
        logical_item_key="episode",
        execution_status=StageExecutionStatus.READY,
        acceptance_status=AcceptanceStatus.NOT_REQUIRED,
        quality_gate_id=None,
        expected_input_manifest_id=None,
        active_attempt_id=None,
        accepted_output_artifact_ids=[],
        created_at=at(1),
        updated_at=at(1),
    )
    with database.transaction() as connection:
        EffectiveConfigRepository(connection).insert(config)
        WorkflowRunRepository(connection).insert(run)
        StageInstanceRepository(connection).insert(stage)
    return ExecutionRecords(database=database, config=config, run=run, stage=stage)
