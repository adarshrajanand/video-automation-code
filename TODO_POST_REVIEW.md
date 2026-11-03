# Post-Review TODO

Single source of truth for post-review work. `FAQ.md` links here by ID.

**Status:** open unless marked `[x]` or moved to `Completed`.
**Last reviewed:** 2026-11-03.

## Conventions

- **IDs are stable.** `PR5-NN` is a PR #5 review item; `GEN-NN` is a carried-over
  FV-11 item. Never renumber or reuse an ID.
- **Priority.** `P0` blocks correctness or merge; `P1` is the next design/behavior
  work; `P2` is normal documentation and hardening; `P3` is opportunistic or
  scale-dependent.
- **Type.** One primary tag per item: `[code]`, `[docs]`, `[test]`, `[ops]`,
  `[build]`, or `[design]`. Secondary work stays in `Work`.
- **Shape.** Every item has `Context`, `Work`, `Acceptance`, and
  `Files/References`. Keep each section short and testable.
- **One concern per item.** If two parts can ship independently, split them. If
  they cannot, keep one item and say why.
- **Cross-reference by ID**, not by position or line number. Add the TODO item
  before referencing it from `FAQ.md`.
- **Completion.** Check the box, add the PR/commit, and move the item to
  `Completed`. Do not delete history.

## Index

| ID | Priority | Type | Title |
|----|----------|------|-------|
| `PR5-01` | P0 | code | Fix atlas generator rendering |
| `PR5-02` | P0 | code | Fix idempotency-record projection drift |
| `PR5-03` | P0 | code | Fix `stage_` ID collisions and add a stage creator |
| `PR5-04` | P0 | code | Remove double prefixes from `eval_`, `qgr_`, `repair_` |
| `PR5-05` | P0 | code | Fix `quality evaluate` |
| `PR5-06` | P0 | code | Fix `human-review list` and `show` |
| `PR5-07` | P0 | code | Canonicalize persisted timestamps |
| `PR5-08` | P0 | code | Make `capabilities list` read-only |
| `GEN-01` | P0 | ops | Isolate `PIPELINE_HOME` per worktree |
| `GEN-02` | P0 | test | Add CLI smoke and integration tests |
| `GEN-03` | P0 | docs | Add ADR-001 through ADR-007 to both design logs |
| `PR5-09` | P1 | code | Decide outbox delivery semantics for multiple consumers |
| `PR5-10` | P1 | code | Load quality gate policy and calibrate thresholds |
| `PR5-11` | P1 | docs | Write the ID derivation contract |
| `PR5-12` | P1 | code | Rename `logical_slot` to `artifact_key` |
| `PR5-13` | P1 | code | Implement run-overrides resolution |
| `PR5-14` | P1 | docs | Reconcile failure-action vocabularies |
| `PR5-15` | P1 | docs | Map artifact types to repair scopes |
| `PR5-16` | P1 | code | Persist readiness and stage creation end to end |
| `PR5-21` | P1 | code | Rename `idempotency_records` for its capability scope |
| `PR5-22` | P1 | design | Resolve `policy_ids` |
| `PR5-23` | P1 | code | Fingerprint the full semantic request |
| `PR5-24` | P1 | code | Add provider-side idempotency and reconciliation |
| `PR5-25` | P1 | code | Optional clarity rename: `logical_item_key` to `stage_item_key` |
| `GEN-04` | P1 | code | Add `StageCategory` and `sub_category` to `StageNode` |
| `GEN-05` | P1 | code | Rename `cost_minor` to `cost_cents` |
| `GEN-06` | P1 | design | Add monthly quota config to `BudgetPolicy` |
| `GEN-07` | P1 | code | Move raw SQL from `LeaseManager` to `LeaseRepository` |
| `GEN-08` | P1 | code | Split `DeterministicCheckEvaluator` into focused evaluators |
| `PR5-17` | P2 | docs | Fix factual errors in `REQUEST_FLOW.md` |
| `PR5-18` | P2 | docs | Expand `REQUEST_FLOW.md` explanations |
| `PR5-19` | P2 | docs | Move extension recipes into `docs/AGENTS.md` |
| `PR5-20` | P2 | docs | Make recorded fixtures reproducible |
| `GEN-09` | P2 | docs | Add docstrings to public enums, models, and dataclasses |
| `GEN-10` | P2 | docs | Document inbox/outbox/fenced leases/reconciliation in README |
| `GEN-11` | P2 | code | Convert remaining closed string literals to Enums |
| `GEN-12` | P2 | docs | Document `__all__` purpose |
| `GEN-13` | P2 | docs | Add inline comments for SQL pragmas and context managers |
| `GEN-14` | P2 | docs | Add `StageCategory`/`sub_category` to workflow examples |
| `PR5-26` | P3 | ops | Gitignore local pipeline state |
| `PR5-27` | P3 | ops | SQLite backup with integrity checks every minute |
| `PR5-28` | P3 | docs | Keep request-flow docs current from code |
| `PR5-29` | P3 | build | Add a build/CI system |
| `PR5-30` | P3 | docs | State-transition diagrams per component |
| `GEN-15` | P3 | docs | Move workflow definitions to JSONC |
| `GEN-16` | P3 | docs | Litestream setup docs |
| `GEN-17` | P3 | docs | Rclone + Google Drive backup docs |

