# AI Video Automation Pipeline — Local Infrastructure Profile

**Status:** Canonical fast-slice infrastructure profile

**Purpose:** Define the smallest reproducible runtime that can execute the
validated local workflow without selecting a cloud provider, external queue,
hosted database, or permanent model/provider.

This profile turns the local-first decisions in ADR-006, ADR-007, ADR-014, and
ADR-024 into an operational shape. It is an implementation boundary, not a
request to build a distributed platform. The [Fast Validation Plan](AI_Video_Pipeline_Fast_Validation_Plan.md)
remains the only immediate implementation scope.

## 1. Scope and non-goals

The local profile covers:

- one developer-controlled machine;
- one authoritative SQLite database on local storage;
- one local filesystem `ArtifactStore`;
- one process by default, with optional local role separation for testing;
- a SQLite transactional outbox and polling dispatcher;
- claimable jobs, leases, fencing, retries, reconciliation, and recovery scans;
- deterministic startup checks before new work is dispatched;
- version and environment capture sufficient to reproduce a run;
- local fault-injection, observability, and orphan-reconciliation behavior.

It deliberately does not select or require:

- PostgreSQL or another hosted database;
- object-storage vendor or bucket layout;
- a queue/event-broker vendor;
- Docker, Kubernetes, or a cloud scheduler for the first slice;
- a cloud or GPU provider;
- a particular LLM, TTS, ASR, image, video, or publishing provider;
- automatic public publishing.

The local profile must remain usable with fixture/fake capabilities and without
provider credentials. A missing optional provider is a configuration or
capability-eligibility result; it must not prevent contract, workflow, recovery,
or media-fixture tests from running.

## 2. Baseline topology

The default topology is a modular monolith with explicit control-plane and
execution-plane boundaries:

```text
CLI / scheduled trigger
          |
          v
   +---------------+       +---------------------+
   | Control Plane |------>| SQLite repository   |
   | run/readiness |       | workflow truth      |
   +-------+-------+       +----------+----------+
           |                          |
           v                          v
   +---------------+       +---------------------+
   | Outbox poller |------>| Claimable jobs/leases|
   +-------+-------+       +----------+----------+
           |                          |
           +------------+-------------+
                        v
                 +-------------+
                 | Local worker|
                 | capabilities|
                  +------+------+
                        |
          +-------------+--------------+
          v                            v
   +-------------+              +-------------+
   | ArtifactStore|              | Quality jobs|
   | local bytes |              | and gates   |
   +------+------+              +-------------+
          |
          v
   local workspace / temporary files / reports
```

The boxes are responsibilities, not mandatory services. The first executable
form may run the control plane, dispatcher, worker, quality executor, and
reconciler in one bounded process. A separate process or container is an
operational choice only after the same transaction and recovery semantics work
in the single-process mode.

### 2.1 Ownership boundaries

| Responsibility | Local owner | Must not become authoritative for |
|---|---|---|
| Workflow transitions and readiness | Control plane / Workflow Engine | provider selection, model output, or queue state |
| Durable metadata and transactions | SQLite repository | large media bytes |
| Event delivery | Outbox poller / dispatcher | workflow truth or completion by itself |
| Temporary ownership | Job/Lease records | user locks or provider identity |
| Capability execution | Local worker and adapters | workflow transitions or budget bypass |
| Immutable bytes | `ArtifactStore` | stage status, quality acceptance, or publication state |
| Quality evidence and gate result | Quality subsystem | silent artifact mutation or direct workflow mutation |
| Diagnostics | Logs/metrics/reports | authoritative state |

The control plane remains authoritative even when all responsibilities share one
Python process. A capability or provider adapter may return a result, but only a
control-plane transaction may apply the result to workflow state.

## 3. Runtime modes

The implementation supports these modes in order of preference:

