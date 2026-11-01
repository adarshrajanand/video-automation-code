# AI Video Automation Pipeline — Contracts and Data Model

**Status:** Canonical implementation contract

**Purpose:** Define the typed boundaries and durable records that allow coding agents to implement the pipeline without inventing incompatible state models.

## 1. Contract rules

1. Pydantic models are the Python source of truth for Python-facing contracts.
2. JSON Schema is the cross-language boundary for renderer and external payloads.
3. Every contract has a schema version.
4. Every artifact-producing operation records inputs, configuration, producer version, and output hashes.
5. `dict[str, Any]` is permitted only for explicitly extensible metadata, not for core state transitions.
6. Mutable defaults use `Field(default_factory=...)`.
7. IDs are opaque strings; code must not parse semantic meaning from an ID.
8. Timestamps are UTC and serialized as ISO-8601.
9. Monetary amounts use decimal-safe representation or integer minor units; never binary floating point for accounting decisions.
10. Secrets and raw sensitive payloads are excluded from persisted fingerprints and ordinary logs.

## 1.1 How to read the model catalog

The Python blocks below are contract shapes, not a recommendation to put every
class in one module or database table. A model answers one durable question:
what was requested, what was attempted, what was produced, what evidence was
checked, or what decision was made. The table maps the groups to their role in
the run lifecycle.

| Model group | What it means | Typical handoff |
|---|---|---|
| `Contract`, `MetadataContract`, `UTCRecord` | Shared serialization, versioning, and timestamp rules | Every other contract |
| `FailureCode`, `NormalizedError` | A stable explanation of why work failed and whether it can be retried or reconciled | Capability result, attempt, recovery decision |
| `RunOverrides`, `EffectiveConfig` | Requested settings and the immutable resolved settings for one run | Run creation, routing, reproducibility |
| `InputSelector`, `ConditionExpression`, `CardinalityPolicy`, `StageNode`, `WorkflowDefinition` | The validated workflow graph and how each node selects and expands work | Workflow loader and readiness evaluator |
| `WorkflowRun`, `StageInstance`, `StageAttempt`, `InputManifest` | Durable logical work, its attempts, and the expected inputs for fan-in/fan-out | Workflow engine and execution runtime |
| `RetryPolicy`, `RecoveryPolicy`, `RecoveryDecision` | What the control plane does after retryable, unknown, quality, or repeated failure | Recovery and repair handling |
| `Job`, `Lease` | Claimable delivery work and temporary ownership of that work | Dispatcher and worker |
| `CapabilityRequest`, `ExecutionContext`, `CapabilityExecution`, `CapabilityResult` | The provider-independent request/attempt/result boundary for a capability | Stage executor and capability adapter |
| `UsageRecord`, `IdempotencyRecord`, `BudgetReservation` | Cost, duplicate-suppression, and spend-control evidence | Router, provider adapter, recovery |
| `RoutingContext`, `RoutingDecision`, `WorkloadRequirements`, `ResourceConstraints`, `ResourceAssignment`, `ProviderInvocation` | Which implementation/provider/resource was selected and what external call occurred | Router, resource broker, provider adapter |
| `Artifact`, `ArtifactDependency`, `ArtifactPointer`, `InvalidationRequest`, `InvalidationResult` | Immutable outputs, their lineage, active versions, and scoped replacement | Artifact store and repair planner |
| `QualityCheck`, `QualityInputManifest`, `QualityEvaluation`, `QualityGatePolicy`, `QualityGateResult`, `RepairPlan` | Individual checks, the exact inputs checked, aggregate decisions, and targeted repair | Quality subsystem and workflow engine |
| `HumanReview`, `HumanReviewDecision`, `PublicationRequest`, `PublicationAttempt` | Durable human decisions and the exact approved hashes allowed to publish | Review queue and publishing adapter |
| `EventEnvelope`, `OutboxMessage`, `InboxReceipt` | Serialized facts/commands plus at-least-once delivery state | Workflow event history and dispatcher |
| `BudgetPolicy`, `SystemPolicy`, `DomainProfile`, `ChannelProfile` | Policy layers used to resolve effective behavior for a run | Configuration resolver |
| `ProductionIdea`, `ContentPackage`, `Episode`, `Cut`, `Sequence`, `Scene`, `Shot` | Editorial hierarchy from idea to a specific long-form or short cut | Content stages and composition |
| `AssetProvenance`, `SourceAsset`, `AssetInstance`, `LayerInstance` | What media was obtained, where it came from, and where it is placed | Asset acquisition, composition, rights checks |
| `SpeechManifest`, `AudioTiming`, `Composition*` models | Speech alignment and renderer-neutral timeline data | Speech, composition, and renderer |
| `CompositionSpec`, `RenderChunkManifest`, `AssemblyManifest`, `RenderProfile`, `ShortSelectionManifest` | Immutable renderer input, chunk fan-in, output profile, and short derivation | Rendering, assembly, short derivative |
| `SourceRef`, `SourceSnapshot`, `Evidence`, `Claim`, `Script*` models | Research provenance, claim support, narration, and visual intent | Research, script, and quality stages |

Enums such as `RunStatus`, `StageExecutionStatus`, `AttemptStatus`,
`AcceptanceStatus`, `GateDecision`, and `CheckOutcome` are state vocabularies.
They are not separate workflow records; they constrain fields on the records
that own the state.

## 1.2 Attribute semantics and lookup rules

The model catalog explains what each model group is for. This section explains
how to read an individual attribute and how to find the record again later.
Unless a model-specific table says otherwise, use these conventions:

| Attribute pattern | Meaning | How to identify or interpret it |
|---|---|---|
| `schema_version` | Version of the serialized shape | Validate before deserializing; it is not an entity revision |
| `*_id` | Opaque identity of one durable record or referenced record | Use the exact ID for joins and lookups; do not parse its text |
| `*_ids` | References to multiple records | The owning model defines whether order matters; an empty list means known empty |
| `*_key` | Idempotency, logical-item, or lookup key rather than a record ID | Read the field's model-specific scope; keys are not globally unique by default |
| `logical_item_key` | Stable work-item identity within a run and workflow node | Join with `(run_id, node_id, logical_item_key)` |
| `version` | Revision of the entity or editorial object | Interpret with the model's identity scope; do not confuse with `schema_version` |
| `*_version` | Version of the referenced implementation, policy, evaluator, model, prompt, rubric, or script | Persist it with the result so the old run remains reproducible |
| `attempt_number` | Transport/execution retry ordinal for one logical work item | Scope to the parent attempt-bearing record; it is not a quality score or artifact version |
| `*_hash`, `sha256`, `content_hash` | Fingerprint of bytes or canonical serialized content | The model must state what was hashed; equal hashes mean equal addressed content under that procedure |
| `config_hash`, `settings_hash` | Fingerprint of configuration/settings | Look up the corresponding snapshot or configuration record; do not treat it as media content identity |
| `request_fingerprint`, `payload_fingerprint` | Fingerprint used for duplicate suppression or request comparison | `request_fingerprint` covers behavior-affecting request inputs; `payload_fingerprint` is the payload-only subset |
| `*_at` | UTC instant | Parse as an ISO-8601 timestamp, not a duration |
| `*_seconds`, `*_milliseconds`, `*_bytes`, `*_minor` | Explicit unit-bearing scalar | The suffix is part of the contract; monetary `*_minor` values also need a currency policy |
| `start_frame`, `end_frame` | Media interval boundaries | Use the render profile's timebase; intervals are half-open: `[start_frame, end_frame)` |
| `status` | Lifecycle of the record or execution | The owning subsystem controls transitions |
| `state` | Lifecycle of an artifact or pointer | It is not interchangeable with execution `status` |
| `outcome` | Result of one check/evaluator | It does not by itself unlock downstream workflow |
| `decision` | Aggregate policy, recovery, or human action | It is the control-plane result derived from evidence |
| `null` / `[]` / `{}` | Unknown/not applicable, known empty collection, known empty mapping | Persisted records must not use omission to mean a fourth hidden state |

### InputSelector: selecting upstream records

`InputSelector` is part of a static `StageNode`. It describes **where a node
gets eligible inputs**; it does not itself identify the final runtime artifact
set. The static selector is identified by:

```text
(workflow_id, workflow_version, node_id)
```

The resolved runtime selection is identified by `InputManifest.manifest_id`.
That manifest records the actual artifact IDs and expected count used by one
stage instance.