## P0 — Blocking correctness

### PR5-01 [code] Fix atlas generator rendering

**Context.** The generated `CONTRACT_FIELD_ATLAS.md` shows `<enum 'FailureCode`
instead of a type name, unescaped `|` unions shift Required/Default cells, and
`default_factory` fields render as `PydanticUndefined`.

**Work.**
- Render Enum subclasses by class name; never call `str()` on the class.
- Escape `|` inside Markdown table cells so one type cannot create extra cells.
- Read `field.default_factory` and render the produced default safely.
- Add generator tests for enums, unions, lists, and `default_factory`.
- Regenerate the atlas and review the diff.

**Acceptance.** No `<enum`, no shifted rows, no `PydanticUndefined`; each bug has
a regression test.

**Files/References.** `scripts/generate_contract_atlas.py`, atlas generator
tests, `CONTRACT_FIELD_ATLAS.md`. FAQ: `L50`, `L72`, `L143`, `L233`, `L854`.

### PR5-02 [code] Fix idempotency-record projection drift

**Context.** `idempotency_records` has DDL columns for `operation_version`,
`input_artifact_ids`, `required_features`, `locale`, and `result_artifact_ids`,
but `IdempotencyRecordRepository.columns` omits them. The payload is correct;
the extracted columns silently keep defaults.

**Work.**
- Add the missing columns to the repository projection.
- Teach `_column_value()` to JSON-encode list values.
- Backfill or validate existing rows from `payload`.
- Add round-trip tests and a SQL-filter test on each restored column.

**Acceptance.** Every DDL column is projected; SQL filtering matches the payload;
tests cover list and scalar columns.

**Files/References.** `src/pipeline/storage/repositories/control.py`,
`src/pipeline/storage/repositories/base.py`, storage tests. FAQ: `L949`, `L2920`.

### PR5-03 [code] Fix `stage_` ID collisions and add a stage creator

**Context.** The `stage_` formula uses only `(run_id, node_id)`, so two items in
one node receive the same ID even though the table allows both rows. There is
also no production stage-instance creation path.

**Work.**
- Include the stage item key in `deterministic_id("stage", ...)`.
- Add the production stage-instance creation/upsert path.
- Rely on the `(run_id, node_id, logical_item_key)` unique constraint for
  idempotency; translate a conflict into a re-read.
- Update golden examples and add a multi-item regression test.
- Keep the current `logical_item_key` name; `PR5-25` owns the optional rename.

**Acceptance.** Two items in one node get different IDs; repeated creation is a
no-op; tests cover both.

**Files/References.** `src/pipeline/ids.py`, workflow/execution creation code,
tests. FAQ: `L524`, `L3147`.

### PR5-04 [code] Remove double prefixes from `eval_`, `qgr_`, `repair_`

**Context.** `deterministic_id()` already returns the prefix, but several call
sites prepend it again. Some random evaluator IDs are single-prefixed but
random, so the docs cannot claim every path is double-prefixed.

**Work.**
- Use the helper result directly at every deterministic call site.
- Normalize random evaluator IDs to one `eval_` prefix.
- Update tests, fixtures, and documented example IDs.
- Add an assertion that generated IDs contain exactly one prefix.

**Acceptance.** No `eval_eval_`, `qgr_qgr_`, or `repair_repair_` IDs; regression
tests cover all three families.

**Files/References.** `src/pipeline/quality/evaluators.py`, `gate.py`,
`repair.py`, `semantic.py`, `media.py`, `speech.py`, tests. FAQ: `L1208`,
`L1223`, `L1253`, `L3150`.

### PR5-05 [code] Fix `quality evaluate`

**Context.** The command opens `Database` directly and skips migrations, a second
identical evaluation fails with `ConflictError`, and a `REGENERATE` decision
returns exit code `0`.

**Work.**
- Use the migrated-database path, or require an explicit `db migrate` with a
  clear error.
- Make a repeated identical evaluation idempotent, or fail with a documented
  conflict that names the existing evaluation.
- Define and test exit codes, including `REGENERATE`.
- Add CLI integration tests on a fresh and an existing database.

**Acceptance.** A fresh database works; rerunning the same evaluation is
deterministic; every gate decision has a documented exit code.

**Files/References.** `src/pipeline/cli.py`, quality pipeline, CLI integration
tests. FAQ: `L1182`, `L3249`. Merges the older “re-runnable” and “REGENERATE”
items.

### PR5-06 [code] Fix `human-review list` and `show`

**Context.** `src/pipeline/cli.py` imports `cli_human_review_list` and
`cli_human_review_show` from `pipeline.quality.human_review`, but neither
function exists. Both commands fail with `ImportError`; `decide` works.

**Work.**
- Implement and export the two helpers, or call `HumanReviewManager` directly.
- Add CLI tests for `list`, `show`, `decide`, and the `review` alias.
- Cover the empty-list and missing-review paths.

**Acceptance.** All four commands exit successfully with real data and clear
errors for missing IDs.

