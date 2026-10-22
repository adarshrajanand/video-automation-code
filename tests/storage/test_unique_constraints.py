from __future__ import annotations

import sqlite3

import pytest

from pipeline.storage import (
    ArtifactDependencyRepository,
    ArtifactPointerRepository,
    ArtifactRepository,
    BudgetReservationRepository,
    ConflictError,
    EffectiveConfigRepository,
    IdempotencyRecordRepository,
    JobRepository,
    LeaseRepository,
    StageAttemptRepository,
    StageInstanceRepository,
    WorkflowRunRepository,
)


def _insert_graph_prefix(database, records):
    config = records.effective_config()
    run = records.run(config)
    stage = records.stage_instance(run)
    attempt = records.stage_attempt(stage)
    with database.transaction() as connection:
        EffectiveConfigRepository(connection).insert(config)
        WorkflowRunRepository(connection).insert(run)
        StageInstanceRepository(connection).insert(stage)
        StageAttemptRepository(connection).insert(attempt)
    return config, run, stage, attempt


def _event(connection: sqlite3.Connection, event_id: str) -> None:
    connection.execute(
        "INSERT INTO workflow_events "
        "(event_id, event_type, correlation_id, payload_schema_version, "
        "created_at, schema_version, payload) "
        "VALUES (?, 'RUN_READY', 'corr_01', 'run-ready.v1', ?, "
        "'event-envelope.v1', '{}')",
        (event_id, "2026-10-21T09:00:00Z"),
    )


def test_effective_config_primary_key_conflicts(database, records) -> None:
    config = records.effective_config()

    with database.transaction() as connection:
        repository = EffectiveConfigRepository(connection)
        repository.insert(config)
        with pytest.raises(ConflictError):
            repository.insert(config)


def test_workflow_run_key_is_unique(database, records) -> None:
    config, run, _, _ = _insert_graph_prefix(database, records)
    duplicate = records.run(config, "02", run_key=run.run_key)

    with pytest.raises(ConflictError), database.transaction() as connection:
        WorkflowRunRepository(connection).insert(duplicate)


def test_stage_instance_logical_item_is_unique(database, records) -> None:
    _, run, stage, _ = _insert_graph_prefix(database, records)
    duplicate = records.stage_instance(run, "02", node_id=stage.node_id)

    with pytest.raises(ConflictError), database.transaction() as connection:
        StageInstanceRepository(connection).insert(duplicate)


def test_stage_attempt_number_is_unique_per_stage(database, records) -> None:
    _, _, stage, _ = _insert_graph_prefix(database, records)
    duplicate = records.stage_attempt(stage, "02", attempt_number=1)

    with pytest.raises(ConflictError), database.transaction() as connection:
        StageAttemptRepository(connection).insert(duplicate)


def test_job_idempotency_key_is_unique(database, records) -> None:
    _, _, _, attempt = _insert_graph_prefix(database, records)
    job = records.job(attempt, "01")
    with database.transaction() as connection:
        JobRepository(connection).insert(job)
    duplicate = records.job(attempt, "02", idempotency_key=job.idempotency_key)

    with pytest.raises(ConflictError), database.transaction() as connection:
        JobRepository(connection).insert(duplicate)


def test_lease_term_is_unique_per_job(database, records) -> None:
    _, _, _, attempt = _insert_graph_prefix(database, records)
    job = records.job(attempt)
    lease = records.lease(job, fencing_token=3)
    with database.transaction() as connection:
        JobRepository(connection).insert(job)
        LeaseRepository(connection).insert(lease)

    with pytest.raises(ConflictError), database.transaction() as connection:
        LeaseRepository(connection).insert(lease)


def test_idempotency_key_is_unique(database, records) -> None:
    record = records.idempotency_record()
    with database.transaction() as connection:
        IdempotencyRecordRepository(connection).insert(record)

    with pytest.raises(ConflictError), database.transaction() as connection:
        IdempotencyRecordRepository(connection).insert(record)


def test_budget_reservation_identity_and_scoped_key_are_unique(
    database, records
) -> None:
    reservation = records.budget_reservation()
    with database.transaction() as connection:
        BudgetReservationRepository(connection).insert(reservation)

    with pytest.raises(ConflictError), database.transaction() as connection:
        BudgetReservationRepository(connection).insert(reservation)

    duplicate_scope = records.budget_reservation("02")
    duplicate_scope.reservation_id = "reservation_other"
    duplicate_scope.idempotency_key = reservation.idempotency_key
    duplicate_scope.scope_type = reservation.scope_type
    duplicate_scope.scope_id = reservation.scope_id
    with pytest.raises(ConflictError), database.transaction() as connection:
        BudgetReservationRepository(connection).insert(duplicate_scope)


def test_artifact_identity_and_slot_version_are_unique(database, records) -> None:
    _, run, _, attempt = _insert_graph_prefix(database, records)
    artifact = records.artifact(run, attempt, "01", logical_slot="script")
    with database.transaction() as connection:
        ArtifactRepository(connection).insert(artifact)

    with pytest.raises(ConflictError), database.transaction() as connection:
        ArtifactRepository(connection).insert(artifact)

    duplicate_slot = records.artifact(
        run, attempt, "02", logical_slot="script", content=b"other"
    )
    with pytest.raises(ConflictError), database.transaction() as connection:
        ArtifactRepository(connection).insert(duplicate_slot)


