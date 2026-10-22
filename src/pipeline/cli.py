"""Command-line interface for the pipeline bootstrap shell."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from pipeline import __version__
from pipeline.setup_checks import CheckStatus, SetupReport, collect_checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline",
        description=(
            "Local-first AI video automation pipeline (FV-01 bootstrap shell)."
        ),
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
    parser.error(f"unknown command: {arguments.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
