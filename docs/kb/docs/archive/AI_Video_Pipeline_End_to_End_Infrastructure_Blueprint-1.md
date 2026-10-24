# AI Video Automation Pipeline --- End-to-End Infrastructure Blueprint

**Document type:** HISTORICAL / NON-NORMATIVE follow-up to the AI Video Pipeline architecture documents
**Scope:** End-state infrastructure, deployable services, internal
packages and APIs, external integrations, technologies, and deployment
evolution.

> This blueprint is a supporting note, not an implementation checklist. Use
> [the documentation guide](../README.md), the canonical architecture, contracts,
> workflow, quality, and routing documents for current terms and decisions.

## 1. Purpose

This document describes what the AI video automation system is intended
to look like when mature. It is a target blueprint, not a checklist to
implement all at once.

The system should be able to generate videos, evaluate quality, repair
failures, select appropriate model/provider implementations, execute
work in suitable environments, preserve artifact lineage, and eventually
publish accepted outputs.

**Core deployment principle:** keep a monorepo and modular packages
initially. Split components into independently deployed services only
when workload, reliability, or scaling requirements justify it.

## 2. End-State Logical Architecture

``` mermaid
flowchart TD
    T["CLI / Scheduler / Review UI / API"] --> C["Control Plane"]
    C --> W["Workflow Engine"]
    W <--> DB[("Workflow Database")]
    W --> O["Transactional Outbox"]
    O --> D["Outbox Dispatcher"]
    D --> Q["Queue / Event Bus"]
    Q --> WK["Independent Workers"]

    WK --> CR["Capability Router"]
    CR --> PA["Provider Adapters"]
    PA --> EXT["Hosted APIs / Local Models"]

    WK --> RB["Resource Broker"]
    RB -. "Execution placement" .-> WK

    WK --> AS["ArtifactStore"]
    AS --> OBJ[("Local Files / Object Storage")]
    WK --> QC["Quality Evaluation"]
    QC --> G{"Quality Gate"}
    G -->|Pass| W
    G -->|Regenerate| RP["Targeted Repair"]
    RP --> W
    G -->|Human review| H["Review Queue / UI"]
    H --> W

    W --> PUB["Publishing"]
    PUB --> PLAT["YouTube / Other Platforms"]
    WK --> OBS["Logs / Metrics / Traces"]
```

This is a logical diagram. These boxes do not all need to be separate
services. At first, most can be modules inside one Python process.

## 3. Recommended Technology Stack

These are concrete recommendations, not permanent requirements. Recheck
supported versions, provider terms, quotas, and pricing before
deployment.

  --------------------------------------------------------------------------
  Layer                   Recommended technology     Responsibility
  ----------------------- -------------------------- -----------------------
  Main application        Python, using a currently  Workflow logic, stages,
                          supported release          evaluation, routing and
                                                     workers

  Video composition       TypeScript + Remotion      Programmatic video
                                                     composition, animation
                                                     and reusable scene
                                                     templates

  Media processing        FFmpeg + ffprobe           Audio/video conversion,
                                                     encoding, metadata
                                                     inspection and
                                                     technical validation

  Contracts               Pydantic + JSON Schema     Typed inputs/outputs,
                                                     validation, versioned
                                                     event payloads and
                                                     structured model
                                                     responses

  Workflow configuration  YAML + schema validation   Stage graph,
                                                     dependencies, retry
                                                     limits, quality gates
                                                     and policies

  Local state             SQLite                     Initial workflow state,
                                                     execution history,
                                                     artifact metadata,
                                                     evaluations and outbox

  Shared durable state    PostgreSQL                 Authoritative state
                                                     when workers run across
                                                     machines

  Artifact storage        Local filesystem           Scripts, source
                          initially; S3-compatible   material, audio,
                          object storage later       images, clips, renders
                                                     and final videos

  Control API             FastAPI, when an API is    Start runs, inspect
                          needed                     state, request repair
                                                     and integrate the UI

  Review interface        React + TypeScript, or a   Inspect outputs and
                          lightweight initial UI     evidence; approve,
                                                     reject or request
                                                     repair

  Scheduling              CLI initially;             Manual and scheduled
                          cron/systemd timer for     execution
                           scheduled runs

  Event delivery          SQLite-backed outbox       Reliable notification
                          initially; queue/broker    of ready work
                           later

  Testing                 pytest +                   Validate contracts,
                          contract/integration tests routing, QC, recovery
                                                     and provider errors

  CI                      GitHub Actions             Tests, linting,
                                                     packaging and build
                                                     checks

  Observability           Structured JSON logs       Explain failures,
                          initially;                 latency, costs, retries
                          OpenTelemetry-compatible   and routing decisions
                           metrics/traces later

  Packaging               Docker image with distinct Reuse the same codebase
                          commands                   for control-plane,
                                                     dispatcher and worker
                                                     processes
  --------------------------------------------------------------------------

