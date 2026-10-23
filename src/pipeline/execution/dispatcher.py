"""Local polling dispatcher for the transactional outbox.

Every claim, acknowledgement, retry, and expiry decision is a compare-and-set
inside an explicit ``BEGIN IMMEDIATE`` transaction. Delivery is at-least-once;
the inbox consumer makes a repeated delivery a no-op instead of a second effect.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol

from pipeline.contracts.events import EventEnvelope, OutboxMessage
from pipeline.contracts.vocabularies import OutboxStatus
from pipeline.execution.inbox import InboxConsumer
from pipeline.execution.retry import bounded_backoff_seconds, deterministic_jitter
from pipeline.storage.database import Database
from pipeline.storage.repositories.events import OutboxMessageRepository

DEFAULT_OUTBOX_LEASE_SECONDS = 30.0
DEFAULT_MAX_DELIVERY_ATTEMPTS = 5


class OutboxDeliveryHandler(Protocol):
    """Consumer effect invoked exactly once per ``(consumer_id, event_id)``."""

    def __call__(
        self, connection: sqlite3.Connection, event: EventEnvelope
    ) -> object: ...


class NoopOutboxHandler:
    """Safe local handler that records delivery without executing stage work."""

    def __call__(self, connection: sqlite3.Connection, event: EventEnvelope) -> None:
        del connection, event


class DeliveryStatus(StrEnum):
    """Result of processing one claimed outbox message."""

    DELIVERED = "DELIVERED"
    DUPLICATE = "DUPLICATE"
    RETRIED = "RETRIED"
    FAILED = "FAILED"
    STALE = "STALE"


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    """One claimed message processing result."""

    status: DeliveryStatus
    message: OutboxMessage
    acknowledged: bool = False
    error: str | None = None


@dataclass(frozen=True, slots=True)
class DispatchResult:
    """Aggregate of one polling pass."""

    claimed: int = 0
    delivered: int = 0
    duplicates: int = 0
    retried: int = 0
    failed: int = 0
    stale: int = 0


class OutboxDispatcher:
    """Claim and deliver pending outbox rows with durable leases."""

    def __init__(
        self,
        database: Database,
        *,
        dispatcher_id: str = "dispatcher_local_01",
        consumer_id: str = "local_consumer",
        handler: OutboxDeliveryHandler | None = None,
        lease_seconds: float = DEFAULT_OUTBOX_LEASE_SECONDS,
        max_delivery_attempts: int = DEFAULT_MAX_DELIVERY_ATTEMPTS,
        initial_backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 60.0,
        jitter_ratio: float = 0.2,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not dispatcher_id:
            raise ValueError("dispatcher_id must be non-empty")
        if not consumer_id:
            raise ValueError("consumer_id must be non-empty")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if max_delivery_attempts < 1:
            raise ValueError("max_delivery_attempts must be at least 1")
        if max_backoff_seconds < initial_backoff_seconds:
            raise ValueError("max_backoff_seconds must not be below initial")
        self.database = database
        self.dispatcher_id = dispatcher_id
        self.consumer_id = consumer_id
        self.handler = handler or NoopOutboxHandler()
        self.lease_seconds = float(lease_seconds)
        self.max_delivery_attempts = max_delivery_attempts
        self.initial_backoff_seconds = initial_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.jitter_ratio = jitter_ratio
        self._clock = clock or _utc_now
        self._inbox = InboxConsumer(database, clock=self._clock)

    def claim_pending(self, *, limit: int | None = None) -> list[OutboxMessage]:
        """Claim available messages, first recovering expired claims."""

        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1")
        now = self._clock()
        expires_at = now + timedelta(seconds=self.lease_seconds)
        with self.database.transaction(immediate=True) as connection:
            self._expire_claims_locked(connection, now)
            repository = OutboxMessageRepository(connection)
            outbox_ids = repository.list_available(now, limit=limit)
            claimed: list[OutboxMessage] = []
            for outbox_id in outbox_ids:
                message = repository.get(outbox_id)
                if message.status is not OutboxStatus.PENDING:
                    continue
                claimed_message = message.model_copy(
                    update={
                        "status": OutboxStatus.CLAIMED,
                        "delivery_attempts": message.delivery_attempts + 1,
                        "claimed_by": self.dispatcher_id,
                        "claimed_at": now,
                        "lease_expires_at": expires_at,
                    }
                )
                repository.update(claimed_message)
                claimed.append(claimed_message)
            return claimed

    def ack(self, message: OutboxMessage) -> bool:
        """Mark one message delivered only when this dispatcher still owns it."""

        now = self._clock()
        with self.database.transaction(immediate=True) as connection:
            repository = OutboxMessageRepository(connection)
            current = repository.get(message.outbox_id)
            if (
                current.status is not OutboxStatus.CLAIMED
                or current.claimed_by != self.dispatcher_id
            ):
                return False
            delivered = current.model_copy(
                update={
                    "status": OutboxStatus.DELIVERED,
                    "claimed_by": None,
                    "claimed_at": None,
                    "lease_expires_at": None,
                    "delivered_at": now,
                }
            )
            repository.update(delivered)
            return True

    def deliver_claimed(
        self,
        message: OutboxMessage,
        *,
        acknowledge: bool = True,
    ) -> DeliveryResult:
        """Run the deduplicated consumer effect for one claimed message."""

        if message.status is not OutboxStatus.CLAIMED:
            return DeliveryResult(status=DeliveryStatus.STALE, message=message)
        if message.claimed_by != self.dispatcher_id:
            return DeliveryResult(status=DeliveryStatus.STALE, message=message)
        try:
            processed = self._inbox.process(
                message.event,
                self.handler,
                consumer_id=self.consumer_id,
            )
        except Exception as error:
            scheduled = self._schedule_retry(message)
            return DeliveryResult(
                status=scheduled or DeliveryStatus.STALE,
                message=message,
                error=f"{type(error).__name__}: {error}",
            )

        status = (
            DeliveryStatus.DUPLICATE
            if processed.duplicate
            else DeliveryStatus.DELIVERED
        )
        acknowledged = False
        if acknowledge:
            acknowledged = self.ack(message)
            if not acknowledged:
                return DeliveryResult(
                    status=DeliveryStatus.STALE,
                    message=message,
                    error="outbox claim was no longer live at acknowledgement",
                )
        return DeliveryResult(
            status=status,
            message=message,
            acknowledged=acknowledged,
        )

    def dispatch_once(self, *, limit: int | None = None) -> DispatchResult:
        """Claim and deliver one bounded batch of pending messages."""

        messages = self.claim_pending(limit=limit)
        delivered = duplicates = retried = failed = stale = 0
        for message in messages:
            result = self.deliver_claimed(message)
            if result.status is DeliveryStatus.DELIVERED:
                delivered += 1
            elif result.status is DeliveryStatus.DUPLICATE:
                duplicates += 1
            elif result.status is DeliveryStatus.RETRIED:
                retried += 1
            elif result.status is DeliveryStatus.FAILED:
                failed += 1
            else:
                stale += 1
        return DispatchResult(
            claimed=len(messages),
            delivered=delivered,
            duplicates=duplicates,
            retried=retried,
            failed=failed,
            stale=stale,
        )

    def expire_claims(self) -> int:
        """Return expired dispatcher claims to PENDING for redelivery."""

        now = self._clock()
        with self.database.transaction(immediate=True) as connection:
            return self._expire_claims_locked(connection, now)

    def _expire_claims_locked(
        self,
        connection: sqlite3.Connection,
        now: datetime,
    ) -> int:
        repository = OutboxMessageRepository(connection)
        expired = repository.list_expired_claims(now)
        for outbox_id in expired:
            message = repository.get(outbox_id)
            repository.update(
                message.model_copy(
                    update={
                        "status": OutboxStatus.PENDING,
                        "available_at": now,
                        "claimed_by": None,
                        "claimed_at": None,
                        "lease_expires_at": None,
                    }
                )
            )
        return len(expired)

    def _schedule_retry(self, message: OutboxMessage) -> DeliveryStatus | None:
        now = self._clock()
        with self.database.transaction(immediate=True) as connection:
            repository = OutboxMessageRepository(connection)
            current = repository.get(message.outbox_id)
            if (
                current.status is not OutboxStatus.CLAIMED
                or current.claimed_by != self.dispatcher_id
            ):
                return None
            if current.delivery_attempts >= self.max_delivery_attempts:
                repository.update(
                    current.model_copy(
                        update={
                            "status": OutboxStatus.FAILED,
                            "claimed_by": None,
                            "claimed_at": None,
                            "lease_expires_at": None,
                        }
                    )
                )
                return DeliveryStatus.FAILED
            delay = bounded_backoff_seconds(
                current.delivery_attempts,
                initial_backoff_seconds=self.initial_backoff_seconds,
                max_backoff_seconds=self.max_backoff_seconds,
                jitter_ratio=self.jitter_ratio,
                jitter_value=deterministic_jitter(
                    current.outbox_id, current.delivery_attempts
                ),
            )
            repository.update(
                current.model_copy(
                    update={
                        "status": OutboxStatus.PENDING,
                        "available_at": now + timedelta(seconds=delay),
                        "claimed_by": None,
                        "claimed_at": None,
                        "lease_expires_at": None,
                    }
                )
            )
            return DeliveryStatus.RETRIED


def _utc_now() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "DEFAULT_MAX_DELIVERY_ATTEMPTS",
    "DEFAULT_OUTBOX_LEASE_SECONDS",
    "DeliveryResult",
    "DeliveryStatus",
    "DispatchResult",
    "NoopOutboxHandler",
    "OutboxDeliveryHandler",
    "OutboxDispatcher",
]
