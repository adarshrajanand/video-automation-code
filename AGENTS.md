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

## Non-negotiable boundaries

- The [Local Infrastructure Profile](docs/kb/docs/AI_Video_Pipeline_Local_Infrastructure_Profile.md)
  is the implementation baseline; remote infrastructure is deferred.
- `docs/` is a separate repository. Make commits from `video-automation-code`
  only; never commit inside `docs/`.
- Preserve unrelated user changes and runtime state. Do not edit applied
  migrations; add a new migration when required.
- Do not merge PRs or close issues without explicit user approval. Passing
  checks or an instruction to “continue” is not merge authorization.
