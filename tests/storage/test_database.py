from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.storage import (
    ConflictError,
    Database,
    EffectiveConfigRepository,
    IntegrityError,
    MigrationRunner,
    WorkflowRunRepository,
)
from pipeline.storage.repositories import StageInstanceRepository


def test_connection_pragmas_and_wal(database: Database) -> None:
    with database.connection() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5_000

    assert database.journal_mode() == "wal"


def test_commit_and_rollback_boundaries(database: Database, records) -> None:
    config = records.effective_config()

    with database.transaction() as connection:
        EffectiveConfigRepository(connection).insert(config)

    with database.connection() as connection:
        assert EffectiveConfigRepository(connection).count() == 1

    with (
        pytest.raises(RuntimeError, match="abort"),
        database.transaction() as connection,
    ):
        second = records.effective_config("02")
        EffectiveConfigRepository(connection).insert(second)
        raise RuntimeError("abort")

    with database.connection() as connection:
        assert EffectiveConfigRepository(connection).count() == 1


def test_conflict_rolls_back_prior_writes(database: Database, records) -> None:
    config = records.effective_config()

    with pytest.raises(ConflictError), database.transaction() as connection:
        repository = EffectiveConfigRepository(connection)
        repository.insert(config)
        repository.insert(config)

    with database.connection() as connection:
        assert EffectiveConfigRepository(connection).count() == 0


def test_foreign_key_violation_is_translated_and_rolled_back(
    database: Database, records
) -> None:
    missing_config = records.effective_config("missing")
    run = records.run(missing_config)

    with (
        pytest.raises(IntegrityError, match="FOREIGN KEY"),
        database.transaction() as connection,
    ):
        WorkflowRunRepository(connection).insert(run)

    with database.connection() as connection:
        assert WorkflowRunRepository(connection).count() == 0


def test_caller_can_compose_repositories_in_one_transaction(
    database: Database, records
) -> None:
    config = records.effective_config()
    run = records.run(config)
    stage = records.stage_instance(run)

    with database.transaction() as connection:
        EffectiveConfigRepository(connection).insert(config)
        WorkflowRunRepository(connection).insert(run)
        StageInstanceRepository(connection).insert(stage)

    with database.connection() as connection:
        assert WorkflowRunRepository(connection).get(run.run_id) == run
        assert StageInstanceRepository(connection).get(stage.stage_instance_id) == stage


def test_deferred_transaction_configuration(tmp_path: Path, records) -> None:
    database = Database(
        tmp_path / "state" / "pipeline.sqlite3",
        busy_timeout_ms=1_250,
        immediate_transactions=False,
    )
    MigrationRunner(database).migrate()
    config = records.effective_config()

    with database.transaction() as connection:
        EffectiveConfigRepository(connection).insert(config)

    with database.connection() as connection:
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 1_250
        assert EffectiveConfigRepository(connection).get(
            config.effective_config_id
        ) == (config)


def test_invalid_busy_timeout_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="busy_timeout_ms"):
        Database(tmp_path / "db.sqlite3", busy_timeout_ms=0)
