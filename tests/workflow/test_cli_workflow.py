from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_WORKFLOW = REPOSITORY_ROOT / "workflows" / "explainer_validation_v1.yaml"


def _run_cli(
    arguments: list[str],
    *,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pipeline", *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env=dict(os.environ),
        cwd=REPOSITORY_ROOT,
        input=stdin,
    )


def test_workflow_help_lists_actions() -> None:
    completed = _run_cli(["workflow", "--help"])

    assert completed.returncode == 0
    assert "validate" in completed.stdout
    assert "readiness" in completed.stdout


def test_validate_canonical_workflow() -> None:
    completed = _run_cli(["workflow", "validate", str(CANONICAL_WORKFLOW)])

    assert completed.returncode == 0, completed.stderr
    assert "explainer_validation_v1" in completed.stdout
    assert "is valid" in completed.stdout
    assert "13 node(s)" in completed.stdout


def test_validate_rejects_invalid_definition(tmp_path: Path) -> None:
    invalid = tmp_path / "workflow.yaml"
    invalid.write_text("schema_version: workflow-definition.v1\n", encoding="utf-8")

    completed = _run_cli(["workflow", "validate", str(invalid)])

    assert completed.returncode == 1
    assert "Invalid workflow" in completed.stderr
    assert str(invalid) in completed.stderr


def test_validate_rejects_unsafe_yaml(tmp_path: Path) -> None:
    invalid = tmp_path / "workflow.yaml"
    invalid.write_text("!!python/object:os.system {}\n", encoding="utf-8")

    completed = _run_cli(["workflow", "validate", str(invalid)])

    assert completed.returncode == 1
    assert "invalid YAML" in completed.stderr


def test_readiness_without_context_plans_root() -> None:
    completed = _run_cli(["workflow", "readiness", str(CANONICAL_WORKFLOW)])

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["run_id"] == "run_cli"
    assert payload["workflow_id"] == "explainer_validation_v1"
    assert payload["next_status"] == "RUNNING"
    assert payload["ready_node_ids"] == ["intake"]
    assert [item["node_id"] for item in payload["planned_items"]] == ["intake"]
    assert payload["terminal_node_ids"] == ["human_approval"]


def test_readiness_accepts_json_context_file(tmp_path: Path) -> None:
    context = tmp_path / "context.json"
    context.write_text(
        json.dumps(
            {
                "run_status": "RUNNING",
                "stage_instances": [
                    {
                        "schema_version": "stage-instance.v1",
                        "stage_instance_id": "stage_intake_default",
                        "run_id": "run_cli",
                        "node_id": "intake",
                        "logical_item_key": "default",
                        "execution_status": "SUCCEEDED",
                        "acceptance_status": "NOT_REQUIRED",
                        "accepted_output_artifact_ids": ["artifact_intake"],
                        "created_at": "2026-01-01T00:00:00Z",
                        "updated_at": "2026-01-01T00:00:00Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    completed = _run_cli(
        [
            "workflow",
            "readiness",
            str(CANONICAL_WORKFLOW),
            "--context",
            str(context),
        ]
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["ready_node_ids"] == ["idea"]
    assert [item["node_id"] for item in payload["planned_items"]] == ["idea"]
    assert payload["accepted_node_ids"] == ["intake"]


def test_readiness_accepts_stdin_context() -> None:
    completed = _run_cli(
        ["workflow", "readiness", str(CANONICAL_WORKFLOW), "--context", "-"],
        stdin=json.dumps({"run_status": "COMPLETED"}),
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["next_status"] == "COMPLETED"
    assert payload["ready_node_ids"] == []
    assert payload["planned_items"] == []


def test_readiness_rejects_unknown_context_key(tmp_path: Path) -> None:
    context = tmp_path / "context.json"
    context.write_text(json.dumps({"unexpected": True}), encoding="utf-8")

    completed = _run_cli(
        [
            "workflow",
            "readiness",
            str(CANONICAL_WORKFLOW),
            "--context",
            str(context),
        ]
    )

    assert completed.returncode == 1
    assert "unknown readiness context key" in completed.stderr
