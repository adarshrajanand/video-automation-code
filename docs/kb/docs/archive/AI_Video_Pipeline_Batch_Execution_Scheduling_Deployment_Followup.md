# AI Video Pipeline — Batch Execution, Scheduling, and Deployment
## Follow-up Architecture Note

**Status:** HISTORICAL / NON-NORMATIVE SUPPORTING NOTE
**Canonical replacements:** [Workflow and Event Execution](../AI_Video_Pipeline_Workflow_and_Event_Execution.md), [Routing and Providers](../AI_Video_Pipeline_Routing_and_Providers.md), and [End-to-End Implementation Plan](../AI_Video_Pipeline_End_to_End_Implementation_Plan.md)

> This note preserves deployment discussion. Follow the canonical documents and
> registries for current contracts, stage names, event names, and fixtures.

**Recommendation retained for context:** Keep the modular monorepo. Do not move to microservices now. Package the pipeline as one application, with independently claimable stage jobs and workers that can run locally or remotely.

The key distinction:
- **Wake-up:** cron, a manual CLI command, webhook, or cloud scheduler starts work.
- **Execution:** the workflow engine finds eligible jobs; workers claim and run them.

These do not have to be the same process, container, or machine.

## 1. Deployment options

### A. Minimal Python process + cron
A scheduler invokes a Python entry point. The process loads persisted state, reconciles interrupted work, finds eligible jobs, runs or dispatches bounded work, persists outcomes, and exits.

**Pros:** lowest complexity, easy local debugging, no container setup.
**Cons:** dependency/environment drift; explicit retries, timeouts, and recovery are still required.
**Use for:** the first end-to-end prototype.

### B. One Docker image + scheduler — recommended next step
Build the application once and invoke different commands inside the same image.

```bash
docker run --rm pipeline:dev python -m pipeline trigger --workflow daily-content
docker run --rm pipeline:dev python -m pipeline worker --job-id job_123
```

These commands are illustrative, not existing commands. Docker Compose can run one-off commands; Podman is an alternative container engine. Neither provides durable workflow state, a queue, or resource-aware routing by itself.

**Pros:** reproducible dependencies, same runtime on laptop/server/cloud, one build and release process.
**Cons:** media/ML dependencies can make the image large; containerization does not solve orchestration.

### C. Persistent control plane + short-lived workers — likely target
Keep workflow state and dependency evaluation in a control plane. Workers claim bounded jobs and exit when finished. They can run on a laptop, CPU cloud worker, or burst GPU environment.

```text
cron / manual / webhook
          |
          v
   control-plane entry
          |
   workflow state + outbox
          |
    eligible job records
          |
   +------+------+------+
   |             |      |
 CPU worker   GPU worker local worker
   |             |      |
   +------+------+------+
          |
 artifact store + database
```

### D. One microservice per stage
Avoid for now. It adds deployment, networking, versioning, authentication, and operations overhead before each stage needs its own service boundary. A stage can be independently callable and deployable later without being a microservice today.

## 2. Startup and resumption

Treat each invocation as a reconciliation/dispatch opportunity, not as a command to replay the whole pipeline from scratch.

1. Load workflow definition and effective configuration.
2. Load persisted run/job state.
3. Reconcile stale claims and interrupted jobs.
4. Find stages whose dependencies and quality gates are satisfied.
5. Create or identify jobs using stable idempotency keys.
6. Persist dispatch intent (outbox) before attempting dispatch.
7. Dispatch jobs or execute them locally.
8. Workers validate inputs, run stages, store outputs, and report outcomes.
9. Re-evaluate downstream eligibility.
10. Exit when no eligible work remains or the invocation's time/work budget is reached.

Example CLI shape:

```bash
python -m pipeline trigger --workflow daily-content
python -m pipeline dispatch --once
python -m pipeline worker --job-id job_123
python -m pipeline status --run-id run_123
```

If the machine is asleep between scheduled/manual batches, the next invocation can resume from durable state. For immediate event response, something must be awake to receive the event—a queue consumer, webhook endpoint, or scheduler. A database-backed outbox preserves dispatch intent if the process crashes before sending the job.

## 3. Event-driven without microservices

Event-driven should mean **state transitions and job eligibility**, not “one service per stage.”

```text
stage output committed
        |
persist job/artifact state
        |
evaluate dependencies + QC gates
        |
create downstream job(s) + outbox event
        |
dispatcher / queue / polling worker
        |
worker claims eligible job
```

