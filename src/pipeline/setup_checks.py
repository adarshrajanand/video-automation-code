"""Fail-closed local setup diagnostics for the pipeline shell.

The checks in this module are intentionally read-only with respect to workflow
state. They inspect the Python environment, local toolchain, writable runtime
paths, and SQLite capability, and create only the empty ``PIPELINE_HOME``
directory skeleton. No provider SDK, credential, network call, or workflow
record is involved.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pipeline.paths import (
    PIPELINE_DIRECTORIES,
    PIPELINE_HOME_ENV,
    resolve_pipeline_home,
)

DISTRIBUTION_NAME = "video-automation-pipeline"
REQUIRED_PYTHON = (3, 12)
MINIMUM_NODE = (20, 0, 0)
MINIMUM_NPM = (9, 0, 0)
VERSION_TIMEOUT_SECONDS = 5.0

_VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)\.(\d+)")


class CheckStatus(StrEnum):
    """Stable status values used by text and JSON output."""

    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One setup check and its actionable outcome."""

    check_id: str
    title: str
    required: bool
    status: CheckStatus
    detail: str
    remediation: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.check_id,
            "title": self.title,
            "required": self.required,
            "status": self.status.value,
            "detail": self.detail,
            "remediation": self.remediation,
        }


@dataclass(frozen=True, slots=True)
class SetupReport:
    """Aggregate result for one ``check-setup`` invocation."""

    pipeline_home: Path
    checks: tuple[CheckResult, ...]

    @property
    def passed_count(self) -> int:
        return sum(check.status is CheckStatus.PASS for check in self.checks)

    @property
    def warning_count(self) -> int:
        return sum(check.status is CheckStatus.WARN for check in self.checks)

    @property
    def failed_checks(self) -> tuple[CheckResult, ...]:
        return tuple(check for check in self.checks if check.status is CheckStatus.FAIL)

    @property
    def required_failed(self) -> tuple[CheckResult, ...]:
        return tuple(
            check
            for check in self.checks
            if check.required and check.status is CheckStatus.FAIL
        )

    @property
    def ok(self) -> bool:
        """Return true only when every required check passed."""

        return not self.required_failed

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "pipeline_home": str(self.pipeline_home),
            "summary": {
                "checks": len(self.checks),
                "passed": self.passed_count,
                "warnings": self.warning_count,
                "failed": len(self.failed_checks),
                "required_failed": len(self.required_failed),
            },
            "checks": [check.to_dict() for check in self.checks],
        }