**Database and artifact rule:** SQLite is appropriate for the initial
local runner, but should not be used as a shared database for
distributed workers or placed on a network filesystem. Move
authoritative workflow state to PostgreSQL when multiple machines need
to update it. Store large binary artifacts separately behind an
`ArtifactStore` interface.

## 4. Monorepo Package Boundaries

These are logical modules, not a requirement to create a separate Python
distribution for each one. Keep modules together until there is a
practical reason to split them.

### 4.1 Workflow and execution

-   `workflow_definition` --- parses and validates workflow YAML.
-   `workflow_engine` --- manages stage state transitions, dependencies
    and fan-out/fan-in.
-   `readiness_evaluator` --- determines whether a stage has all
    required inputs and may run.
-   `execution_runtime` --- claims work and manages leases, retries and
    idempotency.
-   `event_outbox` --- records event intent and dispatches pending
    events.
-   `scheduler` --- initiates scheduled or manually requested runs.

### 4.2 Capabilities, providers and policy

-   `capability_contracts` --- provider-neutral requests and results for
    text generation, TTS, ASR, image generation, video generation and
    evaluation.
-   `capability_router` --- selects an eligible implementation using
    hard constraints, quality evidence, availability, quota, cost and
    latency.
-   `provider_registry` --- declares available providers, models,
    supported capabilities and relevant limits.
-   `provider_adapters` --- translates internal requests to external
    APIs or local model implementations.
-   `resource_broker` --- eventually chooses the execution environment
    independently of model/provider selection.
-   `budget_policy` --- enforces spend limits and controls paid
    fallbacks.

### 4.3 Production stages

-   `topic_discovery` --- optional scanning of configured sources and
    candidate generation.
-   `idea_selection` --- evaluates and selects candidate ideas.
-   `research` --- gathers evidence and preserves source references.
-   `script_generation` --- creates narration and claims.
-   `visual_planning` --- maps narration to scenes and visual
    treatments.
-   `asset_generation` --- sources or generates images, clips and other
    assets.
-   `speech_generation` --- creates narration and timing metadata.
-   `composition` --- produces the Remotion scene specification.
-   `rendering` --- renders and assembles video outputs.
-   `publishing` --- packages and publishes accepted outputs.

### 4.4 Quality and artifacts

-   `quality_engine` --- applies gate policies and combines evaluator
    results.
-   `deterministic_checks` --- validates schemas, required sources,
    media integrity, duration and platform constraints.
-   `specialized_evaluators` --- runs measurable checks such as
    speech/text comparison and visual relevance.
-   `semantic_judges` --- evaluates meaning, clarity, coherence, claims
    and audience fit.
-   `repair_planner` --- turns a failed gate into a targeted repair
    request.
-   `artifact_store` --- abstracts local files and remote object
    storage.
-   `artifact_lineage` --- records immutable artifact versions and
    dependency relationships.
-   `persistence` --- stores workflow state, execution attempts, routing
    decisions, costs and evaluation evidence.

## 5. Internal APIs and Contracts

