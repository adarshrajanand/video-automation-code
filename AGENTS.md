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

### Issue priority

Every issue has exactly one priority label. Priority is the single measure of
importance: how much the work matters now. Do not add a separate severity axis.

- `P0` Critical / now: blocks the active slice or release gate, or is a critical
  correctness, safety, or data-integrity defect in an enabled path. Fix before
  anything else.
- `P1` High / next: required for current milestone acceptance. Schedule
  immediately after `P0`.
- `P2` Medium / planned: meaningful hardening, contract, documentation, or test
  work for the current or next milestone. Not gate-blocking.
- `P3` Low / deferred: optional, cosmetic, or later-milestone work.

Rules:

- Title: `PR5-NN [P0][code] Short title`.
- Put `**Priority:** P0` at the top of the issue body, before `Context`.
- Use exactly one priority label.
- Reassess priority when the issue is picked up, deferred, or the active
  milestone changes.
- `starter-slice` is a scope label, not a priority.

### Review issues

- One issue per independently shippable concern. Merge duplicates; do not file
  two issues for the same work.
- IDs: `PR5-NN` for PR #5 review items, `GEN-NN` for carried-over FV-11 items.
  IDs are stable; never renumber or reuse.
- Title: `PR5-NN [P0][code] Short title`.
- Priority: exactly one label, as defined in “Issue priority”.
- Type tag: one primary tag, `[code]`, `[docs]`, `[test]`, `[ops]`, `[build]`,
  or `[design]`. Secondary work stays in `Work`.
- Every issue body has `Context`, `Work`, `Acceptance`, and `Files/References`,
  preceded by the priority header.
- Reference other items by ID, never by position or line number.
- When work lands: close the issue with the PR/commit. When an item is dropped,
  close it as not planned with the reason.

## Pull requests

Every pull request description must follow `.github/pull_request_template.md`.
Fill all five sections — Summary, Why, Changes, Verification, and Risk — with a
short, direct explanation. The goal is that a reviewer understands the purpose,
scope, and evidence without reading the diff first. Do not paste commit logs or
restate the diff line by line.