**Files/References.** `src/pipeline/quality/human_review.py`,
`src/pipeline/cli.py`, tests.

### PR5-07 [code] Canonicalize persisted timestamps

**Context.** Some paths emit `...Z`, while `datetime.isoformat()` or Pydantic’s
default JSON emits `+00:00`. Both are valid ISO-8601, but lexicographic
`ORDER BY created_at` can misorder rows.

**Work.**
- Emit one UTC representation, preferably `Z`, from every persistence path.
- Add cross-path ordering tests that mix both serializers.
- Backfill existing rows if the stored strings are mixed.

**Acceptance.** All persisted timestamps use one format; ordering tests pass.

**Files/References.** `src/pipeline/fingerprints.py`,
`src/pipeline/contracts/base.py`, storage tests. FAQ: `L2780`.

### PR5-08 [code] Make `capabilities list` read-only

**Context.** `capabilities list` has no database need, but it calls
`_migrated_database()`, which opens the database and runs migrations.

**Work.**
- Remove `_migrated_database()` from the command.
- Add a test proving a fresh or nonexistent database path is untouched.

**Acceptance.** Listing capabilities creates no database file and runs no
migration.

**Files/References.** `src/pipeline/cli.py`. FAQ: `L283`.

### GEN-01 [ops] Isolate `PIPELINE_HOME` per worktree

**Context.** Two worktrees shared one SQLite file and hit a migration checksum
mismatch.

**Work.**
- Add `.envrc.example` with
  `export PIPELINE_HOME=/tmp/pipeline-$(basename $PWD)`.
- Document the rule in `README.md` and the implementation notes.
- Keep demo databases out of the repository.

**Acceptance.** Two worktrees can migrate independently without checksum errors.

**Files/References.** `.envrc.example`, `README.md`, `AGENTS.md`.

### GEN-02 [test] Add CLI smoke and integration tests

**Context.** Unit tests missed broken CLI imports and argument handling.

**Work.**
- Add a smoke sequence for `db migrate`, `capabilities invoke`,
  `workflow validate`, and `report`.
- Add integration tests for workflow readiness, capabilities list/invoke,
  quality evaluate, human-review list/show/decide, and error paths.
- Run both in the verification checklist or CI.

**Acceptance.** A broken CLI command fails the suite before merge; tests cover
success and failure paths.

**Files/References.** `tests/test_cli_integration.py`, verification docs.

### GEN-03 [docs] Add ADR-001 through ADR-007 to both design logs

**Context.** Accepted decisions need a durable register and a chronological
record.

**Work.**
- Add ADR-001 through ADR-007 to
  `docs/kb/docs/AI_Video_Pipeline_Design_Discussion_Log.md`.
- Add the same decisions to
  `docs/kb/docs/AI_Video_Pipeline_Decisions.md` as the decision index.
- Cross-link the two files and keep dates/status consistent.

**Acceptance.** Both files list the same seven ADRs with valid links.

**Files/References.** `docs/kb/docs/` (separate docs repository).

## P1 — Design and behavior

### PR5-09 [code] Decide outbox delivery semantics for multiple consumers

**Context.** `outbox_messages` has one row and one global ack per event.
`inbox_receipts` is per consumer, but a consumer added after delivery never sees
the event, and two concurrent consumers compete for the same claim.

**Work.**
- Choose one: per-consumer delivery rows, per-consumer cursors, or documented
  future-only semantics.
- If delivery rows: add the migration, repository, claim/ack, and backfill.
- If future-only: stop describing the outbox as multi-consumer pub/sub.
- Record the decision in an ADR and test the chosen behavior.

**Acceptance.** Multi-consumer behavior is explicit; a new consumer either
backfills or is documented as future-only; tests cover concurrent consumers.

**Files/References.** `src/pipeline/execution/dispatcher.py`, outbox/inbox
repositories, tests. FAQ: `L2207`, `F11`.

### PR5-10 [code] Load quality gate policy and calibrate thresholds

**Context.** The CLI hardcodes `0.8` pass and `0.65` review and constructs a
gate policy inline. `ThresholdRegistry` exists but is not used on this path.

**Work.**
- Load `QualityGatePolicy` from `quality_gate_policies`.
- Use `ThresholdRegistry` records for pass/review thresholds.
- Record calibration data and rationale in an ADR.
- Test policy loading and the pass/review/regenerate decisions.

**Acceptance.** No hardcoded thresholds in the CLI; changing policy data changes
the decision; tests cover both.

**Files/References.** quality gate/pipeline code, threshold registry, tests.
FAQ: `L1271`.

### PR5-11 [docs] Write the ID derivation contract

**Context.** Deterministic IDs and shared digests are intentional, but the
formulas, opacity rule, and versioning strategy are only scattered through the
atlas.

**Work.**
- Document every formula: inputs, prefix, shared-digest intent, and parent
  dependency.
- State that prefixes are lookup/documentation indexes, never runtime dispatch.
- Define when to add an entity type or formula version to a digest.
- Add an ADR and link it from `REQUEST_FLOW.md` §8.4.

