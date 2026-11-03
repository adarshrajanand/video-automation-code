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

`FAQ.md` and `TODO_POST_REVIEW.md` are durable review artifacts, not scratch
notes. Apply these rules whenever adding or editing them.

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
- Link follow-up work as `PR5-NN` or `GEN-NN`; every ID must exist in
  `TODO_POST_REVIEW.md`.
- Never delete a question silently. Mark it superseded and link the replacement.
- Use “samples” in user-facing prose; use exact code identifiers when quoting
  code.
- Keep the Contents list and the decision summary current when adding a review
  or changing a decision.

### TODO (`TODO_POST_REVIEW.md`)

- One item per independently shippable concern. Merge duplicates; do not keep
  two entries for the same work.
- IDs: `PR5-NN` for PR #5 review items, `GEN-NN` for carried-over FV-11 items.
  IDs are stable; never renumber or reuse.
- Priority: `P0` blocking, `P1` next design/behavior, `P2` normal documentation
  and hardening, `P3` opportunistic or scale-dependent.
- Type tag: one primary tag, `[code]`, `[docs]`, `[test]`, `[ops]`, `[build]`,
  or `[design]`. Secondary work stays in `Work`.
- Every item has `Context`, `Work`, `Acceptance`, and `Files/References`.
- Put the highest priority first. Update the index table when adding or moving
  an item.
- Reference other items by ID, never by position or line number.
- When work lands: check the box, add the PR/commit, and move the item to
  `Completed`. When an item is dropped, move it to `Merged or dropped` with the
  reason.
