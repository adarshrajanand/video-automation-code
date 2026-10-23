from __future__ import annotations

from datetime import timedelta

from pipeline.contracts.vocabularies import (
    AcceptanceStatus,
    AttemptStatus,
    FailureCode,
    JobStatus,
    RecoveryAction,
    StageExecutionStatus,
)
from pipeline.execution.jobs import JobFactory
from pipeline.execution.leases import (
    CompletionStatus,
    JobClaim,
    LeaseManager,
)
from pipeline.ids import idempotency_key
from pipeline.storage.repositories.control import RecoveryDecisionRepository
from pipeline.storage.repositories.execution import (
    JobRepository,
    LeaseRepository,
    StageAttemptRepository,
    StageInstanceRepository,
)


def _claim(records, clock, owner: str = "worker_a", lease_seconds: float = 30):
    job = JobFactory(records.database, clock=clock).create_job(records.stage).job
    manager = LeaseManager(records.database, lease_seconds=lease_seconds, clock=clock)
    claim = manager.claim_next(owner)
    assert claim is not None
    return job, manager, claim


def test_job_creation_is_idempotent(records, clock) -> None:
    factory = JobFactory(records.database, clock=clock)

    first = factory.create_job(records.stage)
    second = factory.create_job(records.stage)

    assert first.created is True
    assert second.created is False
    assert second.job.job_id == first.job.job_id
    assert second.attempt.attempt_id == first.attempt.attempt_id
    assert first.attempt.attempt_number == 1
    assert first.job.status is JobStatus.READY
    assert first.job.idempotency_key == idempotency_key(
        "job", records.run.run_id, "research", "episode", 1
    )
    assert len(records.attempts()) == 1
    assert len(records.jobs()) == 1


def test_explicit_retry_attempt_is_created_once(records, clock) -> None:
    factory = JobFactory(records.database, clock=clock)
    first = factory.create_job(records.stage)

    retry = factory.create_job(
        records.stage,
        attempt_number=2,
        input_artifact_ids=first.attempt.input_artifact_ids,
    )
    repeated = factory.create_job(records.stage, attempt_number=2)

    assert retry.created is True
    assert retry.attempt.attempt_number == 2
    assert repeated.created is False
    assert repeated.job.job_id == retry.job.job_id
    assert len(records.attempts()) == 2
    assert len(records.jobs()) == 2


def test_claim_renew_release_preserves_lease_history(records, clock) -> None:
    job, manager, claim = _claim(records, clock, lease_seconds=30)

    assert claim.fencing_token == 1
    assert claim.job.status is JobStatus.CLAIMED
    assert claim.attempt.status is AttemptStatus.CLAIMED
    assert claim.stage_instance.execution_status is StageExecutionStatus.CLAIMED
    assert claim.stage_instance.active_attempt_id == claim.attempt.attempt_id
    with records.database.connection() as connection:
        assert JobRepository(connection).get(job.job_id).delivery_count == 1

    clock.advance(seconds=10)
    renewed = manager.renew(claim, lease_seconds=30)
    assert renewed is not None
    assert renewed.lease.expires_at == clock.now + timedelta(seconds=30)
    assert renewed.lease.heartbeat_at == clock.now
    assert renewed.job.lease_expires_at == renewed.lease.expires_at
    assert renewed.attempt.lease_expires_at == renewed.lease.expires_at

    other_owner = JobClaim(
        job=renewed.job,
        attempt=renewed.attempt,
        stage_instance=renewed.stage_instance,
        lease=renewed.lease.model_copy(update={"owner_id": "worker_b"}),
    )
    assert manager.renew(other_owner) is None

    assert manager.release(renewed) is True
    assert records.reload_stage().execution_status is StageExecutionStatus.READY
    assert records.reload_stage().active_attempt_id is None
    with records.database.connection() as connection:
        released_job = JobRepository(connection).get(job.job_id)
        released_attempt = StageAttemptRepository(connection).get(
            claim.attempt.attempt_id
        )
        latest_lease = LeaseRepository(connection).latest_for_job(job.job_id)
    assert released_job.status is JobStatus.READY
    assert released_job.claimed_by is None
    assert released_attempt.status is AttemptStatus.CREATED
    assert released_attempt.worker_id is None
    assert latest_lease is not None
    assert latest_lease.fencing_token == 1
    assert manager.release(renewed) is False


