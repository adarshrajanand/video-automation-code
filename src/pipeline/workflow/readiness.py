"""Pure workflow readiness and run-status evaluation.

The engine consumes an explicit :class:`ReadinessContext` and returns a typed
:class:`ReadinessResult`. It does not open a database, create jobs, claim work,
write outbox rows, choose providers, or run stage code. Calling it twice with
the same context returns the same result.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from pipeline.contracts.execution import InputManifest, StageInstance
from pipeline.contracts.quality import QualityGateResult
from pipeline.contracts.vocabularies import (
    AcceptanceStatus,
    ArtifactPointerType,
    ArtifactState,
    CardinalityMode,
    GateDecision,
    InputSelectorKind,
    ReviewStatus,
    RunStatus,
    StageExecutionStatus,
    StageName,
)
from pipeline.contracts.workflow import StageNode, WorkflowDefinition
from pipeline.workflow.cardinality import (
    CardinalityIssue,
    CardinalityPlan,
    plan_cardinality,
)
from pipeline.workflow.conditions import ConditionEvaluationError, evaluate_condition
from pipeline.workflow.models import (
    BlockedReason,
    PlannedItem,
    ReadinessContext,
    ReadinessReason,
    ReadinessResult,
)

_INVALID_ARTIFACT_STATES = frozenset(
    {ArtifactState.INVALIDATED, ArtifactState.SUPERSEDED, ArtifactState.DELETED}
)
_ACCEPTED_POINTER_TYPES = frozenset(
    {ArtifactPointerType.ACCEPTED, ArtifactPointerType.PUBLISHED}
)
_OPEN_REVIEW_STATUSES = frozenset({ReviewStatus.OPEN, ReviewStatus.ASSIGNED})


@dataclass(slots=True)
class _GateVerdict:
    found: bool
    passed: bool
    decision: GateDecision | None = None
    result: QualityGateResult | None = None
    targets_usable: bool = True


@dataclass(slots=True)
class _InstanceState:
    instance: StageInstance
    accepted: bool
    execution_ready: bool
    waiting_human: bool
    waiting_retry: bool
    terminal_failure: bool
    reasons: tuple[CardinalityIssue, ...] = ()


@dataclass(slots=True)
class _NodeState:
    node: StageNode
    enabled: bool = True
    accepted: bool = False
    expected_keys: tuple[str, ...] = ()
    accepted_keys: set[str] = field(default_factory=set)
    ready_instance_ids: list[str] = field(default_factory=list)
    planned_items: list[PlannedItem] = field(default_factory=list)
    blocked: list[BlockedReason] = field(default_factory=list)
    terminal_failure: bool = False
    waiting_human: bool = False
    waiting_retry: bool = False


def _reason(
    code: ReadinessReason,
    message: str,
    *,
    stage_instance_id: str | None = None,
    logical_item_key: str | None = None,
) -> CardinalityIssue:
    return CardinalityIssue(
        code=code,
        message=message,
        stage_instance_id=stage_instance_id,
        logical_item_key=logical_item_key,
    )


def _blocked(
    node_id: str,
    issue: CardinalityIssue,
    *,
    stage_instance_id: str | None = None,
    logical_item_key: str | None = None,
) -> BlockedReason:
    return BlockedReason(
        node_id=node_id,
        code=issue.code,
        message=issue.message,
        stage_instance_id=issue.stage_instance_id or stage_instance_id,
        logical_item_key=issue.logical_item_key or logical_item_key,
    )


def _topological_order(workflow: WorkflowDefinition) -> tuple[str, ...]:
    nodes = workflow.nodes
    node_ids = [node.node_id for node in nodes]
    indegree = {node.node_id: len(node.depends_on) for node in nodes}
    ready = [node.node_id for node in nodes if indegree[node.node_id] == 0]
    ordered: list[str] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for node in nodes:
            if current in node.depends_on:
                indegree[node.node_id] -= 1
                if indegree[node.node_id] == 0:
                    ready.append(node.node_id)
    if len(ordered) != len(node_ids):
        raise ValueError("workflow definition contains a dependency cycle")
    return tuple(ordered)


def _usable_artifacts(context: ReadinessContext) -> frozenset[str]:
    ids = set(context.accepted_artifact_ids)
    ids.update(context.run_input_artifact_ids)
    for pointer in context.accepted_artifact_pointers:
        if pointer.active and pointer.pointer_type in _ACCEPTED_POINTER_TYPES:
            ids.add(pointer.artifact_id)
    for instance in context.stage_instances:
        ids.update(instance.accepted_output_artifact_ids)
    return frozenset(
        artifact_id
        for artifact_id in ids
        if context.artifact_states.get(artifact_id) not in _INVALID_ARTIFACT_STATES
    )


def _matching_gate_results(
    instance: StageInstance,
    gate_id: str,
    results: Sequence[QualityGateResult],
    *,
    explicitly_linked: bool,
) -> list[QualityGateResult]:
    if explicitly_linked:
        return [
            result
            for result in results
            if result.quality_gate_result_id == instance.quality_gate_result_id
        ]
    return [
        result
        for result in results
        if result.gate_id == gate_id
        and (
            result.stage_instance_id == instance.stage_instance_id
            or (
                result.stage_instance_id is None
                and result.logical_item_key == instance.logical_item_key
            )
        )
    ]


def _gate_verdict(
    instance: StageInstance,
    node: StageNode,
    results: Sequence[QualityGateResult],
    usable_artifacts: frozenset[str],
) -> _GateVerdict:
    gate_id = node.quality_gate_id
    if gate_id is None:
        return _GateVerdict(found=False, passed=True)

    explicit = instance.quality_gate_result_id is not None
    candidates = _matching_gate_results(
        instance, gate_id, results, explicitly_linked=explicit
    )
    if explicit:
        candidates = [result for result in candidates if result.gate_id == gate_id]
    if not candidates:
        return _GateVerdict(found=False, passed=False)

    chosen = sorted(
        candidates,
        key=lambda result: (result.created_at, result.quality_gate_result_id),
    )[-1]
    targets_usable = all(
        artifact_id in usable_artifacts for artifact_id in chosen.target_artifact_ids
    )
    if not targets_usable:
        return _GateVerdict(
            found=True,
            passed=False,
            decision=chosen.decision,
            result=chosen,
            targets_usable=False,
        )
    return _GateVerdict(
        found=True,
        passed=chosen.decision is GateDecision.PASS,
        decision=chosen.decision,
        result=chosen,
        targets_usable=True,
    )


def _instance_state(
    instance: StageInstance,
    node: StageNode,
    context: ReadinessContext,
    usable_artifacts: frozenset[str],
) -> _InstanceState:
    reasons: list[CardinalityIssue] = []
    waiting_human = instance.acceptance_status is AcceptanceStatus.HUMAN_REVIEW
    waiting_retry = False
    terminal_failure = False
    accepted = False
    execution_ready = False

    if instance.execution_status is StageExecutionStatus.WAITING_HUMAN:
        waiting_human = True
        reasons.append(
            _reason(
                ReadinessReason.HUMAN_REVIEW_PENDING,
                "stage instance is waiting for human review",
                stage_instance_id=instance.stage_instance_id,
                logical_item_key=instance.logical_item_key,
            )
        )
    elif instance.execution_status is StageExecutionStatus.WAITING_RETRY:
        waiting_retry = True
        reasons.append(
            _reason(
                ReadinessReason.RETRY_WAIT,
                "stage instance is waiting to be retried",
                stage_instance_id=instance.stage_instance_id,
                logical_item_key=instance.logical_item_key,
            )
        )
    elif instance.execution_status is StageExecutionStatus.UNKNOWN:
        waiting_retry = True
        reasons.append(
            _reason(
                ReadinessReason.UNKNOWN_OUTCOME,
                "stage instance outcome is unknown and must be retried",
                stage_instance_id=instance.stage_instance_id,
                logical_item_key=instance.logical_item_key,
            )
        )
    elif instance.execution_status is StageExecutionStatus.FAILED:
        if instance.stage_instance_id in context.recoverable_stage_instance_ids:
            reasons.append(
                _reason(
                    ReadinessReason.RECOVERY_PENDING,
                    "stage instance failed and an explicit recovery is pending",
                    stage_instance_id=instance.stage_instance_id,
                    logical_item_key=instance.logical_item_key,
                )
            )
        else:
            terminal_failure = True
            reasons.append(
                _reason(
                    ReadinessReason.TERMINAL_FAILURE,
                    "stage instance failed without an explicit recovery",
                    stage_instance_id=instance.stage_instance_id,
                    logical_item_key=instance.logical_item_key,
                )
            )
    elif instance.execution_status is StageExecutionStatus.CANCELLED:
        reasons.append(
            _reason(
                ReadinessReason.CANCELLED,
                "stage instance is cancelled",
                stage_instance_id=instance.stage_instance_id,
                logical_item_key=instance.logical_item_key,
            )
        )
    elif instance.execution_status is StageExecutionStatus.INVALIDATED:
        reasons.append(
            _reason(
                ReadinessReason.INVALIDATED,
                "stage instance is invalidated and requires an explicit recovery",
                stage_instance_id=instance.stage_instance_id,
                logical_item_key=instance.logical_item_key,
            )
        )
    elif instance.execution_status in (
        StageExecutionStatus.CLAIMED,
        StageExecutionStatus.RUNNING,
    ):
        reasons.append(
            _reason(
                ReadinessReason.ACTIVE_ATTEMPT,
                f"stage instance is {instance.execution_status.value}",
                stage_instance_id=instance.stage_instance_id,
                logical_item_key=instance.logical_item_key,
            )
        )
    elif instance.execution_status in (
        StageExecutionStatus.PENDING,
        StageExecutionStatus.READY,
    ):
        execution_ready = not reasons
    elif instance.execution_status is StageExecutionStatus.SUCCEEDED:
        if node.quality_gate_id is not None:
            verdict = _gate_verdict(
                instance, node, context.quality_gate_results, usable_artifacts
            )
            if instance.acceptance_status is AcceptanceStatus.PASSED:
                if verdict.passed:
                    accepted = True
                elif not verdict.found:
                    reasons.append(
                        _reason(
                            ReadinessReason.GATE_RESULT_MISSING,
                            f"quality gate {node.quality_gate_id!r} is not PASS",
                            stage_instance_id=instance.stage_instance_id,
                            logical_item_key=instance.logical_item_key,
                        )
                    )
                elif not verdict.targets_usable:
                    reasons.append(
                        _reason(
                            ReadinessReason.INPUT_ARTIFACT_NOT_ACCEPTED,
                            "quality gate targets are not accepted, usable artifacts",
                            stage_instance_id=instance.stage_instance_id,
                            logical_item_key=instance.logical_item_key,
                        )
                    )
                elif verdict.decision is GateDecision.FAIL:
                    terminal_failure = True
                    reasons.append(
                        _reason(
                            ReadinessReason.GATE_FAILED,
                            f"quality gate {node.quality_gate_id!r} decided FAIL",
                            stage_instance_id=instance.stage_instance_id,
                            logical_item_key=instance.logical_item_key,
                        )
                    )
                elif verdict.decision is GateDecision.HUMAN_REVIEW:
                    waiting_human = True
                    reasons.append(
                        _reason(
                            ReadinessReason.HUMAN_REVIEW_PENDING,
                            f"quality gate {node.quality_gate_id!r} requires "
                            "human review",
                            stage_instance_id=instance.stage_instance_id,
                            logical_item_key=instance.logical_item_key,
                        )
                    )
                else:
                    reasons.append(
                        _reason(
                            ReadinessReason.GATE_REGENERATE,
                            f"quality gate {node.quality_gate_id!r} requires "
                            "regeneration",
                            stage_instance_id=instance.stage_instance_id,
                            logical_item_key=instance.logical_item_key,
                        )
                    )
            elif instance.acceptance_status is AcceptanceStatus.PENDING:
                if node.stage_name is StageName.HUMAN_APPROVAL:
                    waiting_human = True
                    reasons.append(
                        _reason(
                            ReadinessReason.HUMAN_REVIEW_PENDING,
                            "human approval is pending",
                            stage_instance_id=instance.stage_instance_id,
                            logical_item_key=instance.logical_item_key,
                        )
                    )
                else:
                    reasons.append(
                        _reason(
                            ReadinessReason.GATE_PENDING,
                            f"quality gate {node.quality_gate_id!r} is pending",
                            stage_instance_id=instance.stage_instance_id,
                            logical_item_key=instance.logical_item_key,
                        )
                    )
            elif instance.acceptance_status is AcceptanceStatus.REGENERATE:
                reasons.append(
                    _reason(
                        ReadinessReason.GATE_REGENERATE,
                        "quality acceptance requires regeneration",
                        stage_instance_id=instance.stage_instance_id,
                        logical_item_key=instance.logical_item_key,
                    )
                )
            elif instance.acceptance_status is AcceptanceStatus.HUMAN_REVIEW:
                waiting_human = True
                reasons.append(
                    _reason(
                        ReadinessReason.HUMAN_REVIEW_PENDING,
                        "quality acceptance requires human review",
                        stage_instance_id=instance.stage_instance_id,
                        logical_item_key=instance.logical_item_key,
                    )
                )
            elif instance.acceptance_status is AcceptanceStatus.FAILED:
                terminal_failure = True
                reasons.append(
                    _reason(
                        ReadinessReason.GATE_FAILED,
                        "quality acceptance failed terminally",
                        stage_instance_id=instance.stage_instance_id,
                        logical_item_key=instance.logical_item_key,
                    )
                )
            else:
                reasons.append(
                    _reason(
                        ReadinessReason.GATE_RESULT_MISSING,
                        "a quality-gated stage cannot be accepted as NOT_REQUIRED",
                        stage_instance_id=instance.stage_instance_id,
                        logical_item_key=instance.logical_item_key,
                    )
                )
        elif instance.acceptance_status in (
            AcceptanceStatus.NOT_REQUIRED,
            AcceptanceStatus.PASSED,
        ):
            outputs = instance.accepted_output_artifact_ids
            if not outputs:
                reasons.append(
                    _reason(
                        ReadinessReason.NO_ACCEPTED_OUTPUT,
                        "a non-gated succeeded stage has no accepted output artifact",
                        stage_instance_id=instance.stage_instance_id,
                        logical_item_key=instance.logical_item_key,
                    )
                )
            elif any(artifact_id not in usable_artifacts for artifact_id in outputs):
                reasons.append(
                    _reason(
                        ReadinessReason.INPUT_ARTIFACT_NOT_ACCEPTED,
                        "an accepted output artifact is invalid or unknown",
                        stage_instance_id=instance.stage_instance_id,
                        logical_item_key=instance.logical_item_key,
                    )
                )
            else:
                accepted = True
        elif instance.acceptance_status is AcceptanceStatus.PENDING:
            reasons.append(
                _reason(
                    ReadinessReason.ACCEPTANCE_PENDING,
                    "stage execution succeeded but acceptance is still pending",
                    stage_instance_id=instance.stage_instance_id,
                    logical_item_key=instance.logical_item_key,
                )
            )
        elif instance.acceptance_status is AcceptanceStatus.REGENERATE:
            reasons.append(
                _reason(
                    ReadinessReason.GATE_REGENERATE,
                    "stage acceptance requires regeneration",
                    stage_instance_id=instance.stage_instance_id,
                    logical_item_key=instance.logical_item_key,
                )
            )
        elif instance.acceptance_status is AcceptanceStatus.HUMAN_REVIEW:
            waiting_human = True
            reasons.append(
                _reason(
                    ReadinessReason.HUMAN_REVIEW_PENDING,
                    "stage acceptance requires human review",
                    stage_instance_id=instance.stage_instance_id,
                    logical_item_key=instance.logical_item_key,
                )
            )
        elif instance.acceptance_status is AcceptanceStatus.FAILED:
            terminal_failure = True
            reasons.append(
                _reason(
                    ReadinessReason.GATE_FAILED,
                    "stage acceptance failed terminally",
                    stage_instance_id=instance.stage_instance_id,
                    logical_item_key=instance.logical_item_key,
                )
            )

    if (
        not accepted
        and instance.acceptance_status is AcceptanceStatus.FAILED
        and instance.stage_instance_id not in context.recoverable_stage_instance_ids
    ):
        terminal_failure = True
    if accepted:
        reasons = []
        terminal_failure = False
        waiting_human = instance.acceptance_status is AcceptanceStatus.HUMAN_REVIEW
        waiting_retry = False
        execution_ready = False

    return _InstanceState(
        instance=instance,
        accepted=accepted,
        execution_ready=execution_ready,
        waiting_human=waiting_human,
        waiting_retry=waiting_retry,
        terminal_failure=terminal_failure,
        reasons=tuple(reasons),
    )


def _manifest_lookup(manifests: Sequence[InputManifest]) -> dict[str, InputManifest]:
    return {manifest.manifest_id: manifest for manifest in manifests}


def _complete_input_manifest(
    manifest: InputManifest,
    *,
    require_keys: bool,
) -> CardinalityIssue | None:
    if not manifest.complete:
        return _reason(
            ReadinessReason.INCOMPLETE_MANIFEST,
            f"manifest {manifest.manifest_id!r} is not complete",
            stage_instance_id=manifest.stage_instance_id,
        )
    if manifest.expected_count is None:
        return _reason(
            ReadinessReason.INCOMPLETE_MANIFEST,
            f"manifest {manifest.manifest_id!r} does not declare expected_count",
            stage_instance_id=manifest.stage_instance_id,
        )
    if manifest.expected_count == 0:
        return _reason(
            ReadinessReason.EMPTY_MANIFEST,
            f"manifest {manifest.manifest_id!r} declares zero expected items",
            stage_instance_id=manifest.stage_instance_id,
        )
    if len(manifest.resolved_artifact_ids) != manifest.expected_count:
        return _reason(
            ReadinessReason.INCOMPLETE_MANIFEST,
            f"manifest {manifest.manifest_id!r} resolves "
            f"{len(manifest.resolved_artifact_ids)} of "
            f"{manifest.expected_count} expected items",
            stage_instance_id=manifest.stage_instance_id,
        )
    if require_keys and not manifest.expected_artifact_slots:
        return _reason(
            ReadinessReason.MISSING_MANIFEST_KEYS,
            f"manifest {manifest.manifest_id!r} does not declare expected "
            "logical child keys",
            stage_instance_id=manifest.stage_instance_id,
        )
    return None


def _manifest_for_selector(
    node: StageNode,
    instance: StageInstance | None,
    plan: CardinalityPlan,
    manifests_by_id: Mapping[str, InputManifest],
) -> tuple[InputManifest | None, CardinalityIssue | None]:
    if node.input_selector.kind is not InputSelectorKind.MANIFEST:
        return None, None
    manifest_id: str | None = None
    if instance is not None and instance.expected_input_manifest_id is not None:
        manifest_id = instance.expected_input_manifest_id
    elif plan.expected_manifest_id is not None:
        manifest_id = plan.expected_manifest_id
    elif node.cardinality.expected_manifest_id is not None:
        manifest_id = node.cardinality.expected_manifest_id
    if manifest_id is None:
        return None, _reason(
            ReadinessReason.MANIFEST_REQUIRED,
            f"node {node.node_id!r} selects inputs from a manifest but no "
            "expected manifest is declared",
        )
    manifest = manifests_by_id.get(manifest_id)
    if manifest is None:
        return None, _reason(
            ReadinessReason.MISSING_EXPECTED_MANIFEST,
            f"expected manifest {manifest_id!r} is not present",
        )
    issue = _complete_input_manifest(manifest, require_keys=False)
    if issue is not None:
        return manifest, issue
    return manifest, None


def _artifact_inputs(
    node: StageNode,
    dependency_instances: Sequence[StageInstance],
    manifest: InputManifest | None,
    context: ReadinessContext,
    usable_artifacts: frozenset[str],
) -> tuple[tuple[str, ...], CardinalityIssue | None]:
    selected: set[str] = set()
    kind = node.input_selector.kind
    if kind is InputSelectorKind.RUN_INPUT:
        selected.update(context.run_input_artifact_ids)
    elif kind is InputSelectorKind.DEPENDENCY_OUTPUTS:
        for instance in dependency_instances:
            selected.update(instance.accepted_output_artifact_ids)
    elif kind is InputSelectorKind.MANIFEST:
        if manifest is None:
            return (), _reason(
                ReadinessReason.MANIFEST_REQUIRED,
                f"node {node.node_id!r} requires a manifest input",
            )
        selected.update(manifest.resolved_artifact_ids)
    elif kind is InputSelectorKind.POINTERS:
        for pointer in context.accepted_artifact_pointers:
            if pointer.active and pointer.pointer_type in _ACCEPTED_POINTER_TYPES:
                selected.add(pointer.artifact_id)

    missing = sorted(
        artifact_id for artifact_id in selected if artifact_id not in usable_artifacts
    )
    if missing:
        return tuple(sorted(selected)), _reason(
            ReadinessReason.INPUT_ARTIFACT_NOT_ACCEPTED,
            "input artifact(s) are not active, accepted versions: "
            + ", ".join(missing),
        )
    return tuple(sorted(selected)), None


def _dependency_instances(
    node: StageNode,
    instances_by_node: Mapping[str, Sequence[StageInstance]],
) -> tuple[StageInstance, ...]:
    selected: list[StageInstance] = []
    for dependency in node.depends_on:
        selected.extend(instances_by_node.get(dependency, ()))
    return tuple(selected)


def _terminal_node_ids(
    workflow: WorkflowDefinition,
    enabled: Mapping[str, bool],
) -> tuple[str, ...]:
    enabled_nodes = [node for node in workflow.nodes if enabled.get(node.node_id)]
    enabled_ids = {node.node_id for node in enabled_nodes}
    return tuple(
        node.node_id
        for node in enabled_nodes
        if not any(
            node.node_id in dependent.depends_on
            for dependent in enabled_nodes
            if dependent.node_id in enabled_ids
        )
    )


def _derive_status(
    context: ReadinessContext,
    *,
    enabled: Mapping[str, bool],
    node_states: Mapping[str, _NodeState],
    terminal_node_ids: tuple[str, ...],
    open_human_reviews: bool,
) -> RunStatus:
    if context.run.status is RunStatus.CANCELLED:
        return RunStatus.CANCELLED
    if context.run.status in (RunStatus.COMPLETED, RunStatus.FAILED):
        return context.run.status

    relevant = [
        state
        for state in node_states.values()
        if state.enabled and enabled.get(state.node.node_id)
    ]
    if any(state.terminal_failure for state in relevant):
        return RunStatus.FAILED
    if open_human_reviews or any(state.waiting_human for state in relevant):
        return RunStatus.WAITING_HUMAN
    if any(state.waiting_retry for state in relevant):
        return RunStatus.WAITING_RETRY
    if terminal_node_ids and all(
        node_states[node_id].accepted for node_id in terminal_node_ids
    ):
        return RunStatus.COMPLETED
    return RunStatus.RUNNING


def evaluate_readiness(context: ReadinessContext) -> ReadinessResult:
    """Evaluate readiness without mutating the context or any durable record."""

    workflow = context.workflow
    run = context.run
    nodes_by_id = {node.node_id: node for node in workflow.nodes}
    node_order = [node.node_id for node in workflow.nodes]

    instances_by_node: dict[str, list[StageInstance]] = {
        node_id: [] for node_id in node_order
    }
    for instance in sorted(
        context.stage_instances,
        key=lambda item: (
            item.node_id,
            item.logical_item_key,
            item.stage_instance_id,
        ),
    ):
        instances_by_node[instance.node_id].append(instance)

    usable_artifacts = _usable_artifacts(context)
    instance_states = {
        instance.stage_instance_id: _instance_state(
            instance, nodes_by_id[instance.node_id], context, usable_artifacts
        )
        for instance in context.stage_instances
    }
    accepted_instance_ids = {
        instance_id for instance_id, state in instance_states.items() if state.accepted
    }

    enabled: dict[str, bool] = {}
    condition_errors: dict[str, str] = {}
    disabled_node_ids: set[str] = set()
    for node in workflow.nodes:
        try:
            is_enabled = evaluate_condition(
                node.enabled_when, context.condition_context
            )
        except ConditionEvaluationError as error:
            condition_errors[node.node_id] = str(error)
            enabled[node.node_id] = False
            continue
        enabled[node.node_id] = is_enabled
        if not is_enabled:
            disabled_node_ids.add(node.node_id)

    manifests_by_id = _manifest_lookup(context.input_manifests)
    order = _topological_order(workflow)
    node_states: dict[str, _NodeState] = {}

    for node_id in order:
        node = nodes_by_id[node_id]
        state = _NodeState(node=node, enabled=enabled[node_id])
        node_states[node_id] = state

        node_instances = instances_by_node[node_id]
        for instance in node_instances:
            instance_state = instance_states[instance.stage_instance_id]
            state.terminal_failure = (
                state.terminal_failure or instance_state.terminal_failure
            )
            state.waiting_human = state.waiting_human or instance_state.waiting_human
            state.waiting_retry = state.waiting_retry or instance_state.waiting_retry

        if node_id in condition_errors:
            state.blocked.append(
                _blocked(
                    node_id,
                    _reason(
                        ReadinessReason.CONDITION_ERROR,
                        "enabled_when could not be evaluated: "
                        + condition_errors[node_id],
                    ),
                )
            )
            continue
        if not state.enabled:
            continue

        dependency_blocked = False
        for dependency in node.depends_on:
            dependency_state = node_states[dependency]
            if not dependency_state.enabled:
                dependency_blocked = True
                state.blocked.append(
                    _blocked(
                        node_id,
                        _reason(
                            ReadinessReason.DEPENDENCY_DISABLED,
                            f"declared dependency {dependency!r} is disabled by "
                            "its enabled_when condition",
                        ),
                    )
                )
            elif not dependency_state.accepted:
                dependency_blocked = True
                state.blocked.append(
                    _blocked(
                        node_id,
                        _reason(
                            ReadinessReason.DEPENDENCY_NOT_ACCEPTED,
                            f"declared dependency {dependency!r} does not have "
                            "fully accepted outputs and gates",
                        ),
                    )
                )

        plan = plan_cardinality(
            node,
            stage_instances=node_instances,
            input_manifests=context.input_manifests,
            dependency_instances=_dependency_instances(node, instances_by_node),
            accepted_stage_instance_ids=accepted_instance_ids,
        )
        state.expected_keys = plan.item_keys
        for issue in plan.issues:
            state.blocked.append(_blocked(node_id, issue))
        manifest_inputs_ready = True
        if (
            plan.manifest is not None
            and node.cardinality.mode is CardinalityMode.MANY_TO_ONE
        ):
            missing_manifest_artifacts = [
                artifact_id
                for artifact_id in plan.manifest.resolved_artifact_ids
                if artifact_id not in usable_artifacts
            ]
            if missing_manifest_artifacts:
                manifest_inputs_ready = False
                state.blocked.append(
                    _blocked(
                        node_id,
                        _reason(
                            ReadinessReason.INPUT_ARTIFACT_NOT_ACCEPTED,
                            "expected fan-in manifest resolves artifact(s) that "
                            "are not active, accepted versions: "
                            + ", ".join(sorted(missing_manifest_artifacts)),
                            stage_instance_id=plan.manifest.stage_instance_id,
                        ),
                    )
                )
        if dependency_blocked or not plan.complete:
            continue

        dependency_instances = _dependency_instances(node, instances_by_node)

        manifest_for_planned, manifest_issue = _manifest_for_selector(
            node, None, plan, manifests_by_id
        )
        planned_inputs: tuple[str, ...] = ()
        if manifest_issue is None:
            planned_inputs, input_issue = _artifact_inputs(
                node,
                dependency_instances,
                manifest_for_planned,
                context,
                usable_artifacts,
            )
            manifest_issue = input_issue
        if manifest_issue is not None:
            state.blocked.append(_blocked(node_id, manifest_issue))

        by_key: dict[str, list[StageInstance]] = {}
        for instance in node_instances:
            by_key.setdefault(instance.logical_item_key, []).append(instance)

        for logical_key in plan.item_keys:
            matches = by_key.get(logical_key, [])
            if len(matches) > 1:
                state.blocked.append(
                    _blocked(
                        node_id,
                        _reason(
                            ReadinessReason.CARDINALITY_MISMATCH,
                            f"more than one stage instance exists for logical "
                            f"item {logical_key!r}",
                            logical_item_key=logical_key,
                        ),
                    )
                )
                continue
            if not matches:
                if manifest_issue is not None:
                    continue
                state.planned_items.append(
                    PlannedItem(
                        node_id=node_id,
                        logical_item_key=logical_key,
                        input_artifact_ids=planned_inputs,
                        expected_input_manifest_id=(
                            plan.expected_manifest_id
                            or node.cardinality.expected_manifest_id
                        ),
                    )
                )
                continue

            instance = matches[0]
            instance_state = instance_states[instance.stage_instance_id]
            if instance_state.accepted:
                state.accepted_keys.add(logical_key)
                continue

            for issue in instance_state.reasons:
                state.blocked.append(_blocked(node_id, issue))
            if isinstance(instance_state.instance, StageInstance):
                state.waiting_human = (
                    state.waiting_human or instance_state.waiting_human
                )
                state.waiting_retry = (
                    state.waiting_retry or instance_state.waiting_retry
                )
                state.terminal_failure = (
                    state.terminal_failure or instance_state.terminal_failure
                )

            instance_manifest, instance_manifest_issue = _manifest_for_selector(
                node, instance, plan, manifests_by_id
            )
            if instance_manifest_issue is not None:
                state.blocked.append(
                    _blocked(
                        node_id,
                        instance_manifest_issue,
                        stage_instance_id=instance.stage_instance_id,
                        logical_item_key=logical_key,
                    )
                )
                continue
            _, input_issue = _artifact_inputs(
                node,
                dependency_instances,
                instance_manifest,
                context,
                usable_artifacts,
            )
            if input_issue is not None:
                state.blocked.append(
                    _blocked(
                        node_id,
                        input_issue,
                        stage_instance_id=instance.stage_instance_id,
                        logical_item_key=logical_key,
                    )
                )
                continue
            if instance_state.execution_ready and manifest_inputs_ready:
                state.ready_instance_ids.append(instance.stage_instance_id)

        state.accepted = (
            bool(state.expected_keys)
            and len(state.accepted_keys) == len(state.expected_keys)
            and not state.blocked
        )

    terminal_node_ids = _terminal_node_ids(workflow, enabled)
    open_human_reviews = any(
        review.status in _OPEN_REVIEW_STATUSES for review in context.human_reviews
    )
    next_status = _derive_status(
        context,
        enabled=enabled,
        node_states=node_states,
        terminal_node_ids=terminal_node_ids,
        open_human_reviews=open_human_reviews,
    )

    ordered_states = [node_states[node_id] for node_id in node_order]
    blocked: list[BlockedReason] = []
    seen_blockers: set[tuple[str, str | None, str | None, str, str]] = set()
    for state in ordered_states:
        for item in state.blocked:
            key = (
                item.node_id,
                item.stage_instance_id,
                item.logical_item_key,
                item.code.value,
                item.message,
            )
            if key in seen_blockers:
                continue
            seen_blockers.add(key)
            blocked.append(item)

    terminal_run = run.status in (
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    )
    ready_node_ids = (
        ()
        if terminal_run
        else tuple(
            state.node.node_id
            for state in ordered_states
            if state.enabled and (state.planned_items or state.ready_instance_ids)
        )
    )
    ready_instance_ids = (
        ()
        if terminal_run
        else tuple(
            instance_id
            for state in ordered_states
            for instance_id in state.ready_instance_ids
        )
    )
    planned_items = (
        ()
        if terminal_run
        else tuple(
            item
            for state in ordered_states
            for item in sorted(
                state.planned_items, key=lambda planned: planned.logical_item_key
            )
        )
    )

    return ReadinessResult(
        run_id=run.run_id,
        workflow_id=workflow.workflow_id,
        next_status=next_status,
        ready_node_ids=ready_node_ids,
        ready_instance_ids=ready_instance_ids,
        planned_items=planned_items,
        blocked=tuple(blocked),
        accepted_node_ids=tuple(
            state.node.node_id for state in ordered_states if state.accepted
        ),
        disabled_node_ids=tuple(
            node_id for node_id in node_order if node_id in disabled_node_ids
        ),
        terminal_node_ids=terminal_node_ids,
    )


__all__ = ["evaluate_readiness"]