| Mode | Use | Required behavior |
|---|---|---|
| `single_process` | Default fast-slice execution | One process runs bounded control, polling, worker, quality, and recovery loops; startup checks complete before dispatch begins |
| `split_local` | Crash, lease, and isolation tests | Separate local commands use the same local workspace; SQLite remains on one machine and every role revalidates readiness before work |
| `container_smoke` | Later packaging/reproducibility check | One versioned image exposes role commands; container health is a readiness signal, never the source of workflow truth |
| `remote_worker` | Post-validation extension | Only after the promotion gates in Section 14 pass; remote workers use opaque artifact URIs and durable remote-safe metadata |

`single_process` is not a shortcut around the event model. It still creates
outbox rows, jobs, leases, input manifests, quality work, and recovery records.
The loop merely replaces a delivery hop with a local poll.

`split_local` does not require every process to start at the same instant. Jobs
and outbox messages are durable. The dispatcher must not deliver new work until
the control-plane startup barrier passes, but a worker may restart later and
reclaim ready work safely. An operator may require all configured roles to pass
their preflight before starting the dispatcher, but simultaneous process startup
is not the correctness mechanism.

## 4. Local workspace and storage layout

The local adapter uses one configurable `PIPELINE_HOME`. The exact default path
is an implementation choice, but runtime state must be outside versioned source
files and must be easy to delete or archive as one unit.

```text
PIPELINE_HOME/
├── state/
│   ├── pipeline.sqlite3
│   └── migrations/
├── artifacts/
│   ├── immutable bytes addressed by opaque artifact URI
│   └── quarantine/
├── tmp/
│   └── <attempt_id>/<workspace files>
├── runtime/
│   ├── readiness/
│   ├── role leases/
│   └── process diagnostics
├── logs/
└── reports/
```

Rules:

1. `state/pipeline.sqlite3` is local-only. It must not be opened from a network
   filesystem or shared by remote workers.
2. `artifacts/` contains immutable published bytes. A replacement receives a
   new artifact ID/version and never overwrites the historical path.
3. `tmp/` is disposable and scoped by attempt, worker identity, and run where
   useful. Temporary files are not artifact records.
4. `quarantine/` holds bytes that cannot yet be matched to durable metadata.
   Reconciliation must inspect them before garbage collection removes them.
5. `runtime/` contains ephemeral process/readiness information only. It is not
   a second workflow database and must not be used to infer completion.
6. Logs and reports may be rotated, but durable evaluations, gate results,
   recovery decisions, and artifact metadata remain in the repository or
   explicitly retained evidence artifacts.

The persisted `Artifact.uri` is opaque to stages. The local store may map it to
a filesystem path today and a different physical location later without
changing the logical artifact ID, hash, dependencies, or provenance.

## 5. Startup readiness barrier

The runtime must fail closed: no new event delivery or job claim begins until
the local control plane has completed the startup barrier. The barrier is a
process/runtime readiness signal, not a new workflow state and not a replacement
for durable readiness evaluation.

### 5.1 Preflight checks

Before entering `READY_FOR_DISPATCH`, the control plane verifies:

1. the supported Python/package/runtime versions are available;
2. canonical registries and the selected workflow/profile parse and validate;
3. the database path is local, readable, writable, and at the expected schema
   migration version;
4. foreign-key and transaction behavior is available under the repository's
   configured SQLite settings;
5. the artifact root and temporary workspace support create, read, checksum,
   and atomic-publish operations;
6. required media tools such as FFmpeg/ffprobe are present at approved versions
   for the selected media path;
7. configured capability adapters have valid non-secret configuration and
   declared data-policy eligibility;
8. no required paid provider call is needed merely to prove readiness;
9. available disk space, temporary storage, and configured runtime limits meet
   the run policy;
10. the process has a unique local role identity and no incompatible local
    runtime lock is active.

The preflight must report each failed check with a stable reason. It must not
hide a missing optional capability behind a generic “system healthy” result.

### 5.2 Recovery before dispatch

After static preflight and before dispatch, the control plane performs a bounded
recovery scan:

- reclaim expired outbox claims;
- reclaim expired job leases using fencing rules;
- inspect `UNKNOWN` attempts and provider invocations for reconciliation;
- find incomplete artifact publish transactions and quarantine or reconcile
  their bytes;
