from __future__ import annotations

from pipeline.contracts.vocabularies import (
    AcceptanceStatus,
    GateDecision,
    ReviewStatus,
    RunStatus,
    StageExecutionStatus,
)
from pipeline.workflow import ReadinessReason, evaluate_readiness


def test_running_while_work_remains(wf) -> None:
    workflow = wf.chain(2)
    run = wf.run(workflow)
    root = wf.accepted(run, "root")

    result = evaluate_readiness(wf.context(workflow, run, stage_instances=(root,)))

    assert result.next_status is RunStatus.RUNNING


def test_completed_when_terminal_node_is_accepted(wf) -> None:
    workflow = wf.chain(2)
    run = wf.run(workflow)
    root = wf.accepted(run, "root")
    last = wf.accepted(run, "node_1")

    result = evaluate_readiness(wf.context(workflow, run, stage_instances=(root, last)))

    assert result.next_status is RunStatus.COMPLETED
    assert result.ready_node_ids == ()
    assert set(result.accepted_node_ids) == {"root", "node_1"}


def test_terminal_failure_marks_run_failed(wf) -> None:
    workflow = wf.root_workflow()
    run = wf.run(workflow)
    failed = wf.instance(
        run,
        "root",
        execution=StageExecutionStatus.FAILED,
        acceptance=AcceptanceStatus.FAILED,
    )

    result = evaluate_readiness(wf.context(workflow, run, stage_instances=(failed,)))

    assert result.next_status is RunStatus.FAILED
    assert ReadinessReason.TERMINAL_FAILURE in {block.code for block in result.blocked}


def test_explicit_recovery_keeps_run_running(wf) -> None:
    workflow = wf.root_workflow()
    run = wf.run(workflow)
    failed = wf.instance(
        run,
        "root",
        execution=StageExecutionStatus.FAILED,
        acceptance=AcceptanceStatus.FAILED,
    )

    result = evaluate_readiness(
        wf.context(
            workflow,
            run,
            stage_instances=(failed,),
            recoverable_stage_instance_ids={failed.stage_instance_id},
        )
    )

    assert result.next_status is RunStatus.RUNNING
    assert ReadinessReason.RECOVERY_PENDING in {block.code for block in result.blocked}


def test_gate_fail_marks_run_failed(wf) -> None:
    workflow = wf.workflow(
        [
            wf.node("root", stage_name="manual_topic"),
            wf.node("gated", depends_on=["root"], gate="research_gate_v1"),
        ]
    )
    run = wf.run(workflow)
    root = wf.accepted(run, "root")
    gated = wf.instance(
        run,
        "gated",
        acceptance=AcceptanceStatus.PASSED,
        gate="research_gate_v1",
        outputs=("artifact_gated",),
    )
    gate_fail = wf.gate_result(gated, "research_gate_v1", decision=GateDecision.FAIL)

    result = evaluate_readiness(
        wf.context(
            workflow,
            run,
            stage_instances=(root, gated),
            quality_gate_results=(gate_fail,),
        )
    )

    assert result.next_status is RunStatus.FAILED
    assert ReadinessReason.GATE_FAILED in {block.code for block in result.blocked}


def test_retry_wait_status(wf) -> None:
    workflow = wf.root_workflow()
    run = wf.run(workflow)
    retrying = wf.instance(
        run,
        "root",
        execution=StageExecutionStatus.WAITING_RETRY,
        acceptance=AcceptanceStatus.NOT_REQUIRED,
    )

    result = evaluate_readiness(wf.context(workflow, run, stage_instances=(retrying,)))

    assert result.next_status is RunStatus.WAITING_RETRY
    assert ReadinessReason.RETRY_WAIT in {block.code for block in result.blocked}


def test_unknown_outcome_is_a_retryable_wait(wf) -> None:
    workflow = wf.root_workflow()
    run = wf.run(workflow)
    unknown = wf.instance(
        run,
        "root",
        execution=StageExecutionStatus.UNKNOWN,
        acceptance=AcceptanceStatus.NOT_REQUIRED,
    )

    result = evaluate_readiness(wf.context(workflow, run, stage_instances=(unknown,)))

    assert result.next_status is RunStatus.WAITING_RETRY
    assert ReadinessReason.UNKNOWN_OUTCOME in {block.code for block in result.blocked}


def test_stage_waiting_human_status(wf) -> None:
    workflow = wf.root_workflow()
    run = wf.run(workflow)
    waiting = wf.instance(
        run,
        "root",
        execution=StageExecutionStatus.WAITING_HUMAN,
        acceptance=AcceptanceStatus.HUMAN_REVIEW,
    )

    result = evaluate_readiness(wf.context(workflow, run, stage_instances=(waiting,)))

    assert result.next_status is RunStatus.WAITING_HUMAN
    assert ReadinessReason.HUMAN_REVIEW_PENDING in {
        block.code for block in result.blocked
    }


def test_open_human_review_status(wf) -> None:
    workflow = wf.chain(2)
    run = wf.run(workflow)
    root = wf.accepted(run, "root")
    review = wf.review(run, status=ReviewStatus.OPEN)

    result = evaluate_readiness(
        wf.context(
            workflow,
            run,
            stage_instances=(root,),
            human_reviews=(review,),
        )
    )

    assert result.next_status is RunStatus.WAITING_HUMAN


def test_resolved_human_review_does_not_wait(wf) -> None:
    workflow = wf.chain(2)
    run = wf.run(workflow)
    root = wf.accepted(run, "root")
    review = wf.review(run, status=ReviewStatus.RESOLVED)

    result = evaluate_readiness(
        wf.context(
            workflow,
            run,
            stage_instances=(root,),
            human_reviews=(review,),
        )
    )

    assert result.next_status is RunStatus.RUNNING


def test_pending_human_approval_stage_waits_human(wf) -> None:
    workflow = wf.workflow(
        [
            wf.node("root", stage_name="manual_topic"),
            wf.node(
                "human_approval",
                depends_on=["root"],
                stage_name="human_approval",
                gate="human_publication_gate_v1",
            ),
        ]
    )
    run = wf.run(workflow)
    root = wf.accepted(run, "root")
    approval = wf.instance(
        run,
        "human_approval",
        acceptance=AcceptanceStatus.PENDING,
        gate="human_publication_gate_v1",
        outputs=("artifact_final",),
    )

    result = evaluate_readiness(
        wf.context(workflow, run, stage_instances=(root, approval))
    )

    assert result.next_status is RunStatus.WAITING_HUMAN


def test_durable_failed_status_is_preserved(wf) -> None:
    workflow = wf.root_workflow()
    run = wf.run(workflow, status=RunStatus.FAILED)
    accepted = wf.accepted(run, "root")

    result = evaluate_readiness(wf.context(workflow, run, stage_instances=(accepted,)))

    assert result.next_status is RunStatus.FAILED


def test_durable_completed_status_is_preserved_even_without_rows(wf) -> None:
    workflow = wf.root_workflow()
    run = wf.run(workflow, status=RunStatus.COMPLETED)

    result = evaluate_readiness(wf.context(workflow, run))

    assert result.next_status is RunStatus.COMPLETED
    assert result.ready_node_ids == ()


def test_durable_cancelled_status_is_preserved(wf) -> None:
    workflow = wf.root_workflow()
    run = wf.run(workflow, status=RunStatus.CANCELLED)

    result = evaluate_readiness(wf.context(workflow, run))

    assert result.next_status is RunStatus.CANCELLED
    assert result.ready_node_ids == ()
