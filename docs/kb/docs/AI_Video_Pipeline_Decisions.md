# AI Video Automation Pipeline — Decision Log

This is the cross-cutting decision index. Component documents should link to decision IDs rather than silently introducing competing interpretations. A decision may be revised only when implementation evidence, a missing requirement, or a concrete contradiction justifies it.

## Decision status vocabulary

| Status | Meaning |
|---|---|
| `ACCEPTED` | Use this decision in implementation unless a newer decision supersedes it |
| `DEFERRED` | Direction is known, but implementation is intentionally postponed |
| `OPEN` | Needs a concrete choice before the affected implementation begins |
| `REJECTED` | Considered and deliberately not selected |
| `SUPERSEDED` | Replaced by a later decision; retain for history |

## ADR-001 — Modular monolith before service decomposition

**Status:** `ACCEPTED`

**Decision:** Keep one repository and one modular application initially. Use package and process boundaries without requiring one service per stage.

**Why:** The system has no implementation yet. Service boundaries would add network, authentication, deployment, versioning, and failure-handling costs before the workflow and media quality are proven.

**Consequence:** Every meaningful stage must still have a typed contract, bounded execution behavior, artifact references, and structured results so it can move later.

## ADR-002 — Domain profiles instead of domain-specific pipelines

**Status:** `ACCEPTED`

**Decision:** Finance, software engineering, mathematics/physics, and entertainment use one platform with `DomainProfile` and `ChannelProfile` policies.

**Why:** The workflow, artifact, composition, QC, recovery, and publishing infrastructure is shared. The main domain differences are evidence, risk, validators, rubrics, and enabled stages.

**Consequence:** Stage contracts must support optional capabilities and policy-driven gates. Domain assumptions must not be hidden in generic core code.

## ADR-003 — Long-form episode is canonical; shorts are derived cuts

**Status:** `ACCEPTED`

**Decision:** Produce a landscape long-form episode as the canonical editorial product. Generate vertical shorts from selected episode material and a short-specific composition plan.

**Why:** It supports the desired long-form and short-form volume while preserving source lineage and avoiding independent, contradictory content generation.

**Consequence:** The content model must represent `Episode`, `Cut`, scene/shot selection, vertical reframing, and separate short QC. A short is not merely a crop of an encoded landscape file.

## ADR-004 — Canonical content hierarchy

**Status:** `ACCEPTED`

**Decision:** Use `Episode → Cut → Sequence → Scene → Shot → LayerInstance → AssetInstance → SourceAsset → Artifact`. Treat frames as rendered/QC units, not ordinary workflow entities.

**Why:** Scenes are semantic narration units, shots are temporal visual units, and layers are actual composition elements. Per-frame orchestration would be too granular.

**Consequence:** The composition schema uses frame/time ranges, but artifact and repair boundaries normally stop at scene, shot, or layer.

## ADR-005 — Immutable artifact versions and graph invalidation

**Status:** `ACCEPTED`

**Decision:** Artifacts are immutable. A regenerated result creates a new artifact version, explicit dependency edges, and descendant invalidation records. Active accepted pointers are separate from historical artifact records.

**Why:** It makes reproduction, audit, caching, surgical repair, and rollback possible.

**Consequence:** No stage may overwrite a historical artifact path or silently reuse an invalidated descendant.

## ADR-006 — SQLite and local filesystem behind replaceable boundaries

**Status:** `ACCEPTED`

**Decision:** Use SQLite for the single-machine prototype and local filesystem storage behind `WorkflowRepository` and `ArtifactStore` interfaces.

**Why:** This is the smallest reliable local implementation. The interfaces preserve a migration path to PostgreSQL and object storage.

**Consequence:** SQLite must not be shared by remote workers over a network filesystem. Large bytes do not belong in relational rows.

## ADR-007 — Events notify; durable state decides

**Status:** `ACCEPTED`

**Decision:** Use a transactional outbox and at-least-once delivery. A worker must revalidate job eligibility against authoritative state before executing.

