"""Command-line interface for the pipeline bootstrap shell.

Entry point: ``python -m pipeline``

Commands:
- ``workflow validate``: Validate workflow definition against schema
- ``workflow readiness``: Evaluate readiness for a workflow run
- ``outbox dispatch``: Dispatch pending outbox messages
- ``worker run``: Run a single worker iteration
- ``capabilities list``: List registered capability implementations
- ``capabilities invoke``: Invoke a fake capability with scripted outcome
- ``contracts export-schemas``: Export JSON schemas to schemas/
- ``check-setup``: Verify local environment (python, node, ffmpeg, etc.)

Architecture:
The CLI is the single entry point for all pipeline operations. It uses
argparse for command parsing and delegates to internal modules. All
commands that access the database accept explicit ``--database`` path
(defaults to ``PIPELINE_HOME/state/pipeline.sqlite3``).

No external dependencies: all commands operate on local SQLite database.
No network calls, no provider SDKs, no external credentials required.

Exit Codes:
- 0: Success
- 1: General error / validation failure
- 2: Invalid command usage
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline import __version__
from pipeline.contracts.execution import WorkflowRun
from pipeline.contracts.schema_export import (
    check_schemas,
    default_schema_dir,
    export_schemas,
)
from pipeline.contracts.vocabularies import RunStatus
from pipeline.contracts.workflow import WorkflowDefinition
from pipeline.execution import (
    NoopJobHandler,
    NoopOutboxHandler,
    OutboxDispatcher,
    WorkerLoop,
)
from pipeline.paths import default_database_path
from pipeline.report import generate_validation_report
from pipeline.setup_checks import CheckStatus, SetupReport, collect_checks
from pipeline.storage import Database, MigrationError, MigrationRunner
from pipeline.workflow import (
    ReadinessContext,
    WorkflowLoadError,
    evaluate_readiness,
    load_workflow,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline",
        description=("Local-first AI video automation pipeline (FV-01 through FV-05)."),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    check_setup = subparsers.add_parser(
        "check-setup",
        help="check local prerequisites and PIPELINE_HOME paths",
        description=(
            "Report stable, actionable results for the Python package, Node.js "
            "and npm, Remotion renderer readiness, FFmpeg/ffprobe, PIPELINE_HOME "
            "paths, and SQLite. Exits non-zero when a required check fails."
        ),
    )
    check_setup.add_argument(
        "--json",
        action="store_true",
        help="emit the same results as machine-readable JSON",
    )
    contracts = subparsers.add_parser(
        "contracts",
        help="contract tooling",
        description="Export or verify the committed JSON Schemas.",
    )
    contracts_subparsers = contracts.add_subparsers(
        dest="contracts_command", metavar="ACTION"
    )
    export_schemas_parser = contracts_subparsers.add_parser(
        "export-schemas",
        help="write JSON Schemas and the manifest, or check for drift",
        description=(
            "Write one JSON Schema per public contract plus schemas/manifest.json. "
            "With --check, compare committed files against freshly rendered schemas "
            "and exit non-zero when they differ."
        ),
    )
    export_schemas_parser.add_argument(
        "--check",
        action="store_true",
        help="verify committed schemas without writing any files",
    )
    export_schemas_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="schema directory (defaults to the repository schemas/ directory)",
    )
    db = subparsers.add_parser(
        "db",
        help="local SQLite repository tooling",
        description="Inspect or migrate the local SQLite repository schema.",
    )
    db_subparsers = db.add_subparsers(dest="db_command", metavar="ACTION")
    for action, help_text, description in (
        (
            "migrate",
            "apply pending schema migrations",
            "Apply every pending migration once. A second run is a no-op.",
        ),
        (
            "status",
            "show applied and pending migrations",
            "Report the current schema version and pending migrations.",
        ),
    ):
        action_parser = db_subparsers.add_parser(
            action,
            help=help_text,
            description=description,
        )
        action_parser.add_argument(
            "--database",
            type=Path,
            default=None,
            help=(
                "SQLite database path "
                "(defaults to PIPELINE_HOME/state/pipeline.sqlite3)"
            ),
        )
    workflow = subparsers.add_parser(
        "workflow",
        help="workflow definition validation and readiness inspection",
        description=(
            "Validate a versioned YAML workflow definition or evaluate pure "
            "readiness from an explicit JSON context."
        ),
    )
    workflow_subparsers = workflow.add_subparsers(
        dest="workflow_command", metavar="ACTION"
    )
    workflow_validate = workflow_subparsers.add_parser(
        "validate",
        help="parse and statically validate a workflow YAML file",
        description=(
            "Parse a workflow file with yaml.safe_load and validate it through "
            "the canonical WorkflowDefinition contract."
        ),
    )
    workflow_validate.add_argument(
        "path",
        type=Path,
        help="workflow definition YAML file",
    )
    workflow_readiness = workflow_subparsers.add_parser(
        "readiness",
        help="evaluate pure readiness and print a JSON result",
        description=(
            "Evaluate workflow readiness from explicit durable records supplied "
            "in a JSON context. With no context, only root readiness is planned."
        ),
    )
    workflow_readiness.add_argument(
        "path",
        type=Path,
        help="workflow definition YAML file",
    )
    workflow_readiness.add_argument(
        "--context",
        type=Path,
        default=None,
        help=(
            "JSON readiness context file, or - for stdin "
            "(defaults to an empty synthetic run)"
        ),
    )
    outbox = subparsers.add_parser(
        "outbox",
        help="local transactional-outbox tooling",
        description=(
            "Claim and deliver local outbox rows. No external broker is used."
        ),
    )
    outbox_subparsers = outbox.add_subparsers(dest="outbox_command", metavar="ACTION")
    outbox_dispatch = outbox_subparsers.add_parser(
        "dispatch",
        help="claim and deliver one batch of pending outbox messages",
        description=(
            "Claim a bounded batch with explicit leases, run the safe local "
            "no-op delivery handler, and acknowledge each message. Use --once "
            "for a single smoke pass."
        ),
    )
    outbox_dispatch.add_argument(
        "--once",
        action="store_true",
        required=True,
        help="run one bounded polling pass (the supported local mode)",
    )
    outbox_dispatch.add_argument(
        "--database",
        type=Path,
        default=None,
        help=(
            "SQLite database path (defaults to PIPELINE_HOME/state/pipeline.sqlite3)"
        ),
    )
    outbox_dispatch.add_argument(
        "--consumer-id",
        default="local_consumer",
        help="durable inbox consumer identity (default: local_consumer)",
    )
    outbox_dispatch.add_argument(
        "--lease-seconds",
        type=float,
        default=30.0,
        help="dispatcher claim lease in seconds (default: 30)",
    )
    worker = subparsers.add_parser(
        "worker",
        help="local worker-loop smoke tooling",
        description=(
            "Claim one job with a fenced lease and run the safe no-op handler. "
            "This smoke command does not execute stage business logic."
        ),
    )
    worker_subparsers = worker.add_subparsers(dest="worker_command", metavar="ACTION")
    worker_run = worker_subparsers.add_parser(
        "run",
        help="claim and complete at most one job with a no-op handler",
        description=(
            "Claim at most one READY job, run the safe local no-op handler, and "
            "commit the result through a compare-and-set on job and fencing token. "
            "A full worker requires stage handlers from later work packages."
        ),
    )
    worker_run.add_argument(
        "--once",
        action="store_true",
        required=True,
        help="run one polling iteration (the supported local smoke mode)",
    )
    worker_run.add_argument(
        "--database",
        type=Path,
        default=None,
        help=(
            "SQLite database path (defaults to PIPELINE_HOME/state/pipeline.sqlite3)"
        ),
    )
    worker_run.add_argument(
        "--owner-id",
        default="worker_local_cli",
        help="worker lease owner identity (default: worker_local_cli)",
    )
    worker_run.add_argument(
        "--queue",
        default=None,
        help="optional queue name filter",
    )
    worker_run.add_argument(
        "--lease-seconds",
        type=float,
        default=60.0,
        help="job lease in seconds (default: 60)",
    )
    capabilities = subparsers.add_parser(
        "capabilities",
        help="capability registry and fake provider tooling",
        description=(
            "List registered capabilities or invoke a fake capability with a "
            "scripted outcome for testing."
        ),
    )
    capabilities_subparsers = capabilities.add_subparsers(
        dest="capabilities_command", metavar="ACTION"
    )
    capabilities_list = capabilities_subparsers.add_parser(
        "list",
        help="list registered capability implementations",
        description=(
            "Print all registered capability implementations with their metadata."
        ),
    )
    capabilities_list.add_argument(
        "--database",
        type=Path,
        default=None,
        help=(
            "SQLite database path (defaults to PIPELINE_HOME/state/pipeline.sqlite3)"
        ),
    )
    capabilities_invoke = capabilities_subparsers.add_parser(
        "invoke",
        help="invoke a fake capability with a scripted outcome",
        description=(
            "Execute a fake capability request with a deterministic scripted "
            "outcome. Requires an explicit database path for persistence."
        ),
    )
    capabilities_invoke.add_argument(
        "--database",
        type=Path,
        required=True,
        help="SQLite database path (required for persistence)",
    )
    capabilities_invoke.add_argument(
        "--capability",
        required=True,
        help="capability name (e.g., speech_generation)",
    )
    capabilities_invoke.add_argument(
        "--operation-version",
        required=True,
        help="operation version (e.g., v1)",
    )
    capabilities_invoke.add_argument(
        "--fake-outcome",
        required=True,
        choices=sorted(
            [
                "success",
                "validation",
                "authentication",
                "authorization",
                "rate_limit",
                "quota",
                "transient",
                "permanent",
                "timeout_unknown",
                "media",
                "quality",
                "budget",
                "configuration",
                "human_review",
                "policy",
                "internal",
                "speech_generation",
                "tts_adapter",
                "asr_alignment",
                "audio_qc_pass",
                "audio_qc_fail",
                "composition",
                "rendering",
                "assembly",
                "short_derivative",
            ]
        ),
        help="scripted outcome to return",
    )
    capabilities_invoke.add_argument(
        "--provider",
        default="fake",
        help="provider name (default: fake)",
    )
    capabilities_invoke.add_argument(
        "--model",
        default="deterministic-fixture",
        help="model name (default: deterministic-fixture)",
    )
    capabilities_invoke.add_argument(
        "--attempt-id",
        help="attempt ID (generated if not provided)",
    )
    capabilities_invoke.add_argument(
        "--run-id",
        help="run ID (generated if not provided)",
    )
    capabilities_invoke.add_argument(
        "--stage-instance-id",
        help="stage instance ID (generated if not provided)",
    )

    # Quality commands
    quality = subparsers.add_parser(
        "quality",
        help="quality gate, evaluation, and repair tooling",
        description=(
            "Run quality gates, inspect evaluations, and manage repair plans."
        ),
    )
    quality_subparsers = quality.add_subparsers(
        dest="quality_command", metavar="ACTION"
    )
    quality_eval = quality_subparsers.add_parser(
        "evaluate",
        help="run quality gate evaluation for a gate",
        description=(
            "Execute all checks for a quality gate against provided artifacts."
        ),
    )
    quality_eval.add_argument(
        "--gate-id",
        required=True,
        help="quality gate ID (e.g., script_gate_v1)",
    )
    quality_eval.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="path to QualityInputManifest JSON file",
    )
    quality_eval.add_argument(
        "--artifacts-dir",
        type=Path,
        required=True,
        help="directory containing target and supporting artifacts as JSON files",
    )
    quality_eval.add_argument(
        "--database",
        type=Path,
        default=None,
        help="SQLite database path (defaults to PIPELINE_HOME/state/pipeline.sqlite3)",
    )
    quality_eval.add_argument(
        "--regeneration-count",
        type=int,
        default=0,
        help="current regeneration attempt number (default: 0)",
    )
    quality_eval.add_argument(
        "--output",
        type=Path,
        default=None,
        help="output path for gate result JSON (default: stdout)",
    )
    quality_eval.add_argument(
        "--stage-instance-id",
        default=None,
        help="stage instance ID for linking (optional)",
    )
    quality_eval.add_argument(
        "--logical-item-key",
        default=None,
        help="logical item key for linking (optional)",
    )

    quality_list = quality_subparsers.add_parser(
        "list-checks",
        help="list registered quality checks",
        description="Print all registered quality checks with their metadata.",
    )
    quality_list.add_argument(
        "--kind",
        choices=["DETERMINISTIC", "SPECIALIZED", "SEMANTIC", "HUMAN"],
        default=None,
        help="filter by evaluation kind",
    )
    quality_list.add_argument(
        "--gate-id",
        default=None,
        help="filter by gate ID (shows checks required by that gate)",
    )

    # Human review commands
    human_review = subparsers.add_parser(
        "human-review",
        help="human review management",
        description="List, show, and decide human review requests.",
    )
    hr_subparsers = human_review.add_subparsers(
        dest="human_review_command", metavar="ACTION"
    )
    hr_list = hr_subparsers.add_parser(
        "list",
        help="list human review requests",
        description="List open or resolved human review requests.",
    )
    hr_list.add_argument(
        "--database",
        type=Path,
        default=None,
        help="SQLite database path (defaults to PIPELINE_HOME/state/pipeline.sqlite3)",
    )
    hr_list.add_argument(
        "--run-id",
        default=None,
        help="filter by run ID",
    )
    hr_list.add_argument(
        "--status",
        choices=["OPEN", "ASSIGNED", "RESOLVED", "EXPIRED", "CANCELLED"],
        default=None,
        help="filter by review status",
    )
    hr_show = hr_subparsers.add_parser(
        "show",
        help="show human review details",
        description="Display a human review request with all details.",
    )
    hr_show.add_argument(
        "review_id",
        help="review ID to show",
    )
    hr_show.add_argument(
        "--database",
        type=Path,
        default=None,
        help="SQLite database path (defaults to PIPELINE_HOME/state/pipeline.sqlite3)",
    )
    hr_decide = hr_subparsers.add_parser(
        "decide",
        help="record a human review decision",
        description=(
            "Record a reviewer decision: APPROVE, REGENERATE_SCENE, "
            "REGENERATE_STAGE, or REJECT."
        ),
    )
    hr_decide.add_argument(
        "review_id",
        help="review ID to decide",
    )
    hr_decide.add_argument(
        "decision",
        choices=["APPROVE", "REGENERATE_SCENE", "REGENERATE_STAGE", "REJECT"],
        help="review decision",
    )
    hr_decide.add_argument(
        "--reviewer",
        required=True,
        help="reviewer identifier",
    )
    hr_decide.add_argument(
        "--comments",
        default=None,
        help="optional reviewer comments",
    )
    hr_decide.add_argument(
        "--database",
        type=Path,
        default=None,
        help="SQLite database path (defaults to PIPELINE_HOME/state/pipeline.sqlite3)",
    )

    # Validation report command
    report = subparsers.add_parser(
        "report",
        help="generate validation report for a workflow run",
        description=(
            "Produce a comprehensive markdown validation report including "
            "environment, run manifest, artifact graph, quality results, "
            "fault injection results, timing, provider usage, and regeneration summary."
        ),
    )
    report.add_argument(
        "--run-id",
        required=True,
        help="workflow run ID to report on",
    )
    report.add_argument(
        "--output",
        type=Path,
        default=None,
        help="output markdown file path (default: stdout)",
    )
    report.add_argument(
        "--database",
        type=Path,
        default=None,
        help="SQLite database path (defaults to PIPELINE_HOME/state/pipeline.sqlite3)",
    )

    # Artifact graph command
    artifact = subparsers.add_parser(
        "artifact",
        help="artifact inspection tooling",
        description="Inspect artifact lineage and dependency graphs.",
    )
    artifact_subparsers = artifact.add_subparsers(
        dest="artifact_command", metavar="ACTION"
    )
    artifact_graph = artifact_subparsers.add_parser(
        "graph",
        help="print artifact dependency graph for a run",
        description="Display the artifact dependency graph as text or DOT format.",
    )
    artifact_graph.add_argument(
        "--run-id",
        required=True,
        help="workflow run ID",
    )
    artifact_graph.add_argument(
        "--format",
        choices=["text", "dot"],
        default="text",
        help="output format (default: text)",
    )
    artifact_graph.add_argument(
        "--database",
        type=Path,
        default=None,
        help="SQLite database path (defaults to PIPELINE_HOME/state/pipeline.sqlite3)",
    )

    # Run status command
    run = subparsers.add_parser(
        "run",
        help="workflow run inspection",
        description="Inspect workflow run status and details.",
    )
    run_subparsers = run.add_subparsers(dest="run_command", metavar="ACTION")
    run_status = run_subparsers.add_parser(
        "status",
        help="show workflow run status and summary",
        description="Display the current status and summary of a workflow run.",
    )
    run_status.add_argument(
        "--run-id",
        required=True,
        help="workflow run ID",
    )
    run_status.add_argument(
        "--database",
        type=Path,
        default=None,
        help="SQLite database path (defaults to PIPELINE_HOME/state/pipeline.sqlite3)",
    )

    # Job dispatch command
    job = subparsers.add_parser(
        "job",
        help="job queue tooling",
        description="Dispatch and inspect jobs in the local queue.",
    )
    job_subparsers = job.add_subparsers(dest="job_command", metavar="ACTION")
    job_dispatch = job_subparsers.add_parser(
        "dispatch",
        help="dispatch pending jobs to the queue",
        description=(
            "Claim and enqueue READY stage instances as jobs. "
            "Use --once for a single pass."
        ),
    )
    job_dispatch.add_argument(
        "--once",
        action="store_true",
        required=True,
        help="run one dispatch pass (the supported local mode)",
    )
    job_dispatch.add_argument(
        "--database",
        type=Path,
        default=None,
        help="SQLite database path (defaults to PIPELINE_HOME/state/pipeline.sqlite3)",
    )

    # Review commands (alias for human-review with simpler names)
    review = subparsers.add_parser(
        "review",
        help="human review management (alias for human-review)",
        description="List and decide human review requests.",
    )
    review_subparsers = review.add_subparsers(dest="review_command", metavar="ACTION")
    review_list = review_subparsers.add_parser(
        "list",
        help="list human review requests",
        description="List open or resolved human review requests.",
    )
    review_list.add_argument(
        "--database",
        type=Path,
        default=None,
        help="SQLite database path (defaults to PIPELINE_HOME/state/pipeline.sqlite3)",
    )
    review_list.add_argument(
        "--run-id",
        default=None,
        help="filter by run ID",
    )
    review_list.add_argument(
        "--status",
        choices=["OPEN", "ASSIGNED", "RESOLVED", "EXPIRED", "CANCELLED"],
        default=None,
        help="filter by review status",
    )
    review_decide = review_subparsers.add_parser(
        "decide",
        help="record a human review decision",
        description=(
            "Record a reviewer decision: APPROVE, REGENERATE_SCENE, "
            "REGENERATE_STAGE, or REJECT."
        ),
    )
    review_decide.add_argument(
        "review_id",
        help="review ID to decide",
    )
    review_decide.add_argument(
        "decision",
        choices=["APPROVE", "REGENERATE_SCENE", "REGENERATE_STAGE", "REJECT"],
        help="review decision",
    )
    review_decide.add_argument(
        "--reviewer",
        required=True,
        help="reviewer identifier",
    )
    review_decide.add_argument(
        "--comments",
        default=None,
        help="optional reviewer comments",
    )
    review_decide.add_argument(
        "--database",
        type=Path,
        default=None,
        help="SQLite database path (defaults to PIPELINE_HOME/state/pipeline.sqlite3)",
    )

    return parser


def _print_report(report: SetupReport) -> None:
    print("Pipeline setup check")
    print(f"PIPELINE_HOME: {report.pipeline_home}")
    print()
    for check in report.checks:
        scope = "required" if check.required else "optional"
        print(
            f"[{check.status.value.upper()}] {check.check_id} ({scope}): {check.detail}"
        )
        if check.remediation and check.status is not CheckStatus.PASS:
            print(f"    fix: {check.remediation}")

    print()
    print(
        "Summary: "
        f"{report.passed_count} passed, "
        f"{report.warning_count} warning(s), "
        f"{len(report.failed_checks)} failed."
    )
    if report.ok:
        print("Setup check passed.")
    else:
        print(
            "Setup check failed: "
            f"{len(report.required_failed)} required check(s) failed."
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command is None:
        parser.print_help()
        return 0
    if arguments.command == "check-setup":
        report = collect_checks()
        if arguments.json:
            sys.stdout.write(json.dumps(report.to_dict(), indent=2, sort_keys=True))
            sys.stdout.write("\n")
        else:
            _print_report(report)
        return 0 if report.ok else 1
    if arguments.command == "contracts":
        return _run_contracts_command(arguments)
    if arguments.command == "db":
        return _run_db_command(arguments)
    if arguments.command == "workflow":
        return _run_workflow_command(arguments)
    if arguments.command == "outbox":
        return _run_outbox_command(arguments)
    if arguments.command == "worker":
        return _run_worker_command(arguments)
    if arguments.command == "capabilities":
        return _run_capabilities_command(arguments)
    if arguments.command == "quality":
        return _run_quality_command(arguments)
    if arguments.command == "human-review":
        return _run_human_review_command(arguments)
    if arguments.command == "report":
        return _run_report_command(arguments)
    if arguments.command == "artifact":
        return _run_artifact_command(arguments)
    if arguments.command == "run":
        return _run_run_command(arguments)
    if arguments.command == "job":
        return _run_job_command(arguments)
    if arguments.command == "review":
        return _run_review_command(arguments)
    parser.error(f"unknown command: {arguments.command}")
    return 2


def _run_contracts_command(arguments: argparse.Namespace) -> int:
    if arguments.contracts_command is None:
        print("Usage: python -m pipeline contracts export-schemas [--check]")
        return 0
    output_dir = arguments.output_dir or default_schema_dir()
    if arguments.check:
        result = check_schemas(output_dir)
        if result.ok:
            print(f"Contract schemas are up to date: {output_dir}")
            return 0
        print(f"Contract schema drift detected in {output_dir}:", file=sys.stderr)
        if result.missing:
            print(
                "  missing: " + ", ".join(result.missing),
                file=sys.stderr,
            )
        if result.drifted:
            print(
                "  drifted: " + ", ".join(result.drifted),
                file=sys.stderr,
            )
        if result.extra:
            print(
                "  stale: " + ", ".join(result.extra),
                file=sys.stderr,
            )
        print(
            "Run 'python -m pipeline contracts export-schemas' to regenerate.",
            file=sys.stderr,
        )
        return 1
    result = export_schemas(output_dir)
    print(f"Exported {len(result.written)} schema files to {output_dir}")
    return 0


_CLI_RUN_TIME = datetime(2026, 1, 1, tzinfo=UTC)
_CLI_CONTEXT_KEYS = frozenset(
    {
        "run",
        "run_status",
        "stage_instances",
        "input_manifests",
        "accepted_artifact_ids",
        "accepted_artifact_pointers",
        "quality_gate_results",
        "human_reviews",
        "run_input_artifact_ids",
        "artifact_states",
        "condition_context",
        "recoverable_stage_instance_ids",
    }
)


def _synthetic_run(workflow: WorkflowDefinition, status: RunStatus) -> WorkflowRun:
    return WorkflowRun(
        schema_version="workflow-run.v1",
        run_id="run_cli",
        run_key=f"cli:{workflow.workflow_id}:{workflow.version}",
        workflow_id=workflow.workflow_id,
        workflow_version=workflow.version,
        effective_config_id="cfg_cli",
        effective_config_hash="0" * 64,
        status=status,
        content_package_id="package_cli",
        created_at=_CLI_RUN_TIME,
        updated_at=_CLI_RUN_TIME,
    )


def _readiness_context(
    workflow: WorkflowDefinition, context_path: Path | None
) -> ReadinessContext:
    if context_path is None:
        payload: dict[str, Any] = {}
    else:
        if str(context_path) == "-":
            document = sys.stdin.read()
            source = "<stdin>"
        else:
            document = context_path.read_text(encoding="utf-8")
            source = str(context_path)
        payload = json.loads(document)
        if not isinstance(payload, dict):
            raise ValueError(f"{source}: readiness context must be a JSON object")
        unknown = set(payload) - _CLI_CONTEXT_KEYS
        if unknown:
            raise ValueError(
                f"{source}: unknown readiness context key(s): "
                + ", ".join(sorted(unknown))
            )

    if "run" in payload and "run_status" in payload:
        raise ValueError("provide either 'run' or 'run_status', not both")
    if "run" in payload:
        run = WorkflowRun.model_validate(payload["run"])
    else:
        run = _synthetic_run(
            workflow, RunStatus(str(payload.get("run_status", "CREATED")))
        )

    data = {"run": run, "workflow": workflow}
    for key in _CLI_CONTEXT_KEYS - {"run", "run_status"}:
        if key in payload:
            data[key] = payload[key]
    return ReadinessContext.model_validate(data)


def _run_workflow_command(arguments: argparse.Namespace) -> int:
    if arguments.workflow_command is None:
        print("Usage: python -m pipeline workflow {validate,readiness} PATH")
        return 0
    try:
        workflow = load_workflow(arguments.path)
    except WorkflowLoadError as error:
        print(f"Invalid workflow: {error}", file=sys.stderr)
        return 1

    if arguments.workflow_command == "validate":
        root_ids = [node.node_id for node in workflow.nodes if not node.depends_on]
        terminal_ids = [
            node.node_id
            for node in workflow.nodes
            if not any(
                node.node_id in candidate.depends_on for candidate in workflow.nodes
            )
        ]
        print(
            f"Workflow {workflow.workflow_id!r} version {workflow.version!r} is "
            f"valid: {len(workflow.nodes)} node(s), {len(root_ids)} root(s), "
            f"{len(terminal_ids)} terminal node(s)."
        )
        return 0

    if arguments.workflow_command == "readiness":
        try:
            context = _readiness_context(workflow, arguments.context)
            result = evaluate_readiness(context)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            print(f"Readiness evaluation failed: {error}", file=sys.stderr)
            return 1
        sys.stdout.write(
            json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True)
        )
        sys.stdout.write("\n")
        return 0

    print(
        f"Unknown workflow action: {arguments.workflow_command}",
        file=sys.stderr,
    )
    return 2


def _run_outbox_command(arguments: argparse.Namespace) -> int:
    if arguments.outbox_command is None:
        print("Usage: python -m pipeline outbox dispatch --once [--database PATH]")
        return 0
    if arguments.outbox_command != "dispatch":
        print(f"Unknown outbox action: {arguments.outbox_command}", file=sys.stderr)
        return 2
    try:
        database = _migrated_database(arguments.database)
        dispatcher = OutboxDispatcher(
            database,
            handler=NoopOutboxHandler(),
            consumer_id=arguments.consumer_id,
            lease_seconds=arguments.lease_seconds,
        )
        result = dispatcher.dispatch_once()
    except (MigrationError, OSError, sqlite3.Error, ValueError) as error:
        print(
            f"Outbox dispatch failed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1
    print(
        "Outbox dispatch: "
        f"claimed={result.claimed} delivered={result.delivered} "
        f"duplicates={result.duplicates} retried={result.retried} "
        f"failed={result.failed} stale={result.stale}."
    )
    print(f"Database: {database.path}")
    return 0


def _run_worker_command(arguments: argparse.Namespace) -> int:
    if arguments.worker_command is None:
        print("Usage: python -m pipeline worker run --once [--database PATH]")
        return 0
    if arguments.worker_command != "run":
        print(f"Unknown worker action: {arguments.worker_command}", file=sys.stderr)
        return 2
    try:
        database = _migrated_database(arguments.database)
        worker = WorkerLoop(
            database,
            owner_id=arguments.owner_id,
            handler=NoopJobHandler(),
            queue_name=arguments.queue,
            lease_seconds=arguments.lease_seconds,
        )
        result = worker.run_once()
    except (MigrationError, OSError, sqlite3.Error, ValueError) as error:
        print(
            f"Worker run failed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1
    if result.claim is None:
        print(f"Worker {arguments.owner_id}: idle (no eligible job).")
    else:
        print(
            f"Worker {arguments.owner_id}: {result.status.value} "
            f"job={result.claim.job_id} "
            f"fencing_token={result.claim.fencing_token}."
        )
    print(f"Database: {database.path}")
    return 0


def _run_capabilities_command(arguments: argparse.Namespace) -> int:
    if arguments.capabilities_command is None:
        print("Usage: python -m pipeline capabilities {list,invoke} ...")
        return 0

    if arguments.capabilities_command == "list":
        return _run_capabilities_list(arguments)

    if arguments.capabilities_command == "invoke":
        return _run_capabilities_invoke(arguments)

    print(
        f"Unknown capabilities action: {arguments.capabilities_command}",
        file=sys.stderr,
    )
    return 2


def _run_capabilities_list(arguments: argparse.Namespace) -> int:
    try:
        database = _migrated_database(arguments.database)
        from pipeline.capabilities import CapabilityRegistry

        CapabilityRegistry()
        # The registry is empty by default - we just show it's working
        print("Capability Registry (empty - register implementations to populate)")
        print(f"Database: {database.path}")
        return 0
    except (MigrationError, OSError, sqlite3.Error, ValueError) as error:
        print(
            f"Capabilities list failed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1


def _run_capabilities_invoke(arguments: argparse.Namespace) -> int:
    try:
        database = _migrated_database(arguments.database)

        # Import here to avoid circular imports
        from datetime import UTC, datetime

        from pipeline.capabilities import (
            CapabilityExecutor,
            CapabilityRegistry,
            FakeCapabilityProvider,
            create_asr_alignment_success_outcome,
            create_assembly_success_outcome,
            create_audio_qc_failure_outcome,
            create_audio_qc_success_outcome,
            create_composition_success_outcome,
            create_rendering_success_outcome,
            create_short_derivative_success_outcome,
            create_speech_generation_success_outcome,
            create_success_outcome,
            create_tts_adapter_success_outcome,
            outcome_authentication_failure,
            outcome_authorization_failure,
            outcome_budget_exceeded,
            outcome_configuration,
            outcome_human_review,
            outcome_internal,
            outcome_media_integrity,
            outcome_permanent_provider,
            outcome_policy,
            outcome_quality_failure,
            outcome_quota_exceeded,
            outcome_rate_limit,
            outcome_timeout_unknown,
            outcome_transient_provider,
            outcome_validation_failure,
        )
        from pipeline.contracts.capabilities import (
            CapabilityRequest,
            CapabilityRequirements,
            ExecutionContext,
        )
        from pipeline.contracts.routing import RoutingDecision
        from pipeline.fingerprints import sha256_text
        from pipeline.ids import deterministic_id

        # Map fake outcome names to factory functions
        outcome_factories = {
            "success": create_success_outcome,
            "validation": outcome_validation_failure,
            "authentication": outcome_authentication_failure,
            "authorization": outcome_authorization_failure,
            "rate_limit": outcome_rate_limit,
            "quota": outcome_quota_exceeded,
            "transient": outcome_transient_provider,
            "permanent": outcome_permanent_provider,
            "timeout_unknown": outcome_timeout_unknown,
            "media": outcome_media_integrity,
            "quality": outcome_quality_failure,
            "budget": outcome_budget_exceeded,
            "configuration": outcome_configuration,
            "human_review": outcome_human_review,
            "policy": outcome_policy,
            "internal": outcome_internal,
            "speech_generation": create_speech_generation_success_outcome,
            "tts_adapter": create_tts_adapter_success_outcome,
            "asr_alignment": create_asr_alignment_success_outcome,
            "audio_qc_pass": create_audio_qc_success_outcome,
            "audio_qc_fail": create_audio_qc_failure_outcome,
            "composition": create_composition_success_outcome,
            "rendering": create_rendering_success_outcome,
            "assembly": create_assembly_success_outcome,
            "short_derivative": create_short_derivative_success_outcome,
        }

        outcome_factory = outcome_factories[arguments.fake_outcome]

        # Generate IDs if not provided
        import uuid

        run_suffix = f"cli_{uuid.uuid4().hex[:8]}"
        run_id = arguments.run_id or deterministic_id("run", run_suffix)
        stage_instance_id = arguments.stage_instance_id or deterministic_id(
            "stage", run_id
        )
        attempt_id = arguments.attempt_id or deterministic_id(
            "attempt", stage_instance_id
        )
        capability_execution_id = deterministic_id("capexec", attempt_id)
        routing_decision_id = deterministic_id("route", capability_execution_id)

        import json

        # Create fake payload
        payload = {"test": "data", "capability": arguments.capability}
        payload_fingerprint = sha256_text(json.dumps(payload, sort_keys=True))

        # Create capability request
        request = CapabilityRequest(
            schema_version="capability-request.v1",
            capability_execution_id=capability_execution_id,
            capability=arguments.capability,
            operation_version=arguments.operation_version,
            input_artifact_ids=[],
            payload_fingerprint=payload_fingerprint,
            requirements=CapabilityRequirements(
                schema_version="capability-requirements.v1",
                capability=arguments.capability,
            ),
            payload=payload,
            payload_schema_version="test.v1",
            runtime_context={},
            idempotency_key=deterministic_id("idem", capability_execution_id),
        )

        # Create execution context
        context = ExecutionContext(
            schema_version="execution-context.v1",
            run_id=run_id,
            stage_instance_id=stage_instance_id,
            attempt_id=attempt_id,
            effective_config_id=deterministic_id("config", run_id),
            correlation_id=deterministic_id("corr", run_id),
            timeout_seconds=300,
            allowed_data_classification="PUBLIC",
        )

        # Create routing decision
        routing_decision = RoutingDecision(
            schema_version="routing-decision.v1",
            routing_decision_id=routing_decision_id,
            capability=arguments.capability,
            implementation="fake",
            implementation_version="1.0.0",
            provider=arguments.provider,
            model=arguments.model,
            provider_config_hash="0" * 64,
            fallback_chain=[],
            policy_version="1.0",
            reason_codes=["cli_test"],
            candidate_exclusions=[],
            budget_context={},
            usage_context={},
            attempt=1,
            data_classification="PUBLIC",
            paid_fallback_authorized=False,
            created_at=datetime.now(UTC),
        )

        # Create required database records for the fake attempt
        with database.transaction() as conn:
            from pipeline.contracts.config import EffectiveConfig, RunOverrides
            from pipeline.contracts.execution import (
                StageAttempt,
                StageInstance,
                WorkflowRun,
            )
            from pipeline.contracts.vocabularies import (
                AttemptStatus,
                RunStatus,
                StageExecutionStatus,
            )
            from pipeline.storage.repositories.execution import (
                EffectiveConfigRepository,
                StageAttemptRepository,
                StageInstanceRepository,
                WorkflowRunRepository,
            )

            # Create effective config
            effective_config_id = deterministic_id("config", run_id)
            effective_config = EffectiveConfig(
                schema_version="effective-config.v1",
                effective_config_id=effective_config_id,
                config_hash="0" * 64,
                workflow_id="test_workflow",
                workflow_version="1.0",
                system_policy_version="1.0",
                domain_profile_id="test_domain",
                domain_profile_version="1.0",
                channel_profile_id="test_channel",
                channel_profile_version="1.0",
                run_overrides=RunOverrides(schema_version="run-overrides.v1"),
                snapshot_artifact_id=None,
            )
            EffectiveConfigRepository(conn).insert(effective_config)

            # Create workflow run
            workflow_run = WorkflowRun(
                schema_version="workflow-run.v1",
                run_id=run_id,
                run_key=f"cli_test:{run_id}",
                workflow_id="test_workflow",
                workflow_version="1.0",
                effective_config_id=effective_config_id,
                effective_config_hash="0" * 64,
                status=RunStatus.RUNNING,
                content_package_id=deterministic_id("package", run_id),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            WorkflowRunRepository(conn).insert(workflow_run)

            # Create stage instance
            stage_instance = StageInstance(
                schema_version="stage-instance.v1",
                stage_instance_id=stage_instance_id,
                run_id=run_id,
                node_id="test_node",
                logical_item_key="test_item",
                execution_status=StageExecutionStatus.RUNNING,
                acceptance_status="NOT_REQUIRED",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            StageInstanceRepository(conn).insert(stage_instance)

            # Create stage attempt
            stage_attempt = StageAttempt(
                schema_version="stage-attempt.v1",
                attempt_id=attempt_id,
                stage_instance_id=stage_instance_id,
                attempt_number=1,
                status=AttemptStatus.RUNNING,
                started_at=datetime.now(UTC),
            )
            StageAttemptRepository(conn).insert(stage_attempt)

        # Set up registry and fake provider
        registry = CapabilityRegistry()
        fake_provider = FakeCapabilityProvider(registry)
        fake_provider.register_outcome(payload_fingerprint, outcome_factory())

        # Create executor and execute
        executor = CapabilityExecutor(database, registry, fake_provider)
        result = executor.execute(request, context, routing_decision)

        if isinstance(result, tuple) and len(result) == 2:
            # Handle tuple return (legacy)
            execution_output, _idempotency_record = result
        else:
            # Handle new ExecutionResult/ExecutionError
            if hasattr(result, "execution_output"):
                execution_output = result.execution_output
            else:
                # ExecutionError
                print(f"Execution failed: {result.normalized_error.message}")
                print(f"Category: {result.normalized_error.category}")
                print(f"Retryable: {result.normalized_error.retryable}")
                print(
                    f"Reconciliation required: "
                    f"{result.normalized_error.reconciliation_required}"
                )
                return 1

        print(f"Capability execution completed: {execution_output.result.status}")
        print(f"  Capability: {arguments.capability}")
        print(f"  Operation version: {arguments.operation_version}")
        print(f"  Fake outcome: {arguments.fake_outcome}")
        print(f"  Artifact IDs: {execution_output.result.artifact_ids}")
        print(f"  Database: {database.path}")
        return 0

    except (MigrationError, OSError, sqlite3.Error, ValueError, KeyError) as error:
        print(
            f"Capabilities invoke failed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1


def _migrated_database(path: Path | None) -> Database:
    database = Database(path or default_database_path())
    MigrationRunner(database).migrate()
    return database


def _run_db_command(arguments: argparse.Namespace) -> int:
    if arguments.db_command is None:
        print("Usage: python -m pipeline db {migrate,status} [--database PATH]")
        return 0
    database_path = arguments.database or default_database_path()
    database = Database(database_path)
    runner = MigrationRunner(database)
    try:
        if arguments.db_command == "migrate":
            result = runner.migrate()
            if result.changed:
                versions = ", ".join(
                    f"{migration.version:04d}_{migration.name}"
                    for migration in result.applied
                )
                print(
                    f"Applied {len(result.applied)} migration(s): {versions}. "
                    f"Schema version: {result.current_version}."
                )
            else:
                print(
                    f"No pending migrations. Schema version: {result.current_version}."
                )
            print(f"Database: {database.path}")
            return 0
        if arguments.db_command == "status":
            status = runner.status()
            print(f"Database: {status.database_path}")
            print(f"Current version: {status.current_version}")
            print("Applied migrations:")
            if status.applied:
                for applied in status.applied:
                    print(
                        f"  {applied.version:04d}_{applied.name} "
                        f"({applied.checksum}) applied at {applied.applied_at}"
                    )
            else:
                print("  (none)")
            print("Pending migrations:")
            if status.pending:
                for pending in status.pending:
                    print(f"  {pending.version:04d}_{pending.name}")
            else:
                print("  (none)")
            return 0
    except (MigrationError, sqlite3.Error) as error:
        print(
            f"Database command failed: {type(error).__name__}: {error}", file=sys.stderr
        )
        return 1
    print(f"Unknown db action: {arguments.db_command}", file=sys.stderr)
    return 2


def _run_quality_command(arguments: argparse.Namespace) -> int:
    if arguments.quality_command is None:
        print("Usage: python -m pipeline quality {evaluate,list-checks} ...")
        return 0

    if arguments.quality_command == "list-checks":
        return _run_quality_list_checks(arguments)

    if arguments.quality_command == "evaluate":
        return _run_quality_evaluate(arguments)

    print(f"Unknown quality action: {arguments.quality_command}", file=sys.stderr)
    return 2


def _run_quality_list_checks(arguments: argparse.Namespace) -> int:
    try:
        from pipeline.contracts.vocabularies import EvaluationKind
        from pipeline.quality.registry import get_default_registry

        registry = get_default_registry()

        checks = registry.get_all()
        if arguments.kind:
            kind = EvaluationKind(arguments.kind)
            checks = tuple(c for c in checks if c.kind is kind)

        if arguments.gate_id:
            from pipeline.contracts.vocabularies import QUALITY_GATE_IDS

            if arguments.gate_id not in QUALITY_GATE_IDS:
                print(f"Unknown gate ID: {arguments.gate_id}", file=sys.stderr)
                return 1
            # Would need gate policy to filter - for now show all
            pass

        for check in checks:
            print(f"{check.check_id} [{check.kind.value}]")
            print(f"  Target types: {', '.join(check.target_artifact_types)}")
            print(f"  Evaluator: {check.evaluator} v{check.evaluator_version}")
            severity = check.severity_if_failed.value
            print(f"  Required: {check.required}, Severity if failed: {severity}")
            on_failure = check.on_failure.value
            repair = check.repair_scope.value
            print(f"  On failure: {on_failure}, Repair scope: {repair}")
            if check.rubric_version:
                print(f"  Rubric: {check.rubric_version}")
            print()

        print(f"Total: {len(checks)} check(s)")
        return 0
    except Exception as error:
        print(
            f"Quality list-checks failed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1


def _run_quality_evaluate(arguments: argparse.Namespace) -> int:
    try:
        import json

        from pipeline.contracts.quality import QualityGatePolicy, QualityInputManifest
        from pipeline.contracts.vocabularies import QUALITY_GATE_IDS
        from pipeline.quality.pipeline import (
            run_quality_pipeline,
        )
        from pipeline.quality.registry import get_default_registry

        if arguments.gate_id not in QUALITY_GATE_IDS:
            print(f"Unknown gate ID: {arguments.gate_id}", file=sys.stderr)
            return 1

        # Load manifest
        manifest = QualityInputManifest.model_validate_json(
            arguments.manifest.read_text(encoding="utf-8")
        )

        # Load artifacts
        artifacts = {}
        supporting_artifacts = {}
        artifacts_dir = arguments.artifacts_dir
        for path in artifacts_dir.glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            artifact_id = data.get("artifact_id") or path.stem
            if artifact_id in manifest.target_artifact_ids:
                artifacts[artifact_id] = data
            elif artifact_id in manifest.supporting_artifact_ids:
                supporting_artifacts[artifact_id] = data
            else:
                # Try to infer from content
                if "schema_version" in data:
                    if "script" in data.get("schema_version", ""):
                        artifacts[artifact_id] = data
                    elif "evidence" in data.get(
                        "schema_version", ""
                    ) or "claim" in data.get("schema_version", ""):
                        supporting_artifacts[artifact_id] = data
                    else:
                        supporting_artifacts[artifact_id] = data

        # Get gate policy (would be from registry in real implementation)
        # For now, create a default policy for the gate
        registry = get_default_registry()
        gate_checks = registry.resolve_checks_for_gate(
            tuple(
                [
                    "script_schema_v1",
                    "claim_reference_integrity_v1",
                    "script_claim_evidence_v1",
                    "script_editorial_clarity_v1",
                ]
            )
        )

        # This is a simplified version - in reality would load from policy registry
        policy = QualityGatePolicy(
            schema_version="quality-gate-policy.v1",
            gate_id=arguments.gate_id,
            version="1.0",
            required_check_ids=[c.check_id for c in gate_checks],
            hard_failure_codes=["QUALITY.SCHEMA_INVALID", "QUALITY.UNSUPPORTED_CLAIM"],
            pass_thresholds={
                "claim_support": 0.8,
                "clarity": 0.8,
                "structure": 0.8,
                "tone": 0.8,
            },
            human_review_thresholds={
                "claim_support": 0.65,
                "clarity": 0.65,
                "structure": 0.65,
                "tone": 0.65,
            },
            max_regenerations=2,
            after_max_regenerations="HUMAN_REVIEW",
        )

        # Create database connection
        database = Database(arguments.database)

        # Create human review manager
        from pipeline.quality.human_review import HumanReviewManager

        human_review_manager = HumanReviewManager(database)

        # Run quality pipeline
        result = run_quality_pipeline(
            registry=registry,
            gate_policy=policy,
            manifest=manifest,
            artifacts=artifacts,
            supporting_artifacts=supporting_artifacts,
            database=database,
            human_review_manager=human_review_manager,
            run_id=manifest.manifest_id,  # Use manifest ID as run_id for human review
            stage_instance_id=(
                arguments.stage_instance_id
                if hasattr(arguments, "stage_instance_id")
                else None
            ),
            logical_item_key=(
                arguments.logical_item_key
                if hasattr(arguments, "logical_item_key")
                else None
            ),
            regeneration_count=arguments.regeneration_count,
            max_regenerations=policy.max_regenerations,
            after_max_regenerations=policy.after_max_regenerations,
        )

        # Output result
        output_data = {
            "gate_result": result.gate_result.model_dump(mode="json"),
            "evaluations": [e.model_dump(mode="json") for e in result.evaluations],
        }
        if result.repair_plan:
            output_data["repair_plan"] = result.repair_plan.model_dump(mode="json")
        if result.human_review:
            output_data["human_review"] = result.human_review.model_dump(mode="json")

        output_json = json.dumps(output_data, indent=2, sort_keys=True)

        if arguments.output:
            arguments.output.write_text(output_json, encoding="utf-8")
            print(f"Quality gate result written to {arguments.output}")
        else:
            print(output_json)

        # Exit with non-zero if gate failed
        if result.gate_result.decision.value in ("FAIL", "HUMAN_REVIEW"):
            return 1
        return 0

    except Exception as error:
        print(
            f"Quality evaluate failed: {type(error).__name__}: {error}", file=sys.stderr
        )
        import traceback

        traceback.print_exc()
        return 1


def _run_human_review_command(arguments: argparse.Namespace) -> int:
    if arguments.human_review_command is None:
        print("Usage: python -m pipeline human-review {list,show,decide} ...")
        return 0

    try:
        from pipeline.paths import default_database_path
        from pipeline.storage.database import Database
        from pipeline.storage.migrations import MigrationRunner

        database_path = arguments.database or default_database_path()
        database = Database(database_path)
        MigrationRunner(database).migrate()

        if arguments.human_review_command == "list":
            from pipeline.contracts.vocabularies import ReviewStatus
            from pipeline.quality.human_review import cli_human_review_list

            status = ReviewStatus(arguments.status) if arguments.status else None
            reviews = cli_human_review_list(
                database,
                run_id=arguments.run_id,
                status=status.value if status else None,
            )

            if not reviews:
                print("No human reviews found.")
                return 0

            for review in reviews:
                rid = review.review_id
                status = review.status.value
                run = review.run_id
                gate = review.gate_id
                print(f"{rid} [{status}] run={run} gate={gate}")
                print(f"  Artifacts: {', '.join(review.target_artifact_ids)}")
                print(f"  Reasons: {', '.join(review.reason_codes)}")
                print(f"  Action: {review.requested_action}")
                print(f"  Created: {review.created_at}")
                print()

            return 0

        if arguments.human_review_command == "show":
            from pipeline.quality.human_review import cli_human_review_show

            review = cli_human_review_show(database, arguments.review_id)
            print(f"Review ID: {review.review_id}")
            print(f"Status: {review.status.value}")
            print(f"Run ID: {review.run_id}")
            print(f"Stage Instance: {review.stage_instance_id}")
            print(f"Gate: {review.gate_id}")
            print(f"Target Artifacts: {', '.join(review.target_artifact_ids)}")
            print(f"Target Hashes: {review.target_hashes}")
            print(f"Reason Codes: {', '.join(review.reason_codes)}")
            print(f"Requested Action: {review.requested_action}")
            print(f"Created: {review.created_at}")
            print(f"Resolved: {review.resolved_at}")
            return 0

        if arguments.human_review_command == "decide":
            from pipeline.quality.human_review import cli_human_review_decide

            decision = cli_human_review_decide(
                database=database,
                review_id=arguments.review_id,
                decision=arguments.decision,
                reviewer=arguments.reviewer,
                comments=arguments.comments,
            )
            print(f"Decision recorded for review {arguments.review_id}:")
            print(f"  Decision: {decision.decision.value}")
            print(f"  Reviewer: {decision.reviewer}")
            print(f"  Comments: {decision.comments or '(none)'}")
            print(f"  Created: {decision.created_at}")
            return 0

        print(
            f"Unknown human-review action: {arguments.human_review_command}",
            file=sys.stderr,
        )
        return 2

    except Exception as error:
        print(
            f"Human review command failed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        import traceback

        traceback.print_exc()
        return 1


def _run_report_command(arguments: argparse.Namespace) -> int:
    try:
        database = _migrated_database(arguments.database)
        report = generate_validation_report(database, arguments.run_id)

        markdown = report.to_markdown()
        if arguments.output:
            arguments.output.parent.mkdir(parents=True, exist_ok=True)
            arguments.output.write_text(markdown, encoding="utf-8")
            print(f"Validation report written to {arguments.output}")
        else:
            print(markdown)
        return 0
    except Exception as error:
        print(
            f"Report generation failed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        import traceback

        traceback.print_exc()
        return 1


def _run_artifact_command(arguments: argparse.Namespace) -> int:
    if arguments.artifact_command is None:
        print(
            "Usage: python -m pipeline artifact graph "
            "--run-id RUN_ID [--format text|dot]"
        )
        return 0
    if arguments.artifact_command != "graph":
        print(f"Unknown artifact action: {arguments.artifact_command}", file=sys.stderr)
        return 2
    try:
        database = _migrated_database(arguments.database)
        with database.transaction() as conn:
            from pipeline.storage.repositories.artifacts import (
                ArtifactDependencyRepository,
                ArtifactRepository,
            )
            from pipeline.storage.repositories.execution import WorkflowRunRepository

            # Verify run exists
            run_repo = WorkflowRunRepository(conn)
            try:
                run_repo.get(arguments.run_id)
            except Exception:
                print(f"Run {arguments.run_id} not found", file=sys.stderr)
                return 1

            artifact_repo = ArtifactRepository(conn)
            artifacts = artifact_repo.list_for_run(arguments.run_id)

            dep_repo = ArtifactDependencyRepository(conn)
            dependencies = []
            for artifact in artifacts:
                deps = dep_repo.list_for_parent(artifact.artifact_id)
                dependencies.extend(deps)

        if arguments.format == "dot":
            _print_artifact_graph_dot(artifacts, dependencies)
        else:
            _print_artifact_graph_text(artifacts, dependencies)
        return 0
    except Exception as error:
        print(
            f"Artifact graph failed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        import traceback

        traceback.print_exc()
        return 1


def _print_artifact_graph_text(artifacts: list, dependencies: list) -> None:
    print(
        "Artifact Graph for "
        f"{len(artifacts)} artifacts, {len(dependencies)} dependencies"
    )
    print()
    # Group by logical slot
    by_slot: dict[str, list] = {}
    for artifact in artifacts:
        by_slot.setdefault(artifact.logical_slot, []).append(artifact)

    for slot, slot_artifacts in sorted(by_slot.items()):
        print(f"Slot: {slot}")
        for artifact in sorted(slot_artifacts, key=lambda a: a.version):
            sha_short = artifact.sha256[:16]
            print(
                f"  v{artifact.version} {artifact.artifact_id} "
                f"[{artifact.artifact_type}] {sha_short}... "
                f"({artifact.state.value})"
            )
        print()

    print("Dependencies:")
    for dep in dependencies:
        parent = dep.parent_artifact_id
        child = dep.child_artifact_id
        dtype = dep.dependency_type
        print(f"  {parent} --({dtype})--> {child}")


def _print_artifact_graph_dot(artifacts: list, dependencies: list) -> None:
    print("digraph artifact_graph {")
    print("  rankdir=LR;")
    print("  node [shape=box];")
    for artifact in artifacts:
        label = (
            f"{artifact.logical_slot}\\nv{artifact.version}\\n"
            f"{artifact.artifact_id[:12]}"
        )
        color = "lightgreen" if artifact.state.value == "ACCEPTED" else "lightyellow"
        print(
            f'  "{artifact.artifact_id}" [label="{label}", '
            f"style=filled, fillcolor={color}];"
        )
    for dep in dependencies:
        print(
            f'  "{dep.parent_artifact_id}" -> "{dep.child_artifact_id}" '
            f'[label="{dep.dependency_type}"];'
        )
    print("}")


def _run_run_command(arguments: argparse.Namespace) -> int:
    if arguments.run_command is None:
        print("Usage: python -m pipeline run status --run-id RUN_ID")
        return 0
    if arguments.run_command != "status":
        print(f"Unknown run action: {arguments.run_command}", file=sys.stderr)
        return 2
    try:
        database = _migrated_database(arguments.database)
        with database.transaction() as conn:
            from pipeline.storage.repositories.artifacts import ArtifactRepository
            from pipeline.storage.repositories.execution import (
                StageAttemptRepository,
                StageInstanceRepository,
                WorkflowRunRepository,
            )

            run_repo = WorkflowRunRepository(conn)
            run = run_repo.get(arguments.run_id)

            si_repo = StageInstanceRepository(conn)
            stage_instances = si_repo.list_for_run(arguments.run_id)

            sa_repo = StageAttemptRepository(conn)
            all_attempts = []
            for si in stage_instances:
                attempts = sa_repo.list_for_stage_instance(si.stage_instance_id)
                all_attempts.extend(attempts)

            artifact_repo = ArtifactRepository(conn)
            artifacts = artifact_repo.list_for_run(arguments.run_id)

        print(f"Run: {run.run_id}")
        print(f"  Key: {run.run_key}")
        print(f"  Workflow: {run.workflow_id} v{run.workflow_version}")
        print(f"  Status: {run.status.value}")
        config_short = run.effective_config_hash[:16]
        print(f"  Config: {run.effective_config_id} ({config_short}...)")
        print(f"  Package: {run.content_package_id}")
        print(f"  Created: {run.created_at.isoformat()}")
        print(f"  Updated: {run.updated_at.isoformat()}")
        print()
        print(f"Stage Instances ({len(stage_instances)}):")
        for si in stage_instances:
            attempts = [
                a for a in all_attempts if a.stage_instance_id == si.stage_instance_id
            ]
            latest = max(attempts, key=lambda a: a.attempt_number) if attempts else None
            print(f"  {si.stage_instance_id} [{si.node_id}] item={si.logical_item_key}")
            print(
                f"    Exec: {si.execution_status.value} "
                f"| Accept: {si.acceptance_status.value}"
            )
            print(
                f"    Gate: {si.quality_gate_id or 'N/A'} "
                f"| Attempt: {si.active_attempt_id or 'N/A'}"
            )
            if latest:
                print(
                    f"    Latest Attempt: {latest.attempt_id} "
                    f"#{latest.attempt_number} [{latest.status.value}]"
                )
        print()
        print(f"Total Attempts: {len(all_attempts)}")
        print(f"Total Artifacts: {len(artifacts)}")
        return 0
    except Exception as error:
        print(
            f"Run status failed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        import traceback

        traceback.print_exc()
        return 1


def _run_job_command(arguments: argparse.Namespace) -> int:
    if arguments.job_command is None:
        print("Usage: python -m pipeline job dispatch --once [--database PATH]")
        return 0
    if arguments.job_command != "dispatch":
        print(f"Unknown job action: {arguments.job_command}", file=sys.stderr)
        return 2
    try:
        from pipeline.execution.dispatcher import JobDispatcher

        database = _migrated_database(arguments.database)
        dispatcher = JobDispatcher(database)
        result = dispatcher.dispatch_once()
        print(
            f"Job dispatch: claimed={result.claimed} enqueued={result.enqueued} "
            f"skipped={result.skipped} errors={result.errors}."
        )
        print(f"Database: {database.path}")
        return 0
    except Exception as error:
        print(
            f"Job dispatch failed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        import traceback

        traceback.print_exc()
        return 1


def _run_review_command(arguments: argparse.Namespace) -> int:
    # Delegate to human-review command handlers
    # Create a mock arguments namespace for human-review
    import argparse

    hr_args = argparse.Namespace()
    hr_args.database = arguments.database
    hr_args.human_review_command = arguments.review_command
    hr_args.run_id = getattr(arguments, "run_id", None)
    hr_args.status = getattr(arguments, "status", None)
    hr_args.review_id = getattr(arguments, "review_id", None)
    hr_args.decision = getattr(arguments, "decision", None)
    hr_args.reviewer = getattr(arguments, "reviewer", None)
    hr_args.comments = getattr(arguments, "comments", None)
    return _run_human_review_command(hr_args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
