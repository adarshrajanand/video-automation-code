# AI Video Automation Pipeline — Design Discussion Log

**Status:** Historical rationale; normative decisions live in [the Decision Log](AI_Video_Pipeline_Decisions.md)

This document records how the current architecture and implementation plan were reached. It is intentionally more conversational than the decision log. The decision log records the normative result; this log preserves the questions, alternatives, reasoning, and unresolved assumptions that led there.

## 1. Purpose

Use this log to answer:

- Why was a decision made?
- Which user requirement caused it?
- What alternatives were considered?
- Which ideas were deliberately deferred rather than rejected?
- What questions still need evidence or a future decision?

When an implementation changes a decision, add a dated entry here and update the corresponding ADR.

## 2. Starting repository state

At the beginning of the discussion, the repository contained no application implementation, package manifest, tests, or agent instructions. It contained architecture notes under `kb/docs/`, including:

- long-term architecture;
- first-class contracts;
- infrastructure blueprint;
- event-driven execution and routing addendum;
- batch execution and deployment follow-up;
- agent integration discussion;
- quality-control discussion.

The system was therefore treated as a design-to-implementation effort, not a refactor of an existing codebase.

## 3. Initial architectural questions

### Question: Should the whole system be an autonomous agent?

**Conclusion:** No. The production workflow has fixed stages, durable state, retry policy, quality gates, and publication controls. The Workflow Engine owns transitions. LLMs and agents may operate inside bounded capabilities, but may not silently own workflow state, budgets, artifacts, or publication.

### Question: Should every stage be a separate process or service?

**Conclusion:** No. Independent execution comes from contracts, persisted jobs, artifact references, leases, and idempotency. A modular monolith is the first implementation. Processes/services are introduced when resource, scale, isolation, or deployment evidence requires them.

### Question: Are LangChain, LangGraph, CrewAI, Strands, or similar frameworks required?

**Conclusion:** No initial framework requirement. Start with structured model calls and Python-controlled loops. Consider a bounded framework only when a capability genuinely needs dynamic tool choice, complex internal branching, or durable internal state.

### Question: Does topic discovery need an autonomous research agent?

**Conclusion:** Not initially. If sources are configured, ordinary ingestion plus structured extraction, deduplication, ranking, and QC is enough. Adaptive research is a later capability if evidence shows fixed-source monitoring is insufficient.

### Question: Should idea generation, script planning, visual planning, and semantic quality all be agents?

**Conclusion:** No. These can initially be structured LLM operations inside deterministic Python loops. A model call is not automatically an agent. The workflow and quality contracts remain the same if a bounded agent replaces one implementation later.

## 4. Product clarification from the user

The target product was clarified as:

- initial niches: finance, computer science/software engineering, mathematics, and physics;
- audience: adults;
- initial language: US English, with localization later;
- canonical format: landscape long form;
- duration: 10 minutes or more for long form;
- derived outputs: shorts extracted from long form;
- platforms: YouTube, Instagram, and major short/long-form platforms;
- publication: human approval before publication;
- target volume: three long-form videos per week and two or more shorts per day;
- provider policy: benchmark quality first, including self-hosted local/cloud open models and hosted providers;
- assets: mixture of generated, licensed stock, public-domain, procedural, and code-created assets.

## 5. Architecture questions resolved during discussion

### Question: Will finance, software engineering, mathematics/physics, and entertainment require separate systems?

**Conclusion:** No separate platform. Use domain and channel profiles for source policy, claim policy, evaluator rubrics, thresholds, enabled stages, and human review. The shared core remains workflow, artifacts, composition, quality, recovery, and publishing.

### Question: Is the long-form video the source for shorts?

**Conclusion:** Yes. The landscape long-form episode is the canonical editorial product. Shorts are derived cuts with their own selection, vertical composition, rendering, QC, and publishing metadata. They are not merely a blind crop of the final landscape file.

### Question: Is the v5 stage list still the right top-level structure?

**Conclusion:** Yes, with one canonical vocabulary and substages. The major stages are Topic Discovery, Idea Development, Research, Script Generation, Visual Planning, Asset Acquisition, Speech Generation, Composition, Rendering, Short Derivatives, Human Review, and Publishing. A substage becomes a first-class workflow node only when it has a meaningful artifact, retry, quality, resource, fan-out/fan-in, or repair boundary.

### Question: Are frames the right smallest unit?

**Conclusion:** Frames are too low-level for ordinary workflow orchestration. Use `Episode → Cut → Sequence → Scene → Shot → LayerInstance → AssetInstance → SourceAsset → Artifact`. Frames are render outputs and QC sampling units. Scene and shot are the initial useful repair boundaries.