def test_artifact_dependency_pair_is_unique(database, records) -> None:
    _, run, _, attempt = _insert_graph_prefix(database, records)
    parent = records.artifact(run, attempt, "parent", logical_slot="script")
    child = records.artifact(run, attempt, "child", logical_slot="speech")
    dependency = records.dependency(parent, child)
    with database.transaction() as connection:
        ArtifactRepository(connection).insert(parent)
        ArtifactRepository(connection).insert(child)
        ArtifactDependencyRepository(connection).insert(dependency)

    duplicate = records.dependency(parent, child, dependency_type="derived")
    with pytest.raises(ConflictError), database.transaction() as connection:
        ArtifactDependencyRepository(connection).insert(duplicate)


def test_only_one_active_pointer_per_slot_and_type(database, records) -> None:
    _, run, _, attempt = _insert_graph_prefix(database, records)
    artifact = records.artifact(run, attempt, "01", logical_slot="script")
    pointer = records.pointer(run, artifact, "01")
    with database.transaction() as connection:
        ArtifactRepository(connection).insert(artifact)
        ArtifactPointerRepository(connection).insert(pointer)

    duplicate = records.pointer(run, artifact, "02")
    with pytest.raises(ConflictError), database.transaction() as connection:
        ArtifactPointerRepository(connection).insert(duplicate)

    history = records.pointer(run, artifact, "03", active=False)
    with database.transaction() as connection:
        ArtifactPointerRepository(connection).insert(history)


def test_quality_evaluation_and_gate_result_ids_are_unique(database) -> None:
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO quality_evaluations "
            "(evaluation_id, gate_id, check_id, outcome, created_at, "
            "schema_version, payload) VALUES "
            "('eval_01', 'gate_01', 'check_01', 'PASS', ?, "
            "'quality-evaluation.v1', '{}')",
            ("2026-10-21T09:00:00Z",),
        )
        connection.execute(
            "INSERT INTO quality_gate_results "
            "(quality_gate_result_id, gate_id, gate_version, decision, "
            "policy_version, created_at, schema_version, payload) VALUES "
            "('gate_result_01', 'gate_01', '1.0', 'PASS', '1.0', ?, "
            "'quality-gate-result.v1', '{}')",
            ("2026-10-21T09:00:00Z",),
        )

    with (
        pytest.raises(sqlite3.IntegrityError),
        database.transaction() as connection,
    ):
        connection.execute(
            "INSERT INTO quality_evaluations "
            "(evaluation_id, gate_id, check_id, outcome, created_at, "
            "schema_version, payload) VALUES "
            "('eval_01', 'gate_01', 'check_02', 'FAIL', ?, "
            "'quality-evaluation.v1', '{}')",
            ("2026-10-21T09:00:00Z",),
        )

    with (
        pytest.raises(sqlite3.IntegrityError),
        database.transaction() as connection,
    ):
        connection.execute(
            "INSERT INTO quality_gate_results "
            "(quality_gate_result_id, gate_id, gate_version, decision, "
            "policy_version, created_at, schema_version, payload) VALUES "
            "('gate_result_01', 'gate_02', '1.0', 'PASS', '1.0', ?, "
            "'quality-gate-result.v1', '{}')",
            ("2026-10-21T09:00:00Z",),
        )


def test_outbox_event_and_inbox_consumer_receipts_are_unique(database) -> None:
    with database.transaction() as connection:
        _event(connection, "event_01")
        _event(connection, "event_02")
        connection.execute(
            "INSERT INTO outbox_messages "
            "(outbox_id, event_id, status, delivery_attempts, available_at, "
            "schema_version, payload) VALUES "
            "('outbox_01', 'event_01', 'PENDING', 0, ?, "
            "'outbox-message.v1', '{}')",
            ("2026-10-21T09:00:00Z",),
        )
        connection.execute(
            "INSERT INTO inbox_receipts "
            "(consumer_id, event_id, status, schema_version, payload) VALUES "
            "('consumer_01', 'event_01', 'PROCESSED', 'inbox-receipt.v1', '{}')",
        )

    with (
        pytest.raises(sqlite3.IntegrityError),
        database.transaction() as connection,
    ):
        connection.execute(
            "INSERT INTO outbox_messages "
            "(outbox_id, event_id, status, delivery_attempts, available_at, "
            "schema_version, payload) VALUES "
            "('outbox_02', 'event_01', 'PENDING', 0, ?, "
            "'outbox-message.v1', '{}')",
            ("2026-10-21T09:00:00Z",),
        )

    with (
        pytest.raises(sqlite3.IntegrityError),
        database.transaction() as connection,
    ):
        connection.execute(
            "INSERT INTO inbox_receipts "
            "(consumer_id, event_id, status, schema_version, payload) VALUES "
            "('consumer_01', 'event_01', 'FAILED', 'inbox-receipt.v1', '{}')",
        )

    # A second consumer can record the same event independently.
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO inbox_receipts "
            "(consumer_id, event_id, status, schema_version, payload) VALUES "
            "('consumer_02', 'event_01', 'PROCESSED', 'inbox-receipt.v1', '{}')",
        )


def test_raw_sqlite_constraint_is_visible_to_callers(database) -> None:
    with (
        pytest.raises(sqlite3.IntegrityError),
        database.transaction() as connection,
    ):
        connection.execute(
            "INSERT INTO workflow_runs "
            "(run_id, run_key, workflow_id, workflow_version, "
            "effective_config_id, effective_config_hash, status, "
            "content_package_id, created_at, schema_version, payload) "
            "VALUES ('run_x', 'key_x', 'wf', '1', 'missing', ?, 'RUNNING', "
            "'pkg', ?, 'workflow-run.v1', '{}')",
            ("0" * 64, "2026-10-21T09:00:00Z"),
        )