- identify stale temporary workspaces;
- verify that active pointers do not reference invalidated artifacts;
- record a `RecoveryDecision` for any non-trivial repair or human-attention
  outcome.

Only after this scan succeeds or records policy-approved deferred work may the
runtime create the dispatcher-ready signal. A recovery item that could cause
duplicate paid work blocks automatic dispatch until reconciliation or explicit
human policy permits continuation.

### 5.3 Startup and shutdown behavior

The default local sequence is:

```text
check setup
  → migrate/verify local repository
  → run startup recovery
  → load workflow/profile/configuration
  → start worker/quality loops
  → enable outbox dispatch
```

Graceful shutdown stops new claims first, lets the current bounded transaction
finish when possible, records diagnostics, and exits. A forced termination is
expected to leave durable jobs or leases that the next startup can reclaim; it
must not require an in-memory callback to resume the run.

## 6. Persistence and transaction boundaries

SQLite is the authoritative local repository for workflow metadata, jobs,
leases, events, outbox delivery, artifacts, quality results, budgets, and
recovery decisions. The local profile does not allow a queue, filesystem marker,
log line, or provider response to become a second source of truth.

The implementation must preserve these boundaries:

### 6.1 Create work

```text
BEGIN TRANSACTION
  resolve or create WorkflowRun and StageInstance
  create StageAttempt, Job, and idempotency records when absent
  insert the EventEnvelope/OutboxMessage intent
COMMIT
```

Duplicate triggers use the contract's `run_key` and job idempotency key. A
repeated request returns or reconciles the existing logical work rather than
creating a second paid operation.

### 6.2 Claim work

```text
BEGIN TRANSACTION
  atomically select an eligible READY job
  increment the delivery/claim evidence
  create or advance the Lease fencing token
  mark the attempt CLAIMED/RUNNING according to the lifecycle
COMMIT
```

The worker receives the job ID, attempt ID, owner ID, expiry, and fencing token.
Every heartbeat and result commit compares those ownership values. An expired
worker may finish in the outside world, but it may not overwrite a newer active
attempt.

### 6.3 Commit a capability result

```text
validate structured result and technical invariants
write bytes to an attempt-scoped temporary workspace
checksum and publish immutable bytes through ArtifactStore
BEGIN TRANSACTION
  create Artifact and ArtifactDependency records
  record capability/provider usage and cost
  apply idempotency/reconciliation result
  mark attempt execution success or failure
  set gated stage acceptance to PENDING
  create QualityInputManifest, quality Job, and event intent
COMMIT
```

The quality worker performs a separate authoritative transaction for evaluation
records, the aggregate gate result, acceptance status, repair plan, human review,
or downstream readiness. Execution success alone never creates downstream work.

### 6.4 Outbox delivery

The dispatcher claims pending outbox rows with an expiry, delivers a small
event envelope, and marks the row delivered only after the local consumer
acknowledges it. A crash between delivery and acknowledgement may duplicate the
event. Consumer receipts and job idempotency turn that duplicate into a no-op or
an explicit reconciliation path.

The dispatcher must never delete a failed outbox row merely because delivery has
been attempted. Retain attempts, last error, availability time, and the
dead-letter or human-attention decision.

## 7. Artifact publication and orphan reconciliation

The local `ArtifactStore` protocol is:

1. create an attempt-scoped temporary directory;
2. write output bytes and structured payloads there;
3. validate media/schema/content before publication;
4. compute the declared content hash and size;
5. publish to an immutable store location through the adapter;
6. verify the published bytes and metadata;
7. commit artifact metadata and dependency edges transactionally;
8. remove the temporary workspace only after the metadata result is durable.

If the metadata transaction fails after bytes are published, the bytes are not
silently deleted or treated as an accepted artifact. The reconciliation scan
records the missing metadata, checks the attempt/idempotency key, and either:

- attaches the bytes to the already-authorized artifact record;
- moves them to quarantine for operator inspection; or
- removes them after the retention/grace policy records why they are safe to
  delete.

If the database records an artifact but the bytes are missing or hash-invalid,
the artifact is marked unusable through the normal invalidation/recovery path.
The system must not repair a missing byte by changing its URI to an arbitrary
new file.

Artifact garbage collection is separate from workflow correctness. It may remove
temporary files and expired quarantine entries only after checking active
pointers, dependency history, retention class, publication references, and
open recovery/review records.

## 8. Dispatcher, worker, and recovery rules

### 8.1 Dispatcher

The local dispatcher:

- polls pending outbox messages with bounded batch size and backoff;
- refuses to start before the control-plane readiness barrier;
- delivers notifications without assuming they are current;
- records delivery attempts and expiry;
- stops dispatching new work when shutdown or a fatal readiness failure is set;
- leaves authoritative eligibility decisions to the Workflow Engine.

Polling cadence is configuration, not a correctness parameter. A slow poller
may delay work; it must not lose work or make an empty queue mean fan-in is
complete.

### 8.2 Worker

The local worker:

1. locates the durable job;
2. claims it transactionally;
3. revalidates dependencies, accepted pointers, budget, policy, and gate state;
4. resolves a capability and resource assignment;
5. executes within the bounded timeout and workspace policy;
6. validates and publishes outputs through the artifact protocol;
7. commits the structured result only while the lease/fencing token is valid;
8. acknowledges delivery after the authoritative commit;
9. emits correlated diagnostics.

Stages never import provider SDKs. A local adapter may invoke a subprocess,
fixture, hosted API, or model, but the capability boundary normalizes its result,
usage, cost, and error classification.

### 8.3 Recovery scan

The recovery scan is safe to run repeatedly. It examines:

- expired leases and stale attempts;
- outbox rows claimed by dead dispatchers;
- provider calls in `UNKNOWN` state;
- artifact bytes without metadata;
- metadata with missing or mismatched bytes;
- quality jobs whose target hashes no longer match active artifacts;
- human reviews whose exact targets were superseded;
- local runtime markers left by a terminated process.

Recovery may resume, retry, reconcile, regenerate, wait for human review, or
fail. Each non-trivial choice is represented by a durable `RecoveryDecision`
and names the relevant failure codes and target records.

## 9. Local commands and role startup

These are target command roles for the fast slice; the exact CLI framework is
reversible, but the responsibilities and readiness behavior are not:

```bash
python -m pipeline check-setup
python -m pipeline control migrate
python -m pipeline control reconcile --once
python -m pipeline dispatcher run --once
python -m pipeline worker run --once
python -m pipeline run create --workflow explainer_validation_v1 --topic-file fixtures/topic.json
python -m pipeline run status --run-id RUN_ID
```

For the default single-process mode, the equivalent command may run the control,
dispatcher, worker, quality, and recovery loops under one process budget. For
split-local mode:

1. the control/reconcile role validates the repository, artifact store, tools,
   and effective configuration;
2. worker roles perform their own local capability preflight and wait for the
   control readiness signal;
3. the dispatcher is enabled only after the control readiness signal exists;
4. a worker may be absent or restarted without losing durable jobs;
5. a new claim is not made if the repository or artifact root becomes
   unavailable after startup.

This ordering prevents a startup race without pretending that process presence
is workflow truth. The authoritative state remains in SQLite and the artifact
store protocol.

## 10. Version control and reproducibility

The following inputs are versioned or captured for every reproducible run:

| Input | Source of truth | Capture requirement |
|---|---|---|
| Pipeline source and docs | Git commit/tag | record commit or immutable build identifier |
| Python/Node dependencies | project manifest and lockfile | record lockfile/fingerprint; do not use floating versions for validation |
| Database schema | ordered migration set | record applied migration version |
| Workflow/stage/event/quality/recovery registries | versioned repository files | record registry versions and workflow ID/version |
| Domain/channel/effective settings | `EffectiveConfig` | record config ID, source map, and canonical hash |
| Prompts/rubrics | versioned files | record exact prompt/rubric versions |
| Capability/provider adapters | implementation/config | record implementation, provider/model, and provider config hash |
| Media toolchain | FFmpeg/ffprobe/renderer/font versions | record executable/version fingerprint in run/report metadata |
| Runtime placement | `ResourceAssignment` | record placement class and constraints hash |
| Container image, when applicable | immutable image digest | record digest, not only a mutable tag |

