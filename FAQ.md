# FV-11 FAQ — Human Review Questions & Answers

This document is the durable Q&A record for human reviews of this
repository. Questions are grouped by review and then by topic, not by comment
order or line number. Each answer names its source so it can be traced back to
the original review.

- **PR #1 review:** consolidated questions and answers from the initial review.
- **PR #5 review:** 81 line comments plus 15 follow-up questions. The 81 replies
  were posted on the PR. No code or reviewed-document fixes were made in
  response; follow-ups are tracked as
  [GitHub issues](https://github.com/adarshrajanand/video-automation-code/issues)
  with `PR5-*` IDs.
- **PR #89 review:** 21 line comments on canonical timestamp persistence and the
  migration backfill. Replies were posted on the PR. This review established the
  payload/projection distinction and the canonical ISO-8601 representation that
  GEN-24 (#92) later revises.
- **PR #94 review:** 18 line comments on the timestamp-column registry. Follow-up
  questions were answered in the PR threads and are recorded below. The
  `CHECK`-only schema-hardening follow-up is GEN-26 (#95).

Formatting rules for this file are in `AGENTS.md`.

## Contents

- [PR #1 Review — Initial Human Review](#pr-1-review--initial-human-review)
- [PR #5 Review — Request-Flow Atlas](#pr-5-review--request-flow-atlas)
  - [Follow-up index](#follow-up-index)
  - [Documentation, Atlas, and Fixtures](#documentation-atlas-and-fixtures)
  - [Workflow Definitions and Readiness](#workflow-definitions-and-readiness)
  - [Execution Model: Stages, Attempts, Jobs, and Leases](#execution-model-stages-attempts-jobs-and-leases)
  - [Identifiers and Idempotency](#identifiers-and-idempotency)
  - [Database, Migrations, and Persistence](#database-migrations-and-persistence)
  - [Capabilities, Providers, and Outbox](#capabilities-providers-and-outbox)
  - [Quality Gates and Checks](#quality-gates-and-checks)
  - [Artifacts, Slots, and Repair](#artifacts-slots-and-repair)
  - [Failure Handling and Recovery](#failure-handling-and-recovery)
  - [PR #5 Decision Summary](#pr-5-decision-summary)
- [PR #89 Review — Canonical Timestamps and Migration Backfill](#pr-89-review--canonical-timestamps-and-migration-backfill)
  - [Migration Model and Checksums](#migration-model-and-checksums)
  - [Payloads, Projections, and Backfill](#payloads-projections-and-backfill)
  - [Tests and Isolation](#tests-and-isolation)
  - [PR #89 Decision Summary](#pr-89-decision-summary)
- [PR #94 Review — Timestamp Column Registry](#pr-94-review--timestamp-column-registry)
  - [Follow-up index](#follow-up-index-1)
  - [Registry Scope: Payloads, Projections, and Storage Format](#registry-scope-payloads-projections-and-storage-format)
  - [Migration Discipline](#migration-discipline)
  - [Registry Behavior](#registry-behavior)
  - [Generated Columns](#generated-columns)
  - [Constraints and NULL Semantics](#constraints-and-null-semantics)
  - [Tests and SQLite Mechanics](#tests-and-sqlite-mechanics)
  - [PR #94 Decision Summary](#pr-94-decision-summary)

---

## PR #1 Review — Initial Human Review

**Source:** PR #1 review.

### Migration & Database

#### **Q: How did the migration mismatch happen with worktrees?**

**A:** Two worktrees (`fv-11-report`, `fv-11-test`) were created from the same commit. Both worktrees share the same `PIPELINE_HOME` environment variable (default: `~/.local/share/video-automation-pipeline/state/pipeline.sqlite3`), so they share the **same SQLite database file**. 

The first worktree (`fv-11-report`) ran `pipeline db migrate`, which applied migration `0001_initial.sql` and recorded its SHA-256 checksum in the `schema_migrations` table. When the second worktree (`fv-11-test`) was created and ran `pipeline db migrate`, the migration runner detected that migration `0001_initial.sql` was already applied (record exists in `schema_migrations` table with checksum X). It then computed the current file's checksum (Y) and found X ≠ Y. The error: `migration 0001_initial.sql changed after it was applied; add a new migration instead`.

**Why the checksum changed:** Documentation updates modified the migration file (comments, whitespace, line endings). Even a single character change produces a different SHA-256 hash.

**Fix:** Use separate `PIPELINE_HOME` per worktree:
```bash
export PIPELINE_HOME=/tmp/pipeline-$(basename $PWD)
# Add to .envrc or direnv per worktree
```
Or delete the DB and re-migrate when switching worktrees.

---

#### **Q: How does migration checksum detection work?**

**A:** The migration runner (`src/pipeline/storage/migrations.py`) computes SHA-256 of each migration file's content:
```python
def _compute_checksum(self, path: Path) -> str:
    content = path.read_bytes()
    return hashlib.sha256(content).hexdigest()
```
On first apply, it stores the checksum in the `schema_migrations` table:
```sql
CREATE TABLE schema_migrations (
    name TEXT PRIMARY KEY,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
);
```
On subsequent runs, it recomputes the checksum and compares to the stored value. Any change (whitespace, comments, line endings, comment edits) = different SHA-256 → `MigrationChecksumError`.

---

#### **Q: What is the migration file `0001_initial.sql`?**

**A:** Located at `src/pipeline/storage/migrations/0001_initial.sql`. It defines the **entire database schema** — 20+ tables:
- `workflow_runs`, `stage_instances`, `stage_attempts`, `jobs`, `leases`
- `idempotency_records`, `outbox_messages`, `inbox_receipts`
- `budget_reservations`, `artifact_pointers`, `effective_configs`
- `quality_evaluations`, `quality_gate_results`, `human_reviews`
- Plus indexes, foreign keys, and the `schema_migrations` tracking table

Every table stores the canonical Pydantic contract as JSON payload plus extracted identity, status, and timestamp columns for uniqueness, lookup, and indexes.

---

#### **Q: How to avoid migration conflicts with worktrees?**

**A:** Each worktree should have its own `PIPELINE_HOME`:
```bash
# In each worktree's .envrc or direnv:
export PIPELINE_HOME=/tmp/pipeline-$(basename $PWD)
```
This gives each worktree its own SQLite database file, eliminating migration conflicts. Alternatively, delete the DB and re-migrate when switching worktrees.

---

#### **Q: Monthly quota — how to configure?**

**A:** The budget system is **not time-based** (month/week). It's per-scope: `WORKFLOW_RUN`, `PROJECT`, `ORGANIZATION`. Monthly quota is enforced externally by a billing system.

Add to `BudgetPolicy` for external reference tracking:
```python
class BudgetPolicy(Contract):
    # Per-run/project caps (enforced by pipeline)
    max_cost_per_run_minor: int
    max_cost_per_project_minor: int
    
    # External quota reference (not enforced, just tracked)
    monthly_quota_minor: int | None = None
    monthly_quota_reset_day: int = 1  # 1st of month
    alert_at_percent: float = 0.8  # Alert at 80%
```
Pipeline tracks and alerts; external billing system enforces hard stop.

---

### Architecture & Design

#### **Q: Why is AUDIO_QC a separate stage?**

**A:** AUDIO_QC is separate because it requires **heavy provider calls**:
- Runs **after** speech generation (post-generation validation)
- Calls **ffprobe** for media analysis + potentially ML models for signal quality
- **Different budget profile** (analysis vs generation)
- **Independent retry/retry policy** (different failure modes than generation)
- Can run **in parallel** with VISUAL_PLANNING

Other QC is integrated:
- Light QC (schema, references) inline in generation stages
- Quality gate aggregates all checks at the end
- AUDIO_QC is the only heavy QC requiring separate provider calls and budget

---

#### **Q: Why not make all QC separate stages?**

**A:** Light QC (schema validation, reference integrity) is inline in generation stages. Only heavy QC requiring provider calls (ffprobe, ML models) warrants separate stages. Current design:
- `SCRIPT_GENERATION` → includes schema + reference QC
- `SPEECH_GENERATION` → includes WER/CER, forced alignment QC
- **AUDIO_QC** (separate) → heavy ffprobe + ML signal quality
- `VISUAL_PLANNING` → includes visual intent QC
- `COMPOSITION` → includes timeline/AV sync QC
- `RENDERING` → includes media decode QC
- `QUALITY_GATE` → final aggregation

---

#### **Q: What is `major_stage` in workflow YAML?**

**A:** `major_stage: true` marks a node as a **logical grouping** for:
- **Progress tracking**: Dashboard shows "CONTENT 100% → PRODUCTION 60% → POST 0%"
- **Budget allocation**: Per-major-stage budget caps
- **Retry policies**: Different retry/backoff per major stage
- **Human gates**: Gates between major stages (e.g., human review before POST)

Categories (`StageCategory`):
```python
class StageCategory(StrEnum):
    CONTENT = "CONTENT"  # topic_discovery, script_generation
    PRODUCTION = "PRODUCTION"  # speech_generation, audio_qc
    POST = "POST"  # composition, rendering
    GOVERNANCE = "GOVERNANCE"  # quality_gate, human_review
```

Example in YAML:
```yaml
- stage_name: topic_discovery
  kind: major_stage
  major_stage: true
  optional: true
```

---

#### **Q: What is `operation_version` in capability registry?**

**A:** Capability interface version (e.g., `v1`, `v2`). Same capability can have multiple versions with different input/output schemas. Registry keys by `(capability, operation_version)` → evaluator.

Example:
```python
# Operation v1:
class SpeechGenerationInputV1(Contract):
    text: str
    voice: str = "alloy"


# Operation v2 (adds speed, emotion):
class SpeechGenerationInputV2(Contract):
    text: str
    voice: str
    speed: float = 1.0
    emotion: str = "neutral"
```

Registry keys: `("speech_generation", "v1")` and `("speech_generation", "v2")` → different evaluators.

---

#### **Q: Why "Lease" not "Reservation Token"?**

**A:** "Lease" is the **industry standard term** (Chubby, Consul, etcd, ZooKeeper). Alternatives:
| Term | Used By | Why Not |
|------|---------|---------|
| **Lease** | etcd, Consul, Chubby, ZooKeeper | Standard |
| Reservation | Some systems | Conflicts with `BudgetReservation` |
| Token | Generic | Ambiguous (JWT, auth token, etc.) |
| Grant | Some systems | Less common |

**Keep "Lease"** — it's the standard term. Added docstring:
```python
class Lease(Contract):
    """Time-bounded lock on a resource (fenced lease).

    Industry standard term (Chubby, etcd, ZooKeeper, Consul).
    Also known as: reservation, grant, token.
    """

    token: int  # Monotonic fence token
```

---

#### **Q: Why YAML for workflows, not JSON/JSONC?**

**A:** YAML is preferred for **human authors** — comments, anchors, readability. JSON/JSONC for machine-generated configs. No strong need to unify.

---

### Contracts & Models

#### **Q: What is `schema_version` and why everywhere?**

**A:** Every contract has `schema_version` (e.g., `script.v1`, `quality-gate-result.v1`). Enables:
- Versioned contract evolution
- Migration/translation between versions
- Forward/backward compatibility
- Fixture validation
- Schema registry lookup

Few places lack it = oversight/legacy.

---

#### **Q: Contract vs Model — difference?**
| Aspect | Contract | Model |
|--------|----------|-------|
| **Public API** | Yes | No |
| **Versioned** | Yes (`schema_version`) | No |
| **Schema exported** | Yes (JSON Schema) | No |
| **Frozen** | Yes (`frozen=True`) | Often mutable |
| **Cross-module boundary** | Yes | No (internal) |

**Contract** = public, versioned, schema-exported, frozen, cross-module boundary.  
**Model** = internal, mutable, no schema export, implementation detail.

---

#### **Q: Why `frozen=True` on contracts but `model_copy()` for changes?**

**A:** 
- **Frozen** = immutable after creation (thread safety, cache keys, audit trail)
- To "modify": `new = old.model_copy(update={"field": value})` → creates new instance
- Original preserved for audit trail

**Why frozen + copy:**
1. **Thread safety** — immutable objects shareable
2. **Audit trail** — original preserved
3. **Cache keys** — can use as dict keys
4. **Predictability** — no surprise mutations

---

#### **Q: What is `ExtensionObject`?**

**A:** `Dict[str, Any]` for **extensible metadata without schema**. "Arbitrary" = any JSON-serializable value. Used for provider-specific params, feature flags, future-proofing. Contract doesn't validate contents; provider SDK handles it.

```python
class SpeechGenerationInputV1(Contract):
    text: str
    voice: str
    metadata: ExtensionObject = Field(default_factory=dict)
    # Provider-specific:
    # OpenAI: {"model": "tts-1", "response_format": "mp3"}
    # Azure: {"voice_name": "en-US-JennyNeural", "style": "cheerful"}
    # Google: {"voice_name": "en-US-Standard-A", "effects_profile_id": ["telephony"]}
    # ElevenLabs: {"voice_id": "xyz", "stability": 0.5, "similarity_boost": 0.8}
```

---

#### **Q: Why `NonEmptyStr` not Enum for `pointer_type`?**

**A:** 
| Approach | Pros | Cons |
|----------|------|------|
| Enum | Validation, autocomplete, docs, no typos | Migration for new values |
| String | Extensible, no migration | Typos allowed, no autocomplete |

**Current:** `NonEmptyStr` for extensibility. **Should be Enum** — vocabulary is stable (`ACCEPTED`, `PUBLISHED`, `SUPERSEDED`, `INVALIDATED`, `DELETED`). Will change to Enum.

---

#### **Q: Fixture vs Sample — what's the difference?**
| Term | Meaning |
|------|---------|
| **Fixture** | pytest term for "known good test data" (stored in `tests/fixtures/contracts/valid/`) |
| Sample | Informal term for example data |

**Recommendation:** Keep "fixture" in code (pytest convention), "sample" in user-facing docs.

---

#### **Q: What is `InvalidationScope`?**
```python
class InvalidationScope(StrEnum):
    NONE = "NONE"
    ARTIFACT = "ARTIFACT"  # Single artifact invalidated
    STAGE = "STAGE"  # All artifacts from a stage
    WORKFLOW = "WORKFLOW"  # All artifacts in workflow run
```
Used in `RepairPlan`: what artifacts to mark INVALIDATED. Independent of `RepairScope` (can invalidate broader than repair).

| Scenario | RepairScope | InvalidationScope |
|----------|-------------|-------------------|
| Regenerate one shot | `SHOT` | `ARTIFACT` |
| Regenerate scene | `SCENE` | `STAGE` (all shots in scene) |
| Quality gate fails | `NONE` | `ARTIFACT` (mark bad artifacts) |
| Human review rejects | `NONE` | `WORKFLOW` (invalidate everything) |

Independence: You can invalidate without repairing, or repair without invalidation.

---

### Execution & Concurrency

#### **Q: What is a fenced lease?**

**A:** Fenced Lease = `(lease_id, token, owner_id, expires_at)` where:
- **Token** = monotonically increasing integer per grant
- **Owner** = worker ID claiming the lease
- **Expires_at** = deadline for renewal/completion

**Fencing Protocol:**
1. Worker claims lease → gets `(lease_id, token=N, owner=W1)`
2. Worker does work, attempts commit with `token=N`
3. If W1 crashes before commit, lease expires at `expires_at`
4. New worker W2 claims → gets `token=N+1`
5. If W1 wakes up and tries to commit with `token=N` → **REJECTED** (token mismatch)
6. Only W2 with `token=N+1` can commit

**Code:** `src/pipeline/execution/leases.py` → `LeaseManager.verify_live_claim()`:
```python
def verify_live_claim(
    self, conn, lease_id: str, expected_token: int, owner_id: str
) -> bool:
    row = conn.execute(
        "SELECT token, owner_id, expires_at FROM leases WHERE lease_id = ?", [lease_id]
    ).fetchone()
    if not row:
        return False  # Lease deleted
    if row.token != expected_token:
        return False  # STALE — token changed
    if row.owner_id != owner_id:
        return False  # Different owner
    if row.expires_at < utc_now():
        return False  # Expired
    return True
```

---

#### **Q: How does inbox/outbox work?**

**A:** **Transactional Outbox Pattern** for reliable event delivery without external brokers.

**Outbox (Producer Side):**
- Events + delivery rows written in **same DB transaction** as state change
- `OutboxDispatcher` claims pending rows with **bounded leases**, delivers, acks **only if lease still owned**
- If dispatcher crashes mid-delivery → lease expires → another dispatcher claims → redelivery (at-least-once)

**Inbox (Consumer Side):**
- Deduplication layer for **at-least-once delivery**
- Incoming event ID checked against `inbox_receipts` table
- If NEW: process + write `PROCESSED` receipt in **same transaction** as consumer effect
- If DUPLICATE: skip (exactly-once effect)

**Delivery Semantics:**
- **At-least-once**: Outbox retries until acked
- **At-most-once commit per attempt**: Fenced leases prevent stale commits
- **Exactly-once effect**: Inbox deduplication + idempotent handlers

---

#### **Q: What happens after dead-letter?**

**A:** Dead-letter → human reviews via `HumanReview` workflow:
1. Human reviews via `HumanReview` workflow
2. Verifies actual provider state (API call, dashboard, logs)
3. Decides: **retry** / **skip** / **manual fix**

Automated reconciliation = **FV-12+**.

---

#### **Q: Multi-repo atomic transactions = multi tables?**

**A:** Yes. "Repo" = `SqliteRepository` class per table. "Multi-repo" = multiple repositories in one transaction.

```python
# In JobDispatcher.dispatch_once():
with self.db.transaction() as conn:  # Single connection, single transaction
    stage_instance_repo = StageInstanceRepository(conn)
    lease_repo = LeaseRepository(conn)
    job_repo = JobRepository(conn)
    idempotency_repo = IdempotencyRecordRepository(conn)
    
    stage = stage_instance_repo.get(stage_id)
    lease = lease_repo.create(...)
    job = job_repo.create(...)
    idempotency_repo.update(...)
    # All commit together or all rollback
```

**Why:** SQLite connection = transaction context. Passing same `conn` to multiple repos = single atomic transaction across tables.

---

#### **Q: Where is SQLite saved? How to persist in VM?**

**A:** Default: `$PIPELINE_HOME/state/pipeline.sqlite3` 
- Default: `$HOME/.local/share/video-automation-pipeline/state/pipeline.sqlite3`
- Override: `export PIPELINE_HOME=/mnt/data/video-pipeline`

**In VM (single machine):**
```bash
# Option 1: Default location (persistent disk)
/home/ubuntu/.local/share/video-automation-pipeline/state/pipeline.sqlite3

# Option 2: Dedicated mount (recommended)
export PIPELINE_HOME=/data/video-pipeline
# Mount persistent volume at /data
```

**Directory structure:**
```
PIPELINE_HOME/
├── state/           # pipeline.sqlite3
├── artifacts/       # .staging/ + sha256/<prefix>/<hash>
├── tmp/             # <attempt_id>/workspace/
├── logs/
└── reports/
```

---

#### **Q: SQLite redundancy / corruption protection?**

**A:** 
| Protection | Mechanism |
|------------|-----------|
| **WAL mode** | Enabled (`PRAGMA journal_mode=WAL`) — readers don't block writers |
| **Integrity check** | `PRAGMA integrity_check` on boot |
| **FK check** | `PRAGMA foreign_key_check` on boot |
| **Hourly backups** | SQLite backup API + cron |
| **Best: Litestream** | Real-time replication to S3/GCS/Azure Blob |
| **Free option** | Rclone + Google Drive (15 GB) hourly cron |

**Litestream (recommended for VM):**
```bash
# Install
curl -sL https://github.com/benbjohnson/litestream/releases/download/v0.3.13/litestream-v0.3.13-linux-amd64.tar.gz | tar xz
sudo mv litestream /usr/local/bin/

# /etc/litestream.yml
dbs:
  - path: /mnt/data/video-pipeline/state/pipeline.sqlite3
    replicas:
      - type: s3
        bucket: my-bucket
        path: video-pipeline/pipeline.sqlite3
        region: us-east-1

# systemd service
systemctl enable --now litestream
```
**Benefits:** Real-time replication to S3, point-in-time recovery, zero-downtime, cross-region replication.

**Free option: Rclone + Google Drive (15 GB)**
```bash
rclone config  # → gdrive
# Hourly cron: sqlite3 backup + gzip + rclone copy to gdrive
```

---

### Budget & Cost

#### **Q: Budget system — per month/week?**

**A:** NOT time-based. Per scope: `WORKFLOW_RUN`, `PROJECT`, `ORGANIZATION`. Monthly quota = external enforcement (billing system). Pipeline tracks/alerts; external system enforces hard stop.

Add config for external quota reference:
```python
class BudgetPolicy(Contract):
    max_cost_per_run_minor: int
    max_cost_per_project_minor: int
    monthly_quota_minor: int | None = None
    monthly_quota_reset_day: int = 1
    alert_at_percent: float = 0.8
```

---

#### **Q: Budget = per-request + cumulative?**

**A:** Two-layer budget:

```python
# Per-request limit (set by caller)
cost_limit_minor = 5000  # $50.00 max for THIS capability call

# Cumulative enforcement (across all requests in scope)
# Scope = workflow run, or project, or organization
```

**BudgetReservation tracks:**
```python
class BudgetReservation(Contract):
    scope_type: BudgetScopeType  # WORKFLOW_RUN, PROJECT, ORG
    scope_id: str  # e.g., "run_abc123"
    budget_cap_minor: int  # HARD CAP (stored here!)
    reserved_minor: int  # Optimistic: what we PLAN to spend
    committed_minor: int  # Actual: what we ACTUALLY spent
    status: BudgetReservationStatus  # RESERVED, SETTLED, RELEASED
```

**Flow:**
```
Request (cost_limit_minor=5000):
  1. Check: reserved_minor + cost_limit_minor <= budget_cap_minor
  2. Reserve: reserved_minor += 5000 (optimistic)
  3. Execute capability
  4. Success: committed_minor += actual_cost (e.g., 3200)
             reserved_minor -= 5000 (release reservation)
     Failure: reserved_minor -= 5000 (release)
```

**Prevents runaway:** If `reserved_minor + cost_limit > budget_cap` → reject request upfront.

---

### Capabilities & Fake Provider

#### **Q: IdempotencyRecord — only for capability execution?**

**A:** Currently yes. But the pattern is reusable. Could add `domain` field (`capability`, `workflow`, `quality`) for any idempotent operation.

```python
class IdempotencyRecord(Contract):
    idempotency_key: str
    operation: str
    operation_version: str
    input_artifact_ids: list[str]
    required_features: list[str]
    locale: str
    status: IdempotencyStatus  # SUCCEEDED, IN_FLIGHT, FAILED, etc.
    result_payload: dict | None
```

---

#### **Q: Idempotency key vs fingerprint?**
| Aspect | Idempotency Key | Fingerprint |
|--------|-----------------|-------------|
| Purpose | Exactly-once **execution** deduplication | Content-addressed **storage** deduplication |
| Scope | Capability + inputs + version | Content bytes only |
| Generated by | Caller (or deterministic from inputs) | `SHA-256(canonical_json(content))` |
| Used by | `IdempotencyRecord` lookup | `ArtifactStore` addressing |

---

#### **Q: Why fake provider only? When real providers?**

**A:** FV-11 = local/fake-provider milestone. Real providers (AWS Bedrock, OpenAI, Google Vertex) = **FV-12+**. Executor interface allows swap; fake used for local dev/CI.

---

#### **Q: Why 8 missing outcome factories in `__init__.py`?**

**A:** The CLI `capabilities invoke` command imports them directly for the `--fake-outcome` argument. Unit tests mock the registry → never exercise the CLI import path.

**Fixed:** Added 8 missing exports to `src/pipeline/capabilities/__init__.py`:
```python
create_assembly_success_outcome
create_composition_success_outcome
create_rendering_success_outcome
create_short_derivative_success_outcome
create_speech_generation_success_outcome
create_tts_adapter_success_outcome
create_asr_alignment_success_outcome
create_audio_qc_failure_outcome
```

**Lesson:** CLI integration tests ≠ unit tests. Always run actual CLI commands.

---

### Testing & CLI

#### **Q: Why no quality tests in `tests/quality/`?**

**A:** Quality tests are integrated in `tests/capabilities/test_audio_capabilities.py` and execution tests. Quality gate logic tested via capability + execution tests.

---

#### **Q: Correct CLI usage?**
```bash
# Workflow validation (positional arg, not --workflow)
uv run python -m pipeline workflow validate workflows/explainer_validation_v1.yaml

# Workflow readiness (positional workflow path, optional --context)
uv run python -m pipeline workflow readiness workflows/explainer_validation_v1.yaml

# Capabilities (requires --database, --fake-outcome)
uv run python -m pipeline capabilities invoke \
  --database /path/to/pipeline.sqlite3 \
  --capability speech_generation \
  --operation-version v1 \
  --fake-outcome success

# Report (requires --run-id from actual run)
uv run python -m pipeline report --run-id run_actual_id_from_db

# DB migrations
uv run python -m pipeline db migrate
```

---

### Design Log

#### **Q: Two design log files — both need updates?**

**A:** Yes, both:
- `docs/kb/docs/AI_Video_Pipeline_Design_Discussion_Log.md` = chronological discussions
- `docs/kb/docs/AI_Video_Pipeline_Decisions.md` = decision register (ADR index)

Both need ADR-001 through ADR-007 added.

---

### Backup & Recovery

#### **Q: Free remote backup without AWS S3?**
**Best: Rclone + Google Drive (15 GB free)**
```bash
# Install
curl https://rclone.org/install.sh | sudo bash

# Configure
rclone config  # → name: gdrive, type: drive, scope: full

# Backup script (hourly cron)
#!/bin/bash
DB_PATH="/mnt/data/video-pipeline/state/pipeline.sqlite3"
BACKUP_DIR="/tmp/sqlite-backups"
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
sqlite3 "$DB_PATH" ".backup $BACKUP_DIR/pipeline_${TIMESTAMP}.sqlite3"
gzip "$BACKUP_DIR/pipeline_${TIMESTAMP}.sqlite3"
rclone copy "$BACKUP_DIR/pipeline_${TIMESTAMP}.sqlite3.gz" "gdrive:video-pipeline-backups/"
# Cleanup: keep 24 local, 168 remote
```

**Alternative:** Rclone + Mega (20 GB), Dropbox (2 GB), OneDrive (5 GB), pCloud (10 GB)

---

### Quality Gate

#### **Q: Review zone logic fixed?**

**A:** Yes:
- `review_threshold <= score < pass_threshold` → HUMAN_REVIEW
- Pass-only (no review threshold): scores < pass_threshold → FAIL
- Duplicate failure codes eliminated (hash mismatches, missing artifacts, thresholds)

---

#### **Q: Duplicate failure codes — how fixed?**

**A:** Check before appending:
```python
if code not in failure_codes:
    failure_codes.append(code)
```
Applies to: hash mismatches, missing artifacts, threshold failures.

---

### Summary Table

| Topic | Key Point |
|-------|-----------|
| Migration mismatch | Shared DB across worktrees → use separate `PIPELINE_HOME` |
| Missing exports | CLI imports not tested by unit tests → added 8 to `__init__.py` |
| Migration detection | SHA-256 checksum in `schema_migrations` table |
| AUDIO_QC stage | Heavy QC (ffprobe/ML) needs separate budget/retry |
| Major stage | Logical grouping for progress/budget/retry/human gates |
| Fenced lease | Monotonic token prevents stale commits |
| Monthly quota | External enforcement; pipeline tracks/alerts |
| Design log | Update both `Discussion_Log.md` and `Decisions.md` |
| SQLite backup | Litestream to S3 (best) or Rclone + Google Drive (free) |

---

## PR #5 Review — Request-Flow Atlas

**Source:** 81 line comments on PR #5 (`docs/request-flow-atlas`, head `7e2004e`) and 15 follow-up questions.
**Status:** the 81 replies were posted on the PR. No code or reviewed-document
fixes were made in response; follow-ups are tracked as
[GitHub issues](https://github.com/adarshrajanand/video-automation-code/issues).
Each `PR5-NN` ID matches an issue title.

Questions are grouped by topic, not by comment order. The original line and
comment ID are in each `**Source:**` line. Follow-up questions keep their
`F1`–`F15` labels there; inline references such as `L3249` or “see F6” point to
the matching Source line and Q&A in this section.

### Follow-up index

The 15 follow-up questions are integrated into the topic they belong to. Their `F` labels are stable; use this table to find the matching topic.

| ID | Question | Topic |
|----|----------|-------|
| `F1` | Why is the table called `idempotency_records` if it is for capabilities? | Identifiers and Idempotency |
| `F2` | Why is `jobs.idempotency_key` not just `job_id`? | Identifiers and Idempotency |
| `F3` | What does “include the entity type or a formula version in the digest” mean? | Identifiers and Idempotency |
| `F4` | How do I decide what belongs in `ExecutionContext` and what belongs in `CapabilityRequest`? | Execution Model: Stages, Attempts, Jobs, and Leases |
| `F5` | What is a `schema_migrations` example? | Database, Migrations, and Persistence |
| `F6` | What is `policy_ids` actually used for? | Workflow Definitions and Readiness |
| `F7` | Were the `PR5-21` and `PR5-22` references stale? | Documentation, Atlas, and Fixtures |
| `F8` | Should `logical_slot` be renamed to `artifact_key`? | Artifacts, Slots, and Repair |
| `F9` | What is a Protocol, and why only three? | Capabilities, Providers, and Outbox |
| `F10` | How can duplicate provider side effects still happen? Give an example. | Capabilities, Providers, and Outbox |
| `F11` | What is the outbox multi-consumer limitation? Give an example. | Capabilities, Providers, and Outbox |
| `F12` | How does a migration actually run, step by step? | Database, Migrations, and Persistence |
| `F13` | What is updated in place, what is appended, and what decides that? | Execution Model: Stages, Attempts, Jobs, and Leases |
| `F14` | What is a “mutating transition”, in plain terms? | Execution Model: Stages, Attempts, Jobs, and Leases |
| `F15` | How do UUIDs make replay and dedupe harder? Give concrete examples. | Identifiers and Idempotency |

---

### Documentation, Atlas, and Fixtures

#### **Q: “Three ways” lists more than three — what should the heading say?**

**A:** Correct: the table lists seven destinations (golden path, component atlas,
interface catalog, database atlas, state machines, cheat sheets, field atlas).
Change the heading to “Where to look” or “Seven ways to read this document”.
See `PR5-17`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L54, comment `4443723135`.

---

#### **Q: Why is `<` coming?**

**A:** The `<` is a generator bug, not part of the contract type. `type_text()` does
`str(annotation)` and then strips `<class '` and `'>`. An Enum class stringifies
as `<enum 'FailureCode'>`; stripping `'>` leaves `<enum 'FailureCode`.

Fix: detect `Enum` subclasses and render the class name (for example
`FailureCode` or `FailureCode (enum)`), never `str(enum_class)`. See `PR5-01`.

**Source:** PR #5 review, `CONTRACT_FIELD_ATLAS.md` L50, comment `4443585960`.

---

#### **Q: Why are Required and Default “switched” for some rows?**

**A:** There are two separate generator bugs here:

1. The union pipe in `list[...] | None` is not escaped. Markdown treats it as a
   cell separator, so `output_profile_ids` gets five cells and the remaining
   values shift one column right. Required and Default are not actually
   swapped; the extra cell makes them *look* swapped under the header.
2. `enabled_optional_stages` uses `default_factory=list`. `field.default` is
   `PydanticUndefined`, and `default_text()` only calls `field.is_required()`.
   It therefore falls through to `repr(PydanticUndefined)`. It should read
   `field.default_factory` and render `[]` (or call the factory safely).

See `PR5-01`.

**Source:** PR #5 review, `CONTRACT_FIELD_ATLAS.md` L72, comment `4443610614`.

---

#### **Q: Why does `enabled_when` shift the Required/Default columns?**

**A:** Same unescaped union pipe. `workflow.ConditionExpression | None` splits the row
and shifts Required/Default. Not a contract problem.

**Source:** PR #5 review, `CONTRACT_FIELD_ATLAS.md` L143, comment `4443634907`.

---

#### **Q: Why does `failure_code` shift the Required/Default columns?**

**A:** Same unescaped union pipe (`vocabularies.FailureCode | None`). Same column
shift.

**Source:** PR #5 review, `CONTRACT_FIELD_ATLAS.md` L233, comment `4443643800`.

---

#### **Q: Why does `normalized_error` shift the Required/Default columns?**

**A:** Same unescaped union pipe (`base.NormalizedError | None`). Same column shift.

**Source:** PR #5 review, `CONTRACT_FIELD_ATLAS.md` L854, comment `4443678005`.

---

#### **Q: Where is the recorded CLI fixture?**

**A:** It is the SQLite database at
`/tmp/opencode/pipeline-demo/state/pipeline.sqlite3`, created by the
`capabilities invoke` command shown in §2.8. The table in §2.8 lists its real
IDs (`config_d27a…`, `run_e39d…`, `stage_d27a…`, `attempt_a49b…`). It is a
local demo artifact, not checked into the repository. Add a checked-in
reproduction script/sample so readers can regenerate it. See `PR5-20`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L837, comment `4444242936`.

---

#### **Q: Should extension recipes be added to `AGENTS.md`?**

**A:** Agreed. The extension recipes are useful agent guidance. Add them to
`docs/AGENTS.md` (the separate docs repository) or the README later. See
`PR5-19`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L1964, comment `4444649412`.

---

#### **Q: Were the `PR5-21` and `PR5-22` references stale?**

**A:** Correct. The earlier references to `PR5-21` and `PR5-22` were stale
placeholders; no such TODO items existed. The dangling references are fixed:

- queue names -> `PR5-18` (docs expansion), not `PR5-21`;
- `latency_budget_ms` -> `PR5-17` (factual doc fix), not `PR5-22`;
- payload-size tradeoff -> `PR5-18`, not `PR5-22`.

`PR5-21` is now allocated to the capability idempotency table rename and
`PR5-22` to `policy_ids`. No GitHub comment uses these IDs; they are local
tracking IDs.

**Source:** Follow-up `F7`.

---

### Workflow Definitions and Readiness

#### **Q: Is “PURE WORKFLOW” a plane?**

**A:** It is a layer of pure functions (loader, conditions, cardinality, readiness),
not a runtime plane or a separate process. Planes 3 and 4 own durable control
and acceptance state. The diagram label would be clearer as “PURE WORKFLOW
LAYER”. See `PR5-17`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L146, comment `4443836400`.

---

#### **Q: Should a human define the workflow?**

**A:** Yes. The workflow definition is an authored, reviewed, versioned artifact
(`explainer_validation_v1.yaml`), not a runtime system choice. It is loaded
immutably; changing the graph requires a new definition/version. The runtime
resolves policy and readiness, but does not invent the stage graph.

**Source:** PR #5 review, `REQUEST_FLOW.md` L314, comment `4443941994`.

---

#### **Q: What does “No custom tags, no execution” mean?**

**A:** `yaml.safe_load()` constructs only standard YAML scalars, lists, and maps. It
does not instantiate arbitrary Python objects from tags such as
`!!python/object`, and it does not execute workflow content. The workflow is
data only.

**Source:** PR #5 review, `REQUEST_FLOW.md` L385, comment `4444002634`.

---

#### **Q: Resulting object of what?**

**A:** `load_workflow_data()` validates the mapping into a `WorkflowDefinition`
Pydantic model instance. It contains the node graph, selectors, cardinality,
and policy references. It is not a raw dict.

**Source:** PR #5 review, `REQUEST_FLOW.md` L395, comment `4444010778`.

---

#### **Q: What is `policy_ids`?**

**A:** It is the workflow-level list of policy IDs the definition adopts (currently
`default_recovery_v1`). Each node also declares its own
`recovery_policy_id`. `policy_ids` is a reference list, not an inlined policy
body; the policy definitions live in the policy registry/config.

Today it is only duplicate-validated, not resolved or checked against the
registry. The docs validator checks it, but the runtime loader does not.
`policy_ids` currently has almost no runtime effect; see F6 for the intended
use, the precedence question, and `PR5-22`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L402, comment `4444013163`.

---

#### **Q: What do multiple nodes look like?**

**A:** `nodes` is an array of `StageNode` objects. Multiple nodes are simply more
objects in the same array:

```json
"nodes": [
  {
    "node_id": "intake",
    "stage_name": "manual_topic",
    "depends_on": [],
    "cardinality": {"mode": "one_to_one"}
  },
  {
    "node_id": "idea",
    "stage_name": "idea_development",
    "depends_on": ["intake"],
    "cardinality": {"mode": "one_to_one"}
  }
]
```

Each node also carries `schema_version`, `implementation_version`,
`input_selector`, `quality_gate_id`, `recovery_policy_id`, and `enabled_when`.
`depends_on` references earlier node IDs; the loader validates uniqueness,
known references, and the acyclic/topological order.

**Source:** PR #5 review, `REQUEST_FLOW.md` L403, comment `4444023133`.

---

#### **Q: What does each policy look like?**

**A:** The contracts in `src/pipeline/contracts/profiles.py` and `config.py` are:

- `SystemPolicy`: `policy_id`, `version`, `max_parallelism`,
  `max_retry_attempts`, `budget_policy_id`, `allowed_providers`,
  `non_overridable_fields`.
- `BudgetPolicy`: `policy_id`, `version`, `system_cap_minor`,
  `monthly_cap_minor`, `default_run_cap_minor`, `default_stage_cap_minor`,
  `evaluation_cap_minor`, `paid_fallback_enabled`, `reservation_required`.
- `DomainProfile`: `profile_id`, `version`, `content_mode`, `default_locale`,
  `required_stages`, `optional_stages`, `source_policy_id`, `claim_policy_id`,
  `quality_profile_id`, `human_review_policy_id`, `asset_policy_id`.
- `ChannelProfile`: `profile_id`, `version`, `domain_profile_id`, `locale`,
  `audience`, `target_duration_seconds`, `output_profile_ids`,
  `brand_profile_id`, `voice_profile_id`, `publishing_policy_id`.
- `RunOverrides`: `locale`, `target_duration_seconds`, `variant_count`,
  `max_cost_minor`, `enabled_optional_stages`, `output_profile_ids`,
  `quality_profile_id`.
- `EffectiveConfig`: the system/domain/channel/workflow IDs and versions,
  `run_overrides`, `resolved_values`, `source_map`, `config_hash`, and
  `snapshot_artifact_id`.

See `PR5-17` for adding representative JSON examples to §2.2.

**Source:** PR #5 review, `REQUEST_FLOW.md` L441, comment `4444046058`.

---

#### **Q: Who sets `RunOverrides`? Does it change every run?**

**A:** `RunOverrides` are caller-supplied (human/API/CLI), optional, and per run.
Domain/channel profiles provide defaults; system policy bounds what may be
overridden (`non_overridable_fields`). They can change on every run, but the
resolved `EffectiveConfig` is persisted as an immutable snapshot.

There is no production resolver yet: the CLI constructs an empty
`RunOverrides(schema_version="run-overrides.v1")`. Implementing resolution
(with bounds, `resolved_values`, and `source_map`) is `PR5-13`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L447, comment `4444041417`.

---

#### **Q: What is one-to-many? Which stage?**

**A:** `speech` is `one_to_many`: one speech node expands into one `StageInstance` per
manifest child (for example, per scene/segment), not one speech artifact for
the whole run. `visual_plan` is `one_to_one`.

The YAML says:

```yaml
cardinality: {schema_version: cardinality.v1, mode: one_to_many,
              count: null, selection_policy: manifest_children}
```

`manifest_children` means the expected item keys come from the input manifest.

**Source:** PR #5 review, `REQUEST_FLOW.md` L230, comment `4443887933`.

---

#### **Q: What is one-to-many for assets? Is there no many-to-one?**

**A:** `assets` is also `one_to_many`: one required-asset slot/manifest child becomes
one stage instance. `many_to_one` does exist: `composition`,
`long_form_assembly`, and `final_review` are fan-in nodes. One stage instance
consumes multiple dependency outputs. See the YAML lines for those nodes.

**Source:** PR #5 review, `REQUEST_FLOW.md` L234, comment `4443893660`.

---

#### **Q: If one-to-many has count 1, isn't it one-to-one?**

**A:** The final cardinality is one, yes. The mode still describes how the planner
derives keys: `one_to_many` fans out from a manifest, while `count: 1` caps it
at one item. If the count will always be one, `one_to_one` is simpler and this
is a modeling smell. The current YAML keeps `one_to_many` to preserve the
fan-out semantics and allow a later increase without changing the node class.
See `PR5-17`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L269, comment `4443908416`.

---

#### **Q: How does cardinality work for stage instances and attempts?**

**A:** - `one_to_one`: one stage instance, typically one item key.
- `one_to_many`: the planner expands expected item keys from manifest children
  or render chunks; N stage instances are created, each with its own attempts
  and jobs. `count` caps or forces the number.
- `many_to_one`: one stage instance consumes multiple dependency
  instances/outputs (fan-in).

`StageInstance` = node + logical item. `StageAttempt` = one try at that
instance; retries and regenerations increment the attempt number and create a
new attempt. `Job` = claimable transport for one attempt.

So N items produce N instances and up to N attempt/job chains; one item with
retries produces one instance and multiple attempts/jobs. `short_derivative`
with `one_to_many` and `count: 1` produces exactly one instance despite the
fan-out mode.

**Source:** PR #5 review, `REQUEST_FLOW.md` L3353, comment `4445505869`.

---

#### **Q: What is `policy_ids` actually used for?**

**A:** Honest answer: today, almost nothing. `WorkflowDefinition.policy_ids` is only
checked for duplicates:

```python
policy_ids: list[NonEmptyStr] = Field(default_factory=list)

if len(set(self.policy_ids)) != len(self.policy_ids):
    raise ValueError("policy_ids must not contain duplicates")
```

The runtime loader does not resolve the IDs against a registry, and readiness
and execution do not read them. `StageNode.recovery_policy_id` is separately
validated against `RECOVERY_POLICY_IDS`, but execution still uses the default
recovery policy rather than a node-specific lookup. The docs validator checks
`policy_ids` against the recovery-policy registry, so docs and runtime disagree
about how strict the field is.

Intended use: a workflow-level declaration of the policy set/versions the
definition expects. For example:

```yaml
policy_ids: [default_recovery_v1]
nodes:
  - node_id: research
    recovery_policy_id: default_recovery_v1
```

A correct loader would resolve each ID to a typed policy, fail if it is unknown
or the wrong version, and record the resolved policy IDs/versions in
`EffectiveConfig`. That lets a run fail before spending money:

```text
workflow says policy_ids: [default_recovery_v2]
registry only has default_recovery_v1
-> loader rejects the workflow
```

Today that workflow loads, and execution silently uses
`default_recovery_policy()` v1. That is the bug.

There is also a precedence question: workflow-level `policy_ids` versus
node-level `recovery_policy_id`. Pick one rule:

- workflow-level defaults, node-level override; or
- remove workflow-level `policy_ids` and require every node to name its policy.

Recommended: keep the workflow-level list as a manifest, validate it against
the registry, and define node-level `recovery_policy_id` as the override. If
that is not wanted, remove `policy_ids` rather than leaving a dead field.
Tracked as `PR5-22`.

**Source:** Follow-up `F6`.

---

### Execution Model: Stages, Attempts, Jobs, and Leases

#### **Q: How do I map a job to the research stage?**

**A:** Do not parse the job ID. Join the durable rows:

```text
jobs.attempt_id
  -> stage_attempts.attempt_id
  -> stage_attempts.stage_instance_id
  -> stage_instances.node_id          -- "research"
  -> workflow definition / node_id
```

`jobs` has no `node_id` or `stage_instance_id` column. The job is transport; the
attempt and stage instance carry the work identity. §8.3 has the join recipe.

**Source:** PR #5 review, `REQUEST_FLOW.md` L80, comment `4443769413`.

---

#### **Q: Where is the attempt ID?**

**A:** It is directly above the sentence, at line 79 (`attempt_0ed59dd3...`). The
sentence says `capexec_` is derived from the attempt ID:
`deterministic_id("capexec", attempt_id)`. The formula is repeated in §8.4.
`attempt_id` is not a field of `CapabilityRequest`; it is carried by
`ExecutionContext.attempt_id`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L91, comment `4443790742`.

---

#### **Q: How does a stage instance relate to a job?**

**A:** The chain is:

```text
StageInstance 1 -> N StageAttempt 1 -> N Job
```

- `StageInstance` is one logical node/item (`stage_instance_id`).
- `StageAttempt` is one try at that instance (`attempt_id`,
  `stage_instance_id`, `attempt_number`).
- `Job` is the claimable transport row for one attempt (`job_id`,
  `attempt_id`, `queue_name`).

`JobFactory` normally creates one attempt and one job per READY stage item.
Retries/regenerations create a new attempt and a new job. `StageInstance` has
`active_attempt_id`; `jobs` has no direct `stage_instance_id`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L317, comment `4443950981`.

---

#### **Q: How is `ExecutionContext` different from the others?**

**A:** - `EffectiveConfig`: immutable run-level policy/profile snapshot and hash.
- `ReadinessContext`: all durable state passed to the pure readiness function
  (run, workflow, stage instances, manifests, gates, reviews, conditions).
- `ReadinessResult`: readiness output (ready/blocked items, next run status).
- `CapabilityRequest`: provider-neutral description of one capability
  invocation (operation, inputs, payload, requirements, idempotency key).
- `ExecutionContext`: runtime envelope for that invocation (run/stage/attempt/
  config IDs, correlation ID, timeout, allowed data classification).
- `RoutingDecision`: which implementation/provider/model was selected.

They differ by lifecycle and purpose. `ExecutionContext` is not a duplicate of
the request; it carries runtime scope that should not affect the request’s
content fingerprint.

**Source:** PR #5 review, `REQUEST_FLOW.md` L324, comment `4443964040`.

---

#### **Q: What does the unique constraint buy us?**

**A:** Scenario: two callers/event handlers try to create work for the same
`(run_id, node_id, logical_item_key)`. The unique constraint permits exactly
one `stage_instances` row. The second insert raises an integrity error
(translated to `ConflictError`), so the caller can re-read the existing row
instead of executing the work twice.

It is a database backstop, not an upsert. There is no production stage creator
yet. Also, the stage ID formula currently uses only `(run_id, node_id)`, so two
logical items in one node would collide *before* the constraint helps. Fix the
formula and add a creator/upsert path. See `PR5-03`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L524, comment `4444102663`.

---

#### **Q: What other queue names are possible?**

**A:** Only `"default"` is used today (`JobFactory.create_job` default and the CLI
`--queue` default). `queue_name` is a free-form `NonEmptyStr` with no enum or
`CHECK`. Any label works if producers and workers agree, for example `"gpu"`,
`"tts"`, `"render"`, or `"human"`, but none are defined. A worker filters the
exact queue name when `--queue` is passed; there is no additional routing
semantics. See `PR5-18`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L685, comment `4444163633`.

---

#### **Q: What does “builds a request in code” mean?**

**A:** The CLI constructs `CapabilityRequest`, `RoutingDecision`, and
`ExecutionContext` inline from command-line flags plus a synthetic fixture graph
(`test_workflow`, `test_node`, `test_item`). It does not load the workflow YAML,
run readiness, or resolve effective config from profiles. That is why this is a
real end-to-end slice but not a full orchestration path.

**Source:** PR #5 review, `REQUEST_FLOW.md` L766, comment `4444215757`.

---

#### **Q: Why is `ExecutionContext` not part of the request?**

**A:** Because it is the runtime envelope, not work content. It carries run, stage,
attempt, and effective-config IDs, correlation ID, timeout, and allowed data
classification. Those change per attempt and are used for budget, telemetry,
and authorization. Putting them in the request would make the content
fingerprint depend on runtime identity. The separation also lets the same
request be replayed under a new attempt context.

**Source:** PR #5 review, `REQUEST_FLOW.md` L853, comment `4444252974`.

---

#### **Q: What is `usage_id` for?**

**A:** `UsageRecord` has no ID field. `UsageRecordRepository` generates `usage_id`
deterministically from `(capability_execution_id, provider)` to key the usage
table, dedupe repeated writes, and join usage to the execution. It is a storage
key, not domain data.

**Source:** PR #5 review, `REQUEST_FLOW.md` L1023, comment `4444310887`.

---

#### **Q: Is there no `CREATED` for stage execution?**

**A:** Correct. `StageExecutionStatus` starts at `PENDING` (planned, not ready) and
moves to `READY`. `CREATED` belongs to `AttemptStatus`: the attempt row is
created before it is claimed. The stage instance is the logical plan; the
attempt is the first execution object.

**Source:** PR #5 review, `REQUEST_FLOW.md` L2309, comment `4445157932`.

---

#### **Q: What is not updated in place?**

**A:** Updated in place: `jobs`, `stage_instances`, `stage_attempts`,
`idempotency_records` (status/result fields only; the key/fingerprint/inputs
are immutable), `budget_reservations` (status/actual cost only; amounts are
immutable), and `outbox_messages` (status/timestamps; the row is retained).

Mixed: `leases` inserts a new `(job_id, fencing_token)` row per claim, so
ownership history is append-only; a renewal updates the live term’s
`expires_at`/`heartbeat_at`. `artifact_pointers` deactivates the old row and
inserts a new active row; the pointer row is not rewritten.

Append-only/immutable: `workflow_events`, `artifacts` versions,
`quality_evaluations`, `quality_gate_results`, `repair_plans`, human-review
decisions (autoincrement sequence), `recovery_decisions`, `routing_decisions`,
`provider_invocations`, and `usage_records`.

See F13 for the decision rule (“current truth” versus “historical fact” versus
“immutable identity”) and more examples.

**Source:** PR #5 review, `REQUEST_FLOW.md` L2402, comment `4445187302`.

---

#### **Q: What does “old RETRY, new READY” mean?**

**A:** The failed job row is marked `RETRY` and kept for history. `RecoveryManager`
then creates a **new** job row at `attempt_number + 1` in `READY`, available
after the backoff. The stage is `WAITING_RETRY` until the new job is claimable.
“Old” and “new” refer to two job rows, not one row changing status.

**Source:** PR #5 review, `REQUEST_FLOW.md` L2476, comment `4445230070`.

---

#### **Q: What is a mutating transition?**

**A:** Any operation that changes durable execution state: claim, renew, complete,
fail, recover, or cancel. It is the opposite of a pure read/readiness
evaluation. These transitions re-read the job, latest lease, attempt, and
stage inside `BEGIN IMMEDIATE` and require the live owner, fencing token, and
unexpired lease before writing.

**Source:** PR #5 review, `REQUEST_FLOW.md` L2680, comment `4445287891`.

---

#### **Q: What does “append” mean here?**

**A:** `EventOutbox.append()` inserts the `workflow_events` row and its
`outbox_messages` row in one transaction. “Caller retries append” means that if
the process crashes before the transaction commits, nothing durable was
written, so the caller can call append again. It is not appending to a file or
a log.

**Source:** PR #5 review, `REQUEST_FLOW.md` L2702, comment `4445298668`.

---

#### **Q: How do I decide what belongs in `ExecutionContext` and what belongs in `CapabilityRequest`?**

**A:** Use one question: **would the provider produce a different artifact or result
if this value changed?**

- Yes -> it belongs in the request, and normally in the request fingerprint.
- No, it only changes where/when/by whom/how long -> it belongs in the
  context.

Concrete examples:

**Request (content/result-affecting):**

- `capability`: speech generation versus research.
- `operation_version` and `payload_schema_version`.
- `payload`: text, voice ID, model settings, prompt inputs.
- `input_artifact_ids`: exact script/version the provider consumes.
- `requirements.locale`: changes language/accent/content.
- `requirements.quality_requirement`: draft versus broadcast can change routing
  and acceptance.
- `requirements.required_features`: feature set the provider must support.
- `requirements.cost_limit_minor`: a replay with a different budget limit is
  not the same allowed operation.
- `requirements.latency_requirement`: if it constrains which provider/output
  quality is acceptable, it is part of the request.

**Context (execution scope/tracing):**

- `run_id`, `stage_instance_id`, `attempt_id`: where this work sits, not what
  it produces.
- `correlation_id`: tracing.
- `effective_config_id`: which immutable policy snapshot was resolved; the
  snapshot’s content-affecting values still belong in the request payload or
  config hash.
- `timeout_seconds`: an operational bound. A retry with a longer timeout should
  reuse the same logical request and idempotency key.
- `allowed_data_classification`: a permission gate on the execution path.

The context may still influence the **idempotency key**. For example, the key
can include `run_id`/`stage_instance_id` so the same text in two runs is two
logical operations. That does not mean those IDs belong in the content
fingerprint.

Current implementation gap: `payload_fingerprint` covers only `request.payload`.
The executor manually compares `capability`, `operation_version`,
`input_artifact_ids`, `required_features`, and `locale`, but it does **not**
compare `quality_requirement`, `latency_requirement`,
`data_classification`, `cost_limit_minor`, or `payload_schema_version`. So this
replay would be accepted today even though the budget changed:

```text
first request:  cost_limit_minor=100, payload={...}, key=idem_x
retry:          cost_limit_minor=1000, same payload, same key
```

The fix is to fingerprint one canonical “semantic request” object containing
every request field that can affect the result or the permission to run, and
exclude only the context fields. Do not fingerprint the whole Pydantic model
including `runtime_context` unless you first decide that field is semantic.
`CapabilityRequest.runtime_context` is currently unused; either move anything
that affects output into `payload` or remove it. Tracked as `PR5-23`.

**Source:** Follow-up `F4`.

---

#### **Q: What is updated in place, what is appended, and what decides that?**

**A:** The rule is about **identity and history**, not table size:

- If there is one current truth per identity and readers only want the latest,
  update in place.
- If the old value must remain explainable, auditable, or replayable, append a
  new row.
- If the row is an immutable identity or content snapshot, never update it;
  create a new version.

Examples:

**Update in place (current-state projection):**

- `workflow_runs.status`, `updated_at`.
- `stage_instances.execution_status`, `acceptance_status`, `active_attempt_id`.
- `stage_attempts.status`, `worker_id`, `lease_expires_at`, `finished_at`.
- `jobs.status`, `claimed_by`, `lease_expires_at`, `delivery_count`.
- `idempotency_records.status`, result linkage, `completed_at`. The key,
  fingerprint, input artifacts, and capability are immutable.
- `budget_reservations.status`, `actual_cost_minor`, `settled_at`. The reserved
  amount is immutable; a new operation gets a new reservation.
- `outbox_messages.status`, attempts, delivery timestamps. The row is retained,
  not deleted.
- `human_reviews.status`, `resolved_at`.

**Append (historical fact):**

- `workflow_events`: every event is a fact; never rewrite an old event.
- `artifacts`: a regeneration creates version 2; version 1 remains for lineage
  and rollback.
- `artifact_pointers`: activating a new pointer deactivates the old row and
  inserts a new one; the old pointer row is retained. The `active` flag is
  updated, but the pointer identity/content is not rewritten.
- `quality_evaluations` and `quality_gate_results`: a re-evaluation is a new
  evaluation/result; do not overwrite a prior FAIL with a PASS.
- `repair_plans`: each plan is a decision record.
- `human_review_decisions`: each decision is a new sequence row.
- `recovery_decisions`: each recovery choice is a new audit row.
- `inbox_receipts`: one row per `(consumer_id, event_id)`.
- `routing_decisions`, `provider_invocations`, `usage_records`: each invocation
  is a fact.

**Immutable identity/snapshot:**

- `workflow_definitions`: a new version is a new definition.
- `effective_configs`: the resolved snapshot is immutable.
- artifact content (`uri`, `sha256`, `size_bytes`): a new artifact version, not
  an edit.

Borderline cases:

- `leases`: a new claim inserts a new `(job_id, fencing_token)` row, so the
  ownership history is append-only. A renewal updates the current term’s
  `expires_at`/`heartbeat_at`; that is an update to the live term, not a
  rewrite of history. The latest term wins.
- `idempotency_records`: status is current state, but the request identity is
  immutable. A retry does not rewrite the fingerprint.
- `artifact_pointers`: the row is a historical pointer record; only the
  `active` flag changes when it is superseded.

The test to apply: “If I delete the old value, can I still explain what
happened and reproduce the decision?” If no, append. “Do all readers want only
the latest, and is the old value uninteresting?” Then update in place.

**Source:** Follow-up `F13`.

---

#### **Q: What is a “mutating transition”, in plain terms?**

**A:** It is a write that changes durable execution state and must be authorized by
the current owner. A read/readiness check is not a mutating transition.

Concrete fencing example:

```text
Worker W1 claims job J -> lease token 7, expires at 10:01.
W1 stalls.
Worker W2 recovers the expired lease and claims J -> token 8.
W1 wakes up and calls complete_success(J, token=7).
```

Without a fence, W1’s `UPDATE jobs SET status='ACKED'` would overwrite W2’s
work and record W1’s stale output. With `verify_live_claim()` inside
`BEGIN IMMEDIATE`:

```text
re-read job J
re-read latest lease -> token 8
compare owner/token/expiry
token 7 != 8 -> REJECTED: FENCING_TOKEN_MISMATCH
```

W1’s result is discarded; W2 remains the owner. That is the point of the
fencing token.

The claim path does this in one transaction:

1. `BEGIN IMMEDIATE` takes the write lock before reading state, so no other
   writer can change the job between the decision and the write.
2. Recover expired leases (return them to READY and record a recovery
   decision).
3. Select the next READY job.
4. Read the job, attempt, stage, and latest lease.
5. Compute the next fencing token (`latest + 1`).
6. Insert the new lease row; update the attempt, stage, and job with the owner,
   token, and expiry.
7. Commit. A crash rolls the whole claim back; there is no half-claimed job.

`renew()` only extends the caller’s own live term. `complete_success()` accepts
an idempotent repeat only when the job is already ACKED with the same token;
otherwise it requires a live claim. `recover_expired()` treats an expired term
as lost ownership and does not let the old owner commit.

Mutating transitions include claim, renew, start, complete, fail, recover,
cancel, outbox ack, and idempotency status changes. Pure reads include
readiness evaluation, status/report queries, and list commands. Not every write
needs a fencing token: a quality evaluation write needs idempotency, but it is
not owned by a worker lease.

**Source:** Follow-up `F14`.

---

### Identifiers and Idempotency

#### **Q: Why `idem_job_` instead of just `idem_`?**

**A:** They dedupe different things:

- `idem_job_...` is the value in `jobs.idempotency_key`. It is produced by
  `idempotency_key("job", run_id, node_id, item_key, attempt_number)` and makes
  repeated job creation for the same logical attempt a no-op.
- `idem_...` is the primary key of `idempotency_records`. It dedupes one
  capability operation and stores the request fingerprint, status, and result
  linkage.

Both are opaque. The extra prefix keeps the two dedupe boundaries visible in
logs and avoids confusing a job key with an operation key.

**Source:** PR #5 review, `REQUEST_FLOW.md` L81, comment `4443778200`.

---

#### **Q: Is deriving IDs like this fine?**

**A:** The derivation is stable as long as its input parts are stable. That is the
intent: the digest identifies a logical unit, and the prefix identifies the
record type. The real risks are:

- changing a parent formula (all children change);
- reusing a key for a different semantic unit;
- two record types sharing a digest (intentional here, but easy to confuse).

The code never parses an ID to recover meaning. Reuse is caught by unique
constraints and by the idempotency fingerprint/operation-version checks. If we
want stronger isolation, add an ID-formula version or include the entity type
in the digest; that does not remove the parent dependency. This is a design
contract worth writing down rather than changing ad hoc. See `PR5-11`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L92, comment `4443797295`.

---

#### **Q: Do prefixes drive if/else logic?**

**A:** No. There is no `if id.startswith("job_")` dispatch. Repositories are typed
(`JobRepository`, `StageInstanceRepository`, and so on) and query their own
tables by key columns. The prefix table is a human/debugging lookup index; IDs
are opaque to callers.

**Source:** PR #5 review, `REQUEST_FLOW.md` L101, comment `4443810890`.

---

#### **Q: Deterministic IDs depend on other IDs; isn't that flaky?**

**A:** The dependency is deliberate and explicit. `attempt_` and `job_` share a
digest because they identify the same `(stage_id, attempt_number)` logical unit;
only the prefix differs. `capexec_` depends on `attempt_id`; `idem_`, `route_`,
and `inv_` depend on `capexec_id`. This is testable and reproducible. It is not
a random or hidden dependency.

What would make it flaky is changing a parent formula or treating the digest as
a stable public API without versioning. Use `new_id()`/UUID where there is no
natural key. See `PR5-11`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L125, comment `4443846488`.

---

#### **Q: Why `qgr_` twice?**

**A:** A real bug. `deterministic_id("qgr", ...)` already returns `qgr_<digest>`, and
`_create_gate_result()` prepends `qgr_` again. The same pattern affects `eval_`
and `repair_`. The IDs are stable and unique but wrong-shaped. See `PR5-04`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L1208, comment `4444395679`.

---

#### **Q: Why `eval_` twice?**

**A:** Same bug in `DeterministicCheckEvaluator`: `deterministic_id("eval", ...)`
returns `eval_<digest>`, then the constructor prepends `eval_`. Note that some
semantic/media/speech evaluators use `f"eval_{uuid4().hex[:12]}"`, which is
single-prefixed but random; the documentation should not claim every evaluator
path is double-prefixed. See `PR5-04` and `PR5-17`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L1223, comment `4444398438`.

---

#### **Q: If it is a quirk, should it be fixed?**

**A:** Yes. The “do not fix casually” warning was about persisted production identity.
There is no production data here, so fix the three deterministic call sites
(`eval`, `qgr`, `repair`) to use the helper result directly, update tests,
fixtures, and example IDs, and add regression assertions. No migration is
needed. See `PR5-04`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L1253, comment `4444412863`.

---

#### **Q: Is the projection drift bad? Must it be corrected?**

**A:** Yes. It is a real bug, not just an aesthetic issue. The DDL columns exist, but
`IdempotencyRecordRepository.columns` omits five of them, so the extracted
columns keep their defaults while the payload has the correct values. Any SQL
filtering, joining, or sorting on those columns is wrong.

Fix by adding `operation_version`, `input_artifact_ids`, `required_features`,
`locale`, and `result_artifact_ids` to `columns`, teaching `_column_value()` to
JSON-encode list values (it currently handles only bool/Enum/datetime), and
backfilling or validating existing rows from the payload. There is no production
data, so this is low risk. See `PR5-02`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L949, comment `4444290889`.

---

#### **Q: Is the budget-reservation update conditional?**

**A:** Yes. The executor only creates/reserves a budget row when
`requirements.cost_limit_minor` is set **and** a `BudgetReservationRepository`
is supplied. The recorded CLI fixture does neither, so it has no
`budget_reservations` row. Separately, if a prior reservation is `RELEASED`, a
new reservation with the same `(idempotency_key, scope_type, scope_id)` updates
that row in place instead of inserting (the unique constraint would otherwise
reject it). That update is not the normal first path.

**Source:** PR #5 review, `REQUEST_FLOW.md` L958, comment `4444298992`.

---

#### **Q: Where does idempotency first appear?**

**A:** Two levels:

1. At job creation, `jobs.idempotency_key` (`idem_job_...`) makes repeated
   attempt/job creation idempotent.
2. At executor entry, inside the first transaction, the executor does
   `IdempotencyRecordRepository.get(key)` or creates a `RESERVED` record
   **before** budget reservation, routing/execution persistence, or provider
   invocation. That record is the replay boundary for provider side effects.

So the answer depends on whether you mean transport-level or operation-level
idempotency.

**Source:** PR #5 review, `REQUEST_FLOW.md` L1041, comment `4444318332`.

---

#### **Q: Why only the first 32 hex characters?**

**A:** 32 hex characters = 128 bits of SHA-256. That is ample for run-scale uniqueness
(the birthday bound is around 2^64) while keeping IDs readable and compact. The
full SHA-256 remains available where content addressing needs it. Truncation is
a display/storage tradeoff, not a security claim.

**Source:** PR #5 review, `REQUEST_FLOW.md` L1809, comment `4444580430`.

---

#### **Q: If every table is idempotent, why `idempotency_records`?**

**A:** Database constraints make **writes** idempotent: they prevent duplicate rows.
They do not prevent duplicate provider side effects. `idempotency_records`
stores the operation key, request fingerprint, status, and result linkage so a
replay returns the prior result or rejects a conflicting request. That is
semantic idempotency, which a unique constraint cannot provide.

The table is capability-specific, so it should be named
`capability_idempotency_records`. See F1 and `PR5-21`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L2159, comment `4444730847`.

---

#### **Q: Won’t storing the full payload increase table size?**

**A:** Yes. The payload duplicates the extracted columns. The tradeoff is deliberate:
the payload is the canonical, versioned contract (safe evolution, full audit),
while extracted columns are small indexed projections for filtering and
ordering. At local SQLite scale this is acceptable. If it grows, normalize the
hot fields or compress payloads. This is a documented tradeoff, not an
immediate change. See `PR5-18`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L2184, comment `4444736333`.

---

#### **Q: Why not write those columns?**

**A:** Because `IdempotencyRecordRepository.columns` omits them. `_extracted()` only
emits the listed columns, so the INSERT does not include them and SQLite applies
the DDL defaults. The payload has the true values. This is the same projection
drift as L949; fix `PR5-02`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L2920, comment `4445386441`.

---

#### **Q: Why deterministic IDs instead of UUIDs?**

**A:** Deterministic IDs give reproducibility, idempotent creation, stable
fixtures/tests, cross-run dedupe, and visible relationships. UUIDs give
independent uniqueness but are not reproducible and make replay/dedupe harder.
We still use random IDs (`new_id`, some reports) where there is no natural key
or independence is required. The tradeoff is that deterministic identity
couples to its formula, so formula changes need versioning/migration.

Concretely: a retried `create_job()` with a deterministic ID hits the primary
key and can re-read the existing job; with a UUID it creates a second job and a
second provider call. A repeated event append with a deterministic `event_id`
is a conflict; with a UUID it is a new event and the inbox cannot dedupe it.
See F15 for the crash/replay examples.

**Source:** PR #5 review, `REQUEST_FLOW.md` L3099, comment `4445456891`.

---

#### **Q: Why `idempotency_key` in `idem_job_` but not `idem_`?**

**A:** `idem_job_...` is not a primary key; it is the value stored in
`jobs.idempotency_key` to dedupe job creation. `idem_...` is the primary key of
`idempotency_records`, so the column *is* the key; there is no separate
`idempotency_key` column beyond the PK. Both are keys, for different tables and
different units.

`jobs.idempotency_key` is not a second `job_id`. `job_id` names the row;
`idempotency_key` names the enqueue request that creates it. They are 1:1
today, but they are different identities. See F2.

**Source:** PR #5 review, `REQUEST_FLOW.md` L3117, comment `4445425746`.

---

#### **Q: Why share a digest?**

**A:** The digest identifies the logical unit; the prefix identifies the record type.
`config_`, `package_`, and `corr_` all derive from `run_id`; `attempt_` and
`job_` from `(stage_id, attempt_number)`; `idem_`, `route_`, and `inv_` from
`capexec_id`. Sharing avoids duplicate hashing and makes relationships visible
in logs. `op_` has its own digest because it derives from the payload
fingerprint.

This is only safe because IDs are opaque and prefixes are never parsed. If a
formula changes, include an entity/formula version in the digest so old and new
IDs are different namespaces. That does not remove parent dependency. See F3
and `PR5-11`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L3133, comment `4445444868`.

---

#### **Q: “This should be fixed” — what is wrong with the stage ID formula?**

**A:** Agreed. `stage_` must include `logical_item_key`; otherwise two items in one
node get the same ID while the table’s unique constraint allows both rows. Fix
the formula/helper, use it in the stage creator, and add a multi-item
regression test. See `PR5-03`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L3147, comment `4445468603`.

---

#### **Q: “Nothing is in prod, let us fix it” — does that apply to the double prefixes?**

**A:** Agreed. Since there is no production data, change `eval_`, `qgr_`, and `repair_`
call sites to use the helper result directly, update golden examples/tests/docs,
and add assertions that IDs contain exactly one prefix. No migration/backfill.
See `PR5-04`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L3150, comment `4445472538`.

---

#### **Q: Why is the table called `idempotency_records` if it is for capabilities?**

**A:** Short answer: you are right; it is a capability-specific table and should be
named like the other capability tables. The current name is too broad.

The table stores exactly one kind of record:

- `capability` and `operation_version`;
- `request_fingerprint`;
- `capability_execution_id`;
- `provider_invocation_id` and `provider_operation_id`;
- `result_artifact_ids`.

It is written only by `CapabilityExecutor`. Jobs, outbox delivery, repairs, and
publication have their own dedupe mechanisms. Calling this table
`idempotency_records` suggests a generic, cross-domain ledger, which it is not.
A future job/outbox idempotency table would then either reuse these
capability-shaped columns or create a confusing second “idempotency_records”.

The concrete rename is:

```sql
-- 000N_rename_capability_idempotency_records.sql
-- Use the next free version; for example 0003 if the artifact_key rename
-- lands first.
ALTER TABLE idempotency_records
    RENAME TO capability_idempotency_records;
```

SQLite keeps indexes and foreign-key references attached to the renamed table,
but index names are not renamed automatically. Drop and recreate the two index
names if they should also be capability-scoped:

```sql
DROP INDEX idx_idempotency_status;
DROP INDEX idx_idempotency_capability_execution;

CREATE INDEX idx_capability_idempotency_status
    ON capability_idempotency_records (status);
CREATE INDEX idx_capability_idempotency_execution
    ON capability_idempotency_records (capability_execution_id);
```

Then update `IdempotencyRecordRepository.table`, the migration tests, the
atlas/docs, and any raw SQL. Keep the primary-key column `idempotency_key`:
within this table it really is the capability idempotency key. Renaming the
column too would ripple through `CapabilityRequest` and the contract for no
semantic gain.

`capability_operations` is a possible alternative, but it sounds like an
operation history/log. The table stores dedupe state for one capability
operation, not a history of operations. `capability_idempotency_records` says
what it is. Tracked as `PR5-21`.

**Source:** Follow-up `F1`.

---

#### **Q: Why is `jobs.idempotency_key` not just `job_id`?**

**A:** Because they answer different questions:

- `job_id` identifies the job row: “which job is this?”
- `idempotency_key` identifies the enqueue request: “have I already created
  this unit of work?”

Today both are deterministic and one-to-one, so the extra column looks
redundant. They are still different identities:

```text
job_id         = job_<H(stage_instance_id, attempt_number)>
idempotency_key = idem_job_<H("job", run_id, node_id, item_key, attempt_number)>
```

The key is the caller’s dedupe claim. The job ID is the row identity created by
the factory. If a producer crashes after `create_job()` commits but before it
reads the response, it retries with the same key:

```text
create_job(stage, attempt_number=1)
  -> job_id=job_abc..., idempotency_key=idem_job_def..., created=True
crash
create_job(stage, attempt_number=1)
  -> lookup idem_job_def... -> job_abc..., created=False
```

That retry does not need to know `job_abc...` in advance. It only needs the
logical key, which is derived from the work it is trying to enqueue.

If the column were named `job_id`, it would collide with the existing primary
key and imply that the dedupe token is the row identity. If the column were
removed and dedupe relied only on the `job_id` primary key, changing the job-ID
formula would silently stop detecting duplicates, because the same logical
enqueue would produce a different primary key.

Rule of thumb: a primary key names the row; an idempotency key names the
request that creates the row. They can coincide, but they are not the same
concept. Keeping both also leaves room for a caller-supplied key later.

**Source:** Follow-up `F2`.

---

#### **Q: What does “include the entity type or a formula version in the digest” mean?**

**A:** `deterministic_id(prefix, *parts)` hashes only `parts`; the prefix is not in the
digest. So these two IDs have the same 32-hex suffix:

```text
deterministic_id("config", run_id)  -> config_<H(run_id)>
deterministic_id("package", run_id) -> package_<H(run_id)>
```

That is intentional for related records: `config_`, `package_`, and `corr_` can
share a digest so the relationship is visible in logs.

**Entity type in the digest** means adding a literal type marker to the hashed
input:

```text
deterministic_id("config", "config", run_id)
  -> config_<H("config", run_id)>
```

Now the suffix differs by entity even if the other inputs are the same. This is
defense in depth if a prefix is stripped, a digest is stored alone, or two
formulas accidentally use the same inputs. It breaks deliberate shared-digest
relationships, so it should be applied per ID family, not blindly everywhere.

**Formula version in the digest** means adding a version marker when the ID
formula changes:

```text
v1: stage_<H(run_id, node_id)>
v2: stage_<H("stage.v2", run_id, node_id, item_key)>
```

Without the marker, `stage_...` means two different formulas depending on when
the row was created. You cannot tell which formula produced an ID, and a
migration cannot reliably map old IDs to new ones. With the marker, old and new
IDs are distinct namespaces, and the migration is explicit.

This does **not** remove parent dependency. If an attempt ID is derived from a
stage-instance ID:

```text
attempt = H(stage_instance_id, attempt_number)
```

then changing the stage-ID formula changes every attempt ID too. To decouple
them, derive the child directly from stable inputs:

```text
attempt = H(run_id, node_id, item_key, attempt_number)
```

That repeats the parent’s inputs and gives up the automatic “child changes when
parent changes” property. It is a design tradeoff, not something a version
marker fixes.

Since there is no production data, the immediate plan is to fix the known
formula bugs now (`PR5-03`) and document the formulas (`PR5-11`). Add version
markers only when a formula actually changes after data exists.

**Source:** Follow-up `F3`.

---

#### **Q: How do UUIDs make replay and dedupe harder? Give concrete examples.**

**A:** Deterministic ID/key:

```text
create_job(stage, attempt=1) -> job_abc..., key=idem_job_def...
retry the same call        -> key lookup finds job_abc...
                              created=False
```

Even if the lookup were skipped, the deterministic `job_id` primary key turns
the second insert into a `ConflictError` instead of a duplicate row.

UUIDv4:

```text
create_job(stage, attempt=1) -> job_9f3a...
retry the same call        -> job_7c21...
INSERT succeeds             -> two jobs for one logical unit
```

Now the database has two claimable jobs. Two workers can claim them and call
the provider twice. The UUID did not encode “this is the same logical work,” so
you need a separate unique natural key `(stage_instance_id, attempt_number)` to
catch it. At that point the UUID is just a random row label; the dedupe work is
elsewhere.

Other examples:

- **Artifact regeneration:** a deterministic stage/artifact ID lets a rerun
  find the existing version and either return it or create version 2. A UUID
  creates a new stage instance/artifact with no link to the first, so
  downstream fan-in sees duplicates.
- **Event append:** if callers derive `event_id` from
  `(run, type, stage, attempt)`, a repeated append is a primary-key conflict.
  The current `EventOutbox.append()` takes the envelope as supplied, so this
  depends on the producer. A random UUID creates a second event and outbox row;
  the inbox only dedupes by `event_id`, so a different UUID is a different
  event and the consumer runs twice.
- **Golden tests:** deterministic IDs let fixtures assert exact values and make
  parent/child relationships visible. UUIDs force tests to normalize or ignore
  IDs, which can hide a broken relationship (for example, an attempt pointing
  at the wrong stage).
- **Crash recovery:** after a crash, the caller may not know whether the first
  call committed. A deterministic key lets it recompute the same ID and probe;
  a UUID requires a stored request->UUID mapping, and if that mapping write was
  not atomic with the effect, the retry still duplicates.

UUIDv5 (name-based) is deterministic and avoids the random-retry problem, but
it is still a hash namespace: you must choose the name inputs, and formula
changes have the same versioning problem. The project’s `deterministic_id` is
essentially a truncated SHA-256 with a prefix, so it has the same tradeoff.

Random IDs are still right where there is no natural key and independence is
desired: request IDs, correlation IDs, some report IDs. The rule is: use a
deterministic ID when the identity is derived from durable inputs; use a random
ID when the identity is genuinely new.

**Source:** Follow-up `F15`.

---

### Database, Migrations, and Persistence

#### **Q: Why does `capabilities list` migrate the DB?**

**A:** It should not. `capabilities list` has no database need, but the
implementation calls `_migrated_database()`, which opens the DB and runs
`MigrationRunner.migrate()`. That is an accidental side effect of sharing the
helper. Make the command read-only. See `PR5-08`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L283, comment `4443928026`.

---

#### **Q: What is `synchronous=NORMAL`?**

**A:** It is SQLite’s fsync policy. In WAL mode, `NORMAL` avoids an fsync on every
commit and syncs at checkpoints. Commits are fast; a power loss can lose recent
transactions, but the database remains consistent. `FULL` is safer and slower.
The local baseline chooses `NORMAL`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L346, comment `4443985940`.

---

#### **Q: Do these steps run every time?**

**A:** Every connection opened by `Database` runs the PRAGMAs (`busy_timeout`,
`foreign_keys`, WAL, `synchronous=NORMAL`). `MigrationRunner.migrate()` runs
only when a command calls it: `_migrated_database()` users, `db migrate`, and
the human-review commands. `quality evaluate` opens `Database` directly and
currently skips migration (that is a bug, see L3249).

`migrate()` is idempotent when up to date: it creates/reads
`schema_migrations` and applies only pending files.

**Source:** PR #5 review, `REQUEST_FLOW.md` L347, comment `4443980491`.

---

#### **Q: What is the `schema_migrations` row for?**

**A:** `schema_migrations` is the migration ledger: one row per applied file with
`version`, `name`, `checksum`, and `applied_at`. It lets the runner:

- know which files are already applied;
- detect an edited applied migration by checksum;
- enforce a contiguous, prefix-valid history;
- apply only pending files.

Without it, `migrate()` could not be idempotent or fail closed on drift.

**Source:** PR #5 review, `REQUEST_FLOW.md` L365, comment `4443992451`.

---

#### **Q: Why migrate on open?**

**A:** That row describes the **target**, not current behavior: current
`quality evaluate` opens `Database` directly and does not migrate; the proposed
fix is “migrate on open” so the command is self-sufficient on a fresh database.
Today a fresh DB fails with `no such table: quality_evaluations`. See `PR5-05`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L1182, comment `4444388352`.

---

#### **Q: What does `CHECK` mean here?**

**A:** It is a SQLite table-level `CHECK` constraint, for example
`CHECK (complete IN (0,1))` or `CHECK (end_frame > start_frame)`. It rejects
invalid rows at write time. It is unrelated to quality checks.

**Source:** PR #5 review, `REQUEST_FLOW.md` L2015, comment `4444691914`.

---

#### **Q: Explain migrations in more detail**

**A:** - **Why:** schema changes must be ordered, repeatable, and tamper-evident.
- **What:** `NNNN_name.sql` files shipped with the package; ledger
  `schema_migrations(version, name, checksum, applied_at)`.
- **How:** discover contiguous versions; read applied rows; verify the applied
  history is a prefix and each checksum matches; for each pending file,
  `BEGIN IMMEDIATE`, execute statements, insert the ledger row, commit.

Editing an applied file raises `MigrationChecksumError`; a missing file or gap
raises `MigrationError`. It does not use `executescript()` (which would commit
implicitly). Up to date, it is a cheap read-only check.

For a concrete ledger row, a `0002` example, and the failure cases, see F5 and
F12.

**Source:** PR #5 review, `REQUEST_FLOW.md` L2259, comment `4445139731`.

---

#### **Q: Why are timestamps written two different ways?**

**A:** Different paths use different serializers: `canonical_datetime()`/some code
emits `...Z`, while `datetime.isoformat()` or Pydantic’s default JSON emits
`+00:00`. Both are valid ISO-8601, but lexicographic string ordering differs,
so `ORDER BY created_at` can misorder rows. Canonicalize every persisted
timestamp to one representation (`Z`) and test both paths. See `PR5-07`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L2780, comment `4445351702`.

---

#### **Q: What is a `schema_migrations` example?**

**A:** The recorded demo database has this actual row:

```text
version | name    | checksum (first 8) | applied_at
1       | initial | 63f1c279           | 2026-11-02T03:27:25.389957Z
```

It is one row per applied migration file, not one row per SQL statement. The
runner uses it like this:

1. Discover local files `0001_initial.sql`, `0002_....sql`, ... and require
   contiguous versions starting at 1.
2. Create `schema_migrations` if it does not exist.
3. Read applied rows ordered by `version`.
4. Check that the applied history is a prefix of the local set. A database at
   version 2 can accept local files 1, 2, 3; it cannot accept a gap or a local
   set that is missing an already-applied file.
5. Compare `name` and `checksum` for every applied row. If `0001_initial.sql`
   changed after it was applied, refuse to run with `MigrationChecksumError`.
6. For each pending file: `BEGIN IMMEDIATE`, execute its statements, insert the
   ledger row, commit.

Example: add `0002_rename_artifact_key.sql` to the package. On the old database:

```text
$ pipeline db status --database /tmp/opencode/pipeline-demo/state/pipeline.sqlite3
Current version: 1
Applied migrations:
  0001_initial (63f1c279...) applied at 2026-11-02T03:27:25.389957Z
Pending migrations:
  0002_rename_artifact_key (a1b2c3d4...)
```

Run `db migrate`; only 0002 executes and one new row is inserted. Run it again;
it is a no-op. If someone edits 0001, `db status` fails the checksum check. The
fix is to restore 0001 and put the change in a new `0003_...sql`.

`schema_migrations` is per database file. A different `PIPELINE_HOME` points at
a different SQLite file with its own ledger.

**Source:** Follow-up `F5`.

---

#### **Q: How does a migration actually run, step by step?**

**A:** The runner is deliberately small:

```python
status = runner.status()          # read + validate applied history
for migration in status.pending:
    with database.transaction() as connection:
        execute_sql_statements(connection, migration.path.read_text())
        connection.execute(
            "INSERT INTO schema_migrations "
            "(version, name, checksum, applied_at) VALUES (?, ?, ?, ?)",
            (...),
        )
```

Details that matter:

- Files are `NNNN_name.sql`, contiguous from `0001`.
- `status()` creates `schema_migrations` if needed, then validates the applied
  rows against local files: prefix, name, checksum.
- Each pending file runs in its own `BEGIN IMMEDIATE` transaction. If any
  statement fails, the file’s changes and its ledger row roll back together.
- The runner does not use `executescript()`, because that would commit
  implicitly. It splits on complete SQL statements and executes them inside the
  caller’s transaction.
- `applied_at` is audit data, not ordering data. Ordering is `version`.
- Running `migrate()` when up to date is a read-only check and a no-op.

Adding a migration, concretely:

```text
1. Add src/pipeline/storage/migrations/0002_rename_artifact_key.sql
2. Run: pipeline db status --database <db>
   -> 0002 is listed as pending
3. Run: pipeline db migrate --database <db>
   -> 0002 executes; schema_migrations gains row (2, rename_artifact_key, ...)
4. Run status again
   -> current version 2; pending none
```

Failure examples:

- Edit `0001_initial.sql` after it was applied -> checksum mismatch; restore
  the file and add `0003_...sql`.
- Delete `0001_initial.sql` -> “applied migration 1 has no local file”.
- Add `0003` without `0002` -> “migration versions must be contiguous”.
- Put `BEGIN`/`COMMIT` inside a migration file -> the runner owns the
  transaction; remove them.

`quality evaluate` currently bypasses this and opens `Database` directly, which
is why a fresh database fails with `no such table`. That is `PR5-05`, not a
migration-runner bug.

**Source:** Follow-up `F12`.

---

### Capabilities, Providers, and Outbox

#### **Q: Why does a capability need `input_artifact_ids`?**

**A:** They bind the request to exact input artifact versions for provenance,
idempotency validation, and replay. They may be empty for an operation with no
artifact inputs; the CLI fixture uses `[]`. On key reuse the executor compares
the list, and the idempotency record stores it.

**Source:** PR #5 review, `REQUEST_FLOW.md` L811, comment `4444221315`.

---

#### **Q: Which payload’s fingerprint is this?**

**A:** It is the fingerprint of `request.payload`, the capability’s input payload. The
CLI computes `sha256_text(json.dumps(payload, sort_keys=True))`; the executor
only compares the fingerprint for equality and does not inspect the payload.
It does not cover requirements or runtime context.

**Source:** PR #5 review, `REQUEST_FLOW.md` L812, comment `4444226847`.

---

#### **Q: What do `requirements` mean? Where is effective config?**

**A:** `requirements` are per-request hard eligibility constraints: `capability`,
`required_features`, `locale`, `quality_requirement`, `latency_requirement`,
`data_classification`, and `cost_limit_minor`.

The effective config is **not** part of `CapabilityRequest`. It is the
run-level policy snapshot; its ID is `ExecutionContext.effective_config_id`.
The CLI inserts a fixture `EffectiveConfig` before invoking the executor.

Doc bug: the golden example in §2.8.1 shows `latency_budget_ms`, but the
contract has no such field (and extra fields are forbidden). It should be
`latency_requirement` (a string) or be removed. See `PR5-17`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L813, comment `4444230048`.

---

#### **Q: Why is quota not reconcilable? Does dead letter solve it?**

**A:** “Reconcile” here means resolving an **ambiguous external outcome** by checking
provider state: did the call happen, and what result did it produce? It is not
“retry later”.

`QUOTA` is a definite policy refusal with no unknown side effect, so it is
`retryable=False` and there is nothing to reconcile. A dependency being down
should classify as `TRANSIENT` (retryable) and use backoff; after the retry
budget is exhausted, policy chooses `WAIT_HUMAN` or `FAIL`. Dead letter is
terminal and does not retry, so it does not solve a later quota reset. A
quota-reset retry is a new scheduling decision and is not implemented.

**Source:** PR #5 review, `REQUEST_FLOW.md` L1124, comment `4444351379`.

---

#### **Q: Why only three Protocols?**

**A:** They are the only real plugin/handler boundaries:

- `Evaluator` — quality check implementations.
- `JobHandler` — worker job execution.
- `OutboxDeliveryHandler` — outbox consumer effect.

Everything else is a concrete class or function, either because there is one
implementation or there is no injection point. Protocols are not used just for
documentation; they are structural interfaces at real substitution seams. See
F9 for the `JobHandler` example and when not to add a Protocol.

**Source:** PR #5 review, `REQUEST_FLOW.md` L1853, comment `4444599405`.

---

#### **Q: Who is the consumer, and what does a new consumer pick up?**

**A:** `consumer_id` is a logical subscriber using `InboxConsumer` (for example, a
stage engine, metrics collector, or notification handler). Each
`(consumer_id, event_id)` gets one receipt, which makes that consumer’s effect
exactly-once.

The outbox row has a single global `DELIVERED` status/ack. A consumer added
after an event was delivered will not see that event; it only sees future
events unless a backfill/replay is added. This is a real limitation. Decide
between per-consumer delivery rows/cursors and documented future-only
semantics. See `PR5-09`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L2207, comment `4444748481`.

---

#### **Q: What is a Protocol, and why only three?**

**A:** A `Protocol` is a structural interface: a class does not inherit from it; it
just has to provide matching methods. The caller depends on the Protocol, and
any conforming object can be injected. It is a real seam, not documentation.

Example:

```python
class JobHandler(Protocol):
    def __call__(self, claim: JobClaim) -> JobHandlerResult: ...


class NoopJobHandler:
    def __call__(self, claim: JobClaim) -> JobHandlerResult:
        return JobHandlerResult(succeeded=True)


class FutureSpeechJobHandler:          # illustrative, not shipped
    def __call__(self, claim: JobClaim) -> JobHandlerResult:
        ...


def run_once(handler: JobHandler) -> ...:
    ...
```

`run_once` does not care which class it receives. Tests can pass a fake that
records the claim; production passes the real handler. `SpeechJobHandler` does
not need `class SpeechJobHandler(JobHandler)`, and there is no import cycle
between the worker and every handler implementation.

The three Protocols are the three places where substitution is actually
useful:

- `Evaluator`: deterministic checks today, ML/semantic evaluators later; tests
  inject a fake evaluator.
- `JobHandler`: the worker loop versus the actual stage work; tests inject a
  no-op or failing handler.
- `OutboxDeliveryHandler`: the dispatcher versus the consumer effect; tests
  inject a handler that counts deliveries.

Why not make everything a Protocol? A Protocol only pays for itself when there
is more than one implementation, a test fake, or a module boundary you want to
decouple. If there is one concrete class and callers need its exact transaction
semantics, a Protocol adds indirection without a seam. For example,
`LeaseManager` is concrete because a fake would hide the SQL/fencing behavior
under test; `Database` is concrete because it owns connection and PRAGMA
behavior.

A Protocol is also not runtime-enforced. It is checked by the type checker; at
runtime, any object with the right method name is accepted. `@runtime_checkable`
only checks method presence, not signatures. So “Protocols are not used just for
documentation” means: use one when you need substitutability, not to describe a
class that will only ever have one implementation.

**Source:** Follow-up `F9`.

---

#### **Q: How can duplicate provider side effects still happen? Give an example.**

**A:** The database can prevent two identical rows. It cannot see an external charge,
upload, or generated asset. Concrete timeline:

```text
t0  executor INSERTs idempotency_records(key=idem_speech_x, status=RESERVED)
t1  executor UPDATEs status=IN_FLIGHT, COMMITs
t2  executor calls provider: POST /generate
t3  provider creates the asset and charges $0.12
t4  process crashes before persisting the result
t5  retry with idem_speech_x sees IN_FLIGHT -> "already in flight"
t6  operator reconciles. If they decide to retry, the provider creates a
    second asset and charges again
```

What the current code does well:

- `BEGIN IMMEDIATE` serializes concurrent executors, so two processes cannot
  both insert the same key and both call the provider.
- A retry that sees `IN_FLIGHT` returns an error instead of calling again.
- A timeout that becomes `UNKNOWN` returns “reconciliation required” instead of
  blindly retrying.
- `FAILED` can be retried, but only after the executor has recorded a failure.

The remaining gaps:

1. The provider is not given an idempotency key derived from
   `idem_speech_x`. If the process dies after the provider succeeds, the
   provider has no way to recognize the retry.
2. `provider_operation_id` is stored, but the executor never uses it to query
   the provider’s status before retrying an `UNKNOWN` outcome.
3. A provider error after the side effect (for example, the response is lost)
   may be classified as `FAILED`; a later retry calls the provider again.
4. The fake provider is deterministic, so the demo cannot show this failure
   mode. A real provider would.

The fix is provider-side idempotency plus reconciliation:

```text
request header: Idempotency-Key: idem_speech_x
provider returns: operation_id=op_123, status=accepted
persist op_123
on UNKNOWN: GET /operations/op_123 before any retry
```

Only retry when the provider says the operation does not exist or failed
without side effects. Tracked as `PR5-24`.

**Source:** Follow-up `F10`.

---

#### **Q: What is the outbox multi-consumer limitation? Give an example.**

**A:** Mental model: `outbox_messages` is **one mailbox with one copy of each event**,
not a mailing list with one copy per subscriber. `consumer_id` on the inbox
means “who processed this copy”; it does not mean a copy exists for every
consumer.

```text
event E1: stage.succeeded
outbox row: status=PENDING -> CLAIMED -> DELIVERED
```

`inbox_receipts` is per consumer: `(consumer_id, event_id)`. That dedupes a
consumer’s repeated delivery, but it does not give a new consumer the event.
A receipt can only exist after that consumer has received the event.

Scenario:

```text
E1 appended.
Consumer A (stage engine) claims E1, processes it, acks it.
outbox E1 is now DELIVERED.

Later, Consumer B (metrics/notification) is added.
claim_pending() selects only PENDING rows.
E1 is DELIVERED, so B never sees it.
B has no inbox receipt, but there is no delivery to dedupe.
```

A second problem: if A and B run at the same time, only one can claim E1,
because the outbox row has one `claimed_by` and one status. The outbox is
single-consumer delivery even though the inbox is per-consumer.

```text
What people expect from "consumer_id":
  E1 -> copy for A
  E1 -> copy for B

What the outbox actually has:
  E1 -> one row -> first claimant wins -> DELIVERED
```

If you reset E1 to `PENDING` by hand, B can then process it; A may also see it
again, but A’s inbox receipt makes that a no-op. That is manual replay, not
automatic multi-consumer delivery. It also means “new consumer gets old events”
only if someone performs that replay/backfill.

Options:

1. **Per-consumer delivery rows.** Add
   `outbox_deliveries(outbox_id, consumer_id, status, attempts, available_at,
   claimed_by, lease_expires_at, delivered_at)` with primary key
   `(outbox_id, consumer_id)`. Claim and ack per row. A new consumer can
   backfill by inserting delivery rows for retained events.
2. **Per-consumer cursor.** Keep the event log and store
   `last_event_sequence` per consumer. Each consumer reads forward. Simpler,
   but requires a retention/compaction policy and a sequence column.
3. **Document future-only semantics.** Consumers only see events appended
   after registration; no replay. Then stop describing the outbox as
   multi-consumer pub/sub; it is a single local dispatcher.

Recommended for the current SQLite scale: per-consumer delivery rows. The
inbox already makes redelivery safe, so delivery rows can be at-least-once.
Tracked as `PR5-09`.

**Source:** Follow-up `F11`.

---

### Quality Gates and Checks

#### **Q: What is `ABSTAIN`?**

**A:** `ABSTAIN` is a `CheckOutcome`: the evaluator could not make a PASS/FAIL
decision (for example, insufficient evidence or a deliberately
non-determinable check). It is not PASS and not `NOT_APPLICABLE`. The gate
escalates any ABSTAIN to `HUMAN_REVIEW` rather than silently passing.

**Source:** PR #5 review, `REQUEST_FLOW.md` L1266, comment `4444420827`.

---

#### **Q: Is `after_max_regenerations` a code?**

**A:** It is a policy field, not a failure code. `QualityGatePolicy` has
`after_max_regenerations: RepeatedFailureAction`, whose values are
`HUMAN_REVIEW` and `FAIL`. The CLI sets `HUMAN_REVIEW`. The gate applies it
when the regeneration budget is exhausted.

**Source:** PR #5 review, `REQUEST_FLOW.md` L1268, comment `4444422667`.

---

#### **Q: How were the thresholds decided?**

**A:** They were not calibrated. The CLI hardcodes `0.8` pass and `0.65` review for
`claim_support`, `clarity`, `structure`, and `tone`. `ThresholdRegistry` exists
with per-dimension records and recalibration fields, but the CLI gate path does
not use it. This is a placeholder policy. See `PR5-10` to load policies from
the database, use threshold records, and record calibration/rationale in an
ADR.

**Source:** PR #5 review, `REQUEST_FLOW.md` L1271, comment `4444430560`.

---

#### **Q: `QualityGatePolicy` vs `QualityCheck` — what is the difference?**

**A:** `QualityCheck` is one registered check definition: target artifact types,
evaluator, severity, repair scope, required flag, and rubric version.
`QualityGatePolicy` is the gate composition: required check IDs, hard failure
codes, pass/review thresholds, regeneration limit, and after-max action.

In short: a check is “what to evaluate”; a policy is “which checks, with what
thresholds and decision rules”.

**Source:** PR #5 review, `REQUEST_FLOW.md` L1985, comment `4444663829`.

---

#### **Q: Why does `quality evaluate` need migrations?**

**A:** It opens `Database(arguments.database)` directly and then queries
`quality_evaluations`/`quality_gate_results`; it never calls
`MigrationRunner`. A fresh database therefore has no tables and fails with
`no such table: quality_evaluations`. It should use the migrated-database path
(or require explicit `db migrate`) and be re-runnable.

Related bugs: a second identical evaluation fails with `ConflictError` on the
deterministic evaluation IDs, and the command returns exit code `0` for a
`REGENERATE` decision (it only returns nonzero for `FAIL`/`HUMAN_REVIEW`).
Fix all three under `PR5-05`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L3249, comment `4445489477`.

---

### Artifacts, Slots, and Repair

#### **Q: What is a `RepairPlan`?**

**A:** It is a durable **instruction**, not an executed action. It records the source
gate result, reason codes, target artifact/stage-instance IDs, invalidation
scope, max attempts, and creation time. Creating it does not invalidate
artifacts or enqueue replacement work; no executor consumes it yet. It is a
plan for a future repair/recovery path.

**Source:** PR #5 review, `REQUEST_FLOW.md` L1356, comment `4444456524`.

---

#### **Q: What is `logical_slot`, and why that name?**

**A:** `logical_slot` is the stable editorial position/name for an artifact within a
run (`script`, `speech_scene_001`, `render_chunk_02`), independent of version.
Successive artifact versions fill the same slot; `(run_id, logical_slot,
version)` is unique, and pointers select the active version per slot/type.

The name comes from the content/timeline idea of a “slot” that gets filled.
It is being renamed to `artifact_key`: it says what the value is, and it stays
accurate for manifests and render chunks that are not “content”. The rename
needs a new migration (not an edit to `0001_initial.sql`), plus contract,
repository, index, test, and docs updates. See F8 and `PR5-12`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L1478, comment `4444498798`.

---

#### **Q: Is there a better name than “slot”?**

**A:** See L1478. Decided: rename to `artifact_key`. It is the key for the artifact’s
editorial position, not a content-only slot. Do it with a new migration plus
the contract/repository/test/docs change. See F8 and `PR5-12`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L2143, comment `4444727788`.

---

#### **Q: What about artifact types? A script is an artifact; how is it repaired?**

**A:** A script is an artifact, but repair is scoped to editorial/execution units, not
arbitrary artifact types. A script problem is repaired by regenerating the
script stage (or a narrower scene/shot scope for downstream content), producing
new artifact versions and invalidating descendants. `RepairPlan` targets
artifact IDs and stage-instance IDs with an `invalidation_scope`.

There is no separate “repair this artifact type” API. Add a mapping table
(artifact type → checks → repair scope) to the docs. See `PR5-15`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L2445, comment `4445207566`.

---

#### **Q: Should `logical_slot` be renamed to `artifact_key`?**

**A:** Decision: yes, rename it to `artifact_key`.

`artifact_key` is the stable editorial identity of an artifact within one run,
independent of version:

```text
run_id=run_e39d..., artifact_key="script",          version=3
run_id=run_e39d..., artifact_key="speech_scene_001", version=2
run_id=run_e39d..., artifact_key="render_chunk_02",  version=1
```

It is not a filename, URI, or global key. Uniqueness is per run and version:
`(run_id, artifact_key, version)`. A pointer selects the active artifact for
`(run_id, artifact_key, pointer_type)`.

Scope of the rename:

- `Artifact.logical_slot` -> `Artifact.artifact_key`
- `ArtifactPointer.logical_slot` -> `ArtifactPointer.artifact_key`
- `artifacts.logical_slot` -> `artifacts.artifact_key`
- `artifact_pointers.logical_slot` -> `artifact_pointers.artifact_key`
- repository methods such as `get_by_slot_version`, `next_version`,
  `list_for_slot`, and `list_active_for_run`
- index and constraint names containing `slot`
- docs, atlas examples, and golden fixtures

Do **not** rename `stage_instances.logical_item_key` or
`quality_evaluations.logical_item_key` **to `artifact_key`**. They are a
different identity, not a different spelling of the same thing:

- `stage_instances.logical_item_key` identifies one planned unit of work
  produced by cardinality expansion, for example `asset_001`,
  `speech_scene_003`, or `render_chunk_02`. It scopes the unique constraint
  `(run_id, node_id, logical_item_key)` and the attempts/jobs for that unit.
- `quality_evaluations.logical_item_key` records which stage item an evaluation
  targeted. One evaluation can cover several artifacts from that item.
- `artifact_key` identifies an artifact version slot. One stage item can
  produce several artifacts (video, thumbnail, manifest), so the two keys are
  not interchangeable.

Renaming them to `artifact_key` would imply “one stage item = one artifact,”
which is false and would break the stage-item uniqueness and ID formula. A
separate clarity rename to `stage_item_key` is reasonable, but it is not part
of `PR5-12`; it is tracked separately as `PR5-25`.

Because 0001 has already been applied in demo databases, do not edit it. Add:

```sql
-- 0002_rename_artifact_key.sql
ALTER TABLE artifacts
    RENAME COLUMN logical_slot TO artifact_key;

ALTER TABLE artifact_pointers
    RENAME COLUMN logical_slot TO artifact_key;

DROP INDEX idx_artifacts_run_slot_state;
CREATE INDEX idx_artifacts_run_key_state
    ON artifacts (run_id, artifact_key, state);

DROP INDEX idx_artifact_pointers_lookup;
CREATE INDEX idx_artifact_pointers_lookup
    ON artifact_pointers (run_id, artifact_key, pointer_type, active);

DROP INDEX uq_artifact_pointers_active;
CREATE UNIQUE INDEX uq_artifact_pointers_active
    ON artifact_pointers (run_id, artifact_key, pointer_type)
    WHERE active = 1;
```

SQLite 3.25+ updates the column references inside existing indexes when
`RENAME COLUMN` runs, but the index names still say `slot`. Recreating them
with `artifact_key` names keeps the schema readable. Verify with
`PRAGMA table_info(artifacts)` and `PRAGMA index_list(artifacts)`.

Why this name:

- `artifact_key` says what the value is: a key for artifact identity.
- `content_slot` is narrower; not every artifact is “content” (for example a
  manifest or render chunk).
- `slot_key` keeps the metaphor that caused the confusion.

`PR5-12` is now the rename plan, not a “decide” item. No production data means
no backfill beyond the migration; demo databases can be recreated.

**Source:** Follow-up `F8`.

---

### Failure Handling and Recovery

#### **Q: What does the recovery-actions table mean?**

**A:** It maps a recovery decision (`FailureAction`, defined in
`src/pipeline/execution/retry.py`) to the resulting status of each execution
record: attempt, job, and stage. It answers “if this action is chosen, what
happens to each record?” It is not a table of failure codes or gate decisions.

Doc improvement: label the columns “Attempt status / Job status / Stage status”
and note that `FailureAction` lives in `execution/retry.py`, while
`RecoveryAction`, `QualityFailureAction`, and `RepeatedFailureAction` live in
`contracts/vocabularies.py`. See `PR5-14`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L2472, comment `4445225805`.

---

#### **Q: Failure action for what component?**

**A:** For the stage execution records: attempt, job, and stage. The action is chosen
at the stage-recovery boundary after a capability attempt fails. It is not an
outbox or quality-gate action.

**Source:** PR #5 review, `REQUEST_FLOW.md` L2474, comment `4445236064`.

---

#### **Q: Failure code for what component?**

**A:** `FailureCode` classifies why a capability/provider invocation failed
(`EXEC.VALIDATION`, `EXEC.QUOTA`, and so on). It is stored on the attempt
(`failure_code`) and in `NormalizedError`; its category drives retry/recovery.
It is not a quality-check code or an HTTP status.

**Source:** PR #5 review, `REQUEST_FLOW.md` L2484, comment `4445238712`.

---

#### **Q: Default action for what component?**

**A:** “Default action” means the stage-level `RecoveryAction` selected by
`classify_failure()` under the default retry/recovery policy when that failure
code occurs. It maps to the attempt/job/stage transitions in §6.12.

Doc bug: the catalogue uses `PAUSE`, `DEFER`, and `HUMAN_REVIEW` as default
actions, but `FailureAction` only has `RETRY`, `RECONCILE`, `WAIT_HUMAN`, and
`FAIL`; `RecoveryAction` has `RESUME`, `RETRY`, `RECONCILE`, `REGENERATE`,
`WAIT_HUMAN`, and `FAIL`. `PAUSE` and `DEFER` do not exist in code. The
catalogue must be corrected or mapped explicitly. See `PR5-14`.

**Source:** PR #5 review, `REQUEST_FLOW.md` L2486, comment `4445242361`.

---

#### **Q: What happens once it is `FAIL`?**

**A:** Attempt `FAILED`, job `DEAD_LETTER`, stage `FAILED`. If the node is required,
readiness derives run `FAILED`. There is no automatic retry; an operator or
human must repair or re-run. `RECONCILE` and `WAIT_HUMAN` are the other
terminal branches.

**Source:** PR #5 review, `REQUEST_FLOW.md` L2633, comment `4445277313`.

---

### PR #5 Decision Summary

| Topic | Decision | Issue |
|-------|----------|------|
| Atlas rendering | Fix enum names, escape union pipes, and render `default_factory` defaults | `PR5-01` |
| Repository projections | Store every extracted column, including JSON-encoded lists | `PR5-02` |
| Stage identity | Include `logical_item_key` in the `stage_` formula and add a stage creator | `PR5-03` |
| Double prefixes | Use the helper result directly for `eval_`, `qgr_`, and `repair_` | `PR5-04` |
| `quality evaluate` | Migrate, be re-runnable, and return a distinct `REGENERATE` status | `PR5-05` |
| Human review CLI | Implement `list`/`show` and test the full command group | `PR5-06` |
| Timestamps | Persist one canonical UTC representation | `PR5-07` |
| `capabilities list` | Make it a read-only registry query | `PR5-08` |
| Outbox | Add per-consumer delivery rows or document future-only semantics | `PR5-09` |
| Quality policy | Load gate policy/thresholds from the database and calibrate them | `PR5-10` |
| ID contract | Document formulas, shared digests, opacity, and versioning | `PR5-11` |
| Artifact identity | Rename `logical_slot` to `artifact_key` | `PR5-12` |
| Run overrides | Resolve defaults, bounds, `source_map`, and `config_hash` | `PR5-13` |
| Failure actions | Reconcile the docs catalogue with the real enums | `PR5-14` |
| Repair scopes | Map artifact types to checks and allowed repair scopes | `PR5-15` |
| Readiness persistence | Persist `next_status` and create stages/attempts/jobs end to end | `PR5-16` |
| Capability idempotency | Rename `idempotency_records` to `capability_idempotency_records` | `PR5-21` |
| `policy_ids` | Resolve it against the registry or remove it | `PR5-22` |
| Request fingerprint | Fingerprint the full semantic request, not only `payload` | `PR5-23` |
| Provider side effects | Add provider idempotency keys and reconcile `UNKNOWN` outcomes | `PR5-24` |
| Stage item key | Optionally rename `logical_item_key` to `stage_item_key` | `PR5-25` |

---

## PR #89 Review — Canonical Timestamps and Migration Backfill

**Source:** PR #89 review (`fix/storage-projections-canonical-timestamps`), 21
line comments. Replies are on the PR. Each answer names its comment ID.

PR #89 introduced the canonical six-digit UTC timestamp representation, the
0002 data migration, and the Python backfill module. GEN-25 (#93) later replaced
suffix-based column detection with an explicit registry, and GEN-24 (#92)
revisits the storage representation.

### Migration Model and Checksums

#### **Q: Why is `0002_canonical_timestamps.sql` empty?**

**A:** It is a comment-only SQL anchor. `MigrationRunner` needs an
`NNNN_name.sql` file to assign version 2, compute a checksum, enforce ordering,
and record the migration in `schema_migrations`. The actual repair needs Python:
JSON parsing, Pydantic validation, schema-directed traversal, and datetime
canonicalization. The runner executes the SQL file, then calls the Python hook
registered for `(2, "canonical_timestamps")` in the same transaction. If the
hook fails, the transaction rolls back and no version row is recorded.

**Source:** PR #89 review, `0002_canonical_timestamps.sql` L1, comment
`4481070984`; reply `4483039420`.

---

#### **Q: Why can SQLite not normalize these timestamps reliably in SQL?**

**A:** SQLite's date functions understand offsets, but they cannot produce the
required representation reliably:

```text
datetime('2026-10-21T14:00:00.123456+02:00')
-> '2026-10-21 12:00:00'        -- drops microseconds

strftime('%Y-%m-%dT%H:%M:%fZ', '2026-10-21T14:00:00.123456+02:00')
-> '2026-10-21T12:00:00.123Z'   -- milliseconds, not six digits
```

JSON is the harder problem. SQL sees two strings named `created_at` but cannot
tell that one is a typed `EventEnvelope.created_at` and the other is opaque
extension data such as `resolved_values.provider_options.created_at`. A generic
SQL/JSON rewrite would repeat the key-name-matching bug from the earlier
projection defect. Python plus Pydantic supplies the schema context.

**Source:** PR #89 review, `0002_canonical_timestamps.sql` L3, comment
`4481076266`; reply `4483040131`.

---

#### **Q: What is `migrations.py`, who uses it, and when?**

**A:** It is the migration runner. It discovers `NNNN_name.sql` files, validates
unique and contiguous versions from `0001`, verifies checksums of already-applied
migrations, applies pending migrations in explicit transactions, records each
applied version, and invokes registered Python data-migration hooks.

It is used by the CLI (`python -m pipeline db migrate` and `db status`) and by
`_migrated_database()` before database-backed CLI commands. Tests use it to
create temporary migrated databases. It should run before repository access on
a new or existing database. It is not a general normalization utility.

**Source:** PR #89 review, `migrations.py` L9, comment `4481112450`.

---

#### **Q: Why does 0002 need a Python hook when other migrations are plain SQL?**

**A:** Most migrations are pure SQL. This one needs operations SQL cannot do
reliably: parse JSON, validate it through Pydantic, traverse typed models, and
canonicalize datetimes while preserving opaque extension values.

The hook registry maps an exact migration identity to a Python callable. During
`migrate()`, the runner executes the SQL file, looks up `(version, name)`, calls
the hook inside the same transaction, and records the migration only if both
succeed. To add another data migration, add a `(version, name): function` entry
and a matching `.sql` file. The hook must be idempotent and fail closed.

**Source:** PR #89 review, `migrations.py` L39, comment `4481128869`.

---

#### **Q: Why is the hook tied to version 2?**

**A:** Because the matching file is `0002_canonical_timestamps.sql`: version `2`,
name `canonical_timestamps`. `0001_initial.sql` creates the schema, so this repair
is the next contiguous migration. The runner looks up hooks by
`(migration.version, migration.name)`, not just by filename, so a hook cannot
accidentally run for a different migration with a similar name. Version and name
are also part of the checksum/history record.

**Source:** PR #89 review, `migrations.py` L40, comment `4481134362`.

---

#### **Q: Why is the filename `0002`, and what happens after 9999 migrations?**

**A:** `0002` is the next contiguous version after `0001_initial.sql`. The
four-digit zero-padded format keeps filenames ordered and readable. The current
implementation is strictly four digits, so version `10000` would be rejected by
`MIGRATION_FILE_PATTERN`. Supporting more would require widening the regex and
the `:04d` formatting. This is tracked as GEN-23 (#90).

**Source:** PR #89 review, `0002_canonical_timestamps.sql` L1, comment
`4481147817`; reply `4483042690`.

---

### Payloads, Projections, and Backfill

#### **Q: What is `backfill.py`, who calls it, and when?**

**A:** It is the Python data-repair module for migration 0002. It is called by
`MigrationRunner.migrate()` through
`_DATA_MIGRATION_HOOKS[(2, "canonical_timestamps")]`, immediately after the empty
SQL anchor and inside the same transaction.

Its jobs are:

- rebuild the broken `idempotency_records` projection columns from validated
  payloads;
- normalize schema-declared payload timestamps;
- normalize extracted timestamp columns;
- fail closed if durable data is invalid.

It is also called directly by tests. It is not part of the normal repository
request path and is not intended to run outside a migration transaction.

**Source:** PR #89 review, `backfill.py` L1, comment `4481175059`.

---

#### **Q: Why does 0002 special-case `idempotency_records`? Does that make the migration pass artificially?**

**A:** It is not only `idempotency_records`. After the special step, the function
loops over every user table and calls `_normalize_table()` for any table with a
`payload` column or registered timestamp columns. All other payloads and
timestamp columns are processed too.

`idempotency_records` gets an extra step because its SQL projection columns were
incomplete or wrong (the #9 defect). Its non-timestamp projection columns
(`operation_version`, `locale`, artifact ID lists, and so on) must be rebuilt
from the validated payload, not just have timestamps normalized. Other tables do
not have that known projection defect. The special case is a targeted repair,
not a workaround to make the migration pass.

**Source:** PR #89 review, `backfill.py` L46, comment `4481184588`; reply
`4483043776`.

---

#### **Q: Why read all rows before writing them back?**

**A:** It is a deliberate read-modify-write:

1. Read the durable rows once with `fetchall()`.
2. Validate each stored JSON payload through the current model.
3. Check that the payload key matches the SQL row key.
4. Recompute projection columns from that validated record.
5. Write the corrected payload and projections back.

The correct projections cannot be computed without reading the payload first.
`fetchall()` materializes the rows before updates, so iterating and updating is
safe. All updates remain inside the caller's transaction; any validation or write
failure rolls the whole migration back.

**Source:** PR #89 review, `backfill.py` L74, comment `4481194446`; reply
`4483044239`.

---

#### **Q: If payload traversal is schema-directed, why does the SQL side use an `_at` suffix?**

**A:** They are two different scopes:

- Inside JSON payloads, key names are not trusted because extension data can
  contain arbitrary keys such as `created_at`. Payload traversal is
  schema-directed.
- At the SQL table level, `_at` columns were the schema's declared timestamp
  convention. `PRAGMA table_info` only reports `TEXT`, not the semantic
  “timestamp”, so the DDL convention was the available signal.

The `_at` rule was not guessing inside arbitrary metadata; it was recognizing the
storage schema. When a future column ends in `_at` but is not a timestamp, an
explicit map is needed. GEN-25 (#93) replaced the suffix inference with the
explicit `TIMESTAMP_COLUMNS` registry; the suffix now survives only as a
test-time completeness guard.

**Source:** PR #89 review, `backfill.py` L83, comment `4481208521`; reply
`4483044699`.

---

#### **Q: Where does the backfill decide which payload fields are timestamps?**

**A:** In `_normalize_payload()`. The payload's `schema_version` resolves to a
contract model through `CONTRACT_MODELS`. Each declared field is inspected;
`_unwrap_annotation()` removes `Annotated`, `Optional`, and similar wrappers. If
the resolved annotation is `datetime`, and the field is present, it is treated as
a timestamp.

`UTCDateTime` resolves to `datetime`, so typed fields such as `created_at` and
`available_at` are recognized. `ExtensionObject` is a `dict`, so it is not
included and its contents are never traversed. The annotation comes from Pydantic
model metadata, not from SQLite.

**Source:** PR #89 review, `backfill.py` L171, comment `4481231031`; reply
`4483045182`.

---

#### **Q: Walk through the normalization with a concrete dry run.**

**A:** Take this stored outbox payload:

```json
{
  "schema_version": "outbox-message.v1",
  "outbox_id": "outbox_1",
  "event_id": "event_1",
  "event": {
    "schema_version": "event-envelope.v1",
    "event_id": "event_1",
    "created_at": "2026-10-21T09:00:00Z",
    "payload": {"created_at": "provider-managed"}
  },
  "status": "PENDING",
  "available_at": "2026-10-21T09:00:00Z"
}
```

1. `_normalize_table()` finds the payload and the registered timestamp columns.
2. `_parse_payload()` parses the JSON object.
3. `_normalize_payload()` resolves `outbox-message.v1` to `OutboxMessage`.
4. It identifies `available_at` as a declared `datetime`.
5. `_normalize_nested_model()` walks declared fields.
6. `available_at` becomes `2026-10-21T09:00:00.000000Z`.
7. `event` is a declared `EventEnvelope`, so it recurses.
8. `event.created_at` becomes `2026-10-21T09:00:00.000000Z`.
9. `event.payload` is an `ExtensionObject` (`dict`), so recursion stops and
   `"provider-managed"` is untouched.
10. The payload is serialized with `canonical_json()` and written with the
    normalized projection columns in one `UPDATE`.

If a declared timestamp is invalid or naive, `_normalize_timestamp()` raises
`MigrationError` and the transaction rolls back.

**Source:** PR #89 review, `backfill.py` L182, comment `4481245130`; reply
`4483045832`.

---

#### **Q: Is the nested normalization recursive? Can it loop forever?**

**A:** Yes, it is recursive by design, but only through declared model fields:

```text
_normalize_payload
  -> _normalize_nested_model
    -> _normalize_field_value
      -> _normalize_nested_model   # for another declared BaseModel field
```

It does not recursively walk arbitrary dictionaries. For `OutboxMessage` it
recurses into `event` because that field is declared `EventEnvelope`. For
`EventEnvelope.payload` or `EffectiveConfig.resolved_values`, the annotation is
`ExtensionObject`/`dict`, so recursion stops. Depth is bounded by the JSON
nesting depth, and the input is finite.

**Source:** PR #89 review, `backfill.py` L173, comment `4481253896`; reply
`4483046288`.

---

#### **Q: What does `canonical_datetime()` do, and is it used everywhere?**

**A:** It returns fixed-precision ISO-8601 UTC text with exactly six fractional
digits and a trailing `Z`. Fixed precision makes SQLite text ordering agree with
chronological ordering.

For durable SQLite writes it is used directly or indirectly:

- `canonical_json()` uses it for every serialized `datetime`, so repository
  payloads and fingerprints use it.
- `SqliteRepository._column_value()` uses it for extracted datetime columns.
- Direct SQL writers use it, for example `HumanReviewRepository.insert_decision()`
  and `UsageRecordRepository.insert()`.
- Event/outbox helper timestamps, lease parameters, `schema_migrations.applied_at`,
  and the migration backfill use it.
- `fingerprints._normalize()` uses it for datetime values.

It is not used for every datetime the application displays. Report, CLI, and
quality-export code may use `.isoformat()` because those are presentation/export
formats, not SQLite ordering or fingerprint inputs. GEN-24 (#92) may change SQL
projections and payload datetime values to integer microseconds; persistence,
payload serialization, and fingerprints must then move together.

**Source:** PR #89 review, `fingerprints.py` L43, comment `4481101399`; reply
`4483040673`.

---

#### **Q: Do we need the backfill at all if the test data can be deleted?**

**A:** No — if you delete and recreate the development database, the legacy
timestamp backfill is unnecessary. It only repairs old rows. The canonical write
path is still required.

The migration is kept because it must also be safe for existing version-1
databases that are not discarded. A local pipeline database can contain real
runs, artifacts, effective configs, idempotency records, human reviews, and audit
history. Deleting rows would lose durable runtime data, break foreign-key
references, and discard audit history. A destructive reset policy is a separate
scope decision, not the migration's behavior.

**Source:** PR #89 review, `backfill.py` L2, comment `4481475025`; reply
`4483049311`.

---

### Tests and Isolation

#### **Q: Do these tests insert into my real SQLite database?**

**A:** No. The `database` fixture in `tests/storage/conftest.py` creates
`Database(tmp_path / "state" / "pipeline.sqlite3")`. `tmp_path` is pytest's
per-test temporary directory, the fixture runs migrations on that temporary
database, and the file is discarded after the test. Your pipeline database is not
touched.

**Source:** PR #89 review, `tests/storage/test_timestamps.py` L146, comment
`4481311507`; reply `4483046646`.

---

#### **Q: What is the persisted-text ordering test for?**

**A:** It is the regression for the ordering bug in #14. SQLite stores
timestamps as text, so `ORDER BY created_at` is lexicographic. The test inserts
six timestamps around second and microsecond boundaries:

```text
12:00:00.000000
12:00:00.000001
12:00:00.999999
12:00:01.000000
12:00:01.000001
12:00:02.000000
```

It asserts that SQL order equals chronological order, every value ends in `Z`,
and every value has the same 27-character length. Without fixed six-digit
precision, a value with no fractional part can sort after a fractional value
because `.` sorts before `Z`.

**Source:** PR #89 review, `tests/storage/test_timestamps.py` L52, comment
`4481374691`; reply `4483047122`.

---

#### **Q: What is an idempotency projection, and what does the repair test cover?**

**A:** An idempotency projection is the set of SQL columns extracted from the
canonical `IdempotencyRecord` JSON payload for indexing and filtering:
`operation_version`, `input_artifact_ids`, `required_features`, `locale`,
`provider_invocation_id`, `provider_operation_id`, `result_artifact_ids`,
`created_at`, `completed_at`, and so on. The payload remains the source of truth;
the columns are a queryable copy.

The test simulates a version-1 database with a valid payload but wrong/defaulted
extracted columns (the #9 defect). It runs migration 0002 and asserts that the
projection columns are rebuilt, payload timestamps are canonicalized, projection
timestamps agree with the payload, `schema_migrations.applied_at` is canonical,
and the row still round-trips through `IdempotencyRecordRepository`.

**Source:** PR #89 review, `tests/storage/test_migrations.py` L278, comment
`4481401747`; reply `4483047453`.

---

#### **Q: Why separate tests for idempotency projection and generic payload/projection repair?**

**A:** They cover different migration paths:

- The idempotency test exercises `_reproject_idempotency_records()`: validating a
  payload and rebuilding non-timestamp projection columns.
- The generic test exercises `_normalize_table()`: normalizing a schema-declared
  payload timestamp and keeping the extracted column consistent with it.

Keeping them separate makes failures easier to localize. If generic timestamp
normalization breaks, one test fails; if idempotency projection rebuilding
breaks, the other fails. They are not redundant.

**Source:** PR #89 review, `tests/storage/test_migrations.py` L323, comment
`4481418891`; reply `4483047895`.

---

#### **Q: What is nested in the nested-timestamp test?**

**A:** The nested record is:

```text
outbox_messages.payload
  -> OutboxMessage.event
       -> EventEnvelope.created_at
```

`OutboxMessage.event` is declared as `EventEnvelope`, so `event.created_at` is a
real typed timestamp nested inside the outbox payload and must be normalized.
At the same time, `EventEnvelope.payload` is an `ExtensionObject` containing:

```python
"created_at": "provider-managed",
"updated_at": "2026-10-21T12:00:00Z",
```

Those are opaque extension values and must remain unchanged. The test proves both
behaviors at once: recurse into typed nested records, stop at extension objects.

**Source:** PR #89 review, `tests/storage/test_migrations.py` L453, comment
`4481435231`; reply `4483048257`.

---

#### **Q: What does the restored-columns SQL filter test add?**

**A:** It tests the user-visible consequence of the #9 bug: the restored columns
must actually work in SQL filters. It inserts two idempotency records and queries
each restored column, including JSON-encoded list columns, asserting that
filtering returns exactly the expected record and that empty lists are stored and
filterable as `[]`. Checking that columns exist is not enough; this proves their
values are correctly projected and queryable.

**Source:** PR #89 review, `tests/storage/test_idempotency_projection.py` L105,
comment `4481464329`; reply `4483048748`.

---

### PR #89 Decision Summary

| Topic | Decision |
|-------|----------|
| Timestamp representation | Canonical UTC ISO-8601 text with exactly six fractional digits and `Z` |
| Migration 0002 shape | Comment-only SQL anchor plus a Python hook in the same transaction |
| Payload timestamps | Schema-directed through Pydantic annotations; never inferred from JSON keys |
| SQL timestamp columns | Extracted projections, normalized in the same transaction as the payload |
| Idempotency repair | Rebuild every projection column from the validated payload |
| Backfill safety | Idempotent, fail-closed, read-modify-write inside the migration transaction |
| Display formatting | `isoformat()` is acceptable outside persistence, ordering, and fingerprints |
| Follow-up | GEN-24 (#92) revisits the SQL and payload representation; GEN-25 (#93) replaces suffix detection with a registry |

---

## PR #94 Review — Timestamp Column Registry

**Source:** PR #94 review (`fix/timestamp-column-registry`), 18 line comments.
Replies are on the PR. Follow-up questions are labelled `F1`–`F13` in the Source
lines.

### Follow-up index

| ID | Question | Topic |
|----|----------|-------|
| `F1` | What is the payload, and aren't SQL columns derived from it? | Registry Scope |
| `F2` | Why does checksum validation fail, how do I revert, and what does “versioned” mean? | Migration Discipline |
| `F3` | Does the test require the migration to run first? | Migration Discipline |
| `F4` | What are “writable columns”? | Registry Behavior |
| `F5` | Are payload keys and values also changing to `*_timestamp_micro`? | Registry Scope |
| `F6` | Is the suffix check just a safety check, and what do “register” and “rename” mean? | Registry Behavior |
| `F7` | Why does the backfill not touch unregistered timestamp-like columns? | Registry Behavior |
| `F8` | What is a generated column, and how are generated timestamps handled? | Generated Columns |
| `F9` | Are `STRICT` and `CHECK` good practice, and how does `NULL` behave? | Constraints and NULL Semantics |
| `F10` | Are the `PRAGMA` tuple indices SQLite-provided? | Tests and SQLite Mechanics |
| `F11` | Where does `monkeypatch.setitem` write? | Tests and SQLite Mechanics |
| `F12` | Where should a derived timestamp live so code is unaffected? | Generated Columns |
| `F13` | What was decided about `CHECK` and `STRICT`? | Constraints and NULL Semantics |

### Registry Scope: Payloads, Projections, and Storage Format

#### **Q: What is the payload, and aren't SQL columns derived from it?**

**A:** A payload is the JSON document stored in a row's `payload` column (or an
equivalent JSON column such as `effective_configs.resolved_values`). It is the
full serialized Pydantic contract and the source of truth for the record.

A **projection column** is a SQL column that duplicates one payload field for
querying: filtering, ordering, uniqueness, and `NOT NULL` enforcement. For
`WorkflowRun`, the payload contains `created_at` and `updated_at` from
`UTCRecord`, and `workflow_runs` contains matching `created_at` and `updated_at`
columns listed in `WorkflowRunRepository.columns`.

So yes, the SQL columns are derived from the payload — but “derived” does not mean
“automatically kept in sync”. They are denormalized copies. The write path
usually writes both, but a direct SQL writer or an old migration can update only
one. That is why backfill reconciles them and why validation exists.

**Source:** PR #94 review, `timestamp_columns.py` L9, comment `4493551868`;
follow-up `F1`.

---

#### **Q: What does “projection” mean here?**

**A:** It means the extracted SQL copy of a payload field, not a relational
algebra projection and not a Pydantic projection. Concrete examples:

```text
payload JSON:        {"run_id": "...", "status": "running",
                      "created_at": "2026-10-21T09:00:00.000000Z"}
projection columns:  run_id TEXT, status TEXT, created_at TEXT
```

`created_at` appears twice: inside the JSON payload and as a column. The column
is the projection. It exists so SQL can do `WHERE status = ? ORDER BY created_at`
with an index without parsing JSON.

Related but distinct terms:

- **payload field** — the authoritative value inside JSON;
- **projection column** — the denormalized SQL copy;
- **generated column** — a column SQLite derives from other SQL columns, not from
  the payload.

The migration only rewrites timestamp projections it owns (the registry). It
does not touch IDs, statuses, or the JSON payload.

**Source:** PR #94 review, `timestamp_columns.py` L9, comment `4493551868`;
follow-up `F1`.

---

#### **Q: Is the registry still using ISO text, or are we moving to epoch microseconds?**

**A:** Not in #93. #93 records the current representation so the safety net
matches today's schema. The registry entry `_iso()` expands to
`TimestampColumn(TimestampFormat.ISO8601_TEXT, nullable=False)`, which expects
`TEXT`. Writing `UNIX_MICROSECONDS` today would immediately fail validation
because `0001_initial.sql` declares these columns `TEXT`.

GEN-24 (#92) performs the representation change: rename to
`*_timestamp_micro`, store integer microseconds, and migrate values. The registry
already supports both formats through `TimestampFormat` and `_DECLARED_TYPES`
(`TEXT` for ISO, `INTEGER` for micros), so #92 can flip entries safely.

**Source:** PR #94 review, `timestamp_columns.py` L92, comment `4493613829`;
follow-up `F5`.

---

#### **Q: Did we decide to align payload keys and values too?**

**A:** Yes. GEN-24 (#92) now records **full alignment**:

- rename JSON payload timestamp keys to `*_timestamp_micro`;
- store integer microseconds in payload values as well;
- bump affected `schema_version` literals;
- update fingerprints, events, and consumers.

There is no real data yet, so the contract break is acceptable. The decision is
recorded in the issue; implementation is deferred and no code changes were
authorized by that record.

**Source:** PR #94 review, `timestamp_columns.py` L20/L92, comments
`4493567274` and `4493613829`; follow-up `F5`; GEN-24 (#92).

---

### Migration Discipline

#### **Q: Why does an existing database fail the checksum check on startup?**

**A:** The runner compares each migration file's bytes with the checksum recorded
when it was applied, before doing anything else. `migrations.py:189` raises:

```text
migration 0001_initial.sql changed after it was applied; add a new migration instead
```

If `0001_initial.sql` is edited after it was applied, the new hash differs from
the recorded one, so startup fails. The alternative — silently rerunning or
ignoring the difference — would either fail partway or leave the database in a
shape that does not match the files. That is exactly the silent drift this
project is trying to eliminate.

**Source:** PR #94 review, `timestamp_columns.py` L15, comment `4493558590`;
follow-up `F2`.

---

#### **Q: How do I revert an edited migration, and what does “versioned” mean?**

**A:** Restore the exact applied bytes:

```bash
git restore src/pipeline/storage/migrations/0001_initial.sql
```

Then add a new migration for the intended change. If the modified file was
already applied to a development database, that database recorded the modified
checksum, so restoring the file creates the reverse mismatch. Recreate the
development database; never rewrite `schema_migrations` by hand.

“Versioned” means two things: the file is git-versioned, and the filename number
is the schema version whose content is frozen by the checksum once applied.
Applied migrations are append-only.

**Source:** PR #94 review, `timestamp_columns.py` L15, comment `4493558590`;
follow-up `F2`.

---

#### **Q: Does the test require the migration to run first?**

**A:** You must write the migration file first, but you do not run it manually.
The `database` fixture creates a fresh temporary database and calls
`MigrationRunner(database).migrate()`. The test then validates the real
post-migration shape. The loop is:

1. write `0003_....sql`;
2. add the registry entry;
3. run `uv run pytest tests/storage/test_timestamp_registry.py`.

Your real `PIPELINE_HOME` database is not involved.

**Source:** PR #94 review, `timestamp_columns.py` L17, comment `4493561511`;
follow-up `F3`.

---

### Registry Behavior

#### **Q: What are “writable columns”?**

**A:** The columns the backfill is allowed to `UPDATE`: the intersection of the
registry and the live schema, excluding primary keys and generated/hidden
columns. In `backfill.py`:

```python
registered = registered_timestamp_columns(table)
timestamp_columns = [name for name, _ in columns if name in registered]
```

Only those columns are read and rewritten. Key columns go in `WHERE`, not `SET`;
generated columns cannot be written at all; unrelated columns are out of scope.
“Writable” is the mutation boundary, not a claim that every timestamp-like
column is writable.

**Source:** PR #94 review, `timestamp_columns.py` L17, comment `4493561511`;
follow-up `F4`.

---

#### **Q: Is the `_at` suffix check just a safety check? What if we remove it?**

**A:** Yes. It is not required for correct writes. It is a completeness guard
against omission. Without it, a developer could add `archived_at TEXT`, forget the
registry entry, and nothing would complain; the column would silently never be
normalized and could hold a different format after #92.

With it, the test fails immediately with `unregistered timestamp column
workflow_runs.archived_at`, and the developer either registers or renames the
column. The trade is occasional false positives on names such as `note_at`,
resolved by renaming. The check runs only in validation/tests, not in the write
path.

**Source:** PR #94 review, `timestamp_columns.py` L21, comment `4493571892`;
follow-up `F6`.

---

#### **Q: What does “register” mean, and when should I rename instead?**

**A:** Registering means adding an explicit entry to `TIMESTAMP_COLUMNS` with the
column's format and nullability:

```python
"workflow_runs": {
    "created_at": _iso(),
    "updated_at": _iso(nullable=True),
    "archived_at": _iso(nullable=True),
}
```

After that, the column is no longer unregistered, and the backfill will normalize
it according to the declared format. Registration is not a way to silence the
check; type and nullability are still validated against the live schema.

Rename when the column is **not** a timestamp. The suffix is reserved, so a free
text column such as `note_at` should become `note_text` (or another name without
the reserved suffix). The two outcomes are: real timestamp -> register; not a
timestamp -> rename.

**Source:** PR #94 review, `timestamp_columns.py` L21, comment `4493571892`;
follow-up `F6`.

---

#### **Q: Why doesn't the backfill touch unregistered timestamp-like columns?**

**A:** Because detection and mutation are deliberately separate. Detection is
broad and heuristic (name-based) so it catches omissions. Mutation is narrow and
explicit (registry-based) so it only touches columns whose representation is
known. If backfill guessed from the suffix, an unrelated `note_at` containing
`'not-a-timestamp'` would be parsed or rewritten. The regression
`test_backfill_ignores_unregistered_timestamp_suffix` asserts that the value
stays unchanged.

So `note_at` is reported by validation (“classify me”) but ignored by the
backfill (“I only rewrite classified columns”).

**Source:** PR #94 review, `timestamp_columns.py` L21 and
`tests/storage/test_timestamp_registry.py` L180, comments `4493571892` and
`4493739869`; follow-up `F7`.

---

#### **Q: Why is `updated_at` registered as `nullable=True`?**

**A:** Because the actual column is nullable. In `0001_initial.sql`,
`workflow_runs.created_at` is `TEXT NOT NULL` while `workflow_runs.updated_at` is
`TEXT` with no `NOT NULL`. A row is created before its first update, so
`updated_at` is legitimately `NULL` until then. The registry must match the
schema exactly; declaring it `NOT NULL` would fail validation with:

```text
timestamp column workflow_runs.updated_at is nullable, expected NOT NULL
```

The same applies to `stage_instances.updated_at`.

**Source:** PR #94 review, `timestamp_columns.py` L187, comment `4493629712`.

---

#### **Q: What does `actual` contain during validation?**

**A:** It is a three-tuple built from `PRAGMA table_xinfo` in `_table_columns`:

```python
columns[str(column[1])] = (
    str(column[2]),   # declared_type, e.g. "TEXT"
    bool(column[3]),  # not_null, e.g. False
    int(column[6]),   # hidden, e.g. 0
)
```

Examples:

| column | `actual` |
|---|---|
| `workflow_runs.created_at` | `("TEXT", True, 0)` |
| `workflow_runs.updated_at` | `("TEXT", False, 0)` |
| generated `workflow_runs.archived_at` | `("TEXT", False, 2)` |

`hidden` is `0` for an ordinary column, `1` for hidden, `2` for generated
`VIRTUAL`, and `3` for generated `STORED`.

**Source:** PR #94 review, `timestamp_columns.py` L224, comment `4493635360`;
follow-up `F10`.

---

#### **Q: Are those tuple indices something SQLite provides?**

**A:** Yes. `PRAGMA table_xinfo(table)` returns rows with seven fields: `cid`,
`name`, `type`, `notnull`, `dflt_value`, `pk`, and `hidden`. The code keeps only
`name`, `type`, `notnull`, and `hidden`. `table_xinfo` is `table_info` plus
generated/hidden columns, which is why the earlier `table_info` version missed
generated timestamp columns.

**Source:** PR #94 review, `timestamp_columns.py` L224, comment `4493635360`;
follow-up `F10`.

---

### Generated Columns

#### **Q: What is a generated column, and why does it break the backfill?**

**A:** A generated column is a real table column whose value SQLite computes from
other columns:

```sql
ALTER TABLE workflow_runs ADD COLUMN archived_at TEXT
    GENERATED ALWAYS AS (created_at) VIRTUAL;
```

`archived_at` always mirrors `created_at`; you cannot insert or update it
directly. `PRAGMA table_info` omits it, so the original validator could not see
it. If it were registered, the backfill would try:

```sql
UPDATE workflow_runs SET archived_at = ?
```

and SQLite would reject it with `cannot UPDATE generated column`. If it were
silently skipped, it would appear supported but never be normalized. GEN-25
(#93) now uses `table_xinfo` and rejects generated timestamp columns explicitly.

**Source:** PR #94 review, `timestamp_columns.py` L28, comment `4493578234`;
follow-up `F8`.

---

#### **Q: Is a generated column just a view? Where is it defined, and when is it computed?**

**A:** No, it is a real column of the table, but read-only. Similar in spirit to a
view, different in mechanism.

- Definition: stored in the table schema (`sqlite_master.sql`), created once by
  `CREATE TABLE` or `ALTER TABLE`.
- `VIRTUAL`: computed on every read, not stored on disk.
- `STORED`: computed on every insert/update of the source, stored on disk, and
  indexable.
- A view is a separate named query object, not part of a row.

The definition is created once; the value is computed per read or per write
depending on the kind.

**Source:** PR #94 review, `timestamp_columns.py` L28, comment `4493578234`;
follow-up `F8`.

---

#### **Q: Should generated columns never be created? How are they backed up?**

**A:** Generated columns are valid and can be created by migrations. The
restriction is narrower: a **generated timestamp column cannot be registered as a
normal writable projection**. Non-timestamp generated columns such as a lowercase
hash are unaffected.

“Backup” and “backfill” are different. A SQLite backup stores the generated
column's definition, not its values; on restore, SQLite recomputes them. A
generated column needs no backfill because it is derived from its source:
normalize the source and the derived value follows.

**Source:** PR #94 review, `timestamp_columns.py` L28, comment `4493578234`;
follow-up `F8`.

---

#### **Q: Why reject generated timestamps instead of only skipping them in the backfill?**

**A:** Because early rejection is better than a late runtime failure or silent
divergence. If a generated column is registered and included in the writable set,
the backfill issues `UPDATE` and SQLite raises `cannot UPDATE generated column`
during a migration, on someone's database, possibly mid-startup. If it is
silently skipped, it looks supported but is never normalized, which is worse after
#92 changes representations.

Validation therefore fails early and actionably:

```text
timestamp column workflow_runs.archived_at is generated or hidden;
generated timestamp columns are not supported because the backfill cannot write them
```

**Source:** PR #94 review, `tests/storage/test_timestamp_registry.py` L126,
comment `4493727578`; follow-up `F8`.

---

#### **Q: If we need a derived timestamp, where should it live so code is unaffected?**

**A:** Do not persist it as an independently normalized value. Options:

1. **Compute at read time** in the query or a view, keeping the output column name
   the same. No schema column, no backfill.
2. **STORED generated column** with the same name and representation your code
   already expects. Readers keep working; writers never wrote it anyway.
3. Under #92, define it in terms of the new source and drop/re-add it in the same
   migration:
   ```sql
   archived_timestamp_micro INTEGER
       GENERATED ALWAYS AS (created_timestamp_micro) STORED
   ```
   Keep the exported name and type stable so upper layers do not change.

The rule is: derived values are defined next to their source, not normalized
independently. Once that holds, choosing view vs virtual vs stored is a
performance decision (storage, read cost, indexability), not a correctness
decision.

**Source:** PR #94 review, `timestamp_columns.py` L28 and
`tests/storage/test_timestamp_registry.py` L126; follow-up `F12`.

---

#### **Q: Does the representation change affect ordinary columns too?**

**A:** Yes, but differently. Every column has the same representation-change
problem when #92 moves from ISO text to integer micros. Ordinary columns can be
converted with `UPDATE` and are writable by the backfill. Generated columns
cannot be written, and their expression may reference the old source, so they must
be dropped/re-added or the table rebuilt.

**Source:** PR #94 review, `tests/storage/test_timestamp_registry.py` L126,
comment `4493727578`; follow-up `F8`.

---

#### **Q: How is a generated-column migration actually done?**

**A:** SQLite supports more than a full rebuild:

```sql
-- rename the source; the generated expression follows automatically
ALTER TABLE t RENAME COLUMN created_at TO created_ts;

-- drop the generated column when nothing depends on it
ALTER TABLE t DROP COLUMN archived_at;

-- re-add with the new expression
ALTER TABLE t ADD COLUMN archived_at TEXT
    GENERATED ALWAYS AS (upper(created_at)) STORED;
```

For #92, add the new ordinary column, convert values, drop dependent indexes or
triggers, drop and re-add the generated column against the new source, recreate
dependents, then drop the old column when nothing references it.

A full 12-step rebuild is still needed when a dependency cannot be dropped first,
when changing table properties such as `STRICT`, when altering an ordinary
column's type in place, or when the intermediate state would violate a
constraint.

**Source:** PR #94 review, `timestamp_columns.py` L28; follow-up `F12`.

---

### Constraints and NULL Semantics

#### **Q: Why not add `CHECK` or `STRICT` in the registry PR?**

**A:** Because adding either to an existing table requires a rebuild, and #93's
job is the registry safety net. SQLite cannot add a `CHECK` in place, and `STRICT`
is fixed at table creation. A rebuild of the existing tables would mix schema
hardening with the registry change, require a data audit, and risk unrelated
breakage. GEN-24 (#92) is the natural place because it already changes the
timestamp columns and may rebuild tables anyway.

**Source:** PR #94 review, `timestamp_columns.py` L35, comment `4493597139`.

---

#### **Q: Are `STRICT` and `CHECK` good practice? What are the costs?**

**A:** Yes, in the right role, but they are not interchangeable with code
validation.

`STRICT` enforces declared types at the table level. It still allows lossless
conversion (`'12'` becomes `12`, `123` becomes `'123'`) and rejects lossy
conversion (`12.5` into `INTEGER`, `'abc'` into `INTEGER`). It does not enforce
`NOT NULL`, and it cannot be added to an existing table without a rebuild.

`CHECK` enforces a boolean expression on writes. It is good for cheap, stable
physical invariants such as `x >= 0` or `finished >= started`. It is poor for
business rules because changing a `CHECK` requires a table rebuild, and business
rules change often. Keep policy in Pydantic/service code.

**Source:** PR #94 review, `timestamp_columns.py` L35, comment `4493597139`;
follow-up `F9`.

---

#### **Q: What does `NULL` do in a `CHECK`?**

**A:** SQL uses three-valued logic. A `CHECK` fails only when the expression is
`FALSE`; if it evaluates to `NULL`/`UNKNOWN`, the row is accepted:

```sql
CREATE TABLE c (x INTEGER CHECK (x > 0));
INSERT INTO c (x) VALUES (NULL);  -- accepted
INSERT INTO c (x) VALUES (0);     -- rejected
```

So `CHECK (x > 0)` means “if `x` is present, it must be positive”. State the
intent explicitly:

```sql
-- reject NULL explicitly
CHECK (x IS NOT NULL AND x > 0)

-- allow NULL, validate only when present
CHECK (x IS NULL OR x > 0)
```

For nullable timestamps, the second form is usually correct. If the value must be
present, use `NOT NULL` instead of encoding it in `CHECK`.

**Source:** PR #94 review, `timestamp_columns.py` L35, comment `4493597139`;
follow-up `F9`.

---

#### **Q: What did we decide about `STRICT` and `CHECK`?**

**A:** Adopt `CHECK` only, in a separate PR: GEN-26 (#95). Do not adopt `STRICT`.
Keep only physical/structural invariants that will not change with product
policy, and state `NULL` behavior explicitly in each constraint. Business rules
stay in code. The change is blocked by GEN-24 (#92) because it targets the final
integer-microsecond columns, and it is separate from both #92 and #93 so it gets
its own review and verification.

**Source:** PR #94 review, `timestamp_columns.py` L35; follow-up `F13`; GEN-26
(#95).

---

### Tests and SQLite Mechanics

#### **Q: What does the freshly-migrated-schema test cover?**

**A:** It runs `validate_timestamp_columns` against a temporary database with
every migration applied. It asserts that every registered table exists, every
registered column exists, declared types match (`TEXT` now, `INTEGER` later),
nullability matches, no registered column is generated/hidden, and no
timestamp-like column is missing from the registry. It is the single test that
fails if the migrations and `TIMESTAMP_COLUMNS` drift apart.

**Source:** PR #94 review, `tests/storage/test_timestamp_registry.py` L21,
comment `4493656226`.

---

#### **Q: What is pytest `MonkeyPatch`, and where does `monkeypatch.setitem` write?**

**A:** `MonkeyPatch` is a built-in pytest fixture for temporary, automatically
reverted changes to attributes, dict items, environment variables, and similar
state.

In `test_registered_generated_timestamp_column_is_rejected`, this:

```python
monkeypatch.setitem(TIMESTAMP_COLUMNS, "workflow_runs", {...})
```

mutates the imported `TIMESTAMP_COLUMNS` dict **in process memory** for the
duration of the test, storing the old value on the fixture's undo stack. It does
not write to SQLite or disk. After the test, pass or fail, pytest restores the
original entry. That is how the test can simulate “someone registered this
column” without changing the production registry or leaking state.

**Source:** PR #94 review, `tests/storage/test_timestamp_registry.py` L105,
comment `4493711659`; follow-up `F11`.

---

#### **Q: What does “unregistered” mean?**

**A:** The column exists in the live SQLite schema but has no matching entry in
`TIMESTAMP_COLUMNS`. For example, adding:

```sql
ALTER TABLE workflow_runs ADD COLUMN archived_at TEXT
    GENERATED ALWAYS AS (created_at) VIRTUAL;
```

without a registry entry produces:

```text
unregistered timestamp column workflow_runs.archived_at; add it to
pipeline.storage.timestamp_columns.TIMESTAMP_COLUMNS
```

The opposite case is a registered column missing from the database
(`registered timestamp column ... does not exist`). Both are registry/schema
drift.

**Source:** PR #94 review, `tests/storage/test_timestamp_registry.py` L80,
comment `4493717355`; follow-up `F6`.

---

#### **Q: Why does a registered generated timestamp still fail validation?**

**A:** Because registration implies “the backfill may write this column”, and
SQLite forbids writing generated columns. In the test, `monkeypatch` adds
`archived_at` to the registry, then the column is created as
`GENERATED ALWAYS AS (created_at) VIRTUAL`. `table_xinfo` reports
`("TEXT", False, 2)`, and the `hidden` check rejects it before type/nullability
checks:

```text
timestamp column workflow_runs.archived_at is generated or hidden;
generated timestamp columns are not supported because the backfill cannot write them
```

So registration is necessary but not sufficient: support is determined by
writability.

**Source:** PR #94 review, `tests/storage/test_timestamp_registry.py` L126,
comment `4493727578`; follow-up `F8`.

---

#### **Q: What is the suffix-bypass/backfill test?**

**A:** `test_backfill_ignores_unregistered_timestamp_suffix` adds
`schema_migrations.note_at`, fills it with `'not-a-timestamp'`, runs the real
backfill, and asserts the value is unchanged. It proves the backfill does not
guess from `_at`; it only rewrites columns in the registry. This is the
regression against the old `name.endswith("_at")` implementation, which would
have tried to normalize the text and either raised or corrupted it.

Validation would still flag `note_at` as unregistered. Detection and mutation are
separate steps.

**Source:** PR #94 review, `tests/storage/test_timestamp_registry.py` L180,
comment `4493739869`; follow-up `F7`.

---

#### **Q: Do we need the backfill if tables are always written correctly?**

**A:** You do not need an ongoing repair backfill if every write is correct and
there is no legacy data. You still need schema migrations for structural changes,
and GEN-24 (#92) needs a one-time conversion from ISO text to integer micros.
Validation also remains valuable because “I take care of my tables” is a human
process; the registry test proves it.

Backfill is a one-time conversion/repair tool, not a permanent runtime path.

**Source:** PR #94 review, `tests/storage/test_timestamp_registry.py` L180,
comment `4493739869`; follow-up `F7`.

---

#### **Q: What do `@dataclass(frozen=True, slots=True)` and the Java analogy mean?**

**A:** `frozen=True` makes instances immutable and hashable; assigning a field
raises `FrozenInstanceError`. `slots=True` gives the class `__slots__` instead of
a per-instance `__dict__`: lower memory, no arbitrary attribute creation, and a
typo like `col.nullabel = True` fails immediately.

The closest Java analogy is a `record` with all-final components:

```java
record TimestampColumn(TimestampFormat format, boolean nullable) {}
```

`frozen=True` is like `final` fields plus generated `equals`/`hashCode`;
`slots=True` is a fixed field layout with no ability to attach dynamic fields.
Java never allows dynamic fields, so that part is more of a memory-layout
guarantee than a semantic one.

This matters because `TIMESTAMP_COLUMNS` is module-level shared state; immutable
entries prevent one caller or test from mutating the registry for everyone.

**Source:** PR #94 review, `timestamp_columns.py` L70, comment `4493606856`.

---

### PR #94 Decision Summary

| Topic | Decision | Issue |
|-------|----------|-------|
| Timestamp registry | Explicit `TIMESTAMP_COLUMNS` table/column/format/nullability map | GEN-25 (#93) |
| Completeness guard | `_at` and `_timestamp_micro` suffixes are reserved and checked in validation | GEN-25 (#93) |
| Backfill source | Registry-driven; payload timestamps stay Pydantic-directed | GEN-25 (#93) |
| Generated columns | Enumerated with `table_xinfo`; generated timestamp projections rejected | GEN-25 (#93) |
| Migration discipline | Applied migrations are immutable and checksummed; restore bytes or reset dev DB | GEN-25 (#93) |
| Future representation | `*_timestamp_micro` integer microseconds for SQL and payload | GEN-24 (#92) |
| Payload alignment | Rename payload keys and values to integer microseconds; bump schema versions | GEN-24 (#92) |
| Schema constraints | `CHECK` only, physical invariants, explicit `NULL` semantics, no `STRICT` | GEN-26 (#95) |