| Attribute | Meaning | How to identify it later |
|---|---|---|
| `kind` | Input namespace: run input, dependency outputs, a manifest-based selection, or pointers | Read with the workflow node; it does not encode ordering or fan-out |
| `dependency_node_ids` | Upstream **workflow node IDs**, not stage names and not runtime `stage_instance_id` values | Resolve through `(workflow_id, workflow_version, node_id)` and then the current run's logical item scope |
| `artifact_types` | Optional filter on eligible output artifact types | An empty list means no artifact-type restriction; it is a filter, not an identity |
| `selection_policy` | Named rule for choosing eligible outputs from the source namespace | Resolve through the workflow/policy registry; it is not a provider route and should not be interpreted as arbitrary code |

For example, a composition node may select the accepted outputs of the visual
plan, asset, and speech nodes. The selector names those upstream nodes; the
runtime `InputManifest` records exactly which script, asset, and audio artifact
IDs were selected. A later run must not re-evaluate the selector against moving
`CURRENT` pointers and assume it got the same inputs.

Do not confuse `StageNode.depends_on` with
`InputSelector.dependency_node_ids`. `depends_on` is the workflow-DAG
prerequisite used for readiness. `dependency_node_ids` describes the upstream
node outputs this selector will read. They may contain the same node IDs, but
they answer different questions and must not be collapsed into one field.

### Lease: temporary ownership of a job

`Lease` answers: **which worker is currently authorized to commit work for this
job, until when, and under which ownership term?** It is not the job itself, a
provider invocation, or a user lock.

| Attribute | Meaning | How to identify or validate it later |
|---|---|---|
| `job_id` | The claimable `Job` record temporarily owned by the worker | Join to `Job.job_id`; only one active lease should exist for a job |
| `owner_id` | Stable worker-process or worker-instance identity | Compare with the claimant on commit; it is not a user ID or provider ID |
| `fencing_token` | Monotonically increasing ownership term for that job | Compare-and-set it on every heartbeat/result commit; a stale token must be rejected. It is a concurrency token, not the lease's record ID |
| `acquired_at` | UTC time at which ownership was granted | Audit the beginning of this lease term |
| `heartbeat_at` | UTC time of the last heartbeat accepted by the control plane | Use it for expiry/reclamation decisions; it is not merely the time a worker attempted a heartbeat |
| `expires_at` | Authoritative UTC deadline after the last successful renewal | A lease is valid only before this deadline and while the owner/token match |

With the current illustrative shape, the lease term can be looked up by
`(job_id, fencing_token)`, while the active term is found by `job_id`. The
current shape does not include a `lease_id`, `status`, or release timestamp. If
lease history must be independently addressed after a job has had many lease
terms, add an opaque `lease_id` and explicit lifecycle fields before
implementation; do not pretend that `owner_id` is a durable lease identity.
Likewise, `Job.claimed_by` and `Job.lease_expires_at` should be treated as
read-only projections of the active lease if they are retained, not as a second
source of ownership truth.

### High-risk attributes in the other model groups

These fields deserve explicit attention during implementation because their
names alone are easy to misread.

| Attribute | Meaning | Later lookup or invariant |
|---|---|---|
| `StageNode.node_id` | Stable identifier of a node in one workflow revision | Scope by `(workflow_id, workflow_version)`; it is not a runtime stage-instance ID |
| `StageNode.stage_name` | Canonical registered stage responsibility, such as `speech_generation` | Resolve against `registries/stages.yaml`; aliases are not valid in new workflow definitions |
| `StageNode.depends_on` | Workflow graph edges that must be satisfied before readiness | Values are other `node_id` values in the same workflow; cycles are invalid |
| `StageInstance.logical_item_key` | The item this node is processing, such as `episode` or `scene_03` | Scope by `(run_id, node_id)`; it lets retries address the same logical work |
| `StageInstance.expected_input_manifest_id` | Frozen set of inputs that readiness expects this stage instance to consume | Join to `InputManifest.manifest_id`; do not replace it with “whatever is currently queued” |
| `StageInstance.active_attempt_id` | Current attempt selected for execution/recovery | Join to one `StageAttempt`; old attempts remain history |
| `StageInstance.accepted_output_artifact_ids` | Exact artifact versions that passed the required gate for this logical work | Treat as versioned references, not just artifact types |
| `StageAttempt.attempt_number` | Transport/execution retry ordinal | Scope to one `stage_instance_id`; it does not count quality regenerations |
| `StageAttempt.quality_regeneration_number` | Number of quality-driven replacement cycles | Keep separate from `attempt_number`; a repair plan should explain why it changed |
| `StageAttempt.worker_id` | Worker that executed or claimed the attempt | Operational attribution only; ownership validity comes from the lease/fencing check |
| `StageAttempt.failure_code` | Registered reason for failed execution | Resolve against `registries/failure_codes.yaml`; do not use free-form recovery strings |
| `Job.idempotency_key` | Stable key for one logical delivery operation | Unique lookup that makes duplicate triggers/deliveries harmless |
| `Job.available_at` | Earliest time the dispatcher may offer the job | A future value means delayed retry/defer, not a missing job |
| `Job.delivery_count` | Number of delivery/claim attempts by the dispatcher | Transport evidence; not the same as provider or quality attempt counts |
| `CapabilityRequest.payload_fingerprint` | Fingerprint of the capability payload being requested | Compare requests without logging sensitive payloads; keep distinct from full request fingerprint |
| `CapabilityRequest.idempotency_key` | Duplicate-suppression key for the external-capability operation | Join to `IdempotencyRecord` and any `ProviderInvocation` |
| `CapabilityExecution.implementation_version` | Version of the selected capability implementation | Persist with the result so a later run can explain which code path ran |
| `CapabilityExecution.status` | Control-plane lifecycle of the capability execution | The execution record owns this status; `CapabilityResult` reports the returned outcome |
| `Artifact.logical_slot` | Role of an output within its run, such as `script` or `scene_03` | Scope by `run_id` or content-package namespace; it is not globally unique |
| `Artifact.version` | Replacement revision for one logical slot | Look up history by `(run_id, logical_slot, version)`; bytes remain immutable |
| `Artifact.producer_attempt_id` | Attempt that created the artifact | Join to provenance and the exact execution evidence |
| `Artifact.config_hash` | Effective configuration used to create the artifact | Join to the immutable effective-config snapshot, not current settings |
| `ArtifactPointer.pointer_type` | Role of the selected pointer: `CURRENT`, `ACCEPTED`, or `PUBLISHED` | The role determines what may consume it; it does not change artifact identity |
| `QualityInputManifest.target_hashes` | Hashes of the exact target artifact bytes checked by a gate | Keys are `artifact_id`; values are the corresponding `sha256` values |
| `QualityEvaluation.evaluation_input_manifest_id` | Exact input manifest used by one evaluator invocation | Prevents a later re-run from being mistaken for the original evidence |
| `QualityEvaluation.abstained` | Whether the evaluator deliberately declined to judge | Must equal `outcome == ABSTAIN`; it is not the same as `NOT_APPLICABLE` |
| `QualityGateResult.evaluation_ids` | Individual evaluations included in the aggregate decision | Every required check must be represented before a gate can pass |
| `QualityGateResult.repair_scope` | Smallest policy-approved boundary to regenerate or review | It controls descendant invalidation; it is not merely a display label |
| `EventEnvelope.correlation_id` | Trace ID shared by related work in one operational flow | Use for logs/traces; it is not an idempotency key |
| `EventEnvelope.causation_id` | Event that directly caused this event | Use to reconstruct causal history; it may be null for a root event |
| `OutboxMessage.delivery_attempts` | Number of attempts to deliver the same committed event | Transport evidence; event consumers still deduplicate by `event_id` |
| `SpeechManifest.strategy` | Whether audio came from one continuous pass or scene-level artifacts | Selects interpretation of the artifact references; both modes still require aligned scene timing |
| `SpeechManifest.narration_text_hashes` | Approved script text hash for each scene represented in the audio | Composition rejects a speech/visual/script mismatch |
| `SpeechManifest.alignment_artifact_id` | Artifact containing word/scene timing evidence | Join to `AudioTiming` records and use it as the timing source |
| `CompositionSpec.render_manifest_hash` | Fingerprint of the exact frozen renderer input | A renderer must be able to reproduce the same input from this manifest |
| `CompositionSpec.resolved_artifacts` | Exact artifact IDs, hashes, URIs, and metadata resolved before rendering | Do not query mutable pointers during render |
| `CompositionSpec.fps` and `timebase` | Frame conversion rules for all ranges in the manifest | Every `start_frame`/`end_frame` value must use this timebase |

### Identity map for later lookup

These are the minimum lookup rules for the most important durable records:

| Record | Primary identity or lookup tuple | What the tuple distinguishes |
|---|---|---|
| `WorkflowDefinition` | `(workflow_id, version)` | One immutable workflow definition revision |
| `StageNode` | `(workflow_id, workflow_version, node_id)` | One node inside one workflow revision |
| `WorkflowRun` | `run_id`; idempotent creation by `run_key` | One execution of a workflow; `run_key` prevents accidental duplicate runs |
| `StageInstance` | `(run_id, node_id, logical_item_key)` | One logical work item, independent of retries |
| `StageAttempt` | `attempt_id`; history by `(stage_instance_id, attempt_number)` | One execution try for a logical stage instance |
| `Job` | `job_id`; duplicate suppression by `idempotency_key` | One claimable delivery record and its logical operation |
| `Lease` | Current shape: `(job_id, fencing_token)`; active lookup by `job_id` | One ownership term for a job; the fencing token prevents stale workers from committing |
| `Artifact` | `artifact_id`; version history by `(run_id, logical_slot, version)` | One immutable output and its replacement history |
| `ArtifactPointer` | `(run_id, logical_slot, pointer_type, active)` | Which artifact is currently selected for a logical slot |
| `QualityEvaluation` | `evaluation_id`; evidence key from target artifact hashes plus check/evaluator versions | One check result against exact artifact versions |
| `QualityGateResult` | `quality_gate_result_id` | One aggregate gate decision for exact target/evaluation records |
| `EventEnvelope` | `event_id`; delivery deduplication by `(consumer_id, event_id)` | One event fact/command and one consumer's receipt |
| `BudgetReservation` | `reservation_id`; scoped uniqueness by `(idempotency_key, scope_type, scope_id)` | One spend reservation at one budget scope |

If a future implementation needs a different identity rule, update this table,
the model, the database constraint, and the relevant acceptance test together.

## 1.3 Worked example: one scene through the contracts

This is a relationship example, not a complete payload. It shows why several
small models exist instead of one large `StageExecution` object.

```text
RunCreateRequest(run_key="se-demo:2026-10-21")
  -> EffectiveConfig(config_hash="cfg_hash_01")
  -> WorkflowRun(run_id="run_01", status=RUNNING)
  -> StageInstance(node_id="script", logical_item_key="episode")
  -> StageAttempt(attempt_id="attempt_script_01", status=SUCCEEDED)
  -> Artifact(artifact_id="artifact_script_v1", logical_slot="script", state=ACCEPTED)
  -> StageInstance(node_id="speech", logical_item_key="scene_03")
  -> Job(idempotency_key="speech:run_01:scene_03:v1")
  -> Lease(owner_id="worker_01", fencing_token=7)
  -> CapabilityRequest(capability="speech_generation")
  -> CapabilityExecution(status=SUCCEEDED)
  -> CapabilityResult(artifact_ids=["artifact_audio_scene_03"])
  -> ArtifactDependency(parent_artifact_id="artifact_script_v1", child_artifact_id="artifact_audio_scene_03")
  -> QualityInputManifest(gate_id="speech_gate_v1")
  -> QualityEvaluation(check_id="transcript_fidelity_v1", outcome=PASS)
  -> QualityGateResult(gate_id="speech_gate_v1", decision=PASS)
  -> CompositionAuthoringSpec(...)
  -> CompositionSpec(schema_version="render-manifest.v1")
  -> RenderChunkManifest(...)
  -> AssemblyManifest(...)
```

The important distinctions are:

- `StageInstance` says **what logical work must exist**; `StageAttempt` says
  **which try ran**.
- `Job` says **what can be claimed**; `Lease` says **who temporarily owns it**.
- `CapabilityRequest` says **what a stage asked for**;
  `CapabilityExecution` records **how it ran**; `CapabilityResult` records
  **what came back**.
- `Artifact` is immutable output. `ArtifactPointer` can move to a replacement
  without changing the old artifact.
- `QualityEvaluation` is one check. `QualityGateResult` is the aggregate
  decision that controls downstream readiness.
- `CompositionAuthoringSpec` is a nested authoring structure;
  `CompositionSpec` is the frozen renderer manifest.

## 2. Common types

Illustrative Python shapes:

```python
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str


class MetadataContract(Contract):
    model_config = ConfigDict(extra="allow")


class UTCRecord(Contract):
    created_at: datetime
    updated_at: datetime | None = None


class FailureCode(StrEnum):
    VALIDATION = "EXEC.VALIDATION"
    AUTHENTICATION = "EXEC.AUTHENTICATION"
    AUTHORIZATION = "EXEC.AUTHORIZATION"
    RATE_LIMIT = "EXEC.RATE_LIMIT"
    QUOTA = "EXEC.QUOTA"
    TRANSIENT_PROVIDER = "EXEC.TRANSIENT_PROVIDER"
    PERMANENT_PROVIDER = "EXEC.PERMANENT_PROVIDER"
    TIMEOUT_UNKNOWN = "EXEC.TIMEOUT_UNKNOWN"
    MEDIA_INTEGRITY = "MEDIA.TECHNICAL_INTEGRITY"
    QUALITY = "QUALITY.GENERIC"
    HUMAN_REVIEW = "HUMAN.REVIEW_REQUIRED"
    INTERNAL = "EXEC.INTERNAL"


class NormalizedError(Contract):
    schema_version: Literal["normalized-error.v1"]
    code: str
    category: Literal[
        "VALIDATION",
        "AUTHENTICATION",
        "AUTHORIZATION",
        "RATE_LIMIT",
        "QUOTA",
        "TRANSIENT",
        "PERMANENT",
        "UNKNOWN_OUTCOME",
        "MEDIA",
        "QUALITY",
        "BUDGET",
        "CONFIGURATION",
        "INTERNAL",
    ]
    retryable: bool
    reconciliation_required: bool = False
    severity: Literal["INFO", "MINOR", "MAJOR", "CRITICAL"] = "MAJOR"
    provider_status: str | None = None
    message: str
    safe_details: dict[str, Any] = Field(default_factory=dict)


# Failure-code namespaces prevent execution errors and quality defects from
# being treated as the same kind of recovery event.
# EXEC.TRANSIENT_PROVIDER, EXEC.TIMEOUT_UNKNOWN,
# MEDIA.DECODE_ERROR, QUALITY.UNSUPPORTED_CLAIM,
# QUALITY.CAPTION_OVERFLOW, POLICY.BUDGET_EXCEEDED
```

The actual project may use separate files and richer enums. The important properties are strict core fields, explicit versions, normalized failures, and stable serialization.

## 3. Layered configuration

Configuration is resolved before a run begins:

```text
SystemPolicy
    ↓
DomainProfile
    ↓
ChannelProfile
    ↓
WorkflowDefinition
    ↓
RunOverrides
    ↓
Runtime Context / Previous Results
    ↓
EffectiveConfig
```

```python
class RunOverrides(Contract):
    schema_version: Literal["run-overrides.v1"]
    locale: str | None = None
    target_duration_seconds: int | None = None
    variant_count: int | None = None
    max_cost_minor: int | None = None
    enabled_optional_stages: list[str] = Field(default_factory=list)
    output_profile_ids: list[str] | None = None
    quality_profile_id: str | None = None


class EffectiveConfig(Contract):
    schema_version: Literal["effective-config.v1"]
    effective_config_id: str
    system_policy_version: str
    domain_profile_id: str
    domain_profile_version: str
    channel_profile_id: str
    channel_profile_version: str
    workflow_id: str
    workflow_version: str
    run_overrides: RunOverrides
    resolved_values: dict[str, Any] = Field(default_factory=dict)
    source_map: dict[str, str] = Field(default_factory=dict)
    config_hash: str
    snapshot_artifact_id: str | None = None
```

The effective hash must be calculated from canonical JSON with sorted keys and normalized values. It must not include secrets, current timestamps, or transient worker IDs.

## 4. Workflow contracts