### Question: Should quality control be a final stage?

**Conclusion:** No. Quality is a parallel subsystem attached to stage outputs. It uses deterministic checks first, specialized measurements next, narrow semantic judges when needed, stronger adjudication for difficult cases, and durable human review for unresolved or high-risk cases.

### Question: Should the full end-state infrastructure be implemented now?

**Conclusion:** No. Document the end-state architecture and its extension points, but implement only the minimum reliable vertical slice. Preserve one-way-door decisions—contracts, artifact identity, provenance, time model, idempotency, quality evidence, and repository boundaries—while deferring queues, cloud workers, service decomposition, and advanced routing.

## 6. Decisions requested and answers received

| Question | Answer | Resulting decision |
|---|---|---|
| First validation domain? | Domain-neutral platform validation, using software engineering as a concrete fixture; finance remains commercially important | ADR-016 |
| Initial visual mode? | Faceless narrated explainer | ADR-011 |
| Publication policy? | Human approval required | ADR-009 |
| Documentation commit scope? | Include all existing and new Markdown in the replacement documentation commit | Documentation migration plan |
| Should discussion be tracked? | Yes, in a plan/design log and decision record | ADR-017 and this file |

## 7. Questions intentionally left open

These questions are not forgotten; they require benchmark or operational evidence:

1. Which model/provider is best for each generation and evaluation capability?
2. Which open-weight models fit the laptop and future cloud GPU budgets?
3. What exact source classes are allowed for finance and current affairs?
4. What reviewer workload is sustainable at three episodes per week?
5. What concurrency is required to meet the volume target?
6. Which render profile is most reliable and economical?
7. Which queue and database are justified once remote workers are needed?
8. Does research ever need adaptive tool-using agents?
9. Which short-selection heuristics correlate with human acceptance and retention?
10. When do presenter or hybrid formats justify new capabilities?

## 8. Change protocol

When changing a design:

1. identify the affected ADR and component documents;
2. record the reason and evidence here;
3. update the parent architecture if vocabulary or boundaries change;
4. update the fast or end-to-end plan if implementation order changes;
5. add a migration note if existing artifacts, contracts, or state are affected;
6. do not silently update one component document in isolation.

## 9. Current implementation posture

The repository is documentation-first. The next implementation should be a local vertical slice, not a cloud platform. Every agent task should point to the canonical parent and relevant component document, identify the exact owned files, and include tests and acceptance criteria.

## 10. Documentation review follow-up

After the first draft of the canonical documents was prepared, an independent review checked whether coding agents could implement the contracts without inventing missing state. That review identified several issues and the documents were tightened before the replacement commit:

- execution success and quality acceptance were separated into execution/acceptance state;
- aggregate `QualityGateResult` was added instead of treating individual evaluations as the gate;
- idempotency, budget reservation, input-manifest, retry/recovery, capability-execution, profile, and media contracts were made explicit;
- artifact slots were scoped to a run/content package and active pointers were made atomic;
- the canonical asset relationship was standardized as `LayerInstance → AssetInstance → SourceAsset → Artifact`;
- the fast workflow was changed to include schema versions, implementation versions, cardinality, gate IDs, recovery policy IDs, and a stage/policy registry;
- quality-accepted, human-approved, and publication-ready were defined as different states;
- outbox claims gained claimant/expiry recovery semantics;
- render profile identity was bound to composition identity;
- the fast plan gained a deterministic ASR fixture fallback and a ten-minute duration-scale render checkpoint;
- profile merge and non-overridable policy semantics were documented;
- the generic capability protocol was made the single integration boundary for structured calls and future agents.

The documentation reconciliation then made four additional implementation
decisions:

- canonical stage, event, failure-code, workflow, quality, and recovery
  registries are machine-readable under `kb/docs/registries/` (ADR-018);
- rendering and assembly are separate durable boundaries because chunk fan-in
  and continuity are independently recoverable (ADR-019);
- execution status, quality acceptance, human approval, and publication
  readiness are separate state concepts and fields (ADR-020);
- new events use lowercase dot notation and failure codes use namespaces
  (ADR-021).

These changes preserve the incremental implementation strategy. They add contracts and invariants that are painful to retrofit, but they do not require PostgreSQL, an external queue, cloud workers, or an agent framework in the first slice.

## 11. Narration continuity strategy review — 2026-10-21

