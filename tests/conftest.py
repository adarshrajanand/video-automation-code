from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest


def _write_tool(path: Path, version_output: str) -> None:
    path.write_text(
        f"#!/bin/sh\nprintf '%s\\n' '{version_output}'\nexit 0\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


@pytest.fixture
def write_tool() -> Callable[[Path, str], None]:
    return _write_tool


@pytest.fixture
def fake_bin(tmp_path: Path, write_tool: Callable[[Path, str], None]) -> Path:
    bin_directory = tmp_path / "fake-bin"
    bin_directory.mkdir()
    write_tool(bin_directory / "node", "v24.1.0")
    write_tool(bin_directory / "npm", "11.0.0")
    write_tool(bin_directory / "ffmpeg", "ffmpeg version 7.0.2")
    write_tool(bin_directory / "ffprobe", "ffprobe version 7.0.2")
    return bin_directory


@pytest.fixture
def setup_env(fake_bin: Path, tmp_path: Path) -> dict[str, str]:
    return {
        "PATH": str(fake_bin),
        "PIPELINE_HOME": str(tmp_path / "pipeline-home"),
    }
