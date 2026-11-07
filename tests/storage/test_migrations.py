from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pipeline.contracts.config import EffectiveConfig
from pipeline.fingerprints import unix_microseconds
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
    """Create a pre-#92 database by applying only ``0001_initial.sql``.

    The reset policy, not automatic conversion, governs databases like this. The
    helper exists to prove that ``migrate()`` refuses them with guidance.
    """

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


def _current_database(target: Path) -> Database:
    """Create a database at the current schema (all shipped migrations applied)."""

    database = Database(target / "state" / "pipeline.sqlite3")
    result = MigrationRunner(database).migrate()
    assert result.current_version == len(MigrationRunner(database).migrations)
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


def _idempotency_payload() -> dict[str, object]:
    return {
        "schema_version": "idempotency-record.v2",
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
        "created_timestamp_micro": unix_microseconds(
            datetime(2026, 10, 21, 9, 0, 0, tzinfo=UTC)
        ),
        "completed_timestamp_micro": unix_microseconds(
            datetime(2026, 10, 21, 9, 0, 1, 123456, tzinfo=UTC)
        ),
    }


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
            "SELECT version, name, checksum, applied_timestamp_micro "
            "FROM schema_migrations ORDER BY version"
        ).fetchall()
    assert len(rows) == len(runner.migrations)
    for row, migration in zip(rows, runner.migrations, strict=True):
        assert row[0] == migration.version
        assert row[1] == migration.name
        assert row[2] == migration.checksum
        # The applied timestamp is persisted as integer microseconds, not text.
        assert isinstance(row[3], int)
        assert row[3] > 0


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
    (migrations_dir / "0004_broken.sql").write_text(
        "CREATE TABLE should_not_survive (id INTEGER PRIMARY KEY);\n"
        "INSERT INTO missing_table (id) VALUES (1);\n",
        encoding="utf-8",
    )
    database = Database(tmp_path / "state" / "pipeline.sqlite3")
    runner = MigrationRunner(database, migrations_dir=migrations_dir)

    with pytest.raises(MigrationError, match="0004_broken failed"):
        runner.migrate()

    status = runner.status()
    assert status.current_version == 3
    assert [migration.version for migration in status.pending] == [4]
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


def test_populated_legacy_database_is_refused_before_partial_rewrites(
    tmp_path: Path,
) -> None:
    # The reset policy is a preflight, not a late guard: migration 0002 must not
    # rewrite a version-1 database that migration 0003 will reject anyway.
    database = _legacy_v1_database(tmp_path)
    encoded = _insert_legacy_idempotency(database)
    runner = MigrationRunner(database)

    with pytest.raises(MigrationError, match="must be reset"):
        runner.migrate()

    assert runner.status().current_version == 1
    with database.connection() as connection:
        row = connection.execute(
            "SELECT payload FROM idempotency_records WHERE idempotency_key = ?",
            ("idem_legacy",),
        ).fetchone()
    assert row is not None
    assert row["payload"] == encoded


def test_empty_legacy_database_upgrades_to_integer_schema(tmp_path: Path) -> None:
    database = _legacy_v1_database(tmp_path)

    result = MigrationRunner(database).migrate()

    assert result.current_version == 3
    with database.connection() as connection:
        columns = {
            row[1]: str(row[2]).upper()
            for row in connection.execute(
                "PRAGMA table_info(idempotency_records)"
            ).fetchall()
        }
        history = connection.execute(
            "SELECT applied_timestamp_micro FROM schema_migrations ORDER BY version"
        ).fetchall()
    assert columns["created_timestamp_micro"] == "INTEGER"
    assert columns["completed_timestamp_micro"] == "INTEGER"
    assert "created_at" not in columns
    assert all(isinstance(row[0], int) for row in history)


def test_backfill_rebuilds_idempotency_projection_from_payload(
    tmp_path: Path,
) -> None:
    # A projection is the set of SQL columns extracted from a validated payload.
    # This exercises the targeted repair for the #9 defect: rebuild every
    # idempotency projection column from the payload, not only the timestamps.
    database = _current_database(tmp_path)
    payload = _idempotency_payload()
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO idempotency_records "
            "(idempotency_key, capability, operation_version, request_fingerprint, "
            "input_artifact_ids, required_features, locale, provider, status, "
            "capability_execution_id, result_artifact_ids, created_timestamp_micro, "
            "completed_timestamp_micro, schema_version, payload) "
            "VALUES (?, ?, ?, ?, '[]', '[]', NULL, ?, ?, ?, '[]', 0, 0, ?, ?)",
            (
                payload["idempotency_key"],
                payload["capability"],
                "v1",
                payload["request_fingerprint"],
                payload["provider"],
                payload["status"],
                payload["capability_execution_id"],
                payload["schema_version"],
                json.dumps(payload),
            ),
        )
        canonicalize_persisted_timestamps(connection)

    with database.connection() as connection:
        row = connection.execute(
            "SELECT * FROM idempotency_records WHERE idempotency_key = ?",
            ("idem_legacy",),
        ).fetchone()
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
    assert row["created_timestamp_micro"] == payload["created_timestamp_micro"]
    assert row["completed_timestamp_micro"] == payload["completed_timestamp_micro"]
    assert isinstance(row["created_timestamp_micro"], int)

    stored_payload = json.loads(row["payload"])
    assert (
        stored_payload["created_timestamp_micro"]
        == (payload["created_timestamp_micro"])
    )
    assert (
        stored_payload["completed_timestamp_micro"]
        == (payload["completed_timestamp_micro"])
    )
    assert record.created_timestamp_micro.isoformat() == "2026-10-21T09:00:00+00:00"


