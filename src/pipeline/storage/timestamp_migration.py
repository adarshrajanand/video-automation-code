"""Migration 0003: rebuild the schema with ``*_timestamp_micro INTEGER``.

The project made a one-way representation decision (GEN-24 / #92): every
persisted timestamp, in SQL columns and in JSON payloads, is an integer count of
microseconds since the Unix epoch in UTC. Column names state the unit, so
``created_at TEXT`` becomes ``created_timestamp_micro INTEGER``.

Why this is not a pure SQL migration
------------------------------------
SQLite can rename a column in place, but it cannot change a column's declared type
or affinity. A rename would leave ``created_timestamp_micro`` as ``TEXT``, whose
affinity silently converts inserted integers back to text. The only way to get
``INTEGER`` columns is to recreate the tables. This module derives the final DDL
from the immutable ``0001_initial.sql``, renames every registered timestamp
column, changes its declared type to ``INTEGER``, and recreates the tables inside
the migration transaction. ``0003_timestamp_micros.sql`` stays a comment-only
version/checksum anchor.

Reading ``0001`` is safe: the runner verifies the recorded checksum before
applying 0003, so the bytes used here are exactly the bytes this database was
created from. The file is never edited.

Reset policy for existing data
------------------------------
This migration refuses to run when any durable table contains rows. The payload
contracts also rename their timestamp keys and bump their ``schema_version``
literals; converting stored payloads would require frozen copies of every old
contract. There is no production data yet, so the documented policy is a manual
development-database reset: stop the pipeline, delete the local SQLite database
file, and rerun ``python -m pipeline db migrate``. The migration never deletes
data itself and never rewrites ``schema_migrations`` by hand.

Applied-migration rows are different: they are migration history, not durable
product data. Their ``applied_at`` column is renamed and converted in place so an
otherwise empty database can still be upgraded.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path

from pipeline.fingerprints import unix_microseconds
from pipeline.storage.errors import MigrationError
from pipeline.storage.timestamp_columns import TIMESTAMP_COLUMNS

_INITIAL_MIGRATION = Path(__file__).resolve().parent / "migrations" / "0001_initial.sql"

_RESET_GUIDANCE = (
    "GEN-24 (#92) renames timestamps to *_timestamp_micro and changes their "
    "representation to integer microseconds. This database contains rows that "
    "cannot be converted automatically because payload contracts also changed. "
    "Development databases must be reset: stop any running pipeline, delete the "
    "local SQLite database file, and rerun 'python -m pipeline db migrate'. "
    "Applied-migration checksums are never rewritten by hand."
)


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _column_exists(connection: sqlite3.Connection, table: str, column: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({_quote(table)})").fetchall()
    return any(str(row[1]) == column for row in rows)


def require_reset_only_database(connection: sqlite3.Connection) -> None:
    """Refuse automatic conversion when durable rows exist.

    ``schema_migrations`` is intentionally excluded: it is migration history and
    every database has rows there. Any other application table means real runtime
    data, which the documented reset policy handles manually.
    """

    tables = connection.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    populated: list[str] = []
    for (table,) in tables:
        name = str(table)
        if name == "schema_migrations":
            continue
        count = connection.execute(f"SELECT COUNT(*) FROM {_quote(name)}").fetchone()
        if count is not None and int(count[0]) > 0:
            populated.append(name)
    if populated:
        raise MigrationError(
            f"{_RESET_GUIDANCE} Populated tables: {', '.join(populated)}."
        )


_SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_timestamp_micro INTEGER NOT NULL
)
"""


