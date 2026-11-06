from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import Enum

from pipeline.contracts.capabilities import IdempotencyRecord
from pipeline.fingerprints import canonical_json, unix_microseconds
from pipeline.storage import Database, IdempotencyRecordRepository


def _projection_row(
    database: Database, idempotency_key: str
) -> tuple[list[str], object]:
    with database.connection() as connection:
        columns = [
            str(row[1])
            for row in connection.execute("PRAGMA table_info(idempotency_records)")
        ]
        row = connection.execute(
            "SELECT * FROM idempotency_records WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
    assert row is not None
    return columns, row


def _assert_projection_matches(record: IdempotencyRecord, columns, row) -> None:
    assert set(columns) - {"payload"} == set(IdempotencyRecord.model_fields)
    for column in columns:
        if column == "payload":
            continue
        expected = getattr(record, column)
        actual = row[column]
        if isinstance(expected, list):
            assert json.loads(actual) == expected
        elif isinstance(expected, Enum):
            assert actual == expected.value
        elif isinstance(expected, datetime):
            assert actual == unix_microseconds(expected)
        else:
            assert actual == expected


def _changed_record(records, suffix: str) -> IdempotencyRecord:
    return records.idempotency_record(suffix).model_copy(
        update={
            "operation_version": "v2",
            "input_artifact_ids": ["artifact_in_02", "artifact_in_01"],
            "required_features": ["voice_clone", "ssml"],
            "locale": "en-US",
            "provider_invocation_id": f"inv_{suffix}",
            "provider_operation_id": f"op_{suffix}",
            "result_artifact_ids": [f"artifact_out_{suffix}"],
            "created_timestamp_micro": datetime(2026, 10, 21, 9, 0, 0, 123456, tzinfo=UTC),
            "completed_timestamp_micro": datetime(2026, 10, 21, 9, 0, 1, 654321, tzinfo=UTC),
        }
    )


def test_idempotency_insert_projects_every_ddl_column(database, records) -> None:
    record = _changed_record(records, "01")

    with database.transaction() as connection:
        IdempotencyRecordRepository(connection).insert(record)

    columns, row = _projection_row(database, record.idempotency_key)
    _assert_projection_matches(record, columns, row)
    assert row["created_timestamp_micro"] == 1_792_573_200_123_456
    assert row["completed_timestamp_micro"] == 1_792_573_201_654_321
    with database.connection() as connection:
        assert (
            IdempotencyRecordRepository(connection).get(record.idempotency_key)
            == record
        )


def test_idempotency_update_reprojects_every_ddl_column(database, records) -> None:
    record = _changed_record(records, "01")
    updated = record.model_copy(
        update={
            "operation_version": "v3",
            "input_artifact_ids": [],
            "required_features": ["translated"],
            "locale": "fr-CA",
            "result_artifact_ids": ["artifact_out_child"],
            "completed_timestamp_micro": datetime(2026, 10, 21, 9, 0, 2, tzinfo=UTC),
        }
    )

    with database.transaction() as connection:
        repository = IdempotencyRecordRepository(connection)
        repository.insert(record)
        repository.update(updated)

    columns, row = _projection_row(database, record.idempotency_key)
    _assert_projection_matches(updated, columns, row)
    with database.connection() as connection:
        assert (
            IdempotencyRecordRepository(connection).get(record.idempotency_key)
            == updated
        )


def test_idempotency_restored_columns_support_sql_filters(database, records) -> None:
    # Checking that projection columns exist is not enough. This proves their
    # values are usable by real SQL filters, including JSON-encoded list
    # columns, which is the user-visible purpose of a projection.
    populated = _changed_record(records, "01")
    empty = records.idempotency_record("02").model_copy(
        update={"operation_version": "v1", "locale": "fr-FR"}
    )
    with database.transaction() as connection:
        repository = IdempotencyRecordRepository(connection)
        repository.insert(populated)
        repository.insert(empty)

    filters = {
        "operation_version": populated.operation_version,
        "input_artifact_ids": canonical_json(populated.input_artifact_ids),
        "required_features": canonical_json(populated.required_features),
        "locale": populated.locale,
        "result_artifact_ids": canonical_json(populated.result_artifact_ids),
    }
    with database.connection() as connection:
        for column, value in filters.items():
            rows = connection.execute(
                f"SELECT idempotency_key FROM idempotency_records WHERE {column} = ?",
                (value,),
            ).fetchall()
            assert [row[0] for row in rows] == [populated.idempotency_key]

        empty_rows = connection.execute(
            "SELECT idempotency_key FROM idempotency_records "
            "WHERE input_artifact_ids = '[]' AND required_features = '[]' "
            "AND result_artifact_ids = '[]'"
        ).fetchall()
        assert [row[0] for row in empty_rows] == [empty.idempotency_key]
