"""Local runtime path resolution.

Runtime state lives outside version-controlled source files and may be deleted
or archived as one unit. This module resolves and describes the layout; feature
packages own migrations, repositories, and artifact bytes.

Directory Layout:
PIPELINE_HOME/
├── state/
│   └── pipeline.sqlite3          # SQLite database
├── artifacts/
│   ├── .staging/                  # Transient publication files
│   └── sha256/<prefix>/<hash>     # Immutable content-addressed bytes
├── tmp/
│   └── <attempt-id>/workspace-*  # Attempt-scoped scratch space
├── runtime/                       # Runtime ephemeral files
├── logs/                          # Structured logs
└── reports/                       # Validation reports

PIPELINE_HOME Resolution:
1. PIPELINE_HOME env var (if non-empty)
2. $HOME/.local/share/video-automation-pipeline (default)
$HOME falls back to Path.home() if HOME not set

All paths are absolute, expanded (~), and resolved (no symlinks).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

PIPELINE_HOME_ENV = "PIPELINE_HOME"

# Top-level directories required by the local infrastructure baseline.
PIPELINE_DIRECTORIES: tuple[str, ...] = (
    "state",
    "artifacts",
    "tmp",
    "runtime",
    "logs",
    "reports",
)


def resolve_pipeline_home(environ: Mapping[str, str] | None = None) -> Path:
    """Return the absolute ``PIPELINE_HOME`` path.

    ``PIPELINE_HOME`` wins when set to a non-empty value. Otherwise the default
    is ``$HOME/.local/share/video-automation-pipeline`` so that runtime files
    are not placed inside the repository.
    """

    env = os.environ if environ is None else environ
    configured = env.get(PIPELINE_HOME_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    home = env.get("HOME", "").strip()
    base = Path(home).expanduser() if home else Path.home()
    return (base / ".local" / "share" / "video-automation-pipeline").resolve()


def default_database_path(environ: Mapping[str, str] | None = None) -> Path:
    """Return the default local SQLite database path under ``PIPELINE_HOME``."""

    return resolve_pipeline_home(environ) / "state" / "pipeline.sqlite3"


def default_artifact_root(environ: Mapping[str, str] | None = None) -> Path:
    """Return the default immutable artifact root under ``PIPELINE_HOME``."""

    return resolve_pipeline_home(environ) / "artifacts"


def default_tmp_root(environ: Mapping[str, str] | None = None) -> Path:
    """Return the default disposable workspace root under ``PIPELINE_HOME``."""

    return resolve_pipeline_home(environ) / "tmp"


__all__ = [
    "PIPELINE_DIRECTORIES",
    "PIPELINE_HOME_ENV",
    "default_artifact_root",
    "default_database_path",
    "default_tmp_root",
    "resolve_pipeline_home",
]