**Acceptance.** Docs match `src/pipeline/ids.py`; examples show replay and
dedupe; a formula change has a documented versioning rule.

**Files/References.** `src/pipeline/ids.py`, `REQUEST_FLOW.md`, ADRs. FAQ:
`L92`, `L125`, `L3099`, `L3133`, `F3`.

### PR5-12 [code] Rename `logical_slot` to `artifact_key`

**Context.** `logical_slot` is the stable editorial identity of an artifact
within a run, independent of version. “Slot” is narrower and has caused
confusion with stage work items.

**Work.**
- Add a new migration; do not edit `0001_initial.sql`.
- Rename `artifacts.logical_slot` and `artifact_pointers.logical_slot`.
- Recreate the affected indexes and the partial unique index with
  `artifact_key` names.
- Update `Artifact`/`ArtifactPointer`, repositories, method names, raw SQL,
  atlas/docs examples, and golden fixtures.
- Do not rename `stage_instances.logical_item_key` or
  `quality_evaluations.logical_item_key` to `artifact_key`; those are stage item
  keys.
- Add an ADR and verify with `PRAGMA table_info`/`index_list`.

**Acceptance.** The schema, indexes, contracts, repositories, and docs use
`artifact_key`; no artifact table still has `logical_slot`; tests pass.

**Files/References.** new migration, `contracts/artifacts.py`, repositories,
docs, fixtures. FAQ: `L1478`, `L2143`, `F8`.

### PR5-13 [code] Implement run-overrides resolution

**Context.** The CLI constructs an empty `RunOverrides`; there is no resolver
that applies system/domain/channel defaults or bounds.

**Work.**
- Resolve system, domain, and channel defaults plus `RunOverrides` under
  `SystemPolicy` bounds.
- Populate `resolved_values`, `source_map`, and `config_hash`.
- Persist the immutable `EffectiveConfig` snapshot.
- Test allowed and forbidden overrides and the source map.

**Acceptance.** Overrides cannot bypass non-overridable fields; the snapshot is
reproducible from its inputs.

**Files/References.** `contracts/config.py`, `contracts/profiles.py`, config
resolution code, tests. FAQ: `L441`, `L447`.

### PR5-14 [docs] Reconcile failure-action vocabularies

**Context.** `FailureAction` lives in `execution/retry.py`; `RecoveryAction`,
`QualityFailureAction`, and `RepeatedFailureAction` live in
`contracts/vocabularies.py`. The §6.13 catalogue uses `PAUSE`, `DEFER`, and
`HUMAN_REVIEW` as default actions, but `PAUSE` and `DEFER` do not exist in code.

**Work.**
- Correct the catalogue to the real enum values.
- Label the columns “Attempt status / Job status / Stage status”.
- Add a consistency test that compares the catalogue with the enums.

**Acceptance.** No nonexistent action values; the test fails if docs and enums
drift.

**Files/References.** `REQUEST_FLOW.md` §6.13, `execution/retry.py`,
`contracts/vocabularies.py`, docs test. FAQ: `L2472`, `L2474`, `L2484`,
`L2486`.

### PR5-15 [docs] Map artifact types to repair scopes

**Context.** Repair is scoped to editorial/execution units, not arbitrary
artifact types. There is no table showing which checks apply to which artifact
type or which `RepairScope` is allowed.

**Work.**
- Add a table: artifact type → checks → allowed `RepairScope`.
- Document script/content repair through stage regeneration and descendant
  invalidation.
- Implement missing repair/invalidation execution where the table promises it.

**Acceptance.** The table matches `QualityCheck`/`RepairPlan`; repair plans use
an allowed scope; tests cover one content and one media artifact.

**Files/References.** quality repair code, `REQUEST_FLOW.md`, tests. FAQ:
`L1356`, `L2445`.

### PR5-16 [code] Persist readiness and stage creation end to end

**Context.** Readiness computes `next_status` but does not write it, and there is
no production stage-instance/attempt/job creation flow for every cardinality
mode.

**Work.**
- Add the caller that persists the readiness result and run status.
- Create stage instances, attempts, and jobs for one-to-one, one-to-many, and
  many-to-one nodes.
- Add integration tests that start from a workflow and end with claimable jobs.

**Acceptance.** Readiness is persisted; each ready item gets exactly one chain;
tests cover all three cardinality modes.

**Files/References.** readiness engine, `execution/jobs.py`, workflow tests.
FAQ: `L524`, `L3353`.

### PR5-21 [code] Rename `idempotency_records` for its capability scope

**Context.** The table is written only by `CapabilityExecutor` and stores
capability, operation version, request fingerprint, executor ID, provider IDs,
and result artifacts. Its current name suggests a generic cross-domain ledger.

**Work.**
- Add a migration renaming it to `capability_idempotency_records`.
- Recreate the status and execution indexes with capability-scoped names.
- Update `IdempotencyRecordRepository.table`, raw SQL, tests, atlas/docs, and
  recorded fixtures.
- Keep the primary-key column `idempotency_key`; within this table it is the
  capability idempotency key.
- Do not reuse this table for job, outbox, or repair idempotency.

