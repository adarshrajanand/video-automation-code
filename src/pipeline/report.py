"""Validation report generation for workflow runs."""

from __future__ import annotations

import os
import platform
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pipeline.contracts.artifacts import Artifact, ArtifactDependency
from pipeline.contracts.execution import StageAttempt, StageInstance, WorkflowRun
from pipeline.contracts.quality import QualityGateResult
from pipeline.contracts.vocabularies import (
    AttemptStatus,
)

if TYPE_CHECKING:
    from pipeline.storage.database import Database


@dataclass(slots=True)
class ValidationReport:
    """Complete validation report for a workflow run."""

    schema_version: str = "validation-report.v1"
    report_id: str = field(default_factory=lambda: f"vrpt_{uuid.uuid4().hex[:12]}")
    run_id: str = ""
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Environment and command info
    command: str = ""
    environment: dict[str, str] = field(default_factory=dict)
    python_version: str = ""
    platform_info: str = ""
    package_version: str = ""

    # Run manifest
    workflow_run: WorkflowRun | None = None
    stage_instances: list[StageInstance] = field(default_factory=list)
    stage_attempts: list[StageAttempt] = field(default_factory=list)

    # Artifact graph
    artifacts: list[Artifact] = field(default_factory=list)
    artifact_dependencies: list[ArtifactDependency] = field(default_factory=list)

    # Output media metadata
    output_artifacts: list[dict[str, Any]] = field(default_factory=list)

    # Quality results
    quality_gate_results: list[QualityGateResult] = field(default_factory=list)
    known_blind_spots: list[str] = field(default_factory=list)

    # Fault injection results
    fault_injection_results: list[dict[str, Any]] = field(default_factory=list)

    # Time per stage
    stage_timings: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Provider usage/cost
    provider_usage: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Regeneration scope and count
    regeneration_summary: dict[str, Any] = field(default_factory=dict)

    # Next extension decision
    next_extension_decision: str = ""

    def to_markdown(self) -> str:
        """Generate markdown report."""
        lines = [
            f"# Validation Report: {self.run_id}",
            "",
            f"**Report ID:** {self.report_id}",
            f"**Generated:** {self.generated_at.isoformat()}",
            "",
            "---",
            "",
            "## 1. Execution Environment",
            "",
            f"**Command:** `{self.command}`",
            f"**Python:** {self.python_version}",
            f"**Platform:** {self.platform_info}",
            f"**Package Version:** {self.package_version}",
            "",
            "### Environment Variables",
            "",
        ]
        for key, value in sorted(self.environment.items()):
            lines.append(f"- `{key}` = `{value}`")
        lines.append("")

        lines.extend(
            [
                "---",
                "",
                "## 2. Run Manifest",
                "",
            ]
        )
        if self.workflow_run:
            run = self.workflow_run
            lines.extend(
                [
                    f"- **Run ID:** {run.run_id}",
                    f"- **Run Key:** {run.run_key}",
                    f"- **Workflow:** {run.workflow_id} v{run.workflow_version}",
                    f"- **Status:** {run.status.value}",
                    (
                        "- **Effective Config:** "
                        f"{run.effective_config_id} "
                        f"(hash: {run.effective_config_hash[:16]}...)"
                    ),
                    f"- **Content Package:** {run.content_package_id}",
                    f"- **Created:** {run.created_at.isoformat()}",
                    f"- **Updated:** {run.updated_at.isoformat()}",
                    "",
                ]
            )

        lines.extend(
            [
                "### Stage Instances",
                "",
                (
                    "| Stage Instance ID | Node | Item Key | Exec Status | "
                    "Accept Status | Quality Gate | Active Attempt |"
                ),
                (
                    "|-------------------|------|----------|-------------|---------------|"
                    "--------------|----------------|"
                ),
            ]
        )
        for si in self.stage_instances:
            lines.append(
                f"| {si.stage_instance_id} | {si.node_id} | {si.logical_item_key} | "
                f"{si.execution_status.value} | {si.acceptance_status.value} | "
                f"{si.quality_gate_id or 'N/A'} | {si.active_attempt_id or 'N/A'} |"
            )
        lines.append("")

        lines.extend(
            [
                "### Stage Attempts",
                "",
                (
                    "| Attempt ID | Stage Instance | # | Regen # | Status | Worker | "
                    "Started | Finished | Failure |"
                ),
                (
                    "|------------|----------------|---|---------|--------|--------|"
                    "---------|----------|---------|"
                ),
            ]
        )
        for sa in self.stage_attempts:
            worker = sa.worker_id or "N/A"
            started = sa.started_at.isoformat() if sa.started_at else "N/A"
            finished = sa.finished_at.isoformat() if sa.finished_at else "N/A"
            failure = sa.failure_code.value if sa.failure_code else "N/A"
            lines.append(
                f"| {sa.attempt_id} | {sa.stage_instance_id} | {sa.attempt_number} | "
                f"{sa.quality_regeneration_number} | {sa.status.value} | {worker} | "
                f"{started} | {finished} | {failure} |"
            )
        lines.append("")

        lines.extend(
            [
                "---",
                "",
                "## 3. Artifact Graph",
                "",
                f"Total artifacts: {len(self.artifacts)}",
                f"Total dependencies: {len(self.artifact_dependencies)}",
                "",
                "### Artifacts",
                "",
                (
                    "| Artifact ID | Run | Slot | Type | Version | SHA256 | Size | "
                    "Media Type | State | Producer Attempt |"
                ),
                (
                    "|-------------|-----|------|------|---------|--------|------|------------"
                    "|-------|------------------|"
                ),
            ]
        )
        for artifact in self.artifacts:
            sha_short = artifact.sha256[:16]
            media_type = artifact.media_type or "N/A"
            lines.append(
                f"| {artifact.artifact_id} | {artifact.run_id} | "
                f"{artifact.logical_slot} | {artifact.artifact_type} | "
                f"{artifact.version} | {sha_short}... | {artifact.size_bytes} | "
                f"{media_type} | {artifact.state.value} | "
                f"{artifact.producer_attempt_id} |"
            )
        lines.append("")

        lines.extend(
            [
                "### Dependencies",
                "",
                "| Parent Artifact | Child Artifact | Type |",
                "|-----------------|----------------|------|",
            ]
        )
        for dep in self.artifact_dependencies:
            lines.append(
                f"| {dep.parent_artifact_id} | {dep.child_artifact_id} | "
                f"{dep.dependency_type} |"
            )
        lines.append("")

        lines.extend(
            [
                "---",
                "",
                "## 4. Output Media Metadata",
                "",
            ]
        )
        if self.output_artifacts:
            lines.extend(
                [
                    (
                        "| Artifact ID | Slot | Type | Duration (s) | Resolution | "
                        "Codec | Bitrate |"
                    ),
                    (
                        "|-------------|------|------|--------------|------------|"
                        "-------|---------|"
                    ),
                ]
            )
            for out in self.output_artifacts:
                meta = out.get("media_metadata", {})
                aid = out.get("artifact_id", "")
                slot = out.get("logical_slot", "")
                atype = out.get("artifact_type", "")
                dur = meta.get("duration_seconds", "N/A")
                w = meta.get("width", "N/A")
                h = meta.get("height", "N/A")
                vcodec = meta.get("video_codec", "N/A")
                bitrate = meta.get("bitrate_bps", "N/A")
                lines.append(
                    f"| {aid} | {slot} | {atype} | {dur} | "
                    f"{w}x{h} | {vcodec} | {bitrate} |"
                )
        else:
            lines.append("No output artifacts found.")
        lines.append("")

        lines.extend(
            [
                "---",
                "",
                "## 5. Quality Results",
                "",
            ]
        )
        if self.quality_gate_results:
            for qgr in self.quality_gate_results:
                lines.extend(
                    [
                        f"### Gate: {qgr.gate_id} v{qgr.gate_version}",
                        f"- **Decision:** {qgr.decision.value}",
                        f"- **Run ID:** {qgr.run_id}",
                        f"- **Stage Instance:** {qgr.stage_instance_id}",
                        f"- **Evaluations:** {len(qgr.evaluations)}",
                        f"- **Created:** {qgr.created_at.isoformat()}",
                        "",
                    ]
                )
        else:
            lines.append("No quality gate results found.")
        lines.append("")

        lines.extend(
            [
                "### Known Blind Spots",
                "",
            ]
        )
        if self.known_blind_spots:
            for spot in self.known_blind_spots:
                lines.append(f"- {spot}")
        else:
            lines.append("- None documented")
        lines.append("")

        lines.extend(
            [
                "---",
                "",
                "## 6. Fault Injection Results",
                "",
            ]
        )
        if self.fault_injection_results:
            lines.extend(
                [
                    "| Scenario | Status | Details |",
                    "|----------|--------|---------|",
                ]
            )
            for fi in self.fault_injection_results:
                scenario = fi.get("scenario", "")
                status = fi.get("status", "")
                details = fi.get("details", "")
                lines.append(f"| {scenario} | {status} | {details} |")
        else:
            lines.append("No fault injection results recorded.")
        lines.append("")

        lines.extend(
            [
                "---",
                "",
                "## 7. Time Per Stage",
                "",
                "| Stage Instance | Node | Started | Finished | Duration (s) |",
                "|----------------|------|---------|----------|--------------|",
            ]
        )
        for si_id, timing in self.stage_timings.items():
            node = timing.get("node_id", "")
            started = timing.get("started_at", "N/A")
            finished = timing.get("finished_at", "N/A")
            duration = timing.get("duration_seconds", "N/A")
            lines.append(f"| {si_id} | {node} | {started} | {finished} | {duration} |")
        lines.append("")

        lines.extend(
            [
                "---",
                "",
                "## 8. Provider Usage / Cost",
                "",
            ]
        )
        if self.provider_usage:
            lines.extend(
                [
                    (
                        "| Provider | Model | Calls | Total Latency (ms) | "
                        "Total Cost (minor) |"
                    ),
                    (
                        "|----------|-------|-------|-------------------|"
                        "-------------------|"
                    ),
                ]
            )
            for provider, usage in self.provider_usage.items():
                model = usage.get("model", "N/A")
                calls = usage.get("calls", 0)
                latency = usage.get("total_latency_ms", 0)
                cost = usage.get("total_cost_minor", 0)
                lines.append(f"| {provider} | {model} | {calls} | {latency} | {cost} |")
        else:
            lines.append("No provider usage data recorded.")
        lines.append("")

        lines.extend(
            [
                "---",
                "",
                "## 9. Regeneration Summary",
                "",
            ]
        )
        if self.regeneration_summary:
            lines.extend(
                [
                    (
                        "- **Total Regenerations:** "
                        f"{self.regeneration_summary.get('total_regenerations', 0)}"
                    ),
                    "- **By Scope:**",
                ]
            )
            for scope, count in self.regeneration_summary.get("by_scope", {}).items():
                lines.append(f"  - {scope}: {count}")
            lines.append("- **By Stage:**")
            for stage, count in self.regeneration_summary.get("by_stage", {}).items():
                lines.append(f"  - {stage}: {count}")
        else:
            lines.append("No regeneration data.")
        lines.append("")

        lines.extend(
            [
                "---",
                "",
                "## 10. Next Extension Decision",
                "",
                self.next_extension_decision or "No decision recorded.",
                "",
                "---",
                "",
                "*Report generated by video-automation-pipeline validation framework*",
            ]
        )

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "schema_version": self.schema_version,
            "report_id": self.report_id,
            "run_id": self.run_id,
            "generated_at": self.generated_at.isoformat(),
            "command": self.command,
            "environment": self.environment,
            "python_version": self.python_version,
            "platform_info": self.platform_info,
            "package_version": self.package_version,
            "workflow_run": self.workflow_run.model_dump(mode="json")
            if self.workflow_run
            else None,
            "stage_instances": [
                si.model_dump(mode="json") for si in self.stage_instances
            ],
            "stage_attempts": [
                sa.model_dump(mode="json") for sa in self.stage_attempts
            ],
            "artifacts": [a.model_dump(mode="json") for a in self.artifacts],
            "artifact_dependencies": [
                ad.model_dump(mode="json") for ad in self.artifact_dependencies
            ],
            "output_artifacts": self.output_artifacts,
            "quality_gate_results": [
                qgr.model_dump(mode="json") for qgr in self.quality_gate_results
            ],
            "known_blind_spots": self.known_blind_spots,
            "fault_injection_results": self.fault_injection_results,
            "stage_timings": self.stage_timings,
            "provider_usage": self.provider_usage,
            "regeneration_summary": self.regeneration_summary,
            "next_extension_decision": self.next_extension_decision,
        }


