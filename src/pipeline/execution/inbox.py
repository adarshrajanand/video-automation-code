"""Durable inbox deduplication for at-least-once event delivery."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TypeVar

from pipeline.contracts.events import EventEnvelope, InboxReceipt
from pipeline.contracts.vocabularies import FailureCode, InboxStatus
from pipeline.storage.database import Database
from pipeline.storage.errors import StorageError
from pipeline.storage.repositories.events import InboxReceiptRepository

T = TypeVar("T")

InboxEffect = Callable[[sqlite3.Connection, EventEnvelope], T]


@dataclass(frozen=True, slots=True)
class InboxProcessResult:
    """Outcome of one consumer receipt attempt."""

    consumer_id: str
    event_id: str
    duplicate: bool
    receipt: InboxReceipt
    value: Any = None


class InboxConsumer:
    """Run a consumer effect at most once per ``(consumer_id, event_id)``.

    The effect and the ``PROCESSED`` receipt commit in one transaction. A crash
    before that commit leaves no receipt, so redelivery may run the effect again.
    A crash after the commit leaves a receipt, so a duplicate delivery is a
    no-op. Consumers that need cross-event invariants should also use an
    idempotent durable record (for example a job idempotency key).
    """

    def __init__(
        self,
        database: Database,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.database = database
        self._clock = clock or _utc_now

    def process(
        self,
        event: EventEnvelope,
        effect: InboxEffect[T],
        *,
        consumer_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> InboxProcessResult:
        """Run ``effect`` once for this consumer and event.

        When the caller owns the transaction (``connection`` is supplied), the
        caller also owns rollback and failure recording. Otherwise this method
        opens one ``BEGIN IMMEDIATE`` transaction and records a failed receipt in
        a separate transaction before re-raising an effect error.
        """

        now = self._clock()
        if connection is not None:
            if not connection.in_transaction:
                raise ValueError(
                    "InboxConsumer.process requires an explicit caller "
                    "transaction when a connection is supplied"
                )
            result = self._process(
                connection,
                event,
                effect,
                consumer_id=consumer_id,
                now=now,
            )
            return result

        try:
            with self.database.transaction(immediate=True) as transaction:
                return self._process(
                    transaction,
                    event,
                    effect,
                    consumer_id=consumer_id,
                    now=now,
                )
        except Exception as error:
            with (
                suppress(StorageError, sqlite3.Error),
                self.database.transaction(immediate=True) as transaction,
            ):
                self._mark_failed(
                    transaction,
                    event,
                    consumer_id=consumer_id,
                    now=now,
                    error=error,
                )
            raise

    def ignore(self, event: EventEnvelope, *, consumer_id: str) -> InboxReceipt:
        """Record a deliberate no-op receipt for an event.

        Preserves existing PROCESSED status - cannot downgrade from PROCESSED.
        """
        now = self._clock()
        with self.database.transaction(immediate=True) as connection:
            repository = InboxReceiptRepository(connection)
            existing = repository.get_receipt(consumer_id, event.event_id)
            if existing is not None and existing.status is InboxStatus.PROCESSED:
                # Cannot downgrade PROCESSED to IGNORED
                return existing
            receipt = InboxReceipt(
                schema_version="inbox-receipt.v1",
                consumer_id=consumer_id,
                event_id=event.event_id,
                status=InboxStatus.IGNORED,
                processed_at=now,
            )
            if existing is None:
                return repository.insert(receipt)
            return repository.update(receipt)

    def get_receipt(self, *, consumer_id: str, event_id: str) -> InboxReceipt | None:
        with self.database.connection() as connection:
            return InboxReceiptRepository(connection).get_receipt(consumer_id, event_id)

    def _process(
        self,
        connection: sqlite3.Connection,
        event: EventEnvelope,
        effect: InboxEffect[T],
        *,
        consumer_id: str,
        now: datetime,
    ) -> InboxProcessResult:
        repository = InboxReceiptRepository(connection)
        existing = repository.get_receipt(consumer_id, event.event_id)
        if existing is not None and existing.status in (
            InboxStatus.PROCESSED,
            InboxStatus.IGNORED,
        ):
            return InboxProcessResult(
                consumer_id=consumer_id,
                event_id=event.event_id,
                duplicate=True,
                receipt=existing,
            )

        if existing is None:
            repository.insert(
                InboxReceipt(
                    schema_version="inbox-receipt.v1",
                    consumer_id=consumer_id,
                    event_id=event.event_id,
                    status=InboxStatus.RECEIVED,
                )
            )
        elif existing.status is InboxStatus.FAILED:
            repository.update(
                InboxReceipt(
                    schema_version="inbox-receipt.v1",
                    consumer_id=consumer_id,
                    event_id=event.event_id,
                    status=InboxStatus.RECEIVED,
                )
            )

        value = effect(connection, event)
        processed = InboxReceipt(
            schema_version="inbox-receipt.v1",
            consumer_id=consumer_id,
            event_id=event.event_id,
            status=InboxStatus.PROCESSED,
            processed_at=now,
        )
        repository.update(processed)
        return InboxProcessResult(
            consumer_id=consumer_id,
            event_id=event.event_id,
            duplicate=False,
            receipt=processed,
            value=value,
        )

    def _mark_failed(
        self,
        connection: sqlite3.Connection,
        event: EventEnvelope,
        *,
        consumer_id: str,
        now: datetime,
        error: Exception,
    ) -> None:
        del now, error
        repository = InboxReceiptRepository(connection)
        existing = repository.get_receipt(consumer_id, event.event_id)
        failed = InboxReceipt(
            schema_version="inbox-receipt.v1",
            consumer_id=consumer_id,
            event_id=event.event_id,
            status=InboxStatus.FAILED,
            error_code=FailureCode.INTERNAL,
        )
        if existing is None:
            repository.insert(failed)
        else:
            repository.update(failed)


def _utc_now() -> datetime:
    return datetime.now(UTC)


__all__ = ["InboxConsumer", "InboxEffect", "InboxProcessResult"]
