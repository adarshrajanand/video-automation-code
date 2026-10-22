"""Repositories for idempotency records and budget reservations."""

from __future__ import annotations

from pipeline.contracts.capabilities import BudgetReservation, IdempotencyRecord
from pipeline.contracts.vocabularies import BudgetReservationStatus, IdempotencyStatus
from pipeline.storage.repositories.base import SqliteRepository


class IdempotencyRecordRepository(SqliteRepository[IdempotencyRecord]):
    model = IdempotencyRecord
    table = "idempotency_records"
    key_columns = ("idempotency_key",)
    columns = (
        "idempotency_key",
        "capability",
        "request_fingerprint",
        "provider",
        "status",
        "capability_execution_id",
        "provider_invocation_id",
        "provider_operation_id",
        "created_at",
        "completed_at",
    )
    order_by = ("created_at", "idempotency_key")

    def list_by_status(self, status: IdempotencyStatus) -> list[IdempotencyRecord]:
        rows = self.connection.execute(
            "SELECT payload FROM idempotency_records WHERE status = ? "
            "ORDER BY created_at, idempotency_key",
            (status.value,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]

    def list_for_capability_execution(
        self, capability_execution_id: str
    ) -> list[IdempotencyRecord]:
        rows = self.connection.execute(
            "SELECT payload FROM idempotency_records "
            "WHERE capability_execution_id = ? ORDER BY created_at, idempotency_key",
            (capability_execution_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]


class BudgetReservationRepository(SqliteRepository[BudgetReservation]):
    model = BudgetReservation
    table = "budget_reservations"
    key_columns = ("reservation_id",)
    columns = (
        "reservation_id",
        "scope_type",
        "scope_id",
        "idempotency_key",
        "estimated_cost_minor",
        "reserved_cost_minor",
        "actual_cost_minor",
        "status",
        "created_at",
        "settled_at",
    )
    order_by = ("created_at", "reservation_id")

    def get_by_scope(
        self, idempotency_key: str, scope_type: str, scope_id: str
    ) -> BudgetReservation | None:
        row = self.connection.execute(
            "SELECT payload FROM budget_reservations "
            "WHERE idempotency_key = ? AND scope_type = ? AND scope_id = ?",
            (idempotency_key, scope_type, scope_id),
        ).fetchone()
        if row is None:
            return None
        return self.model.model_validate_json(row[0])

    def list_for_scope(
        self,
        scope_type: str,
        scope_id: str,
        *,
        status: BudgetReservationStatus | None = None,
    ) -> list[BudgetReservation]:
        if status is None:
            rows = self.connection.execute(
                "SELECT payload FROM budget_reservations "
                "WHERE scope_type = ? AND scope_id = ? "
                "ORDER BY created_at, reservation_id",
                (scope_type, scope_id),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT payload FROM budget_reservations "
                "WHERE scope_type = ? AND scope_id = ? AND status = ? "
                "ORDER BY created_at, reservation_id",
                (scope_type, scope_id, status.value),
            ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]


__all__ = ["BudgetReservationRepository", "IdempotencyRecordRepository"]
