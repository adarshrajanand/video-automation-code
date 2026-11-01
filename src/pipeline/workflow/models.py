"""Typed inputs and outputs for the pure workflow readiness engine."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipeline.contracts.artifacts import ArtifactPointer
from pipeline.contracts.execution import InputManifest, StageInstance, WorkflowRun
from pipeline.contracts.quality import QualityGateResult
from pipeline.contracts.review import HumanReview
from pipeline.contracts.vocabularies import ArtifactState, RunStatus
from pipeline.contracts.workflow import WorkflowDefinition
from pipeline.workflow.conditions import Scalar

_IMMUTABLE_CONFIG = ConfigDict(frozen=True, extra="forbid")


class ReadinessReason(StrEnum):
    """Stable machine-readable reasons a node or item is not ready."""

    CONDITION_ERROR = "CONDITION_ERROR"
    DEPENDENCY_DISABLED = "DEPENDENCY_DISABLED"
    DEPENDENCY_NOT_ACCEPTED = "DEPENDENCY_NOT_ACCEPTED"
    MISSING_STAGE_INSTANCE = "MISSING_STAGE_INSTANCE"
    MISSING_EXPECTED_MANIFEST = "MISSING_EXPECTED_MANIFEST"
    INCOMPLETE_MANIFEST = "INCOMPLETE_MANIFEST"
    EMPTY_MANIFEST = "EMPTY_MANIFEST"
    AMBIGUOUS_MANIFEST = "AMBIGUOUS_MANIFEST"
    MISSING_MANIFEST_KEYS = "MISSING_MANIFEST_KEYS"
    UNKNOWN_SELECTION_POLICY = "UNKNOWN_SELECTION_POLICY"
    CARDINALITY_MISMATCH = "CARDINALITY_MISMATCH"
    UNEXPECTED_INSTANCES = "UNEXPECTED_INSTANCES"
    ACTIVE_ATTEMPT = "ACTIVE_ATTEMPT"
    ACCEPTANCE_PENDING = "ACCEPTANCE_PENDING"
    GATE_PENDING = "GATE_PENDING"
    GATE_RESULT_MISSING = "GATE_RESULT_MISSING"
    GATE_REGENERATE = "GATE_REGENERATE"
    GATE_FAILED = "GATE_FAILED"
    HUMAN_REVIEW_PENDING = "HUMAN_REVIEW_PENDING"
    RETRY_WAIT = "RETRY_WAIT"
    UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"
    RECOVERY_PENDING = "RECOVERY_PENDING"
    TERMINAL_FAILURE = "TERMINAL_FAILURE"
    INVALIDATED = "INVALIDATED"
    CANCELLED = "CANCELLED"
    NO_ACCEPTED_OUTPUT = "NO_ACCEPTED_OUTPUT"
    INPUT_ARTIFACT_NOT_ACCEPTED = "INPUT_ARTIFACT_NOT_ACCEPTED"
    MANIFEST_REQUIRED = "MANIFEST_REQUIRED"


class BlockedReason(BaseModel):
    """One reason one node or logical item is not ready."""

    model_config = _IMMUTABLE_CONFIG

    node_id: str
    code: ReadinessReason
    message: str
    stage_instance_id: str | None = None
    logical_item_key: str | None = None


class PlannedItem(BaseModel):
    """A logical stage instance the control plane would need to create."""

    model_config = _IMMUTABLE_CONFIG

    node_id: str
    logical_item_key: str
    input_artifact_ids: tuple[str, ...] = ()
    expected_input_manifest_id: str | None = None


class ReadinessResult(BaseModel):
    """Pure, deterministic readiness decision for one workflow run."""

    model_config = _IMMUTABLE_CONFIG

    run_id: str
    workflow_id: str
    next_status: RunStatus
    ready_node_ids: tuple[str, ...] = ()
    ready_instance_ids: tuple[str, ...] = ()
    planned_items: tuple[PlannedItem, ...] = ()
    blocked: tuple[BlockedReason, ...] = ()
    accepted_node_ids: tuple[str, ...] = ()
    disabled_node_ids: tuple[str, ...] = ()
    terminal_node_ids: tuple[str, ...] = ()


class ReadinessContext(BaseModel):
    """Explicit, immutable input to one readiness evaluation.

    The engine never reads or writes a database, creates jobs, claims leases,
    writes outbox rows, selects providers, or executes stage logic. A caller
    reads durable rows first and passes them here.

    ``accepted_artifact_ids`` and active ``ACCEPTED``/``PUBLISHED`` artifact
    pointers supplement the accepted output IDs already recorded on stage
    instances. ``artifact_states`` is optional; when supplied, artifacts marked
    ``INVALIDATED``, ``SUPERSEDED`` or ``DELETED`` are never treated as usable.
    """

    model_config = _IMMUTABLE_CONFIG

    run: WorkflowRun
    workflow: WorkflowDefinition
    stage_instances: tuple[StageInstance, ...] = ()
    input_manifests: tuple[InputManifest, ...] = ()
    accepted_artifact_ids: frozenset[str] = Field(default_factory=frozenset)
    accepted_artifact_pointers: tuple[ArtifactPointer, ...] = ()
    quality_gate_results: tuple[QualityGateResult, ...] = ()
    human_reviews: tuple[HumanReview, ...] = ()
    run_input_artifact_ids: frozenset[str] = Field(default_factory=frozenset)
    artifact_states: Mapping[str, ArtifactState] = Field(default_factory=dict)
    condition_context: Mapping[str, Scalar] = Field(default_factory=dict)
    recoverable_stage_instance_ids: frozenset[str] = Field(default_factory=frozenset)

    @model_validator(mode="after")
    def _validate_context(self) -> ReadinessContext:
        if self.run.workflow_id != self.workflow.workflow_id:
            raise ValueError(
                "run.workflow_id must match workflow.workflow_id: "
                f"{self.run.workflow_id!r} != {self.workflow.workflow_id!r}"
            )
        if self.run.workflow_version != self.workflow.version:
            raise ValueError(
                "run.workflow_version must match workflow.version: "
                f"{self.run.workflow_version!r} != {self.workflow.version!r}"
            )

        node_ids = {node.node_id for node in self.workflow.nodes}
        unknown_nodes = {
            instance.node_id
            for instance in self.stage_instances
            if instance.node_id not in node_ids
        }
        if unknown_nodes:
            raise ValueError(
                "stage instances reference unknown workflow node(s): "
                + ", ".join(sorted(unknown_nodes))
            )

        for field_name, values in (
            (
                "stage_instances",
                [instance.stage_instance_id for instance in self.stage_instances],
            ),
            (
                "input_manifests",
                [manifest.manifest_id for manifest in self.input_manifests],
            ),
            (
                "accepted_artifact_pointers",
                [pointer.pointer_id for pointer in self.accepted_artifact_pointers],
            ),
            (
                "quality_gate_results",
                [result.quality_gate_result_id for result in self.quality_gate_results],
            ),
            ("human_reviews", [review.review_id for review in self.human_reviews]),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicate IDs")

        mismatched_instances = [
            instance.stage_instance_id
            for instance in self.stage_instances
            if instance.run_id != self.run.run_id
        ]
        if mismatched_instances:
            raise ValueError(
                "stage instances must belong to the context run: "
                + ", ".join(sorted(mismatched_instances))
            )
        mismatched_pointers = [
            pointer.pointer_id
            for pointer in self.accepted_artifact_pointers
            if pointer.run_id != self.run.run_id
        ]
        if mismatched_pointers:
            raise ValueError(
                "artifact pointers must belong to the context run: "
                + ", ".join(sorted(mismatched_pointers))
            )
        mismatched_reviews = [
            review.review_id
            for review in self.human_reviews
            if review.run_id != self.run.run_id
        ]
        if mismatched_reviews:
            raise ValueError(
                "human reviews must belong to the context run: "
                + ", ".join(sorted(mismatched_reviews))
            )
        return self


__all__ = [
    "BlockedReason",
    "PlannedItem",
    "ReadinessContext",
    "ReadinessReason",
    "ReadinessResult",
]
