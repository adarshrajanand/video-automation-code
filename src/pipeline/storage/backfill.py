"""Transactional data repairs for durable records.

Most migrations are plain SQL. Repairs that must parse JSON payloads or
timezone-aware datetimes run as Python hooks inside the migration transaction.
Every hook is idempotent and fails closed on malformed durable data so a failed
migration rolls back instead of leaving payload and projection disagreement.

SQL timestamp columns are identified by the explicit registry in
:mod:`pipeline.storage.timestamp_columns`, not by a name suffix. Payload
timestamps remain schema-directed through Pydantic annotations.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from functools import lru_cache
from types import UnionType
from typing import Annotated, Any, Union, get_args, get_origin

from pydantic import BaseModel, ValidationError

from pipeline.contracts.base import Contract
from pipeline.contracts.capabilities import IdempotencyRecord
from pipeline.contracts.registry import CONTRACT_MODELS, contract_schema_version
from pipeline.fingerprints import canonical_datetime, canonical_json
from pipeline.storage.errors import MigrationError, StorageError
from pipeline.storage.timestamp_columns import registered_timestamp_columns


@lru_cache(maxsize=1)
def _contracts_by_schema_version() -> dict[str, type[Contract]]:
    return {contract_schema_version(model): model for model in CONTRACT_MODELS}


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
    registered = registered_timestamp_columns(table)
    timestamp_columns = [name for name, _ in columns if name in registered]
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
        payload_timestamps: frozenset[str] = frozenset()
        if has_payload:
            payload = _parse_payload(values["payload"], table=table, key=key)
            payload, payload_changed, payload_timestamps = _normalize_payload(
                payload,
                table=table,
                key=key,
            )
            if payload_changed:
                canonical_payload = canonical_json(payload)

        updates: dict[str, Any] = {}
        if canonical_payload is not None and canonical_payload != values["payload"]:
            updates["payload"] = canonical_payload
        for column in timestamp_columns:
            if payload is not None and column in payload_timestamps:
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
    value: dict[str, Any],
    *,
    table: str,
    key: object,
) -> tuple[dict[str, Any], bool, frozenset[str]]:
    """Normalize only timestamps declared by the payload's contract model.

    Payloads are opaque when no registered contract claims their
    ``schema_version``. Declared extension fields and identifier-keyed maps are
    never traversed, so provider metadata and configuration values keep their
    original representation.
    """

    schema_version = value.get("schema_version")
    if not isinstance(schema_version, str):
        return value, False, frozenset()
    model = _contracts_by_schema_version().get(schema_version)
    if model is None:
        return value, False, frozenset()

    timestamps = frozenset(
        name
        for name, field in model.model_fields.items()
        if name in value and _unwrap_annotation(field.annotation) is datetime
    )
    normalized, changed = _normalize_nested_model(
        value,
        model,
        table=table,
        key=key,
    )
    return normalized, changed, timestamps


def _normalize_field_value(
    value: Any,
    annotation: Any,
    *,
    table: str,
    key: object,
) -> tuple[Any, bool]:
    if value is None:
        return value, False

    model = _contract_model(annotation)
    if model is not None:
        return _normalize_nested_model(value, model, table=table, key=key)

    item_model = _sequence_item_model(annotation)
    if item_model is not None and isinstance(value, list):
        normalized: list[Any] = []
        changed = False
        for item in value:
            nested, nested_changed = _normalize_nested_model(
                item,
                item_model,
                table=table,
                key=key,
            )
            normalized.append(nested)
            changed = changed or nested_changed
        return (normalized if changed else value), changed

    return value, False


def _normalize_nested_model(
    value: Any,
    model: type[BaseModel],
    *,
    table: str,
    key: object,
) -> tuple[Any, bool]:
    if not isinstance(value, dict):
        return value, False

    normalized = dict(value)
    changed = False
    for name, field in model.model_fields.items():
        if name not in value:
            continue
        annotation = _unwrap_annotation(field.annotation)
        if annotation is datetime:
            timestamp = _normalize_timestamp(
                value[name],
                table=table,
                column=name,
                key=key,
            )
            if timestamp != value[name]:
                normalized[name] = timestamp
                changed = True
            continue

        nested, nested_changed = _normalize_field_value(
            value[name],
            annotation,
            table=table,
            key=key,
        )
        if nested_changed:
            normalized[name] = nested
            changed = True

    return (normalized if changed else value), changed


def _unwrap_annotation(annotation: Any) -> Any:
    while True:
        origin = get_origin(annotation)
        if origin is Annotated:
            annotation = get_args(annotation)[0]
            continue
        if origin in (Union, UnionType):
            arguments = tuple(
                argument
                for argument in get_args(annotation)
                if argument is not type(None)
            )
            if len(arguments) == 1:
                annotation = arguments[0]
                continue
        return annotation


def _contract_model(annotation: Any) -> type[BaseModel] | None:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


def _sequence_item_model(annotation: Any) -> type[BaseModel] | None:
    origin = get_origin(annotation)
    if origin not in (list, tuple, set, frozenset):
        return None
    arguments = get_args(annotation)
    if origin is tuple:
        if len(arguments) != 2 or arguments[1] is not Ellipsis:
            return None
        arguments = arguments[:1]
    if not arguments:
        return None
    return _contract_model(_unwrap_annotation(arguments[0]))


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
