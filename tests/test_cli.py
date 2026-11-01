from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _run_cli(
    arguments: list[str],
    *,
    path: str | None = None,
    pipeline_home: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    if path is not None:
        environment["PATH"] = path
    if pipeline_home is not None:
        environment["PIPELINE_HOME"] = str(pipeline_home)
    return subprocess.run(
        [sys.executable, "-m", "pipeline", *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        env=environment,
    )


def test_help_lists_check_setup() -> None:
    completed = _run_cli(["--help"])

    assert completed.returncode == 0
    assert "check-setup" in completed.stdout
    assert "python -m pipeline" in completed.stdout


def test_no_arguments_prints_help() -> None:
    completed = _run_cli([])

    assert completed.returncode == 0
    assert "check-setup" in completed.stdout


def test_check_setup_json_success(fake_bin: Path, tmp_path: Path) -> None:
    pipeline_home = tmp_path / "pipeline-home"

    completed = _run_cli(
        ["check-setup", "--json"],
        path=str(fake_bin),
        pipeline_home=pipeline_home,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["pipeline_home"] == str(pipeline_home.resolve())
    statuses = {check["id"]: check["status"] for check in payload["checks"]}
    assert statuses["ffmpeg"] == "pass"
    assert statuses["remotion-renderer"] == "warn"
    assert payload["summary"]["required_failed"] == 0


def test_check_setup_text_fails_for_missing_media_tools(
    fake_bin: Path, tmp_path: Path
) -> None:
    (fake_bin / "ffmpeg").unlink()
    (fake_bin / "ffprobe").unlink()

    completed = _run_cli(
        ["check-setup"],
        path=str(fake_bin),
        pipeline_home=tmp_path / "pipeline-home",
    )

    assert completed.returncode == 1
    assert "[FAIL] ffmpeg (required)" in completed.stdout
    assert "[FAIL] ffprobe (required)" in completed.stdout
    assert "[WARN] remotion-renderer (optional)" in completed.stdout
    assert "Setup check failed: 2 required check(s) failed." in completed.stdout
    assert "fix:" in completed.stdout
