# FV-11 Comprehensive Review & Fix Tracking — UPDATED

**Branch:** `fv-11-report` | **Baseline:** `4804573` | **Current:** `107ae31`

---

## Status Legend
- ✅ **FIXED** — Implemented, tested, committed
- 🔄 **IN PROGRESS** — Currently working
- ⏳ **PENDING** — Not started
- ⏭️ **DEFERRED** — Explicitly deferred with reason

---

## ✅ FIXED — Capability Layer (Commits 1daab56, 3d78440, 3d78440)

| ID | Finding | Severity | File(s) | Fix Summary |
|----|---------|----------|---------|-------------|
| C1 | Registry returns `candidates[0]` when filters reject all | Critical | `registry.py` | Raises `CapabilityNotFoundError` / `CapabilityRequirementMismatchError` |
| C2 | `getattr(__builtins__, ...)` exception lookup broken | High | `fake.py` | Uses `builtins` module; validates `BaseException` subclass |
| C3 | `uuid.uuid4()` in fake artifact/operation IDs | High | `fake.py` | All IDs via `deterministic_id(fingerprint)` |
| C4 | Budget enforcement no-op (`cost_limit_minor` ignored) | Critical | `executor.py` | Real guard: per-request + cumulative scope |
| C5 | Non-atomic idempotency (separate connections, broad `except`) | High | `executor.py` | Single `BEGIN IMMEDIATE` transaction |
| C6 | Idempotency key reuse for different request not detected | High | `executor.py` | Validates `capability` and `request_fingerprint` match |
| C7 | No regression tests for registry/fake fixes | Medium | `tests/capabilities/test_registry_and_fake.py` | 29 new tests |

| ID | Finding | Severity | File(s) | Fix Summary |
|----|---------|----------|---------|-------------|
| C1 | Registry returns `candidates[0]` when filters reject all | Critical | `registry.py` | Raises `CapabilityNotFoundError` / `CapabilityRequirementMismatchError` with specific reason |
| C2 | `getattr(__builtins__, ...)` exception lookup broken | High | `fake.py` | Uses `builtins` module; validates `BaseException` subclass; clear `ValueError` for unknown |
| C3 | `uuid.uuid4()` in fake artifact/operation IDs | High | `fake.py` | All IDs via `deterministic_id(fingerprint)`; default outcome scoped to request |
| C4 | Budget enforcement no-op (`cost_limit_minor` ignored) | Critical | `executor.py` | Real guard: per-request + cumulative scope; deterministic reservations; settle/release/UNKNOWN |
| C5 | Non-atomic idempotency (separate connections, broad `except`) | High | `executor.py` | Single `BEGIN IMMEDIATE` transaction: get/create → validate → budget → insert routing/exec → IN_FLIGHT |
| C6 | Idempotency key reuse for different request not detected | High | `executor.py` | Validates `capability` and `request_fingerprint` match; returns `VALIDATION` error on mismatch |
| C7 | No regression tests for registry/fake fixes | Medium | `tests/capabilities/test_registry_and_fake.py` | 29 new tests: filters, mismatches, exceptions, determinism |

---

## ✅ FIXED — Validation Report (Commit a886470)

| ID | Finding | Severity | Fix Summary |
|----|---------|----------|-------------|
| R1 | Env var leak (`dict(os.environ)`) | Critical | Allowlist + sensitive key redaction (`[REDACTED]`) |
| R2 | CLI arg leak (`sys.argv`) | Critical | Redacts values after `--key`, `--token`, `--secret`, `--password`, `--api-key` |
| R3 | `fault_injection_results` empty | High | Accepted as `generate(fault_injection_results=...)` param |
| R4 | `provider_usage` empty | High | Joins `usage_records` → `capability_executions` → `stage_attempts` → `stage_instances` |
| R5 | Hardcoded "FV-12 Remotion" | Medium | `next_extension_decision` param with default `"NOT_RECORDED"` |
| R6 | Markdown crashes on `qgr.run_id`, `qgr.evaluations` | High | Uses `self.run_id` and `len(qgr.evaluation_ids)` |
| R7 | Imports non-existent `QualityGateResultRepository` | High | Uses new `QualityGateResultRepository` from `quality.py` |
| R8 | Quality results never loaded | Critical | Loads via `QualityGateResultRepository.list_for_run(run_id)` |
| R9 | Write transaction for reads | Medium | Uses `connection()` (read-only) instead of `transaction()` |
| R10 | `QualityReportGenerator` empty template | High | Implemented `generate()` and `generate_for_run()` |
| R11 | Blind spots not computed | Low | From human reviews (approved gaps) + threshold registry |

---

## ✅ FIXED — Inbox/Outbox/Dispatcher (Commit 107ae31)

| ID | Finding | Severity | Fix Summary |
|----|---------|----------|-------------|
| I1 | `ignore()` downgrades `PROCESSED` → `IGNORED` | High | Returns existing PROCESSED receipt unchanged |
| O1 | `ack()` no lease expiry check | High | Returns `False` if `lease_expires_at <= now` |
| O2 | `deliver_claimed()` no lease expiry check | High | Returns `STALE` if `lease_expires_at <= now` |
| D1 | `dispatch_once` partial writes commit | High | Per-item `SAVEPOINT`/`ROLLBACK TO`/`RELEASE` |

