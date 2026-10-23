from __future__ import annotations

from datetime import timedelta

from pipeline.contracts.execution import RetryPolicy
from pipeline.contracts.vocabularies import (
    AttemptStatus,
    FailureCategory,
    FailureCode,
    JobStatus,
    RecoveryAction,
    StageExecutionStatus,
)
from pipeline.execution.jobs import JobFactory
from pipeline.execution.leases import LeaseManager
from pipeline.execution.recovery import RecoveryManager
from pipeline.execution.retry import (
    FailureAction,
    bounded_backoff_seconds,
    classify_failure,
    default_retry_policy,
)
from pipeline.storage.repositories.control import RecoveryDecisionRepository
from pipeline.storage.repositories.execution import (
    JobRepository,
    StageAttemptRepository,
    StageInstanceRepository,
)


def _claimed(records, clock, *, lease_seconds: float = 30):
    job = JobFactory(records.database, clock=clock).create_job(records.stage).job
    manager = LeaseManager(records.database, lease_seconds=lease_seconds, clock=clock)
    claim = manager.claim_next("worker_a")
    assert claim is not None
    return job, claim


def _policy(**overrides) -> RetryPolicy:
    values = {
        "schema_version": "retry-policy.v1",
        "policy_id": "test_retry_v1",
        "max_attempts": 3,
        "initial_backoff_seconds": 4.0,
        "max_backoff_seconds": 10.0,
        "jitter_ratio": 0.5,
        "retryable_categories": [
            FailureCategory.TRANSIENT,
            FailureCategory.RATE_LIMIT,
        ],
    }
    values.update(overrides)
    return RetryPolicy(**values)


def test_transient_failure_schedules_new_attempt_with_backoff(records, clock) -> None:
    old_job, claim = _claimed(records, clock)
    recovery = RecoveryManager(
        records.database,
        retry_policy=_policy(),
        clock=clock,
    )

    outcome = recovery.handle_failure(
        claim,
        FailureCode.TRANSIENT_PROVIDER,
        failure_message="provider timeout",
        jitter_value=1.0,
    )

    assert outcome.accepted is True
    assert outcome.decision.action is FailureAction.RETRY
    assert outcome.decision.backoff_seconds == 6.0
    assert outcome.new_creation is not None
    new_attempt = outcome.new_creation.attempt
    new_job = outcome.new_creation.job
    assert new_attempt.attempt_number == 2
    assert new_job.status is JobStatus.READY
    assert new_job.available_at == clock.now + timedelta(seconds=6)
    assert outcome.job is not None
    assert outcome.job.status is JobStatus.RETRY
    assert outcome.attempt is not None
    assert outcome.attempt.attempt_id == claim.attempt.attempt_id
    assert outcome.attempt.status is AttemptStatus.FAILED
    assert outcome.attempt.failure_code is FailureCode.TRANSIENT_PROVIDER
    assert outcome.stage_instance is not None
    assert outcome.stage_instance.execution_status is StageExecutionStatus.WAITING_RETRY
    assert outcome.recovery_decision is not None
    assert outcome.recovery_decision.action is RecoveryAction.RETRY

    with records.database.connection() as connection:
        stored_old_job = JobRepository(connection).get(old_job.job_id)
        decisions = RecoveryDecisionRepository(connection).list_for_run(
            records.run.run_id
        )
    assert stored_old_job.status is JobStatus.RETRY
    assert len(decisions) == 1


def test_retry_is_not_claimed_before_available_at(records, clock) -> None:
    _, claim = _claimed(records, clock)
    recovery = RecoveryManager(records.database, retry_policy=_policy(), clock=clock)
    outcome = recovery.handle_failure(
        claim,
        FailureCode.RATE_LIMIT,
        jitter_value=0.0,
    )
    assert outcome.new_creation is not None

    manager = LeaseManager(records.database, lease_seconds=30, clock=clock)
    assert manager.claim_next("worker_b") is None

    clock.advance(seconds=outcome.decision.backoff_seconds)
    next_claim = manager.claim_next("worker_b")
    assert next_claim is not None
    assert next_claim.attempt.attempt_number == 2


def test_validation_failure_is_terminal_without_replacement_attempt(
    records, clock
) -> None:
    old_job, claim = _claimed(records, clock)
    recovery = RecoveryManager(records.database, clock=clock)

    outcome = recovery.handle_failure(
        claim,
        FailureCode.VALIDATION,
        failure_message="input manifest invalid",
    )

    assert outcome.accepted is True
    assert outcome.decision.action is FailureAction.FAIL
    assert outcome.decision.retryable is False
    assert outcome.new_creation is None
    assert outcome.job is not None
    assert outcome.job.status is JobStatus.DEAD_LETTER
    assert outcome.attempt is not None
    assert outcome.attempt.status is AttemptStatus.FAILED
    assert outcome.stage_instance is not None
    assert outcome.stage_instance.execution_status is StageExecutionStatus.FAILED
    assert outcome.recovery_decision is not None
    assert outcome.recovery_decision.action is RecoveryAction.FAIL
    with records.database.connection() as connection:
        assert JobRepository(connection).get(old_job.job_id).status is (
            JobStatus.DEAD_LETTER
        )
    assert len(records.attempts()) == 1
    assert len(records.jobs()) == 1


