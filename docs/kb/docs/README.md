# AI Video Automation Pipeline — Documentation Guide

**Status:** Canonical documentation index

This repository is intentionally documentation-first. The documents describe a
small, local, deterministic control plane with bounded probabilistic
capabilities. They are not a request to build the eventual distributed system
before the local vertical slice proves its assumptions.

## Canonical reading order

### 1. Orientation and decisions

1. [Canonical Architecture](AI_Video_Pipeline_Architecture.md)
2. [Decision Log](AI_Video_Pipeline_Decisions.md)
3. [Design Discussion Log](AI_Video_Pipeline_Design_Discussion_Log.md)

The architecture defines the shared vocabulary and boundaries. The decision log
is normative when it contains an accepted ADR. The discussion log explains why
the decisions were made but does not override an ADR.

### 2. Contracts and execution

4. [Contracts and Data Model](AI_Video_Pipeline_Contracts_and_Data_Model.md)
5. [Workflow and Event Execution](AI_Video_Pipeline_Workflow_and_Event_Execution.md)
6. [Routing and Providers](AI_Video_Pipeline_Routing_and_Providers.md)
7. [Local Infrastructure Profile](AI_Video_Pipeline_Local_Infrastructure_Profile.md)

Read these before designing a repository, worker, provider adapter, or event
consumer. The contracts document defines durable identity and state; the
workflow document defines when transitions are allowed; routing is a separate
decision from readiness and resource placement; the local profile defines the
first runtime and storage topology without selecting remote infrastructure. The
remote expansion document defines deferred target evolution and is not current
implementation scope.

### 3. Media and quality

8. [Content Model and Composition](AI_Video_Pipeline_Content_Model_and_Composition.md)
9. [Quality System](AI_Video_Pipeline_Quality_System.md)
10. [Domain Profiles](AI_Video_Pipeline_Domain_Profiles.md)
11. [Agent and Model Use](AI_Video_Pipeline_Agent_and_Model_Use.md)

These documents define media ownership, timing, provenance, quality evidence,
domain risk, and the permitted role of model-backed capabilities.

### 4. Implementation scope

12. [Fast Validation Plan](AI_Video_Pipeline_Fast_Validation_Plan.md)
13. [End-to-End Implementation Plan](AI_Video_Pipeline_End_to_End_Implementation_Plan.md)
14. [Remote Infrastructure Expansion](AI_Video_Pipeline_Remote_Infrastructure_Expansion.md)

The fast plan is the only immediate implementation scope. The end-to-end plan
and remote expansion document describe later evolution and must not be treated
as a list of prerequisites for the first code change. The remote expansion
document is the target-infrastructure reference only after the promotion gates
in ADR-024 pass.

## Normative registries and fixtures

The following files are machine-readable normative inputs for the first slice:

- `registries/stages.yaml` — canonical stage IDs, names, boundaries, and aliases;
- `registries/events.yaml` — canonical event names and payload roles;
- `registries/failure_codes.yaml` — namespaced failure codes and default actions;
- `registries/fast_workflow.yaml` — the validated fast workflow graph;
- `registries/quality_gates.yaml` — fast-slice checks and gate policies;
- `registries/recovery.yaml` — fast-slice retry and recovery policy.

If a Markdown example differs from a registry, the registry is authoritative and
the discrepancy must be fixed rather than worked around in code.

## Canonical terminology

- `StageInstance` is logical work for one node and logical item.
- `StageAttempt` is one execution attempt for that stage instance.
- `Job` is a claimable execution work record associated with an attempt.
- `execution_status` records whether execution ran successfully.
- `acceptance_status` records whether required quality acceptance passed.
- `quality_accepted`, `human_approved`, and `publication_ready` are distinct.
- `SourceAsset` is reusable obtained/generated media; `AssetInstance` is its
  placement; `Artifact` is the immutable stored bytes or structured payload.
- `EventEnvelope` is the serialized event; `OutboxMessage` is its delivery record.
- `QualityEvaluation` records one check outcome; `QualityGateResult` records the
  aggregate workflow decision.

## Historical supporting notes

Superseded design notes are kept in the
[non-normative archive](archive/README.md). They preserve useful reasoning but
are not implementation authorities and are not required reading for a coding
agent. They may contain older names such as `StageExecution`, `tts`, `assemble`,
or PascalCase event names. Use the canonical documents and registries instead.

## Change protocol

When changing a contract, stage, event, policy, or durable state:

1. identify the affected ADR and canonical documents;
2. update the relevant registry or fixture;
3. state whether the change is backward-compatible or requires migration;
4. update examples and acceptance criteria;
5. add a decision-log entry for a new or changed architectural decision;
6. run the documentation validation listed in `AGENTS.md`.

No application code should be written against an unresolved contradiction.

## Documentation validation

The repository keeps the documentation checks in a single executable validator
so that local development and later automation use the same rules. From the
repository root, run:

```bash
python3 scripts/validate_docs.py
```

The validator checks Markdown fences, fenced Python syntax, YAML parsing and
cross-registry references, internal Markdown links, and working-tree/staged
Git diff whitespace. It is read-only: documented Python is parsed but never
executed, and external links are not fetched. PyYAML is required for the YAML
checks:

```bash
python3 -m pip install -r requirements-docs.txt
```
