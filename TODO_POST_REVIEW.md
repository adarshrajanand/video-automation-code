# Post-Review TODO List

## PR #5 Review Follow-ups (open PR)

> From the 81 comments on PR #5 (`docs/request-flow-atlas`). Answers are in
> `FAQ.md` under “PR #5 Review”. No fixes were made to the code or to the
> reviewed documents in response to the review.

### P0 — Correctness (PR #5)

- [ ] **PR5-01 [code] Fix `CONTRACT_FIELD_ATLAS.md` generator rendering**
  - Enum classes render as `<enum 'FailureCode`; render the enum class name.
  - Escape `|` inside type cells so Markdown does not shift Required/Default.
  - Render `default_factory` defaults instead of `PydanticUndefined`.
  - Add tests for enums, unions, and `default_factory`; regenerate the atlas.
  - Files: `scripts/generate_contract_atlas.py`, atlas generator tests.

- [ ] **PR5-02 [code] Fix `IdempotencyRecordRepository` projection drift**
  - Add `operation_version`, `input_artifact_ids`, `required_features`,
    `locale`, and `result_artifact_ids` to `columns`.
  - Teach `SqliteRepository._column_value()` to JSON-encode list values.
  - Backfill or validate existing rows from `payload`; add round-trip tests.
  - Files: `src/pipeline/storage/repositories/control.py`,
    `src/pipeline/storage/repositories/base.py`, storage tests.

- [ ] **PR5-03 [code] Fix `stage_` ID collisions and add a stage creator**
  - Include `logical_item_key` in `deterministic_id("stage", ...)`.
  - Add the production stage-instance creation path; rely on the
    `(run_id, node_id, logical_item_key)` unique constraint for idempotency.
  - Update golden-path examples and add a multi-item regression test.
  - Files: `src/pipeline/ids.py`, workflow/execution creation code, tests.

- [ ] **PR5-04 [code] Remove double prefixes from `eval_`, `qgr_`, `repair_`**
  - Use the value returned by `deterministic_id()` directly; do not prepend the
    prefix again.
  - Normalize the random evaluator IDs to one `eval_` prefix as well.
  - Update tests, fixtures, and documented example IDs; add regression tests.
  - Files: `src/pipeline/quality/evaluators.py`, `gate.py`, `repair.py`,
    `semantic.py`, `media.py`, `speech.py`, tests.

- [ ] **PR5-05 [code] Fix `quality evaluate`**
  - Apply migrations (or require an explicit migrated database) before
    querying quality tables.
  - Make a repeated identical evaluation idempotent or fail with a clear,
    documented conflict instead of `ConflictError`.
  - Define and test exit codes, including `REGENERATE`.
  - Files: `src/pipeline/cli.py`, quality pipeline, CLI integration tests.

- [ ] **PR5-06 [code] Fix `human-review list` and `show`**
  - Implement/export `cli_human_review_list` and `cli_human_review_show`, or
    change the CLI to existing APIs.
  - Add CLI tests for `list`, `show`, `decide`, and the `review` alias.
  - Files: `src/pipeline/quality/human_review.py`, `src/pipeline/cli.py`,
    tests.

- [ ] **PR5-07 [code] Canonicalize persisted timestamps**
  - Emit one UTC representation (`Z`) from every persistence path.
  - Add cross-path ordering tests; backfill existing rows if needed.
  - Files: `src/pipeline/fingerprints.py`, `src/pipeline/contracts/base.py`,
    storage tests.

- [ ] **PR5-08 [code] Make `capabilities list` read-only**
  - Remove `_migrated_database()` from the command; do not create or migrate a
    database for a registry listing.
  - Add a test that a fresh/nonexistent database is untouched.
  - File: `src/pipeline/cli.py`.

### P1 — Design and behavior (PR #5)

- [ ] **PR5-09 [code] Decide outbox delivery semantics for multiple consumers**
  - Current ack is global; a new consumer does not receive already-delivered
    events.
  - Either add per-consumer cursors/delivery rows/backfill, or document
    future-only semantics and forbid assuming replay.
  - Record the decision in an ADR; update dispatcher/inbox tests.

- [ ] **PR5-10 [code] Load quality gate policy and calibrate thresholds**
  - Load `QualityGatePolicy` from `quality_gate_policies` instead of
    hardcoding one in `cli.py`.
  - Use `ThresholdRegistry` records for pass/review thresholds.
  - Record calibration data/rationale for 0.8/0.65 in an ADR.
  - Add tests for policy loading and threshold decisions.

