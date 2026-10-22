"""Local runtime path resolution.

Runtime state lives outside version-controlled source files and may be deleted
or archived as one unit. This module only resolves and describes the layout;
later work packages will add migrations, artifact storage, and databases.
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
