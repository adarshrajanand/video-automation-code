# AI Video Automation Pipeline — End-to-End Implementation Plan

**Status:** Target implementation plan after fast validation

**Purpose:** Give coding agents a dependency-aware sequence for evolving the validated local slice into a high-quality, recoverable, event-driven production platform.

**Rule:** Do not start a later phase because it is described here. Start it when the preceding exit criteria and measured bottleneck justify it.

## 1. Implementation strategy

The implementation progresses through a modular monolith, selective worker separation, and only then distributed durability.

```text
Contracts and evidence
        ↓
Local execution spine
        ↓
Real media vertical slice
        ↓
Quality and repair
        ↓
Repeatable local production
        ↓
Selective workers and containerization
        ↓
Remote durable state and artifacts
        ↓
Scaling, routing, publishing, analytics
```

The system should be complex in its documented model before it is complex in its deployment. The implementation must preserve one-way-door decisions without implementing every future component.

## 2. Target repository layout

The names are a recommended starting point. Agents may adjust names only when they preserve the responsibilities and contracts.

```text
video-automation/
├── pyproject.toml
├── README.md
├── AGENTS.md
├── Makefile or task runner configuration
├── src/
│   └── pipeline/
│       ├── cli.py
│       ├── settings.py
│       ├── contracts/
│       │   ├── common.py
│       │   ├── workflow.py
│       │   ├── execution.py
│       │   ├── capabilities.py
│       │   ├── artifacts.py
│       │   ├── quality.py
│       │   ├── review.py
│       │   └── content.py
│       ├── persistence/
│       │   ├── migrations/
│       │   ├── repository.py
│       │   ├── sqlite.py
│       │   └── transactions.py
│       ├── artifacts/
│       │   ├── store.py
│       │   ├── local.py
│       │   ├── lineage.py
│       │   └── garbage_collection.py
│       ├── workflow/
│       │   ├── definition.py
│       │   ├── validation.py
│       │   ├── readiness.py
│       │   ├── cardinality.py
│       │   ├── transitions.py
│       │   ├── recovery.py
│       │   └── invalidation.py
│       ├── execution/
│       │   ├── jobs.py
│       │   ├── leases.py
│       │   ├── worker.py
│       │   ├── registry.py
│       │   └── result_commit.py
│       ├── events/
│       │   ├── envelope.py
│       │   ├── outbox.py
│       │   ├── dispatcher.py
│       │   └── polling.py
│       ├── capabilities/
│       │   ├── protocol.py
│       │   ├── registry.py
│       │   ├── requests.py
│       │   └── results.py
│       ├── routing/
│       │   ├── router.py
│       │   ├── registry.py
│       │   ├── policy.py
│       │   ├── budget.py
│       │   └── health.py
│       ├── providers/
│       │   ├── base.py
│       │   ├── fake/
│       │   ├── llm/
│       │   ├── speech/
│       │   ├── asr/
│       │   ├── media/
│       │   └── publishing/
│       ├── stages/
│       │   ├── intake/
│       │   ├── ideation/
│       │   ├── research/
│       │   ├── script/
│       │   ├── visuals/
│       │   ├── speech/
│       │   ├── composition/
│       │   ├── rendering/
│       │   ├── assembly/
│       │   ├── derivatives/
│       │   └── publishing/
│       ├── quality/
│       │   ├── checks.py
│       │   ├── evaluators.py
│       │   ├── gates.py
│       │   ├── escalation.py
│       │   ├── repairs.py
│       │   └── gold_set.py
│       ├── profiles/
│       │   ├── domain.py
│       │   ├── channel.py
│       │   └── effective_config.py
│       └── observability/
│           ├── logging.py
│           ├── metrics.py
│           └── correlation.py
├── packages/
│   └── renderer/
│       ├── package.json
│       ├── src/
│       ├── schemas/
│       └── tests/
├── workflows/
├── configs/
│   ├── system/
│   ├── domains/
│   ├── channels/
│   └── providers/
├── prompts/
├── rubrics/
├── fixtures/
├── gold_set/
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   ├── recovery/
│   ├── media/
│   └── evaluation/
├── reports/
└── kb/docs/
```

Do not create every directory in the first commit. Create a directory when its first bounded implementation is ready.

## 3. Phase 0 — Repository bootstrap

### Objective

Make the repository runnable and give agents precise checks.

