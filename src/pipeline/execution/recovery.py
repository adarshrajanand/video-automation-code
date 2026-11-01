"""Recovery decisions for failed attempts and expired leases."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pipeline.contracts.execution import (
    RecoveryDecision,
    RecoveryPolicy,
    RetryPolicy,
    StageAttempt,
    StageInstance,
)
from pipeline.contracts.jobs import Job
from pipeline.contracts.vocabularies import (
    AttemptStatus,
    FailureCode,
    JobStatus,
    RecoveryAction,
    StageExecutionStatus,
)
from pipeline.execution.jobs import JobCreationResult, JobFactory
from pipeline.execution.leases import JobClaim, verify_live_claim
from pipeline.execution.retry import (
    FailureAction,
    RetryDecision,
    classify_failure,
    default_recovery_policy,
    default_retry_policy,
)
from pipeline.ids import deterministic_id
from pipeline.storage.database import Database
from pipeline.storage.repositories.control import RecoveryDecisionRepository
from pipeline.storage.repositories.execution import (
    JobRepository,
    StageAttemptRepository,
    StageInstanceRepository,
)


@dataclass(frozen=True, slots=True)
class RecoveryOutcome:
    """One classified failure and the durable transition it produced."""

    accepted: bool
    decision: RetryDecision
    claim: JobClaim
    recovery_decision: RecoveryDecision | None = None
    job: Job | None = None
    attempt: StageAttempt | None = None
    stage_instance: StageInstance | None = None
    new_creation: JobCreationResult | None = None
    reason: str | None = None


class RecoveryManager:
    """Apply retry, reconciliation, review, and terminal-failure policy.

    This module never repairs artifacts or evaluates quality. It records the
    control-plane decision and preserves the failed attempt as history.
    """

    def __init__(
        self,
        database: Database,
        *,
        retry_policy: RetryPolicy | None = None,
        recovery_policy: RecoveryPolicy | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.database = database
        self.retry_policy = retry_policy or default_retry_policy()
        self.recovery_policy = recovery_policy or default_recovery_policy()
        self._clock = clock or _utc_now
        self._factory = JobFactory(database, clock=self._clock)

    def handle_failure(
        self,
        claim: JobClaim,
        failure_code: FailureCode,
        *,
        failure_message: str | None = None,
        jitter_value: float | None = None,
    ) -> RecoveryOutcome:
        """Classify and durably apply one failed claim.

        A stale worker whose lease was reclaimed receives ``accepted=False`` and
        cannot mutate the new owner's job, attempt, or stage state.
        """

        now = self._clock()
        decision = classify_failure(
            failure_code,
            claim.attempt.attempt_number,
            retry_policy=self.retry_policy,
            recovery_policy=self.recovery_policy,
            jitter_value=jitter_value,
        )
        with self.database.transaction(immediate=True) as connection:
            check = verify_live_claim(connection, claim, now)
            if not check.live or check.job is None or check.attempt is None:
                return RecoveryOutcome(
                    accepted=False,
                    decision=decision,
                    claim=claim,
                    reason=check.reason or "STALE_CLAIM",
                )
            assert check.stage_instance is not None
            return self._apply_locked(
                connection,
                claim,
                check.job,
                check.attempt,
                check.stage_instance,
                decision,
                failure_message=failure_message,
                now=now,
            )

    def _apply_locked(
        self,
        connection: sqlite3.Connection,
        claim: JobClaim,
        job: Job,
        attempt: StageAttempt,
        stage: StageInstance,
        decision: RetryDecision,
        *,
        failure_message: str | None,
        now: datetime,
    ) -> RecoveryOutcome:
        action = decision.action
        attempt_status = (
            AttemptStatus.UNKNOWN
            if action is FailureAction.RECONCILE
            else AttemptStatus.FAILED
        )
        failed_attempt = attempt.model_copy(
            update={
                "status": attempt_status,
                "worker_id": None,
                "lease_expires_at": None,
                "finished_at": now,
                "failure_code": decision.failure_code,
                "failure_message": failure_message or None,
            }
        )
        StageAttemptRepository(connection).update(failed_attempt)

        if action is FailureAction.RETRY:
            retry_job = job.model_copy(
                update={
                    "status": JobStatus.RETRY,
                    "claimed_by": None,
                    "lease_expires_at": None,
                }
            )
            JobRepository(connection).update(retry_job)
            ready_stage = stage.model_copy(
                update={
                    "execution_status": StageExecutionStatus.READY,
                    "active_attempt_id": None,
                    "updated_at": now,
                }
            )
            StageInstanceRepository(connection).update(ready_stage)
            creation = self._factory.create_job(
                ready_stage,
                queue_name=job.queue_name,
                input_artifact_ids=attempt.input_artifact_ids,
                attempt_number=attempt.attempt_number + 1,
                available_at=now + timedelta(seconds=decision.backoff_seconds),
                connection=connection,
            )
            waiting_stage = ready_stage.model_copy(
                update={
                    "execution_status": StageExecutionStatus.WAITING_RETRY,
                    "active_attempt_id": None,
                    "updated_at": now,
                }
            )
            StageInstanceRepository(connection).update(waiting_stage)
            recovery_decision = self._record_decision(
                connection,
                stage=stage,
                attempt=failed_attempt,
                decision=decision,
                action=RecoveryAction.RETRY,
                now=now,
            )
            return RecoveryOutcome(
                accepted=True,
                decision=decision,
                claim=claim,
                recovery_decision=recovery_decision,
                job=retry_job,
                attempt=failed_attempt,
                stage_instance=waiting_stage,
                new_creation=creation,
            )

        terminal_job = job.model_copy(
            update={
                "status": JobStatus.DEAD_LETTER,
                "claimed_by": None,
                "lease_expires_at": None,
            }
        )
        JobRepository(connection).update(terminal_job)

        if action is FailureAction.RECONCILE:
            stage_status = StageExecutionStatus.UNKNOWN
            recovery_action = RecoveryAction.RECONCILE
        elif action is FailureAction.WAIT_HUMAN:
            stage_status = StageExecutionStatus.WAITING_HUMAN
            recovery_action = RecoveryAction.WAIT_HUMAN
        else:
            stage_status = StageExecutionStatus.FAILED
            recovery_action = RecoveryAction.FAIL

        terminal_stage = stage.model_copy(
            update={
                "execution_status": stage_status,
                "active_attempt_id": None,
                "updated_at": now,
            }
        )
        StageInstanceRepository(connection).update(terminal_stage)
        recovery_decision = self._record_decision(
            connection,
            stage=stage,
            attempt=failed_attempt,
            decision=decision,
            action=recovery_action,
            now=now,
        )
        return RecoveryOutcome(
            accepted=True,
            decision=decision,
            claim=claim,
            recovery_decision=recovery_decision,
            job=terminal_job,
            attempt=failed_attempt,
            stage_instance=terminal_stage,
        )

    def _record_decision(
        self,
        connection: sqlite3.Connection,
        *,
        stage: StageInstance,
        attempt: StageAttempt,
        decision: RetryDecision,
        action: RecoveryAction,
        now: datetime,
    ) -> RecoveryDecision:
        reason_codes = list(
            dict.fromkeys([decision.failure_code.value, decision.reason])
        )
        recovery_decision = RecoveryDecision(
            schema_version="recovery-decision.v1",
            recovery_decision_id=deterministic_id(
                "recovery",
                "failure",
                stage.stage_instance_id,
                attempt.attempt_id,
                action.value,
            ),
            run_id=stage.run_id,
            failed_attempt_id=attempt.attempt_id,
            action=action,
            target_stage_instance_ids=[stage.stage_instance_id],
            reason_codes=reason_codes,
            created_at=now,
        )
        repository = RecoveryDecisionRepository(connection)
        existing = repository.get_optional(recovery_decision.recovery_decision_id)
        if existing is not None:
            return existing
        return repository.insert(recovery_decision)


def _utc_now() -> datetime:
    return datetime.now(UTC)


__all__ = ["RecoveryManager", "RecoveryOutcome"]
