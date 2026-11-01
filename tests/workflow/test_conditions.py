from __future__ import annotations

import pytest

from pipeline.contracts.vocabularies import ConditionOperator
from pipeline.contracts.workflow import ConditionExpression
from pipeline.workflow import ConditionEvaluationError, evaluate_condition


def condition(operator: ConditionOperator, *operands: object) -> ConditionExpression:
    return ConditionExpression.model_validate(
        {
            "schema_version": "condition-expression.v1",
            "operator": operator.value,
            "operands": list(operands),
        }
    )


def test_missing_condition_is_enabled() -> None:
    assert evaluate_condition(None, {}) is True


def test_always_ignores_context_and_operands() -> None:
    assert evaluate_condition(condition(ConditionOperator.ALWAYS, "unused"), {}) is True


@pytest.mark.parametrize(
    ("context", "expected"),
    [
        ({}, False),
        ({"flag": None}, False),
        ({"flag": False}, True),
        ({"flag": ""}, True),
        ({"flag": 0}, True),
    ],
)
def test_exists_requires_present_non_none_key(
    context: dict[str, object], expected: bool
) -> None:
    assert (
        evaluate_condition(condition(ConditionOperator.EXISTS, "flag"), context)
        is expected
    )


@pytest.mark.parametrize(
    ("context", "expected"),
    [
        ({}, False),
        ({"mode": "A"}, True),
        ({"mode": "B"}, False),
        ({"mode": 1}, False),
    ],
)
def test_equals_uses_strict_scalar_semantics(
    context: dict[str, object], expected: bool
) -> None:
    assert (
        evaluate_condition(condition(ConditionOperator.EQUALS, "mode", "A"), context)
        is expected
    )


def test_equals_does_not_treat_booleans_as_integers() -> None:
    assert (
        evaluate_condition(
            condition(ConditionOperator.EQUALS, "value", 1), {"value": True}
        )
        is False
    )
    assert (
        evaluate_condition(
            condition(ConditionOperator.EQUALS, "value", True), {"value": 1}
        )
        is False
    )


@pytest.mark.parametrize(
    ("context", "expected"),
    [
        ({}, False),
        ({"mode": "A"}, True),
        ({"mode": "B"}, True),
        ({"mode": "C"}, False),
    ],
)
def test_in_membership(context: dict[str, object], expected: bool) -> None:
    assert (
        evaluate_condition(condition(ConditionOperator.IN, "mode", "A", "B"), context)
        is expected
    )


@pytest.mark.parametrize(
    ("context", "expected"),
    [
        ({}, False),
        ({"count": 3}, True),
        ({"count": 2}, False),
        ({"count": "3"}, False),
        ({"count": None}, False),
        ({"count": True}, False),
    ],
)
def test_greater_than_requires_real_numbers(
    context: dict[str, object], expected: bool
) -> None:
    assert (
        evaluate_condition(
            condition(ConditionOperator.GREATER_THAN, "count", 2), context
        )
        is expected
    )


def test_greater_than_rejects_non_numeric_threshold() -> None:
    with pytest.raises(ConditionEvaluationError, match="threshold must be a number"):
        evaluate_condition(
            condition(ConditionOperator.GREATER_THAN, "count", "2"), {"count": 3}
        )


@pytest.mark.parametrize(
    ("operator", "context", "expected"),
    [
        (ConditionOperator.ALL, {"a": True, "b": 1}, True),
        (ConditionOperator.ALL, {"a": True, "b": 0}, False),
        (ConditionOperator.ANY, {"a": False, "b": ""}, False),
        (ConditionOperator.ANY, {"a": False, "b": "yes"}, True),
        (ConditionOperator.ALL, {"a": True}, False),
    ],
)
def test_all_and_any_use_truthiness(
    operator: ConditionOperator, context: dict[str, object], expected: bool
) -> None:
    assert evaluate_condition(condition(operator, "a", "b"), context) is expected


def test_all_and_any_accept_one_operand() -> None:
    assert evaluate_condition(condition(ConditionOperator.ALL, "a"), {"a": 1}) is True
    assert evaluate_condition(condition(ConditionOperator.ANY, "a"), {"a": 0}) is False


def malformed_condition(
    operator: ConditionOperator, *operands: object
) -> ConditionExpression:
    # Bypass contract validation to exercise the evaluator's defensive checks.
    return ConditionExpression.model_construct(
        schema_version="condition-expression.v1",
        operator=operator,
        operands=list(operands),
    )


@pytest.mark.parametrize(
    "expression",
    [
        malformed_condition(ConditionOperator.EQUALS, "only-key"),
        malformed_condition(ConditionOperator.EXISTS, 7),
        malformed_condition(ConditionOperator.IN, "only-key"),
    ],
)
def test_invalid_operand_shapes_raise(expression: ConditionExpression) -> None:
    with pytest.raises(ConditionEvaluationError):
        evaluate_condition(expression, {"only-key": "value"})
