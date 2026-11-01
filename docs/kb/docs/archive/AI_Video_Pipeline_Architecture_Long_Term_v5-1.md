# AI Video Pipeline — Long-Term Architecture v5

**Date:** September 2026
**Status:** HISTORICAL / NON-NORMATIVE SUPPORTING NOTE
**Canonical replacement:** [AI Video Pipeline — Canonical Architecture](../AI_Video_Pipeline_Architecture.md)

> This document preserves earlier design reasoning. It is not an implementation
> authority. Its stage names, contract shapes, and examples may be obsolete;
> follow the canonical documents and registries in `kb/docs/README.md`.

## 0. Changes in v5

This revision incorporates the latest design decisions:

- First-class **Workflow Definition** controlling topology, dependencies, cardinality, quality gates and recovery.
- Layered configuration: **System Policy → Channel Config → Workflow Definition → Run Overrides → Effective Config**.
- First-class **Router** separated from workflow control.
- Data-driven router policies using capability requirements, provider health, quotas, cost, quality, locale and previous results.
- **Per-stage Quality Gates**, including automated and human review, with regeneration.
- Explicit **Idea Discovery** stage that can be skipped for manually supplied topics.
- Generic **1→1, 1→N, N→1, N→M** workflow cardinality.
- Immutable **Artifact Graph** with surgical descendant invalidation and reuse.
- Crash recovery using **execution state + idempotency/reconciliation**, not merely “first incomplete stage”.
- Durable DB records for meaningful execution history, but not every low-level function/log.
- Retention split between inexpensive metadata/lineage and expensive binary artifacts.
- `VideoState` treated as a convenient projection; normalized DB + artifact metadata/events are authoritative.

---

# 1. Core Mental Model

```text
Effective Workflow Configuration
              │
              ▼
       Workflow Engine
          WHAT / WHEN
              │
              ▼
        StageExecution
              │
              ▼
       Capability Request
              │
              ▼
            Router
          HOW TO RUN
              │
              ▼
 Capability Implementation
              │
              ▼
       Provider Adapter
              │
              ▼
      External / Local Provider
              │
              ▼
           Artifact
              │
              ▼
         Quality Gate
       /       |        \
    PASS   REGENERATE   HUMAN
      │         │          │
      ▼         ▼          ▼
    NEXT      Router     WAITING
              AGAIN      HUMAN
```

Responsibilities:

| Component | Owns | Must not own |
|---|---|---|
| Workflow Engine | transitions, dependencies, fan-out/fan-in, recovery | vendor/model selection |
| Stage | domain boundary and stage policy | provider SDK details |
| Capability | reusable operation contract | workflow transitions |
| Router | provider/implementation/config selection | business workflow transitions |
| Provider Adapter | provider integration | business policy |
| Artifact Graph | dependency/reuse/invalidation | execution |
| Quality Gate | output evaluation and decision | silent mutation |
| DB | authoritative workflow/execution/lineage metadata | every debug log |
| Object Storage | large bytes | workflow state |
| Logs | diagnostics | workflow state |

---

# 2. Layered Configuration

Do **not** build one giant workflow config.

```text
System Policy
      ↓
Channel Configuration
      ↓
Workflow Definition
      ↓
Run Overrides
      ↓
Runtime Context / Previous Results
      ↓
Effective Configuration
```

### System Policy

Global safety and operational limits:

```yaml
system:
  max_parallelism: 4
  max_retry_attempts: 3
  hard_cost_limit_usd: 5
  allowed_providers:
    - local
    - provider_a
    - provider_b
```

### Channel Configuration

Stable editorial/channel choices:

```yaml
channel:
  niche: finance
  language: en-IN
  target_duration_seconds: 600
  brand_profile: default_finance
  human_review_required_for:
    - factual_finance_claims
    - final_publish
```

### Workflow Definition

Controls the graph itself:

```yaml
workflow:
  id: finance_explainer_v1
  version: 3

  nodes:

    - id: discover_topics
      stage: topic_discovery
      cardinality:
        mode: one_to_many
        count: 10
      quality_gate: topic_qc

    - id: generate_ideas
      stage: idea_generation
      depends_on: [discover_topics]
      cardinality:
        mode: many_to_many
        output_per_input: 3
      quality_gate: idea_qc

    - id: select_production_ideas
      stage: idea_selection
      depends_on: [generate_ideas]
      cardinality:
        mode: many_to_many
        selection_policy: top_n
        count: 2

    - id: generate_script
      stage: script_generation
      depends_on: [select_production_ideas]
      cardinality:
        mode: one_to_many
        count: 2
      quality_gate: script_qc

    - id: generate_tts
      stage: tts
      depends_on: [generate_script]
      quality_gate: tts_qc

    - id: compose
      stage: composition
      depends_on: [generate_tts]
      quality_gate: composition_qc

    - id: render
      stage: render
      depends_on: [compose]
      cardinality:
        mode: one_to_many
        count: auto
      quality_gate: render_qc

    - id: assemble
      stage: assemble
      depends_on: [render]
      quality_gate: assembly_qc

    - id: final_review
      stage: final_review
      depends_on: [assemble]
      quality_gate: final_qc

  recovery:
    default: retry
    on_quality_failure: regenerate
    on_repeated_failure: human_review
```

The workflow definition is data, not hard-coded Python control flow.

---

# 3. Run Overrides and Previous-Step-Based Decisions

A workflow definition is a baseline.

Example:

```yaml
run_overrides:
  target_language: ja-JP
  script_variants: 3
  max_cost_usd: 2
```

Previous results can affect policy through explicit runtime context:

```yaml
routing_context_rules:

  - when:
      previous.quality.score: "< 0.80"
    set:
      quality_requirement: high

  - when:
      previous.provider: "provider_a"
      previous.status: "failed"
    set:
      exclude_providers:
        - provider_a

  - when:
      attempt: ">= 2"
    set:
      require_provider_diversity: true
```

Keep the distinction explicit:

```text
Previous result:
  script quality = 0.74

Workflow policy:
  regenerate script

Router:
  use provider B for the regeneration
```

---

# 4. Workflow Definition

Conceptually:

```python
class WorkflowDefinition:
    workflow_id: str
    version: str
    nodes: list[StageNode]
    policies: WorkflowPolicies
```

A node declares:

```python
class StageNode:
    node_id: str
    stage_name: str
    depends_on: list[str]
    input_selector: InputSelector
    cardinality: CardinalityPolicy
    quality_gate: QualityGatePolicy | None
    recovery_policy: RecoveryPolicy
    enabled_when: Condition | None
```

---

# 5. Generic Cardinality

Do not hard-code fields such as `script_count`.

Use generic workflow cardinality:

```text
1 → 1
topic → idea

1 → N
idea → script variants

N → 1
render chunks → assembled video

N → M
topics → ideas → scripts
```

```python
class CardinalityPolicy:
    mode: Literal[
        "one_to_one",
        "one_to_many",
        "many_to_one",
        "many_to_many"
    ]
    count: int | None
    selection_policy: str | None
```

The Workflow Engine owns cardinality. The Router does not.

---

# 6. Idea Discovery

Idea Discovery is a first-class but optional stage.

```text
Trigger
   │
   ├── manual topic ──────────────┐
   │                              │
   └── scheduled discovery        │
          ↓                       │
      Topic Discovery             │
          ↓                       │
        Topic[]                   │
          └──────────────┬────────┘
                         ▼
                  Idea Generation
                         ↓
                  CandidateIdea[]
                         ↓
                  Idea Selection
                         ↓
                  ProductionIdea[]
```

**Topic** = what subject/opportunity exists.

**Idea** = what the video should say about it, for which audience, with what angle and promise.

Discovery can be scheduled, manual, webhook-driven, or skipped.

---

# 7. Router — First-Class Architecture

The Router is central, but it does not control the workflow.

Inputs:

```text
CapabilityRequest
EffectiveConfig
RuntimeContext
ProviderRegistry
ProviderHealth
ProviderUsage
PreviousQuality
PreviousProvider
AttemptNumber
Budget
```

Selection pipeline:

```text
Candidate providers
       ↓
Capability compatibility
       ↓
Hard constraints
       ↓
Locale/language
       ↓
Credentials
       ↓
Provider health
       ↓
Quota/budget
       ↓
Previous-result constraints
       ↓
Policy scoring
       ↓
Primary provider
       ↓
Fallback chain
```

Output:

