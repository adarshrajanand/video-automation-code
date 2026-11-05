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

## Non-negotiable boundaries

- The [Local Infrastructure Profile](docs/kb/docs/AI_Video_Pipeline_Local_Infrastructure_Profile.md)
  is the implementation baseline; remote infrastructure is deferred.
- `docs/` is a separate repository. Make commits from `video-automation-code`
  only; never commit inside `docs/`.
- Preserve unrelated user changes and runtime state. Do not edit applied
  migrations; add a new migration when required.
- Do not merge PRs or close issues without explicit user approval. Passing
  checks or an instruction to “continue” is not merge authorization.
