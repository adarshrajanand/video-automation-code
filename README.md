# AI Video Automation Pipeline

Bootstrap shell for a local-first, modular-monolith video pipeline. This
repository currently implements FV-01 through FV-03: the Python package
skeleton, CLI entry point, local setup diagnostics, versioned Pydantic
contracts, deterministic fingerprint/ID helpers, committed JSON Schemas with
fixtures, a typed SQLite repository with ordered migrations, and an immutable
local `ArtifactStore`.

It does **not** implement workflow scheduling or readiness evaluation, outbox
dispatch, provider adapters, or media stage logic. There are no provider SDKs,
credentials, network calls, or real media generation.

## Prerequisites

| Tool | Requirement | Used for |
|---|---|---|
| Python | 3.12.x | Control plane and CLI |
| [uv](https://docs.astral.sh/uv/) | Current release | Dependency management and command execution |
| Node.js | 20.0.0 or newer | Future Remotion renderer |
| npm | 9.0.0 or newer | Future Remotion renderer |
| FFmpeg | Working `ffmpeg` and `ffprobe` binaries | Future media inspection and rendering |
| SQLite | Standard CPython `sqlite3` support | Local durable repository |

Install system media tools before running the setup check. For example, on
Debian/Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
```

Install Python and Node.js with your normal version manager, then confirm:

```bash
python3.12 --version
node --version
npm --version
ffmpeg -version
ffprobe -version
```

## Local setup

From the repository root:

```bash
uv sync
uv run python -m pipeline --help
uv run python -m pipeline check-setup
uv run python -m pipeline db migrate
uv run python -m pipeline db status
```

`uv sync` installs the project in editable mode plus the `dev` dependency group
(pytest and ruff). `uv.lock` is committed so the same versions are selected on
every machine.

`check-setup` prints one line per check and exits non-zero if a required
prerequisite is missing or unusable. It does not stop at the first failure, and
it still reports optional capability status when a required check fails.

For machine-readable output:

```bash
uv run python -m pipeline check-setup --json
```

Exit codes:

| Code | Meaning |
|---|---|
| `0` | Every required check passed; optional warnings are allowed |
| `1` | At least one required check failed |
| `2` | Invalid command-line usage |

## Configuration

The CLI reads process environment variables. It does **not** auto-load `.env`
in FV-01; export variables in your shell or use your preferred environment
manager. `.env.example` lists names only and contains no credentials.

| Variable | Default | Purpose |
|---|---|---|
| `PIPELINE_HOME` | `$HOME/.local/share/video-automation-pipeline` | Runtime root outside versioned source |
| `PIPELINE_NODE_BINARY` | `node` | Alternative Node.js executable or name |
| `PIPELINE_NPM_BINARY` | `npm` | Alternative npm executable or name |
| `PIPELINE_FFMPEG_BINARY` | `ffmpeg` | Alternative FFmpeg executable or path |
| `PIPELINE_FFPROBE_BINARY` | `ffprobe` | Alternative ffprobe executable or path |

`check-setup` creates the runtime root and these top-level directories if they
do not exist. FV-03 keeps its database, immutable bytes, and disposable
workspaces inside the same root:

```text
PIPELINE_HOME/
├── state/
│   └── pipeline.sqlite3
├── artifacts/
│   ├── .staging/                 # transient publication files
│   └── sha256/<prefix>/<hash>    # immutable content-addressed bytes
├── tmp/
│   └── <attempt-id>/workspace-*  # attempt-scoped scratch space
├── runtime/
├── logs/
└── reports/
```

Runtime state is local-only and must not be committed or stored on a shared
network filesystem. Artifact URIs are opaque: callers receive
`artifact://sha256/<hash>` and must not derive workflow meaning from the hash or
from the physical path.

## Checks performed

| Check ID | Required | What it verifies |
|---|---|---|
| `python-version` | Yes | The active interpreter is CPython 3.12.x |
| `pipeline-package` | Yes | The `video-automation-pipeline` distribution is installed |
| `node` | Yes | `node` is executable and at least version 20.0.0 |
| `npm` | Yes | `npm` is executable and at least version 9.0.0 |
| `remotion-renderer` | No | `packages/renderer/package.json` declares Remotion, when present |
| `ffmpeg` | Yes | `ffmpeg` is executable and reports a version |
| `ffprobe` | Yes | `ffprobe` is executable and reports a version |
| `pipeline-home` | Yes | `PIPELINE_HOME` exists, is a directory, and accepts writes |
| `pipeline-home-layout` | Yes | Every required runtime subdirectory is writable |
| `sqlite` | Yes | SQLite enables foreign keys and rolls back transactions |

The Remotion check is optional in FV-01 because the TypeScript renderer package
is deferred. It inspects a local manifest only; it never runs `npx`, installs
packages, or contacts the network. A missing renderer is surfaced as a warning,
not as a passing required check.

## Contracts

FV-02 adds strict Pydantic v2 contract models under `src/pipeline/contracts/`.
The public surface covers:

- configuration, workflow graphs, runs, stage instances, attempts, and manifests;
- jobs, leases, capabilities, budgets, routing, and provider invocation records;
- artifacts, lineage, pointers, invalidation, quality gates, and repair plans;
- human review, publication boundaries, events, outbox/inbox delivery, and profiles;
- minimal editorial references for packages, episodes, cuts, sequences, scenes,
  shots, layers, and composition references.

Contract records reject unknown core fields, require timezone-aware timestamps,
normalize them to UTC, require lowercase SHA-256 digests, and validate cross-field
references and workflow graph invariants. Free-form JSON is accepted only in
declared extension fields such as `payload`, `metadata`, `properties`, and
`safe_details`.

Synthetic editorial/research/script/speech/render stage payloads are deferred to
later work packages. The contracts here define only the references and control
plane needed to persist and validate them.

Deterministic helpers live in `src/pipeline/ids.py` and
`src/pipeline/fingerprints.py`. Canonical JSON sorts keys, normalizes UTC
datetimes and decimals, and redacts common secret-bearing keys for fingerprints.
Prefixed IDs, run keys, and idempotency keys are opaque; callers must not parse
semantics back out of them.

JSON Schemas are committed under `schemas/` with a content-hash manifest. Do not
edit generated schema files by hand. Verify or regenerate them with:

```bash
uv run python -m pipeline contracts export-schemas --check
uv run python -m pipeline contracts export-schemas
```

Valid and invalid fixtures live under `fixtures/contracts/`. Every public
contract has one valid fixture; `fixtures/contracts/invalid_manifest.json`
records the expected validation error for each invalid fixture.

## Local persistence and artifacts

FV-03 adds the local durable layer under `src/pipeline/storage/`.

### SQLite database and migrations

The default database is `PIPELINE_HOME/state/pipeline.sqlite3`. Migrations are
ordered SQL files shipped in `src/pipeline/storage/migrations/` and are recorded
in `schema_migrations` with their name, checksum, and application time. Running
`migrate` again is a no-op. Editing an already-applied migration is refused; add
a new migration instead.

```bash
uv run python -m pipeline db migrate
uv run python -m pipeline db status
uv run python -m pipeline db migrate --database /path/to/pipeline.sqlite3
```

Connections enable `PRAGMA foreign_keys=ON`, a bounded busy timeout (5 seconds by
default), and WAL where the filesystem and SQLite build support it. Transactions
use `BEGIN IMMEDIATE` by default and always commit or roll back before the
per-operation connection closes:

```python
from pipeline.storage import (
    Database,
    EffectiveConfigRepository,
    WorkflowRunRepository,
)

database = Database("state/pipeline.sqlite3")
with database.transaction() as connection:
    EffectiveConfigRepository(connection).insert(config)
    WorkflowRunRepository(connection).insert(run)
```

Repositories accept a connection rather than owning one, so several writes can
share one transaction. Each table stores the canonical contract as a JSON
`payload` plus extracted identity, status, and timestamp columns used by
uniqueness constraints and indexes. Loaded payloads are revalidated through the
Pydantic model. Repository failures are typed as `NotFoundError`,
`ConflictError`, or `IntegrityError` rather than leaking SQLite message text.

Typed repositories cover effective config, workflow runs, stage instances,
stage attempts, jobs, leases, idempotency records, budget reservations,
artifacts, artifact dependencies, artifact pointers, and the editorial hierarchy
(content package, episode, cut, sequence, scene, shot, layer, composition ref).
Tables also exist for input manifests, artifact invalidation requests/results,
quality records, human review and publication, events and outbox/inbox delivery,
routing/provider/capability and usage records, and recovery decisions. Those
families deliberately do not have typed repositories yet; later work packages
add them.

### Immutable artifact store

`ArtifactStore` publishes bytes under `PIPELINE_HOME/artifacts`, addressed by
lowercase SHA-256. Publication writes and fsyncs a temporary file before an
atomic link into the content-addressed path. Existing bytes are verified on
collision and are never overwritten with different content. Duplicate content
deduplicates naturally. Attempt workspaces live under `PIPELINE_HOME/tmp` and
are removed after use, including on failure.

```python
from pipeline.paths import resolve_pipeline_home
from pipeline.storage import ArtifactStore

store = ArtifactStore(pipeline_home=resolve_pipeline_home())
stored = store.publish_bytes(b"render output")
assert store.read(stored.uri) == b"render output"
store.verify(stored.uri, expected_sha256=stored.sha256)

with store.workspace("attempt_01") as workspace:
    temporary_output = workspace / "output.bin"
    temporary_output.write_bytes(b"render output")
    store.publish_file(temporary_output)
```

Artifact URIs use the opaque form `artifact://sha256/<hash>`. Stages should pass
the URI through without parsing it; the store can move to another physical
location later without changing artifact ID, hash, dependencies, or provenance.
Missing or corrupt bytes raise `ArtifactNotFoundError` or
`ArtifactIntegrityError`, and a mismatched declared hash raises
`HashMismatchError` before publication.

## Development checks

Run from the repository root:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Use `uv run ruff format .` to apply formatting.

## Repository layout

```text
src/pipeline/          Python package, CLI, and versioned contracts
src/pipeline/storage/  SQLite helpers, migrations, repositories, ArtifactStore
tests/                 Unit, contract, CLI, and storage tests
tests/storage/         Migration, transaction, repository, and artifact tests
fixtures/contracts/    Deterministic valid and invalid contract fixtures
schemas/               Generated JSON Schemas and content-hash manifest
```

## Scope boundaries

- Local modular monolith only; no remote infrastructure or service split.
- No provider SDKs, API keys, paid calls, or network access from setup checks.
- No workflow scheduling, readiness evaluation, outbox dispatch, provider calls,
  or stage business logic yet.
- Artifacts and runtime data stay under `PIPELINE_HOME`, never in Git.
- The canonical architecture and implementation plans live in the separate
  documentation repository; this README covers the code bootstrap only.
