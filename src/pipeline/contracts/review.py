"""Durable human review and publication-boundary contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from pipeline.contracts.base import (
    Contract,
    NonEmptyStr,
    NormalizedError,
    OpaqueId,
    Sha256Hex,
    UTCDateTime,
)
from pipeline.contracts.vocabularies import (
    PublicationStatus,
    ReviewDecision,
    ReviewStatus,
)


class HumanReview(Contract):
    """Durable reviewer request tied to exact artifact versions."""

    schema_version: Literal["human-review.v1"]
    review_id: OpaqueId
    run_id: OpaqueId
    stage_instance_id: OpaqueId | None = None
    gate_id: NonEmptyStr | None = None
    target_artifact_ids: list[OpaqueId] = Field(min_length=1)
    target_hashes: dict[OpaqueId, Sha256Hex] = Field(default_factory=dict)
    reason_codes: list[NonEmptyStr] = Field(default_factory=list)
    requested_action: NonEmptyStr
    status: ReviewStatus
    created_at: UTCDateTime
    resolved_at: UTCDateTime | None = None

    @model_validator(mode="after")
    def _validate_review(self) -> HumanReview:
        if len(set(self.target_artifact_ids)) != len(self.target_artifact_ids):
            raise ValueError("target_artifact_ids must not contain duplicates")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("reason_codes must not contain duplicates")
        if self.target_hashes and set(self.target_hashes) != set(
            self.target_artifact_ids
        ):
            raise ValueError(
                "target_hashes keys must exactly match target_artifact_ids"
            )
        if self.resolved_at is not None and self.resolved_at < self.created_at:
            raise ValueError("resolved_at must not be earlier than created_at")
        return self


class HumanReviewDecision(Contract):
    """Recorded reviewer decision for one human review request."""

    schema_version: Literal["human-review-decision.v1"]
    review_id: OpaqueId
    decision: ReviewDecision
    comments: NonEmptyStr | None = None
    reviewer: NonEmptyStr
    target_hashes: dict[OpaqueId, Sha256Hex] = Field(default_factory=dict)
    created_at: UTCDateTime


class PublicationRequest(Contract):
    """Exact approved hashes and metadata allowed through the publishing boundary."""

    schema_version: Literal["publication-request.v1"]
    publication_request_id: OpaqueId
    run_id: OpaqueId
    cut_ids: list[OpaqueId] = Field(min_length=1)
    approved_artifact_hashes: dict[OpaqueId, Sha256Hex] = Field(min_length=1)
    approval_ids: list[OpaqueId] = Field(min_length=1)
    platform: NonEmptyStr
    metadata_artifact_id: OpaqueId
    idempotency_key: NonEmptyStr

    @model_validator(mode="after")
    def _validate_unique_publication_lists(self) -> PublicationRequest:
        for field_name in ("cut_ids", "approval_ids"):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
        return self


class PublicationAttempt(Contract):
    """One attempt to publish an approved publication request."""

    schema_version: Literal["publication-attempt.v1"]
    publication_attempt_id: OpaqueId
    publication_request_id: OpaqueId
    status: PublicationStatus
    external_publication_id: NonEmptyStr | None = None
    provider_operation_id: NonEmptyStr | None = None
    normalized_error: NormalizedError | None = None
    started_at: UTCDateTime | None = None
    finished_at: UTCDateTime | None = None

    @model_validator(mode="after")
    def _validate_publication_attempt(self) -> PublicationAttempt:
        if (
            self.started_at is not None
            and self.finished_at is not None
            and self.finished_at < self.started_at
        ):
            raise ValueError("finished_at must not be earlier than started_at")
        if self.status is PublicationStatus.FAILED and self.normalized_error is None:
            raise ValueError("a failed publication attempt requires a normalized_error")
        if (
            self.status is PublicationStatus.SUCCEEDED
            and self.normalized_error is not None
        ):
            raise ValueError(
                "a succeeded publication attempt must not carry a normalized_error"
            )
        return self


__all__ = [
    "HumanReview",
    "HumanReviewDecision",
    "PublicationAttempt",
    "PublicationRequest",
]
