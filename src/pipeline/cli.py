"""Command-line interface for the pipeline bootstrap shell."""

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


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