def test_unknown_outcome_goes_to_reconciliation(records, clock) -> None:
    old_job, claim = _claimed(records, clock)
    recovery = RecoveryManager(records.database, clock=clock)

    outcome = recovery.handle_failure(
        claim,
        FailureCode.TIMEOUT_UNKNOWN,
        failure_message="provider response ambiguous",
    )

    assert outcome.accepted is True
    assert outcome.decision.action is FailureAction.RECONCILE
    assert outcome.decision.backoff_seconds == 0
    assert outcome.new_creation is None
    assert outcome.job is not None
    assert outcome.job.status is JobStatus.DEAD_LETTER
    assert outcome.attempt is not None
    assert outcome.attempt.status is AttemptStatus.UNKNOWN
    assert outcome.stage_instance is not None
    assert outcome.stage_instance.execution_status is StageExecutionStatus.UNKNOWN
    assert outcome.recovery_decision is not None
    assert outcome.recovery_decision.action is RecoveryAction.RECONCILE
    with records.database.connection() as connection:
        assert JobRepository(connection).get(old_job.job_id).status is (
            JobStatus.DEAD_LETTER
        )
    assert len(records.attempts()) == 1


def test_repeated_retryable_failure_waits_for_human(records, clock) -> None:
    _, claim = _claimed(records, clock)
    recovery = RecoveryManager(
        records.database,
        retry_policy=_policy(max_attempts=1),
        clock=clock,
    )

    outcome = recovery.handle_failure(claim, FailureCode.TRANSIENT_PROVIDER)

    assert outcome.decision.retry_exhausted is True
    assert outcome.decision.action is FailureAction.WAIT_HUMAN
    assert outcome.new_creation is None
    assert outcome.stage_instance is not None
    assert outcome.stage_instance.execution_status is StageExecutionStatus.WAITING_HUMAN
    assert outcome.recovery_decision is not None
    assert outcome.recovery_decision.action is RecoveryAction.WAIT_HUMAN


def test_stale_failure_report_cannot_mutate_new_owner(records, clock) -> None:
    old_job, first = _claimed(records, clock, lease_seconds=10)
    clock.advance(seconds=10)
    manager = LeaseManager(records.database, lease_seconds=30, clock=clock)
    second = manager.claim_next("worker_b")
    assert second is not None

    recovery = RecoveryManager(records.database, clock=clock)
    outcome = recovery.handle_failure(first, FailureCode.VALIDATION)

    assert outcome.accepted is False
    assert outcome.reason == "FENCING_TOKEN_MISMATCH"
    with records.database.connection() as connection:
        job = JobRepository(connection).get(old_job.job_id)
        attempt = StageAttemptRepository(connection).get(first.attempt.attempt_id)
        stage = StageInstanceRepository(connection).get(records.stage.stage_instance_id)
    assert job.status is JobStatus.CLAIMED
    assert job.claimed_by == "worker_b"
    assert job.fencing_token == 2
    assert attempt.status is AttemptStatus.CLAIMED
    assert stage.execution_status is StageExecutionStatus.CLAIMED


def test_backoff_is_bounded_and_deterministic() -> None:
    policy = default_retry_policy()
    first = bounded_backoff_seconds(
        4,
        initial_backoff_seconds=policy.initial_backoff_seconds,
        max_backoff_seconds=policy.max_backoff_seconds,
        jitter_ratio=policy.jitter_ratio,
    )
    second = bounded_backoff_seconds(
        4,
        initial_backoff_seconds=policy.initial_backoff_seconds,
        max_backoff_seconds=policy.max_backoff_seconds,
        jitter_ratio=policy.jitter_ratio,
    )
    high = bounded_backoff_seconds(
        30,
        initial_backoff_seconds=policy.initial_backoff_seconds,
        max_backoff_seconds=policy.max_backoff_seconds,
        jitter_ratio=policy.jitter_ratio,
        jitter_value=1.0,
    )

    assert first == second
    assert 0 <= first <= policy.max_backoff_seconds
    assert high <= policy.max_backoff_seconds
    decision = classify_failure(
        FailureCode.AUTHENTICATION,
        1,
        retry_policy=policy,
    )
    assert decision.action is FailureAction.FAIL