The review raised a synchronization and voice-consistency concern about keeping
visual planning and speech generation parallel, especially because independent
scene-level TTS can introduce differences in prosody, pronunciation, pauses,
or voice continuity. The review also recognized that one continuous pass makes
surgical scene repair and recovery harder.

The accepted resolution is ADR-022: make narration continuity a configurable
speech strategy rather than choosing one artifact shape permanently. A
`CONTINUOUS` pass preserves whole-narration continuity and derives scene timing
from ASR/forced alignment. A `SCENE_SEGMENTED` pass preserves scene-level
repairability and assembles an audio manifest after checks. Both paths consume
the same immutable script scene manifest and emit the same scene-addressable
speech/timing contract.

Composition remains the synchronization boundary. It verifies script/version,
scene IDs, and narration text hashes across the visual and speech branches,
then derives final frame ranges from actual aligned audio. A repair may not
silently splice incompatible audio from different continuity strategies.

## 12. Quality measurement framework review — 2026-10-21

The quality review expanded the existing layered quality design into an
artifact-specific measurement framework. The accepted resolution is ADR-023:
run deterministic integrity and policy checks first, specialized signal or
measurement models second, narrow semantic judges third, and human review for
high-risk or unresolved cases.

The framework explicitly separates:

- technical/integrity quality;
- parent/child and provenance correctness;
- domain-semantic correctness;
- perceptual quality;
- policy and publication readiness.

Existing metrics such as WER/CER, forced alignment, VMAF, LPIPS, CLIPScore,
DNSMOS, VoiceMOS, and VBench are treated as versioned measurement components,
not universal acceptance scores. The pipeline will create its own verified gold
set with controlled defects, domain slices, holdout examples, human labels,
repair actions, and cost/latency measurements. Critical-defect false-pass rate
is the primary safety metric; cost per accepted artifact is the primary
efficiency metric.

The fast slice will implement a small set of deterministic and specialized
measurements plus narrow claim/evidence and narration/visual semantic judges.
It will not add a large judge matrix before the evaluator harness can measure
false passes, false rejects, abstentions, repair precision, and evaluator cost.

Thresholds are operating points, not universal properties of metrics. They will
be selected on development data using risk/cost targets, frozen, and evaluated
on an untouched holdout set. Critical semantic checks will not auto-pass when
the holdout is too small to support the declared false-pass bound; they will
escalate to human review instead.

## 13. Local infrastructure profile review — 2026-10-21

The infrastructure discussion now moves from end-state options to the first
operational baseline. The accepted resolution is ADR-024: the fast slice uses a
single-machine modular monolith with SQLite, a local filesystem `ArtifactStore`,
transactional outbox polling, durable jobs, leases with fencing, and bounded
workers. The default runtime is one process; local role separation or one
container image is optional for crash/isolation testing and packaging.

The local profile adds a fail-closed startup barrier. It validates registries,
workflow/profile configuration, database migrations, artifact/temp-store
read/write behavior, required media tools, safe capability configuration, and
runtime limits. It then reconciles stale outbox claims, expired leases, unknown
provider outcomes, and orphaned artifact bytes before enabling dispatch. Process
presence and container startup ordering are not treated as workflow truth.

The discussion also resolved the remote promotion-order conflict between the
workflow document and the end-to-end plan. The default sequence is: optional
local image, object-storage adapter and migration rehearsal, authoritative
PostgreSQL or justified equivalent, one remote CPU worker, one bounded GPU/media
worker when justified, and a queue only if polling is a measured bottleneck.
Backpressure and independent worker pools follow measured need. This keeps
opaque artifact access and authoritative state stable before remote execution,
and avoids introducing a queue merely because it is available.

No cloud, queue, database host, GPU vendor, or model provider was selected. Any
different migration order requires an accepted ADR and an explicit migration
note. To keep current implementation guidance separate from future target
guidance, the detailed deferred design is captured in the [Remote Infrastructure
Expansion](AI_Video_Pipeline_Remote_Infrastructure_Expansion.md) document. It
defines stable boundaries, migration evidence, security, backup, and rollback
requirements without selecting a deployment vendor.

## 14. Version-control sequence

The requested documentation migration has two commits:

1. commit the two original discussion TXT files as source notes;
2. create the canonical/focused Markdown documents, stage all existing Markdown, remove the TXT files, and commit the replacement knowledge base.

The first commit has been made before the second documentation commit. This preserves the original discussion exactly in Git history while making the working documentation easier to navigate.

Plan mode is read-only in this coding environment. It was used to inspect and discuss the architecture, but no commit could be created until build mode was restored. This is an execution-mode restriction, not an architectural decision.
