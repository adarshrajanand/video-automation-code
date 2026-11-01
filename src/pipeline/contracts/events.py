"""Event envelope, transactional outbox, and inbox receipt contracts.

The envelope is the serialized durable event. Its payload is an explicit typed
extension validated by ``(event_type, payload_schema_version)``; core references
must agree with the envelope and with the canonical event registry.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, model_validator

from pipeline.contracts.base import (
    Contract,
    ExtensionObject,
    NonEmptyStr,
    NonNegativeInt,
    OpaqueId,
    UTCDateTime,
)
from pipeline.contracts.vocabularies import (
    EVENT_PAYLOAD_REQUIRED_FIELDS,
    EVENT_PAYLOAD_SCHEMAS,
    EventType,
    FailureCode,
    InboxStatus,
    OutboxStatus,
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class EventEnvelope(Contract):
    """Canonical serialized event fact, notification, or command."""

    schema_version: Literal["event-envelope.v1"]
    event_id: OpaqueId
    event_type: EventType
    run_id: OpaqueId | None = None
    stage_instance_id: OpaqueId | None = None
    attempt_id: OpaqueId | None = None
    correlation_id: OpaqueId
    causation_id: OpaqueId | None = None
    payload_schema_version: NonEmptyStr
    payload: ExtensionObject = Field(default_factory=dict)
    created_at: UTCDateTime

    @model_validator(mode="after")
    def _validate_payload_references(self) -> EventEnvelope:
        expected_version = EVENT_PAYLOAD_SCHEMAS[self.event_type]
        if self.payload_schema_version != expected_version:
            raise ValueError(
                f"event type {self.event_type.value!r} requires payload schema "
                f"{expected_version!r}, not {self.payload_schema_version!r}"
            )
        required = EVENT_PAYLOAD_REQUIRED_FIELDS[expected_version]
        missing = sorted(key for key in required if key not in self.payload)
        if missing:
            raise ValueError(
                f"event payload {expected_version!r} is missing required "
                f"reference(s): {', '.join(missing)}"
            )
        for key in required:
            self._validate_payload_value(key, self.payload[key])

        payload_run_id = self.payload.get("run_id")
        if not isinstance(payload_run_id, str) or not payload_run_id:
            raise ValueError("canonical event payloads require a non-empty run_id")
        if self.run_id is None:
            raise ValueError("canonical event envelopes require run_id")
        if self.run_id != payload_run_id:
            raise ValueError("envelope run_id must match payload run_id")
        for key in ("stage_instance_id", "attempt_id"):
            payload_value = self.payload.get(key)
            if payload_value is not None:
                envelope_value = getattr(self, key)
                if envelope_value is not None and envelope_value != payload_value:
                    raise ValueError(
                        f"envelope {key} must match payload {key} when both exist"
                    )
                if envelope_value is None:
                    raise ValueError(
                        f"envelope {key} is required when the payload references it"
                    )
        return self

    @staticmethod
    def _validate_payload_value(key: str, value: object) -> None:
        if key.endswith("_ids"):
            if not isinstance(value, list) or any(
                not isinstance(item, str) or not item for item in value
            ):
                raise ValueError(f"payload field {key!r} must be a list of IDs")
            if len(set(value)) != len(value):
                raise ValueError(f"payload field {key!r} must not contain duplicates")
            return
        if key == "reason_codes":
            if not isinstance(value, list) or any(
                not isinstance(item, str) or not item for item in value
            ):
                raise ValueError("reason_codes must be a list of non-empty strings")
            return
        if key == "sha256":
            if not isinstance(value, str) or _SHA256_PATTERN.match(value) is None:
                raise ValueError("payload sha256 must be a lowercase SHA-256 digest")
            return
        if key == "failure_code":
            FailureCode(value)
            return
        if not isinstance(value, str) or not value:
            raise ValueError(f"payload field {key!r} must be a non-empty string")


class OutboxMessage(Contract):
    """Delivery state for one committed event, claimed with a lease."""

    schema_version: Literal["outbox-message.v1"]
    outbox_id: OpaqueId
    event_id: OpaqueId
    event: EventEnvelope
    status: OutboxStatus
    delivery_attempts: NonNegativeInt = 0
    available_at: UTCDateTime
    claimed_by: NonEmptyStr | None = None
    claimed_at: UTCDateTime | None = None
    lease_expires_at: UTCDateTime | None = None
    delivered_at: UTCDateTime | None = None

    @model_validator(mode="after")
    def _validate_outbox_message(self) -> OutboxMessage:
        if self.event_id != self.event.event_id:
            raise ValueError("event_id must match the nested event.event_id")
        if self.status is OutboxStatus.CLAIMED and (
            self.claimed_by is None
            or self.claimed_at is None
            or self.lease_expires_at is None
        ):
            raise ValueError(
                "a claimed outbox message requires claimant and lease fields"
            )
        if (
            self.claimed_at is not None
            and self.lease_expires_at is not None
            and self.lease_expires_at <= self.claimed_at
        ):
            raise ValueError("lease_expires_at must be later than claimed_at")
        if self.status is OutboxStatus.DELIVERED and self.delivered_at is None:
            raise ValueError("a delivered outbox message requires delivered_at")
        if self.delivered_at is not None and self.delivered_at < self.available_at:
            raise ValueError("delivered_at must not be earlier than available_at")
        return self


class InboxReceipt(Contract):
    """One consumer's durable deduplication and processing receipt."""

    schema_version: Literal["inbox-receipt.v1"]
    consumer_id: OpaqueId
    event_id: OpaqueId
    status: InboxStatus
    processed_at: UTCDateTime | None = None
    error_code: FailureCode | None = None

    @model_validator(mode="after")
    def _validate_receipt(self) -> InboxReceipt:
        if self.status is InboxStatus.RECEIVED:
            if self.processed_at is not None or self.error_code is not None:
                raise ValueError(
                    "a received inbox entry must not be processed or failed"
                )
        elif self.status in (InboxStatus.PROCESSED, InboxStatus.IGNORED):
            if self.processed_at is None:
                raise ValueError(
                    f"a {self.status.value.lower()} receipt requires processed_at"
                )
            if self.error_code is not None:
                raise ValueError("a processed receipt must not carry error_code")
        elif self.status is InboxStatus.FAILED and self.error_code is None:
            raise ValueError("a failed inbox receipt requires error_code")
        return self


__all__ = ["EventEnvelope", "InboxReceipt", "OutboxMessage"]
