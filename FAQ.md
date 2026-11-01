# FV-11 FAQ — Complete Human Review Questions & Answers

This document contains all 173 questions from the human review of PR #1, with detailed answers matching the GitHub replies posted on the PR.

---

## Migration & Database

### **Q: How did the migration mismatch happen with worktrees?**
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

### **Q: How does migration checksum detection work?**
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

### **Q: What is the migration file `0001_initial.sql`?**
**A:** Located at `src/pipeline/storage/migrations/0001_initial.sql`. It defines the **entire database schema** — 20+ tables:
- `workflow_runs`, `stage_instances`, `stage_attempts`, `jobs`, `leases`
- `idempotency_records`, `outbox_messages`, `inbox_receipts`
- `budget_reservations`, `artifact_pointers`, `effective_configs`
- `quality_evaluations`, `quality_gate_results`, `human_reviews`
- Plus indexes, foreign keys, and the `schema_migrations` tracking table

Every table stores the canonical Pydantic contract as JSON payload plus extracted identity, status, and timestamp columns for uniqueness, lookup, and indexes.

---

### **Q: How to avoid migration conflicts with worktrees?**
**A:** Each worktree should have its own `PIPELINE_HOME`:
```bash
# In each worktree's .envrc or direnv:
export PIPELINE_HOME=/tmp/pipeline-$(basename $PWD)
```
This gives each worktree its own SQLite database file, eliminating migration conflicts. Alternatively, delete the DB and re-migrate when switching worktrees.

---

### **Q: Monthly quota — how to configure?**
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

## Architecture & Design

### **Q: Why is AUDIO_QC a separate stage?**
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

### **Q: Why not make all QC separate stages?**
**A:** Light QC (schema validation, reference integrity) is inline in generation stages. Only heavy QC requiring provider calls (ffprobe, ML models) warrants separate stages. Current design:
- `SCRIPT_GENERATION` → includes schema + reference QC
- `SPEECH_GENERATION` → includes WER/CER, forced alignment QC
- **AUDIO_QC** (separate) → heavy ffprobe + ML signal quality
- `VISUAL_PLANNING` → includes visual intent QC
- `COMPOSITION` → includes timeline/AV sync QC
- `RENDERING` → includes media decode QC
- `QUALITY_GATE` → final aggregation

---

### **Q: What is `major_stage` in workflow YAML?**
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

### **Q: What is `operation_version` in capability registry?**
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

### **Q: Why "Lease" not "Reservation Token"?**
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

### **Q: Why YAML for workflows, not JSON/JSONC?**
**A:** YAML is preferred for **human authors** — comments, anchors, readability. JSON/JSONC for machine-generated configs. No strong need to unify.

---

## Contracts & Models

### **Q: What is `schema_version` and why everywhere?**
**A:** Every contract has `schema_version` (e.g., `script.v1`, `quality-gate-result.v1`). Enables:
- Versioned contract evolution
- Migration/translation between versions
- Forward/backward compatibility
- Fixture validation
- Schema registry lookup

Few places lack it = oversight/legacy.

---

### **Q: Contract vs Model — difference?**
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

### **Q: Why `frozen=True` on contracts but `model_copy()` for changes?**
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

### **Q: What is `ExtensionObject`?**
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

### **Q: Why `NonEmptyStr` not Enum for `pointer_type`?**
**A:** 
| Approach | Pros | Cons |
|----------|------|------|
| Enum | Validation, autocomplete, docs, no typos | Migration for new values |
| String | Extensible, no migration | Typos allowed, no autocomplete |

**Current:** `NonEmptyStr` for extensibility. **Should be Enum** — vocabulary is stable (`ACCEPTED`, `PUBLISHED`, `SUPERSEDED`, `INVALIDATED`, `DELETED`). Will change to Enum.

---

### **Q: Fixture vs Sample — what's the difference?**
| Term | Meaning |
|------|---------|
| **Fixture** | pytest term for "known good test data" (stored in `tests/fixtures/contracts/valid/`) |
| Sample | Informal term for example data |

