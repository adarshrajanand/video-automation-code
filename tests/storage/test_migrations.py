from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from pipeline.contracts.config import EffectiveConfig
from pipeline.storage import (
    Database,
    EffectiveConfigRepository,
    IdempotencyRecordRepository,
    MigrationChecksumError,
    MigrationError,
    MigrationRunner,
    OutboxMessageRepository,
    discover_migrations,
)
from pipeline.storage.backfill import canonicalize_persisted_timestamps
from pipeline.storage.migrations import DEFAULT_MIGRATIONS_DIR

HASH_A = "a" * 64


def _copy_migrations(target: Path) -> Path:
    source = Path(__file__).resolve().parents[2] / "src" / "pipeline" / "storage"
    directory = target / "migrations"
    shutil.copytree(source / "migrations", directory)
    return directory


def _legacy_v1_database(target: Path) -> Database:
    migrations_dir = target / "legacy-migrations"
    migrations_dir.mkdir()
    shutil.copy(
        DEFAULT_MIGRATIONS_DIR / "0001_initial.sql",
        migrations_dir / "0001_initial.sql",
    )
    database = Database(target / "state" / "pipeline.sqlite3")
    result = MigrationRunner(database, migrations_dir=migrations_dir).migrate()
    assert result.current_version == 1
    return database


def _legacy_idempotency_payload() -> dict[str, object]:
    return {
        "schema_version": "idempotency-record.v1",
        "idempotency_key": "idem_legacy",
        "capability": "speech_generation",
        "operation_version": "v2",
        "request_fingerprint": HASH_A,
        "input_artifact_ids": ["artifact_in_02", "artifact_in_01"],
        "required_features": ["voice_clone", "ssml"],
        "locale": "en-US",
        "provider": "local_speech_fixture",
        "status": "SUCCEEDED",
        "capability_execution_id": "capexec_legacy",
        "provider_invocation_id": "inv_legacy",
        "provider_operation_id": "op_legacy",
        "result_artifact_ids": ["artifact_out_01"],
        "created_at": "2026-10-21T09:00:00Z",
        "completed_at": "2026-10-21T09:00:01.123456+00:00",
    }


def _insert_legacy_idempotency(database: Database) -> str:
    payload = _legacy_idempotency_payload()
    encoded = json.dumps(payload)
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO idempotency_records "
            "(idempotency_key, capability, request_fingerprint, provider, status, "
            "capability_execution_id, created_at, completed_at, schema_version, "
            "payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                payload["idempotency_key"],
                payload["capability"],
                payload["request_fingerprint"],
                payload["provider"],
                payload["status"],
                payload["capability_execution_id"],
                "2026-10-21T11:00:00+02:00",
                "2026-10-21T09:00:01.123456+00:00",
                payload["schema_version"],
                encoded,
            ),
        )
    return encoded


def test_discovered_migrations_are_ordered_and_checksummed() -> None:
    migrations = discover_migrations()

    assert len(migrations) >= 1
    assert [migration.version for migration in migrations] == sorted(
        migration.version for migration in migrations
    )
    assert all(len(migration.checksum) == 64 for migration in migrations)


def test_migrate_is_idempotent_and_records_checksums(tmp_path: Path) -> None:
    database = Database(tmp_path / "state" / "pipeline.sqlite3")
    runner = MigrationRunner(database)

    before = runner.status()
    assert before.current_version == 0
    assert before.is_up_to_date is False
    assert before.pending

    first = runner.migrate()
    assert first.changed is True
    assert first.current_version == len(runner.migrations)
    assert len(first.applied) == len(runner.migrations)

    second = runner.migrate()
    assert second.changed is False
    assert second.applied == ()
    assert second.current_version == first.current_version

    with database.connection() as connection:
        rows = connection.execute(
            "SELECT version, name, checksum, applied_at FROM schema_migrations "
            "ORDER BY version"
        ).fetchall()
    assert len(rows) == len(runner.migrations)
    for row, migration in zip(rows, runner.migrations, strict=True):
        assert row[0] == migration.version
        assert row[1] == migration.name
        assert row[2] == migration.checksum
        assert row[3].endswith("Z")