Keep responsibilities separate:
- **Workflow engine:** decides what is eligible.
- **Router:** selects allowed implementation/provider/resource pool.
- **Dispatcher/queue:** makes jobs available to workers.
- **Worker:** claims a job, invokes the stage, commits outcome.
- **Artifact store:** stores large inputs/outputs.
- **Database:** authoritative workflow/job state and artifact metadata.

Do not hard-code a stage to call its successor directly. Commit its result and let the workflow engine evaluate what becomes eligible.

## 4. Suggested monorepo structure

This is illustrative; retain existing names and create modules only when needed.

```text
repo/
├── pyproject.toml
├── Dockerfile
├── compose.yaml
├── src/pipeline/
│   ├── cli.py
│   ├── contracts/
│   ├── workflow/{engine.py,readiness.py,recovery.py}
│   ├── events/{outbox.py,dispatcher.py}
│   ├── router/
│   ├── resources/
│   ├── artifacts/store.py
│   ├── execution/worker.py
│   ├── quality/
│   └── stages/{topic_discovery,idea,script,audio,visuals,composition,render}/
└── tests/
```

The worker resolves a job's stage type, loads input references, selects an eligible implementation, executes it, and commits output/status. The same stage contract can run as a local Python function, local worker, Docker job, cloud batch job, or future resource-specific worker.

**Independent execution comes from contracts, persisted job records, idempotency, and artifact references—not from separate deployment units.**

## 5. Docker image strategy

Start with **one image** and different commands/roles:
- trigger/reconcile;
- dispatcher;
- CPU stage worker;
- media/render worker.

Build once, version the image, and reuse that version across jobs. Do not rebuild for every job.

Split into multiple build targets/images only when there is evidence that:
- rendering needs large system libraries;
- GPU stages need different dependencies;
- image size materially affects cold starts/transfers;
- security boundaries differ;
- incompatible packages make one environment unreliable.

The split should follow runtime requirements, not a rule that every stage gets its own image.

## 6. Media and artifact transfers

Do not embed images, audio, or video in queue messages or database rows. Jobs/events should carry artifact references and metadata.

```text
job record (input URIs + metadata)
          |
download required inputs to temp workspace
          |
validate checksums/type/contract
          |
run stage -> write outputs locally
          |
upload output artifacts
          |
commit metadata + job outcome
          |
clean temporary workspace
```

Rules:
1. Use an `ArtifactStore` interface: local disk first, object storage later.
2. Treat artifact URIs as opaque; stages should not assume a local path or cloud vendor.
3. Download only what the stage needs. A text judge often needs text/metadata, not a video; a render worker may need visuals, audio, and timing data.
4. Store URI, checksum, media type, size, dimensions/duration, version, and lineage metadata as appropriate.
5. Use temporary workspaces and define cleanup for success, failure, and abandoned jobs.
6. Hashes help integrity checks and deduplication, but caching must never be required for correctness.
7. Worker-local disk is not the only durable copy for distributed execution.
8. Upload outputs before committing metadata; reconcile crashes between upload and database commit.

Progression:
- Local prototype: local files and predictable workspaces.
- Single machine/container: bind mount or volume.
- Distributed workers: remote object storage and database-held references.

## 7. Scheduling options

| Option | Best use | Limitation |
|---|---|---|
| Manual CLI | Development and debugging | Needs a person/trigger |
| Cron | Simple recurring batch on an always-on machine | Not a durable job queue |
| systemd timer | Scheduled Linux job with service controls/logging | Recovery/idempotency remain application responsibilities |
| GitHub Actions schedule | Repository-centric lightweight tasks | Not an always-on worker or workflow database; runs can be delayed |
| Managed cloud scheduler | Cloud-triggered entry point | Configuration and possible cost |
| Persistent queue + workers | Asynchronous dispatch and independent worker pools | More infrastructure to operate |

Recommended progression: manual CLI → reliable end-to-end run → cron/systemd timer → queue only when asynchronous dispatch, separate worker pools, or fast event response are needed.

Define timezone and missed-run behavior explicitly. GitHub Actions schedules use cron syntax and are generally interpreted in UTC unless a supported timezone option is configured. Make overlapping triggers safe with a run key/lease and idempotent job creation.

## 8. Control plane vs execution plane

Separate responsibilities even if they initially run in one process/container.

**Control plane**
- workflow/effective configuration;
- run and job state;
- dependency and quality-gate evaluation;
- idempotency keys, leases, retries, recovery;
- outbox/dispatch intent;
- routing policy and budget limits;
- run status and operator visibility.