### Deliverables

- supported Python version;
- package manager and lockfile policy;
- lint, format, typecheck, test, and build commands;
- Node/Remotion package and renderer check;
- setup diagnostics for FFmpeg/ffprobe;
- local infrastructure profile with startup/readiness and recovery behavior;
- `AGENTS.md` with implementation rules;
- secret handling and `.env.example`;
- CI running contract/unit checks.

### Acceptance criteria

- a new developer can run setup from the README;
- tests run without provider credentials;
- no credentials are committed or printed;
- CI fails on contract/type/test regressions.

## 4. Phase 1 — Stable contracts and configuration

### Objective

Make all boundaries explicit before adding complex stage behavior.

### Work packages

1. Common identifiers, timestamps, fingerprints, versions, and errors.
2. Layered configuration resolver.
3. Workflow definition schema and validation.
4. Execution and job contracts.
5. Capability/provider contracts.
6. Artifact and lineage contracts.
7. Quality/review contracts.
8. Content/composition contracts.

### Required behavior

- every serialized contract has a schema/version;
- unknown or incompatible versions fail clearly;
- configuration resolution records source layer and effective hash;
- mutable dictionaries are not used where a stable typed contract is required;
- request fingerprints exclude nondeterministic fields;
- secrets are never part of fingerprints or logs;
- external errors normalize into retryability, provider status, and unknown-outcome fields.

### Exit criteria

- contract fixtures pass;
- JSON schemas can be generated or checked;
- a contract migration test demonstrates rejection of incompatible payloads;
- the renderer can consume a minimal composition fixture.

## 5. Phase 2 — Persistence, artifacts, and lineage

### Objective

Create authoritative local state and immutable binary references.

### Initial tables

Implement the tables described in the contracts document, at minimum:

- `workflow_runs`;
- `effective_configs`;
- `stage_instances`;
- `stage_attempts`;
- `jobs`;
- `leases` or lease fields with history;
- `capability_executions`;
- `idempotency_records`;
- `budget_reservations`;
- `provider_invocations`;
- `routing_decisions`;
- `artifacts`;
- `artifact_dependencies`;
- `artifact_pointers`;
- `quality_evaluations`;
- `quality_gate_results`;
- `human_reviews`;
- `workflow_events`;
- `outbox_messages`;
- `usage_records`;
- `recovery_decisions`.

### Artifact protocol

1. Write output to a temporary workspace.
2. Validate output structure and media integrity.
3. Compute checksum and metadata.
4. Move/copy bytes into the ArtifactStore using an immutable URI.
5. Commit artifact metadata and dependency edges transactionally with stage result.
6. Create quality work and a quality-event intent in the same transaction where possible; create downstream readiness only after the aggregate gate passes.
7. Reconcile orphaned bytes if the metadata transaction fails.

### Exit criteria

- artifact history cannot be overwritten;
- active pointers can change without changing artifact identity;
- descendants can be found by graph traversal;
- local files can be moved without changing logical artifact IDs;
- database records remain meaningful if large binaries are later deleted.

## 6. Phase 3 — Deterministic workflow engine

### Objective

Implement fixed, inspectable control flow before adding model creativity.

### Required engine capabilities

- load a versioned workflow;
- validate DAG topology and stage references;
- resolve effective configuration;
- create a run and initial stage instances;
- determine readiness from durable state;
- support selected `1→1`, `1→N`, and `N→1` cases;
- create idempotent logical stage instances;
- apply quality gate decisions;
- schedule retries and repairs;
- pause and resume for human review;
- calculate descendant invalidation;
- mark workflow terminal state.

### Explicit non-goal

Do not begin with an arbitrary user-programmable workflow language. Use a validated data definition and a bounded set of selectors/cardinality policies. Generalize only when a real workflow requires it.

## 7. Phase 4 — Local event-driven execution

### Objective

Make work independently claimable while keeping state local.

### Components

- outbox writer;
- polling dispatcher;
- job claim transaction;
- lease renewal/expiry;
- worker registry;
- stage registry;
- result commit protocol;
- recovery scan;
- dead-letter/human-attention record.

### Required transaction boundaries

**Create work**

```text
BEGIN
  create or find stage instance
  create attempt/job if absent
  insert outbox notification
COMMIT
```

**Claim work**

```text
BEGIN
  atomically claim READY job
  assign lease owner and expiry
  mark attempt RUNNING
COMMIT
```