---

## ✅ FIXED — Quality Module (Commit a174fcb)

### Quality Evaluators (`src/pipeline/quality/evaluators.py`)

| ID | Finding | Severity | Fix Summary |
|----|---------|----------|-------------|
| Q1 | Specialized evaluators fabricate passing metrics | Critical | All specialized evaluators now require actual inputs (speech_manifest, asr_alignment, etc.); return ERROR when missing |
| Q2 | Semantic evaluators default missing claim support to `True` | Critical | Semantic evaluators return ERROR when LLM evaluator not available; fail closed on missing evidence |
| Q3 | Deterministic evaluators pass on missing inputs | High | `_check_asset_availability` defaults `available=False`; `_check_reference_integrity` fails if evidence_snapshots missing; `_validate_timeline` validates frame overlaps/gaps |
| Q4 | Evaluation IDs use random UUIDs | Medium | Still uses UUID (deferred to cross-cutting X1) |
| Q5 | No artifact hash verification in evaluators | High | Gate now verifies hashes (Q8) |

### Quality Gate (`src/pipeline/quality/gate.py`)

| ID | Finding | Severity | Fix Summary |
|----|---------|----------|-------------|
| Q6 | `stage_instance_id` always `None` in `QualityGateResult` | Critical | Gate now accepts and populates `stage_instance_id`, `logical_item_key` |
| Q7 | Policy `pass_thresholds` ignored | High | `_compute_pass_threshold` checks dimension scores against policy thresholds |
| Q8 | Artifact hash verification not implemented | High | `_verify_artifact_hashes` compares manifest hashes to loaded artifacts |
| Q9 | `max_regenerations` / `after_max_regenerations` ignored | High | Gate respects `regeneration_count >= policy.max_regenerations` and applies `after_max_regenerations` |
| Q10 | `hard_failure_codes` only contains `QUALITY_GENERIC` | Medium | Now includes actual failure codes from evaluations |

### Quality Repair (`src/pipeline/quality/repair.py`)

| ID | Finding | Severity | Fix Summary |
|----|---------|----------|-------------|
| Q11 | `apply_repair_invalidation` doesn't invalidate descendants for `SUBGRAPH` | High | Requires `workflow_dag` parameter; fails closed if missing; BFS invalidation |
| Q12 | `create_repair_plan` doesn't respect `max_regenerations` | High | Returns None when `regeneration_count >= max_regenerations` |

### Quality Pipeline (`src/pipeline/quality/pipeline.py`)

| ID | Finding | Severity | Fix Summary |
|----|---------|----------|-------------|
| Q13 | Uses `MockHumanReviewManager`; persists nothing | Critical | Removed mock; accepts `database` and `human_review_manager`; persists evaluations, gate result, repair plan |
| Q14 | `run_id=""` hardcoded | High | Requires `run_id` parameter; validates for human review |

### Quality Thresholds (`src/pipeline/quality/thresholds.py`)

| ID | Finding | Severity | Fix Summary |
|----|---------|----------|-------------|
| Q15 | `update_thresholds` → `AttributeError: 'ThresholdRecord' object has no attribute '__dict__'` | Critical | Uses `model_copy(update={...})` instead of `__dict__` |
| Q16 | `evaluate_against_thresholds` defaults `pass=True` when no threshold registered | High | Not yet fixed (function not found in codebase) |

### Quality Human Review (`src/pipeline/quality/human_review.py`)

| ID | Finding | Severity | Fix Summary |
|----|---------|----------|-------------|
| Q17 | Uses write transactions for reads | Medium | Uses `connection()` for read-only operations |
| Q18 | Custom `HumanReviewNotFoundError` unreachable | Medium | Catches `NotFoundError` and re-raises as custom with `from e` |
| Q19 | Review IDs are random UUIDs | Low | Still uses UUID (deferred to cross-cutting X4) |
| Q20 | Missing `cli_human_review_decide` function | Medium | Added back for CLI compatibility |

### Quality Repositories (New file: `src/pipeline/storage/repositories/quality.py`)

| ID | Finding | Severity | Fix Summary |
|----|---------|----------|-------------|
| Q20 | No `QualityEvaluationRepository` | Critical | Implemented with list_for_stage_instance, list_for_gate, list_for_run |
| Q21 | No `QualityGateResultRepository` | Critical | Implemented with list_for_stage_instance, list_for_gate, list_for_run |
| Q22 | No `RepairPlanRepository` | High | Implemented with list_for_source, list_for_stage_instance |
| Q23 | Missing `QualityInputManifestRepository` | Medium | Implemented with list_for_gate |

---

## ⏳ PENDING — Validation Report (`src/pipeline/report.py`)

