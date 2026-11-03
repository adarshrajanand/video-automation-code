"""Idempotent creation of logical stage instances.

A stage instance is one workflow node applied to one logical item. Its durable
identity is derived from the run, the node, and the item key, matching the
contract in ``AI_Video_Pipeline_Workflow_and_Event_Execution.md``. Creating the
same logical item twice returns the existing row instead of inserting a second
one.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import TypeAdapter

from pipeline.contracts.base import NonEmptyStr
from pipeline.contracts.execution import StageInstance, WorkflowRun
from pipeline.contracts.vocabularies import AcceptanceStatus, StageExecutionStatus
from pipeline.contracts.workflow import StageNode
from pipeline.ids import deterministic_id
from pipeline.storage.database import Database
from pipeline.storage.errors import ConflictError
from pipeline.storage.repositories.execution import StageInstanceRepository

_LOGICAL_ITEM_KEY = TypeAdapter(NonEmptyStr)


def _normalize_logical_item_key(value: str) -> str:
    """Apply the same normalization as ``StageInstance.logical_item_key``."""

    return _LOGICAL_ITEM_KEY.validate_python(value)


class StageCreationError(RuntimeError):
    """A stage instance could not be created or re-read safely."""


@dataclass(frozen=True, slots=True)
class StageCreationResult:
    """One logical stage instance and whether this call created it."""

    stage_instance: StageInstance
    created: bool


def derive_stage_instance_id(
    run_id: str,
    node_id: str,
    logical_item_key: str,
) -> str:
    """Return the stable ``stage_`` ID for one logical workflow item.

    The item key is part of the digest because one node may expand to many
    logical items. Omitting it would make every item in a counted or
    manifest-driven node share one ID.

    The key is normalized with the contract's rules first, so padded input and
    its canonical form produce the same ID.
    """

    return deterministic_id(
        "stage", run_id, node_id, _normalize_logical_item_key(logical_item_key)
    )


class StageFactory:
    """Create StageInstance rows idempotently per logical workflow item.

    The ``(run_id, node_id, logical_item_key)`` unique constraint is the final
    authority. A concurrent creator that loses the insert race re-reads the
    winning row instead of raising, so callers can treat creation as an
    upsert-like no-op.

    Creation always owns an immediate transaction. Caller-owned transaction
    composition is not exposed: a deferred caller transaction can upgrade to a
    write lock after another writer commits, producing ``SQLITE_BUSY_SNAPSHOT``
    instead of the documented re-read. The end-to-end creation flow will define
    a safe shared transaction boundary when it needs one.
    """

    def __init__(
        self,
        database: Database,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.database = database
        self._clock = clock or _utc_now

    def create_stage(
        self,
        run: WorkflowRun,
        node: StageNode,
        logical_item_key: str,
        *,
        execution_status: StageExecutionStatus = StageExecutionStatus.READY,
        expected_input_manifest_id: str | None = None,
    ) -> StageCreationResult:
        """Create or return the one stage instance for this logical item."""

        logical_item_key = _normalize_logical_item_key(logical_item_key)
        stage_instance_id = derive_stage_instance_id(
            run.run_id, node.node_id, logical_item_key
        )
        with self.database.transaction(immediate=True) as transaction:
            return self._create(
                transaction,
                run,
                node,
                logical_item_key,
                stage_instance_id,
                execution_status=execution_status,
                expected_input_manifest_id=expected_input_manifest_id,
            )

    def _create(
        self,
        connection: sqlite3.Connection,
        run: WorkflowRun,
        node: StageNode,
        logical_item_key: str,
        stage_instance_id: str,
        *,
        execution_status: StageExecutionStatus,
        expected_input_manifest_id: str | None,
    ) -> StageCreationResult:
        repository = StageInstanceRepository(connection)
        existing = repository.get_by_logical_item(
            run.run_id, node.node_id, logical_item_key
        )
        if existing is not None:
            return StageCreationResult(stage_instance=existing, created=False)

        now = self._clock()
        acceptance_status = (
            AcceptanceStatus.PENDING
            if node.quality_gate_id is not None
            else AcceptanceStatus.NOT_REQUIRED
        )
        stage_instance = StageInstance(
            schema_version="stage-instance.v1",
            stage_instance_id=stage_instance_id,
            run_id=run.run_id,
            node_id=node.node_id,
            logical_item_key=logical_item_key,
            execution_status=execution_status,
            acceptance_status=acceptance_status,
            quality_gate_id=node.quality_gate_id,
            expected_input_manifest_id=expected_input_manifest_id,
            created_at=now,
            updated_at=now,
        )
        try:
            repository.insert(stage_instance)
        except ConflictError:
            # A concurrent creator may have inserted the same logical item
            # after our read. The unique constraint remains authoritative.
            existing = repository.get_by_logical_item(
                run.run_id, node.node_id, logical_item_key
            )
            if existing is None:
                raise StageCreationError(
                    "stage instance insert conflicted but the logical item "
                    f"could not be re-read: {run.run_id!r}, {node.node_id!r}, "
                    f"{logical_item_key!r}"
                ) from None
            return StageCreationResult(stage_instance=existing, created=False)
        return StageCreationResult(stage_instance=stage_instance, created=True)


def _utc_now() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "StageCreationError",
    "StageCreationResult",
    "StageFactory",
    "derive_stage_instance_id",
]
