"""Durable execution spine: outbox, dispatch, inbox, jobs, leases, and recovery.

FV-05 is local and in-process. None of these helpers contact an external broker,
provider, or network service. Durable SQLite rows are the only source of truth.

Architecture:
The execution spine provides the durable runtime for the video pipeline.
All components are in-process and use SQLite as the sole source of truth.
No external message brokers (Kafka, RabbitMQ), no Redis, no external services.
Every coordination decision is made via SQLite transactions.

Components:
- **EventOutbox**: Transactional outbox pattern for reliable event delivery.
  Events and their outbox delivery rows are written in a single transaction.
- **OutboxDispatcher**: Claims pending outbox messages with bounded leases,
  acknowledges delivery only if lease still owned, expires stale claims.
- **InboxConsumer**: Deduplication layer for at-least-once delivery.
  Consumer effect + PROCESSED receipt commit in same transaction.
- **JobDispatcher**: Claims READY stage instances, creates Jobs with
  idempotency keys and fenced leases.
- **JobFactory**: Creates StageAttempt + Job atomically with deterministic IDs.
- **LeaseManager**: Fenced leases with monotonic tokens. Expired leases
  reclaimed with audit trail (RecoveryDecision).
- **WorkerLoop**: Claims jobs, runs handlers, handles completion/failure
  with retry/recovery classification.
- **RecoveryManager**: Bounded exponential backoff with deterministic jitter.
  Classifies failures: retryable vs permanent vs reconciliation.

Delivery Semantics:
- **At-least-once**: Outbox + inbox deduplication
- **At-most-once commit per attempt**: Fenced leases prevent stale commits;
  a worker may re-execute but only the first commit succeeds
- **Exactly-once effect**: Inbox deduplication + idempotent handlers

Failure Handling:
- Validation/permanent failures: No retry, dead-letter
- Transient/rate-limit: Bounded exponential backoff with deterministic jitter
- Timeout/unknown: Dead-letter, reconciliation required
- Exhausted retries: Human review or fail per policy

No External Dependencies:
- No Kafka, RabbitMQ, Redis, Celery
- SQLite rows are the only source of truth
- All coordination via SQLite transactions
"""

from __future__ import annotations

from pipeline.execution.dispatcher import (
    DEFAULT_MAX_DELIVERY_ATTEMPTS,
    DEFAULT_OUTBOX_LEASE_SECONDS,
    DeliveryResult,
    DeliveryStatus,
    DispatchResult,
    JobDispatcher,
    JobDispatchResult,
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
    "JobDispatchResult",
    "JobDispatcher",
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
