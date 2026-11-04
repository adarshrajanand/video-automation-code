"""Transactional data repairs for durable records.

Most migrations are plain SQL. Repairs that must parse JSON payloads or
timezone-aware datetimes run as Python hooks inside the migration transaction.
Every hook is idempotent and fails closed on malformed durable data so a failed
migration rolls back instead of leaving payload and projection disagreement.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from pipeline.contracts.capabilities import IdempotencyRecord
from pipeline.fingerprints import canonical_datetime, canonical_json
from pipeline.storage.errors import MigrationError, StorageError

_CANONICAL_TIMESTAMP_FIELDS = frozenset(
    {
        "acquired_at",
        "assembled_at",
        "available_at",
        "claimed_at",
        "completed_at",
        "created_at",
        "delivered_at",
        "expires_at",
        "extracted_at",
        "finished_at",
        "heartbeat_at",
        "lease_expires_at",
        "processed_at",
        "published_at",
        "render_finished_at",
        "render_started_at",
        "resolved_at",
        "retrieved_at",
        "settled_at",
        "started_at",
        "updated_at",
    }
)


def canonicalize_persisted_timestamps(connection: sqlite3.Connection) -> None:
    """Repair durable projections and normalize every persisted timestamp.

    Idempotency projections are rebuilt from their validated payloads first.
    Every table with a JSON payload or an extracted timestamp column is then
    normalized in place. The caller owns the transaction; any error must roll
    back the whole migration.
    """

    _reproject_idempotency_records(connection)
    for table in _user_tables(connection):
        _normalize_table(connection, table)


def _reproject_idempotency_records(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "idempotency_records"):
        return

    rows = connection.execute(
        'SELECT idempotency_key, payload FROM "idempotency_records"'
    ).fetchall()
    if not rows:
        return

    # Imported lazily so the migration runner can import this module without
    # creating a package import cycle.
    from pipeline.storage.repositories.control import IdempotencyRecordRepository

    repository = IdempotencyRecordRepository(connection)
    for key, payload in rows:
        try:
            record = IdempotencyRecord.model_validate_json(payload)
        except ValidationError as error:
            raise MigrationError(
                f"idempotency_records row {key!r} has an invalid payload: {error}"
            ) from error
        if record.idempotency_key != key:
            raise MigrationError(
                f"idempotency_records row {key!r} payload key is "
                f"{record.idempotency_key!r}"
            )
        try:
            repository.update(record)
        except StorageError as error:
            raise MigrationError(
                f"idempotency_records row {key!r} could not be reprojected: {error}"
            ) from error


def _normalize_table(connection: sqlite3.Connection, table: str) -> None:
    columns = _columns(connection, table)
    timestamp_columns = [name for name, _ in columns if name.endswith("_at")]
    has_payload = any(name == "payload" for name, _ in columns)
    if not has_payload and not timestamp_columns:
        return

    key_columns = [name for name, position in columns if position > 0]
    if not key_columns:
        raise MigrationError(f"cannot normalize {table}: table has no primary key")

    selected = list(
        dict.fromkeys(
            [*key_columns, *timestamp_columns, *(["payload"] if has_payload else [])]
        )
    )
    rows = connection.execute(
        f"SELECT {', '.join(_quote(name) for name in selected)} FROM {_quote(table)}"
    ).fetchall()
    for row in rows:
        values = {name: row[index] for index, name in enumerate(selected)}
        key = _row_key(key_columns, values)

        payload: dict[str, Any] | None = None
        canonical_payload: str | None = None
        if has_payload:
            payload = _parse_payload(values["payload"], table=table, key=key)
            payload = _normalize_payload(payload, table=table, key=key)
            canonical_payload = canonical_json(payload)

        updates: dict[str, Any] = {}
        if canonical_payload is not None and canonical_payload != values["payload"]:
            updates["payload"] = canonical_payload
        for column in timestamp_columns:
            if payload is not None and column in payload:
                normalized = payload[column]
            else:
                normalized = _normalize_timestamp(
                    values[column],
                    table=table,
                    column=column,
                    key=key,
                )
            if normalized != values[column]:
                updates[column] = normalized

        if not updates:
            continue
        assignments = ", ".join(f"{_quote(name)} = ?" for name in updates)
        where = " AND ".join(f"{_quote(name)} = ?" for name in key_columns)
        parameters = [
            *updates.values(),
            *(values[name] for name in key_columns),
        ]
        connection.execute(
            f"UPDATE {_quote(table)} SET {assignments} WHERE {where}",
            parameters,
        )


def _normalize_payload(
    value: Any,
    *,
    table: str,
    key: object,
) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for name, item in value.items():
            if name in _CANONICAL_TIMESTAMP_FIELDS:
                normalized[name] = _normalize_timestamp(
                    item,
                    table=table,
                    column=name,
                    key=key,
                )
            else:
                normalized[name] = _normalize_payload(item, table=table, key=key)
        return normalized
    if isinstance(value, list):
        return [_normalize_payload(item, table=table, key=key) for item in value]
    return value


def _normalize_timestamp(
    value: Any,
    *,
    table: str,
    column: str,
    key: object,
) -> Any:
    if value is None:
        return None
    if not isinstance(value, str):
        raise MigrationError(
            f"{table} row {key!r} column {column!r} must be a timestamp string "
            f"or null, found {type(value).__name__}"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise MigrationError(
            f"{table} row {key!r} column {column!r} is not an ISO-8601 "
            f"timestamp: {value!r}"
        ) from error
    try:
        return canonical_datetime(parsed)
    except ValueError as error:
        raise MigrationError(
            f"{table} row {key!r} column {column!r} must include a timezone "
            f"offset: {value!r}"
        ) from error


def _parse_payload(text: str, *, table: str, key: object) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except (TypeError, json.JSONDecodeError) as error:
        raise MigrationError(
            f"{table} row {key!r} has invalid JSON payload: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise MigrationError(f"{table} row {key!r} payload must be a JSON object")
    return payload


def _user_tables(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [str(row[0]) for row in rows]


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _columns(connection: sqlite3.Connection, table: str) -> list[tuple[str, int]]:
    rows = connection.execute(f"PRAGMA table_info({_quote(table)})").fetchall()
    return [(str(row[1]), int(row[5])) for row in rows]


def _row_key(key_columns: list[str], values: dict[str, Any]) -> object:
    key = tuple(values[name] for name in key_columns)
    return key[0] if len(key) == 1 else key


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


__all__ = ["canonicalize_persisted_timestamps"]
