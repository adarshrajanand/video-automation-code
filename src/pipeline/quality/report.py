"""Quality report generation with false-pass rate, false-reject rate,
abstention rate, etc."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pipeline.contracts.vocabularies import CheckOutcome
from pipeline.ids import deterministic_id

if TYPE_CHECKING:
    from pipeline.storage.database import Database


@dataclass(slots=True)
class QualityReport:
    """Aggregate quality report for a time period or run set."""

    schema_version: str = "quality-report.v1"
    report_id: str = field(
        default_factory=lambda: (
            f"rpt_{deterministic_id('qrpt', str(datetime.now(UTC).timestamp()))}"
        )
    )
    run_ids: list[str] = field(default_factory=list)
    gate_ids: list[str] = field(default_factory=list)
    period_start: datetime | None = None
    period_end: datetime | None = None

    # Gate decision counts
    total_gates: int = 0
    pass_count: int = 0
    regenerate_count: int = 0
    human_review_count: int = 0
    fail_count: int = 0

    # Check outcome counts
    total_checks: int = 0
    check_pass_count: int = 0
    check_fail_count: int = 0
    check_abstain_count: int = 0
    check_error_count: int = 0
    check_not_applicable_count: int = 0

    # Quality metrics
    false_pass_rate: float = 0.0
    false_reject_rate: float = 0.0
    abstention_rate: float = 0.0
    escalation_rate: float = 0.0
    repair_scope_precision: float = 0.0

    # Latency and cost
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    total_cost_minor: int = 0
    avg_cost_per_gate_minor: float = 0.0

    # Dimension-level metrics
    dimension_metrics: dict[str, dict[str, float]] = field(default_factory=dict)

    # Failure code distribution
    failure_code_distribution: dict[str, int] = field(default_factory=dict)

    # Recalibration status
    thresholds_needing_recalibration: list[str] = field(default_factory=list)

    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "schema_version": self.schema_version,
            "report_id": self.report_id,
            "run_ids": self.run_ids,
            "gate_ids": self.gate_ids,
            "period_start": self.period_start.isoformat()
            if self.period_start
            else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "total_gates": self.total_gates,
            "pass_count": self.pass_count,
            "regenerate_count": self.regenerate_count,
            "human_review_count": self.human_review_count,
            "fail_count": self.fail_count,
            "total_checks": self.total_checks,
            "check_pass_count": self.check_pass_count,
            "check_fail_count": self.check_fail_count,
            "check_abstain_count": self.check_abstain_count,
            "check_error_count": self.check_error_count,
            "check_not_applicable_count": self.check_not_applicable_count,
            "false_pass_rate": self.false_pass_rate,
            "false_reject_rate": self.false_reject_rate,
            "abstention_rate": self.abstention_rate,
            "escalation_rate": self.escalation_rate,
            "repair_scope_precision": self.repair_scope_precision,
            "avg_latency_ms": self.avg_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "total_cost_minor": self.total_cost_minor,
            "avg_cost_per_gate_minor": self.avg_cost_per_gate_minor,
            "dimension_metrics": self.dimension_metrics,
            "failure_code_distribution": self.failure_code_distribution,
            "thresholds_needing_recalibration": self.thresholds_needing_recalibration,
            "generated_at": self.generated_at.isoformat(),
        }


class QualityReportGenerator:
    """Generates quality reports from stored evaluations and gate results."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def generate(
        self,
        run_ids: list[str] | None = None,
        gate_ids: list[str] | None = None,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> QualityReport:
        """Generate a quality report for the given filters."""
        with self.database.connection() as conn:
            from pipeline.storage.repositories.quality import (
                QualityEvaluationRepository,
                QualityGateResultRepository,
            )

            eval_repo = QualityEvaluationRepository(conn)
            gate_repo = QualityGateResultRepository(conn)

            # Query gate results
            if run_ids:
                gate_results = []
                for run_id in run_ids:
                    gate_results.extend(gate_repo.list_for_run(run_id))
            elif gate_ids:
                gate_results = []
                for gate_id in gate_ids:
                    gate_results.extend(gate_repo.list_for_gate(gate_id))
            else:
                # Get all gate results (could be large, but we need to filter)
                gate_results = gate_repo.list()

            # Filter by period if specified
            if period_start:
                gate_results = [g for g in gate_results if g.created_at >= period_start]
            if period_end:
                gate_results = [
                    g
                    for g in gate_results
                    if g.completed_at and g.completed_at <= period_end
                ]

            # Query evaluations
            if run_ids:
                evaluations = []
                for run_id in run_ids:
                    evaluations.extend(eval_repo.list_for_run(run_id))
            elif gate_ids:
                evaluations = []
                for gate_id in gate_ids:
                    evaluations.extend(eval_repo.list_for_gate(gate_id))
            else:
                evaluations = eval_repo.list()

            # Filter by period
            if period_start:
                evaluations = [e for e in evaluations if e.created_at >= period_start]
            if period_end:
                evaluations = [e for e in evaluations if e.created_at <= period_end]

        # Build report
        report = QualityReport(
            run_ids=run_ids or [],
            gate_ids=gate_ids or [],
            period_start=period_start,
            period_end=period_end,
        )

        report.total_gates = len(gate_results)
        report.pass_count = sum(1 for g in gate_results if g.decision.value == "PASS")
        report.regenerate_count = sum(
            1 for g in gate_results if g.decision.value == "REGENERATE"
        )
        report.human_review_count = sum(
            1 for g in gate_results if g.decision.value == "HUMAN_REVIEW"
        )
        report.fail_count = sum(1 for g in gate_results if g.decision.value == "FAIL")

        report.total_checks = len(evaluations)
        report.check_pass_count = sum(
            1 for e in evaluations if e.outcome is CheckOutcome.PASS
        )
        report.check_fail_count = sum(
            1 for e in evaluations if e.outcome is CheckOutcome.FAIL
        )
        report.check_abstain_count = sum(
            1 for e in evaluations if e.outcome is CheckOutcome.ABSTAIN
        )
        report.check_error_count = sum(
            1 for e in evaluations if e.outcome is CheckOutcome.ERROR
        )

        # Calculate metrics
        if report.total_checks > 0:
            report.false_pass_rate = 0.0  # Would need gold set
            report.false_reject_rate = 0.0
            report.abstention_rate = report.check_abstain_count / report.total_checks
            report.escalation_rate = report.human_review_count / max(
                report.total_gates, 1
            )

        # Latency and cost
        if evaluations:
            latencies = [e.latency_ms or 0 for e in evaluations]
            report.avg_latency_ms = sum(latencies) / len(latencies)
            sorted_latencies = sorted(latencies)
            p95_idx = int(0.95 * len(sorted_latencies))
            report.p95_latency_ms = sorted_latencies[
                min(p95_idx, len(sorted_latencies) - 1)
            ]

            costs = [
                e.actual_cost_minor or e.estimated_cost_minor or 0 for e in evaluations
            ]
            report.total_cost_minor = sum(costs)
            report.avg_cost_per_gate_minor = report.total_cost_minor / max(
                report.total_gates, 1
            )

        # Failure code distribution
        failure_codes = {}
        for eval_record in evaluations:
            for dim in eval_record.dimensions:
                for fc in dim.failure_codes:
                    failure_codes[fc.value] = failure_codes.get(fc.value, 0) + 1
        report.failure_code_distribution = failure_codes

        return report

    def generate_for_run(self, run_id: str) -> QualityReport:
        """Generate a quality report for a single workflow run."""
        return self.generate(run_ids=[run_id])


def generate_quality_report(
    database: Database,
    run_ids: list[str] | None = None,
    gate_ids: list[str] | None = None,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> QualityReport:
    """Convenience function to generate a quality report."""
    generator = QualityReportGenerator(database)
    return generator.generate(run_ids, gate_ids, period_start, period_end)
