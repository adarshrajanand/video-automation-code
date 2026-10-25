"""Declarative cardinality expansion and fan-in planning.

The planner only decides which logical item keys are expected. It never creates
stage instances, manifests, jobs, or events. Readiness compares those keys with
the durable stage instances supplied by the caller.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence

from pydantic import BaseModel, ConfigDict

from pipeline.contracts.execution import InputManifest, StageInstance
from pipeline.contracts.vocabularies import CardinalityMode
from pipeline.contracts.workflow import StageNode
from pipeline.workflow.models import ReadinessReason

_CONFIG = ConfigDict(frozen=True, extra="forbid")
MANIFEST_CHILDREN_POLICIES = frozenset({"manifest_children", "render_chunk_manifest"})


class CardinalityIssue(BaseModel):
    """One reason cardinality could not be planned completely."""

    model_config = _CONFIG

    code: ReadinessReason
    message: str
    stage_instance_id: str | None = None
    logical_item_key: str | None = None


class CardinalityPlan(BaseModel):
    """Expected logical item keys and any planning issues."""

    model_config = _CONFIG

    mode: CardinalityMode
    item_keys: tuple[str, ...] = ()
    issues: tuple[CardinalityIssue, ...] = ()
    manifest: InputManifest | None = None
    expected_manifest_id: str | None = None

    @property
    def complete(self) -> bool:
        return not self.issues


def _issue(
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


def _ordered_instances(instances: Sequence[StageInstance]) -> tuple[StageInstance, ...]:
    return tuple(
        sorted(
            instances, key=lambda item: (item.logical_item_key, item.stage_instance_id)
        )
    )


def _generated_key(node_id: str, index: int) -> str:
    return f"{node_id}:{index:02d}"


def _count_keys(
    node: StageNode,
    count: int,
    instances: Sequence[StageInstance],
) -> tuple[tuple[str, ...], tuple[CardinalityIssue, ...]]:
    ordered = _ordered_instances(instances)
    keys = [instance.logical_item_key for instance in ordered]
    issues: list[CardinalityIssue] = []
    if len(set(keys)) != len(keys):
        issues.append(
            _issue(
                ReadinessReason.CARDINALITY_MISMATCH,
                "stage instances repeat a logical_item_key for a counted node",
            )
        )
    if len(keys) > count:
        issues.append(
            _issue(
                ReadinessReason.CARDINALITY_MISMATCH,
                f"node {node.node_id!r} declares count {count} but has "
                f"{len(keys)} stage instance(s)",
            )
        )
        return tuple(keys), tuple(issues)
    used = set(keys)
    index = 1
    while len(keys) < count:
        candidate = _generated_key(node.node_id, index)
        index += 1
        if candidate in used:
            continue
        keys.append(candidate)
        used.add(candidate)
    return tuple(keys), tuple(issues)


def _complete_manifest_issue(manifest: InputManifest) -> CardinalityIssue | None:
    if not manifest.complete:
        return _issue(
            ReadinessReason.INCOMPLETE_MANIFEST,
            f"manifest {manifest.manifest_id!r} is not complete",
            stage_instance_id=manifest.stage_instance_id,
        )
    if manifest.expected_count is None:
        return _issue(
            ReadinessReason.INCOMPLETE_MANIFEST,
            f"manifest {manifest.manifest_id!r} does not declare expected_count",
            stage_instance_id=manifest.stage_instance_id,
        )
    if manifest.expected_count == 0:
        return _issue(
            ReadinessReason.EMPTY_MANIFEST,
            f"manifest {manifest.manifest_id!r} declares zero expected items; "
            "an empty queue is not completion",
            stage_instance_id=manifest.stage_instance_id,
        )
    if len(manifest.resolved_artifact_ids) != manifest.expected_count:
        return _issue(
            ReadinessReason.INCOMPLETE_MANIFEST,
            f"manifest {manifest.manifest_id!r} resolves "
            f"{len(manifest.resolved_artifact_ids)} of "
            f"{manifest.expected_count} expected item(s)",
            stage_instance_id=manifest.stage_instance_id,
        )
    return None


def _manifest_children(
    node: StageNode,
    instances: Sequence[StageInstance],
    manifests: Sequence[InputManifest],
    dependency_instances: Sequence[StageInstance],
) -> tuple[CardinalityPlan | None, CardinalityIssue | None]:
    by_id = {manifest.manifest_id: manifest for manifest in manifests}
    explicit_references: list[str] = []
    for instance in _ordered_instances(instances):
        if instance.expected_input_manifest_id is not None:
            explicit_references.append(instance.expected_input_manifest_id)
    if node.cardinality.expected_manifest_id is not None:
        explicit_references.append(node.cardinality.expected_manifest_id)
    for instance in _ordered_instances(dependency_instances):
        if instance.expected_input_manifest_id is not None:
            explicit_references.append(instance.expected_input_manifest_id)

    seen: set[str] = set()
    for manifest_id in explicit_references:
        if manifest_id in seen:
            continue
        seen.add(manifest_id)
        manifest = by_id.get(manifest_id)
        if manifest is None:
            return None, _issue(
                ReadinessReason.MISSING_EXPECTED_MANIFEST,
                f"node {node.node_id!r} references missing manifest {manifest_id!r}",
            )
        return (
            CardinalityPlan(
                mode=node.cardinality.mode,
                manifest=manifest,
                expected_manifest_id=manifest.manifest_id,
            ),
            None,
        )

    complete = sorted(
        (manifest for manifest in manifests if manifest.complete),
        key=lambda manifest: manifest.manifest_id,
    )
    if len(complete) == 1:
        manifest = complete[0]
        return (
            CardinalityPlan(
                mode=node.cardinality.mode,
                manifest=manifest,
                expected_manifest_id=manifest.manifest_id,
            ),
            None,
        )
    if len(complete) > 1:
        return None, _issue(
            ReadinessReason.AMBIGUOUS_MANIFEST,
            f"node {node.node_id!r} has {len(complete)} complete manifests and no "
            "explicit expected_manifest_id; refusing to guess expected children",
        )
    if manifests:
        return None, _issue(
            ReadinessReason.INCOMPLETE_MANIFEST,
            f"node {node.node_id!r} has only incomplete input manifests",
        )
    return None, _issue(
        ReadinessReason.MISSING_EXPECTED_MANIFEST,
        f"node {node.node_id!r} requires a complete input manifest to plan "
        "manifest_children fan-out",
    )


def plan_cardinality(
    node: StageNode,
    *,
    stage_instances: Sequence[StageInstance],
    input_manifests: Sequence[InputManifest],
    dependency_instances: Sequence[StageInstance] = (),
    accepted_stage_instance_ids: Collection[str] = (),
) -> CardinalityPlan:
    """Plan expected item keys for one node from explicit durable records."""

    mode = node.cardinality.mode
    if mode in (CardinalityMode.ONE_TO_ONE, CardinalityMode.MANY_TO_ONE):
        keys = tuple(
            instance.logical_item_key
            for instance in _ordered_instances(stage_instances)
        )
        issues: list[CardinalityIssue] = []
        if len(keys) > 1:
            issues.append(
                _issue(
                    ReadinessReason.CARDINALITY_MISMATCH,
                    f"node {node.node_id!r} is {mode.value} but has "
                    f"{len(keys)} stage instances",
                )
            )
        if mode is CardinalityMode.ONE_TO_ONE:
            if not keys:
                keys = ("default",)
            return CardinalityPlan(mode=mode, item_keys=keys, issues=tuple(issues))

        plan = CardinalityPlan(mode=mode, item_keys=keys)
        if not keys:
            return plan.model_copy(
                update={
                    "issues": (
                        _issue(
                            ReadinessReason.MISSING_STAGE_INSTANCE,
                            f"node {node.node_id!r} is many_to_one and has no "
                            "stage instance; an empty queue does not prove "
                            "fan-in completion",
                        ),
                    )
                }
            )
        instance = _ordered_instances(stage_instances)[0]
        if instance.stage_instance_id in accepted_stage_instance_ids:
            return plan.model_copy(update={"issues": tuple(issues)})
        manifest_id = (
            instance.expected_input_manifest_id or node.cardinality.expected_manifest_id
        )
        if manifest_id is None:
            issues.append(
                _issue(
                    ReadinessReason.MISSING_EXPECTED_MANIFEST,
                    f"stage instance {instance.stage_instance_id!r} for "
                    f"many_to_one node {node.node_id!r} has no "
                    "expected_input_manifest_id",
                    stage_instance_id=instance.stage_instance_id,
                    logical_item_key=instance.logical_item_key,
                )
            )
            return plan.model_copy(update={"issues": tuple(issues)})
        manifest = next(
            (
                candidate
                for candidate in input_manifests
                if candidate.manifest_id == manifest_id
            ),
            None,
        )
        if manifest is None:
            issues.append(
                _issue(
                    ReadinessReason.MISSING_EXPECTED_MANIFEST,
                    f"expected manifest {manifest_id!r} is not present in the "
                    "readiness context",
                    stage_instance_id=instance.stage_instance_id,
                    logical_item_key=instance.logical_item_key,
                )
            )
            return plan.model_copy(update={"issues": tuple(issues)})
        manifest_issue = _complete_manifest_issue(manifest)
        if manifest_issue is not None:
            issues.append(manifest_issue)
        return plan.model_copy(
            update={
                "issues": tuple(issues),
                "manifest": manifest,
                "expected_manifest_id": manifest.manifest_id,
            }
        )

    if node.cardinality.count is not None:
        keys, issues = _count_keys(node, node.cardinality.count, stage_instances)
        return CardinalityPlan(mode=mode, item_keys=keys, issues=issues)

    selection_policy = node.cardinality.selection_policy
    if selection_policy is None:
        return CardinalityPlan(
            mode=mode,
            issues=(
                _issue(
                    ReadinessReason.MISSING_EXPECTED_MANIFEST,
                    f"node {node.node_id!r} has neither count nor "
                    "selection_policy, so its expected items cannot be declared",
                ),
            ),
        )
    if selection_policy not in MANIFEST_CHILDREN_POLICIES:
        return CardinalityPlan(
            mode=mode,
            issues=(
                _issue(
                    ReadinessReason.UNKNOWN_SELECTION_POLICY,
                    f"node {node.node_id!r} uses unsupported selection_policy "
                    f"{selection_policy!r}",
                ),
            ),
        )

    base_plan, issue = _manifest_children(
        node, stage_instances, input_manifests, dependency_instances
    )
    if issue is not None:
        return CardinalityPlan(mode=mode, issues=(issue,))
    assert base_plan is not None
    manifest = base_plan.manifest
    assert manifest is not None
    manifest_issue = _complete_manifest_issue(manifest)
    if manifest_issue is not None:
        return base_plan.model_copy(update={"issues": (manifest_issue,)})

    keys = tuple(manifest.expected_artifact_slots)
    if not keys:
        return base_plan.model_copy(
            update={
                "issues": (
                    _issue(
                        ReadinessReason.MISSING_MANIFEST_KEYS,
                        f"manifest {manifest.manifest_id!r} is complete but does "
                        "not declare expected child logical keys",
                        stage_instance_id=manifest.stage_instance_id,
                    ),
                )
            }
        )
    issues: list[CardinalityIssue] = []
    if len(set(keys)) != len(keys):
        issues.append(
            _issue(
                ReadinessReason.CARDINALITY_MISMATCH,
                f"manifest {manifest.manifest_id!r} repeats an expected child key",
                stage_instance_id=manifest.stage_instance_id,
            )
        )
    if manifest.expected_count is not None and len(keys) != manifest.expected_count:
        issues.append(
            _issue(
                ReadinessReason.INCOMPLETE_MANIFEST,
                f"manifest {manifest.manifest_id!r} declares "
                f"{manifest.expected_count} expected item(s) but "
                f"{len(keys)} child key(s)",
                stage_instance_id=manifest.stage_instance_id,
            )
        )
    expected = set(keys)
    unexpected = [
        instance.logical_item_key
        for instance in _ordered_instances(stage_instances)
        if instance.logical_item_key not in expected
    ]
    if unexpected:
        issues.append(
            _issue(
                ReadinessReason.UNEXPECTED_INSTANCES,
                f"node {node.node_id!r} has stage instances outside manifest "
                f"{manifest.manifest_id!r}: " + ", ".join(sorted(set(unexpected))),
            )
        )
    return base_plan.model_copy(update={"item_keys": keys, "issues": tuple(issues)})


__all__ = [
    "MANIFEST_CHILDREN_POLICIES",
    "CardinalityIssue",
    "CardinalityPlan",
    "plan_cardinality",
]
