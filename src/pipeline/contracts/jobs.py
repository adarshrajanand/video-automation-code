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

    schema_version: Literal["job.v2"]
    job_id: OpaqueId
    attempt_id: OpaqueId
    queue_name: NonEmptyStr
    status: JobStatus
    idempotency_key: NonEmptyStr
    available_timestamp_micro: UTCDateTime
    claimed_by: NonEmptyStr | None = None
    lease_expires_timestamp_micro: UTCDateTime | None = None
    delivery_count: NonNegativeInt = 0
    # Projection of the active lease term. The leases table remains the
    # authoritative ownership record; this copy lets a job be inspected without
    # a join and is compare-and-set on every fenced completion.
    fencing_token: PositiveInt | None = None

    @model_validator(mode="after")
    def _validate_claimed_job(self) -> Job:
        if self.status is JobStatus.CLAIMED and self.claimed_by is None:
            raise ValueError("a claimed job requires claimed_by")
        return self


class Lease(Contract):
    """Temporary ownership term for one job, fenced by a monotonic token."""

    schema_version: Literal["lease.v2"]
    job_id: OpaqueId
    owner_id: NonEmptyStr
    fencing_token: PositiveInt
    acquired_timestamp_micro: UTCDateTime
    expires_timestamp_micro: UTCDateTime
    heartbeat_timestamp_micro: UTCDateTime | None = None

    @model_validator(mode="after")
    def _validate_lease_term(self) -> Lease:
        if self.expires_timestamp_micro <= self.acquired_timestamp_micro:
            raise ValueError("expires_timestamp_micro must be later than acquired_timestamp_micro")
        if self.heartbeat_timestamp_micro is not None and not (
            self.acquired_timestamp_micro <= self.heartbeat_timestamp_micro <= self.expires_timestamp_micro
        ):
            raise ValueError("heartbeat_timestamp_micro must fall within the acquired/expires term")
        return self


__all__ = ["Job", "Lease"]
