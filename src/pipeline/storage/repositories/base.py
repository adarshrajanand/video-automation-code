"""Small typed SQLite repository base shared by the durable record families.

A repository owns no connection lifecycle. Callers pass a configured
:class:`sqlite3.Connection`, usually from :meth:`Database.transaction`, so
multiple repository writes can share one explicit transaction. Every read
revalidates the stored JSON through the canonical Pydantic model.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel

from pipeline.fingerprints import canonical_datetime, canonical_json
from pipeline.storage.errors import ConflictError, IntegrityError, NotFoundError


def translate_integrity_error(
    entity: str,
    error: sqlite3.IntegrityError,
) -> Exception:
    """Translate SQLite constraint text into a typed storage exception."""

    detail = str(error)
    lowered = detail.lower()
    if (
        "unique constraint failed" in lowered
        or "primary key constraint failed" in lowered
    ):
        return ConflictError(entity, detail)
    return IntegrityError(entity, detail)


class SqliteRepository[ModelT: BaseModel]:
    """Insert/get/list/update for a contract-backed table."""

    model: type[ModelT]
    table: str
    key_columns: tuple[str, ...]
    columns: tuple[str, ...] = ()
    order_by: tuple[str, ...] = ()

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    @property
    def entity_name(self) -> str:
        return self.model.__name__

    def _column_value(self, column: str, value: Any) -> Any:
        del column
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, datetime):
            return canonical_datetime(value)
        return value

    def _extracted(self, record: ModelT) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for column in self.columns:
            values[column] = self._column_value(column, getattr(record, column))
        values["schema_version"] = record.schema_version
        return values

    def _row_payload(self, record: ModelT) -> str:
        return canonical_json(record)

    def _key_values(self, record: ModelT) -> tuple[Any, ...]:
        return tuple(getattr(record, column) for column in self.key_columns)

    def _where_key(self) -> str:
        return " AND ".join(f"{column} = ?" for column in self.key_columns)

    def insert(self, record: ModelT) -> ModelT:
        """Insert one record and translate unique/integrity failures."""

        values = self._extracted(record)
        values["payload"] = self._row_payload(record)
        column_names = tuple(values)
        placeholders = ", ".join("?" for _ in column_names)
        sql = (
            f"INSERT INTO {self.table} ({', '.join(column_names)}) "
            f"VALUES ({placeholders})"
        )
        try:
            self.connection.execute(sql, tuple(values[name] for name in column_names))
        except sqlite3.IntegrityError as error:
            raise translate_integrity_error(self.entity_name, error) from error
        return record

    def get(self, *key: Any) -> ModelT:
        """Load one record by its durable key or raise :class:`NotFoundError`."""

        if len(key) != len(self.key_columns):
            raise TypeError(
                f"{self.entity_name}.get expects {len(self.key_columns)} key "
                f"value(s): {', '.join(self.key_columns)}"
            )
        row = self.connection.execute(
            f"SELECT payload FROM {self.table} WHERE {self._where_key()}",
            tuple(key),
        ).fetchone()
        if row is None:
            raise NotFoundError(self.entity_name, key if len(key) > 1 else key[0])
        return self.model.model_validate_json(row[0])

    def get_optional(self, *key: Any) -> ModelT | None:
        """Like :meth:`get`, but return ``None`` when no record exists."""

        try:
            return self.get(*key)
        except NotFoundError:
            return None

    def list(self) -> list[ModelT]:
        """Return every record ordered by the repository's stable key order."""

        order = ", ".join(self.order_by or self.key_columns)
        rows = self.connection.execute(
            f"SELECT payload FROM {self.table} ORDER BY {order}"
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]

    def update(self, record: ModelT) -> ModelT:
        """Replace one record's mutable projection and payload by its key."""

        values = self._extracted(record)
        values["payload"] = self._row_payload(record)
        assignments = ", ".join(f"{name} = ?" for name in values)
        parameters = tuple(values[name] for name in values) + self._key_values(record)
        try:
            cursor = self.connection.execute(
                f"UPDATE {self.table} SET {assignments} WHERE {self._where_key()}",
                parameters,
            )
        except sqlite3.IntegrityError as error:
            raise translate_integrity_error(self.entity_name, error) from error
        if cursor.rowcount == 0:
            raise NotFoundError(self.entity_name, self._key_values(record))
        return record

    def count(self) -> int:
        row = self.connection.execute(f"SELECT COUNT(*) FROM {self.table}").fetchone()
        return int(row[0]) if row is not None else 0


__all__ = ["SqliteRepository", "translate_integrity_error"]