```python
class InputSelector(Contract):
    schema_version: Literal["input-selector.v1"]
    # Selects the source namespace, not the expansion/cardinality behavior.
    kind: Literal["RUN_INPUT", "DEPENDENCY_OUTPUTS", "MANIFEST", "POINTERS"]
    # Workflow node IDs in the same workflow definition; not stage instances.
    dependency_node_ids: list[str] = Field(default_factory=list)
    # Optional filter on the types of artifacts eligible for selection.
    artifact_types: list[str] = Field(default_factory=list)
    # Named selection rule resolved by workflow/policy configuration.
    selection_policy: str | None = None


class ConditionExpression(Contract):
    schema_version: Literal["condition-expression.v1"]
    operator: Literal["ALWAYS", "ALL", "ANY", "EQUALS", "IN", "GREATER_THAN", "EXISTS"]
    operands: list[Any] = Field(default_factory=list)


class CardinalityPolicy(Contract):
    schema_version: Literal["cardinality.v1"]
    mode: Literal["one_to_one", "one_to_many", "many_to_one", "many_to_many"]
    count: int | None = None
    selection_policy: str | None = None
    expected_manifest_id: str | None = None


class StageNode(Contract):
    schema_version: Literal["stage-node.v1"]
    node_id: str
    stage_name: str
    depends_on: list[str] = Field(default_factory=list)
    input_selector: InputSelector
    cardinality: CardinalityPolicy
    quality_gate_id: str | None = None
    recovery_policy_id: str | None = None
    enabled_when: ConditionExpression | None = None
    implementation_version: str


class WorkflowDefinition(Contract):
    schema_version: Literal["workflow-definition.v1"]
    workflow_id: str
    version: str
    nodes: list[StageNode]
    policy_ids: list[str] = Field(default_factory=list)
```

`count` may be `null` for `one_to_many` only when `selection_policy` names an
explicit child manifest. The manifest must declare the expected child logical
keys before fan-out begins. `many_to_one` requires an expected input manifest;
it may not use queue emptiness as a completion signal.

Definition validation must reject:

- duplicate node IDs;
- missing dependency nodes;
- cycles;
- invalid cardinality settings;
- unknown stage names;
- unknown quality/recovery policy IDs;
- selectors that refer to unavailable dependency outputs;
- disabled required roots with no input path.

## 5. Run and execution contracts

```python
class RunStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    WAITING_HUMAN = "WAITING_HUMAN"
    WAITING_RETRY = "WAITING_RETRY"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StageExecutionStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    WAITING_HUMAN = "WAITING_HUMAN"
    WAITING_RETRY = "WAITING_RETRY"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"
    INVALIDATED = "INVALIDATED"


class AttemptStatus(StrEnum):
    CREATED = "CREATED"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    CANCELLED = "CANCELLED"


class AcceptanceStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    PASSED = "PASSED"
    REGENERATE = "REGENERATE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    FAILED = "FAILED"


class WorkflowRun(Contract):
    schema_version: Literal["workflow-run.v1"]
    run_id: str
    run_key: str
    workflow_id: str
    workflow_version: str
    effective_config_id: str
    effective_config_hash: str
    status: RunStatus
    content_package_id: str
    created_at: datetime
    updated_at: datetime


class RunCreateRequest(Contract):
    schema_version: Literal["run-create-request.v1"]
    run_key: str
    workflow_id: str
    workflow_version: str
    content_package_id: str
    effective_config_overrides: RunOverrides
    duplicate_policy: Literal["RETURN_EXISTING", "REJECT", "CREATE_NEW"] = "RETURN_EXISTING"


class StageInstance(Contract):
    schema_version: Literal["stage-instance.v1"]
    stage_instance_id: str
    run_id: str
    node_id: str
    logical_item_key: str
    execution_status: StageExecutionStatus
    acceptance_status: AcceptanceStatus
    quality_gate_id: str | None = None
    quality_gate_result_id: str | None = None
    expected_input_manifest_id: str | None = None
    active_attempt_id: str | None = None
    accepted_output_artifact_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class StageAttempt(Contract):
    schema_version: Literal["stage-attempt.v1"]
    attempt_id: str
    stage_instance_id: str
    attempt_number: int
    quality_regeneration_number: int = 0
    status: AttemptStatus
    input_artifact_ids: list[str] = Field(default_factory=list)
    output_artifact_ids: list[str] = Field(default_factory=list)
    worker_id: str | None = None
    lease_expires_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    failure_code: FailureCode | None = None
    failure_message: str | None = None


class InputManifest(Contract):
    schema_version: Literal["input-manifest.v1"]
    manifest_id: str
    stage_instance_id: str
    expected_artifact_slots: list[str] = Field(default_factory=list)
    resolved_artifact_ids: list[str] = Field(default_factory=list)
    expected_count: int | None = None
    complete: bool = False
    created_at: datetime


class RetryPolicy(Contract):
    schema_version: Literal["retry-policy.v1"]
    policy_id: str
    max_attempts: int
    initial_backoff_seconds: float
    max_backoff_seconds: float
    jitter_ratio: float
    retryable_categories: list[str] = Field(default_factory=list)


class RecoveryPolicy(Contract):
    schema_version: Literal["recovery-policy.v1"]
    policy_id: str
    retry_policy_id: str
    on_unknown_outcome: Literal["RECONCILE", "RETRY", "WAIT_HUMAN", "FAIL"]
    on_quality_failure: Literal["REGENERATE", "HUMAN_REVIEW", "FAIL"]
    on_repeated_failure: Literal["HUMAN_REVIEW", "FAIL"]
```

`StageInstance` is logical work. `StageAttempt` is a retry/reassignment. Do not use one record for both concepts.

Execution and quality acceptance are deliberately separate. An attempt may be
`SUCCEEDED` while its stage instance has `acceptance_status=PENDING`.
Downstream readiness requires `execution_status=SUCCEEDED` plus
`acceptance_status=PASSED` (or `NOT_REQUIRED` for a node without a gate).
`PASSED` means quality-accepted; it does not mean human-approved for
publication.

The state meanings are normative:

| Field | Meaning | Owner |
|---|---|---|
| `StageInstance.execution_status` | Current durable execution/recovery state of the logical work item | Workflow Engine |
| `StageInstance.acceptance_status` | Current quality acceptance state for the active output versions | Quality subsystem, applied by Workflow Engine |
| `StageAttempt.status` | State of one claimable execution attempt | Execution runtime |
| `HumanReview.status` | State of a durable reviewer request | Review queue |

Quality regeneration creates a new attempt and new output artifact versions
while retaining the same logical stage instance and an explicit repair
relationship. Transport retry and quality regeneration must have separate
counters; `attempt_number` alone must not be used as both.

## 6. Job and lease contracts

```python
class Job(Contract):
    schema_version: Literal["job.v1"]
    job_id: str
    attempt_id: str
    queue_name: str
    status: Literal["READY", "CLAIMED", "ACKED", "RETRY", "DEAD_LETTER", "CANCELLED"]
    idempotency_key: str
    available_at: datetime
    claimed_by: str | None = None
    lease_expires_at: datetime | None = None
    delivery_count: int = 0


class Lease(Contract):
    schema_version: Literal["lease.v1"]
    # The claimable job temporarily owned by this lease term.
    job_id: str
    # Stable worker-instance identity; not a user or provider identity.
    owner_id: str
    # Monotonic per-job ownership term used to fence stale workers.
    fencing_token: int
    # UTC time when the control plane granted this ownership term.
    acquired_at: datetime
    # Absolute UTC deadline after the last successful renewal.
    expires_at: datetime
    # UTC time of the last heartbeat accepted by the control plane.
    heartbeat_at: datetime | None = None
```

Claiming must use an atomic compare-and-set or transactionally locked update. A worker must verify that it still owns the lease before committing a result.

## 7. Capability contracts

```python
class CapabilityRequirements(Contract):
    schema_version: Literal["capability-requirements.v1"]
    capability: str
    required_features: list[str] = Field(default_factory=list)
    locale: str | None = None
    quality_requirement: str | None = None
    latency_requirement: str | None = None
    data_classification: str = "PUBLIC"
    cost_limit_minor: int | None = None


class CapabilityRequest(Contract):
    schema_version: Literal["capability-request.v1"]
    capability_execution_id: str
    capability: str
    operation_version: str
    input_artifact_ids: list[str] = Field(default_factory=list)
    payload_fingerprint: str
    requirements: CapabilityRequirements
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_schema_version: str
    runtime_context: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str


class ExecutionContext(Contract):
    schema_version: Literal["execution-context.v1"]
    run_id: str
    stage_instance_id: str
    attempt_id: str
    effective_config_id: str
    correlation_id: str
    timeout_seconds: int
    allowed_data_classification: str


class UsageRecord(Contract):
    schema_version: Literal["usage.v1"]
    provider: str
    model: str | None = None
    input_units: int | None = None
    output_units: int | None = None
    runtime_seconds: float | None = None
    estimated_cost_minor: int = 0
    actual_cost_minor: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CapabilityResult(Contract):
    schema_version: Literal["capability-result.v1"]
    capability_execution_id: str
    status: Literal["SUCCEEDED", "FAILED", "UNKNOWN"]
    artifact_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    usage: UsageRecord | None = None
    normalized_error: NormalizedError | None = None


class CapabilityExecution(Contract):
    schema_version: Literal["capability-execution.v1"]
    capability_execution_id: str
    attempt_id: str
    capability: str
    operation_version: str
    implementation_version: str
    prompt_version: str | None = None
    rubric_version: str | None = None
    settings_hash: str | None = None
    tool_versions: dict[str, str] = Field(default_factory=dict)
    request_fingerprint: str
    idempotency_key: str
    routing_decision_id: str | None = None
    resource_assignment_id: str | None = None
    status: Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED", "UNKNOWN"]
    input_artifact_ids: list[str] = Field(default_factory=list)
    output_artifact_ids: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    normalized_error: NormalizedError | None = None


class IdempotencyRecord(Contract):
    schema_version: Literal["idempotency-record.v1"]
    idempotency_key: str
    capability: str
    request_fingerprint: str
    provider: str | None = None
    status: Literal["RESERVED", "IN_FLIGHT", "SUCCEEDED", "FAILED", "UNKNOWN", "RECONCILED"]
    capability_execution_id: str
    provider_invocation_id: str | None = None
    provider_operation_id: str | None = None
    result_artifact_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime | None = None


class BudgetReservation(Contract):
    schema_version: Literal["budget-reservation.v1"]
    reservation_id: str
    scope_type: Literal["SYSTEM", "MONTH", "RUN", "STAGE", "CAPABILITY"]
    scope_id: str
    idempotency_key: str
    estimated_cost_minor: int
    reserved_cost_minor: int
    actual_cost_minor: int | None = None
    status: Literal["RESERVED", "SETTLED", "RELEASED", "UNKNOWN"]
    created_at: datetime
    settled_at: datetime | None = None
```