Runtime state, local database files, credentials, temporary bytes, and provider
payloads are not source control. They must not be committed merely to make a
run reproducible. Reproducibility comes from immutable references, hashes,
versioned configuration, and retained evidence.

An implementation may store environment/toolchain data in a run report or
environment-fingerprint artifact when the existing contract has no dedicated
field. If that evidence changes workflow eligibility or quality, the affected
contract and decision log must be updated before implementation.

## 11. Observability and local resource controls

Every structured log, metric, and report should include the identifiers that
exist for the operation:

```text
run_id
stage_instance_id
attempt_id
job_id
event_id
artifact_id
evaluation_id
provider_invocation_id
correlation_id
```

At minimum, the local runtime reports:

- startup/preflight result and failed-check reason;
- schema migration version and repository path class;
- ready, running, waiting, unknown, and terminal work counts;
- outbox pending/claimed/failed counts and oldest age;
- lease expiry/reclamation counts;
- stage latency and attempt number;
- provider timeout, retry, reconciliation, and cost observations;
- artifact publish, checksum, orphan, and quarantine counts;
- quality pass/regenerate/review/fail outcomes;
- invalidation fan-out and repair scope;
- temporary-workspace size and cleanup results;
- available disk and configured runtime budget.

Logs must redact credentials, authorization headers, raw private payloads, and
unbounded provider responses. A report may contain a safe request fingerprint,
provider operation ID, or evidence artifact reference without containing the
secret request itself.

Each job class has an explicit timeout, retry policy, workspace limit, and cost
authorization. The local runner stops or pauses when those limits are reached;
it does not silently continue because a process still has CPU or disk available.

## 12. Fault-injection requirements

The local profile is accepted only when the following scenarios are testable
without a cloud service:

| Injection point | Required result |
|---|---|
| Before repository migration completes | Runtime remains not-ready and dispatch does not begin |
| After outbox claim, before delivery | Expiry returns the message to a safe retry/recovery path |
| Duplicate outbox delivery | Consumer receipt/job idempotency prevents duplicate logical work |
| After job claim, before provider call | Lease expiry allows safe reclamation |
| After provider success, before local commit | Idempotency/reconciliation prevents blind duplicate spend |
| After artifact publish, before metadata commit | Bytes are found and quarantined/reconciled as an orphan |
| After metadata commit, before acknowledgement | Redelivery becomes a no-op or reconciliation |
| Stale worker returns with old fencing token | Result commit is rejected |
| Quality job sees invalidated target | Evaluation cannot unlock downstream work |
| One scene is repaired | Only the affected descendants are invalidated |
| Tool or artifact root disappears after startup | New claims stop; existing state remains inspectable |
| Paid fallback is disabled | No paid invocation is made; policy records pause/defer/fail |
| Process exits while human review is open | Review remains durable and resumable |

The test harness should exercise the same repository and artifact-store
interfaces used by the runtime. It must not pass only because a fake dispatcher
short-circuits the transaction boundaries.

## 13. Container boundary

Containers are a packaging and isolation option after the local single-process
semantics are proven. The first containerized shape should use one versioned
image with role commands rather than one container per workflow event:

```text
pipeline control reconcile
pipeline dispatcher run
pipeline worker cpu
pipeline worker media
pipeline worker evaluator
```

If a local Compose-like launcher is introduced:

- health checks must run real repository/artifact/tool preflight, not merely
  test that a process is listening;
- the control/reconcile role must reach readiness before the dispatcher begins;
- worker restarts must be safe because jobs, leases, and artifacts are durable;
- `depends_on`-style startup ordering is only a convenience and cannot replace
  readiness checks or recovery;
