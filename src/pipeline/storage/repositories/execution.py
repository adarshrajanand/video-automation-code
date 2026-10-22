"""Repositories for effective config, runs, stages, attempts, jobs, and leases."""

from __future__ import annotations

from pipeline.contracts.config import EffectiveConfig
from pipeline.contracts.execution import StageAttempt, StageInstance, WorkflowRun
from pipeline.contracts.jobs import Job, Lease
from pipeline.contracts.vocabularies import JobStatus, RunStatus
from pipeline.storage.errors import NotFoundError
from pipeline.storage.repositories.base import SqliteRepository


class EffectiveConfigRepository(SqliteRepository[EffectiveConfig]):
    model = EffectiveConfig
    table = "effective_configs"
    key_columns = ("effective_config_id",)
    columns = (
        "effective_config_id",
        "config_hash",
        "workflow_id",
        "workflow_version",
        "system_policy_version",
        "domain_profile_id",
        "domain_profile_version",
        "channel_profile_id",
        "channel_profile_version",
        "snapshot_artifact_id",
    )
    order_by = ("effective_config_id",)

    def list_by_config_hash(self, config_hash: str) -> list[EffectiveConfig]:
        rows = self.connection.execute(
            "SELECT payload FROM effective_configs WHERE config_hash = ? "
            "ORDER BY effective_config_id",
            (config_hash,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]


class WorkflowRunRepository(SqliteRepository[WorkflowRun]):
    model = WorkflowRun
    table = "workflow_runs"
    key_columns = ("run_id",)
    columns = (
        "run_id",
        "run_key",
        "workflow_id",
        "workflow_version",
        "effective_config_id",
        "effective_config_hash",
        "status",
        "content_package_id",
        "created_at",
        "updated_at",
    )
    order_by = ("created_at", "run_id")

    def get_by_run_key(self, run_key: str) -> WorkflowRun:
        row = self.connection.execute(
            "SELECT payload FROM workflow_runs WHERE run_key = ?", (run_key,)
        ).fetchone()
        if row is None:
            raise NotFoundError(self.entity_name, run_key)
        return self.model.model_validate_json(row[0])

    def list_by_status(self, status: RunStatus) -> list[WorkflowRun]:
        rows = self.connection.execute(
            "SELECT payload FROM workflow_runs WHERE status = ? "
            "ORDER BY created_at, run_id",
            (status.value,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]


class StageInstanceRepository(SqliteRepository[StageInstance]):
    model = StageInstance
    table = "stage_instances"
    key_columns = ("stage_instance_id",)
    columns = (
        "stage_instance_id",
        "run_id",
        "node_id",
        "logical_item_key",
        "execution_status",
        "acceptance_status",
        "quality_gate_id",
        "quality_gate_result_id",
        "expected_input_manifest_id",
        "active_attempt_id",
        "created_at",
        "updated_at",
    )
    order_by = ("run_id", "created_at", "stage_instance_id")

    def list_for_run(self, run_id: str) -> list[StageInstance]:
        rows = self.connection.execute(
            "SELECT payload FROM stage_instances WHERE run_id = ? "
            "ORDER BY created_at, stage_instance_id",
            (run_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]

    def get_by_logical_item(
        self, run_id: str, node_id: str, logical_item_key: str
    ) -> StageInstance | None:
        row = self.connection.execute(
            "SELECT payload FROM stage_instances "
            "WHERE run_id = ? AND node_id = ? AND logical_item_key = ?",
            (run_id, node_id, logical_item_key),
        ).fetchone()
        if row is None:
            return None
        return self.model.model_validate_json(row[0])


class StageAttemptRepository(SqliteRepository[StageAttempt]):
    model = StageAttempt
    table = "stage_attempts"
    key_columns = ("attempt_id",)
    columns = (
        "attempt_id",
        "stage_instance_id",
        "attempt_number",
        "quality_regeneration_number",
        "status",
        "worker_id",
        "lease_expires_at",
        "started_at",
        "finished_at",
        "failure_code",
    )
    order_by = ("stage_instance_id", "attempt_number", "attempt_id")

    def list_for_stage_instance(self, stage_instance_id: str) -> list[StageAttempt]:
        rows = self.connection.execute(
            "SELECT payload FROM stage_attempts WHERE stage_instance_id = ? "
            "ORDER BY attempt_number, attempt_id",
            (stage_instance_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]


class JobRepository(SqliteRepository[Job]):
    model = Job
    table = "jobs"
    key_columns = ("job_id",)
    columns = (
        "job_id",
        "attempt_id",
        "queue_name",
        "status",
        "idempotency_key",
        "available_at",
        "claimed_by",
        "lease_expires_at",
        "delivery_count",
    )
    order_by = ("available_at", "job_id")

    def get_by_idempotency_key(self, idempotency_key: str) -> Job:
        row = self.connection.execute(
            "SELECT payload FROM jobs WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if row is None:
            raise NotFoundError(self.entity_name, idempotency_key)
        return self.model.model_validate_json(row[0])

    def list_by_status(self, status: JobStatus) -> list[Job]:
        rows = self.connection.execute(
            "SELECT payload FROM jobs WHERE status = ? ORDER BY available_at, job_id",
            (status.value,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]


class LeaseRepository(SqliteRepository[Lease]):
    model = Lease
    table = "leases"
    key_columns = ("job_id", "fencing_token")
    columns = (
        "job_id",
        "owner_id",
        "fencing_token",
        "acquired_at",
        "expires_at",
        "heartbeat_at",
    )
    order_by = ("job_id", "fencing_token")

    def list_for_job(self, job_id: str) -> list[Lease]:
        rows = self.connection.execute(
            "SELECT payload FROM leases WHERE job_id = ? "
            "ORDER BY acquired_at, fencing_token",
            (job_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]

    def latest_for_job(self, job_id: str) -> Lease | None:
        """Return the highest fencing term recorded for a job, without claiming."""

        row = self.connection.execute(
            "SELECT payload FROM leases WHERE job_id = ? "
            "ORDER BY fencing_token DESC LIMIT 1",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        return self.model.model_validate_json(row[0])


__all__ = [
    "EffectiveConfigRepository",
    "JobRepository",
    "LeaseRepository",
    "StageAttemptRepository",
    "StageInstanceRepository",
    "WorkflowRunRepository",
]