## 8. Routing and provider contracts

```python
class RoutingContext(Contract):
    schema_version: Literal["routing-context.v1"]
    capability_request: CapabilityRequest
    effective_config_hash: str
    provider_health: dict[str, Any] = Field(default_factory=dict)
    provider_usage: dict[str, Any] = Field(default_factory=dict)
    previous_results: list[dict[str, Any]] = Field(default_factory=list)
    attempt: int
    budget_remaining_minor: int | None = None


class RoutingDecision(Contract):
    schema_version: Literal["routing-decision.v1"]
    routing_decision_id: str
    capability: str
    implementation: str
    implementation_version: str
    provider: str
    model: str | None = None
    provider_config_hash: str
    fallback_chain: list[str] = Field(default_factory=list)
    policy_version: str
    reason_codes: list[str] = Field(default_factory=list)
    candidate_exclusions: list[dict[str, Any]] = Field(default_factory=list)
    budget_context: dict[str, Any] = Field(default_factory=dict)
    usage_context: dict[str, Any] = Field(default_factory=dict)
    attempt: int
    data_classification: str
    paid_fallback_authorized: bool = False
    created_at: datetime


class WorkloadRequirements(Contract):
    schema_version: Literal["workload-requirements.v1"]
    cpu_cores: int | None = None
    memory_mb: int | None = None
    vram_mb: int | None = None
    expected_runtime_seconds: int | None = None
    required_tools: list[str] = Field(default_factory=list)
    data_classification: str = "PUBLIC"


class ResourceConstraints(Contract):
    schema_version: Literal["resource-constraints.v1"]
    allowed_placement_classes: list[str] = Field(default_factory=list)
    max_runtime_seconds: int | None = None
    max_cost_minor: int | None = None
    network_required: bool = False


class ResourceAssignment(Contract):
    schema_version: Literal["resource-assignment.v1"]
    assignment_id: str
    placement_class: str
    worker_pool: str
    implementation_version: str
    constraints_hash: str
    created_at: datetime


class ProviderInvocation(Contract):
    schema_version: Literal["provider-invocation.v1"]
    invocation_id: str
    capability_execution_id: str
    provider: str
    operation_id: str | None = None
    idempotency_key: str
    request_fingerprint: str
    status: Literal["STARTED", "SUCCEEDED", "FAILED", "UNKNOWN"]
    started_at: datetime
    finished_at: datetime | None = None
```

## 9. Artifact contracts

```python
class ArtifactState(StrEnum):
    GENERATED = "GENERATED"
    ACCEPTED = "ACCEPTED"
    SUPERSEDED = "SUPERSEDED"
    INVALIDATED = "INVALIDATED"
    DELETED = "DELETED"


class Artifact(Contract):
    schema_version: Literal["artifact.v1"]
    artifact_id: str
    run_id: str
    logical_slot: str
    artifact_type: str
    version: int
    uri: str
    sha256: str
    size_bytes: int
    media_type: str | None = None
    media_metadata: dict[str, Any] = Field(default_factory=dict)
    producer_attempt_id: str
    producer_version: str
    input_artifact_ids: list[str] = Field(default_factory=list)
    config_hash: str
    state: ArtifactState
    retention_class: str = "intermediate"
    created_at: datetime


class ArtifactDependency(Contract):
    schema_version: Literal["artifact-dependency.v1"]
    parent_artifact_id: str
    child_artifact_id: str
    dependency_type: str


class ArtifactPointer(Contract):
    schema_version: Literal["artifact-pointer.v1"]
    pointer_id: str
    run_id: str
    logical_slot: str
    artifact_id: str
    pointer_type: Literal["CURRENT", "ACCEPTED", "PUBLISHED"]
    active: bool = True
    updated_at: datetime


class InvalidationRequest(Contract):
    schema_version: Literal["invalidation-request.v1"]
    request_id: str
    root_artifact_ids: list[str]
    reason: str
    scope: Literal["artifact", "scene", "subgraph", "workflow"]
    requested_by: str


class InvalidationResult(Contract):
    schema_version: Literal["invalidation-result.v1"]
    request_id: str
    invalidated_artifact_ids: list[str]
    retained_artifact_ids: list[str]
    created_at: datetime
```

The physical URI may change during storage migration. The logical artifact ID, hash, dependencies, and provenance remain stable.

`logical_slot` is scoped to `run_id` (or, for reusable cross-run artifacts, to an explicitly recorded content-package namespace). A slot such as `script` or `scene_01` is never globally unique. Creating a new active pointer replaces the previous pointer atomically and marks the old pointer inactive; it does not mutate the artifact record.

## 10. Quality contracts

```python
class GateDecision(StrEnum):
    PASS = "PASS"
    REGENERATE = "REGENERATE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    FAIL = "FAIL"


class EvaluationDimension(Contract):
    schema_version: Literal["evaluation-dimension.v1"]
    name: str
    score: float | None = None
    threshold: float | None = None
    severity: Literal["INFO", "MINOR", "MAJOR", "CRITICAL"] = "INFO"
    failure_codes: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class CheckOutcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    ABSTAIN = "ABSTAIN"
    ERROR = "ERROR"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class QualityCheck(Contract):
    schema_version: Literal["quality-check.v1"]
    check_id: str
    target_artifact_types: list[str]
    required_input_types: list[str] = Field(default_factory=list)
    kind: Literal["DETERMINISTIC", "SPECIALIZED", "SEMANTIC", "HUMAN"]
    evaluator: str
    evaluator_version: str
    rubric_version: str | None = None
    required: bool = True
    severity_if_failed: Literal["INFO", "MINOR", "MAJOR", "CRITICAL"]
    on_failure: Literal["REGENERATE", "HUMAN_REVIEW", "FAIL"]
    repair_scope: Literal["NONE", "LAYER", "ASSET", "SHOT", "SCENE", "STAGE", "CUT", "SUBGRAPH", "WORKFLOW"]


class QualityInputManifest(Contract):
    schema_version: Literal["quality-input-manifest.v1"]
    manifest_id: str
    gate_id: str
    check_id: str
    target_artifact_ids: list[str]
    target_hashes: dict[str, str]
    supporting_artifact_ids: list[str] = Field(default_factory=list)
    policy_snapshot_artifact_id: str | None = None
    created_at: datetime


class QualityGatePolicy(Contract):
    schema_version: Literal["quality-gate-policy.v1"]
    gate_id: str
    version: str
    required_check_ids: list[str]
    hard_failure_codes: list[str] = Field(default_factory=list)
    pass_thresholds: dict[str, float] = Field(default_factory=dict)
    human_review_thresholds: dict[str, float] = Field(default_factory=dict)
    max_regenerations: int = 0
    after_max_regenerations: Literal["HUMAN_REVIEW", "FAIL"]


class QualityEvaluation(Contract):
    schema_version: Literal["quality-evaluation.v1"]
    evaluation_id: str
    stage_instance_id: str | None = None
    logical_item_key: str | None = None
    scene_id: str | None = None
    shot_id: str | None = None
    target_artifact_ids: list[str]
    target_hashes: dict[str, str]
    evaluation_input_manifest_id: str
    gate_id: str
    check_id: str
    evaluator: str
    evaluator_version: str
    rubric_version: str | None = None
    dimensions: list[EvaluationDimension]
    outcome: CheckOutcome
    confidence: Literal["LOW", "MEDIUM", "HIGH"] | None = None
    abstained: bool = False  # must equal (outcome == CheckOutcome.ABSTAIN)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    estimated_cost_minor: int = 0
    actual_cost_minor: int | None = None
    provider_invocation_id: str | None = None
    latency_ms: int | None = None
    created_at: datetime


class QualityGateResult(Contract):
    schema_version: Literal["quality-gate-result.v1"]
    quality_gate_result_id: str
    gate_id: str
    gate_version: str
    stage_instance_id: str | None = None
    logical_item_key: str | None = None
    target_artifact_ids: list[str]
    target_hashes: dict[str, str]
    required_check_ids: list[str]
    evaluation_ids: list[str]
    decision: GateDecision
    hard_failure_codes: list[str] = Field(default_factory=list)
    repair_scope: str | None = None
    policy_version: str
    created_at: datetime
    completed_at: datetime | None = None


class RepairPlan(Contract):
    schema_version: Literal["repair-plan.v1"]
    repair_plan_id: str
    source_gate_result_id: str
    reason_codes: list[str]
    target_artifact_ids: list[str]
    target_stage_instance_ids: list[str]
    invalidation_scope: Literal["ARTIFACT", "SCENE", "SUBGRAPH", "WORKFLOW"]
    max_attempts: int
    created_at: datetime
```

