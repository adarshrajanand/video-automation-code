"""Idempotent creation of one stage attempt and one claimable job."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from pipeline.contracts.execution import StageAttempt, StageInstance
from pipeline.contracts.jobs import Job
from pipeline.contracts.vocabularies import (
    AttemptStatus,
    JobStatus,
    StageExecutionStatus,
)
from pipeline.ids import deterministic_id, idempotency_key
from pipeline.storage.database import Database
from pipeline.storage.repositories.execution import (
    JobRepository,
    StageAttemptRepository,
    StageInstanceRepository,
)


class JobCreationError(RuntimeError):
    """A stage instance is not in a state that may create claimable work."""


@dataclass(frozen=True, slots=True)
class JobCreationResult:
    """One attempt/job pair, including whether this call created it."""

    stage_instance: StageInstance
    attempt: StageAttempt
    job: Job
    created: bool


class JobFactory:
    """Create StageAttempt/Job pairs transactionally from READY stage work.

    Default creation is idempotent per logical stage instance: if any attempt
    already has a job, the existing pair is returned instead of creating another
    accepted unit of work. Callers that deliberately need a new transport attempt
    (for example after a classified transient failure) pass
    ``attempt_number``/``allow_new_attempt=True``; the unique job
    ``idempotency_key`` still makes an accidental repeat of that number a no-op.
    """

    def __init__(
        self,
        database: Database,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.database = database
        self._clock = clock or _utc_now

    def create_job(
        self,
        stage_instance: StageInstance,
        *,
        queue_name: str = "default",
        input_artifact_ids: Sequence[str] = (),
        attempt_number: int | None = None,
        available_at: datetime | None = None,
        allow_new_attempt: bool = False,
        connection: sqlite3.Connection | None = None,
    ) -> JobCreationResult:
        """Create or return the idempotent attempt/job pair for one stage item."""

        if connection is not None:
            if not connection.in_transaction:
                raise ValueError(
                    "JobFactory.create_job requires an explicit caller "
                    "transaction when a connection is supplied"
                )
            return self._create(
                connection,
                stage_instance,
                queue_name=queue_name,
                input_artifact_ids=input_artifact_ids,
                attempt_number=attempt_number,
                available_at=available_at,
                allow_new_attempt=allow_new_attempt,
            )
        with self.database.transaction(immediate=True) as transaction:
            return self._create(
                transaction,
                stage_instance,
                queue_name=queue_name,
                input_artifact_ids=input_artifact_ids,
                attempt_number=attempt_number,
                available_at=available_at,
                allow_new_attempt=allow_new_attempt,
            )

    def _create(
        self,
        connection: sqlite3.Connection,
        stage_instance: StageInstance,
        *,
        queue_name: str,
        input_artifact_ids: Sequence[str],
        attempt_number: int | None,
        available_at: datetime | None,
        allow_new_attempt: bool,
    ) -> JobCreationResult:
        stages = StageInstanceRepository(connection)
        attempts = StageAttemptRepository(connection)
        jobs = JobRepository(connection)

        stage = stages.get(stage_instance.stage_instance_id)
        now = self._clock()
        existing_attempts = attempts.list_for_stage_instance(stage.stage_instance_id)

        if attempt_number is not None:
            if attempt_number < 1:
                raise ValueError("attempt_number must be at least 1")
            key = self._job_key(stage, attempt_number)
            existing_job = jobs.get_by_idempotency_key_optional(key)
            if existing_job is not None:
                attempt = attempts.get(existing_job.attempt_id)
                return JobCreationResult(
                    stage_instance=stage,
                    attempt=attempt,
                    job=existing_job,
                    created=False,
                )
        elif not allow_new_attempt:
            existing = self._latest_existing(connection, stage, existing_attempts)
            if existing is not None:
                return existing

        if stage.execution_status is not StageExecutionStatus.READY:
            raise JobCreationError(
                "stage instance must be READY to create a job, not "
                f"{stage.execution_status.value}"
            )
        if not allow_new_attempt and existing_attempts and attempt_number is None:
            # A prior attempt exists without a job. That should be an
            # all-or-nothing transaction rollback, so treat it as corruption
            # rather than silently inventing a second attempt.
            raise JobCreationError(
                "stage instance already has an attempt without a job; "
                "repair the incomplete creation explicitly"
            )

        number = attempt_number or (
            max((attempt.attempt_number for attempt in existing_attempts), default=0)
            + 1
        )
        key = self._job_key(stage, number)
        duplicated = jobs.get_by_idempotency_key_optional(key)
        if duplicated is not None:
            attempt = attempts.get(duplicated.attempt_id)
            return JobCreationResult(
                stage_instance=stage,
                attempt=attempt,
                job=duplicated,
                created=False,
            )

        attempt_id = deterministic_id("attempt", stage.stage_instance_id, number)
        attempt = StageAttempt(
            schema_version="stage-attempt.v1",
            attempt_id=attempt_id,
            stage_instance_id=stage.stage_instance_id,
            attempt_number=number,
            quality_regeneration_number=0,
            status=AttemptStatus.CREATED,
            input_artifact_ids=list(dict.fromkeys(input_artifact_ids)),
        )
        job = Job(
            schema_version="job.v1",
            job_id=deterministic_id("job", stage.stage_instance_id, number),
            attempt_id=attempt.attempt_id,
            queue_name=queue_name,
            status=JobStatus.READY,
            idempotency_key=key,
            available_at=available_at or now,
            delivery_count=0,
        )
        attempts.insert(attempt)
        jobs.insert(job)
        return JobCreationResult(
            stage_instance=stage,
            attempt=attempt,
            job=job,
            created=True,
        )

    def _latest_existing(
        self,
        connection: sqlite3.Connection,
        stage: StageInstance,
        existing_attempts: Sequence[StageAttempt],
    ) -> JobCreationResult | None:
        jobs = JobRepository(connection)
        for attempt in reversed(existing_attempts):
            attempt_jobs = jobs.list_for_attempt(attempt.attempt_id)
            if attempt_jobs:
                return JobCreationResult(
                    stage_instance=stage,
                    attempt=attempt,
                    job=attempt_jobs[0],
                    created=False,
                )
        return None

    @staticmethod
    def _job_key(stage: StageInstance, attempt_number: int) -> str:
        return idempotency_key(
            "job",
            stage.run_id,
            stage.node_id,
            stage.logical_item_key,
            attempt_number,
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)


__all__ = ["JobCreationError", "JobCreationResult", "JobFactory"]