**Commit success**

```text
validate outputs
write bytes to ArtifactStore
BEGIN
  create artifact metadata/dependencies
  record capability/provider usage
  mark attempt execution_status=SUCCEEDED
  mark stage acceptance_status=PENDING
  create quality work and a quality-event notification
COMMIT
```

The quality worker then performs a separate authoritative transition:

```text
BEGIN
  persist individual QualityEvaluation records
  persist aggregate QualityGateResult
  update stage acceptance_status
  if decision == PASS:
      create downstream stage readiness and outbox notification
  elif decision == REGENERATE:
      persist RepairPlan and invalidation intent
  elif decision == HUMAN_REVIEW:
      persist HumanReview and pause affected work
COMMIT
```

No downstream stage is eligible merely because execution succeeded.

**Recovery**

```text
find expired/unknown attempts
inspect idempotency and artifact records
reconcile provider operation if possible
otherwise apply bounded retry or human-attention policy
record RecoveryDecision
```

### Exit criteria

- duplicate notifications are harmless;
- stale leases are recoverable;
- state transition and event intent cannot diverge silently;
- workers revalidate readiness rather than trusting old messages.

## 8. Phase 5 — Real content stages

Implement stages in this order:

### 8.1 Intake and idea development

Inputs:

- topic or source candidates;
- domain/channel profile;
- target audience;
- target duration;
- output profile;
- budget and provider policy.

Outputs:

- `ProductionIdea`;
- editorial brief;
- constraints and prohibited claims/topics;
- desired audience promise.

Deterministic checks:

- required fields;
- language/locale;
- duplicate idea IDs;
- channel constraints;
- title/promise length;
- similarity to recent ideas where a corpus exists.

### 8.2 Research and evidence

Outputs:

- source records/snapshots;
- claim ledger;
- evidence records;
- unresolved questions;
- source conflict record.

No script claim should be treated as verified merely because a model labels it verified. Source existence, excerpt references, dates, numbers, and units must be mechanically checked where possible.

### 8.3 Script generation

Outputs:

- outline;
- script version;
- scene list;
- claim IDs;
- visual intents;
- duration policy;
- caption text;
- pronunciation hints.

The script stage may use several model calls, but the stage contract is one bounded execution with explicit internal limits.

### 8.4 Visual planning and asset acquisition

Visual planning must precede asset acquisition. It should specify:

- scene objective;
- shot purpose;
- required visual elements;
- prohibited/misleading elements;
- asset type preference;
- timing;
- text/graphic overlays;
- provenance/licensing requirements.

Asset acquisition must return provenance and a content hash for every source asset.

### 8.5 Speech generation

Speech generation selects the configured `CONTINUOUS` or `SCENE_SEGMENTED`
strategy and emits the same normalized speech manifest for either mode. A
continuous pass derives scene timing from alignment; a scene-segmented pass
preserves surgical repair boundaries. It must preserve:

- script ID and version;
- scene IDs and narration text hashes;
- voice/provider/model identity;
- voice configuration hash;
- normalized narration text;
- audio metadata;
- word and scene timing from ASR/forced alignment;
- ASR transcript;
- loudness and peak measurements.

Composition must reject mismatched script versions, scene IDs, or narration
text hashes across the speech and visual branches. Switching continuity modes
during repair requires an explicit replacement and continuity check; it must
not silently splice incompatible audio.

### 8.6 Composition, rendering, and assembly

Composition must be deterministic with respect to:

- composition schema version;
- input artifact IDs/hashes;
- effective configuration;
- renderer version;
- fonts and template versions;
- timing/timebase;
- random seeds where randomness is used.

Rendering produces chunk or complete-cut artifacts from the resolved manifest.
Assembly is the explicit fan-in boundary for chunked outputs and records its
ordered chunk manifest, continuity checks, and resulting cut artifact.

## 9. Phase 6 — Quality system and repair

Implement quality as its own package and data model, not as ad hoc checks inside stages.

### Gate order

1. deterministic schema/constraint checks;
2. technical media checks;
3. specialized measurements;
4. narrow semantic evaluation;
5. escalation for borderline/high-impact/disagreement cases;
6. human review where policy requires it;
7. gate decision and repair scope.

### Repair protocol

