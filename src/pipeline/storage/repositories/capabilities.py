"""Typed repositories for capability-related tables."""

from __future__ import annotations

from datetime import UTC, datetime

from pipeline.contracts.capabilities import (
    CapabilityExecution,
    UsageRecord,
)
from pipeline.contracts.routing import (
    ProviderInvocation,
    RoutingDecision,
)
from pipeline.fingerprints import canonical_datetime
from pipeline.ids import deterministic_id
from pipeline.storage.repositories.base import SqliteRepository
from pipeline.storage.repositories.control import (
    BudgetReservationRepository,
    IdempotencyRecordRepository,
)


class RoutingDecisionRepository(SqliteRepository[RoutingDecision]):
    """Repository for routing_decisions table."""

    model = RoutingDecision
    table = "routing_decisions"
    key_columns = ("routing_decision_id",)
    columns = (
        "routing_decision_id",
        "capability",
        "implementation",
        "implementation_version",
        "provider",
        "model",
        "policy_version",
        "attempt",
        "data_classification",
        "created_at",
    )
    order_by = ("created_at", "routing_decision_id")


class CapabilityExecutionRepository(SqliteRepository["CapabilityExecution"]):
    """Repository for capability_executions table."""

    model = CapabilityExecution  # type: ignore[assignment]
    table = "capability_executions"
    key_columns = ("capability_execution_id",)
    columns = (
        "capability_execution_id",
        "attempt_id",
        "capability",
        "status",
        "idempotency_key",
        "request_fingerprint",
        "started_at",
        "finished_at",
    )
    order_by = ("attempt_id", "capability_execution_id")

    def list_for_attempt(self, attempt_id: str) -> list[CapabilityExecution]:
        rows = self.connection.execute(
            "SELECT payload FROM capability_executions WHERE attempt_id = ? "
            "ORDER BY started_at, capability_execution_id",
            (attempt_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]

    def get_by_idempotency_key(
        self, idempotency_key: str
    ) -> CapabilityExecution | None:
        row = self.connection.execute(
            "SELECT payload FROM capability_executions WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if row is None:
            return None
        return self.model.model_validate_json(row[0])


class ProviderInvocationRepository(SqliteRepository[ProviderInvocation]):
    """Repository for provider_invocations table."""

    model = ProviderInvocation
    table = "provider_invocations"
    key_columns = ("invocation_id",)
    columns = (
        "invocation_id",
        "capability_execution_id",
        "provider",
        "operation_id",
        "idempotency_key",
        "request_fingerprint",
        "status",
        "started_at",
        "finished_at",
    )
    order_by = ("capability_execution_id", "invocation_id")

    def list_for_execution(
        self, capability_execution_id: str
    ) -> list[ProviderInvocation]:
        rows = self.connection.execute(
            "SELECT payload FROM provider_invocations "
            "WHERE capability_execution_id = ? "
            "ORDER BY started_at, invocation_id",
            (capability_execution_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]


class UsageRecordRepository(SqliteRepository["UsageRecord"]):
    """Repository for usage_records table.

    UsageRecord has no ID field; we generate a deterministic usage_id for the
    durable row and persist the canonical contract JSON plus extracted columns.
    """

    model = UsageRecord  # type: ignore[assignment]
    table = "usage_records"
    key_columns = ("usage_id",)
    columns = (
        "usage_id",
        "capability_execution_id",
        "provider",
        "model",
        "estimated_cost_minor",
        "actual_cost_minor",
        "created_at",
        "schema_version",
        "payload",
    )
    order_by = ("capability_execution_id", "usage_id")

    def insert(self, record: UsageRecord, capability_execution_id: str) -> UsageRecord:
        """Insert a usage record with a generated deterministic usage_id."""
        usage_id = deterministic_id("usage", capability_execution_id, record.provider)
        now = canonical_datetime(datetime.now(UTC))
        placeholders = ", ".join(["?"] * len(self.columns))
        columns_str = ", ".join(self.columns)
        self.connection.execute(
            f"INSERT INTO {self.table} ({columns_str}) VALUES ({placeholders})",
            (
                usage_id,
                capability_execution_id,
                record.provider,
                record.model,
                record.estimated_cost_minor,
                record.actual_cost_minor,
                now,
                record.schema_version,
                record.model_dump_json(),
            ),
        )
        return record

    def get(self, usage_id: str) -> UsageRecord:
        row = self.connection.execute(
            f"SELECT payload FROM {self.table} WHERE usage_id = ?",
            (usage_id,),
        ).fetchone()
        if row is None:
            from pipeline.storage.errors import NotFoundError

            raise NotFoundError(self.entity_name, usage_id)
        return self.model.model_validate_json(row[0])

    def get_optional(self, usage_id: str) -> UsageRecord | None:
        row = self.connection.execute(
            f"SELECT payload FROM {self.table} WHERE usage_id = ?",
            (usage_id,),
        ).fetchone()
        if row is None:
            return None
        return self.model.model_validate_json(row[0])

    def list_for_execution(self, capability_execution_id: str) -> list[UsageRecord]:
        rows = self.connection.execute(
            f"SELECT payload FROM {self.table} "
            "WHERE capability_execution_id = ? "
            "ORDER BY created_at, usage_id",
            (capability_execution_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]


__all__ = [
    "BudgetReservationRepository",
    "CapabilityExecutionRepository",
    "IdempotencyRecordRepository",
    "ProviderInvocationRepository",
    "RoutingDecisionRepository",
    "UsageRecordRepository",
]
