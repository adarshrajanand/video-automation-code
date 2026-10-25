# AI Video Automation Pipeline — Fast Validation Plan

**Status:** Ready for implementation after repository bootstrap

**Purpose:** Validate the most important architectural and media chokepoints quickly without implementing the full distributed end state.

**Primary references:** [Canonical Architecture](AI_Video_Pipeline_Architecture.md), [Contracts](AI_Video_Pipeline_Contracts_and_Data_Model.md), [Workflow and Event Execution](AI_Video_Pipeline_Workflow_and_Event_Execution.md), [Local Infrastructure Profile](AI_Video_Pipeline_Local_Infrastructure_Profile.md), [Content Model](AI_Video_Pipeline_Content_Model_and_Composition.md), and [Quality System](AI_Video_Pipeline_Quality_System.md).

## 1. Outcome

The fast validation is complete when the repository can:

1. run a manually supplied software-engineering explainer through a local workflow;
2. produce a landscape long-form render and one derived vertical short;
3. persist every meaningful run, stage, attempt, artifact, dependency, routing decision, evaluation, and human-review state;
4. perform deterministic validation before downstream readiness;
5. perform at least one structured semantic evaluation;
6. pause for and resume from a human approval record;
7. regenerate one failed scene without rebuilding unrelated scenes;
8. survive forced process termination and duplicate delivery safely;
9. explain the final output from a run manifest, hashes, versions, and evidence; and
10. demonstrate that the architecture can later move a worker or artifact store without changing stage business contracts.

This is a validation slice, not a production-ready publishing service.

## 2. Scope and deliberate exclusions

### 2.1 Included

- Python control plane and local CLI;
- Pydantic contracts and JSON-serializable payloads;
- SQLite repository;
- local filesystem `ArtifactStore`;
- one fixed, versioned workflow definition;
- manual topic input;
- small research/evidence fixture or configured local source fixture;
- structured script generation through a capability interface;
- visual planning with procedural and/or fixture assets;
- configurable continuous or scene-segmented speech strategy, backed by one TTS
  implementation or deterministic audio fixture;
- ASR/timing validation where available;
- Remotion composition and FFmpeg media inspection;
- one short derivative;
- deterministic QC checks;
- one narrow semantic judge capability;
- artifact lineage and scoped invalidation;
- local outbox and polling dispatcher;
- one worker execution path;
- local startup readiness, recovery scan, and orphan-reconciliation behavior;
- fault injection and recovery tests;
- human approval represented as durable state.

### 2.2 Excluded

- automatic public publishing;
- multiple external queues;
- PostgreSQL;
- cloud object storage;
- cloud GPU scheduling;
- multiple production channels;
- a general-purpose agent framework;
- autonomous topic discovery across the open web;
- automatic paid fallback;
- a full review UI;
- production-grade analytics ingestion;
- remote workers, external queues, hosted databases, and cloud object storage;
- presenter/avatar/lip-sync modes;
- a complete finance production workflow.

## 3. Validation architecture

The fast plan has two lanes that share the same contracts and repository.

```text
Lane A: Execution Spine
mock capabilities → jobs → leases → artifacts → QC → recovery

Lane B: Real Media Slice
topic → script → visual/audio → composition → render chunks → assembly
→ short → QC → review
```

Lane A proves state and failure behavior cheaply. Lane B proves that the abstractions actually carry a media product from input to inspectable output.

## 4. Reference workflow

The normative workflow YAML fixture is
[`registries/fast_workflow.yaml`](registries/fast_workflow.yaml). The loader
must normalize it into the `WorkflowDefinition` and `StageNode` contracts
without silently inventing fields. The registry is the only source of truth for
IDs, versions, dependencies, stage names, cardinality, gates, and recovery
policies.

For the first run, `intake` accepts a supplied topic and `idea` returns a
deterministic production brief. `selection_policy: manifest_children` resolves
the one-to-many children from an explicit scene/shot manifest created by the
upstream stage, not from queue length. Rendering fans out into chunks and
assembly explicitly fans those chunks back in before short derivation and final
review.

