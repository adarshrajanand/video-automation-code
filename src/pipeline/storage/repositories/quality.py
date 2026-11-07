"""Quality-related repositories for durable storage."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipeline.contracts.quality import (
    QualityEvaluation,
    QualityGateResult,
    QualityInputManifest,
    RepairPlan,
)
from pipeline.storage.repositories.base import SqliteRepository

if TYPE_CHECKING:
    pass


class QualityEvaluationRepository(SqliteRepository[QualityEvaluation]):
    model = QualityEvaluation
    table = "quality_evaluations"
    key_columns = ("evaluation_id",)
    columns = (
        "evaluation_id",
        "stage_instance_id",
        "logical_item_key",
        "scene_id",
        "shot_id",
        "gate_id",
        "check_id",
        "outcome",
        "created_timestamp_micro",
    )
    order_by = ("created_timestamp_micro", "evaluation_id")

    def list_for_stage_instance(
        self, stage_instance_id: str
    ) -> list[QualityEvaluation]:
        """List evaluations for a stage instance."""
        rows = self.connection.execute(
            "SELECT payload FROM quality_evaluations "
            "WHERE stage_instance_id = ? "
            "ORDER BY created_timestamp_micro, evaluation_id",
            (stage_instance_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]

    def list_for_gate(
        self, gate_id: str, stage_instance_id: str | None = None
    ) -> list[QualityEvaluation]:
        """List evaluations for a gate, optionally filtered by stage instance."""
        if stage_instance_id:
            rows = self.connection.execute(
                "SELECT payload FROM quality_evaluations "
                "WHERE gate_id = ? AND stage_instance_id = ? "
                "ORDER BY created_timestamp_micro, evaluation_id",
                (gate_id, stage_instance_id),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT payload FROM quality_evaluations "
                "WHERE gate_id = ? ORDER BY created_timestamp_micro, evaluation_id",
                (gate_id,),
            ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]

    def list_for_run(self, run_id: str) -> list[QualityEvaluation]:
        """List evaluations for a workflow run (joins via stage_instances)."""
        rows = self.connection.execute(
            "SELECT qe.payload FROM quality_evaluations qe "
            "JOIN stage_instances si ON qe.stage_instance_id = si.stage_instance_id "
            "WHERE si.run_id = ? ORDER BY qe.created_timestamp_micro, qe.evaluation_id",
            (run_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]


class QualityGateResultRepository(SqliteRepository[QualityGateResult]):
    model = QualityGateResult
    table = "quality_gate_results"
    key_columns = ("quality_gate_result_id",)
    columns = (
        "quality_gate_result_id",
        "gate_id",
        "gate_version",
        "stage_instance_id",
        "logical_item_key",
        "decision",
        "policy_version",
        "created_timestamp_micro",
        "completed_timestamp_micro",
    )
    order_by = ("created_timestamp_micro", "quality_gate_result_id")

    def list_for_stage_instance(
        self, stage_instance_id: str
    ) -> list[QualityGateResult]:
        """List gate results for a stage instance."""
        rows = self.connection.execute(
            "SELECT payload FROM quality_gate_results "
            "WHERE stage_instance_id = ? "
            "ORDER BY created_timestamp_micro, quality_gate_result_id",
            (stage_instance_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]

    def list_for_gate(
        self, gate_id: str, stage_instance_id: str | None = None
    ) -> list[QualityGateResult]:
        """List gate results for a gate, optionally filtered by stage instance."""
        if stage_instance_id:
            rows = self.connection.execute(
                "SELECT payload FROM quality_gate_results "
                "WHERE gate_id = ? AND stage_instance_id = ? "
                "ORDER BY created_timestamp_micro, quality_gate_result_id",
                (gate_id, stage_instance_id),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT payload FROM quality_gate_results "
                "WHERE gate_id = ? "
                "ORDER BY created_timestamp_micro, quality_gate_result_id",
                (gate_id,),
            ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]

    def list_for_run(self, run_id: str) -> list[QualityGateResult]:
        """List gate results for a workflow run (joins via stage_instances)."""
        rows = self.connection.execute(
            "SELECT qgr.payload FROM quality_gate_results qgr "
            "JOIN stage_instances si "
            "ON qgr.stage_instance_id = si.stage_instance_id "
            "WHERE si.run_id = ? "
            "ORDER BY qgr.created_timestamp_micro, qgr.quality_gate_result_id",
            (run_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]


class QualityInputManifestRepository(SqliteRepository[QualityInputManifest]):
    model = QualityInputManifest
    table = "quality_input_manifests"
    key_columns = ("manifest_id",)
    columns = (
        "manifest_id",
        "gate_id",
        "check_id",
        "created_timestamp_micro",
    )
    order_by = ("created_timestamp_micro", "manifest_id")

    def list_for_gate(
        self, gate_id: str, check_id: str | None = None
    ) -> list[QualityInputManifest]:
        """List manifests for a gate."""
        if check_id:
            rows = self.connection.execute(
                "SELECT payload FROM quality_input_manifests "
                "WHERE gate_id = ? AND check_id = ? "
                "ORDER BY created_timestamp_micro, manifest_id",
                (gate_id, check_id),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT payload FROM quality_input_manifests "
                "WHERE gate_id = ? ORDER BY created_timestamp_micro, manifest_id",
                (gate_id,),
            ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]


class RepairPlanRepository(SqliteRepository[RepairPlan]):
    model = RepairPlan
    table = "repair_plans"
    key_columns = ("repair_plan_id",)
    columns = (
        "repair_plan_id",
        "source_gate_result_id",
        "invalidation_scope",
        "created_timestamp_micro",
    )
    order_by = ("created_timestamp_micro", "repair_plan_id")

    def list_for_source(self, source_gate_result_id: str) -> list[RepairPlan]:
        """List repair plans for a source gate result."""
        rows = self.connection.execute(
            "SELECT payload FROM repair_plans "
            "WHERE source_gate_result_id = ? "
            "ORDER BY created_timestamp_micro, repair_plan_id",
            (source_gate_result_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]

    def list_for_stage_instance(self, stage_instance_id: str) -> list[RepairPlan]:
        """List repair plans targeting a stage instance."""
        rows = self.connection.execute(
            "SELECT payload FROM repair_plans "
            "WHERE ? IN (SELECT value FROM json_each(target_stage_instance_ids)) "
            "ORDER BY created_timestamp_micro, repair_plan_id",
            (stage_instance_id,),
        ).fetchall()
        return [self.model.model_validate_json(row[0]) for row in rows]
