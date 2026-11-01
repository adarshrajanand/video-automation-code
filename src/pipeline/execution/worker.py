"""Narrow worker loop primitives around claim, handler, and recovery."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from pipeline.contracts.execution import RecoveryPolicy, RetryPolicy
from pipeline.contracts.vocabularies import FailureCode
from pipeline.execution.leases import (
    CompletionResult,
    CompletionStatus,
    JobClaim,
    LeaseManager,
)
from pipeline.execution.recovery import RecoveryManager, RecoveryOutcome
from pipeline.execution.retry import FailureAction
from pipeline.storage.database import Database


@dataclass(frozen=True, slots=True)
class JobHandlerResult:
    """Normalized success/failure returned by a stage job handler."""

    succeeded: bool
    output_artifact_ids: tuple[str, ...] = ()
    failure_code: FailureCode | None = None
    failure_message: str | None = None

    def __post_init__(self) -> None:
        if not self.succeeded and self.failure_code is None:
            raise ValueError("a failed job result requires a failure_code")
        if self.succeeded and self.failure_code is not None:
            raise ValueError("a succeeded job result must not carry a failure_code")


class JobHandler(Protocol):
    """Narrow stage execution boundary; FV-05 supplies test/no-op handlers."""

    def __call__(self, claim: JobClaim) -> JobHandlerResult: ...


class NoopJobHandler:
    """Safe smoke handler that acknowledges work without producing artifacts."""

    def __call__(self, claim: JobClaim) -> JobHandlerResult:
        del claim
        return JobHandlerResult(succeeded=True)


class WorkerRunStatus(StrEnum):
    """Outcome of one worker polling iteration."""

    IDLE = "IDLE"
    COMPLETED = "COMPLETED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    RECONCILED = "RECONCILED"
    WAITING_HUMAN = "WAITING_HUMAN"
    FAILED = "FAILED"
    STALE = "STALE"


@dataclass(frozen=True, slots=True)
class WorkerRunResult:
    """One claim/handler/completion/recovery cycle."""

    status: WorkerRunStatus
    claim: JobClaim | None = None
    completion: CompletionResult | None = None
    recovery: RecoveryOutcome | None = None
    error: str | None = field(default=None)


class WorkerLoop:
    """Claim one job, run a narrow handler, and commit a fenced result.

    The loop is deliberately a primitive rather than a stage implementation. It
    does not select capabilities, call providers, write artifacts, or evaluate
    quality. Those belong to later work packages.
    """

    def __init__(
        self,
        database: Database,
        *,
        owner_id: str = "worker_local_01",
        handler: JobHandler | None = None,
        queue_name: str | None = None,
        lease_seconds: float = 60.0,
        retry_policy: RetryPolicy | None = None,
        recovery_policy: RecoveryPolicy | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not owner_id:
            raise ValueError("owner_id must be non-empty")
        self.database = database
        self.owner_id = owner_id
        self.handler = handler or NoopJobHandler()
        self.queue_name = queue_name
        self.leases = LeaseManager(
            database,
            lease_seconds=lease_seconds,
            clock=clock,
        )
        self.recovery = RecoveryManager(
            database,
            retry_policy=retry_policy,
            recovery_policy=recovery_policy,
            clock=clock,
        )

    def run_once(self) -> WorkerRunResult:
        """Process at most one available job."""

        claim = self.leases.claim_next(
            self.owner_id,
            queue_name=self.queue_name,
        )
        if claim is None:
            return WorkerRunResult(status=WorkerRunStatus.IDLE)

        running = self.leases.start(claim)
        if running is None:
            return WorkerRunResult(status=WorkerRunStatus.STALE, claim=claim)

        try:
            outcome = self.handler(running)
        except Exception as error:
            outcome = JobHandlerResult(
                succeeded=False,
                failure_code=FailureCode.INTERNAL,
                failure_message=f"{type(error).__name__}: {error}",
            )

        if outcome.succeeded:
            completion = self.leases.complete_success(
                running,
                output_artifact_ids=outcome.output_artifact_ids,
            )
            if completion.status is CompletionStatus.REJECTED:
                return WorkerRunResult(
                    status=WorkerRunStatus.STALE,
                    claim=running,
                    completion=completion,
                )
            return WorkerRunResult(
                status=WorkerRunStatus.COMPLETED,
                claim=running,
                completion=completion,
            )

        assert outcome.failure_code is not None
        recovery = self.recovery.handle_failure(
            running,
            outcome.failure_code,
            failure_message=outcome.failure_message,
        )
        return WorkerRunResult(
            status=_status_for_recovery(recovery),
            claim=running,
            recovery=recovery,
        )


def _status_for_recovery(recovery: RecoveryOutcome) -> WorkerRunStatus:
    if not recovery.accepted:
        return WorkerRunStatus.STALE
    return {
        FailureAction.RETRY: WorkerRunStatus.RETRY_SCHEDULED,
        FailureAction.RECONCILE: WorkerRunStatus.RECONCILED,
        FailureAction.WAIT_HUMAN: WorkerRunStatus.WAITING_HUMAN,
        FailureAction.FAIL: WorkerRunStatus.FAILED,
    }[recovery.decision.action]


def _utc_now() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "JobHandler",
    "JobHandlerResult",
    "NoopJobHandler",
    "WorkerLoop",
    "WorkerRunResult",
    "WorkerRunStatus",
]