The short derivative depends on quality-accepted composition and assembled
long-form inputs, not on human publication approval. Long-form and short outputs
each receive their own quality gates; the final review and `human_approval`
nodes then decide whether the package becomes `publication_ready`.

### 4.1 Fast-slice stage and policy registry

The loader must reject names not in this registry:

| ID | Kind | Initial implementation |
|---|---|---|
| `manual_topic` | stage | manual input |
| `idea_development` | stage | deterministic brief fixture |
| `research` | stage | bounded source/evidence fixture |
| `script_generation` | stage | structured model or fixture |
| `visual_planning` | stage | structured plan |
| `asset_acquisition` | stage | procedural/fixture assets |
| `speech_generation` | stage | TTS adapter or fixture |
| `composition` | stage | composition builder |
| `rendering` | stage | Remotion/FFmpeg |
| `short_derivative` | stage | selection/recomposition |
| `assembly` | stage | render-chunk fan-in and continuity |
| `technical_content_review` | stage | aggregate final QC |
| `human_approval` | stage | durable review decision |
| `research_gate_v1` | gate | deterministic source/evidence checks |
| `script_gate_v1` | gate | schema/claim/editorial checks |
| `visual_plan_gate_v1` | gate | plan structure/relevance |
| `asset_gate_v1` | gate | media/provenance checks |
| `speech_gate_v1` | gate | audio/ASR checks |
| `composition_gate_v1` | gate | timeline checks |
| `render_gate_v1` | gate | technical media checks |
| `assembly_gate_v1` | gate | chunk order, duration, sync, and loudness checks |
| `short_gate_v1` | gate | vertical/context checks |
| `final_gate_v1` | gate | final technical/content checks |
| `human_publication_gate_v1` | gate | human approval |
| `default_recovery_v1` | recovery | bounded retry, repair, then review |

The fast slice must register these versioned `QualityCheck` fixtures. The columns map directly to the `QualityCheck` contract.

| Check ID | Kind | Target | On failure | Repair scope |
|---|---|---|---|---|
| `source_exists_v1` | `DETERMINISTIC` | source/evidence | `FAIL` | `NONE` |
| `evidence_reference_integrity_v1` | `DETERMINISTIC` | evidence | `REGENERATE` | `SCENE` |
| `script_schema_v1` | `DETERMINISTIC` | script | `REGENERATE` | `STAGE` |
| `claim_reference_integrity_v1` | `DETERMINISTIC` | script | `REGENERATE` | `SCENE` |
| `script_claim_evidence_v1` | `SEMANTIC` | script | `REGENERATE` | `SCENE` |
| `script_editorial_clarity_v1` | `SEMANTIC` | script | `REGENERATE` | `STAGE` |
| `scene_shot_structure_v1` | `DETERMINISTIC` | visual plan | `REGENERATE` | `SCENE` |
| `visual_intent_completeness_v1` | `SEMANTIC` | visual plan | `REGENERATE` | `SCENE` |
| `media_decode_v1` | `DETERMINISTIC` | source asset | `REGENERATE` | `SHOT` |
| `media_dimensions_v1` | `DETERMINISTIC` | source asset | `REGENERATE` | `ASSET` |
| `provenance_v1` | `DETERMINISTIC` | source asset | `HUMAN_REVIEW` | `ASSET` |
| `audio_decode_v1` | `DETERMINISTIC` | speech | `REGENERATE` | `SCENE` |
| `audio_duration_loudness_v1` | `SPECIALIZED` | speech | `REGENERATE` | `SCENE` |
| `transcript_fidelity_v1` | `SPECIALIZED` | speech | `REGENERATE` | `SCENE` |
| `timeline_ranges_v1` | `DETERMINISTIC` | composition | `REGENERATE` | `SCENE` |
| `required_layers_v1` | `DETERMINISTIC` | composition | `REGENERATE` | `SHOT` |
| `composition_reconstructable_v1` | `DETERMINISTIC` | composition | `FAIL` | `STAGE` |
| `render_decode_v1` | `DETERMINISTIC` | render | `REGENERATE` | `STAGE` |
| `output_profile_v1` | `DETERMINISTIC` | render | `REGENERATE` | `STAGE` |
| `black_freeze_audio_presence_v1` | `SPECIALIZED` | render | `REGENERATE` | `STAGE` |
| `assembly_order_duration_v1` | `DETERMINISTIC` | assembled cut | `REGENERATE` | `CUT` |
| `assembly_sync_loudness_v1` | `SPECIALIZED` | assembled cut | `REGENERATE` | `CUT` |
| `vertical_profile_v1` | `DETERMINISTIC` | short | `REGENERATE` | `STAGE` |
| `context_preservation_v1` | `SEMANTIC` | short | `HUMAN_REVIEW` | `SCENE` |
| `caption_safe_area_v1` | `DETERMINISTIC` | short | `REGENERATE` | `SHOT` |
| `complete_technical_review_v1` | `DETERMINISTIC` | final cut | `FAIL` | `CUT` |
| `final_content_review_v1` | `SEMANTIC` | final cut | `HUMAN_REVIEW` | `CUT` |
| `human_publication_approval_v1` | `HUMAN` | final package | `HUMAN_REVIEW` | `WORKFLOW` |

