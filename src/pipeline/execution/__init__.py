"""Durable execution spine: outbox, dispatch, inbox, jobs, leases, and recovery.

FV-05 is local and in-process. None of these helpers contact an external broker,
provider, or network service. Durable SQLite rows are the only source of truth.
"""

from pipeline.execution.dispatcher import (
    DEFAULT_MAX_DELIVERY_ATTEMPTS,
    DEFAULT_OUTBOX_LEASE_SECONDS,
    DeliveryResult,
    DeliveryStatus,
    DispatchResult,
    NoopOutboxHandler,
    OutboxDeliveryHandler,
    OutboxDispatcher,
)
from pipeline.execution.events import EventOutbox, utc_now
from pipeline.execution.inbox import InboxConsumer, InboxEffect, InboxProcessResult
from pipeline.execution.jobs import JobCreationError, JobCreationResult, JobFactory
from pipeline.execution.leases import (
    DEFAULT_LEASE_SECONDS,
    CompletionResult,
    CompletionStatus,
    ExpiredLeaseRecovery,
    JobClaim,
    LeaseCheck,
    LeaseManager,
    verify_live_claim,
)
from pipeline.execution.recovery import RecoveryManager, RecoveryOutcome
from pipeline.execution.retry import (
    DEFAULT_RECOVERY_POLICY_ID,
    DEFAULT_RETRY_POLICY_ID,
    FailureAction,
    RetryDecision,
    bounded_backoff_seconds,
    classify_failure,
    default_recovery_policy,
    default_retry_policy,
    deterministic_jitter,
    retry_backoff_seconds,
)
from pipeline.execution.worker import (
    JobHandler,
    JobHandlerResult,
    NoopJobHandler,
    WorkerLoop,
    WorkerRunResult,
    WorkerRunStatus,
)

__all__ = [
    "DEFAULT_LEASE_SECONDS",
    "DEFAULT_MAX_DELIVERY_ATTEMPTS",
    "DEFAULT_OUTBOX_LEASE_SECONDS",
    "DEFAULT_RECOVERY_POLICY_ID",
    "DEFAULT_RETRY_POLICY_ID",
    "CompletionResult",
    "CompletionStatus",
    "DeliveryResult",
    "DeliveryStatus",
    "DispatchResult",
    "EventOutbox",
    "ExpiredLeaseRecovery",
    "FailureAction",
    "InboxConsumer",
    "InboxEffect",
    "InboxProcessResult",
    "JobClaim",
    "JobCreationError",
    "JobCreationResult",
    "JobFactory",
    "JobHandler",
    "JobHandlerResult",
    "LeaseCheck",
    "LeaseManager",
    "NoopJobHandler",
    "NoopOutboxHandler",
    "OutboxDeliveryHandler",
    "OutboxDispatcher",
    "RecoveryManager",
    "RecoveryOutcome",
    "RetryDecision",
    "WorkerLoop",
    "WorkerRunResult",
    "WorkerRunStatus",
    "bounded_backoff_seconds",
    "classify_failure",
    "default_recovery_policy",
    "default_retry_policy",
    "deterministic_jitter",
    "retry_backoff_seconds",
    "utc_now",
    "verify_live_claim",
]
