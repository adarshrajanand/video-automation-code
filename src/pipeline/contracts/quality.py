"""Quality check, evaluation, gate, and repair contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from pipeline.contracts.base import (
    Contract,
    ExtensionObject,
    FiniteFloat,
    NonEmptyStr,
    NonNegativeInt,
    OpaqueId,
    PositiveInt,
    Sha256Hex,
    StrictBoolean,
    UTCDateTime,
)
from pipeline.contracts.vocabularies import (
    CheckOutcome,
    Confidence,
    EvaluationKind,
    FailureCode,
    GateDecision,
    QualityFailureAction,
    RepairInvalidationScope,
    RepairScope,
    RepeatedFailureAction,
    Severity,
)


def _validate_hash_map(
    target_artifact_ids: list[str],
    target_hashes: dict[str, str],
    *,
    require_complete: bool,
) -> None:
    if len(set(target_artifact_ids)) != len(target_artifact_ids):
        raise ValueError("target_artifact_ids must not contain duplicates")
    target_set = set(target_artifact_ids)
    hash_set = set(target_hashes)
    if require_complete and hash_set != target_set:
        missing = sorted(target_set - hash_set)
        extra = sorted(hash_set - target_set)
        raise ValueError(
            "target_hashes keys must exactly match target_artifact_ids"
            + (f"; missing={missing}" if missing else "")
            + (f"; extra={extra}" if extra else "")
        )
    if not hash_set <= target_set:
        raise ValueError("target_hashes must not reference unknown target artifacts")


class EvaluationDimension(Contract):
    """One named score, threshold, and evidence set within an evaluation."""

    schema_version: Literal["evaluation-dimension.v1"]
    name: NonEmptyStr
    score: FiniteFloat | None = None
    threshold: FiniteFloat | None = None
    severity: Severity = Severity.INFO
    failure_codes: list[FailureCode] = Field(default_factory=list)
    evidence_refs: list[OpaqueId] = Field(default_factory=list)
    details: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_unique_dimension_lists(self) -> EvaluationDimension:
        for field_name in ("failure_codes", "evidence_refs"):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
        return self


class QualityCheck(Contract):
    """One registered requirement or evaluator invocation."""

    schema_version: Literal["quality-check.v1"]
    check_id: OpaqueId
    target_artifact_types: list[NonEmptyStr] = Field(min_length=1)
    required_input_types: list[NonEmptyStr] = Field(default_factory=list)
    kind: EvaluationKind
    evaluator: NonEmptyStr
    evaluator_version: NonEmptyStr
    rubric_version: NonEmptyStr | None = None
    required: StrictBoolean = True
    severity_if_failed: Severity
    on_failure: QualityFailureAction
    repair_scope: RepairScope

    @model_validator(mode="after")
    def _validate_check(self) -> QualityCheck:
        for field_name in ("target_artifact_types", "required_input_types"):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
        if self.kind is EvaluationKind.SEMANTIC and self.rubric_version is None:
            raise ValueError("a semantic check requires a rubric_version")
        if self.kind is not EvaluationKind.SEMANTIC and self.rubric_version is not None:
            raise ValueError("only semantic checks may declare a rubric_version")
        return self


class QualityInputManifest(Contract):
    """Exact artifact versions and hashes checked by one gate/check pair."""

    schema_version: Literal["quality-input-manifest.v1"]
    manifest_id: OpaqueId
    gate_id: NonEmptyStr
    check_id: OpaqueId
    target_artifact_ids: list[OpaqueId] = Field(min_length=1)
    target_hashes: dict[OpaqueId, Sha256Hex]
    supporting_artifact_ids: list[OpaqueId] = Field(default_factory=list)
    policy_snapshot_artifact_id: OpaqueId | None = None
    created_at: UTCDateTime

    @model_validator(mode="after")
    def _validate_manifest(self) -> QualityInputManifest:
        _validate_hash_map(
            self.target_artifact_ids, self.target_hashes, require_complete=True
        )
        if len(set(self.supporting_artifact_ids)) != len(self.supporting_artifact_ids):
            raise ValueError("supporting_artifact_ids must not contain duplicates")
        return self


class QualityGatePolicy(Contract):
    """Versioned rules that aggregate required checks into one decision."""

    schema_version: Literal["quality-gate-policy.v1"]
    gate_id: OpaqueId
    version: NonEmptyStr
    required_check_ids: list[OpaqueId] = Field(min_length=1)
    hard_failure_codes: list[FailureCode] = Field(default_factory=list)
    pass_thresholds: dict[NonEmptyStr, FiniteFloat] = Field(default_factory=dict)
    human_review_thresholds: dict[NonEmptyStr, FiniteFloat] = Field(
        default_factory=dict
    )
    max_regenerations: NonNegativeInt = 0
    after_max_regenerations: RepeatedFailureAction

    @model_validator(mode="after")
    def _validate_policy(self) -> QualityGatePolicy:
        if len(set(self.required_check_ids)) != len(self.required_check_ids):
            raise ValueError("required_check_ids must not contain duplicates")
        if len(set(self.hard_failure_codes)) != len(self.hard_failure_codes):
            raise ValueError("hard_failure_codes must not contain duplicates")
        return self


class QualityEvaluation(Contract):
    """Immutable outcome of one check against exact artifact versions."""

    schema_version: Literal["quality-evaluation.v1"]
    evaluation_id: OpaqueId
    stage_instance_id: OpaqueId | None = None
    logical_item_key: NonEmptyStr | None = None
    scene_id: OpaqueId | None = None
    shot_id: OpaqueId | None = None
    target_artifact_ids: list[OpaqueId] = Field(min_length=1)
    target_hashes: dict[OpaqueId, Sha256Hex]
    evaluation_input_manifest_id: OpaqueId
    gate_id: NonEmptyStr
    check_id: OpaqueId
    evaluator: NonEmptyStr
    evaluator_version: NonEmptyStr
    rubric_version: NonEmptyStr | None = None
    dimensions: list[EvaluationDimension] = Field(default_factory=list)
    outcome: CheckOutcome
    confidence: Confidence | None = None
    abstained: StrictBoolean = False
    evidence: list[ExtensionObject] = Field(default_factory=list)
    estimated_cost_minor: NonNegativeInt = 0
    actual_cost_minor: NonNegativeInt | None = None
    provider_invocation_id: OpaqueId | None = None
    latency_ms: NonNegativeInt | None = None
    created_at: UTCDateTime

    @model_validator(mode="after")
    def _validate_evaluation(self) -> QualityEvaluation:
        _validate_hash_map(
            self.target_artifact_ids, self.target_hashes, require_complete=True
        )
        dimension_names = [dimension.name for dimension in self.dimensions]
        if len(set(dimension_names)) != len(dimension_names):
            raise ValueError("dimension names must be unique within an evaluation")
        if self.abstained != (self.outcome is CheckOutcome.ABSTAIN):
            raise ValueError("abstained must be true exactly when outcome is ABSTAIN")
        return self


class QualityGateResult(Contract):
    """Aggregate gate decision over exact targets and evaluation records."""

    schema_version: Literal["quality-gate-result.v1"]
    quality_gate_result_id: OpaqueId
    gate_id: OpaqueId
    gate_version: NonEmptyStr
    stage_instance_id: OpaqueId | None = None
    logical_item_key: NonEmptyStr | None = None
    target_artifact_ids: list[OpaqueId] = Field(min_length=1)
    target_hashes: dict[OpaqueId, Sha256Hex]
    required_check_ids: list[OpaqueId] = Field(min_length=1)
    evaluation_ids: list[OpaqueId] = Field(min_length=1)
    decision: GateDecision
    hard_failure_codes: list[FailureCode] = Field(default_factory=list)
    repair_scope: RepairScope | None = None
    policy_version: NonEmptyStr
    created_at: UTCDateTime
    completed_at: UTCDateTime | None = None

    @model_validator(mode="after")
    def _validate_gate_result(self) -> QualityGateResult:
        _validate_hash_map(
            self.target_artifact_ids, self.target_hashes, require_complete=True
        )
        for field_name in (
            "required_check_ids",
            "evaluation_ids",
            "hard_failure_codes",
        ):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
        if self.completed_at is not None and self.completed_at < self.created_at:
            raise ValueError("completed_at must not be earlier than created_at")
        return self


class RepairPlan(Contract):
    """Policy-approved, targeted replacement of failed artifacts or stages."""

    schema_version: Literal["repair-plan.v1"]
    repair_plan_id: OpaqueId
    source_gate_result_id: OpaqueId
    reason_codes: list[NonEmptyStr] = Field(min_length=1)
    target_artifact_ids: list[OpaqueId] = Field(default_factory=list)
    target_stage_instance_ids: list[OpaqueId] = Field(default_factory=list)
    invalidation_scope: RepairInvalidationScope
    max_attempts: PositiveInt
    created_at: UTCDateTime

    @model_validator(mode="after")
    def _validate_repair_plan(self) -> RepairPlan:
        for field_name in (
            "reason_codes",
            "target_artifact_ids",
            "target_stage_instance_ids",
        ):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
        if not self.target_artifact_ids and not self.target_stage_instance_ids:
            raise ValueError(
                "a repair plan must target at least one artifact or stage instance"
            )
        return self


__all__ = [
    "EvaluationDimension",
    "QualityCheck",
    "QualityEvaluation",
    "QualityGatePolicy",
    "QualityGateResult",
    "QualityInputManifest",
    "RepairPlan",
]
