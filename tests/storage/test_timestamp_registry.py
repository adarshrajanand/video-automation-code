from __future__ import annotations

import re
import sqlite3

import pytest

from pipeline.storage import Database, EffectiveConfigRepository
from pipeline.storage.backfill import canonicalize_persisted_timestamps
from pipeline.storage.errors import TimestampSchemaError
from pipeline.storage.timestamp_columns import (
    TIMESTAMP_COLUMNS,
    TimestampColumn,
    TimestampFormat,
    is_timestamp_like_name,
    timestamp_column_problems,
    validate_timestamp_columns,
)


def test_registry_matches_freshly_migrated_schema(database: Database) -> None:
    with database.connection() as connection:
        validate_timestamp_columns(connection)


def test_registry_covers_every_timestamp_like_column(database: Database) -> None:
    expected = {
        (table, column)
        for table, columns in TIMESTAMP_COLUMNS.items()
        for column in columns
    }
    with database.connection() as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()

        actual: set[tuple[str, str]] = set()
        for (table,) in tables:
            for column in connection.execute(f'PRAGMA table_info("{table}")'):
                name = str(column[1])
                if is_timestamp_like_name(name):
                    actual.add((str(table), name))

    assert not (actual - expected), sorted(actual - expected)


@pytest.mark.parametrize(
    ("column", "declared_type"),
    [
        ("archived_at", "TEXT"),
        ("archived_timestamp_micro", "INTEGER"),
    ],
)
def test_unregistered_timestamp_like_column_fails_validation(
    database: Database,
    column: str,
    declared_type: str,
) -> None:
    with database.transaction() as connection:
        connection.execute(
            f'ALTER TABLE workflow_runs ADD COLUMN "{column}" {declared_type}'
        )

    with database.connection() as connection:
        problems = timestamp_column_problems(connection)
        with pytest.raises(
            TimestampSchemaError,
            match=re.escape(f"unregistered timestamp column workflow_runs.{column}"),
        ):
            validate_timestamp_columns(connection)

    assert (
        f"unregistered timestamp column workflow_runs.{column}; add it to "
        "pipeline.storage.timestamp_columns.TIMESTAMP_COLUMNS"
    ) in problems


def test_missing_registered_column_fails_validation(database: Database) -> None:
    with database.transaction() as connection:
        connection.execute(
            "ALTER TABLE workflow_runs RENAME COLUMN updated_at TO updated_on"
        )

    with database.connection() as connection:
        problems = timestamp_column_problems(connection)

    assert (
        "registered timestamp column workflow_runs.updated_at does not exist"
        in problems
    )


def test_wrong_declared_type_fails_validation() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(
            "CREATE TABLE workflow_runs (created_at INTEGER NOT NULL, updated_at TEXT)"
        )
        problems = timestamp_column_problems(connection)
    finally:
        connection.close()

    assert (
        "timestamp column workflow_runs.created_at has declared type 'INTEGER', "
        "expected 'TEXT'"
    ) in problems


def test_wrong_nullability_fails_validation() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(
            "CREATE TABLE workflow_runs (created_at TEXT, updated_at TEXT NOT NULL)"
        )
        problems = timestamp_column_problems(connection)
    finally:
        connection.close()

    assert (
        "timestamp column workflow_runs.created_at is nullable, expected NOT NULL"
    ) in problems
    assert (
        "timestamp column workflow_runs.updated_at is NOT NULL, expected nullable"
    ) in problems


def test_backfill_ignores_unregistered_timestamp_suffix(database: Database) -> None:
    with database.transaction() as connection:
        connection.execute("ALTER TABLE schema_migrations ADD COLUMN note_at TEXT")
        connection.execute("UPDATE schema_migrations SET note_at = 'not-a-timestamp'")

    with database.transaction() as connection:
        canonicalize_persisted_timestamps(connection)

    with database.connection() as connection:
        value = connection.execute(
            "SELECT note_at FROM schema_migrations ORDER BY version LIMIT 1"
        ).fetchone()[0]

    assert value == "not-a-timestamp"


def test_validation_ignores_payload_timestamp_keys(database: Database, records) -> None:
    config = records.effective_config().model_copy(
        update={
            "resolved_values": {
                "created_at": "provider-managed",
                "updated_at": "2026-10-21T12:00:00Z",
            }
        }
    )
    with database.transaction() as connection:
        EffectiveConfigRepository(connection).insert(config)

    with database.connection() as connection:
        validate_timestamp_columns(connection)


def test_registry_can_describe_text_and_integer_microsecond_formats() -> None:
    assert TimestampColumn(TimestampFormat.ISO8601_TEXT).declared_type == "TEXT"
    assert TimestampColumn(TimestampFormat.UNIX_MICROSECONDS).declared_type == "INTEGER"