def test_initial_schema_contains_every_durable_family(tmp_path: Path) -> None:
    database = Database(tmp_path / "state" / "pipeline.sqlite3")
    MigrationRunner(database).migrate()

    with database.connection() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert {
        "schema_migrations",
        "effective_configs",
        "workflow_runs",
        "stage_instances",
        "stage_attempts",
        "jobs",
        "leases",
        "idempotency_records",
        "budget_reservations",
        "artifacts",
        "artifact_dependencies",
        "artifact_pointers",
        "artifact_invalidation_requests",
        "artifact_invalidation_results",
        "input_manifests",
        "quality_checks",
        "quality_gate_policies",
        "quality_input_manifests",
        "quality_evaluations",
        "quality_gate_results",
        "repair_plans",
        "human_reviews",
        "human_review_decisions",
        "publication_requests",
        "publication_attempts",
        "workflow_events",
        "outbox_messages",
        "inbox_receipts",
        "routing_decisions",
        "capability_executions",
        "provider_invocations",
        "usage_records",
        "recovery_decisions",
        "content_packages",
        "episodes",
        "cuts",
        "sequences",
        "scenes",
        "shots",
        "layer_instances",
        "composition_refs",
    } <= tables


def test_status_reports_pending_without_applying_schema(tmp_path: Path) -> None:
    database = Database(tmp_path / "state" / "pipeline.sqlite3")
    runner = MigrationRunner(database)

    status = runner.status()

    assert status.current_version == 0
    assert status.pending == runner.migrations
    with database.connection() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert "schema_migrations" in tables
    assert "workflow_runs" not in tables


def test_changed_applied_migration_is_refused(tmp_path: Path) -> None:
    migrations_dir = _copy_migrations(tmp_path)
    database = Database(tmp_path / "state" / "pipeline.sqlite3")
    MigrationRunner(database, migrations_dir=migrations_dir).migrate()

    migration_file = migrations_dir / "0001_initial.sql"
    migration_file.write_text(
        migration_file.read_text(encoding="utf-8") + "\n-- changed after apply\n",
        encoding="utf-8",
    )
    runner = MigrationRunner(database, migrations_dir=migrations_dir)

    with pytest.raises(MigrationChecksumError, match="changed after it was applied"):
        runner.status()
    with pytest.raises(MigrationChecksumError):
        runner.migrate()


def test_missing_applied_migration_is_refused(tmp_path: Path) -> None:
    migrations_dir = _copy_migrations(tmp_path)
    database = Database(tmp_path / "state" / "pipeline.sqlite3")
    MigrationRunner(database, migrations_dir=migrations_dir).migrate()

    for migration_file in migrations_dir.glob("*.sql"):
        migration_file.unlink()
    runner = MigrationRunner(database, migrations_dir=migrations_dir)

    with pytest.raises(MigrationError, match="no local file"):
        runner.status()


def test_failed_migration_rolls_back_and_is_not_recorded(tmp_path: Path) -> None:
    migrations_dir = _copy_migrations(tmp_path)
    (migrations_dir / "0003_broken.sql").write_text(
        "CREATE TABLE should_not_survive (id INTEGER PRIMARY KEY);\n"
        "INSERT INTO missing_table (id) VALUES (1);\n",
        encoding="utf-8",
    )
    database = Database(tmp_path / "state" / "pipeline.sqlite3")
    runner = MigrationRunner(database, migrations_dir=migrations_dir)

    with pytest.raises(MigrationError, match="0003_broken failed"):
        runner.migrate()

    status = runner.status()
    assert status.current_version == 2
    assert [migration.version for migration in status.pending] == [3]
    with database.connection() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert "should_not_survive" not in tables


def test_non_contiguous_migrations_are_rejected(tmp_path: Path) -> None:
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "0002_second.sql").write_text(
        "CREATE TABLE second (id INTEGER);\n", encoding="utf-8"
    )

    with pytest.raises(MigrationError, match="contiguous"):
        discover_migrations(migrations_dir)