def test_expired_lease_is_reclaimed_and_renewal_fails(records, clock) -> None:
    job, manager, first = _claim(records, clock, lease_seconds=10)
    clock.advance(seconds=10)

    assert manager.renew(first) is None
    second = manager.claim_next("worker_b", lease_seconds=10)

    assert second is not None
    assert second.job.job_id == job.job_id
    assert second.fencing_token == 2
    assert second.owner_id == "worker_b"
    assert second.job.delivery_count == 2
    assert second.job.claimed_by == "worker_b"
    with records.database.connection() as connection:
        latest = LeaseRepository(connection).latest_for_job(job.job_id)
        decisions = RecoveryDecisionRepository(connection).list_for_run(
            records.run.run_id
        )
    assert latest is not None
    assert latest.fencing_token == 2
    assert len(decisions) == 1
    assert decisions[0].action is RecoveryAction.RETRY
    assert decisions[0].reason_codes == ["LEASE_EXPIRED"]
    assert decisions[0].failed_attempt_id == first.attempt.attempt_id


def test_stale_completion_is_rejected_after_reclaim(records, clock) -> None:
    job, manager, first = _claim(records, clock, lease_seconds=10)
    clock.advance(seconds=10)
    second = manager.claim_next("worker_b", lease_seconds=30)
    assert second is not None

    stale = manager.complete_success(
        first,
        output_artifact_ids=["artifact_stale"],
    )

    assert stale.status is CompletionStatus.REJECTED
    with records.database.connection() as connection:
        current_job = JobRepository(connection).get(job.job_id)
        current_attempt = StageAttemptRepository(connection).get(
            first.attempt.attempt_id
        )
        current_stage = StageInstanceRepository(connection).get(
            records.stage.stage_instance_id
        )
    assert current_job.status is JobStatus.CLAIMED
    assert current_job.claimed_by == "worker_b"
    assert current_job.fencing_token == 2
    assert current_attempt.status is AttemptStatus.CLAIMED
    assert current_stage.execution_status is StageExecutionStatus.CLAIMED
    assert current_attempt.output_artifact_ids == []

    completed = manager.complete_success(
        second,
        output_artifact_ids=["artifact_final"],
    )

    assert completed.status is CompletionStatus.COMPLETED
    assert completed.job is not None
    assert completed.job.status is JobStatus.ACKED
    assert completed.attempt is not None
    assert completed.attempt.status is AttemptStatus.SUCCEEDED
    assert completed.attempt.output_artifact_ids == ["artifact_final"]
    assert completed.stage_instance is not None
    assert completed.stage_instance.execution_status is StageExecutionStatus.SUCCEEDED
    assert completed.stage_instance.acceptance_status is AcceptanceStatus.NOT_REQUIRED

    duplicate = manager.complete_success(
        second,
        output_artifact_ids=["artifact_second_effect"],
    )
    assert duplicate.status is CompletionStatus.ALREADY_COMPLETED
    with records.database.connection() as connection:
        final_attempt = StageAttemptRepository(connection).get(first.attempt.attempt_id)
    assert final_attempt.output_artifact_ids == ["artifact_final"]


def test_completion_after_own_lease_expires_is_rejected(records, clock) -> None:
    _, manager, claim = _claim(records, clock, lease_seconds=10)
    clock.advance(seconds=10)

    completion = manager.complete_success(claim)

    assert completion.status is CompletionStatus.REJECTED
    assert completion.reason == "LEASE_EXPIRED"
    assert records.reload_stage().execution_status is StageExecutionStatus.CLAIMED


def test_success_clears_failure_fields(records, clock) -> None:
    _, manager, claim = _claim(records, clock)
    manager.start(claim)

    completion = manager.complete_success(claim)

    assert completion.status is CompletionStatus.COMPLETED
    assert completion.attempt is not None
    assert completion.attempt.failure_code is None
    assert completion.attempt.failure_code is not FailureCode.INTERNAL