**Why:** Queue delivery can be duplicated, delayed, or lost around a process crash. State and idempotency provide correctness; events provide wake-up and distribution.

**Consequence:** Exactly-once execution is not a design assumption. Duplicate events must become safe no-ops or reconciled attempts.

## ADR-008 — Quality control is a parallel subsystem

**Status:** `ACCEPTED`

**Decision:** Quality checks, evaluations, gate policies, escalation, gold sets, and human review are a separate subsystem attached to artifact boundaries.

**Why:** Quality requires its own contracts, versioning, calibration, benchmarks, and data. It cannot be reduced to a final LLM score.

**Consequence:** Quality results are immutable evidence. The Workflow Engine applies the resulting gate decision and recovery policy.

## ADR-009 — Human approval before publication

**Status:** `ACCEPTED`

**Decision:** No video is published until the effective policy and a human approval record permit it.

**Why:** The initial domains include finance, science, and technical claims, and automated evaluators have unknown blind spots.

**Consequence:** Human review must be durable, resumable, and connected to exact artifact versions.

## ADR-010 — Provider adapters and benchmark-driven model selection

**Status:** `ACCEPTED`

**Decision:** Stages request capabilities, not vendors. Provider/model choices are made by adapters and a router, and are selected through quality/cost/latency benchmarking.

**Why:** Provider terms, models, quotas, prices, and quality change. Hard-coded model names would couple domain logic to unstable infrastructure.

**Consequence:** Provider names are configuration and routing data. The first router may have only one implementation per capability.

## ADR-011 — Faceless narrated explainer first

**Status:** `ACCEPTED`

**Decision:** The first real media path uses narration plus composed visuals, not presenter, avatar, or lip-sync production.

**Why:** It validates the core content, audio, visual, composition, rendering, QC, and short-derivation path without adding identity and lip-sync complexity.

**Consequence:** Presenter/hybrid modes are future composition and asset capabilities, not reasons to distort the initial core model.

## ADR-012 — Python-controlled LLM operations before agent frameworks

**Status:** `ACCEPTED`

**Decision:** Start with structured model calls and explicit Python loops. Introduce bounded tool-using agents or an agent framework only when a benchmarked capability needs dynamic tool choice or durable internal branching.

**Why:** Fixed production stages already have known ordering, contracts, retries, and gates. An autonomous supervisor would duplicate the Workflow Engine.

**Consequence:** Agents, when introduced, remain bounded capabilities and cannot own workflow state, budget, artifacts, or publication.

## ADR-013 — Quality tiers are policy, not model identity

**Status:** `ACCEPTED`

**Decision:** Refer to evaluator tiers as economical/small, strong/medium, and frontier/high-capability. Do not commit to specific vendors before benchmarking.

**Why:** A small model may outperform a larger one on a narrow task; vendor names and pricing change.

**Consequence:** Benchmark false acceptance, false rejection, defect recall, cost, latency, and escalation rate per capability.

## ADR-014 — Initial event-driven implementation is local

**Status:** `ACCEPTED`

**Decision:** The first event-driven implementation uses SQLite outbox rows and a polling dispatcher/local worker. No external broker is required.

**Why:** This validates event semantics, readiness, claiming, retries, and recovery without operating a distributed platform.

**Consequence:** The event envelope and outbox repository must be stable enough to map to a later queue.

## ADR-015 — Initial media defaults

**Status:** `DEFERRED`

**Decision:** Use these defaults unless a channel profile overrides them: landscape 1920×1080, 30 fps, 48 kHz stereo audio; vertical 1080×1920, 30 fps, 48 kHz stereo audio.

**Why deferred:** Exact frame rate, codec, loudness, and platform rules should be confirmed during the media benchmark.

**Consequence:** Time and media contracts must represent these values explicitly rather than hiding them in renderer code.

## ADR-016 — Initial validation topic

**Status:** `ACCEPTED`

