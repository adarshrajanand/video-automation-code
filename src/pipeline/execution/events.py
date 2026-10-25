"""Transactional event and outbox append helpers."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from pipeline.contracts.events import EventEnvelope, OutboxMessage
from pipeline.storage.database import Database
from pipeline.storage.repositories.events import insert_event_and_outbox


def utc_now() -> datetime:
    """Return the current UTC instant with timezone information."""

    return datetime.now(UTC)


class EventOutbox:
    """Append canonical events together with their delivery intent.

    The two rows are always written in one explicit transaction. A caller that
    already owns a transaction passes its connection; otherwise the helper opens
    a ``BEGIN IMMEDIATE`` transaction itself.
    """

    def __init__(
        self,
        database: Database,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.database = database
        self._clock = clock or utc_now

    def append(
        self,
        event: EventEnvelope,
        *,
        outbox_id: str | None = None,
        available_at: datetime | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> OutboxMessage:
        """Insert one event and one outbox row in the same transaction."""

        available = available_at or self._clock()
        if connection is None:
            with self.database.transaction(immediate=True) as transaction:
                return insert_event_and_outbox(
                    transaction,
                    event,
                    outbox_id=outbox_id,
                    available_at=available,
                )
        return insert_event_and_outbox(
            connection,
            event,
            outbox_id=outbox_id,
            available_at=available,
        )

    def append_many(
        self,
        events: Sequence[EventEnvelope],
        *,
        available_at: datetime | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> list[OutboxMessage]:
        """Append a batch of events in one transaction."""

        available = available_at or self._clock()
        if connection is not None:
            return [
                self.append(event, available_at=available, connection=connection)
                for event in events
            ]
        with self.database.transaction(immediate=True) as transaction:
            return [
                self.append(event, available_at=available, connection=transaction)
                for event in events
            ]


__all__ = ["EventOutbox", "utc_now"]