Each row is materialized with `schema_version: quality-check.v1`, `evaluator_version`, `required_input_types`, severity, and the exact `on_failure`/repair scope shown above. The fast implementation may use fixture evaluators, but it must not omit the contract records.

The gate policies use exactly these check IDs:

| Gate ID | Required checks |
|---|---|
| `research_gate_v1` | `source_exists_v1`, `evidence_reference_integrity_v1` |
| `script_gate_v1` | `script_schema_v1`, `claim_reference_integrity_v1`, `script_claim_evidence_v1`, `script_editorial_clarity_v1` |
| `visual_plan_gate_v1` | `scene_shot_structure_v1`, `visual_intent_completeness_v1` |
| `asset_gate_v1` | `media_decode_v1`, `media_dimensions_v1`, `provenance_v1` |
| `speech_gate_v1` | `audio_decode_v1`, `audio_duration_loudness_v1`, `transcript_fidelity_v1` |
| `composition_gate_v1` | `timeline_ranges_v1`, `required_layers_v1`, `composition_reconstructable_v1` |
| `render_gate_v1` | `render_decode_v1`, `output_profile_v1`, `black_freeze_audio_presence_v1` |
| `short_gate_v1` | `vertical_profile_v1`, `context_preservation_v1`, `caption_safe_area_v1` |
| `assembly_gate_v1` | `assembly_order_duration_v1`, `assembly_sync_loudness_v1` |
| `final_gate_v1` | `complete_technical_review_v1`, `final_content_review_v1` |
| `human_publication_gate_v1` | `human_publication_approval_v1` |

Each gate is a `QualityGatePolicy` with `version: "1.0"`, the listed required checks, explicit hard-failure codes, empty or calibrated threshold maps, `max_regenerations: 2` for repairable gates, and `after_max_regenerations: HUMAN_REVIEW`.

The normative check and gate fixture is
[`registries/quality_gates.yaml`](registries/quality_gates.yaml). It includes
the assembly gate and uses namespaced failure codes from
[`registries/failure_codes.yaml`](registries/failure_codes.yaml). The fast
fixture has no implicit score defaults: semantic checks must return an explicit
categorical outcome or use thresholds declared in the registry.

For the fast fixture, every check row uses
`schema_version: quality-check.v1`, `evaluator_version: fast-fixture-v1`,
`required: true`, and `rubric_version: null` unless the check kind is
`SEMANTIC`; semantic checks use `rubric_version: fast-rubric-v1`. Set
`severity_if_failed=CRITICAL` when the check emits a registered hard-failure
code and `MAJOR` otherwise. The table's failure action and repair scope are the
per-check values. The normative retry and recovery fixture is
[`registries/recovery.yaml`](registries/recovery.yaml).

