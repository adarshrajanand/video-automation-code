from __future__ import annotations

from datetime import UTC, datetime

from pipeline.cli import main
from pipeline.contracts.vocabularies import JobStatus, OutboxStatus
from pipeline.execution.events import EventOutbox
from pipeline.execution.jobs import JobFactory
from pipeline.storage.repositories.events import OutboxMessageRepository
from pipeline.storage.repositories.execution import (
    JobRepository,
    StageInstanceRepository,
)


def test_outbox_dispatch_cli_smoke(records, clock, capsys) -> None:
    EventOutbox(records.database, clock=clock).append(records.event())

    exit_code = main(
        [
            "outbox",
            "dispatch",
            "--once",
            "--database",
            str(records.database.path),
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Outbox dispatch: claimed=1 delivered=1" in output
    with records.database.connection() as connection:
        message = OutboxMessageRepository(connection).get_by_event_id("event_ready_01")
    assert message is not None
    assert message.status is OutboxStatus.DELIVERED


def test_worker_run_cli_smoke(records, clock, capsys) -> None:
    old = datetime(2020, 1, 1, tzinfo=UTC)
    stage = records.stage.model_copy(update={"created_at": old, "updated_at": old})
    with records.database.transaction() as connection:
        StageInstanceRepository(connection).update(stage)
    job = JobFactory(records.database, clock=clock).create_job(stage).job

    exit_code = main(
        [
            "worker",
            "run",
            "--once",
            "--database",
            str(records.database.path),
            "--owner-id",
            "worker_cli_test",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "worker_cli_test: COMPLETED" in output
    with records.database.connection() as connection:
        stored = JobRepository(connection).get(job.job_id)
    assert stored.status is JobStatus.ACKED
    assert stored.claimed_by is None