- [ ] **PR5-11 [docs] Write the ID derivation contract**
  - Document the formulas, shared-digest intent, prefix lookup, and why IDs are
    opaque.
  - Decide whether to include an entity type/formula version in digests.
  - Add an ADR and link it from REQUEST_FLOW §8.4.

- [ ] **PR5-12 [code] Rename `logical_slot` to `artifact_key`**
  - Decision: `artifact_key` is the stable editorial artifact identity within
    a run; it is not a content-only slot.
  - Add a new migration (do not edit `0001_initial.sql`) that renames
    `artifacts.logical_slot` and `artifact_pointers.logical_slot`, and
    recreates the affected indexes/partial unique index with `artifact_key`
    names.
  - Update `Artifact`/`ArtifactPointer`, repositories, method names, raw SQL,
    atlas/docs examples, and golden fixtures.
  - Do not rename `stage_instances.logical_item_key` or
    `quality_evaluations.logical_item_key`; those are stage item keys.
  - Add an ADR for the term and verify with `PRAGMA table_info`/`index_list`.

- [ ] **PR5-13 [code] Implement run-overrides resolution**
  - Resolve system/domain/channel defaults plus `RunOverrides` under
    `SystemPolicy` bounds.
  - Populate `resolved_values`, `source_map`, and `config_hash`; persist the
    immutable snapshot.
  - Add tests for allowed/forbidden overrides.

- [ ] **PR5-14 [docs/code] Reconcile failure-action vocabularies**
  - `FailureAction` lives in `execution/retry.py`; `RecoveryAction`,
    `QualityFailureAction`, and `RepeatedFailureAction` are in
    `contracts/vocabularies.py`.
  - Fix the §6.13 catalogue: `PAUSE` and `DEFER` are not actual action values.
  - Add a consistency test between the catalogue and the enums.

- [ ] **PR5-15 [docs/code] Map artifact types to repair scopes**
  - Document how script/content artifacts are repaired (stage regeneration,
    invalidation scope, descendant invalidation).
  - Add a table for artifact type → checks → allowed `RepairScope`.
  - Implement missing repair/invalidation execution where required.

- [ ] **PR5-16 [code] Persist readiness and stage creation end to end**
  - Readiness computes `next_status` but does not write it; add the caller that
    persists it.
  - Add the stage-instance/attempt/job creation flow for all cardinality modes.
  - Add integration tests for one-to-one, one-to-many, and many-to-one.

### P2 — Documentation (PR #5)

- [ ] **PR5-17 [docs] Fix factual errors in `REQUEST_FLOW.md`**
  - “Three ways” lists seven destinations; rename the heading.
  - “PURE WORKFLOW” is a layer, not a plane.
  - Replace `latency_budget_ms` with `latency_requirement` (or remove it).
  - Correct the §6.13 default-action values.
  - Correct the claim that every `eval_` path is double-prefixed.
  - Clarify `short_derivative` with `one_to_many` and `count: 1`.

- [ ] **PR5-18 [docs] Expand `REQUEST_FLOW.md` explanations**
  - Prefix lookup (no if/else dispatch), derivation coupling, shared digests,
    and deterministic IDs vs UUIDs, including concrete replay/dedupe examples.
  - Why migrations exist, `schema_migrations` ledger rows, failure modes, and
    the PRAGMAs.
  - `CHECK`, `ABSTAIN`, `after_max_regenerations`, and `RepairPlan`.
  - Why `idempotency_records` exists despite table idempotency; payload-size
    tradeoff; consumer/global-ack limitation; the capability-scoped table name.
  - Queue names, `RunOverrides` ownership, and the policy shapes that build
    `EffectiveConfig`; what `policy_ids` does and does not do today.
  - Separate `CapabilityRequest`, `ExecutionContext`, `EffectiveConfig`, and
    `ReadinessContext` explicitly, with the “does it change the result?” test.
  - Explain update-in-place vs append (current truth vs historical fact vs
    immutable identity), and mutating transitions/fencing with a stale-worker
    example.

- [ ] **PR5-19 [docs] Move extension recipes into `docs/AGENTS.md`**
  - Add the “add a stage/check/gate/capability” recipes to the docs repository
    guidance, with links from `REQUEST_FLOW.md`.

- [ ] **PR5-20 [docs] Make recorded fixtures reproducible**
  - Add a checked-in script or command transcript that recreates
    `/tmp/opencode/pipeline-demo` and `/tmp/opencode/quality-demo`.
  - Label golden-path IDs vs recorded-demo IDs consistently.

