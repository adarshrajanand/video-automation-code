"""Explicit registry and validation for SQL timestamp projection columns.

SQLite has no native timestamp type. ``PRAGMA table_info`` reports only the
declared storage class (``TEXT``, ``INTEGER``, ...), not whether a column is a
timestamp, an enum, JSON, or an opaque string. The registry in this module is
therefore the single source of truth for "is this SQL column a timestamp, and
what does it store?".

Payload timestamps are different: they are discovered from Pydantic contract
annotations in :mod:`pipeline.storage.backfill` and are never inferred from
arbitrary JSON keys. This module only covers extracted SQL projection columns.

Adding a timestamp column
-------------------------
1. Add the column in a new migration. Never edit an already-applied migration.
2. Add the table and column here with its format and nullability.
3. Run ``uv run pytest tests/storage/test_timestamp_registry.py``. The test
   fails if the registry and the migrated schema disagree.

Validation treats columns ending in ``_at`` or ``_timestamp_micro`` as
timestamp-like. That suffix check is a test-time completeness guard for new
columns; migration/backfill behavior is driven by this registry, not by the
suffix. A registered column may use any name because the explicit entry is
authoritative. Treat those two suffixes as reserved for timestamps: a
non-timestamp column that happens to end in ``_at`` will fail validation and
should be renamed rather than silently ignored.

Generated columns are enumerated with ``PRAGMA table_xinfo`` so they cannot hide
from validation. A generated timestamp projection is rejected explicitly:
the migration backfill can only rewrite ordinary columns, so registering a
generated timestamp column would leave it silently unnormalized.

Why not ``CHECK`` or ``STRICT``?
--------------------------------
``CHECK`` constraints and ``STRICT`` tables can enforce a storage class, for
example that an integer-microsecond column contains only integers. They cannot
say "this column is a timestamp", and adding either to an existing table
requires a table rebuild. Existing ``TEXT`` timestamp columns therefore use
neither. A new table may combine ``STRICT`` or ``CHECK`` with a registry entry,
but those constraints complement the registry and do not replace it.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from enum import StrEnum

from pipeline.storage.errors import TimestampSchemaError


class TimestampFormat(StrEnum):
    """Physical representation of a persisted timestamp."""

    ISO8601_TEXT = "iso8601_text"
    """Canonical UTC ISO-8601 text with six fractional digits and a ``Z``."""

    UNIX_MICROSECONDS = "unix_microseconds"
    """Signed 64-bit integer microseconds since the Unix epoch, in UTC."""


_DECLARED_TYPES: dict[TimestampFormat, str] = {
    TimestampFormat.ISO8601_TEXT: "TEXT",
    TimestampFormat.UNIX_MICROSECONDS: "INTEGER",
}


@dataclass(frozen=True, slots=True)
class TimestampColumn:
    """One registered timestamp projection column."""

    format: TimestampFormat
    nullable: bool = False

    @property
    def declared_type(self) -> str:
        """The SQLite declared type expected for this representation."""

        return _DECLARED_TYPES[self.format]


def _iso(*, nullable: bool = False) -> TimestampColumn:
    return TimestampColumn(TimestampFormat.ISO8601_TEXT, nullable=nullable)


# Single source of truth for every SQL timestamp column in the migrated schema.
# The nesting is table -> column. Keep entries grouped in schema order so the
# registry is easy to compare with the migration files.
TIMESTAMP_COLUMNS: dict[str, dict[str, TimestampColumn]] = {
    "artifact_invalidation_results": {
        "created_at": _iso(),
    },
    "artifact_pointers": {
        "updated_at": _iso(),
    },
    "artifacts": {
        "created_at": _iso(),
    },
    "budget_reservations": {
        "created_at": _iso(),
        "settled_at": _iso(nullable=True),
    },
    "capability_executions": {
        "started_at": _iso(nullable=True),
        "finished_at": _iso(nullable=True),
    },
    "human_review_decisions": {
        "created_at": _iso(),
    },
    "human_reviews": {
        "created_at": _iso(),
        "resolved_at": _iso(nullable=True),
    },
    "idempotency_records": {
        "created_at": _iso(),
        "completed_at": _iso(nullable=True),
    },
    "inbox_receipts": {
        "processed_at": _iso(nullable=True),
    },
    "input_manifests": {
        "created_at": _iso(),
    },
    "jobs": {
        "available_at": _iso(),
        "lease_expires_at": _iso(nullable=True),
    },
    "leases": {
        "acquired_at": _iso(),
        "expires_at": _iso(),
        "heartbeat_at": _iso(nullable=True),
    },
    "outbox_messages": {
        "available_at": _iso(),
        "claimed_at": _iso(nullable=True),
        "lease_expires_at": _iso(nullable=True),
        "delivered_at": _iso(nullable=True),
    },
    "provider_invocations": {
        "started_at": _iso(),
        "finished_at": _iso(nullable=True),
    },
    "publication_attempts": {
        "started_at": _iso(nullable=True),
        "finished_at": _iso(nullable=True),
    },
    "quality_evaluations": {
        "created_at": _iso(),
    },
    "quality_gate_results": {
        "created_at": _iso(),
        "completed_at": _iso(nullable=True),
    },
    "quality_input_manifests": {
        "created_at": _iso(),
    },
    "recovery_decisions": {
        "created_at": _iso(),
    },
    "repair_plans": {
        "created_at": _iso(),
    },
    "routing_decisions": {
        "created_at": _iso(),
    },
    "schema_migrations": {
        "applied_at": _iso(),
    },
    "stage_attempts": {
        "lease_expires_at": _iso(nullable=True),
        "started_at": _iso(nullable=True),
        "finished_at": _iso(nullable=True),
    },
    "stage_instances": {
        "created_at": _iso(),
        "updated_at": _iso(nullable=True),
    },
    "usage_records": {
        "created_at": _iso(),
    },
    "workflow_events": {
        "created_at": _iso(),
    },
    "workflow_runs": {
        "created_at": _iso(),
        "updated_at": _iso(nullable=True),
    },
}

_TIMESTAMP_LIKE_NAME = re.compile(r"(?:_at|_timestamp_micro)$")


def registered_timestamp_columns(table: str) -> frozenset[str]:
    """Return the registered timestamp-column names for ``table``."""

    return frozenset(TIMESTAMP_COLUMNS.get(table, {}))


def is_timestamp_like_name(column: str) -> bool:
    """Return whether a column name is a timestamp-like registration candidate."""

    return _TIMESTAMP_LIKE_NAME.search(column) is not None


def timestamp_column_problems(connection: sqlite3.Connection) -> tuple[str, ...]:
    """Report every disagreement between the registry and the actual schema."""

    tables = _table_columns(connection)
    problems: list[str] = []

    for table, registered in TIMESTAMP_COLUMNS.items():
        actual_columns = tables.get(table)
        if actual_columns is None:
            problems.append(f"registered timestamp table {table!r} does not exist")
            continue
        for column, expected in registered.items():
            actual = actual_columns.get(column)
            if actual is None:
                problems.append(
                    f"registered timestamp column {table}.{column} does not exist"
                )
                continue
            declared_type, not_null, hidden = actual
            if hidden:
                problems.append(
                    f"timestamp column {table}.{column} is generated or hidden; "
                    "generated timestamp columns are not supported because the "
                    "backfill cannot write them"
                )
                continue
            if declared_type.upper() != expected.declared_type:
                problems.append(
                    f"timestamp column {table}.{column} has declared type "
                    f"{declared_type!r}, expected {expected.declared_type!r}"
                )
            if expected.nullable == not_null:
                nullability = "NOT NULL" if not_null else "nullable"
                expected_nullability = "nullable" if expected.nullable else "NOT NULL"
                problems.append(
                    f"timestamp column {table}.{column} is {nullability}, "
                    f"expected {expected_nullability}"
                )

    for table, actual_columns in tables.items():
        registered = TIMESTAMP_COLUMNS.get(table, {})
        for column in actual_columns:
            if column in registered or not is_timestamp_like_name(column):
                continue
            problems.append(
                f"unregistered timestamp column {table}.{column}; add it to "
                "pipeline.storage.timestamp_columns.TIMESTAMP_COLUMNS"
            )

    return tuple(problems)


def validate_timestamp_columns(connection: sqlite3.Connection) -> None:
    """Raise :class:`TimestampSchemaError` if the registry and schema disagree."""

    problems = timestamp_column_problems(connection)
    if problems:
        bullets = "\n".join(f"- {problem}" for problem in problems)
        raise TimestampSchemaError(
            f"timestamp-column registry does not match the migrated schema:\n{bullets}"
        )


def _table_columns(
    connection: sqlite3.Connection,
) -> dict[str, dict[str, tuple[str, bool, int]]]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    tables: dict[str, dict[str, tuple[str, bool, int]]] = {}
    for (table,) in rows:
        columns: dict[str, tuple[str, bool, int]] = {}
        # table_xinfo, unlike table_info, includes generated columns. They must
        # be visible to validation so they cannot bypass registry coverage.
        for column in connection.execute(
            f"PRAGMA table_xinfo({_quote(str(table))})"
        ).fetchall():
            columns[str(column[1])] = (
                str(column[2]),
                bool(column[3]),
                int(column[6]),
            )
        tables[str(table)] = columns
    return tables


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


__all__ = [
    "TIMESTAMP_COLUMNS",
    "TimestampColumn",
    "TimestampFormat",
    "is_timestamp_like_name",
    "registered_timestamp_columns",
    "timestamp_column_problems",
    "validate_timestamp_columns",
]