class ValidationReportGenerator:
    """Generates validation reports from database records."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def generate(self, run_id: str) -> ValidationReport:
        """Generate a complete validation report for a run."""
        report = ValidationReport(run_id=run_id)

        # Capture environment
        report.command = " ".join(sys.argv)
        report.environment = {
            k: v for k, v in os.environ.items() if not k.startswith("_")
        }
        report.python_version = sys.version.split()[0]
        report.platform_info = (
            f"{platform.system()} {platform.release()} ({platform.machine()})"
        )

        # Get package version
        try:
            from pipeline import __version__

            report.package_version = __version__
        except ImportError:
            report.package_version = "unknown"

        with self.database.transaction() as conn:
            from pipeline.storage.repositories.artifacts import (
                ArtifactDependencyRepository,
                ArtifactRepository,
            )
            from pipeline.storage.repositories.execution import (
                StageAttemptRepository,
                StageInstanceRepository,
                WorkflowRunRepository,
            )

            # Load workflow run
            run_repo = WorkflowRunRepository(conn)
            report.workflow_run = run_repo.get(run_id)

            # Load stage instances
            si_repo = StageInstanceRepository(conn)
            report.stage_instances = si_repo.list_for_run(run_id)

            # Load stage attempts
            sa_repo = StageAttemptRepository(conn)
            for si in report.stage_instances:
                attempts = sa_repo.list_for_stage_instance(si.stage_instance_id)
                report.stage_attempts.extend(attempts)

            # Load artifacts
            artifact_repo = ArtifactRepository(conn)
            report.artifacts = artifact_repo.list_for_run(run_id)

            # Load artifact dependencies
            dep_repo = ArtifactDependencyRepository(conn)
            for artifact in report.artifacts:
                deps = dep_repo.list_for_parent(artifact.artifact_id)
                report.artifact_dependencies.extend(deps)

            # Load quality gate results (optional - repository may not exist)
            try:
                from pipeline.storage.repositories.editorial import (
                    QualityGateResultRepository,
                )

                qgr_repo = QualityGateResultRepository(conn)
                report.quality_gate_results = qgr_repo.list_for_run(run_id)
            except ImportError:
                # Repository not available yet
                report.quality_gate_results = []

            # Load human reviews for blind spots
            from pipeline.storage.repositories.editorial import HumanReviewRepository

            hr_repo = HumanReviewRepository(conn)
            reviews = hr_repo.list(run_id=run_id)
            for review in reviews:
                if review.status.value == "RESOLVED":
                    decision = hr_repo.get_decision(review.review_id)
                    if decision and decision.decision.value == "APPROVE":
                        reasons = ", ".join(review.reason_codes)
                        artifacts = ", ".join(review.target_artifact_ids)
                        report.known_blind_spots.append(
                            "Human-approved quality gap: "
                            f"{reasons} on artifacts {artifacts}"
                        )

        # Compute stage timings
        for si in report.stage_instances:
            attempts = [
                a
                for a in report.stage_attempts
                if a.stage_instance_id == si.stage_instance_id
            ]
            if attempts:
                started = min(
                    (a.started_at for a in attempts if a.started_at), default=None
                )
                finished = max(
                    (a.finished_at for a in attempts if a.finished_at), default=None
                )
                duration = None
                if started and finished:
                    duration = (finished - started).total_seconds()
                report.stage_timings[si.stage_instance_id] = {
                    "node_id": si.node_id,
                    "started_at": started.isoformat() if started else None,
                    "finished_at": finished.isoformat() if finished else None,
                    "duration_seconds": duration,
                }

        # Compute regeneration summary
        total_regens = sum(a.quality_regeneration_number for a in report.stage_attempts)
        by_scope: dict[str, int] = {}
        by_stage: dict[str, int] = {}
        for sa in report.stage_attempts:
            if sa.quality_regeneration_number > 0:
                si = next(
                    (
                        s
                        for s in report.stage_instances
                        if s.stage_instance_id == sa.stage_instance_id
                    ),
                    None,
                )
                if si:
                    by_stage[si.node_id] = (
                        by_stage.get(si.node_id, 0) + sa.quality_regeneration_number
                    )
                # Scope would need more context - using attempt status as proxy
                scope = "SCENE" if sa.status == AttemptStatus.SUCCEEDED else "STAGE"
                by_scope[scope] = by_scope.get(scope, 0) + 1

        report.regeneration_summary = {
            "total_regenerations": total_regens,
            "by_scope": by_scope,
            "by_stage": by_stage,
        }

        # Extract output media metadata
        for artifact in report.artifacts:
            if (
                artifact.state.value in ("ACCEPTED", "PUBLISHED")
                and artifact.media_metadata
            ):
                report.output_artifacts.append(
                    {
                        "artifact_id": artifact.artifact_id,
                        "logical_slot": artifact.logical_slot,
                        "artifact_type": artifact.artifact_type,
                        "media_metadata": artifact.media_metadata,
                    }
                )

        # Next extension decision (placeholder - would be based on analysis)
        report.next_extension_decision = (
            "Based on current run analysis, the next recommended extension is "
            "**FV-12: Remotion Renderer Integration** to enable real video composition "
            "and rendering. This will close the gap between composition specs and "
            "final MP4 output, allowing end-to-end validation of the pipeline."
        )

        return report


def generate_validation_report(
    database: Database,
    run_id: str,
) -> ValidationReport:
    """Convenience function to generate a validation report."""
    generator = ValidationReportGenerator(database)
    return generator.generate(run_id)


__all__ = [
    "ValidationReport",
    "ValidationReportGenerator",
    "generate_validation_report",
]
