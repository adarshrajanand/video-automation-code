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
    # End-to-end guard: every registered table/column exists with the declared
    # type and nullability, no registered column is generated, and no
    # timestamp-like column is missing from the registry.
    with database.connection() as connection:
        validate_timestamp_columns(connection)


def test_registry_covers_every_timestamp_like_column(database: Database) -> None:
    # `table_xinfo` includes generated columns. This is the completeness check
    # that a new `_at`/`_timestamp_micro` column cannot bypass by being
    # generated. `validate_timestamp_columns` also checks the reverse direction
    # (registered columns that are missing from the schema).
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
            # table_xinfo includes generated columns, which table_info omits.
            for column in connection.execute(f'PRAGMA table_xinfo("{table}")'):
                name = str(column[1])
                if is_timestamp_like_name(name):
                    actual.add((str(table), name))

    assert not (actual - expected), sorted(actual - expected)


@pytest.mark.parametrize(
    ("column", "declared_type"),
    [
        ("archived_at", "TEXT"),
        ("archived_timestamp_micro", "TEXT"),
        ("archived_timestamp_micro", "INTEGER"),
    ],
)
def test_unregistered_timestamp_like_column_fails_validation(
    database: Database,
    column: str,
    declared_type: str,
) -> None:
    # Both reserved suffixes are covered: the legacy `_at` name and the current
    # `_timestamp_micro` name. After #92 an `_at` column is either a missed rename
    # or a new timestamp; both fail. "Unregistered" means the column exists but
    # has no entry in TIMESTAMP_COLUMNS.
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


def test_unregistered_generated_timestamp_column_fails_validation(
    database: Database,
) -> None:
    # Regression for the coverage hole where PRAGMA table_info omitted
    # generated columns and validation silently passed.
    with database.transaction() as connection:
        connection.execute(
            "ALTER TABLE workflow_runs ADD COLUMN archived_timestamp_micro TEXT "
            "GENERATED ALWAYS AS (created_timestamp_micro) VIRTUAL"
        )

    with database.connection() as connection:
        problems = timestamp_column_problems(connection)
        with pytest.raises(
            TimestampSchemaError,
            match=re.escape(
                "unregistered timestamp column workflow_runs.archived_timestamp_micro"
            ),
        ):
            validate_timestamp_columns(connection)

    assert (
        "unregistered timestamp column "
        "workflow_runs.archived_timestamp_micro; add it to "
        "pipeline.storage.timestamp_columns.TIMESTAMP_COLUMNS"
    ) in problems


def test_registered_generated_timestamp_column_is_rejected(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Registration cannot make a generated column writable. The backfill would
    # issue UPDATE and SQLite would refuse, so validation rejects it early.
    #
    # monkeypatch.setitem mutates the imported TIMESTAMP_COLUMNS dict in process
    # memory for this test only; pytest restores the original entry afterwards.
    monkeypatch.setitem(
        TIMESTAMP_COLUMNS,
        "workflow_runs",
        {
            **TIMESTAMP_COLUMNS["workflow_runs"],
            "archived_timestamp_micro": TimestampColumn(
                TimestampFormat.UNIX_MICROSECONDS
            ),
        },
    )
    with database.transaction() as connection:
        connection.execute(
            "ALTER TABLE workflow_runs ADD COLUMN archived_timestamp_micro TEXT "
            "GENERATED ALWAYS AS (created_timestamp_micro) VIRTUAL"
        )

    with database.connection() as connection:
        problems = timestamp_column_problems(connection)

    assert (
        "timestamp column workflow_runs.archived_timestamp_micro is "
        "generated or hidden; generated timestamp columns are not supported "
        "because the backfill cannot write them"
    ) in problems


def test_missing_registered_column_fails_validation(database: Database) -> None:
    # Reverse drift: the registry promises a column that the migrated schema
    # does not have.
    with database.transaction() as connection:
        connection.execute(
            "ALTER TABLE workflow_runs RENAME COLUMN updated_timestamp_micro "
            "TO updated_on"
        )

    with database.connection() as connection:
        problems = timestamp_column_problems(connection)

    assert (
        "registered timestamp column "
        "workflow_runs.updated_timestamp_micro does not exist" in problems
    )


def test_wrong_declared_type_fails_validation() -> None:
    # Type drift: a TEXT column where the registry requires INTEGER microseconds.
    # The old representation cannot silently reappear after #92.
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(
            "CREATE TABLE workflow_runs ("
            "created_timestamp_micro TEXT NOT NULL, "
            "updated_timestamp_micro INTEGER)"
        )
        problems = timestamp_column_problems(connection)
    finally:
        connection.close()

    assert (
        "timestamp column workflow_runs.created_timestamp_micro has "
        "declared type 'TEXT', expected 'INTEGER'"
    ) in problems


def test_wrong_nullability_fails_validation() -> None:
    # Nullability is part of the persisted contract:
    # created_timestamp_micro is NOT NULL, while
    # updated_timestamp_micro/resolved_timestamp_micro etc. may be NULL until the
    # first transition.
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(
            "CREATE TABLE workflow_runs ("
            "created_timestamp_micro INTEGER, "
            "updated_timestamp_micro INTEGER NOT NULL)"
        )
        problems = timestamp_column_problems(connection)
    finally:
        connection.close()

    assert (
        "timestamp column workflow_runs.created_timestamp_micro is nullable, "
        "expected NOT NULL"
    ) in problems
    assert (
        "timestamp column workflow_runs.updated_timestamp_micro is NOT NULL, "
        "expected nullable"
    ) in problems


def test_backfill_ignores_unregistered_timestamp_suffix(database: Database) -> None:
    # Detection and mutation are separate. `note_at` fails validation as
    # unregistered, but the backfill must not guess from its suffix and rewrite
    # the arbitrary text value. This is the regression against the old
    # `name.endswith("_at")` implementation.
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
    # A payload is not a projection. `resolved_values` is an extension object,
    # so its `created_timestamp_micro`/`updated_timestamp_micro` keys are opaque
    # provider data and must not be validated as SQL timestamp columns.
    config = records.effective_config().model_copy(
        update={
            "resolved_values": {
                "created_timestamp_micro": "provider-managed",
                "updated_timestamp_micro": "2026-10-21T12:00:00Z",
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
