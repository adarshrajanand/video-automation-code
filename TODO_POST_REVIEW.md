# Post-Review TODO List

## P0 — Critical (Before Merge)

- [ ] **Fix migration mismatch for worktrees**
  - Add per-worktree `PIPELINE_HOME` via `.envrc` or direnv
  - Document in README: `export PIPELINE_HOME=/tmp/pipeline-$(basename $PWD)`
  - File: `README.md`, `.envrc.example`

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