```python
class RoutingDecision:
    capability: str
    implementation: str
    provider: str
    model: str | None
    config: dict
    fallback_chain: list[str]
    policy_version: str
    reason_codes: list[str]
```

Every decision is persisted.

---

# 8. Router Configuration

Avoid a giant `if/else`.

Use provider registry + capability policy + constraints:

```yaml
capabilities:

  tts:
    providers:
      - id: local_chatterbox
        capabilities: [tts]
        locales: [en-US, en-IN]
        quality_class: standard
        cost_class: zero

      - id: provider_b
        capabilities: [tts]
        locales: [en-US, ja-JP, en-IN]
        quality_class: premium
        cost_class: paid

    policy:
      hard_constraints:
        locale_supported: true

      preferences:
        - free_if_available
        - quality
        - latency

      fallback:
        - provider_b
        - local_chatterbox
```

This pattern applies to LLM, TTS, image, video, stock, evaluation and rendering capabilities.

---

# 9. Quality Control Is Per Stage

QC is not only a final-stage operation.

```text
Stage
  ↓
Output Artifact(s)
  ↓
Quality Gate
  ├── PASS
  ├── REGENERATE
  ├── HUMAN_REVIEW
  └── FAIL
```

Examples:

| Stage | QC |
|---|---|
| Topic discovery | relevance, novelty, constraints |
| Idea | usefulness, originality, audience fit |
| Script | schema, evidence, structure, clarity |
| TTS | duration, clipping, loudness, WER, naturalness |
| Visual acquisition | resolution, relevance, provenance |
| Composition | timing, missing assets, alignment |
| Render | frame/technical integrity |
| Assembly | A/V sync, loudness, continuity |
| Final | overall quality, factual review, human approval |

Quality gates produce decisions, not just scores.

---

# 10. Automated + Human QC

Example policy:

```yaml
quality_gate:
  checks:
    - deterministic_schema
    - technical_integrity
    - automated_judge

  thresholds:
    pass: 0.85
    human_review: 0.70

  on_fail:
    action: regenerate

  max_regenerations: 2

  after_max_regenerations:
    action: human_review
```

Human review is a durable workflow state.

---

# 11. Surgical Regeneration

A failed QC should invalidate the smallest necessary scope.

Example:

```text
TTS Scene 03 fails
       ↓
TTS scene_03:v2
       ↓
invalidate composition descendants
       ↓
invalidate affected render chunks
       ↓
reassemble
       ↓
rerun affected QC
```

Do not regenerate the entire video.

```python
class InvalidationRequest:
    root_artifact_ids: list[str]
    reason: str
    scope: Literal["artifact", "scene", "subgraph", "workflow"]
```

---

# 12. Artifact Graph

Artifacts are immutable versions:

```text
script:v1
   │
   ├── tts/scene_01:v1 → composition/scene_01:v1 → render/chunk_01:v1
   ├── tts/scene_02:v1 → composition/scene_02:v1 → render/chunk_01:v1
   └── tts/scene_03:v1 → composition/scene_03:v1 → render/chunk_02:v1
```

If Scene 03 changes:

```text
tts/scene_03:v2
      ↓
composition/scene_03:v2
      ↓
render/chunk_02:v2
```

Unrelated branches remain reusable.

Efficiency rules:

1. Immutable versions.
2. Explicit dependency edges.
3. Hashes for content/config.
4. Deterministic cache keys.
5. Descendant-only invalidation.
6. Logical artifact IDs independent of physical paths.
7. Garbage-collect obsolete binaries separately from metadata.

A useful execution identity is:

```text
hash(
  capability
  + operation_version
  + input_artifact_ids
  + request_payload_fingerprint
  + provider
  + provider_config_hash
)
```

---

# 13. Crash Recovery

The simple rule:

```python
find_first_stage_not_succeeded()
```

is insufficient for external side effects.

A crash can occur after a provider completes but before the DB records success.

Therefore every external operation needs an idempotency/reconciliation strategy.

Recovery:

```text
load workflow run
      ↓
inspect incomplete executions
      ↓
artifact already committed?
   ├── yes → reconcile as success
   └── no
        ↓
provider supports reconciliation?
   ├── yes → reconcile
   └── no → retry according to policy
```

Execution states should include:

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

`UNKNOWN` is important for ambiguous external outcomes.

---