- [ ] **PR5-21 [code] Rename `idempotency_records` for its capability scope**
  - The table is written only by `CapabilityExecutor` and stores
    capability-specific columns (`capability`, `operation_version`,
    `capability_execution_id`, provider invocation/operation IDs).
  - Add a migration renaming it to `capability_idempotency_records` (or a
    clearly capability-scoped name); recreate the status/execution indexes
    with matching names.
  - Update `IdempotencyRecordRepository.table`, raw SQL, tests, atlas/docs, and
    any recorded fixtures. Keep the PK column `idempotency_key`; within this
    table it is the capability idempotency key.
  - Do not reuse this table for job/outbox/repair idempotency.

- [ ] **PR5-22 [docs/code] Resolve `policy_ids`**
  - Today `WorkflowDefinition.policy_ids` is only duplicate-validated; the
    runtime loader does not resolve it against a registry, and readiness /
    execution do not consume it.
  - `StageNode.recovery_policy_id` is registry-validated but execution still
    uses the default recovery policy. Docs validation and runtime validation
    disagree.
  - Decide: implement workflow-level policy resolution (fail fast on unknown
    IDs, define node-level override precedence, snapshot resolved IDs/versions
    in `EffectiveConfig`) or remove `policy_ids` and require node-level policy
    references.
  - Add tests for unknown policy IDs and precedence; update §2.2 examples.

- [ ] **PR5-23 [code] Fingerprint the full semantic request**
  - `payload_fingerprint` currently covers only `request.payload`. The executor
    manually compares `capability`, `operation_version`, `input_artifact_ids`,
    `required_features`, and `locale`, but not `quality_requirement`,
    `latency_requirement`, `data_classification`, `cost_limit_minor`, or
    `payload_schema_version`.
  - Define one canonical semantic-request object containing every field that
    can affect the result or the permission to run; exclude execution context
    (`run_id`, `stage_instance_id`, `attempt_id`, `correlation_id`,
    `effective_config_id`, `timeout_seconds`, `allowed_data_classification`).
  - Use it for the idempotency fingerprint and replay comparison. Add
    mismatch tests (for example, same key with a different cost limit or
    quality requirement).
  - Decide whether `CapabilityRequest.runtime_context` is semantic; if yes,
    move it into `payload`/the fingerprint, otherwise remove it.

- [ ] **PR5-24 [code] Provider-side idempotency and reconciliation**
  - A database unique key prevents duplicate rows, not duplicate external
    side effects. A crash after the provider succeeds but before the result is
    persisted can still lead to a second charge/asset on retry.
  - Pass a provider idempotency key derived from the capability idempotency
    key; persist the provider operation ID; on `UNKNOWN`, query the provider
    by operation ID before any retry.
  - Do not retry `UNKNOWN` outcomes blindly; make `FAILED` after a possible
    side effect reconcilable too.
  - Add fake-provider tests for “succeeded then process died”, “response lost”,
    and “provider says operation does not exist”.

- [ ] **PR5-25 [code] Optional clarity rename: `logical_item_key` -> `stage_item_key`**
  - `stage_instances.logical_item_key` and
    `quality_evaluations.logical_item_key` identify a planned stage work item
    (for example `asset_001`, `speech_scene_003`, `render_chunk_02`), not an
    artifact version slot.
  - Do not rename them to `artifact_key`; one stage item can produce several
    artifacts, and the stage-item uniqueness is
    `(run_id, node_id, logical_item_key)`.
  - If the “logical” prefix is confusing, add a separate migration renaming
    both columns to `stage_item_key`, then update contracts, repositories,
    tests, atlas/docs, and fixtures. Keep `artifact_key` (`PR5-12`) separate.

---

## P0 — Critical (Before Merge)

- [ ] **Fix migration mismatch for worktrees**
  - Add per-worktree `PIPELINE_HOME` via `.envrc` or direnv
  - Document in README: `export PIPELINE_HOME=/tmp/pipeline-$(basename $PWD)`
  - File: `README.md`, `.envrc.example`

- [ ] **Fix broken `human-review list` and `show` commands**
  - CLI imports `cli_human_review_list` and `cli_human_review_show` from
    `pipeline.quality.human_review`, but neither function exists
  - Both commands exit 1 with `ImportError`; `decide` works
  - Either implement the helpers or call `HumanReviewManager` directly
  - Files: `src/pipeline/cli.py`, `src/pipeline/quality/human_review.py`