def test_backfill_normalizes_payload_and_projection_together(
    tmp_path: Path,
) -> None:
    # Generic path: a declared payload timestamp and its SQL projection must be
    # normalized to the same integer value in one transaction. This is separate
    # from the idempotency projection rebuild so failures localize.
    database = _current_database(tmp_path)
    review_payload = {
        "schema_version": "human-review.v2",
        "review_id": "review_legacy",
        "run_id": "run_legacy",
        "target_artifact_ids": ["artifact_01"],
        "reason_codes": [],
        "requested_action": "review",
        "status": "OPEN",
        "created_timestamp_micro": "2026-10-21T09:00:00Z",
        "resolved_timestamp_micro": None,
    }
    decision_payload = {
        "schema_version": "human-review-decision.v2",
        "review_id": "review_legacy",
        "decision": "APPROVE",
        "comments": None,
        "reviewer": "alice",
        "target_hashes": {},
        "created_timestamp_micro": "2026-10-21T09:05:00.123456Z",
    }
    expected_review = unix_microseconds(datetime(2026, 10, 21, 9, 0, 0, tzinfo=UTC))
    expected_decision = unix_microseconds(
        datetime(2026, 10, 21, 9, 5, 0, 123456, tzinfo=UTC)
    )
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO human_reviews "
            "(review_id, run_id, status, requested_action, created_timestamp_micro, "
            "resolved_timestamp_micro, schema_version, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "review_legacy",
                "run_legacy",
                "OPEN",
                "review",
                0,
                None,
                "human-review.v2",
                json.dumps(review_payload),
            ),
        )
        connection.execute(
            "INSERT INTO human_review_decisions "
            "(review_id, decision, reviewer, created_timestamp_micro, "
            "schema_version, payload) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "review_legacy",
                "APPROVE",
                "alice",
                0,
                "human-review-decision.v2",
                json.dumps(decision_payload),
            ),
        )
        canonicalize_persisted_timestamps(connection)

    with database.connection() as connection:
        review = connection.execute(
            "SELECT created_timestamp_micro, payload FROM human_reviews "
            "WHERE review_id = ?",
            ("review_legacy",),
        ).fetchone()
        decision = connection.execute(
            "SELECT created_timestamp_micro, payload FROM human_review_decisions "
            "WHERE review_id = ?",
            ("review_legacy",),
        ).fetchone()

    assert review is not None
    assert decision is not None
    assert review["created_timestamp_micro"] == expected_review
    assert json.loads(review["payload"])["created_timestamp_micro"] == expected_review
    assert decision["created_timestamp_micro"] == expected_decision
    assert (
        json.loads(decision["payload"])["created_timestamp_micro"] == expected_decision
    )


def test_backfill_preserves_opaque_configuration_values(tmp_path: Path) -> None:
    database = _current_database(tmp_path)
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
        canonicalize_persisted_timestamps(connection)

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