**Acceptance.** Schema, repository, and docs use the capability-scoped name;
tests pass; no other subsystem writes the table.

**Files/References.** new migration, `storage/repositories/control.py`,
`execution/capability_executor.py`, tests, docs. FAQ: `L2159`, `F1`.

### PR5-22 [design] Resolve `policy_ids`

**Context.** `WorkflowDefinition.policy_ids` is only duplicate-validated. The
runtime loader does not resolve it, readiness/execution do not consume it, and
execution uses the default recovery policy even when a node names another.
Docs validation and runtime validation disagree.

**Work.**
- Decide: implement registry resolution with node-level precedence, or remove
  `policy_ids` and require node-level references.
- If implemented: fail fast on unknown/wrong-version IDs and snapshot resolved
  IDs/versions in `EffectiveConfig`.
- Add tests for unknown IDs and precedence; update §2.2 examples.

**Acceptance.** No dead field; docs and runtime agree; tests cover unknown and
overridden policies.

**Files/References.** `contracts/workflow.py`, policy registry/loader,
`REQUEST_FLOW.md` §2.2, tests. FAQ: `L402`, `F6`.

### PR5-23 [code] Fingerprint the full semantic request

**Context.** `payload_fingerprint` covers only `request.payload`. The executor
manually compares `capability`, `operation_version`, `input_artifact_ids`,
`required_features`, and `locale`, but not `quality_requirement`,
`latency_requirement`, `data_classification`, `cost_limit_minor`, or
`payload_schema_version`. A replay with a different budget is accepted.

**Work.**
- Define one canonical semantic-request object containing every field that can
  affect the result or the permission to run.
- Exclude execution context (`run_id`, `stage_instance_id`, `attempt_id`,
  `correlation_id`, `effective_config_id`, `timeout_seconds`,
  `allowed_data_classification`).
- Use it for the idempotency fingerprint and replay comparison.
- Decide whether `CapabilityRequest.runtime_context` is semantic; move it into
  `payload` or remove it.
- Add mismatch tests for cost limit, quality requirement, and schema version.

**Acceptance.** A changed semantic field rejects replay; a context-only change
does not; tests cover both.

**Files/References.** `contracts/capabilities.py`,
`execution/capability_executor.py`, fingerprint code, tests. FAQ: `L812`,
`F4`.

### PR5-24 [code] Add provider-side idempotency and reconciliation

**Context.** A database unique key prevents duplicate rows, not duplicate
external side effects. A crash after the provider succeeds but before the result
is persisted can still lead to a second charge or asset on retry.

**Work.**
- Pass a provider idempotency key derived from the capability idempotency key.
- Persist the provider operation ID.
- On `UNKNOWN`, query the provider by operation ID before any retry.
- Make `FAILED` after a possible side effect reconcilable too.
- Add fake-provider tests for “succeeded then process died”, “response lost”,
  and “provider says operation does not exist”.

**Acceptance.** No blind retry of an unknown outcome; reconciliation is tested
for all three cases.

**Files/References.** `execution/capability_executor.py`, provider adapter,
fake provider, tests. FAQ: `F10`.

### PR5-25 [code] Optional clarity rename: `logical_item_key` to `stage_item_key`

**Context.** `stage_instances.logical_item_key` and
`quality_evaluations.logical_item_key` identify a planned stage work item
(`asset_001`, `speech_scene_003`, `render_chunk_02`), not an artifact version
slot.

**Work.**
- If adopted, add a migration renaming both columns to `stage_item_key`.
- Update contracts, repositories, tests, atlas/docs, and fixtures.
- Keep `artifact_key` (`PR5-12`) separate; do not merge the two concepts.
- Preserve the `(run_id, node_id, stage_item_key)` uniqueness.

**Acceptance.** The rename is either done consistently or explicitly rejected;
stage-item uniqueness and IDs still work.

**Files/References.** new migration, contracts, repositories, tests, docs. FAQ:
`L1478`, `F8`.

### GEN-04 [code] Add `StageCategory` and `sub_category` to `StageNode`

**Context.** Major-stage grouping is needed for progress, budget, retry, and
human gates, but `StageNode` has no typed category.

**Work.**
- Add `StageCategory` (`CONTENT`, `PRODUCTION`, `POST`, `GOVERNANCE`).
- Add `category` and optional `sub_category` to `StageNode`.
- Update schemas, fixtures, validation, and examples.

**Acceptance.** Workflow definitions can declare a category; schemas and docs
validate; tests cover defaults and invalid values.

**Files/References.** `contracts/vocabularies.py`, `contracts/workflow.py`,
schemas, fixtures.

### GEN-05 [code] Rename `cost_minor` to `cost_cents`

**Context.** The currency unit is ambiguous. Budget values are cents.

**Work.**
- Rename to `cost_cents`, `budget_cap_cents`, `reserved_cents`,
  `committed_cents`, and `actual_cost_cents` across contracts, migrations,
  repositories, tests, docs, and fixtures.
- Add a migration that preserves existing values.
- Remove the duplicate “rename everywhere” item.

**Acceptance.** No `cost_minor` remains; data is preserved; tests pass.