- [ ] **Add CLI smoke tests to verification checklist**
  - Add to CI/verification script:
    ```bash
    uv run python -m pipeline capabilities invoke --database /tmp/test.db --capability speech_generation --operation-version v1 --fake-outcome success
    uv run python -m pipeline workflow validate workflows/explainer_validation_v1.yaml
    uv run python -m pipeline report --run-id <actual_run_id>
    ```

- [ ] **Update both design log files with ADRs**
  - `docs/kb/docs/AI_Video_Pipeline_Design_Discussion_Log.md` — chronological discussions
  - `docs/kb/docs/AI_Video_Pipeline_Decisions.md` — decision register (ADR index)
  - Add ADR-001 through ADR-007

---

## P1 — High Priority (Post-Merge)

- [ ] **Make `quality evaluate` re-runnable**
  - Deterministic evaluation IDs are primary keys; a second identical run fails
    with `ConflictError` on `quality_evaluations.evaluation_id`
  - Use an upsert or delete prior evaluations/gate results for the same
    manifest/stage before inserting
  - File: `src/pipeline/quality/pipeline.py`, `src/pipeline/storage/repositories/base.py`

- [ ] **Return a distinct exit code for `REGENERATE`**
  - `quality evaluate` currently exits 0 for `REGENERATE`; only `FAIL` and
    `HUMAN_REVIEW` return 1
  - Decide whether `REGENERATE` should be non-zero or documented as "needs work"
  - File: `src/pipeline/cli.py`

- [ ] **Change `ArtifactPointerType` to Enum**
  - Current: `NonEmptyStr` (extensible, typos allowed)
  - Enum values: `ACCEPTED`, `PUBLISHED`, `SUPERSEDED`, `INVALIDATED`, `DELETED`
  - File: `src/pipeline/contracts/artifacts.py`

- [ ] **Add `StageCategory` and `sub_category` to `StageNode`**
  ```python
  class StageCategory(StrEnum):
      CONTENT = "CONTENT"
      PRODUCTION = "PRODUCTION"
      POST = "POST"
      GOVERNANCE = "GOVERNANCE"


  class StageNode(Contract):
      stage_name: StageName
      category: StageCategory = StageCategory.CONTENT
      sub_category: str | None = None
  ```
  - Files: `src/pipeline/contracts/vocabularies.py`, `src/pipeline/contracts/workflow.py`

- [ ] **Add `cost_cents` naming (replace `cost_minor`)**
  - Rename across contracts: `cost_cents`, `budget_cap_cents`, `reserved_cents`, `committed_cents`
  - Files: `src/pipeline/contracts/capabilities.py`, `src/pipeline/contracts/config.py`, `src/pipeline/contracts/vocabularies.py`, migrations

- [ ] **Add monthly quota config to `BudgetPolicy`**
  ```python
  class BudgetPolicy(Contract):
      monthly_quota_minor: int | None = None
      monthly_quota_reset_day: int = 1
      alert_at_percent: float = 0.8
  ```
  - File: `src/pipeline/contracts/config.py`

- [ ] **Move raw SQL from LeaseManager to LeaseRepository**
  - File: `src/pipeline/execution/leases.py` → `src/pipeline/storage/repositories/execution.py`

- [ ] **Split `DeterministicCheckEvaluator` into subclasses**
  - One class per evaluator type (schema, reference, asset, timeline)
  - File: `src/pipeline/quality/evaluators.py`

- [ ] **Rename `cost_minor` → `cost_cents` everywhere**
  - Consistent naming across codebase

---

## P2 — Medium Priority

- [ ] **Add docstrings to all public enums, dataclasses, models**
  - PEP 257 field docstrings: `field_name: type  #: Description`
  - Files: `vocabularies.py`, `capabilities.py`, `artifacts.py`, `routing.py`, `review.py`, `jobs.py`, `composition.py`, `config.py`, `content.py`, `editorial.py`, `events.py`, `execution.py`, `profiles.py`

- [ ] **Document inbox/outbox/fenced leases/reconciliation in README**
  - Add architecture section with diagrams
  - File: `README.md`

- [ ] **Convert stable string constants to Enums**
  - `LayerKind`, `CapabilityKind`, `OperationKind` where fixed
  - Files: `composition.py`, `capabilities.py`, `vocabularies.py`

- [ ] **Document `__all__` purpose in each `__init__.py`**
  - One-line comment: `# Public API exports`

- [ ] **Add inline comments for SQL pragmas, context managers**
  - Files: `database.py`, `leases.py`, `migrations/0001_initial.sql`

