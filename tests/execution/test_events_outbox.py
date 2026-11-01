from __future__ import annotations

from datetime import timedelta

import pytest

from pipeline.contracts.events import EventEnvelope
from pipeline.contracts.vocabularies import InboxStatus, OutboxStatus
from pipeline.execution.dispatcher import OutboxDispatcher
from pipeline.execution.events import EventOutbox
from pipeline.execution.inbox import InboxConsumer
from pipeline.storage.repositories.events import (
    InboxReceiptRepository,
    OutboxMessageRepository,
    WorkflowEventRepository,
)


class RecordingHandler:
    def __init__(self) -> None:
        self.events: list[str] = []

    def __call__(self, connection, event: EventEnvelope) -> None:
        del connection
        self.events.append(event.event_id)


class FailingHandler:
    def __call__(self, connection, event: EventEnvelope) -> None:
        del connection, event
        raise RuntimeError("delivery failed")


def counts(database) -> tuple[int, int]:
    with database.connection() as connection:
        events = connection.execute("SELECT COUNT(*) FROM workflow_events").fetchone()[
            0
        ]
        outbox = connection.execute("SELECT COUNT(*) FROM outbox_messages").fetchone()[
            0
        ]
    return int(events), int(outbox)


def test_event_and_outbox_append_share_one_commit(records, clock) -> None:
    outbox = EventOutbox(records.database, clock=clock)

    message = outbox.append(records.event())

    assert counts(records.database) == (1, 1)
    assert message.status is OutboxStatus.PENDING
    with records.database.connection() as connection:
        stored = WorkflowEventRepository(connection).get("event_ready_01")
        assert stored.payload["job_id"] == "job_pending"
        assert OutboxMessageRepository(connection).get(message.outbox_id) == message


def test_rollback_leaves_neither_event_nor_outbox(records, clock) -> None:
    outbox = EventOutbox(records.database, clock=clock)

    with (
        pytest.raises(RuntimeError, match="abort"),
        records.database.transaction() as connection,
    ):
        outbox.append(records.event(), connection=connection)
        raise RuntimeError("abort")

    assert counts(records.database) == (0, 0)


def test_dispatcher_claims_and_acks_message(records, clock) -> None:
    EventOutbox(records.database, clock=clock).append(records.event())
    handler = RecordingHandler()
    dispatcher = OutboxDispatcher(
        records.database,
        handler=handler,
        lease_seconds=30,
        clock=clock,
    )

    result = dispatcher.dispatch_once()

    assert result.claimed == 1
    assert result.delivered == 1
    assert handler.events == ["event_ready_01"]
    with records.database.connection() as connection:
        message = OutboxMessageRepository(connection).get_by_event_id("event_ready_01")
        assert message is not None
        assert message.status is OutboxStatus.DELIVERED
        assert message.delivered_at == clock.now
        receipt = InboxReceiptRepository(connection).get_receipt(
            "local_consumer", "event_ready_01"
        )
        assert receipt is not None
        assert receipt.status is InboxStatus.PROCESSED


def test_crash_before_ack_is_redelivered_without_second_effect(records, clock) -> None:
    EventOutbox(records.database, clock=clock).append(records.event())
    handler = RecordingHandler()
    dispatcher = OutboxDispatcher(
        records.database,
        handler=handler,
        lease_seconds=10,
        clock=clock,
    )

    first_claim = dispatcher.claim_pending()
    assert len(first_claim) == 1
    first_delivery = dispatcher.deliver_claimed(
        first_claim[0],
        acknowledge=False,
    )
    assert first_delivery.acknowledged is False
    assert handler.events == ["event_ready_01"]

    clock.advance(seconds=11)
    redelivery = dispatcher.dispatch_once()

    assert redelivery.claimed == 1
    assert redelivery.duplicates == 1
    assert redelivery.delivered == 0
    assert handler.events == ["event_ready_01"]
    with records.database.connection() as connection:
        message = OutboxMessageRepository(connection).get_by_event_id("event_ready_01")
        assert message is not None
        assert message.status is OutboxStatus.DELIVERED
        assert message.delivery_attempts == 2


def test_duplicate_inbox_effect_is_noop(records, clock) -> None:
    event = records.event()
    EventOutbox(records.database, clock=clock).append(event)
    inbox = InboxConsumer(records.database, clock=clock)
    calls: list[str] = []

    def effect(connection, delivered: EventEnvelope) -> str:
        del connection, delivered
        calls.append("effect")
        return "value"

    first = inbox.process(event, effect, consumer_id="consumer_a")
    second = inbox.process(event, effect, consumer_id="consumer_a")

    assert first.duplicate is False
    assert first.value == "value"
    assert second.duplicate is True
    assert second.value is None
    assert calls == ["effect"]


def test_failed_delivery_retries_then_dead_letters(records, clock) -> None:
    EventOutbox(records.database, clock=clock).append(records.event())
    dispatcher = OutboxDispatcher(
        records.database,
        handler=FailingHandler(),
        lease_seconds=10,
        max_delivery_attempts=2,
        initial_backoff_seconds=5,
        max_backoff_seconds=5,
        jitter_ratio=0,
        clock=clock,
    )

    first = dispatcher.dispatch_once()
    assert first.retried == 1
    with records.database.connection() as connection:
        message = OutboxMessageRepository(connection).get_by_event_id("event_ready_01")
        assert message is not None
        assert message.status is OutboxStatus.PENDING
        assert message.available_at > clock.now
        receipt = InboxReceiptRepository(connection).get_receipt(
            "local_consumer", "event_ready_01"
        )
        assert receipt is not None
        assert receipt.status is InboxStatus.FAILED

    clock.advance(seconds=5)
    second = dispatcher.dispatch_once()
    assert second.failed == 1
    with records.database.connection() as connection:
        message = OutboxMessageRepository(connection).get_by_event_id("event_ready_01")
        assert message is not None
        assert message.status is OutboxStatus.FAILED
        assert message.delivery_attempts == 2


def test_claim_lease_uses_explicit_expiry(records, clock) -> None:
    EventOutbox(records.database, clock=clock).append(records.event())
    dispatcher = OutboxDispatcher(
        records.database,
        lease_seconds=15,
        clock=clock,
    )

    claimed = dispatcher.claim_pending()
    assert len(claimed) == 1
    assert claimed[0].lease_expires_at == clock.now + timedelta(seconds=15)

    assert dispatcher.expire_claims() == 0
    clock.advance(seconds=15)
    assert dispatcher.expire_claims() == 1
