# AI Video Automation Pipeline

Bootstrap shell for a local-first, modular-monolith video pipeline. This
repository currently implements FV-01 only: the Python package skeleton, CLI
entry point, local setup diagnostics, and the empty `PIPELINE_HOME` workspace
layout.

It does **not** implement workflow state, durable contracts, SQLite
repositories, provider adapters, or media stage logic. There are no provider
SDKs, credentials, network calls, or real media generation.

## Prerequisites

| Tool | Requirement | Used for |
|---|---|---|
| Python | 3.12.x | Control plane and CLI |
| [uv](https://docs.astral.sh/uv/) | Current release | Dependency management and command execution |
| Node.js | 20.0.0 or newer | Future Remotion renderer |
| npm | 9.0.0 or newer | Future Remotion renderer |
| FFmpeg | Working `ffmpeg` and `ffprobe` binaries | Future media inspection and rendering |
| SQLite | Standard CPython `sqlite3` support | Future local repository |

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
do not exist:

```text
PIPELINE_HOME/
├── state/
├── artifacts/
├── tmp/
├── runtime/
├── logs/
└── reports/
```

Only the empty directory skeleton is created. Later work packages add database
migrations, artifact quarantine, and workflow records. Runtime state is
local-only and must not be committed or stored on a shared network filesystem.

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
src/pipeline/          Python package and CLI
tests/                 Unit and CLI tests with fake local toolchains
fixtures/              Reserved for deterministic fast-validation fixtures
```

## Scope boundaries

- Local modular monolith only; no remote infrastructure or service split.
- No provider SDKs, API keys, paid calls, or network access from setup checks.
- No workflow state, contracts, SQLite repositories, or stage logic yet.
- Artifacts and runtime data stay under `PIPELINE_HOME`, never in Git.
- The canonical architecture and implementation plans live in the separate
  documentation repository; this README covers the code bootstrap only.