Prefer a small number of stable interfaces. Stage business logic should
depend on these interfaces rather than vendor SDKs or
deployment-specific details.

  ------------------------------------------------------------------------------------
  Interface                                        Responsibility
  ------------------------------------------------ -----------------------------------
  `Stage.run(input, context)`                      Execute one bounded stage using
                                                   declared inputs

  `Capability.execute(request)`                    Request a capability without naming
                                                   a vendor in stage logic

  `ArtifactStore.put/get(uri)`                     Store and retrieve artifacts
                                                   without assuming local disk or
                                                   cloud

  `WorkflowRepository`                             Read and update authoritative
                                                   workflow and stage state

  `QualityEvaluator.evaluate(artifact, context)`   Return a decision, evidence and
                                                   evaluator version

  `EventPublisher.publish(event)`                  Deliver a versioned event through
                                                   the outbox-backed mechanism

  `ResourceBroker.assign(job)`                     Choose an eligible execution
                                                   environment

  `ReviewQueue.submit(item)`                       Pause for human review and resume
                                                   after a decision
  ------------------------------------------------------------------------------------

Every independently executable stage should have a versioned
input/output contract, use artifact references rather than sending large
binaries in events, and record meaningful execution results.

A stage should not: - call provider SDKs directly; - make arbitrary
workflow state transitions; - silently accept failed quality gates; -
overwrite historical artifacts; - assume that a delivered event
guarantees the job is still eligible.

## 6. External APIs and Integrations

Keep external integrations behind adapters. The exact provider and model
should be chosen through benchmarking, policy and configuration.

  -----------------------------------------------------------------------
  Capability              Integration category    Typical uses
  ----------------------- ----------------------- -----------------------
  Text generation and     Hosted LLM APIs;        Idea selection,
  structured extraction   optionally an API       research synthesis,
                          aggregator such as      scripts and scene plans
                          OmniRoute

  Semantic evaluation     Hosted LLM APIs,        Claims, clarity,
                          potentially using       relevance, coherence
                          different model tiers   and final review

  Text-to-speech          TTS API or tested local Narration, voice
                          model                   consistency and
                                                  pronunciation

  Speech recognition      ASR API or local model  Compare narration with
                                                  the approved script

  Image/video generation  Image and video         Scene assets,
                          generation APIs         backgrounds and short
                                                  clips

  Stock media             Licensed stock-media    Visual assets with
                          APIs or curated local   provenance and usage
                          assets                  restrictions

  Rendering               Remotion + FFmpeg       Composition, encoding
                                                  and media validation

  Publishing              YouTube Data API        Upload, metadata,
                          initially; other        scheduling and
                          platform APIs as needed publication status
  -----------------------------------------------------------------------

Do not hard-code one model per stage. The capability router should
select only implementations that meet quality, privacy/data-handling,
availability and budget constraints. If a quota is exhausted, the system
should pause or select another eligible implementation; it must not
silently switch to a paid provider.

## 7. End-State Deployable Roles

These are potential deployment boundaries. They should become separate
processes or services only when there is a concrete reason.

  -----------------------------------------------------------------------
  Deployable role                     Responsibilities
  ----------------------------------- -----------------------------------
  Control plane                       API, workflow state transitions,
                                      dependency readiness, scheduling
                                      and budget policy

  Dispatcher                          Reads the transactional outbox and
                                      delivers work notifications

  General workers                     Research, text generation, metadata
                                      and other lightweight tasks

  Media workers                       TTS, asset processing, rendering
                                      and assembly; potentially separate
                                      CPU/GPU profiles

  Evaluator workers                   Deterministic checks, specialized
                                      evaluators and semantic judges

  Review interface                    Human approvals, evidence
                                      inspection, repair decisions and
                                      run status
  -----------------------------------------------------------------------

Initially, a single Docker image can expose separate commands for the
runner, dispatcher and worker. The same worker package should be
deployable locally or remotely without rewriting stage business logic.

## 8. Compute and Deployment Options

### 8.1 Laptop

Use the existing Ryzen 7 5800H, 16 GB RAM and RTX 3060 6 GB laptop for
development, deterministic tests, debugging, local media processing and
limited local-model experiments. Do not assume every model or rendering
workload will fit or run efficiently.

### 8.2 Persistent low-cost control plane

An eligible Oracle Cloud instance is one candidate for lightweight
persistent services. Cloudflare Workers + D1 could serve some
lightweight ingress or scheduling needs, but avoid introducing both
platforms without a specific requirement. Availability and free-tier
terms must be verified.

### 8.3 On-demand compute