- containers must not share SQLite through a network filesystem;
- image tags are for human convenience; run records use immutable image digests
  or build identifiers;
- secrets are injected at runtime and are never baked into images or logs.

Split images only when media dependencies, GPU libraries, security boundaries,
cold-start/transfer costs, or worker reliability provide measured justification.
Do not create a container per event or per artifact.

## 14. Promotion gates and remote migration order

Remote infrastructure is an evidence-gated extension. The default promotion
order is:

```text
validated local single process
        ↓
one local image with role commands (optional)
        ↓
object-storage adapter and migration rehearsal
        ↓
PostgreSQL or another justified authoritative metadata store
        ↓
one remote CPU worker
        ↓
one bounded GPU/media worker, if measured necessary
        ↓
queue/broker only if polling is a measured bottleneck
        ↓
backpressure, resource pools, and further worker separation
```

This order is deliberate:

- opaque remotely accessible artifact URIs are needed before remote workers;
- multi-machine authoritative state is needed before relying on remote workers
  for production work;
- a queue changes delivery, not workflow truth, so polling remains preferable
  until its latency or load is measured as a bottleneck;
- resource placement and backpressure should be introduced from observed
  workload/cost evidence rather than deployment fashion.

Before each promotion, the validation report must show:

1. the local fast-plan acceptance criteria still pass;
2. crash, duplicate-delivery, lease-fencing, unknown-outcome, fan-in, QC,
   orphan, and surgical-repair tests pass;
3. artifact checksums and opaque URI semantics survive the migration rehearsal;
4. backups, restore, retention, and garbage-collection behavior are defined for
   every new durable store;
5. the measured bottleneck and expected improvement justify the added failure
   surface and operating cost;
6. the same contracts, event taxonomy, recovery decisions, and control-plane
   ownership remain in force.

Any different migration sequence requires a new accepted decision and an
explicit migration note. The queue, database, and object store are replaceable
adapters; none becomes the workflow authority merely because it is introduced.

## 15. Local infrastructure acceptance checklist

- [ ] A clean workspace can run setup checks without provider credentials.
- [ ] Registry/workflow/profile validation occurs before dispatch.
- [ ] SQLite is local-only, versioned, and authoritative for workflow metadata.
- [ ] Artifact bytes use immutable publication and opaque references.
- [ ] Temporary output is isolated by attempt and reconciled after failures.
- [ ] Startup recovery handles stale outbox claims, leases, unknown outcomes,
      and orphan bytes before new work is enabled.
- [ ] Duplicate events and duplicate run/job requests are safe.
- [ ] Fencing prevents an expired worker from committing over a newer owner.
- [ ] Quality work is durable and cannot be bypassed by execution success.
- [ ] Logs/reports correlate durable IDs and exclude secrets.
- [ ] Git, dependency, workflow, schema, tool, provider, and image versions are
      captured for reproducibility.
- [ ] Fault-injection results are recorded in the validation report.
- [ ] Containerization, if used, has a real readiness barrier and no
      container-per-event design.
- [ ] Remote promotion is blocked until the measured evidence gates pass.

## 16. Related canonical documents

- [Documentation Guide](README.md)
- [Canonical Architecture](AI_Video_Pipeline_Architecture.md)
- [Decision Log](AI_Video_Pipeline_Decisions.md)
- [Contracts and Data Model](AI_Video_Pipeline_Contracts_and_Data_Model.md)
- [Workflow and Event Execution](AI_Video_Pipeline_Workflow_and_Event_Execution.md)
- [Routing and Providers](AI_Video_Pipeline_Routing_and_Providers.md)
- [Remote Infrastructure Expansion](AI_Video_Pipeline_Remote_Infrastructure_Expansion.md)
- [Fast Validation Plan](AI_Video_Pipeline_Fast_Validation_Plan.md)
- [End-to-End Implementation Plan](AI_Video_Pipeline_End_to_End_Implementation_Plan.md)