**Execution plane**
- claim job;
- load stage contract and input references;
- acquire selected provider/compute capability;
- download inputs, run stage and applicable checks;
- upload outputs;
- report structured result and usage/cost metadata.

A managed batch service (for example, AWS Batch) is an optional execution substrate, not a requirement. Keep contracts and workflow semantics provider-neutral.

## 9. State, concurrency, and recovery

Use explicit job states, for example:

```text
PENDING -> READY -> CLAIMED -> RUNNING -> SUCCEEDED
                         |          |
                         |          +-> RETRYABLE_FAILURE
                         +-> LEASE_EXPIRED / RECLAIMABLE
```

Also represent terminal failure, cancellation, and quality rejection as needed.

Minimum safeguards:
- **Idempotent job creation:** same run/stage/inputs/config should not create duplicate logical jobs.
- **Leases:** abandoned claims expire and can be reclaimed.
- **Bounded retries:** classify retryable failures, cap attempts, apply backoff.
- **Idempotent outputs:** retries must not silently overwrite accepted artifacts.
- **Outbox:** persist job state and dispatch intent atomically where possible; retry unsent entries.
- **Reconciliation:** inspect stale claims, pending outbox entries, and orphaned uploads.
- **QC gates:** failed required checks do not unlock downstream work.
- **Versioned metadata:** record stage version, effective config, prompt/model/provider versions, input artifact versions, and usage/cost.

SQLite is fine for local development/single-process use. Do not share a SQLite file across remote workers on a network filesystem. Put persistence behind a repository/service interface so it can move to PostgreSQL or a managed database when remote concurrency warrants it. Even if a queue is added, the database remains the authoritative workflow/job state.

## 10. Routing

Keep routing separate from workflow transitions:
- workflow engine determines eligibility;
- router selects an allowed provider, implementation, or resource pool;
- dispatcher exposes the job to workers;
- worker executes and returns a structured outcome.

Never silently use paid compute when a free provider/quota is exhausted. Effective policy should explicitly choose among another eligible provider, defer to a later batch window, enqueue for later, or pause for review. Record the selected route and reason for quality/cost analysis.

## 11. Implementation phases

### Phase 1 — Prove locally
- Monorepo + CLI + minimal workflow runner.
- Local storage and single-process persistence.
- Explicit stage contracts and input/output references.
- Mock external providers initially.
- Demonstrate inspection and resumption.

**Exit criterion:** one small workflow can be triggered, persisted, inspected, and resumed after forced process exit.

### Phase 2 — Repeatable execution
- Add one Docker image.
- Run the same CLI inside/outside the container.
- Add cron/systemd only after manual execution works.
- Implement idempotency, leases, bounded retries, outbox, reconciliation.
- Add crash/duplicate-trigger tests.

**Exit criterion:** repeated triggers or worker termination do not corrupt state or create duplicate accepted outputs.

### Phase 3 — Distribute selectively
- Keep a small control-plane entry point.
- Run bounded workers as separate processes/containers.
- Add remote object storage when workers no longer share local disk.
- Keep queue optional until justified.
- Add CPU/GPU/provider-specific pools only for meaningful resource differences.

**Exit criterion:** one stage can run in another environment using only contracts, job metadata, and artifact references.

### Phase 4 — Optimize from evidence
Measure cost per accepted video, QC pass/reject and regeneration rates, wall-clock/cold-start time, transfer volume, dispatch latency, worker utilization, failures, and recovery time. Split images or adopt a managed queue/batch platform only when measurements show a clear benefit.

## 12. Tests before distributing work

1. The same scheduled trigger is delivered twice.
2. The process exits after job creation but before dispatch.
3. A worker crashes after artifact upload but before metadata commit.
4. A lease expires while a slow worker is still running.
5. A required QC failure prevents downstream execution.
6. A retry does not corrupt or overwrite an accepted artifact.
7. Provider quota exhaustion does not cause an unapproved paid call.
8. Missing/corrupt/incompatible input artifacts are handled safely.
9. Workers download only the artifacts their stage needs.
10. A resumed run uses intended upstream artifact versions and effective configuration.

## Final rule

> **Independent execution is a property of contracts and the job model—not a requirement to deploy every stage as a microservice.**

Build stages so they are independently callable, claimable, observable, and recoverable. Keep codebase, contracts, and releases unified until resource, dependency, reliability, or security constraints justify a split. This lets you run the whole batch on one machine today and distribute selected expensive jobs later without redesigning the pipeline.