def test_timestamp_migration_repairs_idempotency_projection(tmp_path: Path) -> None:
    database = _legacy_v1_database(tmp_path)
    original_payload = _insert_legacy_idempotency(database)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE schema_migrations SET applied_at = ? WHERE version = 1",
            ("2026-10-21T09:00:00+00:00",),
        )

    MigrationRunner(database).migrate()

    with database.connection() as connection:
        row = connection.execute(
            "SELECT * FROM idempotency_records WHERE idempotency_key = ?",
            ("idem_legacy",),
        ).fetchone()
        applied_at = connection.execute(
            "SELECT applied_at FROM schema_migrations WHERE version = 1"
        ).fetchone()[0]
        record = IdempotencyRecordRepository(connection).get("idem_legacy")

    assert row is not None
    assert row["operation_version"] == "v2"
    assert json.loads(row["input_artifact_ids"]) == [
        "artifact_in_02",
        "artifact_in_01",
    ]
    assert json.loads(row["required_features"]) == ["voice_clone", "ssml"]
    assert row["locale"] == "en-US"
    assert row["provider_invocation_id"] == "inv_legacy"
    assert row["provider_operation_id"] == "op_legacy"
    assert json.loads(row["result_artifact_ids"]) == ["artifact_out_01"]
    assert row["created_at"] == "2026-10-21T09:00:00.000000Z"
    assert row["completed_at"] == "2026-10-21T09:00:01.123456Z"
    assert applied_at == "2026-10-21T09:00:00.000000Z"

    stored_payload = json.loads(row["payload"])
    assert stored_payload["created_at"] == "2026-10-21T09:00:00.000000Z"
    assert stored_payload["completed_at"] == "2026-10-21T09:00:01.123456Z"
    assert stored_payload["idempotency_key"] == "idem_legacy"
    assert stored_payload["locale"] == "en-US"
    assert record.created_at.isoformat() == "2026-10-21T09:00:00+00:00"
    assert original_payload != row["payload"]


def test_timestamp_migration_repairs_payload_and_projection_together(
    tmp_path: Path,
) -> None:
    database = _legacy_v1_database(tmp_path)
    review_payload = {
        "schema_version": "human-review.v1",
        "review_id": "review_legacy",
        "run_id": "run_legacy",
        "stage_instance_id": None,
        "gate_id": None,
        "target_artifact_ids": ["artifact_01"],
        "target_hashes": {},
        "reason_codes": [],
        "requested_action": "review",
        "status": "OPEN",
        "created_at": "2026-10-21T09:00:00Z",
        "resolved_at": None,
    }
    decision_payload = {
        "schema_version": "human-review-decision.v1",
        "review_id": "review_legacy",
        "decision": "APPROVE",
        "comments": None,
        "reviewer": "alice",
        "target_hashes": {},
        "created_at": "2026-10-21T09:05:00.123456Z",
    }
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO human_reviews "
            "(review_id, run_id, status, requested_action, created_at, "
            "schema_version, payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "review_legacy",
                "run_legacy",
                "OPEN",
                "review",
                "2026-10-21T09:00:00+00:00",
                "human-review.v1",
                json.dumps(review_payload),
            ),
        )
        connection.execute(
            "INSERT INTO human_review_decisions "
            "(review_id, decision, reviewer, created_at, schema_version, payload) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                "review_legacy",
                "APPROVE",
                "alice",
                "2026-10-21T09:05:00.123456+00:00",
                "human-review-decision.v1",
                json.dumps(decision_payload),
            ),
        )

    MigrationRunner(database).migrate()

    with database.connection() as connection:
        review = connection.execute(
            "SELECT created_at, payload FROM human_reviews WHERE review_id = ?",
            ("review_legacy",),
        ).fetchone()
        decision = connection.execute(
            "SELECT created_at, payload FROM human_review_decisions "
            "WHERE review_id = ?",
            ("review_legacy",),
        ).fetchone()

    assert review is not None
    assert decision is not None
    assert review["created_at"] == "2026-10-21T09:00:00.000000Z"
    assert json.loads(review["payload"])["created_at"] == (
        "2026-10-21T09:00:00.000000Z"
    )
    assert decision["created_at"] == "2026-10-21T09:05:00.123456Z"
    assert json.loads(decision["payload"])["created_at"] == (
        "2026-10-21T09:05:00.123456Z"
    )


def test_timestamp_migration_preserves_opaque_configuration_values(
    tmp_path: Path,
) -> None:
    database = _legacy_v1_database(tmp_path)
    resolved_values = {
        "provider_options": {
            "created_at": "provider-managed",
            "updated_at": "2026-10-21T12:00:00Z",
        }
    }
    config = EffectiveConfig(
        schema_version="effective-config.v1",
        effective_config_id="cfg_opaque",
        system_policy_version="1.0",
        domain_profile_id="software_engineering_explainer_v1",
        domain_profile_version="1.0",
        channel_profile_id="channel_explainer_v1",
        channel_profile_version="1.0",
        workflow_id="explainer_validation_v1",
        workflow_version="1.0",
        run_overrides={"schema_version": "run-overrides.v1"},
        resolved_values=resolved_values,
        source_map={"provider_options": "channel_profile:channel_explainer_v1"},
        config_hash=HASH_A,
    )
    with database.transaction() as connection:
        EffectiveConfigRepository(connection).insert(config)
        original_payload = connection.execute(
            "SELECT payload FROM effective_configs WHERE effective_config_id = ?",
            (config.effective_config_id,),
        ).fetchone()[0]

    MigrationRunner(database).migrate()

    with database.connection() as connection:
        row = connection.execute(
            "SELECT config_hash, payload FROM effective_configs "
            "WHERE effective_config_id = ?",
            (config.effective_config_id,),
        ).fetchone()
        stored = EffectiveConfigRepository(connection).get(config.effective_config_id)

    assert row is not None
    assert row["payload"] == original_payload
    assert row["config_hash"] == HASH_A
    assert stored.config_hash == HASH_A
    assert stored.resolved_values == resolved_values