def _rename_migration_history_column(connection: sqlite3.Connection) -> None:
    """Rebuild ``schema_migrations`` with the integer timestamp column.

    A plain ``ALTER TABLE ... RENAME COLUMN`` would keep the old ``TEXT``
    affinity, and the timestamp registry requires ``INTEGER``. Rebuilding this
    table inside the migration transaction preserves every applied migration
    row while giving the column the correct declared type.
    """

    if not _table_exists(connection, "schema_migrations"):
        return
    columns = {
        str(row[1]): str(row[2])
        for row in connection.execute(
            f"PRAGMA table_info({_quote('schema_migrations')})"
        ).fetchall()
    }
    if (
        columns.get("applied_timestamp_micro", "").upper() == "INTEGER"
        and "applied_at" not in columns
    ):
        return
    source = (
        "applied_timestamp_micro"
        if "applied_timestamp_micro" in columns
        else "applied_at"
        if "applied_at" in columns
        else None
    )
    if source is None:
        return
    rows = connection.execute(
        f"SELECT version, name, checksum, {source} "
        "FROM schema_migrations ORDER BY version"
    ).fetchall()
    converted = [
        (
            int(version),
            str(name),
            str(checksum),
            value
            if isinstance(value, int)
            else _parse_iso_microseconds(value, table="schema_migrations"),
        )
        for version, name, checksum, value in rows
    ]
    connection.execute(f"DROP TABLE {_quote('schema_migrations')}")
    connection.execute(_SCHEMA_MIGRATIONS_DDL)
    connection.executemany(
        "INSERT INTO schema_migrations "
        "(version, name, checksum, applied_timestamp_micro) VALUES (?, ?, ?, ?)",
        converted,
    )


def _parse_iso_microseconds(value: object, *, table: str) -> int:
    if not isinstance(value, str):
        raise MigrationError(
            f"{table} timestamp must be ISO-8601 text or integer microseconds, "
            f"found {type(value).__name__}"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise MigrationError(f"{table} timestamp is not ISO-8601: {value!r}") from error
    return unix_microseconds(parsed)


def timestamp_micros_schema_sql() -> str:
    """Return ``0001_initial.sql`` rewritten to the integer-microsecond schema.

    Registry entries are authoritative:
    ``legacy_name -> name`` renames every reference, and ``name TEXT`` becomes
    ``name INTEGER``. Index definitions and foreign keys are rewritten by the
    same token pass, so the rebuilt schema stays internally consistent.
    """

    sql = _INITIAL_MIGRATION.read_text(encoding="utf-8")
    renames = {
        _legacy_name(column): column
        for columns in TIMESTAMP_COLUMNS.values()
        for column in columns
    }
    # Longest first so ``lease_expires_at`` cannot be partially matched by a
    # shorter suffix entry.
    for legacy, current in sorted(renames.items(), key=lambda item: -len(item[0])):
        sql = re.sub(rf"\b{re.escape(legacy)}\b", current, sql)
    for current in renames.values():
        sql = re.sub(
            rf"(\b{re.escape(current)}\b\s+)TEXT\b",
            r"\1INTEGER",
            sql,
            flags=re.IGNORECASE,
        )
    return sql


def _created_tables(sql: str) -> list[str]:
    return [
        match.group(1)
        for match in re.finditer(
            r"CREATE\s+TABLE\s+([A-Za-z_][A-Za-z0-9_]*)",
            sql,
            flags=re.IGNORECASE,
        )
    ]


def _execute_script(connection: sqlite3.Connection, script: str) -> None:
    """Execute a SQL script without ``executescript``'s implicit commit."""

    buffer = ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if statement:
                connection.execute(statement)
            buffer = ""
    remainder = buffer.strip()
    if remainder:
        connection.execute(remainder)


def convert_timestamp_columns_to_microseconds(connection: sqlite3.Connection) -> None:
    """Recreate the durable schema with integer microsecond columns.

    The caller owns the transaction. The database must be empty apart from
    migration history; otherwise this raises :class:`MigrationError` with the
    documented reset procedure. Tables are dropped children-first (reverse of
    their declaration order) so foreign keys cannot block the rebuild.
    """

    require_reset_only_database(connection)
    _rename_migration_history_column(connection)

    schema_sql = timestamp_micros_schema_sql()
    created = _created_tables(schema_sql)
    for table in reversed(created):
        connection.execute(f"DROP TABLE IF EXISTS {_quote(table)}")
    _execute_script(connection, schema_sql)


def _legacy_name(column: str) -> str:
    """Return the pre-#92 name for a registered ``*_timestamp_micro`` column."""

    return column.removesuffix("_timestamp_micro") + "_at"


__all__ = [
    "convert_timestamp_columns_to_microseconds",
    "require_reset_only_database",
    "timestamp_micros_schema_sql",
]