# 14. What Goes in the DB?

Persist meaningful boundaries:

```text
WorkflowRun
StageExecution
CapabilityExecution
ProviderInvocation
RoutingDecision
Artifact
ArtifactDependency
QualityEvaluation
HumanReview
IdempotencyRecord
WorkflowEvent
RecoveryDecision
ProviderUsage
```

Do not turn every helper function, loop iteration, debug print or FFmpeg stdout line into a database row.

Those belong in logs/diagnostics.

---

# 15. Database Authority

SQL is authoritative for:

- workflow/execution state
- routing history
- quality decisions
- human decisions
- artifact metadata
- dependency graph
- idempotency
- usage
- durable events

Object storage is authoritative for:

- audio
- video
- images
- render chunks
- large research/evaluation payloads

`full_state` can remain a convenience snapshot, but correctness must not depend on it.

Recommended core tables:

```sql
workflow_runs(
  run_id,
  workflow_id,
  workflow_version,
  status,
  effective_config_hash,
  created_at,
  updated_at
)

stage_executions(
  execution_id,
  run_id,
  node_id,
  attempt,
  status,
  input_snapshot,
  output_artifact_ids,
  started_at,
  finished_at
)

capability_executions(
  capability_execution_id,
  stage_execution_id,
  capability,
  implementation,
  status,
  request_fingerprint,
  idempotency_key
)

provider_invocations(
  invocation_id,
  capability_execution_id,
  provider,
  operation_id,
  status,
  started_at,
  finished_at,
  cost
)

routing_decisions(
  id,
  run_id,
  stage_execution_id,
  capability,
  decision_json,
  policy_version,
  created_at
)

artifacts(
  artifact_id,
  run_id,
  type,
  version,
  uri,
  sha256,
  producer_execution_id,
  config_hash,
  state,
  created_at
)

artifact_dependencies(
  parent_artifact_id,
  child_artifact_id,
  dependency_type
)

quality_evaluations(
  evaluation_id,
  artifact_id,
  gate_id,
  evaluator,
  scores_json,
  decision,
  created_at
)

human_reviews(
  review_id,
  run_id,
  target_artifact_id,
  decision,
  comments,
  created_at,
  resolved_at
)

idempotency_records(
  idempotency_key,
  capability,
  provider,
  status,
  result_artifact_ids,
  created_at
)

workflow_events(
  event_id,
  run_id,
  event_type,
  payload_json,
  created_at
)
```

---

# 16. Retention

| Data | Suggested retention |
|---|---|
| Workflow state | Permanent |
| Artifact metadata + lineage | Permanent |
| Routing decisions | 1–2 years+ |
| Quality evaluations | 1–2 years+ |
| Human reviews | Long-term |
| Durable events | 6–12 months+ |
| Aggregated metrics | Long-term |
| Debug logs | 7–30 days |
| Raw provider responses | Short-term unless needed |
| Intermediate render chunks | 7–30 days after terminal state |
| Per-scene audio | 7–30 days unless intentionally retained |
| Final published videos | Permanent |
| Failed/superseded binaries | GC after safety window |

Principle:

> **Metadata is cheap. Preserve it. Large binaries are expensive. Garbage-collect them.**

---

# 17. Human Review

Human review produces a durable state:

```text
WAITING_HUMAN
```

Reviewer actions:

```text
APPROVE
  → continue

REGENERATE_SCENE
  → invalidation request

REGENERATE_STAGE
  → stage recovery

REJECT
  → terminal/archive
```

The workflow does not need to remain running while waiting.

---

# 18. Event vs State vs Artifact vs Log

```text
Event:
  "tts completed"

StageExecution:
  "tts attempt 2 succeeded"

RoutingDecision:
  "provider B selected because provider A was unavailable"

Artifact:
  "tts/scene_03:v2"

QualityEvaluation:
  "naturalness=0.88, PASS"

Log:
  "FFmpeg command took 1.84s"
```

They answer different questions and should remain separate.

---

# 19. Stage Purity Clarification

“Pure stage” does not mean “no side effects anywhere”.

It means business stages do not directly own durable infrastructure/provider mutation.

Preferred boundary:

```text
Stage
  → Capability Request
  → Router
  → Provider
  → Artifact Result
  → Orchestrator persistence
```

