# Contributor workflow

Use the active tracker, priority, and dependencies to choose work. GitHub owns
the current backlog and completion state; this guide is not a second TODO list.
Canonical product/implementation authority remains in [docs/AGENTS.md](docs/AGENTS.md)
and the documents it requires. This guide does not override that authority.

## Start now

The current execution-spine tracker is
[M1-00 (#85)](https://github.com/adarshrajanand/video-automation-code/issues/85).
Confirm its live checklist before choosing work. Its recommended next change is
[PR5-02 (#9)](https://github.com/adarshrajanand/video-automation-code/issues/9),
alongside [PR5-07 (#14)](https://github.com/adarshrajanand/video-automation-code/issues/14)
if practical. Both are independently unblocked; they can share a small
persistence-focused PR without a dependency edge between them.

1. Read [AGENTS.md](AGENTS.md) and `docs/AGENTS.md` in full. Follow the required
   canonical reading order and use [the documentation index](docs/kb/docs/README.md)
   to locate focused contracts and normative registries.
2. Read both issues' Dependencies, Work, Implementation notes, Acceptance, and
   Verification checklist. Confirm scope and expected evidence before editing.
3. Check `git status` and start a fresh branch from current `main`, preserving
   unrelated work. Keep runtime/test state in an isolated external `PIPELINE_HOME`;
   never reuse or delete another worktree's live database.
4. Add failing regressions first: PR5-02 compares raw SQL projections with the
   stored payload, not just repository round-trips. PR5-07 proves chronological
   text ordering across serializers, including zero/nonzero microseconds.
5. Implement only that scope, run verification, and prepare a PR for review.
   Leave optional table/field renames and package refactors out.

Suggested request to an agent:

> Implement PR5-02 (#9) and PR5-07 (#14) following M1-00 (#85). Read the repository
> guidance and canonical documents first. Add failing regressions, implement
> only the issues' scope, and run their verification checklists. Open a PR using
> the repository template, including the consequence of not merging and concrete
> examples. Leave it open for review; do not merge or close issues without approval.

## Choose work in future

**Pick the highest-priority unblocked issue in the active scope.** Do not treat
the entire open-issue list as an ordered queue, or jump to a later milestone
merely because its work looks easy.

| Question | Look at |
|---|---|
| What are we trying to finish? | Active milestone and its tracker |
| What matters most now? | Priority, then the tracker's recommended order |
| Can it proceed? | Dependencies / native GitHub “blocked by” links |
| What will it unlock? | “Blocks” / native GitHub “blocking” links |
| What needs coordination? | “Coordinate with”; no extra hard dependency |
| What exactly should change? | Work and Implementation notes |
| What proves completion? | Acceptance and Verification checklist |
| Which contracts govern it? | `docs/AGENTS.md`, canonical docs, registries |
| How should it be reviewed? | [PR template](.github/pull_request_template.md) |

When several issues qualify, follow the tracker order, then prefer work that
unlocks the next required deliverable. Combine only small, coherent changes.
Preparation/tests may start before a prerequisite closes, but do not claim
completion while required inputs or behavior are missing. If requirements
conflict, resolve them before implementation rather than silently weakening
acceptance.

Suggested future request:

> Pick the next highest-priority unblocked issue from the active tracker. Explain
> why it is next, confirm dependencies and scope, then implement it and open a PR
> using the template. Do not merge without explicit approval.

## Issue priority

Every issue has exactly one priority label. Priority is the single measure of
importance: how much the work matters now. Do not add a separate severity axis.

| Priority | Meaning |
|---|---|
| `P0` Critical / now | Blocks the active slice/release gate, or is a critical correctness, safety, or data-integrity defect in an enabled path. Fix first. |
| `P1` High / next | Required for current milestone acceptance; schedule after P0. |
| `P2` Medium / planned | Meaningful current/next milestone hardening, contract, docs, or test work; not gate-blocking. |
| `P3` Low / deferred | Optional, cosmetic, or later-milestone work. |

Keep the title, body header, and label consistent. Reassess priority when work
is picked up, deferred, or the active milestone changes; record the rationale.
`starter-slice` is a scope label, not another importance measure.

## Issue format and dependencies

- One issue per independently shippable concern. Merge duplicates rather than
  filing the same work twice.
- Preserve IDs: `PR5-NN` for PR #5 review items, `GEN-NN` for carried-over FV-11
  items, and existing roadmap IDs. Never renumber or reuse them.
- Title: `PR5-NN [P0][code] Short title`. Use one primary type tag: `[code]`,
  `[docs]`, `[test]`, `[ops]`, `[build]`, or `[design]`; secondary work stays in Work.
- Start the body with `**Priority:** P0` and the type. Include Context, Work,
  Acceptance, and Files/References; add impact/examples, implementation notes,
  verification cases, and dependencies where needed to make it actionable.
- Reference other items by stable ID and issue link/number, not their position
  in a list or a mutable line number.

Dependencies must distinguish:

- **Blocked by:** required predecessors. Closed, completed prerequisites count
  as satisfied; a “not planned” closure is not proof the required behavior exists.
- **Blocks:** direct dependent issues. GitHub supplies the reverse relationship
  when a blocked-by link is added; do not create a reciprocal blocking edge.
- **Coordinate with:** shared interfaces, file overlap, or co-delivery. These
  links do not introduce hard sequencing requirements.
- **Conditional gates:** approval, live-provider safety, semantic-evaluation
  evidence, or remote promotion. Closing an issue does not grant permission to
  spend money, bypass policy, or publish.

Keep native GitHub dependencies and their explanations consistent and acyclic.
Do not turn optional renames, refactors, diagrams, containers, or queues into
prerequisites for unrelated work.

## Implement and verify

Use this loop: **failing test → focused implementation → verification → PR →
human review → approved merge → tracker update**. For documentation-only work,
reproduce the documentation gap and validate the changed links/examples instead
of manufacturing an unrelated failing application test.

Follow the issue's specific checklist first. Typical Python checks are:

```bash
uv run pytest -q
uv run ruff check .
```

Check formatting on changed files. For contract/schema changes, also run:

```bash
uv run python -m pipeline contracts export-schemas --check
```

For canonical documentation, run this **from `docs/`**:

```bash
uv run --project .. python scripts/validate_docs.py
```

Run focused tests before the full suite, using isolated sample state. Add new
migrations instead of editing applied ones. Update affected canonical docs,
registries, ADRs, and generated references under their change protocol.
Record exact commands/results, known gaps, and pre-existing failures. Never
claim a check passed unless it actually ran, or weaken tests to hide a failure.

## PR review and completion

Every PR description must fill all sections of
[`.github/pull_request_template.md`](.github/pull_request_template.md). Keep it
concise enough to explain purpose, scope, consequences, evidence, and risks
without reading the diff first. Include at least one concrete example: a failing
command, before/after behavior, or a real scenario. Do not paste commit logs or
restate the diff line by line.

Leave the PR open for review. Address important defects; when a comment belongs
to already planned work, explain the boundary and link the owning issue rather
than silently expanding scope. **Green checks and “continue” are not merge
authorization. Do not merge PRs or close issues without explicit user approval.**

After an approved merge, link the landed PR/commit, close satisfied issues, and
update the tracker. When approved work is dropped, close it as not planned with
the reason; resolve dependent requirements rather than pretending they were
implemented. Follow [review guidelines](REVIEW_GUIDELINES.md) when updating FAQ
or review artifacts. Do not maintain a checked-in follow-up TODO file.