- [ ] **Add `StageCategory` and `sub_category` to workflow YAML examples**
  - File: `workflows/explainer_validation_v1.yaml`

---

## P3 — Nice to Have

- [ ] **Move workflow definitions to JSONC**
  - Add `json5` dependency
  - Update loader: `json5.load()` instead of `yaml.safe_load()`
  - Migrate `.yaml` → `.jsonc`
  - Files: `src/pipeline/workflow/loader.py`, `workflows/*.jsonc`

- [ ] **Add `Litestream` setup docs for SQLite replication**
  - File: `docs/operations/sqlite-backup.md`

- [ ] **Add `Rclone + Google Drive` backup docs**
  - File: `docs/operations/sqlite-backup.md`

- [ ] **Split large evaluator class into separate files**
  - `evaluators/schema.py`, `evaluators/reference.py`, `evaluators/asset.py`, `evaluators/timeline.py`

- [ ] **Add integration tests for CLI commands**
  - File: `tests/test_cli_integration.py`

---

### P3 — Operations, documentation process, and build

- [ ] **PR5-26 [ops] Gitignore local pipeline state**
  - Document a standard local state directory (for example `state/` or
    `PIPELINE_HOME`) and add it to `.gitignore` along with `*.sqlite3`,
    `*.sqlite3-wal`, and `*.sqlite3-shm`.
  - The repository may contain the pipeline code and config, but never the
    live SQLite database, WAL files, or local state.
  - Add a README/AGENTS note so worktrees do not accidentally commit DBs.

- [ ] **PR5-27 [ops] SQLite backup with integrity checks**
  - Add a script that runs `PRAGMA integrity_check`, `PRAGMA foreign_key_check`,
    and a backup (`VACUUM INTO` or `.backup`) every minute for local
    development.
  - Store backups outside the repository and retain a small rolling window.
  - Make the destination pluggable so it can later target an S3-compatible
    bucket; keep local filesystem as the default.

- [ ] **PR5-28 [docs] Keep request-flow docs current from code**
  - Update `docs/AGENTS.md` with a rule that `REQUEST_FLOW.md` and generated
    reference docs are updated whenever contracts, IDs, storage, or execution
    semantics change.
  - Prefer generating reference documentation from code (Pydantic contracts,
    enums, repository schemas) instead of maintaining a hand-written atlas.
  - Identify or add a library/tool for automatic doc generation and run it in CI.

- [ ] **PR5-29 [build] Add a build/CI system**
  - There is no build system yet because the project is local-first Python:
    no compiled artifacts, dependencies are managed by `uv`/`hatch`, and
    verification is currently manual (`pytest`, ruff, schema/docs checks).
  - Add CI (for example GitHub Actions) that runs tests, lint/format, schema
    validation, docs generation, and CLI smoke tests on every push/PR.
  - Include automatic documentation generation in the build so generated
    reference docs cannot drift from code.

- [ ] **PR5-30 [docs] State-transition diagrams**
  - Create one diagram per major component: job/lease lifecycle, stage
    instance/attempt lifecycle, capability idempotency lifecycle, outbox
    delivery, quality gate/repair lifecycle, and run readiness.
  - Include terminal states, retry/reconciliation paths, and fencing-token
    ownership changes.
  - Store diagrams as text (Mermaid or DOT) so they can be reviewed in PRs.

---

## Completed (FV-11)

- [x] Fix quality gate review zone logic (review_threshold <= score < pass_threshold)
- [x] Fix pass-only policy (no review_threshold → pass_threshold as floor)
- [x] Fix duplicate failure codes in hash verification
- [x] Fix duplicate failure codes in threshold checking
- [x] Fix duplicate failure codes in missing artifacts
- [x] Add 8 missing outcome factories to `capabilities/__init__.py`
- [x] Fix module docstring ordering (cli, contracts, workflow)
- [x] Fix CLI argument parsing (positional args)
- [x] Fix migration checksum error (delete DB, re-migrate)
- [x] All 1481 tests pass
- [x] All lint/format/schema/docs checks pass
- [x] Add `create_assembly_success_outcome` etc. to `capabilities/__init__.py`

---

## Notes

- **Worktree isolation**: Add `.envrc` with `export PIPELINE_HOME=/tmp/pipeline-$(basename $PWD)` to each worktree
- **Migration rule**: Never edit applied migrations; create new migration file
- **Verification checklist**: Add CLI smoke tests before declaring "done"
- **Design log**: Update both `Design_Discussion_Log.md` and `Decisions.md` with ADRs