## 5. Acceptance criteria

### 5.1 User-visible acceptance

- A developer can create a run from a CLI command using a topic and channel profile.
- The CLI prints a stable run ID and can show current state.
- The run produces an inspectable long-form video file and one vertical short file.
- A reviewer can see the artifacts, QC decisions, evidence, and pending approval state.
- Approval resumes the run; rejection creates a recorded repair or terminal decision.
- A failed scene can be repaired without regenerating unrelated scenes.

### 5.2 Data acceptance

Every accepted output must be traceable to:

- workflow ID/version;
- effective configuration hash;
- input artifact IDs and hashes;
- stage/attempt IDs;
- code/contract version;
- prompt/rubric/model/provider versions where applicable;
- quality evaluations and gate decisions;
- human approval record;
- final artifact hash and media metadata.

### 5.3 Reliability acceptance

The test suite must demonstrate:

1. duplicate trigger with the same `run_key` returns the existing run and does not create duplicate logical work;
2. duplicate event delivery is harmless;
3. worker crash before provider call can be reclaimed;
4. worker crash after provider success is reconciled or remains explicitly `UNKNOWN`;
5. artifact upload before metadata commit can be reconciled;
6. metadata commit before event acknowledgement does not duplicate accepted output;
7. expired leases can be reclaimed safely;
8. an invalid quality gate does not unlock downstream work;
9. invalidating one scene does not invalidate unrelated scenes;
10. a disallowed paid fallback is never called.

### 5.4 Media acceptance

The fast plan uses two media sizes so iteration is quick without ignoring the product requirement:

- **smoke render:** 60–120 seconds for rapid contract, timing, repair, and visual debugging;
- **duration-scale render:** at least 600 seconds (10 minutes) using the same composition/render contracts before the fast plan is declared complete. It may use a deterministic fixture topic/scene set, but it must exercise the real target duration, memory behavior, audio continuity, and final technical checks.

The media checks must verify at minimum:

- output decodes fully;
- expected resolution, aspect ratio, frame rate, and duration are present;
- audio exists, decodes, and has expected sample rate/channel layout;
- no unexpected black/frozen frames are present in tested regions;
- no required scene or layer is missing;
- narration and scene timing are within policy;
- captions/subtitles, if included, fit timing and safe-area constraints;
- the vertical short has a valid independent composition and does not merely rely on landscape dimensions.
- the duration-scale landscape output satisfies the channel profile's minimum long-form duration.

## 6. Implementation phases

### Phase 0 — Repository and toolchain bootstrap

**Goal:** Establish a reproducible project shell without adding speculative infrastructure.

Implement:

- `pyproject.toml` with supported Python version and test/lint/type commands;
- `src/pipeline/` package layout;
- `packages/renderer/` or equivalent TypeScript/Remotion package;
- `tests/` and `fixtures/` directories;
- `.env.example` with names only, never credentials;
- CLI entry point;
- README with exact local setup and checks;
- FFmpeg/ffprobe and Node/Remotion prerequisite checks;
- local infrastructure profile implementation notes and startup/readiness
  diagnostics.

Acceptance:

- a fresh environment can run unit tests and a contract smoke test;
- missing media tools produce a clear setup error;
- dispatch does not begin when repository, artifact, registry, or recovery
  preflight fails;
- no real provider call is made by default.

### Phase 1 — Contracts and local persistence

**Goal:** Make the durable vocabulary real before implementing content logic.

Implement only the initial contracts described in the contracts document:

- workflow/run;
- stage instance/attempt;
- job/lease;
- capability request/result;
- capability execution/context;
- routing decision;
- provider invocation/idempotency/budget reservation;
- artifact/dependency/invalidation;
- quality check/evaluation/gate result/repair plan;
- human review;
- event/outbox;
- episode/cut/scene/shot/layer composition references.