**Decision:** Validate the platform with a domain-neutral engineering goal but use a software-engineering explainer as the concrete content fixture.

**Why:** A completely topic-free media test cannot exercise evidence, narration, visuals, or editorial decisions. Software engineering provides useful deterministic checks without making the first test a high-risk finance production.

**Consequence:** The fast plan must include a finance profile and finance-specific QC design, but does not need to publish finance content.

## ADR-017 — Documentation hierarchy

**Status:** `ACCEPTED`

**Decision:** Maintain one canonical parent architecture, focused component documents, two implementation plans, and one cross-cutting decision index. Preserve discussion history in a design discussion log.

**Why:** One giant architecture document becomes difficult to review, while unlinked component notes drift.

**Consequence:** Each focused document must identify its status, dependencies, decisions, initial implementation, extensions, and acceptance criteria.

## ADR-018 — Machine-readable registries are normative

**Status:** `ACCEPTED`

**Decision:** Keep canonical stage names, event names, failure codes, and fast
workflow/QC/recovery fixtures in versioned machine-readable registries under
`kb/docs/registries/`. Markdown documents explain the registries and may show
small excerpts, but must not create a second authoritative fixture.

**Why:** Prose-only contracts invite transcription drift and make it too easy
for coding agents to choose incompatible names or defaults.

**Consequence:** A registry change is a contract change. It must update affected
canonical documents, acceptance tests/fixtures, and migration notes together.

## ADR-019 — Assembly is a first-class stage

**Status:** `ACCEPTED`

**Decision:** `Rendering` produces immutable render chunks or complete render
outputs; `Assembly` is a separate fan-in stage that produces the complete cut or
master and owns cross-chunk continuity checks.

**Why:** Chunk completeness, ordering, A/V continuity, and surgical chunk repair
are durable boundaries that should not be hidden inside a renderer process.

**Consequence:** The fast workflow includes an `assembly` node and
`assembly_gate_v1`. A chunk repair invalidates assembly and its descendants,
not unrelated source or scene branches.

## ADR-020 — Explicit execution and acceptance state

**Status:** `ACCEPTED`

**Decision:** `StageInstance.execution_status` and
`StageInstance.acceptance_status` are separate durable fields. A successful
execution does not make downstream work eligible until required quality
acceptance passes.

**Why:** Execution success, automated quality acceptance, human approval, and
publication readiness answer different operational questions.

**Consequence:** Transport retries, quality regenerations, human review, and
publication approval use separate records and counters. They must not be
represented by one overloaded status field.

## ADR-021 — Canonical event taxonomy and failure namespaces

**Status:** `ACCEPTED`

**Decision:** New events use lowercase dot notation and are registered with a
role of `command`, `notification`, or `fact`. Failure codes use namespaced
values such as `MEDIA.DECODE_ERROR` and `QUALITY.UNSUPPORTED_CLAIM`.

**Why:** Earlier notes used PascalCase events and unnamespaced failure strings,
which made compatibility and recovery behavior ambiguous.

**Consequence:** Historical aliases may be accepted only at an explicit import
boundary and must be normalized immediately to registry values.

## ADR-022 — Configurable narration continuity strategy

**Status:** `ACCEPTED`

**Decision:** Speech generation supports two explicit strategies behind one
normalized contract: `CONTINUOUS` for one narration/recording pass with
scene boundaries derived by alignment, and `SCENE_SEGMENTED` for one accepted
speech artifact per script scene followed by manifest assembly. The effective
configuration selects the strategy for a run; neither strategy is the only
architectural form.

**Why:** Continuous generation can preserve voice, prosody, pronunciation
context, and transitions more naturally. Scene-segmented generation provides
surgical retry and repair boundaries. The pipeline needs both trade-offs while
keeping synchronization independent from the provider's artifact shape.