Scores are evidence, not universal probabilities. Gate policy must define hard failures, thresholds, escalation, and aggregation separately.

## 11. Human review contracts

```python
class HumanReview(Contract):
    schema_version: Literal["human-review.v1"]
    review_id: str
    run_id: str
    stage_instance_id: str | None = None
    gate_id: str | None = None
    target_artifact_ids: list[str]
    target_hashes: dict[str, str] = Field(default_factory=dict)
    reason_codes: list[str] = Field(default_factory=list)
    requested_action: str
    status: Literal["OPEN", "ASSIGNED", "RESOLVED", "EXPIRED", "CANCELLED"]
    created_at: datetime
    resolved_at: datetime | None = None


class HumanReviewDecision(Contract):
    schema_version: Literal["human-review-decision.v1"]
    review_id: str
    decision: Literal[
        "APPROVE",
        "REGENERATE_SCENE",
        "REGENERATE_STAGE",
        "REJECT",
    ]
    comments: str | None = None
    reviewer: str
    target_hashes: dict[str, str] = Field(default_factory=dict)
    created_at: datetime
```

### 11.1 Publishing boundary

Publishing is optional in the fast slice, but its durable contract is defined
before a platform adapter is introduced. The adapter may publish only the exact
approved artifact hashes recorded in the request.

```python
class PublicationRequest(Contract):
    schema_version: Literal["publication-request.v1"]
    publication_request_id: str
    run_id: str
    cut_ids: list[str]
    approved_artifact_hashes: dict[str, str]
    approval_ids: list[str]
    platform: str
    metadata_artifact_id: str
    idempotency_key: str


class PublicationAttempt(Contract):
    schema_version: Literal["publication-attempt.v1"]
    publication_attempt_id: str
    publication_request_id: str
    status: Literal["PENDING", "STARTED", "SUCCEEDED", "FAILED", "UNKNOWN"]
    external_publication_id: str | None = None
    provider_operation_id: str | None = None
    normalized_error: NormalizedError | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
```

## 12. Recovery and event contracts

```python
class RecoveryDecision(Contract):
    schema_version: Literal["recovery-decision.v1"]
    recovery_decision_id: str
    run_id: str
    failed_attempt_id: str | None = None
    action: Literal[
        "RESUME",
        "RETRY",
        "RECONCILE",
        "REGENERATE",
        "WAIT_HUMAN",
        "FAIL",
    ]
    target_stage_instance_ids: list[str] = Field(default_factory=list)
    target_artifact_ids: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    created_at: datetime


class EventEnvelope(Contract):
    schema_version: Literal["event-envelope.v1"]
    event_id: str
    event_type: str
    run_id: str | None = None
    stage_instance_id: str | None = None
    attempt_id: str | None = None
    correlation_id: str
    causation_id: str | None = None
    payload_schema_version: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class OutboxMessage(Contract):
    schema_version: Literal["outbox-message.v1"]
    outbox_id: str
    event_id: str
    event: EventEnvelope
    status: Literal["PENDING", "CLAIMED", "DELIVERED", "FAILED"]
    delivery_attempts: int = 0
    available_at: datetime
    claimed_by: str | None = None
    claimed_at: datetime | None = None
    lease_expires_at: datetime | None = None
    delivered_at: datetime | None = None


class InboxReceipt(Contract):
    schema_version: Literal["inbox-receipt.v1"]
    consumer_id: str
    event_id: str
    status: Literal["RECEIVED", "PROCESSED", "IGNORED", "FAILED"]
    processed_at: datetime | None = None
    error_code: str | None = None
```

`EventEnvelope` is the canonical serialized form of a durable `WorkflowEvent`; the `workflow_events` table stores the envelope and delivery/audit metadata. `OutboxMessage` references the same event and adds dispatcher state.

Canonical event names use lowercase dot notation and are registered in
[`registries/events.yaml`](registries/events.yaml). Event names are not free-form
strings in workflow code.

Events have one of three roles:

- `command`: durable intent for another component to perform work;
- `notification`: a wake-up hint that work may be eligible;
- `fact`: an immutable record of a committed state transition.

Consumers must deduplicate by `event_id` or the associated idempotent job key.
The event history is an audit record; it is not a replacement for authoritative
workflow state.

The canonical event names are:

```text
workflow.created
workflow.started
stage.ready
stage.claimed
stage.started
stage.succeeded
stage.failed
stage.unknown
artifact.created
artifact.invalidated
quality.requested
quality.evaluated
repair.requested
human_review.requested
human_review.completed
workflow.paused
workflow.resumed
workflow.completed
workflow.failed
publish.requested
publish.completed
```

## 13. Profile and content contracts