Implement:

- SQLite migrations or schema creation;
- repository interfaces;
- SQLite repository implementation;
- transaction helper;
- deterministic ID and fingerprint helpers;
- local artifact store with checksums and temporary workspaces.

Acceptance:

- contracts validate valid and invalid fixtures;
- repository round-trips records;
- unique constraints protect logical work and idempotency;
- artifacts can be stored, retrieved, hashed, and linked.

### Phase 2 — Execution spine with fake providers

**Goal:** Prove workflow correctness before using external APIs.

Implement:

- workflow loader and graph validator;
- readiness evaluator;
- stage-instance creation;
- job creation and idempotent keys;
- local outbox;
- polling dispatcher;
- worker claim/lease/release;
- stage registry;
- retry classifier and backoff calculation;
- recovery/reconciliation hooks;
- fake capability providers;
- structured event/log correlation.

The fake providers should be able to inject:

- success;
- validation failure;
- transient failure;
- permanent failure;
- timeout/unknown outcome;
- duplicate result;
- malformed structured output;
- delayed completion.

Acceptance:

- a synthetic workflow completes;
- fan-out and fan-in are tested for the selected validation graph;
- duplicate messages do not create duplicate accepted outputs;
- forced process termination tests pass.

### Phase 3 — Real content and audio slice

**Goal:** Produce a real narrated explainer with typed intermediate artifacts.

Implement:

- manual topic intake;
- software-engineering validation profile;
- source/evidence fixture or bounded configured-source ingestion;
- structured idea and script capability;
- claim/reference validation;
- scene-level visual plan;
- procedural or fixture asset generator;
- one TTS adapter and audio metadata extraction;
- speech strategy selection with a common speech manifest for continuous and
  scene-segmented outputs;
- ASR/transcript comparison using a local deterministic fixture or one configured ASR adapter; if live ASR is unavailable, the fixture must still exercise omission/substitution detection;
- audio QC.

Keep provider choice behind adapters. The first real provider can be configured manually; it is not a permanent routing decision.

Acceptance:

- the script contains stable scene IDs and claim/reference IDs;
- each scene has a voice artifact or explicit deterministic fixture;
- timing metadata is persisted;
- continuous and scene-segmented speech fixtures both resolve to the same
  scene-addressable timing contract;
- composition rejects a speech/visual plan with a mismatched script version,
  scene ID, or narration text hash;
- an intentionally omitted or changed phrase is caught by audio fidelity checks.

### Phase 4 — Composition, rendering, assembly, and one short

**Goal:** Validate the media boundary and derived-output model.

Implement:

- JSON composition schema shared by Python and TypeScript;
- renderer input manifest;
- Remotion composition for narration, visual layers, captions, and procedural overlays;
- preview render;
- final landscape render;
- render-chunk manifest and assembly;
- FFmpeg/ffprobe technical inspection;
- short-selection manifest;
- vertical composition with safe areas;
- one short render;
- render and assembly QC.

Acceptance:

- the composition can be rebuilt from immutable inputs;
- the long-form and short have distinct cut IDs and output profiles;
- one scene can be changed and only its descendants are rebuilt;
- output checks catch corrupted media and timeline defects.

### Phase 5 — Quality gate, repair, and human approval

**Goal:** Validate that quality is a control system rather than a final score.

Implement:

- deterministic check registry;
- quality-check plan resolution;
- one narrow semantic evaluator;
- gate aggregation with hard failures;
- repair planner;
- descendant invalidation;
- human-review record and CLI decision command;
- evaluation evidence and version persistence;
- initial gold examples and evaluator harness.

Acceptance:

- a hard technical defect cannot be averaged away;
- a narrow semantic failure triggers targeted repair;
- repeated failure reaches human review rather than infinite retry;
- reviewer approval is required before publish-ready state.

The initial quality implementation must also demonstrate the measurement
protocol in the Quality System document:

- deterministic validators run before semantic judges;
- every specialized metric records its input normalization, evaluator version,
  raw value, unit, threshold policy, and evidence references;
- speech uses normalized WER/CER, critical-token checks, forced alignment, and
  signal measurements before naturalness/prosody escalation;
- media uses full decode/profile/timeline checks before sampled perceptual or
  multimodal review;
- claim/evidence and narration/visual checks are narrow structured judgments,
  not one aggregate LLM score;
- a small verified gold set, a holdout set, and at least three controlled defect
  fixtures are evaluated without tuning thresholds on the holdout set;
- threshold records identify the evaluator, dataset, domain/channel scope,
  pass/review thresholds, false-pass target, confidence interval, blind spots,
  and recalibration trigger;
- critical semantic checks do not auto-pass until their false-pass target is
  supported by an untouched holdout set; insufficient evidence routes to human
  review instead of being treated as a pass;
- the report includes false-pass rate for critical defects, false-reject rate,
  abstention/escalation rate, repair-scope precision, latency, and cost per
  accepted artifact.

### Phase 6 — Validation report and extension decision

Produce a report containing:

- exact command/environment used;
- run manifest;
- artifact graph;
- output media metadata;
- quality results and known blind spots;
- fault-injection results;
- time per stage;
- provider usage/cost where available;
- regeneration scope and count;
- decision on which extension to implement next.

Do not proceed to PostgreSQL, external queues, or cloud workers merely because the code has interfaces for them. Use the report to identify the actual bottleneck.

## 7. Work packages for coding agents

Agents should take one work package at a time. Each package must preserve the contracts and acceptance tests of its dependencies.

### FV-01 — Bootstrap

**Own:** project manifest, package layout, CLI shell, test configuration.

**Must not:** add provider SDKs, cloud infrastructure, or application logic.

**Done when:** setup and contract smoke commands work in a clean environment.

### FV-02 — Core contracts

**Own:** Pydantic models, enums, schema export, fingerprints, ID helpers.

**Must not:** implement SQL repositories or provider calls.

**Done when:** valid/invalid fixture tests cover every required field and invariant.

### FV-03 — SQLite repository and ArtifactStore

**Own:** migrations/schema, repositories, local artifact implementation.

**Must not:** implement workflow scheduling.

**Done when:** transaction and artifact round-trip tests pass.

### FV-04 — Workflow/readiness engine

**Own:** definition loader, graph validation, readiness, cardinality needed by the validation graph.

**Must not:** select providers or execute stage business logic.

**Done when:** synthetic fan-out/fan-in readiness tests pass.

### FV-05 — Local outbox and worker

**Own:** events, outbox, dispatcher, claims, leases, retry/recovery behavior.

**Must not:** add an external broker.

**Done when:** crash and duplicate-delivery tests pass.

### FV-06 — Capability and fake-provider layer

**Own:** capability registry, fake implementations, normalized errors, usage records.

**Must not:** let stages import provider SDKs.

**Done when:** injected outcomes exercise every recovery branch.

### FV-07 — Content stages

**Own:** topic, idea, research fixture, script, visual plan, and their validators.

**Must not:** write workflow state directly outside execution result contracts.

**Done when:** typed artifacts and claim/reference checks are persisted.

### FV-08 — Speech and audio QC

**Own:** speech strategy selection, TTS/recording adapter, timing, ASR comparison, signal checks, audio artifacts.

**Must not:** assume one provider or hide timing corrections; silently splice
incompatible audio when repairing a continuous narration pass.

**Done when:** valid and intentionally defective audio fixtures are distinguished,
and both speech strategies produce the same normalized manifest/timing contract.

### FV-09 — Composition and rendering

**Own:** composition schema, Remotion bridge, FFmpeg commands/inspection, render-chunk manifest, assembly, long and short output profiles.

**Must not:** embed provider or workflow state logic in TypeScript components.

**Done when:** a reproducible long-form and short render passes technical checks.

### FV-10 — Quality and repair

