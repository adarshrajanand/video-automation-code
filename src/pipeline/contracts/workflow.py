"""Workflow definition contracts and static graph validation.

The static graph is versioned and immutable. Runtime readiness and fan-out are
separate concerns: this module validates only the declared nodes, dependency
edges, selectors, cardinality, and registry references needed to load a graph
safely.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from pipeline.contracts.base import Contract, NonEmptyStr, OpaqueId, PositiveInt
from pipeline.contracts.vocabularies import (
    QUALITY_GATE_IDS,
    RECOVERY_POLICY_IDS,
    CardinalityMode,
    ConditionOperator,
    InputSelectorKind,
    StageName,
)

type ConditionOperand = str | int | float | bool | None


class InputSelector(Contract):
    """Where a node obtains eligible inputs; not the resolved runtime manifest."""

    schema_version: Literal["input-selector.v1"]
    kind: InputSelectorKind
    dependency_node_ids: list[OpaqueId] = Field(default_factory=list)
    artifact_types: list[NonEmptyStr] = Field(default_factory=list)
    selection_policy: NonEmptyStr | None = None

    @model_validator(mode="after")
    def _validate_unique_lists(self) -> InputSelector:
        if len(set(self.dependency_node_ids)) != len(self.dependency_node_ids):
            raise ValueError("dependency_node_ids must not contain duplicates")
        if len(set(self.artifact_types)) != len(self.artifact_types):
            raise ValueError("artifact_types must not contain duplicates")
        return self


class ConditionExpression(Contract):
    """A bounded static condition; operands are scalar JSON values only."""

    schema_version: Literal["condition-expression.v1"]
    operator: ConditionOperator
    operands: list[ConditionOperand] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_operand_arity(self) -> ConditionExpression:
        minimum_by_operator = {
            ConditionOperator.ALL: 1,
            ConditionOperator.ANY: 1,
            ConditionOperator.EQUALS: 2,
            ConditionOperator.IN: 2,
            ConditionOperator.GREATER_THAN: 2,
            ConditionOperator.EXISTS: 1,
        }
        minimum = minimum_by_operator.get(self.operator)
        if minimum is not None and len(self.operands) < minimum:
            raise ValueError(
                f"operator {self.operator.value!r} requires at least "
                f"{minimum} operand(s)"
            )
        return self


class CardinalityPolicy(Contract):
    """Declared expansion/fan-in behavior for one workflow node."""

    schema_version: Literal["cardinality.v1"]
    mode: CardinalityMode
    count: PositiveInt | None = None
    selection_policy: NonEmptyStr | None = None
    expected_manifest_id: OpaqueId | None = None

    @model_validator(mode="after")
    def _validate_cardinality(self) -> CardinalityPolicy:
        if self.mode is CardinalityMode.ONE_TO_ONE:
            if self.count not in (None, 1):
                raise ValueError("one_to_one cardinality allows only count 1")
            if self.selection_policy is not None:
                raise ValueError("one_to_one cardinality must not expand children")
        elif self.mode is CardinalityMode.ONE_TO_MANY:
            if self.count is None and self.selection_policy is None:
                raise ValueError(
                    "one_to_many without a count requires an explicit selection_policy"
                )
        elif self.mode is CardinalityMode.MANY_TO_ONE:
            if self.count not in (None, 1):
                raise ValueError("many_to_one cardinality allows only count 1")
        elif (
            self.mode is CardinalityMode.MANY_TO_MANY
            and self.count is None
            and self.selection_policy is None
        ):
            raise ValueError(
                "many_to_many without a count requires an explicit selection_policy"
            )
        return self


class StageNode(Contract):
    """One node in one immutable workflow definition revision."""

    schema_version: Literal["stage-node.v1"]
    node_id: OpaqueId
    stage_name: StageName
    depends_on: list[OpaqueId] = Field(default_factory=list)
    input_selector: InputSelector
    cardinality: CardinalityPolicy
    quality_gate_id: NonEmptyStr | None = None
    recovery_policy_id: NonEmptyStr | None = None
    enabled_when: ConditionExpression | None = None
    implementation_version: NonEmptyStr

    @model_validator(mode="after")
    def _validate_node_references(self) -> StageNode:
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("depends_on must not contain duplicates")
        if self.node_id in self.depends_on:
            raise ValueError("a stage node must not depend on itself")
        if not set(self.input_selector.dependency_node_ids) <= set(self.depends_on):
            raise ValueError(
                "input selector dependency_node_ids must be declared depends_on "
                "nodes in the same workflow"
            )
        if (
            self.quality_gate_id is not None
            and self.quality_gate_id not in QUALITY_GATE_IDS
        ):
            raise ValueError(f"unknown quality gate id {self.quality_gate_id!r}")
        if (
            self.recovery_policy_id is not None
            and self.recovery_policy_id not in RECOVERY_POLICY_IDS
        ):
            raise ValueError(f"unknown recovery policy id {self.recovery_policy_id!r}")
        return self


class WorkflowDefinition(Contract):
    """Versioned workflow graph with static validation and registry checks."""

    schema_version: Literal["workflow-definition.v1"]
    workflow_id: OpaqueId
    version: NonEmptyStr
    nodes: list[StageNode]
    policy_ids: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_graph(self) -> WorkflowDefinition:
        if not self.nodes:
            raise ValueError("a workflow definition must contain at least one node")
        if len(set(self.policy_ids)) != len(self.policy_ids):
            raise ValueError("policy_ids must not contain duplicates")

        node_ids = [node.node_id for node in self.nodes]
        duplicates = {node_id for node_id in node_ids if node_ids.count(node_id) > 1}
        if duplicates:
            raise ValueError(
                "duplicate workflow node IDs: " + ", ".join(sorted(duplicates))
            )

        known = set(node_ids)
        dependency_map: dict[str, list[str]] = {}
        for node in self.nodes:
            missing = [
                dependency for dependency in node.depends_on if dependency not in known
            ]
            if missing:
                raise ValueError(
                    f"node {node.node_id!r} depends on missing node(s): "
                    + ", ".join(sorted(missing))
                )
            missing_selectors = [
                dependency
                for dependency in node.input_selector.dependency_node_ids
                if dependency not in known
            ]
            if missing_selectors:
                raise ValueError(
                    f"node {node.node_id!r} selector references missing node(s): "
                    + ", ".join(sorted(missing_selectors))
                )
            dependency_map[node.node_id] = list(node.depends_on)

        # Kahn's algorithm detects cycles, including self-dependencies.
        indegree = {
            node_id: len(dependencies)
            for node_id, dependencies in dependency_map.items()
        }
        ready = [node_id for node_id, degree in indegree.items() if degree == 0]
        visited = 0
        while ready:
            current = ready.pop()
            visited += 1
            for node_id, dependencies in dependency_map.items():
                if current in dependencies:
                    indegree[node_id] -= 1
                    if indegree[node_id] == 0:
                        ready.append(node_id)
        if visited != len(dependency_map):
            raise ValueError("workflow contains a dependency cycle")

        return self


__all__ = [
    "CardinalityPolicy",
    "ConditionExpression",
    "InputSelector",
    "StageNode",
    "WorkflowDefinition",
]