**Consequence:** The immutable script scene manifest remains authoritative for
scene identity, order, narration text, and boundaries. Both strategies record
script/version identity, narration text hashes, voice or recording
configuration, audio artifacts, and alignment evidence in the same speech
manifest contract. Composition is the synchronization boundary and derives
final frame ranges from actual aligned audio. A continuous-pass repair must
either regenerate the affected continuous pass or perform an explicit,
continuity-checked switch to scene-segmented replacement; incompatible audio
must not be silently spliced.

## ADR-023 — Artifact-specific layered quality measurement

**Status:** `ACCEPTED`

**Decision:** Quality is measured per artifact type and domain profile using a
layered evaluator plan: deterministic integrity checks first, specialized
signal/measurement models next, narrow semantic judges after that, and human
review for high-risk or unresolved cases. The system must not reduce all
dimensions to one universal quality score.

**Why:** Different artifacts fail in different ways. A media decode failure is
not equivalent to weak pacing; a low WER is not proof of natural prosody; an
image-text similarity score is not proof of factual or rights correctness; and
a strong LLM score can still miss a deterministic contradiction. Existing
benchmarks provide useful components, but claim support, narration/visual
faithfulness, domain correctness, and repair scope require a pipeline-specific
gold set.

**Consequence:** Every evaluator records exact input hashes, preprocessing,
evaluator/model/rubric versions, raw values and units, thresholds, evidence,
confidence, abstention, outcome, repair scope, latency, and cost. The fast
slice implements deterministic checks, selected specialized measurements, and
narrow semantic evaluators first. Thresholds are calibrated on development and
holdout sets against verified labels, with critical-defect false-pass rate as a
primary safety metric. A threshold is a versioned operating point with explicit
pass/review zones, uncertainty, dataset scope, cost targets, and recalibration
triggers; insufficient evidence results in escalation rather than an automatic
pass.

## ADR-024 — Local infrastructure profile before remote promotion

**Status:** `ACCEPTED`

**Decision:** The fast validation runs on a single machine using one
authoritative local SQLite repository, a local filesystem `ArtifactStore`, a
transactional outbox, polling delivery, claimable jobs, leases with fencing,
and bounded local workers. The default runtime is one process with explicit
control-plane and execution-plane boundaries; separate local roles or one
container image are optional test/packaging modes, not prerequisites.

Startup must pass a fail-closed readiness barrier and a recovery scan before new
outbox delivery or job claims begin. Runtime readiness does not replace durable
workflow readiness: SQLite state, artifact hashes, quality gates, and recovery
records remain authoritative.

Remote promotion is evidence-gated and follows this default order: optional
local image with role commands, object-storage adapter and migration rehearsal,
authoritative PostgreSQL or justified equivalent, one remote CPU worker, one
bounded GPU/media worker when justified, and a queue only when polling is a
measured bottleneck. Backpressure, resource pools, and further service
separation follow observed workload evidence.

**Why:** This proves correctness, recoverability, artifact identity, and media
behavior before adding distributed failure modes. Remote workers need stable
opaque artifact references and durable multi-machine metadata. A queue changes
delivery but must not become workflow truth, so it should not be introduced
before its operational value is measured.

**Consequence:** The local infrastructure profile is canonical for the first
implementation. It defines startup checks, local workspace ownership, artifact
publication/orphan handling, process roles, version capture, fault injection,
and promotion criteria. The deferred target details are captured in the
[Remote Infrastructure Expansion](AI_Video_Pipeline_Remote_Infrastructure_Expansion.md)
document. Cloud providers, queue vendors, database hosting, container
orchestration, and exact resource placement remain deferred.

## Deferred decisions

The following are intentionally not selected yet:

- PostgreSQL provider and hosting location;
- object storage provider;
- queue/event broker;
- cloud/GPU execution provider;
- exact LLM/TTS/ASR/image/video providers;
- Remotion renderer version and final media codec profile;
- review UI framework;
- automatic publication scope;
- exact concurrency for the target weekly volume;
- whether a durable workflow engine such as Temporal is eventually justified;
- whether a bounded agent framework is needed for research or revision.

These decisions should be made through benchmarks and operational requirements, not architecture fashion.
