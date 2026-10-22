from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pipeline.storage import (
    Database,
    MigrationChecksumError,
    MigrationError,
    MigrationRunner,
    discover_migrations,
)


def _copy_migrations(target: Path) -> Path:
    source = Path(__file__).resolve().parents[2] / "src" / "pipeline" / "storage"
    directory = target / "migrations"
    shutil.copytree(source / "migrations", directory)
    return directory


def test_discovered_migrations_are_ordered_and_checksummed() -> None:
    migrations = discover_migrations()

    assert len(migrations) >= 1
    assert [migration.version for migration in migrations] == sorted(
        migration.version for migration in migrations
    )
    assert all(len(migration.checksum) == 64 for migration in migrations)


def test_migrate_is_idempotent_and_records_checksums(tmp_path: Path) -> None:
    database = Database(tmp_path / "state" / "pipeline.sqlite3")
    runner = MigrationRunner(database)

    before = runner.status()
    assert before.current_version == 0
    assert before.is_up_to_date is False
    assert before.pending

    first = runner.migrate()
    assert first.changed is True
    assert first.current_version == len(runner.migrations)
    assert len(first.applied) == len(runner.migrations)

    second = runner.migrate()
    assert second.changed is False
    assert second.applied == ()
    assert second.current_version == first.current_version

    with database.connection() as connection:
        rows = connection.execute(
            "SELECT version, name, checksum, applied_at FROM schema_migrations "
            "ORDER BY version"
        ).fetchall()
    assert len(rows) == len(runner.migrations)
    for row, migration in zip(rows, runner.migrations, strict=True):
        assert row[0] == migration.version
        assert row[1] == migration.name
        assert row[2] == migration.checksum
        assert row[3].endswith("Z")


def test_initial_schema_contains_every_durable_family(tmp_path: Path) -> None:
    database = Database(tmp_path / "state" / "pipeline.sqlite3")
    MigrationRunner(database).migrate()

    with database.connection() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert {
        "schema_migrations",
        "effective_configs",
        "workflow_runs",
        "stage_instances",
        "stage_attempts",
        "jobs",
        "leases",
        "idempotency_records",
        "budget_reservations",
        "artifacts",
        "artifact_dependencies",
        "artifact_pointers",
        "artifact_invalidation_requests",
        "artifact_invalidation_results",
        "input_manifests",
        "quality_checks",
        "quality_gate_policies",
        "quality_input_manifests",
        "quality_evaluations",
        "quality_gate_results",
        "repair_plans",
        "human_reviews",
        "human_review_decisions",
        "publication_requests",
        "publication_attempts",
        "workflow_events",
        "outbox_messages",
        "inbox_receipts",
        "routing_decisions",
        "capability_executions",
        "provider_invocations",
        "usage_records",
        "recovery_decisions",
        "content_packages",
        "episodes",
        "cuts",
        "sequences",
        "scenes",
        "shots",
        "layer_instances",
        "composition_refs",
    } <= tables


def test_status_reports_pending_without_applying_schema(tmp_path: Path) -> None:
    database = Database(tmp_path / "state" / "pipeline.sqlite3")
    runner = MigrationRunner(database)

    status = runner.status()

    assert status.current_version == 0
    assert status.pending == runner.migrations
    with database.connection() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert "schema_migrations" in tables
    assert "workflow_runs" not in tables


def test_changed_applied_migration_is_refused(tmp_path: Path) -> None:
    migrations_dir = _copy_migrations(tmp_path)
    database = Database(tmp_path / "state" / "pipeline.sqlite3")
    MigrationRunner(database, migrations_dir=migrations_dir).migrate()

    migration_file = migrations_dir / "0001_initial.sql"
    migration_file.write_text(
        migration_file.read_text(encoding="utf-8") + "\n-- changed after apply\n",
        encoding="utf-8",
    )
    runner = MigrationRunner(database, migrations_dir=migrations_dir)

    with pytest.raises(MigrationChecksumError, match="changed after it was applied"):
        runner.status()
    with pytest.raises(MigrationChecksumError):
        runner.migrate()


def test_missing_applied_migration_is_refused(tmp_path: Path) -> None:
    migrations_dir = _copy_migrations(tmp_path)
    database = Database(tmp_path / "state" / "pipeline.sqlite3")
    MigrationRunner(database, migrations_dir=migrations_dir).migrate()

    (migrations_dir / "0001_initial.sql").unlink()
    runner = MigrationRunner(database, migrations_dir=migrations_dir)

    with pytest.raises(MigrationError, match="no local file"):
        runner.status()


def test_failed_migration_rolls_back_and_is_not_recorded(tmp_path: Path) -> None:
    migrations_dir = _copy_migrations(tmp_path)
    (migrations_dir / "0002_broken.sql").write_text(
        "CREATE TABLE should_not_survive (id INTEGER PRIMARY KEY);\n"
        "INSERT INTO missing_table (id) VALUES (1);\n",
        encoding="utf-8",
    )
    database = Database(tmp_path / "state" / "pipeline.sqlite3")
    runner = MigrationRunner(database, migrations_dir=migrations_dir)

    with pytest.raises(MigrationError, match="0002_broken failed"):
        runner.migrate()

    status = runner.status()
    assert status.current_version == 1
    assert [migration.version for migration in status.pending] == [2]
    with database.connection() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert "should_not_survive" not in tables


def test_non_contiguous_migrations_are_rejected(tmp_path: Path) -> None:
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "0002_second.sql").write_text(
        "CREATE TABLE second (id INTEGER);\n", encoding="utf-8"
    )

    with pytest.raises(MigrationError, match="contiguous"):
        discover_migrations(migrations_dir)
