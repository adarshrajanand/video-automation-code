# AI Video Pipeline — First-Class Contracts v2

**Date:** September 2026
**Status:** HISTORICAL / NON-NORMATIVE SUPPORTING NOTE
**Canonical replacement:** [Contracts and Data Model](../AI_Video_Pipeline_Contracts_and_Data_Model.md)

> This document preserves earlier contract discussion. It contains superseded
> examples such as `StageExecution`, `ACTIVE`, and unversioned dictionaries.
> Do not implement from it; use the canonical contract document and registries.

## 1. Contract hierarchy

```text
WorkflowDefinition
      ↓
StageNode
      ↓
StageExecution
      ↓
CapabilityRequest
      ↓
RoutingDecision
      ↓
ProviderInvocation
      ↓
Artifact(s)
      ↓
QualityEvaluation
      ↓
Recovery / next transition
```

## 2. Configuration contracts

```python
class EffectiveWorkflowConfig(BaseModel):
    system_policy_version: str
    channel_config_version: str
    workflow_id: str
    workflow_version: str
    run_overrides: dict
    resolved_values: dict
    config_hash: str
```

```python
class WorkflowDefinition(BaseModel):
    workflow_id: str
    version: str
    nodes: list["StageNode"]
    policies: "WorkflowPolicies"
```

```python
class StageNode(BaseModel):
    node_id: str
    stage_name: str
    depends_on: list[str]
    input_selector: dict
    cardinality: "CardinalityPolicy"
    quality_gate_id: str | None = None
    recovery_policy_id: str | None = None
    enabled_when: dict | None = None
```

```python
class CardinalityPolicy(BaseModel):
    mode: Literal[
        "one_to_one",
        "one_to_many",
        "many_to_one",
        "many_to_many",
    ]
    count: int | None = None
    selection_policy: str | None = None
```

## 3. Execution contracts

```python
class WorkflowRun(BaseModel):
    run_id: str
    workflow_id: str
    workflow_version: str
    status: str
    effective_config_hash: str
    created_at: datetime
    updated_at: datetime
```

```python
class StageExecution(BaseModel):
    execution_id: str
    run_id: str
    node_id: str
    attempt: int
    status: str
    input_artifact_ids: list[str]
    output_artifact_ids: list[str]
    started_at: datetime | None = None
    finished_at: datetime | None = None
```

Statuses:

```text
PENDING
RUNNING
SUCCEEDED
FAILED
WAITING_HUMAN
WAITING_RETRY
CANCELLED
UNKNOWN
```

`UNKNOWN` represents an ambiguous external outcome after a crash.

## 4. Capability contracts

```python
class CapabilityRequirements(BaseModel):
    capability: str
    required_features: list[str] = []
    locale: str | None = None
    quality_requirement: str | None = None
    latency_requirement: str | None = None
    cost_limit_usd: float | None = None
```

```python
class CapabilityRequest(BaseModel):
    capability: str
    operation_version: str
    input_artifact_ids: list[str]
    payload_fingerprint: str
    requirements: CapabilityRequirements
    runtime_context: dict
```

```python
class CapabilityResult(BaseModel):
    status: str
    artifact_ids: list[str]
    metadata: dict = {}
    usage: dict | None = None
```

## 5. Router contracts

```python
class RoutingContext(BaseModel):
    capability_request: CapabilityRequest
    effective_config: dict
    provider_health: dict
    provider_usage: dict
    previous_results: list[dict]
    attempt: int
    budget_remaining_usd: float | None
```

```python
class RoutingDecision(BaseModel):
    capability: str
    implementation: str
    provider: str
    model: str | None
    config: dict
    fallback_chain: list[str]
    policy_version: str
    reason_codes: list[str]
    created_at: datetime
```

The Router returns execution selection. It does not return workflow transitions.

## 6. Provider and idempotency contracts

```python
class Provider(BaseModel):
    provider_id: str
    capabilities: list[str]
    implementation_version: str
    config_schema_version: str
```

```python
class ProviderInvocation(BaseModel):
    invocation_id: str
    capability_execution_id: str
    provider: str
    operation_id: str | None
    idempotency_key: str
    status: str
    request_fingerprint: str
    started_at: datetime
    finished_at: datetime | None = None
```

```python
class IdempotencyRecord(BaseModel):
    idempotency_key: str
    capability: str
    provider: str
    status: str
    result_artifact_ids: list[str]
    provider_operation_id: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
```

A provider operation must not be blindly repeated after an ambiguous crash.

## 7. Artifact contracts

```python
class Artifact(BaseModel):
    artifact_id: str
    run_id: str
    artifact_type: str
    version: int
    uri: str
    sha256: str
    size_bytes: int
    producer_execution_id: str
    producer_version: str
    input_artifact_ids: list[str]
    config_hash: str
    state: str
    created_at: datetime
```

Artifact states:

```text
ACTIVE
INVALIDATED
SUPERSEDED
DELETED
```

Artifact identity must not depend on its physical URI.

```python
class ArtifactDependency(BaseModel):
    parent_artifact_id: str
    child_artifact_id: str
    dependency_type: str
```

## 8. Invalidation contracts

```python
class InvalidationRequest(BaseModel):
    root_artifact_ids: list[str]
    reason: str
    scope: Literal[
        "artifact",
        "scene",
        "subgraph",
        "workflow",
    ]
```

```python
class InvalidationResult(BaseModel):
    invalidated_artifact_ids: list[str]
    retained_artifact_ids: list[str]
    created_at: datetime
```

Invalidation walks descendants only.

## 9. Quality contracts

```python
class EvaluationDimension(BaseModel):
    name: str
    score: float | None
    threshold: float | None
    details: dict = {}
```

