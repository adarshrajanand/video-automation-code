from __future__ import annotations

from pipeline.contracts.vocabularies import (
    FailureCode,
    JobStatus,
    StageExecutionStatus,
)
from pipeline.execution.jobs import JobFactory
from pipeline.execution.leases import JobClaim
from pipeline.execution.worker import JobHandlerResult, WorkerLoop, WorkerRunStatus
from pipeline.storage.repositories.execution import JobRepository


class SuccessfulHandler:
    def __init__(self) -> None:
        self.claims: list[JobClaim] = []

    def __call__(self, claim: JobClaim) -> JobHandlerResult:
        self.claims.append(claim)
        return JobHandlerResult(
            succeeded=True,
            output_artifact_ids=("artifact_worker_output",),
        )


class ClassifiedFailureHandler:
    def __call__(self, claim: JobClaim) -> JobHandlerResult:
        del claim
        return JobHandlerResult(
            succeeded=False,
            failure_code=FailureCode.TRANSIENT_PROVIDER,
            failure_message="temporary provider outage",
        )


class CrashingHandler:
    def __call__(self, claim: JobClaim) -> JobHandlerResult:
        del claim
        raise RuntimeError("worker crashed in handler")


def test_worker_completes_job_with_fenced_result(records, clock) -> None:
    job = JobFactory(records.database, clock=clock).create_job(records.stage).job
    handler = SuccessfulHandler()
    worker = WorkerLoop(
        records.database,
        owner_id="worker_a",
        handler=handler,
        lease_seconds=30,
        clock=clock,
    )

    result = worker.run_once()

    assert result.status is WorkerRunStatus.COMPLETED
    assert result.completion is not None
    assert result.completion.status.value == "COMPLETED"
    assert handler.claims[0].job_id == job.job_id
    with records.database.connection() as connection:
        stored = JobRepository(connection).get(job.job_id)
    assert stored.status is JobStatus.ACKED
    assert stored.fencing_token == 1
    assert records.reload_stage().execution_status is StageExecutionStatus.SUCCEEDED


def test_worker_idle_when_no_job(records, clock) -> None:
    worker = WorkerLoop(records.database, clock=clock)

    assert worker.run_once().status is WorkerRunStatus.IDLE


def test_worker_schedules_classified_retry(records, clock) -> None:
    job = JobFactory(records.database, clock=clock).create_job(records.stage).job
    worker = WorkerLoop(
        records.database,
        owner_id="worker_a",
        handler=ClassifiedFailureHandler(),
        lease_seconds=30,
        clock=clock,
    )

    result = worker.run_once()

    assert result.status is WorkerRunStatus.RETRY_SCHEDULED
    assert result.recovery is not None
    assert result.recovery.new_creation is not None
    with records.database.connection() as connection:
        old_job = JobRepository(connection).get(job.job_id)
    assert old_job.status is JobStatus.RETRY
    assert records.reload_stage().execution_status is StageExecutionStatus.WAITING_RETRY


def test_worker_maps_unexpected_handler_exception_to_internal_failure(
    records, clock
) -> None:
    job = JobFactory(records.database, clock=clock).create_job(records.stage).job
    worker = WorkerLoop(
        records.database,
        owner_id="worker_a",
        handler=CrashingHandler(),
        lease_seconds=30,
        clock=clock,
    )

    result = worker.run_once()

    assert result.status is WorkerRunStatus.FAILED
    assert result.recovery is not None
    assert result.recovery.attempt is not None
    assert result.recovery.attempt.failure_code is FailureCode.INTERNAL
    with records.database.connection() as connection:
        stored = JobRepository(connection).get(job.job_id)
    assert stored.status is JobStatus.DEAD_LETTER
    assert records.reload_stage().execution_status is StageExecutionStatus.FAILED
