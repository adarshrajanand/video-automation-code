"""Deterministic evaluation of bounded ``enabled_when`` conditions.

Operands are scalar JSON values. String operands name keys in an explicit
scalar context; the evaluator never imports or evaluates Python source.

Semantics
---------
``ALWAYS``
    Always true. Any operands are ignored.
``ALL`` / ``ANY``
    Every operand names a context key. Missing keys are false. The values are
    combined with Python truthiness (``0``, ``""``, ``False`` and ``None`` are
    false), which keeps the rule explicit and boring.
``EQUALS``
    Operands are ``[key, expected]``. A missing key is false. Booleans compare
    only with booleans; other numeric values compare numerically.
``IN``
    Operands are ``[key, candidate, ...]``. A missing key is false, otherwise
    the context value is compared to each candidate with the ``EQUALS`` rule.
``GREATER_THAN``
    Operands are ``[key, threshold]``. The context value and threshold must be
    real numbers (booleans are not numbers here); a missing or non-numeric
    context value is false. A non-numeric threshold is an authoring error.
``EXISTS``
    Operands are ``[key]``. True when the key is present and its value is not
    ``None``. Empty strings and zero count as present.
"""

from __future__ import annotations

from collections.abc import Mapping

from pipeline.contracts.vocabularies import ConditionOperator
from pipeline.contracts.workflow import ConditionExpression

type Scalar = str | int | float | bool | None


class ConditionEvaluationError(ValueError):
    """Raised when a condition's operands cannot be evaluated safely."""


def _key(operand: Scalar, *, position: int) -> str:
    if not isinstance(operand, str) or not operand:
        raise ConditionEvaluationError(
            f"operand {position} must be a non-empty context key string"
        )
    return operand


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _scalar_equal(left: object, right: object) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if _is_number(left) and _is_number(right):
        return float(left) == float(right)
    return type(left) is type(right) and left == right


def _operand_count(expression: ConditionExpression, expected: int) -> None:
    if len(expression.operands) != expected:
        raise ConditionEvaluationError(
            f"operator {expression.operator.value!r} requires exactly "
            f"{expected} operand(s), got {len(expression.operands)}"
        )


def evaluate_condition(
    expression: ConditionExpression | None,
    context: Mapping[str, Scalar],
) -> bool:
    """Evaluate one static condition against an explicit scalar context."""

    if expression is None:
        return True

    operator = expression.operator
    operands = expression.operands

    if operator is ConditionOperator.ALWAYS:
        return True

    if operator in (ConditionOperator.ALL, ConditionOperator.ANY):
        if not operands:
            raise ConditionEvaluationError(
                f"operator {operator.value!r} requires at least one operand"
            )
        values = []
        for index, operand in enumerate(operands):
            key = _key(operand, position=index)
            values.append(bool(context.get(key)))
        return all(values) if operator is ConditionOperator.ALL else any(values)

    if operator is ConditionOperator.EXISTS:
        _operand_count(expression, 1)
        key = _key(operands[0], position=0)
        return key in context and context[key] is not None

    if operator is ConditionOperator.EQUALS:
        _operand_count(expression, 2)
        key = _key(operands[0], position=0)
        if key not in context:
            return False
        return _scalar_equal(context[key], operands[1])

    if operator is ConditionOperator.IN:
        if len(operands) < 2:
            raise ConditionEvaluationError(
                "operator 'IN' requires a key and at least one candidate"
            )
        key = _key(operands[0], position=0)
        if key not in context:
            return False
        return any(_scalar_equal(context[key], candidate) for candidate in operands[1:])

    if operator is ConditionOperator.GREATER_THAN:
        _operand_count(expression, 2)
        key = _key(operands[0], position=0)
        threshold = operands[1]
        if not _is_number(threshold):
            raise ConditionEvaluationError(
                "GREATER_THAN threshold must be a number, not a boolean or string"
            )
        if key not in context:
            return False
        value = context[key]
        if not _is_number(value):
            return False
        return float(value) > float(threshold)

    raise ConditionEvaluationError(f"unsupported condition operator {operator!r}")


__all__ = [
    "ConditionEvaluationError",
    "Scalar",
    "evaluate_condition",
]