def test_timestamp_migration_normalizes_nested_contract_timestamps(
    tmp_path: Path,
) -> None:
    database = _legacy_v1_database(tmp_path)
    event_payload = {
        "schema_version": "event-envelope.v1",
        "event_id": "event_legacy",
        "event_type": "stage.ready",
        "run_id": "run_legacy",
        "stage_instance_id": "stage_legacy",
        "correlation_id": "corr_legacy",
        "payload_schema_version": "stage-ready.v1",
        "payload": {
            "run_id": "run_legacy",
            "stage_instance_id": "stage_legacy",
            "job_id": "job_legacy",
            "created_at": "provider-managed",
            "updated_at": "2026-10-21T12:00:00Z",
        },
        "created_at": "2026-10-21T09:00:00Z",
    }
    outbox_payload = {
        "schema_version": "outbox-message.v1",
        "outbox_id": "outbox_legacy",
        "event_id": "event_legacy",
        "event": event_payload,
        "status": "PENDING",
        "delivery_attempts": 0,
        "available_at": "2026-10-21T09:00:00Z",
    }
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO workflow_events "
            "(event_id, event_type, correlation_id, payload_schema_version, "
            "created_at, schema_version, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                event_payload["event_id"],
                event_payload["event_type"],
                event_payload["correlation_id"],
                event_payload["payload_schema_version"],
                event_payload["created_at"],
                event_payload["schema_version"],
                json.dumps(event_payload),
            ),
        )
        connection.execute(
            "INSERT INTO outbox_messages "
            "(outbox_id, event_id, status, delivery_attempts, available_at, "
            "schema_version, payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                outbox_payload["outbox_id"],
                outbox_payload["event_id"],
                outbox_payload["status"],
                outbox_payload["delivery_attempts"],
                outbox_payload["available_at"],
                outbox_payload["schema_version"],
                json.dumps(outbox_payload),
            ),
        )

    MigrationRunner(database).migrate()

    with database.connection() as connection:
        event_row = connection.execute(
            "SELECT created_at, payload FROM workflow_events WHERE event_id = ?",
            ("event_legacy",),
        ).fetchone()
        outbox_row = connection.execute(
            "SELECT available_at, payload FROM outbox_messages WHERE outbox_id = ?",
            ("outbox_legacy",),
        ).fetchone()
        message = OutboxMessageRepository(connection).get("outbox_legacy")

    assert event_row is not None
    assert outbox_row is not None
    assert event_row["created_at"] == "2026-10-21T09:00:00.000000Z"
    assert outbox_row["available_at"] == "2026-10-21T09:00:00.000000Z"

    stored_event = json.loads(event_row["payload"])
    assert stored_event["created_at"] == "2026-10-21T09:00:00.000000Z"
    assert stored_event["payload"]["created_at"] == "provider-managed"
    assert stored_event["payload"]["updated_at"] == "2026-10-21T12:00:00Z"

    stored_outbox = json.loads(outbox_row["payload"])
    assert stored_outbox["available_at"] == "2026-10-21T09:00:00.000000Z"
    assert stored_outbox["event"]["created_at"] == ("2026-10-21T09:00:00.000000Z")
    assert stored_outbox["event"]["payload"] == event_payload["payload"]
    assert message.event.created_at.isoformat() == "2026-10-21T09:00:00+00:00"