**Own:** check registry, evaluator contracts, deterministic/specialized metric
adapters, narrow semantic evaluators, gate policy, repair/invalidation, review
state, and the initial gold-set harness.

**Must not:** silently mutate artifacts or bypass workflow recovery.

**Done when:** scene-level failure repairs only affected descendants, metric
outputs are reproducible from versioned inputs, and the evaluator harness
reports false-pass/false-reject and cost/latency results.

### FV-11 — Integration and validation report

**Own:** end-to-end fixture, fault injection, CLI inspection, report generation.

**Must not:** weaken tests to hide failures.

**Done when:** all fast-plan exit criteria are evidenced.

## 8. Fault-injection matrix

| Scenario | Expected result |
|---|---|
| Duplicate trigger | Same logical run key or explicit new run policy; no accidental duplicate |
| Crash before job claim | Job remains ready or is reclaimed |
| Crash after claim | Lease expiry makes job reclaimable |
| Provider succeeds, worker crashes before commit | Reconcile by idempotency/provider operation ID or mark `UNKNOWN` |
| Artifact upload succeeds, DB commit fails | Orphan is discoverable and safely reconciled/garbage-collected |
| DB commit succeeds, event ack fails | Redelivery becomes a no-op or reconciliation |
| Malformed structured output | Validation failure; bounded repair/fallback policy; no downstream readiness |
| Transient provider error | Bounded retry with backoff and same logical attempt policy |
| Quality failure | Targeted repair or human review; no silent pass |
| One scene fails | Only scene descendants are invalidated |
| Paid fallback disabled | No paid invocation; pause/defer/fail according to policy |
| Pending human review | Run remains durable and resumable for hours or days |
| Model/prompt version changes | Queued work uses captured effective configuration or is explicitly re-planned |

## 9. Recommended command surface

These commands are target interfaces for the fast slice; agents should implement only what the current phase needs.

```bash
python -m pipeline check-setup
python -m pipeline control migrate
python -m pipeline control reconcile --once
python -m pipeline workflow validate kb/docs/registries/fast_workflow.yaml
python -m pipeline run create --workflow explainer_validation_v1 --topic-file fixtures/topic.json
python -m pipeline run status --run-id RUN_ID
python -m pipeline run resume --run-id RUN_ID
python -m pipeline job dispatch --once
python -m pipeline worker run --once
python -m pipeline review list
python -m pipeline review decide --review-id REVIEW_ID --decision APPROVE
python -m pipeline artifact graph --run-id RUN_ID
python -m pipeline report --run-id RUN_ID --output reports/RUN_ID.md
```

The exact CLI framework is reversible. Stable behavior and exit codes matter more than the framework.

## 10. Exit checklist

- [ ] A clean setup command documents Python, Node, FFmpeg, and provider prerequisites.
- [ ] Contract tests pass without network access.
- [ ] Repository and artifact round trips pass.
- [ ] Synthetic recovery tests pass.
- [ ] One real structured content path succeeds.
- [ ] One real audio path succeeds.
- [ ] One landscape render succeeds.
- [ ] One vertical derived render succeeds.
- [ ] Deterministic QC blocks injected defects.
- [ ] Semantic QC returns versioned evidence.
- [ ] Human approval is durable.
- [ ] One scene is repaired surgically.
- [ ] Duplicate events and forced exits are safe.
- [ ] Cost/latency/quality evidence is recorded.
- [ ] Known gaps are listed in a validation report.

## 11. What happens after validation

Select the next extension from measured evidence:

- media/render bottleneck → worker isolation or burst compute;
- provider cost/quality bottleneck → benchmark and router expansion;
- reviewer bottleneck → review queue and UI;
- concurrency bottleneck → PostgreSQL/object storage and queue;
- weak factuality → research/evidence and evaluator improvements;
- weak shorts → short candidate selection/recomposition experiments;
- repeated content-stage uncertainty → bounded tool-using capability or agent experiment.

The fast plan is successful even if it says “do not add distributed infrastructure yet.”
