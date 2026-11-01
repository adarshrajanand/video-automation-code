"""Immutable artifact, dependency, pointer, and invalidation contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from pipeline.contracts.base import (
    Contract,
    ExtensionObject,
    NonEmptyStr,
    NonNegativeInt,
    OpaqueId,
    PositiveInt,
    Sha256Hex,
    StrictBoolean,
    UTCDateTime,
)
from pipeline.contracts.vocabularies import (
    ArtifactPointerType,
    ArtifactState,
    InvalidationScope,
)


class Artifact(Contract):
    """One immutable output version and its exact content hash."""

    schema_version: Literal["artifact.v1"]
    artifact_id: OpaqueId
    run_id: OpaqueId
    logical_slot: NonEmptyStr
    artifact_type: NonEmptyStr
    version: PositiveInt
    uri: NonEmptyStr
    sha256: Sha256Hex
    size_bytes: NonNegativeInt
    media_type: NonEmptyStr | None = None
    media_metadata: ExtensionObject = Field(default_factory=dict)
    producer_attempt_id: OpaqueId
    producer_version: NonEmptyStr
    input_artifact_ids: list[OpaqueId] = Field(default_factory=list)
    config_hash: Sha256Hex
    state: ArtifactState
    retention_class: NonEmptyStr = "intermediate"
    created_at: UTCDateTime

    @model_validator(mode="after")
    def _validate_artifact(self) -> Artifact:
        if len(set(self.input_artifact_ids)) != len(self.input_artifact_ids):
            raise ValueError("input_artifact_ids must not contain duplicates")
        if self.artifact_id in self.input_artifact_ids:
            raise ValueError("an artifact must not list itself as an input")
        return self


class ArtifactDependency(Contract):
    """Directed lineage edge between two immutable artifact versions."""

    schema_version: Literal["artifact-dependency.v1"]
    parent_artifact_id: OpaqueId
    child_artifact_id: OpaqueId
    dependency_type: NonEmptyStr

    @model_validator(mode="after")
    def _validate_distinct_endpoints(self) -> ArtifactDependency:
        if self.parent_artifact_id == self.child_artifact_id:
            raise ValueError(
                "artifact dependencies must connect two distinct artifact IDs"
            )
        return self


class ArtifactPointer(Contract):
    """Selects one artifact version for a logical slot at a point in time."""

    schema_version: Literal["artifact-pointer.v1"]
    pointer_id: OpaqueId
    run_id: OpaqueId
    logical_slot: NonEmptyStr
    artifact_id: OpaqueId
    pointer_type: ArtifactPointerType
    active: StrictBoolean = True
    updated_at: UTCDateTime


class InvalidationRequest(Contract):
    """Scoped request to invalidate a set of root artifacts and descendants."""

    schema_version: Literal["invalidation-request.v1"]
    request_id: OpaqueId
    root_artifact_ids: list[OpaqueId] = Field(min_length=1)
    reason: NonEmptyStr
    scope: InvalidationScope
    requested_by: NonEmptyStr

    @model_validator(mode="after")
    def _validate_roots(self) -> InvalidationRequest:
        if len(set(self.root_artifact_ids)) != len(self.root_artifact_ids):
            raise ValueError("root_artifact_ids must not contain duplicates")
        return self


class InvalidationResult(Contract):
    """Outcome of one invalidation request with disjoint retained artifacts."""

    schema_version: Literal["invalidation-result.v1"]
    request_id: OpaqueId
    invalidated_artifact_ids: list[OpaqueId] = Field(min_length=1)
    retained_artifact_ids: list[OpaqueId] = Field(default_factory=list)
    created_at: UTCDateTime

    @model_validator(mode="after")
    def _validate_partition(self) -> InvalidationResult:
        invalidated = set(self.invalidated_artifact_ids)
        retained = set(self.retained_artifact_ids)
        if len(invalidated) != len(self.invalidated_artifact_ids):
            raise ValueError("invalidated_artifact_ids must not contain duplicates")
        if len(retained) != len(self.retained_artifact_ids):
            raise ValueError("retained_artifact_ids must not contain duplicates")
        overlap = invalidated & retained
        if overlap:
            raise ValueError(
                "invalidated and retained artifact IDs must be disjoint: "
                + ", ".join(sorted(overlap))
            )
        return self


__all__ = [
    "Artifact",
    "ArtifactDependency",
    "ArtifactPointer",
    "InvalidationRequest",
    "InvalidationResult",
]
