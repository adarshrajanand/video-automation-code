from __future__ import annotations

from pathlib import Path

from pipeline.paths import resolve_pipeline_home


def test_default_home_is_outside_the_repository(tmp_path: Path) -> None:
    resolved = resolve_pipeline_home({"HOME": str(tmp_path)})

    assert (
        resolved
        == (tmp_path / ".local" / "share" / "video-automation-pipeline").resolve()
    )


def test_configured_home_wins(tmp_path: Path) -> None:
    configured = tmp_path / "custom-pipeline-home"

    resolved = resolve_pipeline_home(
        {
            "HOME": str(tmp_path / "ignored-home"),
            "PIPELINE_HOME": str(configured),
        }
    )

    assert resolved == configured.resolve()


def test_empty_configured_home_uses_default(tmp_path: Path) -> None:
    resolved = resolve_pipeline_home(
        {
            "HOME": str(tmp_path),
            "PIPELINE_HOME": "   ",
        }
    )

    assert (
        resolved
        == (tmp_path / ".local" / "share" / "video-automation-pipeline").resolve()
    )