**Files/References.** `contracts/capabilities.py`, `contracts/config.py`,
`contracts/vocabularies.py`, migrations, tests.

### GEN-06 [design] Add monthly quota config to `BudgetPolicy`

**Context.** Monthly quota is enforced externally; the pipeline should track and
alert without pretending to enforce the hard stop.

**Work.**
- Add `monthly_quota_cents`, `monthly_quota_reset_day`, and
  `alert_at_percent`.
- Document that the billing system enforces the quota.
- Add tests for the alert threshold and reset day.

**Acceptance.** Policy carries the external quota reference; no local hard stop;
docs are explicit.

**Files/References.** `contracts/config.py`, docs, tests. FAQ PR #1: monthly
quota.

### GEN-07 [code] Move raw SQL from `LeaseManager` to `LeaseRepository`

**Context.** `LeaseManager` contains SQL, which breaks the repository boundary
and makes fencing behavior harder to test.

**Work.**
- Move the queries and updates into `LeaseRepository`.
- Keep the fencing-token and transaction semantics in the manager.
- Add repository and manager tests for claim, renew, complete, and expire.

**Acceptance.** `LeaseManager` has no raw SQL; behavior is unchanged; tests
cover the fencing paths.

**Files/References.** `execution/leases.py`,
`storage/repositories/execution.py`, tests.

### GEN-08 [code] Split `DeterministicCheckEvaluator` into focused evaluators

**Context.** One large class handles schema, reference, asset, and timeline
checks, which makes extension and testing harder.

**Work.**
- Split into focused modules or subclasses: `schema`, `reference`, `asset`,
  `timeline`.
- Keep the registry and public evaluator names stable.
- Add tests per evaluator and a registry smoke test.

**Acceptance.** Each evaluator has one responsibility; the registry still
resolves all checks; tests pass.

**Files/References.** `quality/evaluators.py` (or `quality/evaluators/`),
registry, tests.

## P2 — Documentation and hardening

### PR5-17 [docs] Fix factual errors in `REQUEST_FLOW.md`

**Context.** The review found several factual errors, not just formatting.

**Work.**
- Rename the “Three ways” heading; it lists seven destinations.
- Change “PURE WORKFLOW” from a plane to a layer.
- Replace `latency_budget_ms` with `latency_requirement` or remove it.
- Correct the §6.13 default-action values.
- Correct the claim that every `eval_` path is double-prefixed.
- Clarify `short_derivative` with `one_to_many` and `count: 1`.

**Acceptance.** Each item is corrected in place; no stale term remains.

**Files/References.** `REQUEST_FLOW.md`. FAQ: `L54`, `L146`, `L269`, `L813`,
`L1223`, `L2486`.

### PR5-18 [docs] Expand `REQUEST_FLOW.md` explanations

**Context.** Several concepts are named but not explained, so readers have to
reverse-engineer the code.

**Work.**
- Prefix lookup vs if/else dispatch, derivation coupling, shared digests, and
  deterministic IDs vs UUIDs, with replay/dedupe examples.
- Why migrations exist, `schema_migrations` rows, failure modes, and PRAGMAs.
- `CHECK`, `ABSTAIN`, `after_max_regenerations`, and `RepairPlan`.
- Why `idempotency_records` exists despite table constraints; payload-size
  tradeoff; consumer/global-ack limitation; capability-scoped name.
- Queue names, `RunOverrides` ownership, and the policy shapes that build
  `EffectiveConfig`; what `policy_ids` does and does not do.
- Separate `CapabilityRequest`, `ExecutionContext`, `EffectiveConfig`, and
  `ReadinessContext`, with the “does it change the result?” test.
- Update-in-place vs append and mutating transitions/fencing with a stale-worker
  example.

**Acceptance.** Each topic has a concrete example and a code reference; no
section relies on an undefined term.

**Files/References.** `REQUEST_FLOW.md`. FAQ: many entries; see the section
sources.

### PR5-19 [docs] Move extension recipes into `docs/AGENTS.md`

**Context.** The atlas has useful “add a stage/check/gate/capability” recipes,
but they belong in agent guidance, not only in a review document.

**Work.**
- Add the recipes to `docs/AGENTS.md` with links from `REQUEST_FLOW.md`.
- Keep each recipe short: files to touch, validation command, common mistakes.
- Add a link check.

**Acceptance.** `docs/AGENTS.md` contains the recipes; links resolve.

**Files/References.** `docs/AGENTS.md`, `REQUEST_FLOW.md`. FAQ: `L1964`.

### PR5-20 [docs] Make recorded fixtures reproducible

**Context.** The atlas uses recorded demo IDs from `/tmp/opencode/...`, but the
databases are not checked in and cannot be regenerated from the repository.

**Work.**
- Add a checked-in script or command transcript that recreates
  `/tmp/opencode/pipeline-demo` and `/tmp/opencode/quality-demo`.
- Label golden-path IDs vs recorded-demo IDs consistently.
- Make the script idempotent and safe to rerun.

**Acceptance.** A reader can regenerate the fixtures and match the documented
IDs.

**Files/References.** scripts, `REQUEST_FLOW.md`, `CONTRACT_FIELD_ATLAS.md`.
FAQ: `L837`.

