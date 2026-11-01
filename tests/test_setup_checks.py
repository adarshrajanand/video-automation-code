from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pipeline.paths import PIPELINE_DIRECTORIES
from pipeline.setup_checks import CheckResult, CheckStatus, SetupReport, collect_checks

REQUIRED_CHECK_IDS = {
    "python-version",
    "pipeline-package",
    "node",
    "npm",
    "ffmpeg",
    "ffprobe",
    "pipeline-home",
    "pipeline-home-layout",
    "sqlite",
}


def _results_by_id(report: SetupReport) -> dict[str, CheckResult]:
    return {check.check_id: check for check in report.checks}


def test_setup_succeeds_with_fake_toolchain(
    setup_env: dict[str, str], tmp_path: Path
) -> None:
    report = collect_checks(environ=setup_env, project_root=tmp_path / "project")

    assert report.ok is True
    results = _results_by_id(report)
    assert set(results) >= REQUIRED_CHECK_IDS
    for check_id in REQUIRED_CHECK_IDS:
        assert results[check_id].status is CheckStatus.PASS, results[check_id]
    assert results["remotion-renderer"].status is CheckStatus.WARN
    assert "deferred beyond FV-01" in results["remotion-renderer"].detail

    pipeline_home = Path(setup_env["PIPELINE_HOME"])
    for name in PIPELINE_DIRECTORIES:
        directory = pipeline_home / name
        assert directory.is_dir()
        assert list(directory.iterdir()) == []


def test_report_json_contract(setup_env: dict[str, str], tmp_path: Path) -> None:
    report = collect_checks(environ=setup_env, project_root=tmp_path / "project")
    payload = report.to_dict()

    assert payload["ok"] is True
    assert payload["pipeline_home"] == str(Path(setup_env["PIPELINE_HOME"]).resolve())
    assert payload["summary"] == {
        "checks": 10,
        "passed": 9,
        "warnings": 1,
        "failed": 0,
        "required_failed": 0,
    }
    assert len(payload["checks"]) == 10
    for check in payload["checks"]:
        assert set(check) == {
            "id",
            "title",
            "required",
            "status",
            "detail",
            "remediation",
        }


def test_missing_media_tools_fail_closed_and_show_optional_status(
    fake_bin: Path, setup_env: dict[str, str], tmp_path: Path
) -> None:
    (fake_bin / "ffmpeg").unlink()
    (fake_bin / "ffprobe").unlink()

    report = collect_checks(environ=setup_env, project_root=tmp_path / "project")

    assert report.ok is False
    results = _results_by_id(report)
    assert results["ffmpeg"].status is CheckStatus.FAIL
    assert results["ffprobe"].status is CheckStatus.FAIL
    assert results["ffmpeg"].remediation is not None
    assert results["ffprobe"].remediation is not None
    assert results["node"].status is CheckStatus.PASS
    assert results["pipeline-home"].status is CheckStatus.PASS
    assert results["sqlite"].status is CheckStatus.PASS
    assert results["remotion-renderer"].status is CheckStatus.WARN
    assert len(report.required_failed) == 2


def test_old_node_version_fails(
    fake_bin: Path,
    setup_env: dict[str, str],
    tmp_path: Path,
    write_tool: Callable[[Path, str], None],
) -> None:
    write_tool(fake_bin / "node", "v18.20.4")

    report = collect_checks(environ=setup_env, project_root=tmp_path / "project")

    assert report.ok is False
    node = _results_by_id(report)["node"]
    assert node.status is CheckStatus.FAIL
    assert node.detail == (
        f"Node.js v18.20.4 at {fake_bin / 'node'}; minimum supported version is 20.0.0."
    )


def test_unwritable_pipeline_home_fails_but_other_checks_run(
    setup_env: dict[str, str], tmp_path: Path
) -> None:
    blocked_home = tmp_path / "blocked-home"
    blocked_home.write_text("not a directory", encoding="utf-8")
    setup_env["PIPELINE_HOME"] = str(blocked_home)

    report = collect_checks(environ=setup_env, project_root=tmp_path / "project")

    assert report.ok is False
    results = _results_by_id(report)
    assert results["pipeline-home"].status is CheckStatus.FAIL
    assert results["pipeline-home-layout"].status is CheckStatus.FAIL
    assert "blocked-home" in results["pipeline-home"].detail
    assert results["node"].status is CheckStatus.PASS
    assert results["sqlite"].status is CheckStatus.PASS
    assert results["remotion-renderer"].status is CheckStatus.WARN


def test_blocked_pipeline_subdirectory_fails_setup(
    setup_env: dict[str, str], tmp_path: Path
) -> None:
    pipeline_home = Path(setup_env["PIPELINE_HOME"])
    pipeline_home.mkdir(parents=True)
    (pipeline_home / "state").write_text("not a directory", encoding="utf-8")

    report = collect_checks(environ=setup_env, project_root=tmp_path / "project")

    assert report.ok is False
    results = _results_by_id(report)
    assert results["pipeline-home"].status is CheckStatus.PASS
    assert results["pipeline-home-layout"].status is CheckStatus.FAIL
    assert "state:" in results["pipeline-home-layout"].detail
    assert results["node"].status is CheckStatus.PASS


def test_remotion_manifest_is_optional_and_detected(
    setup_env: dict[str, str], tmp_path: Path
) -> None:
    project_root = tmp_path / "project"
    renderer = project_root / "packages" / "renderer"
    renderer.mkdir(parents=True)
    (renderer / "package.json").write_text(
        '{"dependencies": {"remotion": "4.0.300"}}',
        encoding="utf-8",
    )

    report = collect_checks(environ=setup_env, project_root=project_root)

    assert report.ok is True
    remotion = _results_by_id(report)["remotion-renderer"]
    assert remotion.status is CheckStatus.PASS
    assert "Remotion 4.0.300" in remotion.detail
