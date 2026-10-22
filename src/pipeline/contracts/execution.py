"""Run, stage-instance, attempt, manifest, and recovery contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from pipeline.contracts.base import (
    Contract,
    NonEmptyStr,
    NonNegativeFloat,
    NonNegativeInt,
    OpaqueId,
    PositiveInt,
    Sha256Hex,
    StrictBoolean,
    UnitInterval,
    UTCDateTime,
    UTCRecord,
)
from pipeline.contracts.config import RunOverrides
from pipeline.contracts.vocabularies import (
    AcceptanceStatus,
    AttemptStatus,
    DuplicatePolicy,
    FailureCategory,
    FailureCode,
    QualityFailureAction,
    RecoveryAction,
    RepeatedFailureAction,
    RunStatus,
    StageExecutionStatus,
    UnknownOutcomeAction,
)


class WorkflowRun(UTCRecord):
    """One execution of a workflow definition."""

    schema_version: Literal["workflow-run.v1"]
    run_id: OpaqueId
    run_key: NonEmptyStr
    workflow_id: OpaqueId
    workflow_version: NonEmptyStr
    effective_config_id: OpaqueId
    effective_config_hash: Sha256Hex
    status: RunStatus
    content_package_id: OpaqueId


class RunCreateRequest(Contract):
    """Idempotent request to create a workflow run."""

    schema_version: Literal["run-create-request.v1"]
    run_key: NonEmptyStr
    workflow_id: OpaqueId
    workflow_version: NonEmptyStr
    content_package_id: OpaqueId
    effective_config_overrides: RunOverrides
    duplicate_policy: DuplicatePolicy = DuplicatePolicy.RETURN_EXISTING


class StageInstance(UTCRecord):
    """Logical work for one workflow node and one logical item."""

    schema_version: Literal["stage-instance.v1"]
    stage_instance_id: OpaqueId
    run_id: OpaqueId
    node_id: OpaqueId
    logical_item_key: NonEmptyStr
    execution_status: StageExecutionStatus
    acceptance_status: AcceptanceStatus
    quality_gate_id: NonEmptyStr | None = None
    quality_gate_result_id: OpaqueId | None = None
    expected_input_manifest_id: OpaqueId | None = None
    active_attempt_id: OpaqueId | None = None
    accepted_output_artifact_ids: list[OpaqueId] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_unique_outputs(self) -> StageInstance:
        if len(set(self.accepted_output_artifact_ids)) != len(
            self.accepted_output_artifact_ids
        ):
            raise ValueError("accepted_output_artifact_ids must not contain duplicates")
        return self


class StageAttempt(Contract):
    """One claimable execution attempt for a logical stage instance."""

    schema_version: Literal["stage-attempt.v1"]
    attempt_id: OpaqueId
    stage_instance_id: OpaqueId
    attempt_number: PositiveInt
    quality_regeneration_number: NonNegativeInt = 0
    status: AttemptStatus
    input_artifact_ids: list[OpaqueId] = Field(default_factory=list)
    output_artifact_ids: list[OpaqueId] = Field(default_factory=list)
    worker_id: NonEmptyStr | None = None
    lease_expires_at: UTCDateTime | None = None
    started_at: UTCDateTime | None = None
    finished_at: UTCDateTime | None = None
    failure_code: FailureCode | None = None
    failure_message: NonEmptyStr | None = None

    @model_validator(mode="after")
    def _validate_attempt(self) -> StageAttempt:
        if len(set(self.input_artifact_ids)) != len(self.input_artifact_ids):
            raise ValueError("input_artifact_ids must not contain duplicates")
        if len(set(self.output_artifact_ids)) != len(self.output_artifact_ids):
            raise ValueError("output_artifact_ids must not contain duplicates")
        if (
            self.started_at is not None
            and self.finished_at is not None
            and self.finished_at < self.started_at
        ):
            raise ValueError("finished_at must not be earlier than started_at")
        if self.status is AttemptStatus.SUCCEEDED and self.failure_code is not None:
            raise ValueError("a succeeded attempt must not carry a failure_code")
        return self


class InputManifest(Contract):
    """Frozen expected input set for one stage instance."""

    schema_version: Literal["input-manifest.v1"]
    manifest_id: OpaqueId
    stage_instance_id: OpaqueId
    expected_artifact_slots: list[NonEmptyStr] = Field(default_factory=list)
    resolved_artifact_ids: list[OpaqueId] = Field(default_factory=list)
    expected_count: NonNegativeInt | None = None
    complete: StrictBoolean = False
    created_at: UTCDateTime

    @model_validator(mode="after")
    def _validate_manifest(self) -> InputManifest:
        if len(set(self.expected_artifact_slots)) != len(self.expected_artifact_slots):
            raise ValueError("expected_artifact_slots must not contain duplicates")
        if len(set(self.resolved_artifact_ids)) != len(self.resolved_artifact_ids):
            raise ValueError("resolved_artifact_ids must not contain duplicates")
        if (
            self.expected_count is not None
            and len(self.resolved_artifact_ids) > self.expected_count
        ):
            raise ValueError(
                "resolved_artifact_ids exceeds the declared expected_count"
            )
        if self.complete:
            if self.expected_count is None:
                raise ValueError("a complete manifest requires expected_count")
            if len(self.resolved_artifact_ids) != self.expected_count:
                raise ValueError(
                    "a complete manifest must resolve exactly expected_count items"
                )
        return self


class RetryPolicy(Contract):
    """Bounded transport retry policy owned by configuration."""

    schema_version: Literal["retry-policy.v1"]
    policy_id: OpaqueId
    max_attempts: PositiveInt
    initial_backoff_seconds: NonNegativeFloat
    max_backoff_seconds: NonNegativeFloat
    jitter_ratio: UnitInterval
    retryable_categories: list[FailureCategory] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_backoff(self) -> RetryPolicy:
        if self.max_backoff_seconds < self.initial_backoff_seconds:
            raise ValueError(
                "max_backoff_seconds must be greater than or equal to "
                "initial_backoff_seconds"
            )
        if len(set(self.retryable_categories)) != len(self.retryable_categories):
            raise ValueError("retryable_categories must not contain duplicates")
        return self


class RecoveryPolicy(Contract):
    """Policy for unknown, quality, and repeated execution failures."""

    schema_version: Literal["recovery-policy.v1"]
    policy_id: OpaqueId
    retry_policy_id: OpaqueId
    on_unknown_outcome: UnknownOutcomeAction
    on_quality_failure: QualityFailureAction
    on_repeated_failure: RepeatedFailureAction


class RecoveryDecision(Contract):
    """Recorded recovery action for one run and optional failed attempt."""

    schema_version: Literal["recovery-decision.v1"]
    recovery_decision_id: OpaqueId
    run_id: OpaqueId
    failed_attempt_id: OpaqueId | None = None
    action: RecoveryAction
    target_stage_instance_ids: list[OpaqueId] = Field(default_factory=list)
    target_artifact_ids: list[OpaqueId] = Field(default_factory=list)
    reason_codes: list[NonEmptyStr] = Field(default_factory=list)
    created_at: UTCDateTime

    @model_validator(mode="after")
    def _validate_unique_references(self) -> RecoveryDecision:
        for field_name in (
            "target_stage_instance_ids",
            "target_artifact_ids",
            "reason_codes",
        ):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
        return self


__all__ = [
    "InputManifest",
    "RecoveryDecision",
    "RecoveryPolicy",
    "RetryPolicy",
    "RunCreateRequest",
    "StageAttempt",
    "StageInstance",
    "WorkflowRun",
]
