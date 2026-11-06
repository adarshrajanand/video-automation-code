"""Explicit registry and validation for SQL timestamp projection columns.

Terminology
-----------
A **payload** is the JSON document stored in a row's ``payload`` column (or an
equivalent JSON column such as ``effective_configs.resolved_values``). It is the
full serialized Pydantic contract and the source of truth for the record.

A **projection column** is a SQL column that duplicates one payload field for
querying: filtering, ordering, uniqueness, and ``NOT NULL`` enforcement. For
example ``workflow_runs.created_timestamp_micro`` is the SQL projection of the
``WorkflowRun.created_timestamp_micro`` field that also appears in the row's payload. The
write path writes both copies; they can drift if a direct SQL writer or an old
migration touches only one. Backfill and validation exist because of that
duplication.

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
1. Add the column in a new migration. Never edit an already-applied migration:
   the runner stores each file's checksum in ``schema_migrations`` and refuses
   to start if an applied file's bytes change. To revert, restore the applied
   bytes. If a modified file was already applied to a development database,
   recreate that database; do not rewrite ``schema_migrations`` by hand.
2. Add the table and column here with its format and nullability.
3. Run ``uv run pytest tests/storage/test_timestamp_registry.py``. The fixture
   applies every migration to a fresh temporary database, then fails if the
   registry and the migrated schema disagree.

Every current column ends in ``_timestamp_micro`` and stores INTEGER
microseconds. Validation also treats the legacy ``_at`` suffix as timestamp-like:
it is a test-time completeness guard, not a migration rule. No ``_at`` column
should exist in the post-#92 schema, so seeing one means either an unregistered
column or an old-style name that was missed. The suffix check is only a guard;
migration and backfill behavior is driven by this registry, not by the name. A
registered column may use any name because the explicit entry is authoritative.
Registering means adding an explicit entry with format and nullability; it is not
a way to silence the check.

Generated columns are enumerated with ``PRAGMA table_xinfo`` so they cannot hide
from validation. A generated column is a real table column whose value SQLite
computes from other columns: ``VIRTUAL`` is evaluated on read, ``STORED`` on
write, and neither can be written directly. It is not a view. A generated
timestamp projection is rejected explicitly because the migration backfill can
only rewrite ordinary columns; registering one would either fail late with
``cannot UPDATE generated column`` or leave it silently unnormalized. Rejecting
it at validation time makes the failure early and actionable. Derived values
should be computed at read time (query or view) or defined as a generated column
next to their source, never normalized independently.

Why not ``STRICT``?
-------------------
``STRICT`` is a table-level property that restricts stored types. It cannot be
added to an existing table without a rebuild, it still allows lossless
conversions such as ``'12'`` to ``INTEGER``, and it says nothing about timestamp
semantics. It is optional for new tables and is not part of the timestamp work.

Why ``CHECK`` constraints are separate
--------------------------------------
``CHECK`` can enforce a physical invariant, for example that an integer
microsecond column is non-negative. It cannot say "this column is a timestamp",
and changing or removing a ``CHECK`` requires a table rebuild. Business rules
therefore stay in code. Any ``CHECK`` must state its ``NULL`` behavior
explicitly because SQL passes a ``CHECK`` that evaluates to ``NULL``. Physical
``CHECK`` constraints are tracked separately in GEN-26 (#95); they are not part
of this registry.
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


def _micro(*, nullable: bool = False) -> TimestampColumn:
    return TimestampColumn(TimestampFormat.UNIX_MICROSECONDS, nullable=nullable)


# Single source of truth for every SQL timestamp column in the migrated schema.
# The nesting is table -> column. Keep entries grouped in schema order so the
# registry is easy to compare with the migration files.
TIMESTAMP_COLUMNS: dict[str, dict[str, TimestampColumn]] = {
    "artifact_invalidation_results": {
        "created_timestamp_micro": _micro(),
    },
    "artifact_pointers": {
        "updated_timestamp_micro": _micro(),
    },
    "artifacts": {
        "created_timestamp_micro": _micro(),
    },
    "budget_reservations": {
        "created_timestamp_micro": _micro(),
        "settled_timestamp_micro": _micro(nullable=True),
    },
    "capability_executions": {
        "started_timestamp_micro": _micro(nullable=True),
        "finished_timestamp_micro": _micro(nullable=True),
    },
    "human_review_decisions": {
        "created_timestamp_micro": _micro(),
    },
    "human_reviews": {
        "created_timestamp_micro": _micro(),
        "resolved_timestamp_micro": _micro(nullable=True),
    },
    "idempotency_records": {
        "created_timestamp_micro": _micro(),
        "completed_timestamp_micro": _micro(nullable=True),
    },
    "inbox_receipts": {
        "processed_timestamp_micro": _micro(nullable=True),
    },
    "input_manifests": {
        "created_timestamp_micro": _micro(),
    },
    "jobs": {
        "available_timestamp_micro": _micro(),
        "lease_expires_timestamp_micro": _micro(nullable=True),
    },
    "leases": {
        "acquired_timestamp_micro": _micro(),
        "expires_timestamp_micro": _micro(),
        "heartbeat_timestamp_micro": _micro(nullable=True),
    },
    "outbox_messages": {
        "available_timestamp_micro": _micro(),
        "claimed_timestamp_micro": _micro(nullable=True),
        "lease_expires_timestamp_micro": _micro(nullable=True),
        "delivered_timestamp_micro": _micro(nullable=True),
    },
    "provider_invocations": {
        "started_timestamp_micro": _micro(),
        "finished_timestamp_micro": _micro(nullable=True),
    },
    "publication_attempts": {
        "started_timestamp_micro": _micro(nullable=True),
        "finished_timestamp_micro": _micro(nullable=True),
    },
    "quality_evaluations": {
        "created_timestamp_micro": _micro(),
    },
    "quality_gate_results": {
        "created_timestamp_micro": _micro(),
        "completed_timestamp_micro": _micro(nullable=True),
    },
    "quality_input_manifests": {
        "created_timestamp_micro": _micro(),
    },
    "recovery_decisions": {
        "created_timestamp_micro": _micro(),
    },
    "repair_plans": {
        "created_timestamp_micro": _micro(),
    },
    "routing_decisions": {
        "created_timestamp_micro": _micro(),
    },
    "schema_migrations": {
        "applied_timestamp_micro": _micro(),
    },
    "stage_attempts": {
        "lease_expires_timestamp_micro": _micro(nullable=True),
        "started_timestamp_micro": _micro(nullable=True),
        "finished_timestamp_micro": _micro(nullable=True),
    },
    "stage_instances": {
        "created_timestamp_micro": _micro(),
        "updated_timestamp_micro": _micro(nullable=True),
    },
    "usage_records": {
        "created_timestamp_micro": _micro(),
    },
    "workflow_events": {
        "created_timestamp_micro": _micro(),
    },
    "workflow_runs": {
        "created_timestamp_micro": _micro(),
        "updated_timestamp_micro": _micro(nullable=True),
    },
}

# The legacy ``_at`` suffix stays in this guard deliberately. After #92 no
# current column uses it, so an ``_at`` column is either a missed rename or a new
# timestamp that was never registered. Both should fail the schema test.
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
