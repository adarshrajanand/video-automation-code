"""FV-04 workflow definition loading, conditions, cardinality, and readiness.

This package implements the workflow engine for FV-04. It provides:

- **Workflow Loading**: YAML workflow definitions validated through
  ``WorkflowDefinition`` contract. Strict schema validation, no YAML execution.
- **Condition Evaluation**: Scalar condition language (ALWAYS, ALL, ANY, EQUALS,
  IN, GREATER_THAN, EXISTS) over scalar context. Pure functions, no side effects.
- **Cardinality Planning**: Expands workflow nodes into concrete planned items
  based on cardinality policy (one_to_one, one_to_many, many_to_one, many_to_many).
- **Readiness Engine**: Determines which stage instances are ready to execute
  based on dependencies, input manifests, gate results, and human reviews.

Core Concepts:
- **WorkflowDefinition**: Versioned YAML with nodes, edges, conditions, cardinality
- **ReadinessContext**: Immutable snapshot of run state (run, instances, manifests)
- **ReadinessResult**: Ready items, planned fan-out, blocked reasons, terminal nodes
- **CardinalityPlan**: Fan-out mapping from source instances to target items

Key Invariants:
- Pure functions: no DB access, no network, no side effects
- Deterministic: same context = same result
- No mutation of input context
- Explicit error types for condition evaluation failures

Usage:
```python
workflow = load_workflow("path/to/workflow.yaml")
context = ReadinessContext(...)
result = evaluate_readiness(context)
for instance_id in result.ready_instance_ids:
    dispatch_job(instance_id)
# Or for planned fan-out items:
for item in result.planned_items:
    dispatch_planned_item(item)
```

"""

from __future__ import annotations

from pipeline.workflow.cardinality import (
    CardinalityIssue,
    CardinalityPlan,
    plan_cardinality,
)
from pipeline.workflow.conditions import (
    ConditionEvaluationError,
    Scalar,
    evaluate_condition,
)
from pipeline.workflow.loader import (
    WorkflowLoadError,
    load_workflow,
    load_workflow_data,
    load_workflow_text,
)
from pipeline.workflow.models import (
    BlockedReason,
    PlannedItem,
    ReadinessContext,
    ReadinessReason,
    ReadinessResult,
)
from pipeline.workflow.readiness import evaluate_readiness

__all__ = [
    "BlockedReason",
    "CardinalityIssue",
    "CardinalityPlan",
    "ConditionEvaluationError",
    "PlannedItem",
    "ReadinessContext",
    "ReadinessReason",
    "ReadinessResult",
    "Scalar",
    "WorkflowLoadError",
    "evaluate_condition",
    "evaluate_readiness",
    "load_workflow",
    "load_workflow_data",
    "load_workflow_text",
    "plan_cardinality",
]