1. store failed evaluation against exact artifact versions;
2. classify failure code and severity;
3. resolve repair policy;
4. calculate minimal invalidation descendants;
5. create a new stage instance/attempt or repair request;
6. preserve previous artifacts;
7. rerun only affected gates and descendants;
8. stop after bounded attempts and request human review.

## 10. Phase 7 — Domain profiles and channels

Implement profile inheritance:

```text
SystemPolicy
  → DomainProfile
  → ChannelProfile
  → WorkflowDefinition
  → RunOverrides
  → EffectiveConfig
```

Initial profiles:

- `software_engineering_explainer_v1`;
- `finance_education_high_review_v1`;
- `math_physics_explainer_v1`;
- `entertainment_narrative_v1`.

Each profile must declare:

- required stages;
- optional stages;
- claim/evidence policy;
- source classes;
- freshness policy;
- quality gates and thresholds;
- human-review triggers;
- asset/licensing policy;
- locale and unit conventions;
- prohibited content and publishing rules.

## 11. Phase 8 — Benchmark-driven provider routing

### Capability benchmarks

Benchmark by capability, not simply by stage:

- structured text generation;
- claim/evidence entailment;
- script clarity and editorial quality;
- code correctness;
- mathematical/physical verification;
- TTS fidelity;
- TTS naturalness;
- ASR timing;
- image/visual relevance;
- visual artifact detection;
- holistic final review.

### Required benchmark metrics

- false-accept rate;
- false-reject rate;
- defect recall by severity;
- abstention/escalation rate;
- human agreement where meaningful;
- latency;
- token/compute cost;
- cost per accepted artifact;
- regeneration rate after acceptance;
- data-policy eligibility.

### Routing rollout

1. fixed provider per capability;
2. registry and eligibility rules;
3. explicit fallback chain;
4. budget reservations and usage ledger;
5. health and quota observations;
6. shadow evaluation;
7. canary routing;
8. evidence-based promotion/rollback.

## 12. Phase 9 — Containerization and selective workers

Use the [Local Infrastructure Profile](AI_Video_Pipeline_Local_Infrastructure_Profile.md)
as the operational baseline. The deferred target details are in the
[Remote Infrastructure Expansion](AI_Video_Pipeline_Remote_Infrastructure_Expansion.md)
document. Start with one image and role commands:

```text
pipeline control reconcile
pipeline dispatcher run
pipeline worker cpu
pipeline worker media
pipeline worker evaluator
```

Split images only when:

- media dependencies materially enlarge the image;
- GPU dependencies conflict with CPU dependencies;
- cold start/transfer time matters;
- security boundaries differ;
- worker reliability requires isolation.

The same contracts and stage packages must work inside and outside containers.

## 13. Phase 10 — Remote durable execution

Introduce remote execution only after local worker behavior is tested.

### Migration order

1. optionally package local roles in one versioned image;
2. move artifact bytes to object storage while retaining local adapter tests and
   completing an orphan/reconciliation rehearsal;
3. move authoritative metadata to PostgreSQL or a justified managed database;
4. run one remote CPU worker using opaque artifact URIs;
5. run one bounded GPU/media worker when measured workload requires it;
6. add a queue if polling is a measured bottleneck;
7. add resource placement, backpressure, and independent worker pools.

This order is the default accepted by ADR-024 and detailed in the Remote
Infrastructure Expansion document. A queue is a delivery adapter, not workflow
authority, and should not be added before its operational value is measured.

### Remote worker rules

- never depend on shared network SQLite;
- download only required artifacts;
- validate checksums before execution;
- upload before metadata commit;
- use temporary workspaces and cleanup;
- tolerate worker disappearance at any point;
- enforce runtime and spend limits;
- keep control-plane state independent of worker lifetime.

## 14. Phase 11 — Publishing and platform integrations

Publishing is a capability behind a durable approval gate.

Before upload, validate:

- exact approved artifact hash;
- title/description/thumbnail alignment;
- platform dimensions and encoding;
- rights/provenance metadata;
- captions and language;
- scheduled time and timezone;
- human reviewer and approval timestamp;
- budget and publication policy.

Upload operations need idempotency and platform reconciliation. A timeout must not blindly upload the same video twice.

## 15. Phase 12 — Analytics and learning

Treat post-publication behavior as evidence, not direct truth. Record:

