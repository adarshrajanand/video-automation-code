from __future__ import annotations

import builtins
import io
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from pipeline.workflow import evaluate_readiness

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_evaluate_readiness_is_deterministic(wf) -> None:
    workflow = wf.chain(3)
    run = wf.run(workflow)
    root = wf.accepted(run, "root")
    first = wf.accepted(run, "node_1")
    context = wf.context(workflow, run, stage_instances=(first, root))

    first_result = evaluate_readiness(context)
    second_result = evaluate_readiness(context)

    assert first_result.model_dump(mode="json") == second_result.model_dump(mode="json")
    assert first_result.model_dump_json() == second_result.model_dump_json()


def test_evaluate_readiness_does_not_mutate_context(wf) -> None:
    workflow = wf.chain(2)
    run = wf.run(workflow)
    root = wf.accepted(run, "root")
    context = wf.context(workflow, run, stage_instances=(root,))
    before = context.model_dump(mode="json")

    evaluate_readiness(context)

    assert context.model_dump(mode="json") == before


def test_evaluate_readiness_is_order_independent(wf) -> None:
    workflow = wf.chain(3)
    run = wf.run(workflow)
    root = wf.accepted(run, "root")
    first = wf.accepted(run, "node_1")
    context = wf.context(workflow, run, stage_instances=(root, first))
    reversed_context = wf.context(workflow, run, stage_instances=(first, root))

    assert evaluate_readiness(context).model_dump(mode="json") == evaluate_readiness(
        reversed_context
    ).model_dump(mode="json")


def test_evaluate_readiness_performs_no_io(monkeypatch, wf) -> None:
    workflow = wf.root_workflow()
    run = wf.run(workflow)
    context = wf.context(workflow, run)

    def refuse(*args, **kwargs):
        raise AssertionError("readiness evaluation must not touch the filesystem")

    def refuse_connect(*args, **kwargs):
        raise AssertionError("readiness evaluation must not open a database")

    monkeypatch.setattr(builtins, "open", refuse)
    monkeypatch.setattr(io, "open", refuse)
    monkeypatch.setattr(sqlite3, "connect", refuse_connect)

    result = evaluate_readiness(context)

    assert result.run_id == run.run_id
    assert json.loads(result.model_dump_json())["run_id"] == run.run_id


def test_importing_workflow_does_not_import_storage_or_cli() -> None:
    script = (
        "import sys\n"
        "import pipeline.workflow\n"
        "forbidden = {'pipeline.storage', 'pipeline.cli', 'sqlite3'}\n"
        "loaded = sorted(forbidden & set(sys.modules))\n"
        "print(','.join(loaded))\n"
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        cwd=REPOSITORY_ROOT,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == ""


def test_evaluate_readiness_returns_frozen_models(wf) -> None:
    workflow = wf.root_workflow()
    run = wf.run(workflow)
    result = evaluate_readiness(wf.context(workflow, run))

    with pytest.raises(ValueError):
        result.next_status = "COMPLETED"  # type: ignore[misc]
