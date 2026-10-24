# Repository guidance for coding agents

## Current repository posture

This repository is documentation-first. The canonical product and implementation
contracts are under `kb/docs/`. There is no application implementation to
preserve yet. Do not begin coding from an isolated document or from a historical
supporting note.

## Required reading order

Before proposing or implementing application changes, read:

1. `kb/docs/README.md` — canonical reading order and conflict rules;
2. `kb/docs/AI_Video_Pipeline_Architecture.md` — boundaries, vocabulary, and
   canonical stage graph;
3. `kb/docs/AI_Video_Pipeline_Decisions.md` — accepted and deferred decisions;
4. `kb/docs/AI_Video_Pipeline_Contracts_and_Data_Model.md` — typed contracts and
   durable records;
5. `kb/docs/AI_Video_Pipeline_Workflow_and_Event_Execution.md` — readiness,
   jobs, events, leases, retries, and recovery;
6. `kb/docs/AI_Video_Pipeline_Content_Model_and_Composition.md` — editorial and
   media hierarchy;
7. `kb/docs/AI_Video_Pipeline_Quality_System.md` — checks, gates, evaluation,
   escalation, and repair;
8. `kb/docs/AI_Video_Pipeline_Domain_Profiles.md` — domain/channel policy;
9. `kb/docs/AI_Video_Pipeline_Routing_and_Providers.md` — capabilities,
   providers, budgets, and placement;
10. `kb/docs/AI_Video_Pipeline_Fast_Validation_Plan.md` — first implementation
    scope and acceptance criteria;
11. `kb/docs/AI_Video_Pipeline_End_to_End_Implementation_Plan.md` — later
    evolution only after fast-validation evidence.

For remote-infrastructure design or implementation, also read
`kb/docs/AI_Video_Pipeline_Remote_Infrastructure_Expansion.md`. It is a
deferred target document, not a prerequisite for the local fast slice.

For local-infrastructure implementation, also read
`kb/docs/AI_Video_Pipeline_Local_Infrastructure_Profile.md`. It is the current
fast-slice runtime, storage, readiness, and recovery baseline.

The machine-readable registries under `kb/docs/registries/` are normative for
stage names, event names, failure codes, and the fast workflow fixtures. The
Markdown documents explain the decisions and constraints around those files.

## Conflict-resolution rules

When documents disagree, apply this order:

1. a newer accepted ADR in `AI_Video_Pipeline_Decisions.md`;
2. the canonical focused document linked by `AI_Video_Pipeline_Architecture.md`;
3. the corresponding machine-readable registry or fixture;
4. the parent architecture;
5. a historical supporting note, which is never an implementation authority.

Do not silently choose between incompatible terms. Record a required change in
the decision log and update the affected registry and canonical documents
together.

## Implementation constraints

- Preserve the modular-monolith-first decision.
- Keep workflow transitions, quality gates, budgets, and recovery in durable
  control-plane logic; capabilities may not mutate them directly.
- Stages request capabilities and must not import provider SDKs directly.
- Treat artifacts as immutable. Replacement creates a new version and explicit
  descendant invalidation.
- Use the explicit execution/acceptance split. Execution success is not quality
  acceptance, human approval, or publication readiness.
- Assume at-least-once event delivery and ambiguous external outcomes.
- Never silently spend money, bypass a required gate, or publish without the
  effective policy's human approval.
- Prefer deterministic validators before semantic model judgments.

## Documentation changes

Documentation changes must update all affected canonical documents, registries,
and ADR references in one change. Historical notes may be corrected only to add
an explicit non-normative banner or a pointer to the canonical replacement.
The active rationale and change history is
`kb/docs/AI_Video_Pipeline_Design_Discussion_Log.md`; architecture and contract
changes must add a dated entry there when they change an accepted decision or
implementation direction.

Before implementation begins, the documentation-only validation should pass:

```bash
python3 scripts/validate_docs.py
```

The validator runs these checks uniformly: balanced Markdown fences, valid YAML
in `kb/docs/registries/`, valid fenced Python examples, canonical
registry/reference consistency, internal Markdown links, and both working-tree
and staged `git diff --check` whitespace validation. It is read-only and does
not execute documented Python examples or contact external URLs.

Do not report a check as passing unless it was actually run.