```python
class QualityEvaluation(BaseModel):
    evaluation_id: str
    target_artifact_ids: list[str]
    gate_id: str
    evaluator: str
    evaluator_version: str
    dimensions: list[EvaluationDimension]
    decision: Literal[
        "PASS",
        "REGENERATE",
        "HUMAN_REVIEW",
        "FAIL",
    ]
    created_at: datetime
```

Quality evaluation is a first-class output associated with exact artifact versions.

## 10. Human review contracts

```python
class HumanReviewRequest(BaseModel):
    review_id: str
    run_id: str
    target_artifact_ids: list[str]
    reason: str
    requested_action: str
    status: str
```

```python
class HumanReviewDecision(BaseModel):
    review_id: str
    decision: Literal[
        "APPROVE",
        "REGENERATE_ARTIFACT",
        "REGENERATE_STAGE",
        "REJECT",
    ]
    comments: str | None
    reviewer: str
    created_at: datetime
```

## 11. Recovery contract

```python
class RecoveryDecision(BaseModel):
    run_id: str
    failed_execution_id: str | None
    action: Literal[
        "RESUME",
        "RETRY",
        "RECONCILE",
        "REGENERATE",
        "WAIT_HUMAN",
        "FAIL",
    ]
    target_node_id: str | None
    target_artifact_ids: list[str] = []
    reason_codes: list[str] = []
    created_at: datetime
```

Recovery is separate from routing.

## 12. Durable events

```python
class WorkflowEvent(BaseModel):
    event_id: str
    run_id: str
    event_type: str
    execution_id: str | None
    payload: dict
    created_at: datetime
```

Examples:

```text
workflow.started
stage.started
stage.succeeded
stage.failed
routing.decided
provider.started
provider.completed
artifact.created
artifact.invalidated
quality.evaluated
human_review.requested
human_review.completed
workflow.paused
workflow.resumed
workflow.completed
```

## 13. Observability contracts

```python
class StructuredLog(BaseModel):
    timestamp: datetime
    level: str
    run_id: str | None
    execution_id: str | None
    stage: str | None
    capability: str | None
    message: str
    fields: dict = {}
```

```python
class MetricPoint(BaseModel):
    metric_name: str
    value: float
    labels: dict
    timestamp: datetime
```

```python
class TraceContext(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: str | None
```

## 14. Domain contracts

### Topic

```python
class Topic(BaseModel):
    topic_id: str
    title: str
    source_refs: list[str]
    discovered_at: datetime
    metadata: dict = {}
```

### CandidateIdea

```python
class CandidateIdea(BaseModel):
    idea_id: str
    topic_id: str | None
    title: str
    angle: str
    audience: str
    promise: str
    language: str
    metadata: dict = {}
```

### ProductionIdea

```python
class ProductionIdea(BaseModel):
    idea_id: str
    source_candidate_ids: list[str]
    title: str
    angle: str
    audience: str
    promise: str
    language: str
    selected_at: datetime
```

### Evidence and Claim

```python
class Evidence(BaseModel):
    evidence_id: str
    source_ref: str
    excerpt_ref: str | None
    claim_support: str
    metadata: dict = {}
```

```python
class Claim(BaseModel):
    claim_id: str
    text: str
    evidence_ids: list[str]
    importance: str
```

### ScriptScene

```python
class ScriptScene(BaseModel):
    scene_id: str
    narration: str
    claim_ids: list[str]
    visual_intent: dict
    duration_policy: dict
    transition_hint: str | None
```

### Script

```python
class Script(BaseModel):
    script_id: str
    production_idea_id: str
    scenes: list[ScriptScene]
    version: int
```

### AudioTiming

```python
class AudioTiming(BaseModel):
    scene_id: str
    duration_seconds: float
    start_seconds: float
    end_seconds: float
    word_timestamps: list[dict] | None = None
```

### TTSResult

```python
class TTSResult(BaseModel):
    scene_artifact_ids: list[str]
    continuous_audio_artifact_id: str
    timings: list[AudioTiming]
    quality_metadata: dict = {}
```

### VisualIntent

```python
class VisualIntent(BaseModel):
    semantic_description: str
    required_elements: list[str]
    prohibited_elements: list[str] = []
```

### VisualSource

```python
class VisualSource(BaseModel):
    source_type: Literal[
        "stock_video",
        "stock_image",
        "generated_video",
        "motion_graphic",
        "text",
        "procedural",
    ]
    asset_artifact_id: str | None
    provenance: dict = {}
```

### VisualLayer

```python
class VisualLayer(BaseModel):
    layer_id: str
    z_index: int
    start_seconds: float
    end_seconds: float
    source: VisualSource
    transform: dict = {}
    opacity: float = 1.0
    blend_mode: str = "normal"
    mask: dict | None = None
    effects: list[dict] = []
    animation: dict | None = None
```

### SceneCompositionPlan

```python
class SceneCompositionPlan(BaseModel):
    scene_id: str
    duration_seconds: float
    layers: list[VisualLayer]
```

## 15. Contract invariants

1. A stage cannot select a provider directly.
2. A Router cannot create workflow transitions.
3. A provider cannot modify workflow state.
4. Artifacts are immutable.
5. Every external side effect has an idempotency strategy.
6. Quality evaluations reference exact artifact versions.
7. Regeneration creates new artifact versions.
8. Invalidated artifacts are never silently reused.
9. Cardinality is generic.
10. Manual topic input may bypass Topic Discovery.
11. Human review is durable state, not an in-memory callback.
12. DB records remain meaningful after large binaries are deleted.
13. Artifact URIs may change without changing artifact identity.
14. Configuration versions are captured in execution metadata.
15. Previous-step results enter routing/workflow policy through explicit runtime context.