- impressions and click-through rate with traffic context;
- retention/drop-off timestamps;
- average view duration;
- completion rate;
- returning viewers;
- comments/negative feedback where permitted;
- corrections and takedowns;
- production cost and time;
- regeneration and review rates.

Use observations to propose experiments. Do not automatically rewrite quality policy from one performance metric.

## 16. Phase 13 — Localization and additional formats

Localization should derive from an approved canonical content package, not independently regenerate unsupported facts.

Preserve:

- source claim IDs;
- translation version;
- localized narration;
- locale-specific voice and pronunciation;
- units/date/currency conventions;
- caption timing;
- localized visual text;
- locale-specific QC.

Presenter or hybrid formats should add capabilities and composition layers rather than fork the workflow engine.

## 17. Cross-cutting engineering requirements

### Security

- secrets only through environment/secret manager;
- no raw credentials in logs or artifacts;
- untrusted source content isolated from system prompts/tools;
- web retrieval allowlists and SSRF protection;
- media type/size/decode limits;
- least-privilege provider credentials;
- data classification before provider routing;
- explicit retention for raw provider payloads.

### Reproducibility

Record:

- source and asset hashes;
- code/package version;
- schema versions;
- workflow/config hashes;
- prompt/rubric versions;
- provider/model/version;
- random seed where relevant;
- renderer/font versions;
- environment/media profile.

### Observability

Every log/event/metric should be correlatable by:

```text
run_id
stage_instance_id
attempt_id
job_id
event_id
artifact_id
evaluation_id
provider_invocation_id
```

Minimum metrics:

- ready/running/paused/unknown counts;
- queue depth and oldest age;
- stage latency p50/p95;
- retry and timeout rate;
- provider errors and quota observations;
- artifact upload/commit failures;
- QC pass/regenerate/review/fail rates;
- false-pass audit findings;
- cost per stage and accepted video;
- invalidation fan-out;
- human-review queue age;
- worker startup/useful runtime.

## 18. Agent work allocation after fast validation

Agents may work in parallel only when their contracts are stable and their owned files do not overlap.

### Track A — Core execution

Contracts, repository, workflow, jobs, outbox, recovery, CLI.

### Track B — Media

Composition schema, Remotion, FFmpeg, audio timing, render profiles, technical checks.

### Track C — Content capabilities

Research, script, visual planning, asset adapters, TTS, ASR.

### Track D — Quality

Check registry, evaluators, gold set, benchmark harness, gates, repair.

### Track E — Profiles and publishing

Domain/channel profiles, metadata, human review, platform adapters.

### Track F — Operations

Docker, worker roles, storage migration, observability, deployment.

Each track must return:

- files changed;
- contracts consumed/added;
- migrations;
- tests run and results;
- known limitations;
- next dependency.

## 19. Release gates

### Local alpha

- fast-plan acceptance criteria pass;
- no known uncontrolled duplicate spending;
- artifact lineage and repair work;
- human approval is required;
- publishing is disabled or dry-run only.

### Private production

- repeated runs meet target quality policy;
- provider/budget policy is enforced;
- reviewer can inspect evidence;
- source/asset provenance is retained;
- recovery drills pass;
- a holdout QC set is used;
- publication adapter reconciliation is tested.

### Scaled production

- remote worker stop/restart is safe;
- database/object-store backup and restore are tested;
- queue/backpressure metrics are available;
- cost per accepted video is within policy;
- false-pass audits are running;
- model/provider changes use shadow/canary evaluation;
- retention and garbage collection preserve required metadata.

## 20. Stop conditions

Pause expansion and fix the foundation if any of these occur:

- accepted artifacts cannot be traced to exact inputs;
- duplicate delivery creates uncontrolled provider spend;
- a provider timeout causes blind duplicate generation;
- a quality failure silently unlocks downstream work;
- scene repair forces full-workflow regeneration without policy reason;
- human decisions are only in memory;
- a provider/model change makes old queued jobs non-reproducible;
- cost per accepted video is unknown;
- source/license provenance is missing;
- a worker cannot be stopped without losing authoritative state.

## 21. Final end-state criterion

The end-to-end system is approaching maturity when it can run the target weekly workload while preserving:

- reproducible content and media artifacts;
- explainable quality decisions;
- bounded and observable cost;
- surgical regeneration;
- safe provider/resource changes;
- durable human review;
- graceful worker failure and resumption;
- domain-specific policy without domain-specific infrastructure forks.