```python
class BudgetPolicy(Contract):
    schema_version: Literal["budget-policy.v1"]
    policy_id: str
    version: str
    system_cap_minor: int
    monthly_cap_minor: int | None = None
    default_run_cap_minor: int | None = None
    default_stage_cap_minor: int | None = None
    evaluation_cap_minor: int | None = None
    paid_fallback_enabled: bool = False
    reservation_required: bool = True


class SystemPolicy(Contract):
    schema_version: Literal["system-policy.v1"]
    policy_id: str
    version: str
    max_parallelism: int
    max_retry_attempts: int
    budget_policy_id: str
    allowed_providers: list[str] = Field(default_factory=list)
    non_overridable_fields: list[str] = Field(default_factory=list)


class DomainProfile(Contract):
    schema_version: Literal["domain-profile.v1"]
    profile_id: str
    version: str
    content_mode: str
    default_locale: str
    required_stages: list[str]
    optional_stages: list[str] = Field(default_factory=list)
    source_policy_id: str | None = None
    claim_policy_id: str | None = None
    quality_profile_id: str
    human_review_policy_id: str
    asset_policy_id: str


class ChannelProfile(Contract):
    schema_version: Literal["channel-profile.v1"]
    profile_id: str
    version: str
    domain_profile_id: str
    locale: str
    audience: str
    target_duration_seconds: int
    output_profile_ids: list[str]
    brand_profile_id: str
    voice_profile_id: str | None = None
    publishing_policy_id: str


class ProductionIdea(Contract):
    schema_version: Literal["production-idea.v1"]
    idea_id: str
    source_topic_ids: list[str] = Field(default_factory=list)
    title: str
    angle: str
    audience: str
    promise: str
    locale: str
    selected_at: datetime | None = None


class ContentPackage(Contract):
    schema_version: Literal["content-package.v1"]
    content_package_id: str
    production_idea_id: str
    episode_ids: list[str] = Field(default_factory=list)
    active_episode_id: str | None = None


class Episode(Contract):
    schema_version: Literal["episode.v1"]
    episode_id: str
    content_package_id: str
    script_artifact_id: str
    sequence_ids: list[str] = Field(default_factory=list)
    cut_ids: list[str] = Field(default_factory=list)
    version: int


class Cut(Contract):
    schema_version: Literal["cut.v1"]
    cut_id: str
    episode_id: str
    kind: Literal["LONG_FORM", "SHORT"]
    output_profile_id: str
    sequence_ids: list[str] = Field(default_factory=list)
    selection_manifest_id: str | None = None


class Sequence(Contract):
    schema_version: Literal["sequence.v1"]
    sequence_id: str
    episode_id: str
    order_index: int
    scene_ids: list[str] = Field(default_factory=list)


class Scene(Contract):
    schema_version: Literal["scene.v1"]
    scene_id: str
    sequence_id: str
    order_index: int
    narration_artifact_id: str | None = None
    claim_ids: list[str] = Field(default_factory=list)
    shot_ids: list[str] = Field(default_factory=list)


class Shot(Contract):
    schema_version: Literal["shot.v1"]
    shot_id: str
    scene_id: str
    order_index: int
    start_frame: int
    end_frame: int
    layer_ids: list[str] = Field(default_factory=list)


class AssetProvenance(Contract):
    schema_version: Literal["asset-provenance.v1"]
    source_kind: Literal["STOCK", "PUBLIC_DOMAIN", "GENERATED", "PROCEDURAL", "USER_SUPPLIED"]
    provider_id: str | None = None
    provider_asset_id: str | None = None
    source_url: str | None = None
    retrieved_at: datetime | None = None
    content_hash: str
    license_type: str | None = None
    license_url: str | None = None
    commercial_use_allowed: bool | None = None
    attribution_required: bool | None = None
    modification_allowed: bool | None = None
    prompt_artifact_id: str | None = None
    generation_model: str | None = None
    generation_settings_hash: str | None = None
    parent_asset_id: str | None = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class SourceAsset(Contract):
    schema_version: Literal["source-asset.v1"]
    source_asset_id: str
    artifact_id: str
    source_type: str
    provenance: AssetProvenance
    license_ref: str | None = None


class AssetInstance(Contract):
    schema_version: Literal["asset-instance.v1"]
    asset_instance_id: str
    source_asset_id: str
    shot_id: str
    start_frame: int
    end_frame: int
    transform: dict[str, Any] = Field(default_factory=dict)


class LayerInstance(Contract):
    schema_version: Literal["layer-instance.v1"]
    layer_id: str
    shot_id: str
    kind: Literal[
        "VIDEO", "IMAGE", "SHAPE", "CHART", "CODE", "TEXT",
        "CAPTION", "AUDIO_VOICE", "AUDIO_MUSIC", "AUDIO_EFFECT",
        "MASK", "TRANSITION",
    ]
    start_frame: int
    end_frame: int
    asset_instance_id: str | None = None
    payload_artifact_id: str | None = None
    z_index: int = 0
    properties: dict[str, Any] = Field(default_factory=dict)


class WordTimestamp(Contract):
    schema_version: Literal["word-timestamp.v1"]
    word: str
    start_frames: int
    end_frames: int
    confidence: float | None = None


class SpeechStrategy(StrEnum):
    CONTINUOUS = "CONTINUOUS"
    SCENE_SEGMENTED = "SCENE_SEGMENTED"


class SpeechManifest(Contract):
    schema_version: Literal["speech-manifest.v1"]
    script_id: str
    script_version: int
    strategy: SpeechStrategy
    master_audio_artifact_id: str
    scene_audio_artifact_ids: dict[str, str] = Field(default_factory=dict)
    voice_configuration_hash: str
    narration_text_hashes: dict[str, str]
    alignment_artifact_id: str


class CompositionLayerSpec(Contract):
    schema_version: Literal["composition-layer.v1"]
    layer_id: str
    kind: str
    start_frame: int
    end_frame: int
    asset_instance_id: str | None = None
    payload_artifact_id: str | None = None
    z_index: int = 0
    transform: dict[str, Any] = Field(default_factory=dict)
    animation: dict[str, Any] | None = None
    safe_area: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class CompositionShotSpec(Contract):
    schema_version: Literal["composition-shot.v1"]
    shot_id: str
    start_frame: int
    end_frame: int
    layers: list[CompositionLayerSpec] = Field(default_factory=list)


class CompositionSceneSpec(Contract):
    schema_version: Literal["composition-scene.v1"]
    scene_id: str
    start_frame: int
    end_frame: int
    shots: list[CompositionShotSpec] = Field(default_factory=list)


class CompositionSequenceSpec(Contract):
    schema_version: Literal["composition-sequence.v1"]
    sequence_id: str
    scenes: list[CompositionSceneSpec] = Field(default_factory=list)


class CompositionAudioTrackSpec(Contract):
    schema_version: Literal["composition-audio-track.v1"]
    track_id: str
    artifact_id: str
    start_frame: int
    end_frame: int


class CompositionAuthoringSpec(Contract):
    schema_version: Literal["composition-authoring.v1"]
    composition_id: str
    episode_id: str
    cut_id: str
    render_profile_id: str
    render_profile_hash: str
    duration_frames: int
    sequences: list[CompositionSequenceSpec] = Field(default_factory=list)
    audio_tracks: list[CompositionAudioTrackSpec] = Field(default_factory=list)
    font_artifact_ids: list[str] = Field(default_factory=list)
    renderer_version: str


class ResolvedArtifactRef(Contract):
    schema_version: Literal["resolved-artifact-ref.v1"]
    artifact_id: str
    sha256: str
    uri: str
    media_type: str | None = None
    media_metadata: dict[str, Any] = Field(default_factory=dict)


class CompositionSpec(Contract):
    schema_version: Literal["render-manifest.v1"]
    composition_id: str
    episode_id: str
    cut_id: str
    render_profile_id: str
    render_profile_hash: str
    fps: int
    timebase: str
    duration_frames: int
    sequence_ids: list[str] = Field(default_factory=list)
    scene_ids: list[str] = Field(default_factory=list)
    shot_ids: list[str] = Field(default_factory=list)
    layer_ids: list[str] = Field(default_factory=list)
    audio_track_artifact_ids: list[str] = Field(default_factory=list)
    font_artifact_ids: list[str] = Field(default_factory=list)
    resolved_artifacts: list[ResolvedArtifactRef] = Field(default_factory=list)
    render_manifest_hash: str
    renderer_version: str


class RenderChunkManifest(Contract):
    schema_version: Literal["render-chunk-manifest.v1"]
    manifest_id: str
    composition_artifact_id: str
    cut_id: str
    chunk_ids: list[str]
    frame_ranges: dict[str, list[int]]
    overlap_policy: str
    expected_count: int


class AssemblyManifest(Contract):
    schema_version: Literal["assembly-manifest.v1"]
    assembly_id: str
    cut_id: str
    render_chunk_manifest_id: str
    ordered_chunk_ids: list[str]
    output_profile_id: str
    continuity_policy_id: str
    assembly_hash: str


class RenderProfile(Contract):
    schema_version: Literal["render-profile.v1"]
    render_profile_id: str
    version: str
    width: int
    height: int
    fps: int
    color_space: str
    pixel_format: str
    video_codec: str
    container: str
    audio_sample_rate: int
    audio_channels: int
    audio_codec: str
    safe_area_id: str
    caption_style_id: str
    loudness_policy_id: str


class ShortSelectionManifest(Contract):
    schema_version: Literal["short-selection.v1"]
    short_id: str
    source_episode_id: str
    source_scene_ids: list[str]
    source_shot_ids: list[str] = Field(default_factory=list)
    hook_policy: str
    target_duration_seconds: int
    aspect_ratio: str
    reframe_policy: str
    caption_policy: str
    selected_claim_ids: list[str] = Field(default_factory=list)


```

`CompositionAuthoringSpec` is the nested authoring document. `CompositionSpec`
(`render-manifest.v1`) is the immutable, resolved renderer manifest. It records
the exact ordered IDs, artifact hashes/URIs, timing/timebase, render profile,
font/template versions, and renderer version used. A renderer worker must be
able to render from this manifest without querying mutable current pointers.
The manifest is stored or content-hashed before rendering; any change creates a
new composition version.