Modal or rented GPUs such as those available through Vast.ai are
candidates for bounded GPU-heavy jobs when measurements justify the
expense. Kaggle and Colab are suitable for bounded experiments, not as
durable production control planes.

### 8.4 Durable storage

When remote workers are needed, use PostgreSQL for authoritative
workflow state and object storage for large artifacts. Do not make
remote workers depend on a shared local directory or a network-mounted
SQLite database.

## 9. End-to-End Execution

1.  **Trigger:** a CLI, scheduler or API creates a workflow run and
    stores its configuration and initial state.
2.  **Discover and plan:** optional topic discovery, idea selection,
    research, script generation and visual planning create versioned
    artifacts.
3.  **Fan out work:** narration and visual asset jobs can run
    independently. The readiness evaluator waits for all declared inputs
    before downstream composition.
4.  **Route and execute:** a stage requests a capability; the capability
    router selects an eligible implementation. Eventually, the resource
    broker chooses where the job executes.
5.  **Evaluate:** deterministic checks and specialized measurements run
    first; semantic judges or human review are used where needed.
6.  **Repair or accept:** failed gates request targeted repair, preserve
    prior artifacts and reevaluate changed outputs. Accepted work
    proceeds.
7.  **Render and publish:** Remotion and FFmpeg produce and validate the
    video. Publishing occurs only after required gates and approvals.
8.  **Measure:** persist costs, latency, failures, evaluation decisions,
    regeneration outcomes and content performance for later analysis.

### Events and durability

Events notify workers that work may be ready; durable database state
remains authoritative. A worker must validate job eligibility before
executing.

Use a transactional outbox so that a committed state transition and the
intent to publish its event are recorded atomically. Expect
at-least-once delivery, not exactly-once execution. Idempotency and
deduplication should make repeated delivery harmless.

Events should carry IDs and references to artifacts, not large binary
payloads. Store meaningful stage transitions, input/output artifact IDs,
evaluation decisions, routing decisions, costs, retries, review
decisions and outbox status in durable state.

## 10. Implementation Evolution

The target architecture should be approached incrementally.

  -----------------------------------------------------------------------
  Milestone                           Deliverable
  ----------------------------------- -----------------------------------
  1\. Local vertical slice            One complete video generated using
                                      a local workflow runner

  2\. Quality and repair              A meaningful QC gate,
                                      evidence-backed decisions and
                                      targeted regeneration

  3\. Recovery                        Resumable runs, idempotency,
                                      immutable artifact lineage and
                                      bounded retries

  4\. Event-driven execution          Outbox, dispatcher and
                                      independently claimable worker jobs

  5\. Remote durability               PostgreSQL and object storage when
                                      remote workers are required

  6\. Independent scaling             Separate worker profiles, resource
                                      placement, review UI and richer
                                      observability

  7\. Evidence-driven optimization    Benchmark model routing and QC
                                      policies against held-out examples;
                                      optimize cost per accepted video
  -----------------------------------------------------------------------

## 11. Architectural Responsibilities That Must Stay Separate

Keep these decisions conceptually separate even if they initially run in
the same process:

-   **Workflow engine:** what runs next?
-   **Capability router:** which implementation should perform the task?
-   **Resource broker:** where should the task execute?
-   **Budget policy:** is this execution permitted at the expected cost?
-   **Quality gate:** is the resulting artifact acceptable?

These are separate responsibilities, not necessarily separate services.

## 12. Target-State Completion Criteria

The infrastructure is approaching the intended state when:

-   a worker can stop or restart without losing authoritative workflow
    state;
-   duplicate event delivery does not cause uncontrolled duplicate work
    or spend;
-   changes to an artifact invalidate only affected downstream work;
-   important quality decisions are explainable and traceable to
    evidence and evaluator versions;
-   provider/model and execution-environment choices can change without
    rewriting stage business logic;
-   paid fallbacks are explicitly budget-authorized;
-   artifacts remain addressable and versioned across local and remote
    storage;
-   cost, latency, retries, quality and regeneration are measurable per
    accepted video.

**Final recommendation:** treat this document as the target blueprint,
not the initial implementation checklist. Begin with a local vertical
slice and introduce each infrastructure component only when a
demonstrated requirement calls for it.
