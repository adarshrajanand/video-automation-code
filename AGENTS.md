# Agent instructions

## Read before working

- Read [docs/AGENTS.md](docs/AGENTS.md) in full before proposing or implementing
  any change. Follow its canonical reading order, conflict rules, implementation
  constraints, and documentation-change protocol.
- Use [CONTRIBUTING.md](CONTRIBUTING.md) for selecting work, issue priorities and
  dependencies, implementation/verification, and PR preparation. Read the
  relevant sections before those activities.
- When adding or editing review material, follow
  [REVIEW_GUIDELINES.md](REVIEW_GUIDELINES.md). `FAQ.md` is a durable review
  artifact; follow-up work belongs in GitHub issues, not a checked-in TODO file.

## Review-comment responses

Answer review comments one at a time, in the order requested. For each comment:

1. Name the location (`path:line`).
2. Quote the relevant code or show a short surrounding-context block.
3. Give a direct answer, then the supporting explanation.

Use concrete examples, dry runs, or before/after values when the behavior is not
obvious. If the answer is only an explanation, say so and do not change code
unless asked. This format applies to chat and inline PR replies;
[REVIEW_GUIDELINES.md](REVIEW_GUIDELINES.md) still governs durable `FAQ.md`
entries.

## Code comments and explainability

Write comments for the reader who has the code but not the conversation that
produced it. A recurring review finding is that behavior is correct but the
reasoning is invisible. Treat missing explanation as a defect, not polish.

Add a comment when the code encodes:

- a non-obvious decision, invariant, or tradeoff (“why”, not “what”);
- a boundary or ownership rule, such as which layer is authoritative;
- a workaround, SQLite/SQL behavior, or ordering constraint;
- a migration/checksum/revert rule someone must follow later;
- a test whose purpose is not obvious from its name, including the regression it
  guards against.

Prefer a short module docstring plus targeted inline comments over narrating
each line. Do not restate the code. Keep comments next to the code they explain
and update them in the same commit as the behavior. When a review answer contains
durable knowledge, move the reusable part into a code comment or docstring and
the review-specific part into `FAQ.md`.

## Non-negotiable boundaries

- The [Local Infrastructure Profile](docs/kb/docs/AI_Video_Pipeline_Local_Infrastructure_Profile.md)
  is the implementation baseline; remote infrastructure is deferred.
- `docs/` is a separate repository. Make commits from `video-automation-code`
  only; never commit inside `docs/`.
- Preserve unrelated user changes and runtime state. Do not edit applied
  migrations; add a new migration when required.
- Do not merge PRs or close issues without explicit user approval. Passing
  checks or an instruction to “continue” is not merge authorization.