### GEN-09 [docs] Add docstrings to public enums, models, and dataclasses

**Context.** Public contracts lack PEP 257 field documentation, so field meaning
is inferred from names.

**Work.**
- Add class and field docstrings/comments, using `field_name: type  #: text`.
- Cover `vocabularies.py`, `capabilities.py`, `artifacts.py`, `routing.py`,
  `review.py`, `jobs.py`, `composition.py`, `config.py`, `content.py`,
  `editorial.py`, `events.py`, `execution.py`, and `profiles.py`.
- Add a lint or docs check for missing public docstrings where practical.

**Acceptance.** Every public contract has a class docstring and non-obvious
fields are documented.

**Files/References.** `src/pipeline/contracts/`.

### GEN-10 [docs] Document inbox/outbox/fenced leases/reconciliation in README

**Context.** These mechanisms are documented in the atlas and review notes, but
the README has no architecture section.

**Work.**
- Add an architecture section covering delivery semantics, leases/fencing,
  idempotency, and ambiguous outcomes.
- Link to the state diagrams from `PR5-30`.
- Keep the README summary short; link to deeper docs.

**Acceptance.** A new reader understands the delivery and ownership model from
the README.

**Files/References.** `README.md`, `PR5-30`.

### GEN-11 [code] Convert remaining closed string literals to Enums

**Context.** Some fixed vocabularies are still plain strings or `Literal`s,
which allows typos. `LayerKind` is already an Enum.

**Work.**
- Audit fixed sets, for example the audio asset `kind` values.
- Convert them to `StrEnum` where the set is closed.
- Update schemas, fixtures, and validation.

**Acceptance.** Closed sets are Enums; open extension points stay strings; no
behavior change.

**Files/References.** `contracts/vocabularies.py`, `contracts/composition.py`,
schemas, fixtures.

### GEN-12 [docs] Document `__all__` purpose

**Context.** `__all__` appears in many modules, but its role (public API export)
is not stated.

**Work.**
- Add a one-line comment to each public `__init__.py` or module with `__all__`:
  `# Public API exports`.
- Keep private helpers out of `__all__`.

**Acceptance.** Consistent comment; public exports are intentional.

**Files/References.** `src/pipeline/**/__init__.py`, public modules.

### GEN-13 [docs] Add inline comments for SQL pragmas and context managers

**Context.** `busy_timeout`, WAL, `synchronous=NORMAL`, and transaction scopes
are not explained where they are set.

**Work.**
- Comment each non-obvious PRAGMA with its tradeoff.
- Comment `BEGIN IMMEDIATE` and transaction context managers with the locking
  reason.
- Comment table-level `CHECK` constraints where the intent is not obvious.

**Acceptance.** A reader can understand the durability/locking choice without
leaving the file.

**Files/References.** `storage/database.py`, `execution/leases.py`,
`storage/migrations/0001_initial.sql`.

### GEN-14 [docs] Add `StageCategory`/`sub_category` to workflow examples

**Context.** `GEN-04` adds the fields; examples must show them.

**Work.**
- Add `category` and `sub_category` to
  `workflows/explainer_validation_v1.yaml` (or the JSONC replacement).
- Validate the workflow and update the atlas examples.

**Acceptance.** Examples validate; docs match the schema.

**Files/References.** `workflows/explainer_validation_v1.yaml`, `GEN-04`,
`PR5-19`.

## P3 — Operations, documentation process, and build

P3 items are not blockers for the current local slice. `PR5-29` is the main
prerequisite for broader collaboration.

### PR5-26 [ops] Gitignore local pipeline state

**Context.** The repository may contain pipeline code and config, but never the
live SQLite database, WAL files, or local state.

**Work.**
- Standardize a local state directory (`state/` or `PIPELINE_HOME`).
- Add `state/`, `*.sqlite3`, `*.sqlite3-wal`, and `*.sqlite3-shm` to
  `.gitignore`.
- Add a README/AGENTS note so worktrees do not commit databases.

**Acceptance.** Running the pipeline leaves `git status` clean.

**Files/References.** `.gitignore`, `README.md`, `AGENTS.md`.

### PR5-27 [ops] SQLite backup with integrity checks every minute

**Context.** The local SQLite database is the system of record. A corrupt or
lost file loses the run history.

**Work.**
- Add a script that runs `PRAGMA integrity_check`, `PRAGMA foreign_key_check`,
  and a backup (`VACUUM INTO` or `.backup`) every minute.
- Store backups outside the repository with a small rolling window.
- Make the destination pluggable: local filesystem now, S3-compatible later.
- Abort the backup on a failed integrity check and alert.

**Acceptance.** The script backs up a healthy database, refuses a corrupt one,
and restores a sample; retention works.

**Files/References.** scripts, operations docs.

### PR5-28 [docs] Keep request-flow docs current from code

**Context.** `REQUEST_FLOW.md` is a useful reference but is maintained by hand;
the generated atlas already drifts.

**Work.**
- Update `docs/AGENTS.md`: update `REQUEST_FLOW.md` and generated reference docs
  whenever contracts, IDs, storage, or execution semantics change.
