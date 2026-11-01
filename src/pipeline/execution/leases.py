"""Job claims, fencing leases, renewal, release, and fenced completion.

The ``leases`` table is authoritative for ownership. ``Job`` and
``StageAttempt`` carry a fencing-token projection for audit and inspection, but
every state transition re-reads the active lease term and compares owner, token,
expiry, and job status inside one ``BEGIN IMMEDIATE`` transaction.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pipeline.contracts.execution import RecoveryDecision, StageAttempt, StageInstance
from pipeline.contracts.jobs import Job, Lease
from pipeline.contracts.vocabularies import (
    AcceptanceStatus,
    AttemptStatus,
    JobStatus,
    RecoveryAction,
    StageExecutionStatus,
)
from pipeline.fingerprints import canonical_datetime
from pipeline.ids import deterministic_id
from pipeline.storage.database import Database
from pipeline.storage.repositories.control import RecoveryDecisionRepository
from pipeline.storage.repositories.execution import (
    JobRepository,
    LeaseRepository,
    StageAttemptRepository,
    StageInstanceRepository,
)

DEFAULT_LEASE_SECONDS = 60.0


class CompletionStatus(StrEnum):
    """Outcome of a fenced result completion attempt."""

    COMPLETED = "COMPLETED"
    ALREADY_COMPLETED = "ALREADY_COMPLETED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class JobClaim:
    """The durable ownership facts handed to one worker."""

    job: Job
    attempt: StageAttempt
    stage_instance: StageInstance
    lease: Lease

    @property
    def job_id(self) -> str:
        return self.job.job_id

    @property
    def owner_id(self) -> str:
        return self.lease.owner_id

    @property
    def fencing_token(self) -> int:
        return self.lease.fencing_token


@dataclass(frozen=True, slots=True)
class LeaseCheck:
    """Result of re-reading a claim inside a transaction."""

    job: Job | None = None
    attempt: StageAttempt | None = None
    stage_instance: StageInstance | None = None
    lease: Lease | None = None
    reason: str | None = None

    @property
    def live(self) -> bool:
        return self.reason is None and self.lease is not None


@dataclass(frozen=True, slots=True)
class CompletionResult:
    """Outcome of a worker's success commit."""

    status: CompletionStatus
    claim: JobClaim
    reason: str | None = None
    job: Job | None = None
    attempt: StageAttempt | None = None
    stage_instance: StageInstance | None = None


@dataclass(frozen=True, slots=True)
class ExpiredLeaseRecovery:
    """Audit summary for one job reclaimed after lease expiry."""

    job_id: str
    attempt_id: str
    stage_instance_id: str
    previous_owner_id: str | None
    previous_fencing_token: int | None
    recovery_decision_id: str


def verify_live_claim(
    connection: sqlite3.Connection,
    claim: JobClaim,
    now: datetime,
) -> LeaseCheck:
    """Re-read and validate a claim's ownership term without mutating state."""

    jobs = JobRepository(connection)
    job = jobs.get(claim.job_id)
    latest = LeaseRepository(connection).latest_for_job(claim.job_id)
    if latest is None:
        return LeaseCheck(job=job, reason="LEASE_MISSING")
    if job.status is JobStatus.ACKED:
        return LeaseCheck(job=job, lease=latest, reason="JOB_ALREADY_ACKED")
    if job.status is not JobStatus.CLAIMED:
        return LeaseCheck(job=job, lease=latest, reason="JOB_NOT_CLAIMED")
    if latest.fencing_token != claim.fencing_token:
        return LeaseCheck(job=job, lease=latest, reason="FENCING_TOKEN_MISMATCH")
    if latest.owner_id != claim.owner_id or job.claimed_by != claim.owner_id:
        return LeaseCheck(job=job, lease=latest, reason="LEASE_OWNER_MISMATCH")
    if now >= latest.expires_at:
        return LeaseCheck(job=job, lease=latest, reason="LEASE_EXPIRED")
    if job.lease_expires_at is None or now >= job.lease_expires_at:
        return LeaseCheck(job=job, lease=latest, reason="LEASE_EXPIRED")

    attempt = StageAttemptRepository(connection).get(job.attempt_id)
    stage = StageInstanceRepository(connection).get(attempt.stage_instance_id)
    if attempt.fencing_token not in (None, claim.fencing_token):
        return LeaseCheck(
            job=job,
            attempt=attempt,
            stage_instance=stage,
            lease=latest,
            reason="ATTEMPT_FENCING_TOKEN_MISMATCH",
        )
    return LeaseCheck(
        job=job,
        attempt=attempt,
        stage_instance=stage,
        lease=latest,
        reason=None,
    )


