from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.cli import main


def test_db_help_lists_actions(capsys) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["db", "--help"])

    captured = capsys.readouterr()
    assert raised.value.code == 0
    assert "migrate" in captured.out
    assert "status" in captured.out


def test_db_migrate_then_status_then_noop(tmp_path: Path, capsys) -> None:
    database = tmp_path / "state" / "pipeline.sqlite3"

    assert main(["db", "migrate", "--database", str(database)]) == 0
    first = capsys.readouterr().out
    assert "Applied 1 migration(s)" in first
    assert "Schema version: 1" in first
    assert database.is_file()

    assert main(["db", "migrate", "--database", str(database)]) == 0
    second = capsys.readouterr().out
    assert "No pending migrations" in second
    assert "Schema version: 1" in second

    assert main(["db", "status", "--database", str(database)]) == 0
    status = capsys.readouterr().out
    assert f"Database: {database}" in status
    assert "Current version: 1" in status
    assert "0001_initial" in status
    assert "Pending migrations:" in status
    assert "(none)" in status


def test_db_status_before_migrate_reports_pending(tmp_path: Path, capsys) -> None:
    database = tmp_path / "state" / "pipeline.sqlite3"

    assert main(["db", "status", "--database", str(database)]) == 0

    output = capsys.readouterr().out
    assert "Current version: 0" in output
    assert "0001_initial" in output


def test_db_defaults_to_pipeline_home(tmp_path: Path, monkeypatch, capsys) -> None:
    pipeline_home = tmp_path / "pipeline-home"
    monkeypatch.setenv("PIPELINE_HOME", str(pipeline_home))

    assert main(["db", "migrate"]) == 0

    output = capsys.readouterr().out
    default_database = pipeline_home / "state" / "pipeline.sqlite3"
    assert f"Database: {default_database}" in output
    assert default_database.is_file()


def test_db_without_action_prints_usage(capsys) -> None:
    assert main(["db"]) == 0

    assert "Usage: python -m pipeline db" in capsys.readouterr().out
