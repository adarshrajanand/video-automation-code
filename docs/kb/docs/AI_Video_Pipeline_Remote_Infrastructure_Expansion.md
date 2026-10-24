# AI Video Automation Pipeline — Remote Infrastructure Expansion

**Status:** Target evolution / deferred implementation

**Purpose:** Define how the validated local pipeline can evolve to remote
workers, durable multi-machine metadata, object storage, and optional queue
delivery without changing the workflow, artifact, quality, recovery, or
provider-neutral capability contracts.

## Authority and implementation boundary

This document describes the target remote evolution. It is not an immediate
implementation scope.

The current implementation authorities are:

- [Canonical Architecture](AI_Video_Pipeline_Architecture.md);
- [Decision Log](AI_Video_Pipeline_Decisions.md);
- [Contracts and Data Model](AI_Video_Pipeline_Contracts_and_Data_Model.md);
- [Workflow and Event Execution](AI_Video_Pipeline_Workflow_and_Event_Execution.md);
- [Local Infrastructure Profile](AI_Video_Pipeline_Local_Infrastructure_Profile.md);
- [Fast Validation Plan](AI_Video_Pipeline_Fast_Validation_Plan.md); and
- the normative registries under `kb/docs/registries/`.

The local profile and fast plan take precedence for current code. Remote work
may begin only after the evidence gates in [ADR-024](AI_Video_Pipeline_Decisions.md#adr-024-local-infrastructure-profile-before-remote-promotion)
pass. A provider, cloud, queue, database host, container orchestrator, or exact
capacity target is not selected by this document.

## 1. Goals and non-goals

The remote expansion should make it possible to:

- run control-plane metadata on a durable multi-machine database;
- store immutable artifact bytes in remotely accessible object storage;
- execute bounded CPU and GPU/media jobs on replaceable worker pools;
- preserve at-least-once delivery, job idempotency, lease fencing, and recovery;
- move selected workers without changing stage business logic;
- apply backpressure and resource placement from measured workload evidence;
- retain exact hashes, versions, provenance, quality evidence, and cost records;
- operate safely when a worker, provider, network, queue, or storage operation
  disappears at any point.

It does not attempt to:

- define one required cloud architecture;
- make a queue the source of workflow truth;
- split every stage into a service;
- require Kubernetes or another orchestrator;
- make remote execution mandatory for every capability;
- define autoscaling numbers before workload measurements exist;
- bypass human approval, quality gates, budgets, or reconciliation;
- preserve shared-network SQLite as a transitional distributed database.

## 2. Invariants carried forward from the local system

Remote infrastructure is acceptable only if these local semantics remain true:

1. The control plane owns workflow transitions, readiness, budgets, recovery,
   quality-gate application, human review, and publication readiness.
2. A queue, worker, object store, provider, log, or metric is not workflow
   authority.
3. Events notify; durable state decides whether work is still eligible.
4. Delivery and execution are at least once; duplicate delivery is expected.
5. Every claimable job has an idempotency key and a lease/fencing term.
6. A stale worker cannot commit over a newer owner or active attempt.
7. External unknown outcomes enter reconciliation before unsafe retry.
8. Artifacts are immutable and referenced through opaque artifact URIs.
9. Artifact bytes and metadata may be published in separate physical systems,
   but reconciliation makes the gap explicit and recoverable.
10. Execution success, quality acceptance, human approval, and publication
    readiness remain separate states.
11. Stages request capabilities and never import provider SDKs directly.
12. Provider routing and resource placement remain separate decisions.
13. Every accepted output retains exact input hashes, configuration, code,
    provider, evaluator, and environment/version evidence.
14. The same failure codes, event names, contracts, and recovery actions apply
    locally and remotely.

These invariants are more important than any particular deployment topology.

## 3. Evidence-gated migration sequence

The default sequence is deliberately incremental:

```text
validated local single process
        ↓
one versioned image with role commands (optional)
        ↓
object-storage adapter and migration/reconciliation rehearsal
        ↓
authoritative multi-machine metadata database
        ↓
one remote CPU worker
        ↓
one bounded GPU/media worker when justified
        ↓
queue adapter only if polling is a measured bottleneck
        ↓
backpressure, resource pools, and further worker isolation
```

| Step | Change | Required evidence before promotion |
|---|---|---|
| Local proof | Single-process and split-local modes | Fast-plan acceptance, crash recovery, fencing, orphan, quality, and surgical-repair tests pass |
| Packaging | One image with role commands | Reproducible build, startup diagnostics, clean shutdown, digest capture, no secret leakage |
| Artifact remote access | Object-storage adapter and migration rehearsal | Hash-preserving copy, URI resolution, missing-byte detection, orphan reconciliation, retention and restore test |
| Durable multi-machine state | PostgreSQL or justified equivalent | Schema migration, transaction/concurrency, backup/restore, lease fencing, outbox recovery, and cutover rehearsal |
| Remote CPU | One stateless bounded worker | Remote download/checksum/upload, worker disappearance recovery, cost/latency comparison, no shared SQLite |
| Remote GPU/media | One bounded specialized worker | Measured GPU need, image/runtime compatibility, artifact transfer cost, timeout/retry behavior, quality evidence |
| Queue delivery | Queue adapter | Polling latency/load bottleneck, duplicate/dead-letter test, replay/recovery behavior, no change to workflow authority |
| Pooling and backpressure | Multiple worker classes/pools | Capacity model, oldest-job/backlog metrics, budget enforcement, fairness, and safe scale-down behavior |

Each step must retain a rollback or pause path. A passing interface test is not
enough to promote a new infrastructure layer; the validation report must show
that the new failure surface is understood and justified.

## 4. Target logical topology

The target topology preserves the same responsibilities while allowing selected
roles to run remotely:

```text
                    +-----------------------------+
CLI / API / Scheduler| Control Plane               |
-------------------->| readiness, workflow, policy |
                    +--------------+--------------+
                                   |
                  +----------------+----------------+
                  |                                 |
                  v                                 v
        +---------------------+           +---------------------+
        | Authoritative DB    |           | Transactional       |
        | runs/jobs/leases/   |           | outbox + event       |
        | artifacts/QC/budget|           | delivery adapter     |
        +----------+----------+           +----------+----------+
                   |                                 |
                   |                                 v
                   |                       +---------------------+
                   |                       | Queue or poller     |
                   |                       | delivery only       |
                   |                       +----------+----------+
                   |                                  |
                   +------------------+---------------+
                                      v
                 +--------------------------------------------+
                 | Stateless bounded worker pools             |
                 | CPU | media | GPU | evaluator | publisher  |
                 +-------------------+------------------------+
                                     |
                     +---------------+---------------+
                     v                               v
            +------------------+             +---------------+
            | Object storage   |             | External/local |
            | immutable bytes  |             | capabilities   |
            +------------------+             +---------------+

          Logs, metrics, traces, reports, and audit evidence
```

The diagram does not require one service per box. A control process may own
workflow and dispatch, and a worker image may support several role commands.
The topology becomes distributed only where a measured resource, isolation,
latency, concurrency, or retention requirement justifies it.

## 5. Control-plane and data-plane boundary

### Control plane

The control plane remains the authoritative owner of:

- workflow definitions and effective configuration;
- run, stage-instance, attempt, job, and lease state;
- readiness and dependency evaluation;
- quality acceptance and repair decisions;
- budgets, reservations, and paid-fallback authorization;
- event/outbox records and consumer receipts;
- human reviews and publication readiness;
- reconciliation, recovery decisions, and operator controls.

It may issue a remote worker a bounded execution assignment, but it does not
transfer workflow authority to that worker.

### Remote execution plane

A remote worker may:

- claim or receive a job reference;
- revalidate current eligibility through an approved control-plane interface;
- obtain a routing/resource assignment;
- download declared input artifacts;
- verify hashes and data policy;
- execute one bounded capability or stage operation;
- publish output bytes through `ArtifactStore`;
- return structured results, usage, diagnostics, and provider operation IDs.

A remote worker may not:

- invent a stage transition;
- mark quality accepted without the quality subsystem;
- change budget policy;
- publish without the effective approval state;
- read arbitrary files from another run;
- treat a queue acknowledgement as a successful execution;
- use a shared network SQLite database.

## 6. Metadata database expansion

The local repository interfaces should remain stable while the physical
metadata store changes. The remote database must preserve the existing durable
records and constraints, including:

- unique logical stage-instance identity;
- idempotency-key uniqueness and request-fingerprint comparison;
- one active lease term per job;
- monotonic fencing tokens;
- exact artifact/hash and dependency references;
- quality evaluation and gate-result immutability;
- outbox delivery attempts and consumer receipts;
- budget reservation uniqueness and settlement state;
- recovery decisions and audit relationships.

### 6.1 Migration requirements

Before cutover:

1. freeze the schema contract version and migration inventory;
2. export a consistent local metadata snapshot;
3. validate row counts, identities, foreign keys, hashes, active pointers,
   leases, outbox rows, and open reviews;
4. load a rehearsal database and run the repository contract suite;
5. run duplicate-delivery, lease-fencing, unknown-outcome, and fan-in tests;
6. test backup and restore from the migrated representation;
7. define the cutover pause, rollback point, and operator decision record.

Do not make the remote database authoritative merely because a connection is
available. Cutover is an explicit control-plane migration with a recorded
schema/version and a way to stop new work safely.

### 6.2 Transaction expectations

The remote database must support the equivalent authoritative transactions for:

- creating a stage instance, attempt, job, and outbox intent;
- claiming a job and advancing its fencing term;
- renewing or expiring a lease;
- committing a result and creating quality work;
- applying a quality gate and creating downstream readiness or repair;
- recording unknown outcomes and recovery decisions;
- settling or releasing budget reservations.

The exact SQL dialect and hosting model are deferred. The repository contract,
isolation requirements, and failure behavior are not deferred.

## 7. Object-storage expansion

Object storage replaces the physical location behind `ArtifactStore`; it does
not change the logical `Artifact` contract. A remote artifact record retains:

- opaque logical artifact ID;
- immutable URI or storage reference;
- SHA-256 or declared content hash;
- byte size and media metadata;
- producer attempt and input artifact IDs;
- configuration, producer, and retention metadata;
- state and active-pointer relationships.

### 7.1 Remote artifact protocol

The remote protocol is:

1. worker creates an attempt-scoped temporary workspace;
2. control plane resolves exact input artifact IDs and hashes;
3. worker obtains authorized access only to those inputs;
4. worker verifies every downloaded hash before execution;
5. worker writes and validates output locally;
6. worker computes the output hash and publishes immutable bytes;
7. worker verifies the remote object and records the object operation metadata;
8. control plane transactionally commits artifact metadata, dependencies, usage,
   and quality work while the lease/fencing term remains valid;
9. cleanup removes only temporary files, never historical accepted bytes.

The object store must support or be wrapped with:

- immutable publication semantics or an equivalent write-once key policy;
- content-hash verification after upload and download;
- scoped access for a worker and job;
- failed-upload and partial-upload detection;
- retention and deletion policy distinct from workflow state;
- listing or manifest support for orphan reconciliation;
- audit information sufficient to investigate reads, writes, and deletes.

The physical object key must not be the only identity. A migration may change
bucket, region, prefix, or provider while retaining the logical artifact ID and
content hash.

### 7.2 Reconciliation and garbage collection

The remote reconciliation process compares:

```text
authoritative artifact metadata
        ↔ object manifest/listing
        ↔ open attempts and idempotency records
        ↔ active pointers and retention references
```

It classifies differences as:

- metadata with missing object;
- object with matching committed metadata;
- object published before metadata commit;
- object with hash or size mismatch;
- object outside any known run/retention scope;
- deletion or lifecycle operation with unknown outcome.

Unknown deletion outcomes are reconciled before a replacement is accepted.
Garbage collection must not delete an object referenced by an active pointer,
publication attempt, quality evidence, open review, recovery decision, or
retention policy. Orphan cleanup requires a grace period and an auditable
decision.

## 8. Remote worker lifecycle

The remote worker lifecycle remains compatible with the local worker:

```text
start and self-check
    ↓
receive notification/job reference
    ↓
claim or validate job ownership in authoritative state
    ↓
renew lease for bounded execution
    ↓
resolve exact inputs and resource assignment
    ↓
download and checksum inputs
    ↓
execute capability/stage operation
    ↓
publish and verify immutable outputs
    ↓
commit result with owner and fencing compare-and-set
    ↓
acknowledge delivery and emit diagnostics
```

The worker must be disposable. A worker process, VM, container, or node may
disappear after any step. Recovery uses the durable job, lease, idempotency,
provider-invocation, artifact, and recovery records rather than a process-local
callback.

### 8.1 Lease and heartbeat rules

- lease duration is selected by job class and expected runtime;
- long media jobs renew only through the authoritative control plane;
- heartbeat success is recorded, not inferred from a local timer;
- a worker may renew only its current owner/fencing term;
- lease expiry makes a job reclaimable but does not prove the old worker stopped;
- every result commit compares owner, attempt, and fencing token;
- a reclaimed job receives a new ownership term and cannot be overwritten by a
  stale worker;
- operators may cancel a lease with a durable audit record;
- lease expiry, renewal failure, and fencing rejection are metrics and recovery
  inputs.

The queue visibility timeout, if a queue is later introduced, is not a
replacement for the database lease or fencing token.

### 8.2 Remote input and output limits

Each assignment declares:

- required artifact IDs and hashes;
- maximum input/output bytes;
- temporary workspace quota;
- CPU, memory, and optional VRAM requirements;
- network/data-classification policy;
- maximum useful runtime and wall-clock deadline;
- expected cost and budget scope;
- cleanup policy;
- capability, implementation, and tool versions.

The worker rejects an assignment it cannot satisfy. It must not silently use a
larger machine, a paid fallback, a different data region, or an unapproved
provider to make the job pass.

## 9. Queue and delivery expansion

A queue is an optional delivery adapter introduced only when polling is a
measured bottleneck. The queue receives a small event or job reference; it does
not receive large media bytes or become authoritative workflow state.

### 9.1 Queue protocol

The queue adapter must support the equivalent of:

1. outbox row is committed with durable workflow state;
2. dispatcher publishes an event/job reference with an event ID;
3. consumer receives the message at least once;
4. consumer looks up authoritative state and claims/revalidates the job;
5. consumer acknowledges only after the local delivery handoff is durable;
6. redelivery is safe through event receipts and job idempotency;
7. poison messages are retained with attempts and a recovery/dead-letter record;
8. replay can be bounded by event ID, time, run, or recovery decision.

The queue message should contain only the fields needed to locate and trace
work:

```text
event_id
event_type
schema_version
run_id
stage_instance_id
attempt_id
job_id
correlation_id
causation_id
created_at
```

It should not contain credentials, media bytes, unbounded provider responses,
or mutable snapshots that compete with the database.

### 9.2 Queue failure behavior

The system must remain correct when:

- publication succeeds but acknowledgement to the outbox writer is lost;
- a message is delivered multiple times;
- a message is delayed past the job's current readiness;
- a consumer crashes after claiming a job;
- the queue is unavailable while the database remains available;
- the queue reorders notifications;
- a poison message exceeds retry policy;
- an operator replays a historical event.

If the queue is unavailable, policy may pause or fall back to polling. It must
not bypass the outbox or create an untracked direct worker invocation.

## 10. Deployment and readiness model

The first remote deployment should use one versioned image with role commands:

```text
pipeline control reconcile
pipeline dispatcher run
pipeline worker cpu
pipeline worker media
pipeline worker evaluator
```

Separate images or services are justified only by measured dependency size,
GPU/runtime incompatibility, security boundary, startup cost, or reliability
isolation. The deployment platform is deferred.

### 10.1 Control-plane readiness

Before the dispatcher enables new delivery, the control plane verifies:

- database connectivity, schema version, migrations, and transaction behavior;
- outbox and inbox/replay records are accessible;
- artifact-store access, checksum operations, and reconciliation status;
- required registries, workflow definitions, and effective policy versions;
- secrets/configuration are present without logging their values;
- backup/restore and retention policy status is known;
- no unresolved migration or cutover lock blocks new work;
- monitoring and audit sinks are available at the required minimum level.

Readiness failures fail closed. The system may continue recovery or inspection
commands when safe, but it must not claim or dispatch new production work.

### 10.2 Worker readiness

A worker advertises a capability/resource class only after it verifies:

- image/build and tool versions;
- CPU/RAM/VRAM availability;
- writable temporary workspace and cleanup behavior;
- authorized artifact access;
- provider credentials and data-policy eligibility;
- capability implementation compatibility;
- clock/UTC behavior needed for lease expiry;
- logging redaction and correlation.

Worker readiness means “eligible to receive a compatible assignment.” It does
not mean a job is ready or that the worker may mutate workflow state.

Startup ordering is a convenience. Durable readiness, leases, and recovery are
the correctness mechanism. A deployment controller must not be trusted merely
because it reports all processes as running.

## 11. Resource placement and backpressure

Resource placement remains separate from capability routing. The router chooses
an eligible implementation/provider/model; the resource broker chooses an
execution placement that satisfies the workload and policy.

A remote assignment may include:

- placement class such as CPU, media, or GPU;
- required tool/image version;
- CPU/RAM/VRAM minimums;
- expected runtime and startup/model-load time;
- maximum cost and data-region constraints;
- artifact transfer limits;
- interruption tolerance;
- concurrency class and priority;
- cancellation and retry policy.

### 11.1 Backpressure signals

The control plane should observe:

- ready-job count and oldest ready age;
- per-pool running and claimed work;
- lease expiry and heartbeat failures;
- input/output transfer time and size;
- worker startup/model-load time;
- useful runtime versus waiting time;
- provider quota and rate limits;
- budget reservations and spend rate;
- retry, unknown, and regeneration rates;
- quality-review queue age.

Backpressure may pause optional work, defer a run, reduce concurrency, choose an
eligible alternate resource, or create human attention. It may not discard
durable jobs, bypass required quality, or silently exceed budget.

Autoscaling, if later justified, must scale bounded worker capacity based on
these durable signals and must be safe to scale down while leases are active.
The first capacity target should be measured from the local validation report,
not inferred from the weekly product aspiration.

## 12. Security and data policy

Remote execution increases the exposure of source snapshots, scripts, media,
credentials, and provider payloads. The expansion must preserve:

- explicit data classification before routing;
- least-privilege control-plane, worker, artifact, and provider identities;
- short-lived or scoped artifact access where supported;
- no credentials in events, artifacts, images, logs, or fingerprints;
- encryption in transit and at rest according to the selected environment;
- network egress restrictions and retrieval/SSRF protection;
- media type, size, decode, and archive-bomb limits;
- separate handling for financial, private, or restricted source material;
- provider retention/training terms recorded before eligibility;
- audit records for privileged reads, writes, publication, and deletion;
- explicit retention and deletion policies for raw provider payloads.

Unknown provider terms or unverified remote storage controls make the affected
provider/resource placement ineligible. They do not get overridden by a higher
quality score or a lower price.

## 13. Observability, cost, and operations

Remote operations must remain correlatable through the same identifiers used by
the local system:

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
worker_id
resource_assignment_id
```

Record at minimum:

- control-plane and worker readiness transitions;
- job age, delivery, claim, lease, heartbeat, and fencing outcomes;
- queue lag and outbox-to-worker delivery latency, if applicable;
- artifact upload/download latency, bytes, checksum failures, and orphan count;
- stage runtime, startup/model-load time, and useful worker runtime;
- CPU/RAM/VRAM utilization and interruption rate;
- provider operation, quota, retry, unknown, and reconciliation outcomes;
- estimated/reserved/actual cost by run, stage, capability, and resource class;
- quality outcomes, regeneration, human review, and false-pass audits;
- backup, restore, retention, deletion, and migration outcomes.

Cost accounting must include transfer, startup/model loading, idle reservation,
retries, quality evaluation, regeneration, storage, and cleanup where those
costs are material. A cheaper invocation is not an improvement if it increases
regeneration or review cost per accepted artifact.

## 14. Backup, restore, and disaster recovery

Before remote production work begins, define and test:

- metadata backup frequency and retention;
- object-storage versioning or equivalent recovery behavior;
- encryption-key backup and rotation recovery;
- artifact/database consistency checkpoints;
- restore order and validation checks;
- recovery of open leases, unknown attempts, outbox rows, and human reviews;
- publication idempotency after restoration;
- maximum acceptable data loss and recovery time for each record class;
- operator authorization for destructive cleanup.

A restore is not complete when the database starts. The restored system must
verify artifact hashes, active pointers, dependency edges, quality evidence,
budget reservations, and pending recovery decisions before dispatch is enabled.

## 15. Rollback and migration safety

Every remote promotion has a stop and rollback plan:

1. stop new claims or pause affected capability classes;
2. let safe in-flight work finish or allow leases to expire;
3. reconcile unknown provider and artifact outcomes;
4. preserve all committed metadata and immutable bytes;
5. restore or switch to the previous adapter/image/schema version if required;
6. replay only explicitly selected outbox/events/jobs;
7. rerun integrity and quality checks against exact hashes;
8. record the rollback reason, impact, and follow-up decision.

Rollback must not mutate historical artifact bytes or erase evidence. A new
implementation version or storage location creates a new versioned operation;
the old records remain inspectable.

## 16. Deferred choices

This document intentionally leaves these choices open:

- PostgreSQL provider, hosting, region, and managed versus self-operated mode;
- object-storage provider, bucket/container layout, and lifecycle mechanism;
- queue or broker technology and delivery topology;
- container/orchestrator technology;
- CPU/GPU provider and worker image distribution;
- exact autoscaling and concurrency limits;
- cross-region replication and disaster-recovery tier;
- service decomposition boundaries;
- scheduler technology and calendar policy;
- remote review UI and operator access model.

Each choice requires a benchmark, threat/risk review, migration plan, cost model,
and accepted decision before it becomes implementation authority. A technology
may be used in an experiment without becoming the canonical platform choice.

## 17. Remote expansion acceptance checklist

- [ ] Local fast-plan acceptance remains green.
- [ ] The selected migration step has a measured bottleneck or explicit risk
      reduction that justifies its added failure surface.
- [ ] Repository contracts and canonical registries remain unchanged or have a
      documented migration.
- [ ] Object bytes remain immutable and hash-verifiable.
- [ ] Metadata/object-store gaps are reconciled and auditable.
- [ ] Remote workers do not use shared-network SQLite.
- [ ] Lease ownership and fencing prevent stale commits.
- [ ] Unknown external outcomes have a reconciliation path.
- [ ] Queue delivery, if introduced, is at least once and not authoritative.
- [ ] Worker startup checks and control-plane readiness fail closed.
- [ ] Backpressure and budget controls are durable and observable.
- [ ] Secrets, data classification, provider terms, and audit requirements are
      enforced before remote execution.
- [ ] Backup, restore, retention, and deletion have been tested.
- [ ] Cost includes transfer, startup, retries, evaluation, and storage where
      material.
- [ ] Rollback preserves historical artifacts and evidence.
- [ ] The promotion, operator decision, and new version are recorded.

## 18. Related canonical documents

- [Documentation Guide](README.md)
- [Canonical Architecture](AI_Video_Pipeline_Architecture.md)
- [Decision Log](AI_Video_Pipeline_Decisions.md)
- [Contracts and Data Model](AI_Video_Pipeline_Contracts_and_Data_Model.md)
- [Workflow and Event Execution](AI_Video_Pipeline_Workflow_and_Event_Execution.md)
- [Local Infrastructure Profile](AI_Video_Pipeline_Local_Infrastructure_Profile.md)
- [Routing and Providers](AI_Video_Pipeline_Routing_and_Providers.md)
- [Fast Validation Plan](AI_Video_Pipeline_Fast_Validation_Plan.md)
- [End-to-End Implementation Plan](AI_Video_Pipeline_End_to_End_Implementation_Plan.md)