def test_timestamp_migration_rolls_back_and_retries_after_invalid_payload(
    tmp_path: Path,
) -> None:
    database = _legacy_v1_database(tmp_path)
    original_payload = _insert_legacy_idempotency(database)
    invalid_payload = {
        "schema_version": "human-review.v1",
        "review_id": "review_bad",
        "run_id": "run_legacy",
        "target_artifact_ids": ["artifact_01"],
        "reason_codes": [],
        "requested_action": "review",
        "status": "OPEN",
        "created_at": "2026-10-21T09:00:00",
        "resolved_at": None,
    }
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO human_reviews "
            "(review_id, run_id, status, requested_action, created_at, "
            "schema_version, payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "review_bad",
                "run_legacy",
                "OPEN",
                "review",
                "2026-10-21T09:00:00+00:00",
                "human-review.v1",
                json.dumps(invalid_payload),
            ),
        )
        connection.execute(
            "UPDATE schema_migrations SET applied_at = ? WHERE version = 1",
            ("2026-10-21T09:00:00+00:00",),
        )

    runner = MigrationRunner(database)
    with pytest.raises(MigrationError, match="0002_canonical_timestamps failed"):
        runner.migrate()

    assert runner.status().current_version == 1
    with database.connection() as connection:
        idempotency = connection.execute(
            "SELECT operation_version, input_artifact_ids, required_features, "
            "locale, result_artifact_ids, payload FROM idempotency_records "
            "WHERE idempotency_key = ?",
            ("idem_legacy",),
        ).fetchone()
        review = connection.execute(
            "SELECT created_at, payload FROM human_reviews WHERE review_id = ?",
            ("review_bad",),
        ).fetchone()
        applied_at = connection.execute(
            "SELECT applied_at FROM schema_migrations WHERE version = 1"
        ).fetchone()[0]

    assert idempotency is not None
    assert idempotency["operation_version"] == "v1"
    assert idempotency["input_artifact_ids"] == "[]"
    assert idempotency["required_features"] == "[]"
    assert idempotency["locale"] is None
    assert idempotency["result_artifact_ids"] == "[]"
    assert idempotency["payload"] == original_payload
    assert review is not None
    assert review["created_at"] == "2026-10-21T09:00:00+00:00"
    assert json.loads(review["payload"])["created_at"] == "2026-10-21T09:00:00"
    assert applied_at == "2026-10-21T09:00:00+00:00"

    with database.transaction() as connection:
        connection.execute(
            "UPDATE human_reviews SET payload = ? WHERE review_id = ?",
            (
                json.dumps(
                    {
                        **invalid_payload,
                        "created_at": "2026-10-21T09:00:00Z",
                    }
                ),
                "review_bad",
            ),
        )

    retry = runner.migrate()
    assert retry.current_version == 2
    with database.connection() as connection:
        review = connection.execute(
            "SELECT created_at FROM human_reviews WHERE review_id = ?",
            ("review_bad",),
        ).fetchone()
    assert review is not None
    assert review["created_at"] == "2026-10-21T09:00:00.000000Z"


def test_timestamp_migration_rejects_mismatched_idempotency_key(
    tmp_path: Path,
) -> None:
    database = _legacy_v1_database(tmp_path)
    original_payload = _insert_legacy_idempotency(database)
    mismatched = json.loads(original_payload)
    mismatched["idempotency_key"] = "idem_other"
    with database.transaction() as connection:
        connection.execute(
            "UPDATE idempotency_records SET payload = ? "
            "WHERE idempotency_key = 'idem_legacy'",
            (json.dumps(mismatched),),
        )

    runner = MigrationRunner(database)
    with pytest.raises(MigrationError, match="payload key"):
        runner.migrate()

    assert runner.status().current_version == 1
    with database.connection() as connection:
        row = connection.execute(
            "SELECT payload FROM idempotency_records WHERE idempotency_key = ?",
            ("idem_legacy",),
        ).fetchone()
    assert row is not None
    assert row["payload"] == json.dumps(mismatched)


def test_timestamp_backfill_is_idempotent(tmp_path: Path) -> None:
    database = _legacy_v1_database(tmp_path)
    _insert_legacy_idempotency(database)
    MigrationRunner(database).migrate()

    with database.connection() as connection:
        before = tuple(
            connection.execute(
                "SELECT * FROM idempotency_records WHERE idempotency_key = ?",
                ("idem_legacy",),
            ).fetchone()
        )

    with database.transaction() as connection:
        canonicalize_persisted_timestamps(connection)
        canonicalize_persisted_timestamps(connection)

    with database.connection() as connection:
        after = tuple(
            connection.execute(
                "SELECT * FROM idempotency_records WHERE idempotency_key = ?",
                ("idem_legacy",),
            ).fetchone()
        )

    assert after == before