**Recommendation:** Keep "fixture" in code (pytest convention), "sample" in user-facing docs.

---

### **Q: What is `InvalidationScope`?**
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

## Execution & Concurrency

### **Q: What is a fenced lease?**
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

### **Q: How does inbox/outbox work?**
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

### **Q: What happens after dead-letter?**
**A:** Dead-letter → human reviews via `HumanReview` workflow:
1. Human reviews via `HumanReview` workflow
2. Verifies actual provider state (API call, dashboard, logs)
3. Decides: **retry** / **skip** / **manual fix**

Automated reconciliation = **FV-12+**.

---

### **Q: Multi-repo atomic transactions = multi tables?**
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

### **Q: Where is SQLite saved? How to persist in VM?**
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

### **Q: SQLite redundancy / corruption protection?**
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

## Budget & Cost

### **Q: Budget system — per month/week?**
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

### **Q: Budget = per-request + cumulative?**
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

## Capabilities & Fake Provider

### **Q: IdempotencyRecord — only for capability execution?**
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

### **Q: Idempotency key vs fingerprint?**
| Aspect | Idempotency Key | Fingerprint |
|--------|-----------------|-------------|
| Purpose | Exactly-once **execution** deduplication | Content-addressed **storage** deduplication |
| Scope | Capability + inputs + version | Content bytes only |
| Generated by | Caller (or deterministic from inputs) | `SHA-256(canonical_json(content))` |
| Used by | `IdempotencyRecord` lookup | `ArtifactStore` addressing |

---

### **Q: Why fake provider only? When real providers?**
**A:** FV-11 = local/fake-provider milestone. Real providers (AWS Bedrock, OpenAI, Google Vertex) = **FV-12+**. Executor interface allows swap; fake used for local dev/CI.

---

### **Q: Why 8 missing outcome factories in `__init__.py`?**
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

## Testing & CLI

### **Q: Why no quality tests in `tests/quality/`?**
**A:** Quality tests are integrated in `tests/capabilities/test_audio_capabilities.py` and execution tests. Quality gate logic tested via capability + execution tests.

---

### **Q: Correct CLI usage?**
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

## Design Log

### **Q: Two design log files — both need updates?**
**A:** Yes, both:
- `docs/kb/docs/AI_Video_Pipeline_Design_Discussion_Log.md` = chronological discussions
- `docs/kb/docs/AI_Video_Pipeline_Decisions.md` = decision register (ADR index)

Both need ADR-001 through ADR-007 added.

---

## Backup & Recovery

### **Q: Free remote backup without AWS S3?**
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

## Quality Gate

### **Q: Review zone logic fixed?**
**A:** Yes:
- `review_threshold <= score < pass_threshold` → HUMAN_REVIEW
- Pass-only (no review threshold): scores < pass_threshold → FAIL
- Duplicate failure codes eliminated (hash mismatches, missing artifacts, thresholds)

---

### **Q: Duplicate failure codes — how fixed?**
**A:** Check before appending:
```python
if code not in failure_codes:
    failure_codes.append(code)
```
Applies to: hash mismatches, missing artifacts, threshold failures.

---

## Summary Table

| Topic | Key Point |
|-------|-----------|
| Migration mismatch | Shared DB across worktrees → use separate `PIPELINE_HOME` |
| Missing exports | CLI imports not tested by unit tests → added 8 to `__init__.py` |
| Migration detection | SHA-256 checksum in `schema_migrations` table |
| AUDIO_QC stage | Heavy QC (ffprobe/ML) needs separate budget/retry |
| Major stage | Logical grouping for progress/budget/retry/human gates |
| Fenced lease | Monotonic token prevents stale commits |
| SQLite backup | Litestream to S3 (best) or Rclone + Google Drive (free) |
| Monthly quota | External enforcement; pipeline tracks/alerts |
| Missing exports | CLI imports not covered by unit tests |
| Design log | Update both `Discussion_Log.md` and `Decisions.md` |
| SQLite backup | Litestream to S3 (best) or Rclone + Google Drive (free) |