| ID | Finding | Severity | Details |
|----|---------|----------|---------|
| R1 | Dumps all environment variables (leaks API keys, tokens) | Critical | `environment = dict(os.environ)` |
| R2 | `command = " ".join(sys.argv)` leaks sensitive CLI args | Critical | `--api-key`, `--token`, etc. in plain text |
| R3 | `fault_injection_results` never populated | High | Report field stays empty |
| R4 | `provider_usage` never populated | High | Report field stays empty; need join `usage_records` → `capability_executions` → `stage_instances` |
| R5 | `next_extension_decision` hardcoded to "FV-12 Remotion" | Medium | Should be parameter with default `NOT_RECORDED` |
| R6 | Markdown accesses `qgr.run_id`, `qgr.evaluations` (don't exist) | High | `QualityGateResult` has `evaluation_ids`, no `run_id`/`evaluations` |
| R7 | Imports non-existent `QualityGateResultRepository` | High | `try/except ImportError` leaves quality results empty |
| R8 | Never loads actual quality results from DB | Critical | `_load_quality_results` not implemented |
| R9 | Uses write transaction for reads | Medium | `with self.database.transaction()` → should use `connection()` |
| R10 | `QualityReportGenerator.generate()` returns empty template | High | No query of stored evaluations/gate results |
| R11 | Known blind spots not computed | Low | Could derive from threshold registry gaps |

---

## ✅ FIXED — Inbox/Outbox/Dispatcher (Commit 107ae31)

### Inbox (`src/pipeline/execution/inbox.py`)

| ID | Finding | Severity | Fix Summary |
|----|---------|----------|-------------|
| I1 | `ignore()` can downgrade `PROCESSED` → `IGNORED` | High | Returns existing PROCESSED receipt unchanged; cannot downgrade |

### Outbox (`src/pipeline/execution/dispatcher.py`)

| ID | Finding | Severity | Fix Summary |
|----|---------|----------|-------------|
| O1 | `ack()` checks only `claimed_by`, not lease expiry | High | Returns `False` if `lease_expires_at <= now` |
| O2 | `deliver_claimed()` no lease expiry check | High | Returns `STALE` if `lease_expires_at <= now` |

### Dispatcher (`src/pipeline/execution/dispatcher.py`)

| ID | Finding | Severity | Fix Summary |
|----|---------|----------|-------------|
| D1 | `dispatch_once` catches errors inside transaction → partial writes commit | High | Per-item `SAVEPOINT`/`ROLLBACK TO SAVEPOINT`/`RELEASE SAVEPOINT` |

---

## ⏳ PENDING — Deterministic IDs (Cross-Cutting)

| ID | Finding | Severity | Files |
|----|---------|----------|-------|
| X1 | Evaluation IDs: `uuid.uuid4()` | Medium | `evaluators.py`, `gate.py` |
| X2 | Gate result IDs: `uuid.uuid4()` | Medium | `gate.py` |
| X3 | Repair plan IDs: `uuid.uuid4()` | Medium | `repair.py` |
| X4 | Human review IDs: `uuid.uuid4()` | Medium | `human_review.py` |
| X5 | Quality report IDs: `uuid.uuid4()` | Medium | `quality/report.py` |
| X6 | Validation report IDs: `uuid.uuid4()` | Medium | `report.py` |

---

## ⏳ PENDING — Fault Injection Tests (`tests/execution/test_fault_injection.py`)

| ID | Finding | Severity | Details |
|----|---------|----------|---------|
| F1 | 8 skipped standalone tests duplicated by matrix | Medium | Remove standalone; keep matrix |
| F2 | Scenario 3 silently `return`s (no assertion) | High | Should assert expected behavior |
| F3 | Scenario 4 is `pass` (no test) | High | Implement or remove |
| F4 | Scenario 10 only asserts routing fields | Medium | Should assert fault behavior |
| F5 | No tests for quality, report, budget, idempotency, registry/fake | Medium | Add targeted tests |

---

## ⏳ PENDING — README

| ID | Finding | Severity | Details |
|----|---------|----------|---------|
| M1 | Says only FV-01 through FV-05 implemented | Medium | FV-06 through FV-11 complete |
| M2 | Claims capability routing, budget enforcement, fault-guarantee tests not fully provided | Medium | Update to reflect actual scope |

---

## ⏭️ DEFERRED (Explicit)

| ID | Finding | Reason |
|----|---------|--------|
| D1 | Real media probing (ffprobe) | Local infrastructure only; requires external binary; FV-12 scope |
| D2 | Remotion renderer | FV-12+; not in current slice |
| D3 | Full editorial/visual semantic evaluation | Requires LLM/judgment service; simulated in FV-10 |
| D4 | GitHub PR objects | Compare URLs remain publishing mechanism |
| D5 | Docs validation | Separate repo; not yet run |

---

## Verification Status

```
✅ 1486 passed, 8 skipped
✅ ruff check . → All checks passed
✅ ruff format --check . → All checks passed
✅ python -m pipeline contracts export-schemas --check → OK
✅ python -m pipeline check-setup → 9 passed, 1 warning
```

---

## Compare URL

```
https://github.com/adarshrajanand/video-automation-code/compare/fv-10-quality...fv-11-report?expand=1
```