Adapters are explicitly responsible for external side effects.

---

# 20. Storage Layout

```text
data/
├── db/
│   └── pipeline.sqlite
├── videos/
│   └── {run_id}/
│       ├── idea/
│       ├── script/
│       ├── tts/
│       ├── visual/
│       ├── composition/
│       ├── render/
│       ├── final/
│       └── evaluation/
└── gold_set/
```

Physical paths are implementation details. Artifact identity lives in SQL.

---

# 21. Complete Failure Example

```text
Script:v1
   ↓
TTS Scene 03:v1
   ↓
Quality Gate
   ↓
REGENERATE
   ↓
Workflow Recovery Policy
   ↓
CapabilityRequest(TTS)
   ↓
Router
   ↓
Provider B
   ↓
TTS Scene 03:v2
   ↓
Artifact Graph
   ↓
invalidate descendants
   ↓
Composition Scene 03:v2
   ↓
Render Chunk 02:v2
   ↓
Assembly:v2
   ↓
Final QC
```

The DB records why regeneration happened, which artifact failed, which provider was selected, which policy selected it, which inputs/config were used, what became invalid and what was reused.

---

# 22. Recommended Repository

```text
video-pipeline/
├── packages/
│   ├── core/
│   │   ├── contracts/
│   │   ├── workflow/
│   │   ├── router/
│   │   ├── artifacts/
│   │   ├── execution/
│   │   ├── quality/
│   │   └── storage/
│   ├── stages/
│   │   ├── topic_discovery/
│   │   ├── idea/
│   │   ├── script/
│   │   ├── tts/
│   │   ├── visual/
│   │   ├── composition/
│   │   ├── render/
│   │   ├── assemble/
│   │   └── publish/
│   ├── adapters/
│   │   ├── llm/
│   │   ├── tts/
│   │   ├── image/
│   │   ├── video/
│   │   ├── stock/
│   │   ├── evaluator/
│   │   ├── renderer/
│   │   └── storage/
│   ├── runners/
│   │   └── local.py
│   └── utils/
├── workflows/
├── configs/
├── prompts/
├── templates/
├── assets/
├── data/
├── tests/
├── AGENTS.md
├── ARCHITECTURE.md
└── main.py
```

---

# 23. Implementation Order

### Phase 1 — Execution spine

1. Contracts
2. SQLite repositories
3. Artifact store
4. Workflow definition loader
5. Workflow engine
6. One capability
7. Router
8. One mock provider
9. QC gate
10. Resume/idempotency

### Phase 2 — Real video path

11. Topic/Idea
12. Script
13. TTS
14. measured timing
15. composition
16. render
17. assembly

### Phase 3 — Recovery and quality

18. per-stage QC
19. automated regeneration
20. human review
21. surgical invalidation
22. artifact GC

### Phase 4 — Scale

23. parallel fan-out
24. fan-in
25. provider health
26. usage/quota tracking
27. multiple providers
28. cloud storage
29. durable workflow engine

Do not start with Temporal/Kafka/Kubernetes/microservices/autonomous orchestration. First prove:

```text
workflow → stage → capability → router → provider
→ artifact → QC → recovery → resume
```

---

# 24. Architecture Invariants

1. Workflow controls transitions; Router controls provider selection.
2. Stages never directly call provider SDKs.
3. Providers never mutate workflow state.
4. Every external side effect has an idempotency strategy.
5. Artifacts are immutable.
6. Artifact dependencies are explicit.
7. Quality gates exist wherever output quality matters.
8. Quality failure can trigger scoped regeneration.
9. Regeneration invalidates descendants, not unrelated branches.
10. Cardinality is generic.
11. Idea Discovery can be skipped or inserted without redesigning the engine.
12. Previous-step results influence policy through explicit runtime context.
13. DB is authoritative for execution metadata.
14. Object storage is authoritative for large bytes.
15. Logs are not workflow state.
16. `full_state` is a convenience projection, not the authority.
17. Metadata retention is independent of binary retention.
18. Provider/model names are configuration, not domain logic.
19. The system remains runnable locally without a cloud orchestrator.
20. The control flow remains deterministic even when capabilities use probabilistic models.

**Historical note:** This document is retained for rationale only. Further
implementation changes must follow the canonical architecture, focused
documents, registries, and accepted ADRs.
