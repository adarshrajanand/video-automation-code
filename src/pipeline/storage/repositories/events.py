"""Typed repositories and transactional helpers for events and delivery.

The canonical event record and its outbox delivery row are separate tables but
one logical fact. Callers that create work must insert both inside the same
explicit transaction: :func:`insert_event_and_outbox` enforces the paired write
shape while leaving transaction ownership to the caller.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from pipeline.contracts.events import EventEnvelope, InboxReceipt, OutboxMessage
from pipeline.contracts.vocabularies import EventType, InboxStatus, OutboxStatus
from pipeline.fingerprints import canonical_datetime
from pipeline.ids import deterministic_id
from pipeline.storage.repositories.base import SqliteRepository


class WorkflowEventRepository(SqliteRepository[EventEnvelope]):
    """Canonical event-envelope repository over ``workflow_events``."""

    model = EventEnvelope
    table = "workflow_events"
    key_columns = ("event_id",)
    columns = (
        "event_id",
        "event_type",
        "run_id",
        "stage_instance_id",
        "attempt_id",
        "correlation_id",
        "causation_id",
        "payload_schema_version",
        "created_at",
    )
    order_by = ("created_at", "event_id")

    def list_for_run(self, run_id: str) -> list[EventEnvelope]:
        rows = self.connection.execute(
            "SELECT payload FROM workflow_events WHERE run_id = ? "
            "ORDER BY created_at, event_id",
            (run_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]

    def list_by_type(self, event_type: EventType) -> list[EventEnvelope]:
        rows = self.connection.execute(
            "SELECT payload FROM workflow_events WHERE event_type = ? "
            "ORDER BY created_at, event_id",
            (event_type.value,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]

    def exists(self, event_id: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM workflow_events WHERE event_id = ?", (event_id,)
        ).fetchone()
        return row is not None


class OutboxMessageRepository(SqliteRepository[OutboxMessage]):
    """Delivery-state repository over ``outbox_messages``.

    These methods are read-only helpers. Claim, acknowledgement, retry, and
    lease expiry use compare-and-set updates inside an explicit
    ``BEGIN IMMEDIATE`` transaction owned by the dispatcher.
    """

    model = OutboxMessage
    table = "outbox_messages"
    key_columns = ("outbox_id",)
    columns = (
        "outbox_id",
        "event_id",
        "status",
        "delivery_attempts",
        "available_at",
        "claimed_by",
        "claimed_at",
        "lease_expires_at",
        "delivered_at",
    )
    order_by = ("available_at", "outbox_id")

    def get_by_event_id(self, event_id: str) -> OutboxMessage | None:
        row = self.connection.execute(
            "SELECT payload FROM outbox_messages WHERE event_id = ?", (event_id,)
        ).fetchone()
        if row is None:
            return None
        return self.model.model_validate_json(row[0])

    def list_by_status(self, status: OutboxStatus) -> list[OutboxMessage]:
        rows = self.connection.execute(
            "SELECT payload FROM outbox_messages WHERE status = ? "
            "ORDER BY available_at, outbox_id",
            (status.value,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]

    def list_available(self, now: datetime, *, limit: int | None = None) -> list[str]:
        """Return PENDING outbox IDs that are available at ``now``.

        SQLite's ``julianday`` keeps ISO-8601 timestamps with or without
        fractional seconds correctly ordered; comparing canonical strings
        directly would not.
        """

        sql = (
            "SELECT outbox_id FROM outbox_messages "
            "WHERE status = ? AND julianday(available_at) <= julianday(?) "
            "ORDER BY julianday(available_at), outbox_id"
        )
        parameters: list[object] = [OutboxStatus.PENDING.value, _timestamp(now)]
        if limit is not None:
            sql += " LIMIT ?"
            parameters.append(limit)
        rows = self.connection.execute(sql, tuple(parameters)).fetchall()
        return [str(row[0]) for row in rows]

    def list_expired_claims(self, now: datetime) -> list[str]:
        rows = self.connection.execute(
            "SELECT outbox_id FROM outbox_messages "
            "WHERE status = ? AND lease_expires_at IS NOT NULL "
            "AND julianday(lease_expires_at) <= julianday(?) "
            "ORDER BY julianday(lease_expires_at), outbox_id",
            (OutboxStatus.CLAIMED.value, _timestamp(now)),
        ).fetchall()
        return [str(row[0]) for row in rows]


class InboxReceiptRepository(SqliteRepository[InboxReceipt]):
    """Consumer deduplication and processing receipts over ``inbox_receipts``."""

    model = InboxReceipt
    table = "inbox_receipts"
    key_columns = ("consumer_id", "event_id")
    columns = (
        "consumer_id",
        "event_id",
        "status",
        "processed_at",
        "error_code",
    )
    order_by = ("consumer_id", "event_id")

    def get_receipt(self, consumer_id: str, event_id: str) -> InboxReceipt | None:
        return self.get_optional(consumer_id, event_id)

    def list_for_consumer(self, consumer_id: str) -> list[InboxReceipt]:
        rows = self.connection.execute(
            "SELECT payload FROM inbox_receipts WHERE consumer_id = ? "
            "ORDER BY event_id",
            (consumer_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]

    def list_by_status(self, status: InboxStatus) -> list[InboxReceipt]:
        rows = self.connection.execute(
            "SELECT payload FROM inbox_receipts WHERE status = ? "
            "ORDER BY consumer_id, event_id",
            (status.value,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]


def insert_event_and_outbox(
    connection: sqlite3.Connection,
    event: EventEnvelope,
    *,
    outbox_id: str | None = None,
    available_at: datetime,
    status: OutboxStatus = OutboxStatus.PENDING,
) -> OutboxMessage:
    """Insert one event envelope and its outbox row in the caller's transaction.

    The helper deliberately does not open or commit a transaction. If the
    caller rolls back, neither the canonical event nor the delivery intent
    remains durable, so a state transition cannot leave orphaned work behind.
    """

    if status is not OutboxStatus.PENDING:
        raise ValueError("new outbox messages must start in PENDING state")
    if available_at.tzinfo is None or available_at.utcoffset() is None:
        raise ValueError("available_at must be timezone-aware")
    if not connection.in_transaction:
        raise ValueError(
            "insert_event_and_outbox requires an explicit caller transaction"
        )
    outbox_id = outbox_id or deterministic_id("outbox", event.event_id)
    WorkflowEventRepository(connection).insert(event)
    message = OutboxMessage(
        schema_version="outbox-message.v1",
        outbox_id=outbox_id,
        event_id=event.event_id,
        event=event,
        status=status,
        delivery_attempts=0,
        available_at=available_at,
    )
    OutboxMessageRepository(connection).insert(message)
    return message


def _timestamp(value: datetime) -> str:
    return canonical_datetime(value)


__all__ = [
    "InboxReceiptRepository",
    "OutboxMessageRepository",
    "WorkflowEventRepository",
    "insert_event_and_outbox",
]