def test_backfill_normalizes_nested_contract_timestamps(tmp_path: Path) -> None:
    # Recursion is schema-directed, not a generic JSON walk:
    #   outbox payload -> OutboxMessage.event -> EventEnvelope.created_timestamp_micro
    # is a declared timestamp and is normalized. `event.payload` is
    # ExtensionObject, so its `created_at`/`updated_at` keys stay untouched.
    database = _current_database(tmp_path)
    expected = unix_microseconds(datetime(2026, 10, 21, 9, 0, 0, tzinfo=UTC))
    event_payload = {
        "schema_version": "event-envelope.v2",
        "event_id": "event_legacy",
        "event_type": "workflow.started",
        "run_id": "run_legacy",
        "stage_instance_id": "stage_legacy",
        "correlation_id": "corr_legacy",
        "payload_schema_version": "workflow-started.v1",
        "payload": {
            "run_id": "run_legacy",
            "stage_instance_id": "stage_legacy",
            "job_id": "job_legacy",
            "created_at": "provider-managed",
            "updated_at": "2026-10-21T12:00:00Z",
        },
        "created_timestamp_micro": "2026-10-21T09:00:00Z",
    }
    outbox_payload = {
        "schema_version": "outbox-message.v2",
        "outbox_id": "outbox_legacy",
        "event_id": "event_legacy",
        "event": event_payload,
        "status": "PENDING",
        "delivery_attempts": 0,
        "available_timestamp_micro": "2026-10-21T09:00:00Z",
    }
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO workflow_events "
            "(event_id, event_type, correlation_id, payload_schema_version, "
            "run_id, created_timestamp_micro, schema_version, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_payload["event_id"],
                event_payload["event_type"],
                event_payload["correlation_id"],
                event_payload["payload_schema_version"],
                event_payload["run_id"],
                0,
                event_payload["schema_version"],
                json.dumps(event_payload),
            ),
        )
        connection.execute(
            "INSERT INTO outbox_messages "
            "(outbox_id, event_id, status, delivery_attempts, "
            "available_timestamp_micro, schema_version, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                outbox_payload["outbox_id"],
                outbox_payload["event_id"],
                outbox_payload["status"],
                outbox_payload["delivery_attempts"],
                0,
                outbox_payload["schema_version"],
                json.dumps(outbox_payload),
            ),
        )
        canonicalize_persisted_timestamps(connection)

    with database.connection() as connection:
        event_row = connection.execute(
            "SELECT created_timestamp_micro, payload FROM workflow_events "
            "WHERE event_id = ?",
            ("event_legacy",),
        ).fetchone()
        outbox_row = connection.execute(
            "SELECT available_timestamp_micro, payload FROM outbox_messages "
            "WHERE outbox_id = ?",
            ("outbox_legacy",),
        ).fetchone()
        message = OutboxMessageRepository(connection).get("outbox_legacy")

    assert event_row is not None
    assert outbox_row is not None
    assert event_row["created_timestamp_micro"] == expected
    assert outbox_row["available_timestamp_micro"] == expected

    stored_event = json.loads(event_row["payload"])
    assert stored_event["created_timestamp_micro"] == expected
    assert stored_event["payload"]["created_at"] == "provider-managed"
    assert stored_event["payload"]["updated_at"] == "2026-10-21T12:00:00Z"

    stored_outbox = json.loads(outbox_row["payload"])
    assert stored_outbox["available_timestamp_micro"] == expected
    assert stored_outbox["event"]["created_timestamp_micro"] == expected
    assert stored_outbox["event"]["payload"] == event_payload["payload"]
    assert message.event.created_timestamp_micro.isoformat() == (
        "2026-10-21T09:00:00+00:00"
    )


def test_backfill_rolls_back_on_invalid_timestamp(tmp_path: Path) -> None:
    database = _current_database(tmp_path)
    invalid_payload = {
        "schema_version": "human-review.v2",
        "review_id": "review_bad",
        "run_id": "run_legacy",
        "target_artifact_ids": ["artifact_01"],
        "reason_codes": [],
        "requested_action": "review",
        "status": "OPEN",
        "created_timestamp_micro": "2026-10-21T09:00:00",
    }
    with (
        pytest.raises(MigrationError, match="timezone"),
        database.transaction() as connection,
    ):
        connection.execute(
            "INSERT INTO human_reviews "
            "(review_id, run_id, status, requested_action, "
            "created_timestamp_micro, schema_version, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "review_bad",
                "run_legacy",
                "OPEN",
                "review",
                0,
                "human-review.v2",
                json.dumps(invalid_payload),
            ),
        )
        canonicalize_persisted_timestamps(connection)

    with database.connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM human_reviews WHERE review_id = ?",
            ("review_bad",),
        ).fetchone()[0]
    assert count == 0


def test_backfill_rejects_mismatched_idempotency_key(tmp_path: Path) -> None:
    database = _current_database(tmp_path)
    payload = _idempotency_payload()
    mismatched = {**payload, "idempotency_key": "idem_other"}
    encoded = json.dumps(mismatched)
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO idempotency_records "
            "(idempotency_key, capability, request_fingerprint, status, "
            "capability_execution_id, created_timestamp_micro, schema_version, "
            "payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "idem_legacy",
                payload["capability"],
                payload["request_fingerprint"],
                payload["status"],
                payload["capability_execution_id"],
                payload["created_timestamp_micro"],
                payload["schema_version"],
                encoded,
            ),
        )

    with (
        pytest.raises(MigrationError, match="payload key"),
        database.transaction() as connection,
    ):
        canonicalize_persisted_timestamps(connection)

    with database.connection() as connection:
        row = connection.execute(
            "SELECT payload FROM idempotency_records WHERE idempotency_key = ?",
            ("idem_legacy",),
        ).fetchone()
    assert row is not None
    assert row["payload"] == encoded


def test_backfill_is_idempotent(tmp_path: Path) -> None:
    database = _current_database(tmp_path)
    payload = _idempotency_payload()
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO idempotency_records "
            "(idempotency_key, capability, request_fingerprint, status, "
            "capability_execution_id, created_timestamp_micro, schema_version, "
            "payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                payload["idempotency_key"],
                payload["capability"],
                payload["request_fingerprint"],
                payload["status"],
                payload["capability_execution_id"],
                payload["created_timestamp_micro"],
                payload["schema_version"],
                json.dumps(payload),
            ),
        )

    with database.transaction() as connection:
        canonicalize_persisted_timestamps(connection)

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
