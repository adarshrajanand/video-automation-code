"""Quality report generation with false-pass rate, false-reject rate,
abstention rate, etc."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pipeline.contracts.quality import QualityEvaluation, QualityGateResult
from pipeline.contracts.vocabularies import CheckOutcome, GateDecision
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
        # In a real implementation, this would query the database for
        # QualityGateResult and QualityEvaluation records
        # For now, return a template report
        return QualityReport(
            run_ids=run_ids or [],
            gate_ids=gate_ids or [],
            period_start=period_start,
            period_end=period_end,
        )

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


@dataclass(slots=True)
class GateQualitySummary:
    """Summary of quality metrics for a single gate evaluation."""

    gate_result: QualityGateResult
    evaluations: tuple[QualityEvaluation, ...]

    @property
    def decision(self) -> GateDecision:
        return self.gate_result.decision

    @property
    def all_checks_passed(self) -> bool:
        return all(e.outcome is CheckOutcome.PASS for e in self.evaluations)

    @property
    def has_human_review_checks(self) -> bool:
        return any(e.outcome is CheckOutcome.ABSTAIN for e in self.evaluations)

    @property
    def failed_checks(self) -> list[QualityEvaluation]:
        return [e for e in self.evaluations if e.outcome is CheckOutcome.FAIL]

    @property
    def total_latency_ms(self) -> int:
        return sum(e.latency_ms or 0 for e in self.evaluations)

    @property
    def total_cost_minor(self) -> int:
        return sum(
            e.actual_cost_minor or e.estimated_cost_minor for e in self.evaluations
        )

    def get_dimension_scores(self) -> dict[str, dict[str, float]]:
        """Get dimension scores by check."""
        result = {}
        for evaluation in self.evaluations:
            dims = {}
            for dim in evaluation.dimensions:
                if dim.score is not None:
                    dims[dim.name] = {
                        "score": dim.score,
                        "threshold": dim.threshold or 0.0,
                        "pass": dim.score >= (dim.threshold or 0.0),
                    }
            result[evaluation.check_id] = dims
        return result

    def get_failure_codes(self) -> list[str]:
        """Get all unique failure codes from failed evaluations."""
        codes = set()
        for evaluation in self.evaluations:
            for dim in evaluation.dimensions:
                codes.update(dim.failure_codes)
        return sorted(codes)
