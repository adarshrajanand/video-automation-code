"""Claimable job and temporary lease contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from pipeline.contracts.base import (
    Contract,
    NonEmptyStr,
    NonNegativeInt,
    OpaqueId,
    PositiveInt,
    UTCDateTime,
)
from pipeline.contracts.vocabularies import JobStatus


class Job(Contract):
    """One claimable delivery record associated with one stage attempt."""

    schema_version: Literal["job.v1"]
    job_id: OpaqueId
    attempt_id: OpaqueId
    queue_name: NonEmptyStr
    status: JobStatus
    idempotency_key: NonEmptyStr
    available_at: UTCDateTime
    claimed_by: NonEmptyStr | None = None
    lease_expires_at: UTCDateTime | None = None
    delivery_count: NonNegativeInt = 0

    @model_validator(mode="after")
    def _validate_claimed_job(self) -> Job:
        if self.status is JobStatus.CLAIMED and self.claimed_by is None:
            raise ValueError("a claimed job requires claimed_by")
        return self


class Lease(Contract):
    """Temporary ownership term for one job, fenced by a monotonic token."""

    schema_version: Literal["lease.v1"]
    job_id: OpaqueId
    owner_id: NonEmptyStr
    fencing_token: PositiveInt
    acquired_at: UTCDateTime
    expires_at: UTCDateTime
    heartbeat_at: UTCDateTime | None = None

    @model_validator(mode="after")
    def _validate_lease_term(self) -> Lease:
        if self.expires_at <= self.acquired_at:
            raise ValueError("expires_at must be later than acquired_at")
        if self.heartbeat_at is not None and not (
            self.acquired_at <= self.heartbeat_at <= self.expires_at
        ):
            raise ValueError("heartbeat_at must fall within the acquired/expires term")
        return self


__all__ = ["Job", "Lease"]