class SetupChecker:
    """Collect every setup check without failing fast.

    Collecting all results is deliberate: a missing media tool must not hide a
    broken runtime path or an unavailable optional renderer capability.
    """

    def __init__(
        self,
        *,
        environ: Mapping[str, str] | None = None,
        project_root: Path | None = None,
    ) -> None:
        self.environ = dict(os.environ if environ is None else environ)
        root = (
            Path(__file__).resolve().parents[2]
            if project_root is None
            else project_root
        )
        self.project_root = root.expanduser().resolve()
        self.pipeline_home = resolve_pipeline_home(self.environ)

    def run(self) -> SetupReport:
        checks = (
            self._check_python(),
            self._check_package(),
            self._check_node(),
            self._check_npm(),
            self._check_remotion(),
            self._check_media_tool(
                check_id="ffmpeg",
                title="FFmpeg",
                variable="PIPELINE_FFMPEG_BINARY",
                default_command="ffmpeg",
            ),
            self._check_media_tool(
                check_id="ffprobe",
                title="ffprobe",
                variable="PIPELINE_FFPROBE_BINARY",
                default_command="ffprobe",
            ),
            self._check_pipeline_home(),
            self._check_pipeline_layout(),
            self._check_sqlite(),
        )
        return SetupReport(pipeline_home=self.pipeline_home, checks=checks)

    def _check_python(self) -> CheckResult:
        actual = (sys.version_info.major, sys.version_info.minor)
        interpreter = platform.python_implementation()
        version = platform.python_version()
        if actual != REQUIRED_PYTHON:
            return CheckResult(
                check_id="python-version",
                title="Python interpreter",
                required=True,
                status=CheckStatus.FAIL,
                detail=(
                    f"{interpreter} {version} at {sys.executable}; "
                    "the project requires Python 3.12.x."
                ),
                remediation=(
                    "Install Python 3.12 and run 'uv sync' so the project uses "
                    "the supported interpreter."
                ),
            )
        return CheckResult(
            check_id="python-version",
            title="Python interpreter",
            required=True,
            status=CheckStatus.PASS,
            detail=(
                f"{interpreter} {version} at {sys.executable}; "
                "the project requires Python 3.12.x."
            ),
        )

    def _check_package(self) -> CheckResult:
        try:
            package_version = importlib.metadata.version(DISTRIBUTION_NAME)
        except importlib.metadata.PackageNotFoundError:
            return CheckResult(
                check_id="pipeline-package",
                title="Pipeline package",
                required=True,
                status=CheckStatus.FAIL,
                detail=(
                    f"Distribution {DISTRIBUTION_NAME!r} is not installed in "
                    f"{sys.executable}."
                ),
                remediation="Run 'uv sync' from the repository root, then retry.",
            )
        module_path = Path(__file__).resolve().parent
        return CheckResult(
            check_id="pipeline-package",
            title="Pipeline package",
            required=True,
            status=CheckStatus.PASS,
            detail=(
                f"{DISTRIBUTION_NAME} {package_version} is installed; "
                f"pipeline module at {module_path}."
            ),
        )

    def _check_node(self) -> CheckResult:
        node_path, requested = self._resolve_tool("PIPELINE_NODE_BINARY", "node")
        remediation = (
            "Install Node.js 20 or newer (for example with nvm), ensure 'node' "
            "is on PATH, or set PIPELINE_NODE_BINARY."
        )
        if node_path is None:
            return CheckResult(
                check_id="node",
                title="Node.js runtime",
                required=True,
                status=CheckStatus.FAIL,
                detail=f"{requested!r} was not found or is not executable.",
                remediation=remediation,
            )
        output, error = self._run_version(node_path, "--version")
        parsed = _parse_version(output or "")
        if error is not None or output is None:
            return CheckResult(
                check_id="node",
                title="Node.js runtime",
                required=True,
                status=CheckStatus.FAIL,
                detail=f"Could not read the Node.js version from {node_path}: {error}",
                remediation=remediation,
            )
        if parsed is None:
            return CheckResult(
                check_id="node",
                title="Node.js runtime",
                required=True,
                status=CheckStatus.FAIL,
                detail=(
                    f"Unexpected Node.js version output {output!r} from {node_path}."
                ),
                remediation=remediation,
            )
        if parsed < MINIMUM_NODE:
            return CheckResult(
                check_id="node",
                title="Node.js runtime",
                required=True,
                status=CheckStatus.FAIL,
                detail=(
                    f"Node.js {output} at {node_path}; minimum supported version "
                    "is 20.0.0."
                ),
                remediation=remediation,
            )
        return CheckResult(
            check_id="node",
            title="Node.js runtime",
            required=True,
            status=CheckStatus.PASS,
            detail=(
                f"Node.js {output} at {node_path}; minimum supported version is 20.0.0."
            ),
        )

    def _check_npm(self) -> CheckResult:
        npm_path, requested = self._resolve_tool("PIPELINE_NPM_BINARY", "npm")
        remediation = (
            "Install npm 9 or newer with Node.js, ensure 'npm' is on PATH, or "
            "set PIPELINE_NPM_BINARY."
        )
        if npm_path is None:
            return CheckResult(
                check_id="npm",
                title="npm package manager",
                required=True,
                status=CheckStatus.FAIL,
                detail=f"{requested!r} was not found or is not executable.",
                remediation=remediation,
            )
        output, error = self._run_version(npm_path, "--version")
        parsed = _parse_version(output or "")
        if error is not None or output is None:
            return CheckResult(
                check_id="npm",
                title="npm package manager",
                required=True,
                status=CheckStatus.FAIL,
                detail=f"Could not read the npm version from {npm_path}: {error}",
                remediation=remediation,
            )
        if parsed is None:
            return CheckResult(
                check_id="npm",
                title="npm package manager",
                required=True,
                status=CheckStatus.FAIL,
                detail=f"Unexpected npm version output {output!r} from {npm_path}.",
                remediation=remediation,
            )
        if parsed < MINIMUM_NPM:
            return CheckResult(
                check_id="npm",
                title="npm package manager",
                required=True,
                status=CheckStatus.FAIL,
                detail=(
                    f"npm {output} at {npm_path}; minimum supported version is 9.0.0."
                ),
                remediation=remediation,
            )
        return CheckResult(
            check_id="npm",
            title="npm package manager",
            required=True,
            status=CheckStatus.PASS,
            detail=f"npm {output} at {npm_path}; minimum supported version is 9.0.0.",
        )

    def _check_remotion(self) -> CheckResult:
        relative_manifest = Path("packages") / "renderer" / "package.json"
        manifest = self.project_root / relative_manifest
        if not manifest.is_file():
            return CheckResult(
                check_id="remotion-renderer",
                title="Remotion renderer package",
                required=False,
                status=CheckStatus.WARN,
                detail=(
                    f"No renderer manifest at {manifest}; Remotion integration is "
                    "deferred beyond FV-01. Node.js and npm are still checked so "
                    "the renderer package can be added later."
                ),
            )
        try:
            manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            return CheckResult(
                check_id="remotion-renderer",
                title="Remotion renderer package",
                required=False,
                status=CheckStatus.WARN,
                detail=f"Could not read {manifest}: {exc}",
            )
        if not isinstance(manifest_data, dict):
            return CheckResult(
                check_id="remotion-renderer",
                title="Remotion renderer package",
                required=False,
                status=CheckStatus.WARN,
                detail=f"{manifest} does not contain a JSON object.",
            )
        remotion_spec = _find_dependency(manifest_data, "remotion")
        if remotion_spec is None:
            return CheckResult(
                check_id="remotion-renderer",
                title="Remotion renderer package",
                required=False,
                status=CheckStatus.WARN,
                detail=f"{manifest} does not declare a 'remotion' dependency.",
            )
        return CheckResult(
            check_id="remotion-renderer",
            title="Remotion renderer package",
            required=False,
            status=CheckStatus.PASS,
            detail=f"Remotion {remotion_spec} is declared in {manifest}.",
        )

    def _check_media_tool(
        self,
        *,
        check_id: str,
        title: str,
        variable: str,
        default_command: str,
    ) -> CheckResult:
        tool_path, requested = self._resolve_tool(variable, default_command)
        remediation = (
            f"Install FFmpeg and ensure {requested!r} is on PATH, or set {variable}."
        )
        if tool_path is None:
            return CheckResult(
                check_id=check_id,
                title=title,
                required=True,
                status=CheckStatus.FAIL,
                detail=f"{requested!r} was not found or is not executable.",
                remediation=remediation,
            )
        output, error = self._run_version(tool_path, "-version")
        if error is not None or output is None:
            return CheckResult(
                check_id=check_id,
                title=title,
                required=True,
                status=CheckStatus.FAIL,
                detail=f"Could not read the {title} version from {tool_path}: {error}",
                remediation=remediation,
            )
        return CheckResult(
            check_id=check_id,
            title=title,
            required=True,
            status=CheckStatus.PASS,
            detail=f"{title} at {tool_path}: {output}",
        )

    def _check_pipeline_home(self) -> CheckResult:
        try:
            self.pipeline_home.mkdir(parents=True, exist_ok=True)
            if not self.pipeline_home.is_dir():
                raise NotADirectoryError(f"{self.pipeline_home} is not a directory")
            _probe_directory(self.pipeline_home)
        except OSError as exc:
            return CheckResult(
                check_id="pipeline-home",
                title="PIPELINE_HOME writability",
                required=True,
                status=CheckStatus.FAIL,
                detail=f"Could not create or write {self.pipeline_home}: {exc}",
                remediation=(
                    f"Set {PIPELINE_HOME_ENV} to a writable local directory or fix "
                    "its permissions, then retry."
                ),
            )
        return CheckResult(
            check_id="pipeline-home",
            title="PIPELINE_HOME writability",
            required=True,
            status=CheckStatus.PASS,
            detail=f"{self.pipeline_home} exists and is writable.",
        )

    def _check_pipeline_layout(self) -> CheckResult:
        errors: list[str] = []
        for name in PIPELINE_DIRECTORIES:
            directory = self.pipeline_home / name
            try:
                directory.mkdir(parents=True, exist_ok=True)
                if not directory.is_dir():
                    raise NotADirectoryError(f"{directory} is not a directory")
                _probe_directory(directory)
            except OSError as exc:
                errors.append(f"{name}: {exc}")
        if errors:
            return CheckResult(
                check_id="pipeline-home-layout",
                title="PIPELINE_HOME layout",
                required=True,
                status=CheckStatus.FAIL,
                detail="; ".join(errors),
                remediation=(
                    f"Fix permissions under {self.pipeline_home} or set "
                    f"{PIPELINE_HOME_ENV} to a writable local directory."
                ),
            )
        return CheckResult(
            check_id="pipeline-home-layout",
            title="PIPELINE_HOME layout",
            required=True,
            status=CheckStatus.PASS,
            detail=(
                "Verified writable directories: "
                + ", ".join(PIPELINE_DIRECTORIES)
                + "."
            ),
        )

    def _check_sqlite(self) -> CheckResult:
        try:
            import sqlite3
        except ImportError as exc:
            return CheckResult(
                check_id="sqlite",
                title="SQLite capability",
                required=True,
                status=CheckStatus.FAIL,
                detail=f"The Python sqlite3 module is unavailable: {exc}",
                remediation=(
                    "Use a CPython 3.12 build with SQLite support and rerun the check."
                ),
            )

        try:
            with tempfile.TemporaryDirectory(prefix="pipeline-sqlite-") as temp_dir:
                database_path = Path(temp_dir) / "capability.sqlite3"
                connection = sqlite3.connect(database_path, isolation_level=None)
                try:
                    connection.execute("PRAGMA foreign_keys = ON")
                    foreign_keys_enabled = (
                        connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
                    )
                    connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
                    connection.execute(
                        "CREATE TABLE child ("
                        "id INTEGER PRIMARY KEY, "
                        "parent_id INTEGER NOT NULL REFERENCES parent(id)"
                        ")"
                    )
                    connection.execute("CREATE TABLE tx_probe (value TEXT)")

                    foreign_key_enforced = False
                    try:
                        connection.execute(
                            "INSERT INTO child (id, parent_id) VALUES (1, 999)"
                        )
                    except sqlite3.IntegrityError:
                        foreign_key_enforced = True

                    connection.execute("BEGIN")
                    connection.execute(
                        "INSERT INTO tx_probe (value) VALUES ('rollback-probe')"
                    )
                    connection.execute("ROLLBACK")
                    rolled_back = (
                        connection.execute("SELECT COUNT(*) FROM tx_probe").fetchone()[
                            0
                        ]
                        == 0
                    )
                    sqlite_version = sqlite3.sqlite_version
                finally:
                    connection.close()
        except (OSError, sqlite3.Error) as exc:
            return CheckResult(
                check_id="sqlite",
                title="SQLite capability",
                required=True,
                status=CheckStatus.FAIL,
                detail=f"SQLite capability check failed: {type(exc).__name__}: {exc}",
                remediation=(
                    "Ensure Python has working SQLite support and the system temporary "
                    "directory is writable."
                ),
            )

        if not foreign_keys_enabled:
            return CheckResult(
                check_id="sqlite",
                title="SQLite capability",
                required=True,
                status=CheckStatus.FAIL,
                detail="SQLite did not enable foreign-key enforcement.",
                remediation="Check the Python SQLite build and rerun the check.",
            )
        if not foreign_key_enforced:
            return CheckResult(
                check_id="sqlite",
                title="SQLite capability",
                required=True,
                status=CheckStatus.FAIL,
                detail="SQLite accepted a row that violated a foreign-key constraint.",
                remediation="Check the Python SQLite build and rerun the check.",
            )
        if not rolled_back:
            return CheckResult(
                check_id="sqlite",
                title="SQLite capability",
                required=True,
                status=CheckStatus.FAIL,
                detail="SQLite did not roll back a transaction correctly.",
                remediation="Check the Python SQLite build and rerun the check.",
            )
        return CheckResult(
            check_id="sqlite",
            title="SQLite capability",
            required=True,
            status=CheckStatus.PASS,
            detail=(
                f"SQLite {sqlite_version}; foreign-key enforcement and transaction "
                "rollback verified."
            ),
        )

    def _resolve_tool(
        self, variable: str, default_command: str
    ) -> tuple[Path | None, str]:
        requested = self.environ.get(variable, "").strip() or default_command
        if os.sep in requested or (os.altsep is not None and os.altsep in requested):
            candidate = Path(requested).expanduser()
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate.resolve(), requested
            return None, requested

        path_value = self.environ.get("PATH") or os.defpath
        located = shutil.which(requested, path=path_value)
        if located is None:
            return None, requested
        return Path(located), requested

    def _run_version(self, tool: Path, flag: str) -> tuple[str | None, str | None]:
        try:
            completed = subprocess.run(
                [str(tool), flag],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=VERSION_TIMEOUT_SECONDS,
                check=False,
                env=self.environ,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, f"{type(exc).__name__}: {exc}"

        if completed.returncode != 0:
            detail = (
                _first_nonempty_line(completed.stderr)
                or _first_nonempty_line(completed.stdout)
                or "no diagnostic output"
            )
            return None, f"exit status {completed.returncode}: {detail}"

        output = _first_nonempty_line(completed.stdout) or _first_nonempty_line(
            completed.stderr
        )
        if output is None:
            return None, "command returned no version text"
        return output, None


def collect_checks(
    *,
    environ: Mapping[str, str] | None = None,
    project_root: Path | None = None,
) -> SetupReport:
    """Run the complete setup check suite."""

    return SetupChecker(environ=environ, project_root=project_root).run()


def _parse_version(text: str) -> tuple[int, int, int] | None:
    match = _VERSION_PATTERN.search(text)
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _first_nonempty_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _find_dependency(manifest: dict[str, object], name: str) -> object | None:
    for section_name in ("dependencies", "devDependencies", "peerDependencies"):
        section = manifest.get(section_name)
        if isinstance(section, dict) and name in section:
            return section[name]
    return None


def _probe_directory(directory: Path) -> None:
    """Create, write, fsync, and remove a probe file in ``directory``."""

    file_descriptor = -1
    probe_path: str | None = None
    try:
        file_descriptor, probe_path = tempfile.mkstemp(
            prefix=".pipeline-setup-", dir=directory
        )
        os.write(file_descriptor, b"pipeline setup probe\n")
        os.fsync(file_descriptor)
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        if probe_path is not None:
            Path(probe_path).unlink(missing_ok=True)