```python
class SourceRef(Contract):
    schema_version: Literal["source-ref.v1"]
    source_id: str
    uri: str
    source_type: str
    retrieved_at: datetime
    content_hash: str | None = None
    snapshot_artifact_id: str | None = None
    authority_class: str | None = None


class SourceSnapshot(Contract):
    schema_version: Literal["source-snapshot.v1"]
    snapshot_id: str
    source_id: str
    snapshot_artifact_id: str
    retrieved_at: datetime
    content_hash: str
    retrieval_method: str
    freshness_class: str | None = None
    expires_at: datetime | None = None


class Evidence(Contract):
    schema_version: Literal["evidence.v1"]
    evidence_id: str
    source_id: str
    snapshot_id: str | None = None
    excerpt_ref: str | None = None
    excerpt_hash: str | None = None
    claim_support: str
    as_of_date: str | None = None
    status: Literal["SUPPORTED", "PARTIAL", "CONTRADICTED", "OUTDATED", "UNRESOLVED"]


class Claim(Contract):
    schema_version: Literal["claim.v1"]
    claim_id: str
    text: str
    claim_type: Literal["FACT", "INFERENCE", "OPINION", "SPECULATION", "FICTION"]
    importance: Literal["LOW", "MEDIUM", "HIGH", "MATERIAL"]
    evidence_ids: list[str] = Field(default_factory=list)
    as_of_date: str | None = None


class VisualIntent(Contract):
    schema_version: Literal["visual-intent.v1"]
    semantic_description: str
    required_elements: list[str] = Field(default_factory=list)
    prohibited_elements: list[str] = Field(default_factory=list)
    preferred_source_types: list[str] = Field(default_factory=list)


class DurationPolicy(Contract):
    schema_version: Literal["duration-policy.v1"]
    minimum_seconds: float | None = None
    maximum_seconds: float | None = None
    target_seconds: float | None = None
    overflow_action: Literal["TRIM", "REWRITE", "EXTEND_VISUAL", "HUMAN_REVIEW"]


class ScriptScene(Contract):
    schema_version: Literal["script-scene.v1"]
    scene_id: str
    sequence_id: str
    narration: str
    claim_ids: list[str] = Field(default_factory=list)
    visual_intent: VisualIntent
    duration_policy: DurationPolicy
    caption_text: str | None = None
    pronunciation_hints: list[str] = Field(default_factory=list)


class Script(Contract):
    schema_version: Literal["script.v1"]
    script_id: str
    production_idea_id: str
    locale: str
    scenes: list[ScriptScene]
    version: int


class AudioTiming(Contract):
    schema_version: Literal["audio-timing.v1"]
    speech_manifest_id: str
    script_version: int
    scene_id: str
    audio_artifact_id: str
    narration_text_hash: str
    start_frames: int
    end_frames: int
    word_timestamps: list[WordTimestamp] = Field(default_factory=list)


class CompositionRef(Contract):
    schema_version: Literal["composition-ref.v1"]
    composition_artifact_id: str
    cut_id: str
    render_profile_id: str
    render_profile_hash: str
    timebase: str
```

## 14. Database authority and indexes

The database is authoritative for:

- workflow/run status;
- stage instances and attempts;
- job claims and leases;
- routing decisions;
- provider invocations and usage;
- artifact metadata and dependency graph;
- quality and human decisions;
- idempotency/reconciliation;
- event/outbox status;
- effective configuration references.

Persist the immutable effective configuration snapshot (or a content-addressed configuration artifact) rather than retaining only its hash. The hash is the lookup/integrity key; the snapshot is what makes an old run inspectable after source configuration changes.

Recommended uniqueness constraints:

```text
workflow_runs(run_key)
effective_configs(effective_config_id)
stage_instances(run_id, node_id, logical_item_key)
stage_attempts(stage_instance_id, attempt_number)
jobs(idempotency_key)
idempotency_records(idempotency_key)
budget_reservations(reservation_id)
budget_reservations(idempotency_key, scope_type, scope_id)
artifacts(artifact_id)
artifacts(run_id, logical_slot, version)
artifact_dependencies(parent_artifact_id, child_artifact_id)
quality_evaluations(evaluation_id)
quality_gate_results(quality_gate_result_id)
artifact_pointers(run_id, logical_slot, pointer_type) WHERE active
outbox_messages(event_id)
inbox_receipts(consumer_id, event_id)
```

`run_key` is caller-supplied or deterministically derived by the trigger (for example, channel + scheduled window + content request) and is unique within the workflow/control-plane namespace. `RETURN_EXISTING` makes duplicate delivery idempotent; `CREATE_NEW` requires the caller to supply a deliberately different key.

Recommended indexes:

```text
stage_instances(run_id, status)
jobs(status, available_at)
jobs(lease_expires_at)
budget_reservations(scope_type, scope_id, status)
artifacts(run_id, logical_slot, state)
artifact_pointers(run_id, logical_slot, pointer_type, active)
artifact_dependencies(parent_artifact_id)
artifact_dependencies(child_artifact_id)
human_reviews(status, created_at)
outbox_messages(status, available_at)
```

## 15. Fingerprints and idempotency

An operation fingerprint includes:

```text
capability
+ operation_version
+ input_artifact_ids and hashes
+ canonical request payload
+ effective config hash
+ provider/model configuration hash
```

It excludes:

- timestamps;
- worker IDs;
- random request IDs;
- secrets;
- diagnostic text that does not change behavior.

An idempotency key should identify the intended logical operation. A retry of the same operation uses the same key; a deliberate regeneration uses a new artifact version and a new logical attempt while retaining the repair relationship.

## 16.1 Contract inventory and ownership

| Contract family | Canonical models | Durable record | Fast slice |
|---|---|---|---|
| Configuration | `SystemPolicy`, `DomainProfile`, `ChannelProfile`, `EffectiveConfig` | `effective_configs` | Required |
| Workflow | `WorkflowDefinition`, `StageNode`, `CardinalityPolicy` | versioned files plus run snapshot | Required |
| Execution | `WorkflowRun`, `StageInstance`, `StageAttempt`, `Job`, `Lease` | `workflow_runs`, `stage_instances`, `stage_attempts`, `jobs` | Required |
| Capability | `CapabilityRequest`, `CapabilityResult`, `CapabilityExecution`, `ExecutionContext` | `capability_executions` | Required |
| Provider | `RoutingDecision`, `ProviderInvocation`, `UsageRecord` | `routing_decisions`, `provider_invocations`, `usage_records` | Required |
| Safety/recovery | `IdempotencyRecord`, `BudgetReservation`, `NormalizedError`, `RecoveryPolicy` | `idempotency_records`, `budget_reservations`, `recovery_decisions` | Required for fake providers; real budgets as soon as paid calls exist |
| Artifacts | `Artifact`, `ArtifactDependency`, `ArtifactPointer`, `InputManifest` | `artifacts`, `artifact_dependencies`, `artifact_pointers`, `input_manifests` | Required |
| Quality | `QualityCheck`, `QualityInputManifest`, `QualityEvaluation`, `QualityGatePolicy`, `QualityGateResult`, `RepairPlan` | quality tables | Required |
| Human review | `HumanReview`, `HumanReviewDecision` | `human_reviews` | Required |
| Publishing | `PublicationRequest`, `PublicationAttempt` | `publication_requests`, `publication_attempts` | Deferred; dry-run/export first |
| Events | `EventEnvelope`, `OutboxMessage`, `InboxReceipt` | `workflow_events`, `outbox_messages`, `inbox_receipts` | Required |
| Editorial content | `ContentPackage`, `Episode`, `Cut`, `Sequence`, `Scene`, `Shot`, `LayerInstance`, `SourceAsset`, `AssetInstance`, `CompositionSpec` | artifact-backed manifests initially; normalized rows later if needed | Required for media slice |

The table is the implementation inventory. If an agent needs a type not listed here, it must either add it to this document and the decision log or keep it private to a stage without pretending it is durable workflow state.

## 16.2 Typed extension boundaries

Some payloads are operation-specific, but they still require a schema boundary:

- `CapabilityRequest.payload` is validated by `payload_schema_version` and the capability registry;
- `EventEnvelope.payload` is validated by `(event_type, payload_schema_version)`;
- `LayerInstance.properties` is validated by the layer `kind`;
- profile policy fields are validated by their policy ID/version;
- `metadata` fields are diagnostic or provider-specific and are not allowed to control workflow transitions.

Core selectors, conditions, gate decisions, and state transitions must not be arbitrary unvalidated dictionaries.

## 16.3 Contract evolution

When changing a contract:

1. add a new schema version if meaning or required fields change;
2. write a migration/compatibility function;
3. keep old readers only for the declared compatibility window;
4. add fixtures for old and new versions;
5. update workflow and artifact metadata to record the version used;
6. never reinterpret old data silently.

## 17. Contract test checklist

- [ ] valid payloads serialize deterministically;
- [ ] invalid enums, missing fields, and unknown core fields fail;
- [ ] schema versions are required;
- [ ] timezones normalize to UTC;
- [ ] fingerprints are stable across key ordering;
- [ ] secrets do not enter fingerprints/logs;
- [ ] duplicate IDs are rejected where required;
- [ ] artifacts reference exact hashes;
- [ ] quality evaluations reference exact artifact versions;
- [ ] event payloads carry IDs and references, not large binaries;
- [ ] old contract fixtures remain readable according to compatibility policy.