- Prefer generating reference docs from code (Pydantic contracts, enums,
  repository schemas) over maintaining a hand-written atlas.
- Choose a generator/library and run it in the build.

**Acceptance.** The rule is in `docs/AGENTS.md`; generated docs are checked in
CI; drift fails the build.

**Files/References.** `docs/AGENTS.md`, `REQUEST_FLOW.md`,
`scripts/generate_contract_atlas.py`, `PR5-29`.

### PR5-29 [build] Add a build/CI system

**Context.** There is no build system yet because the project is local-first
Python: no compiled artifacts, dependencies are managed by `uv`/`hatch`, and
verification is currently manual (`pytest`, ruff, schema/docs checks).

**Work.**
- Add CI (for example GitHub Actions) that runs tests, lint/format, schema
  validation, docs generation/check, and CLI smoke tests on every push/PR.
- Cache `uv` and run on the supported Python version.
- Make the checks required for merge.
- Include automatic documentation generation so generated reference docs cannot
  drift from code.

**Acceptance.** CI is green on `main`; a failing test, lint error, schema error,
or docs drift blocks merge.

**Files/References.** CI configuration, `pyproject.toml`, `PR5-28`,
`GEN-02`.

### PR5-30 [docs] State-transition diagrams per component

**Context.** State machines are spread across code and prose, which makes
terminal states and recovery paths hard to review.

**Work.**
- Create one diagram per component: job/lease lifecycle, stage
  instance/attempt lifecycle, capability idempotency lifecycle, outbox delivery,
  quality gate/repair lifecycle, and run readiness.
- Include terminal states, retry/reconciliation paths, and fencing-token
  ownership changes.
- Store diagrams as text (Mermaid or DOT) so they can be reviewed in PRs.
- Link them from `REQUEST_FLOW.md` and the README.

**Acceptance.** Every diagram renders in the repository UI; each state name
matches the code; reviewers can trace a failure from start to terminal state.

**Files/References.** docs/diagrams, `REQUEST_FLOW.md`, `README.md`.

### GEN-15 [docs] Move workflow definitions to JSONC

**Context.** YAML is permissive and has no native comment-preserving strict
schema. JSONC keeps comments with stricter parsing.

**Work.**
- Add the `json5` dependency.
- Change the loader to `json5.loads()`.
- Migrate `.yaml` workflows to `.jsonc`; update tests, fixtures, and docs.
- Keep a clear error for YAML files.

**Acceptance.** No YAML workflow files remain; the loader and tests use JSONC;
the schema still validates.

**Files/References.** `workflow/loader.py`, `workflows/*.jsonc`, tests.

### GEN-16 [docs] Litestream setup docs

**Context.** Litestream is the recommended continuous SQLite replication option
for the local-to-remote path.

**Work.**
- Add `docs/operations/sqlite-backup.md` with Litestream config, systemd unit,
  retention, and a restore drill.
- Note the S3-compatible endpoint requirements.

**Acceptance.** A reader can configure replication and restore a backup.

**Files/References.** `docs/operations/sqlite-backup.md`.

### GEN-17 [docs] Rclone + Google Drive backup docs

**Context.** Rclone + Google Drive is the free alternative to Litestream/S3.

**Work.**
- Add rclone configuration, cron schedule, retention, encryption, and restore
  steps to `docs/operations/sqlite-backup.md`.
- Compare it with Litestream and state when to use each.

**Acceptance.** A reader can configure and restore the rclone path.

**Files/References.** `docs/operations/sqlite-backup.md`.

## Completed

Completed before this TODO convention; IDs are not assigned retroactively.

- [x] Fix quality gate review-zone logic (`review_threshold <= score <
  pass_threshold`).
- [x] Fix pass-only policy (no `review_threshold` uses `pass_threshold` as the
  floor).
- [x] Fix duplicate failure codes in hash verification.
- [x] Fix duplicate failure codes in threshold checking.
- [x] Fix duplicate failure codes in missing artifacts.
- [x] Add eight missing outcome factories to `capabilities/__init__.py`.
- [x] Fix module docstring ordering (CLI, contracts, workflow).
- [x] Fix CLI argument parsing (positional args).
- [x] Fix migration checksum error (delete DB, re-migrate).
- [x] All 1481 tests pass.
- [x] All lint/format/schema/docs checks pass.
- [x] Add `create_assembly_success_outcome` and related factories.
- [x] `ArtifactPointerType` is already a `StrEnum` (`CURRENT`, `ACCEPTED`,
  `PUBLISHED`); the older TODO was stale.
- [x] PR #5 review: 81 replies posted, 15 follow-up answers recorded, and
  `FAQ.md` regrouped by topic.
- [x] PR #6 merged the review answers and follow-up TODOs into `main`.

## Merged or dropped

- Duplicate `cost_minor` items merged into `GEN-05`.
- `quality evaluate` re-run and `REGENERATE` exit-code items merged into
  `PR5-05`.
- CLI smoke and integration test items merged into `GEN-02`.
- Evaluator split items merged into `GEN-08`.
- `ArtifactPointerType` enum item closed; already implemented.