class LeaseManager:
    """Transactional job claim, lease, and completion control plane."""

    def __init__(
        self,
        database: Database,
        *,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self.database = database
        self.lease_seconds = float(lease_seconds)
        self._clock = clock or _utc_now

    def claim_next(
        self,
        owner_id: str,
        *,
        queue_name: str | None = None,
        lease_seconds: float | None = None,
    ) -> JobClaim | None:
        """Atomically claim the next eligible job, recovering expired leases."""

        now = self._clock()
        duration = self._duration(lease_seconds)
        with self.database.transaction(immediate=True) as connection:
            self._recover_expired_locked(connection, now)
            job_id = self._next_ready_id(connection, now, queue_name)
            if job_id is None:
                return None
            job = JobRepository(connection).get(job_id)
            return self._claim_locked(connection, job, owner_id, now, duration)

    def claim_job(
        self,
        job_id: str,
        owner_id: str,
        *,
        lease_seconds: float | None = None,
    ) -> JobClaim | None:
        """Claim one named job if it is READY and available."""

        now = self._clock()
        duration = self._duration(lease_seconds)
        with self.database.transaction(immediate=True) as connection:
            self._recover_expired_locked(connection, now)
            job = JobRepository(connection).get(job_id)
            eligible = job.status is JobStatus.READY and job.available_at <= now
            if not eligible:
                return None
            return self._claim_locked(connection, job, owner_id, now, duration)

    def renew(
        self,
        claim: JobClaim,
        *,
        lease_seconds: float | None = None,
    ) -> JobClaim | None:
        """Extend only the caller's own live lease; stale/expired claims fail."""

        now = self._clock()
        duration = self._duration(lease_seconds)
        with self.database.transaction(immediate=True) as connection:
            check = verify_live_claim(connection, claim, now)
            if not check.live or check.job is None or check.lease is None:
                return None
            expires_at = now + timedelta(seconds=duration)
            lease = check.lease.model_copy(
                update={"expires_at": expires_at, "heartbeat_at": now}
            )
            LeaseRepository(connection).update(lease)
            job = check.job.model_copy(update={"lease_expires_at": expires_at})
            JobRepository(connection).update(job)
            attempt = check.attempt
            assert attempt is not None
            attempt = attempt.model_copy(update={"lease_expires_at": expires_at})
            StageAttemptRepository(connection).update(attempt)
            stage = check.stage_instance
            assert stage is not None
            return JobClaim(
                job=job,
                attempt=attempt,
                stage_instance=stage,
                lease=lease,
            )

    def start(self, claim: JobClaim) -> JobClaim | None:
        """Mark a claimed attempt RUNNING after the worker has begun."""

        now = self._clock()
        with self.database.transaction(immediate=True) as connection:
            check = verify_live_claim(connection, claim, now)
            if not check.live or check.attempt is None or check.stage_instance is None:
                return None
            attempt = check.attempt.model_copy(update={"status": AttemptStatus.RUNNING})
            StageAttemptRepository(connection).update(attempt)
            stage = check.stage_instance.model_copy(
                update={
                    "execution_status": StageExecutionStatus.RUNNING,
                    "updated_at": now,
                }
            )
            StageInstanceRepository(connection).update(stage)
            assert check.job is not None and check.lease is not None
            return JobClaim(
                job=check.job,
                attempt=attempt,
                stage_instance=stage,
                lease=check.lease,
            )

    def release(self, claim: JobClaim) -> bool:
        """Voluntarily return a live claim to READY, preserving lease history."""

        now = self._clock()
        with self.database.transaction(immediate=True) as connection:
            check = verify_live_claim(connection, claim, now)
            if not check.live or check.attempt is None or check.stage_instance is None:
                return False
            assert check.job is not None
            self._return_to_ready(
                connection,
                check.job,
                check.attempt,
                check.stage_instance,
                now,
            )
            return True

    def complete_success(
        self,
        claim: JobClaim,
        *,
        output_artifact_ids: Sequence[str] = (),
    ) -> CompletionResult:
        """Commit success with a compare-and-set on job ID and fencing token."""

        now = self._clock()
        with self.database.transaction(immediate=True) as connection:
            jobs = JobRepository(connection)
            job = jobs.get(claim.job_id)
            latest = LeaseRepository(connection).latest_for_job(claim.job_id)
            if (
                job.status is JobStatus.ACKED
                and job.fencing_token == claim.fencing_token
                and latest is not None
                and latest.fencing_token == claim.fencing_token
                and latest.owner_id == claim.owner_id
            ):
                return CompletionResult(
                    status=CompletionStatus.ALREADY_COMPLETED,
                    claim=claim,
                    job=job,
                )

            check = verify_live_claim(connection, claim, now)
            if not check.live or check.attempt is None or check.stage_instance is None:
                return CompletionResult(
                    status=CompletionStatus.REJECTED,
                    claim=claim,
                    reason=check.reason or "STALE_CLAIM",
                )

            assert check.job is not None
            attempt = check.attempt.model_copy(
                update={
                    "status": AttemptStatus.SUCCEEDED,
                    "output_artifact_ids": list(dict.fromkeys(output_artifact_ids)),
                    "worker_id": claim.owner_id,
                    "lease_expires_at": None,
                    "fencing_token": claim.fencing_token,
                    "finished_at": now,
                    "failure_code": None,
                    "failure_message": None,
                }
            )
            StageAttemptRepository(connection).update(attempt)
            stage = check.stage_instance.model_copy(
                update={
                    "execution_status": StageExecutionStatus.SUCCEEDED,
                    "acceptance_status": (
                        AcceptanceStatus.PENDING
                        if check.stage_instance.quality_gate_id is not None
                        else AcceptanceStatus.NOT_REQUIRED
                    ),
                    "active_attempt_id": attempt.attempt_id,
                    "updated_at": now,
                }
            )
            StageInstanceRepository(connection).update(stage)
            job = check.job.model_copy(
                update={
                    "status": JobStatus.ACKED,
                    "claimed_by": None,
                    "lease_expires_at": None,
                }
            )
            jobs.update(job)
            return CompletionResult(
                status=CompletionStatus.COMPLETED,
                claim=claim,
                job=job,
                attempt=attempt,
                stage_instance=stage,
            )

    def recover_expired(self) -> list[ExpiredLeaseRecovery]:
        """Return expired claims to READY and record a durable recovery audit."""

        now = self._clock()
        with self.database.transaction(immediate=True) as connection:
            return self._recover_expired_locked(connection, now)

    def _claim_locked(
        self,
        connection: sqlite3.Connection,
        job: Job,
        owner_id: str,
        now: datetime,
        duration: float,
    ) -> JobClaim:
        attempts = StageAttemptRepository(connection)
        stages = StageInstanceRepository(connection)
        leases = LeaseRepository(connection)
        jobs = JobRepository(connection)

        attempt = attempts.get(job.attempt_id)
        stage = stages.get(attempt.stage_instance_id)
        latest = leases.latest_for_job(job.job_id)
        token = (latest.fencing_token if latest is not None else 0) + 1
        expires_at = now + timedelta(seconds=duration)

        lease = Lease(
            schema_version="lease.v1",
            job_id=job.job_id,
            owner_id=owner_id,
            fencing_token=token,
            acquired_at=now,
            expires_at=expires_at,
            heartbeat_at=now,
        )
        leases.insert(lease)

        attempt = attempt.model_copy(
            update={
                "status": AttemptStatus.CLAIMED,
                "worker_id": owner_id,
                "lease_expires_at": expires_at,
                "fencing_token": token,
                "started_at": attempt.started_at or now,
            }
        )
        attempts.update(attempt)
        stage = stage.model_copy(
            update={
                "execution_status": StageExecutionStatus.CLAIMED,
                "active_attempt_id": attempt.attempt_id,
                "updated_at": now,
            }
        )
        stages.update(stage)
        job = job.model_copy(
            update={
                "status": JobStatus.CLAIMED,
                "claimed_by": owner_id,
                "lease_expires_at": expires_at,
                "delivery_count": job.delivery_count + 1,
                "fencing_token": token,
            }
        )
        jobs.update(job)
        return JobClaim(
            job=job,
            attempt=attempt,
            stage_instance=stage,
            lease=lease,
        )

    def _recover_expired_locked(
        self,
        connection: sqlite3.Connection,
        now: datetime,
    ) -> list[ExpiredLeaseRecovery]:
        jobs = JobRepository(connection)
        rows = connection.execute(
            "SELECT job_id FROM jobs WHERE status = ? "
            "AND lease_expires_at IS NOT NULL "
            "AND julianday(lease_expires_at) <= julianday(?) "
            "ORDER BY julianday(lease_expires_at), job_id",
            (JobStatus.CLAIMED.value, canonical_datetime(now)),
        ).fetchall()
        recovered: list[ExpiredLeaseRecovery] = []
        for row in rows:
            job = jobs.get(str(row[0]))
            attempt = StageAttemptRepository(connection).get(job.attempt_id)
            stage = StageInstanceRepository(connection).get(attempt.stage_instance_id)
            lease = LeaseRepository(connection).latest_for_job(job.job_id)
            decision_id = deterministic_id(
                "recovery",
                "lease_expired",
                job.job_id,
                lease.fencing_token if lease is not None else 0,
            )
            decisions = RecoveryDecisionRepository(connection)
            if decisions.get_optional(decision_id) is None:
                decisions.insert(
                    RecoveryDecision(
                        schema_version="recovery-decision.v1",
                        recovery_decision_id=decision_id,
                        run_id=stage.run_id,
                        failed_attempt_id=attempt.attempt_id,
                        action=RecoveryAction.RETRY,
                        target_stage_instance_ids=[stage.stage_instance_id],
                        reason_codes=["LEASE_EXPIRED"],
                        created_at=now,
                    )
                )
            self._return_to_ready(connection, job, attempt, stage, now)
            recovered.append(
                ExpiredLeaseRecovery(
                    job_id=job.job_id,
                    attempt_id=attempt.attempt_id,
                    stage_instance_id=stage.stage_instance_id,
                    previous_owner_id=job.claimed_by,
                    previous_fencing_token=job.fencing_token,
                    recovery_decision_id=decision_id,
                )
            )
        return recovered

    def _return_to_ready(
        self,
        connection: sqlite3.Connection,
        job: Job,
        attempt: StageAttempt,
        stage: StageInstance,
        now: datetime,
    ) -> None:
        StageInstanceRepository(connection).update(
            stage.model_copy(
                update={
                    "execution_status": StageExecutionStatus.READY,
                    "active_attempt_id": None,
                    "updated_at": now,
                }
            )
        )
        StageAttemptRepository(connection).update(
            attempt.model_copy(
                update={
                    "status": AttemptStatus.CREATED,
                    "worker_id": None,
                    "lease_expires_at": None,
                }
            )
        )
        JobRepository(connection).update(
            job.model_copy(
                update={
                    "status": JobStatus.READY,
                    "available_at": now,
                    "claimed_by": None,
                    "lease_expires_at": None,
                }
            )
        )

    @staticmethod
    def _next_ready_id(
        connection: sqlite3.Connection,
        now: datetime,
        queue_name: str | None,
    ) -> str | None:
        if queue_name is None:
            row = connection.execute(
                "SELECT job_id FROM jobs WHERE status = ? "
                "AND julianday(available_at) <= julianday(?) "
                "ORDER BY julianday(available_at), job_id LIMIT 1",
                (JobStatus.READY.value, canonical_datetime(now)),
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT job_id FROM jobs WHERE status = ? AND queue_name = ? "
                "AND julianday(available_at) <= julianday(?) "
                "ORDER BY julianday(available_at), job_id LIMIT 1",
                (
                    JobStatus.READY.value,
                    queue_name,
                    canonical_datetime(now),
                ),
            ).fetchone()
        return None if row is None else str(row[0])

    def _duration(self, lease_seconds: float | None) -> float:
        duration = self.lease_seconds if lease_seconds is None else lease_seconds
        if duration <= 0:
            raise ValueError("lease_seconds must be positive")
        return float(duration)


def _utc_now() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "DEFAULT_LEASE_SECONDS",
    "CompletionResult",
    "CompletionStatus",
    "ExpiredLeaseRecovery",
    "JobClaim",
    "LeaseCheck",
    "LeaseManager",
    "verify_live_claim",
]
