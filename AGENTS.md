# Agent instructions

The canonical agent guidance for this repository lives in `docs/AGENTS.md`
(that directory is a separate repository with its own version control).

Before proposing or implementing any change, read and follow
`docs/AGENTS.md` in full. In particular, apply its:

- required reading order for `docs/kb/docs/`;
- conflict-resolution rules;
- implementation constraints;
- documentation-change rules.

Note for implementation work: local infrastructure is the current baseline
(`docs/kb/docs/AI_Video_Pipeline_Local_Infrastructure_Profile.md`);
remote infrastructure is a deferred target.

Commits are made from this repository (`video-automation-code`) only.
Never commit inside `docs/` — it is a separate repository.

## Review artifact conventions

`FAQ.md` is a durable review artifact, not scratch notes. Follow-up work is
tracked as GitHub issues, not in a checked-in TODO file. Apply these rules
whenever adding or editing review material.

### FAQ (`FAQ.md`)

- Use one `#` title and one `##` section per review (for example `PR #1
  Review`, `PR #5 Review`).
- Group questions by topic, never by comment order, source file, or line
  number. Use `###` for topic groups and `####` for questions.
- Write every question as `#### **Q: <question>?**`, followed by a blank line
  and `**A:** ...`.
- Start with the direct answer, then add evidence, examples, tradeoffs, and
  links. Use fenced code blocks with a language.
- End every answer with `**Source:** ...` naming the review, document, line,
  and comment ID, or the follow-up ID. If every answer in a section shares one
  source, a single `**Source:**` line under the section heading is enough.
  Source lines provide traceability; they are not headings.
- Keep related questions together. When a follow-up expands an existing answer,
  place it in the same topic and keep its `F` label in the Source line.
- Link follow-up work as `PR5-NN` or `GEN-NN`; every ID must match a GitHub
  issue title.
- Never delete a question silently. Mark it superseded and link the replacement.
- Use “samples” in user-facing prose; use exact code identifiers when quoting
  code.
- Keep the Contents list and the decision summary current when adding a review
  or changing a decision.

### Issue severity and priority

Every issue has exactly one severity and one priority. They answer different
questions and must not be inferred from each other.

**Severity** — impact if the issue is left unfixed:

- `S1` Critical: data loss or corruption, duplicate spend, unauthorized
  publication, security or privacy exposure, or a pipeline that cannot execute.
- `S2` High: a core path is broken or produces incorrect durable state,
  artifacts, IDs, timestamps, gates, or replay behavior.
- `S3` Medium: degraded behavior, or a contract, documentation, test, or
  maintainability gap that risks a wrong implementation.
- `S4` Low: cosmetic, naming, or explanatory documentation with no behavioral
  impact.

**Priority** — when to fix it:

- `P0` Now: blocks the active slice or an in-progress release gate.
- `P1` Next: required for current milestone acceptance, after `P0`.
- `P2` Planned: current or next milestone hardening; not gate-blocking.
- `P3` Deferred: optional, opportunistic, or later-milestone work.

Rules:

- Title: `PR5-NN [S2][P1][code] Short title`.
- Put `**Severity:** S2` and `**Priority:** P1` at the top of the issue body,
  before `Context`.
- Use exactly one severity label and one priority label.
- Priority is sequencing, not impact. An `S3` may be `P0` when it blocks
  verification; an `S1` may be `P3` only while the risky capability is disabled
  and the issue records that mitigation.
- Reassess both when the issue is picked up, deferred, or the active milestone
  changes.
- `starter-slice` is a scope label, not a priority.

### Review issues

- One issue per independently shippable concern. Merge duplicates; do not file
  two issues for the same work.
- IDs: `PR5-NN` for PR #5 review items, `GEN-NN` for carried-over FV-11 items.
  IDs are stable; never renumber or reuse.
- Title: `PR5-NN [S2][P1][code] Short title`.
- Severity and priority: one of each, as defined in “Issue severity and
  priority”.
- Type tag: one primary tag, `[code]`, `[docs]`, `[test]`, `[ops]`, `[build]`,
  or `[design]`. Secondary work stays in `Work`.
- Every issue body has `Context`, `Work`, `Acceptance`, and `Files/References`,
  preceded by the severity, priority, and type header.
- Reference other items by ID, never by position or line number.
- When work lands: close the issue with the PR/commit. When an item is dropped,
  close it as not planned with the reason.
