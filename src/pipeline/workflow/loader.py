"""Versioned YAML workflow definition loader.

The loader is deliberately small: it parses a local file with
``yaml.safe_load`` and validates the resulting mapping exclusively through the
canonical :class:`pipeline.contracts.WorkflowDefinition` model. There is no
second workflow schema and no code execution.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from pipeline.contracts.workflow import WorkflowDefinition


class WorkflowLoadError(ValueError):
    """A workflow file or definition is not safe and valid."""


def _safe_load(document: str, *, source: str) -> Any:
    try:
        return yaml.safe_load(document)
    except yaml.YAMLError as error:
        raise WorkflowLoadError(f"{source}: invalid YAML: {error}") from error


def load_workflow_data(data: Any, *, source: str = "<memory>") -> WorkflowDefinition:
    """Validate already-parsed YAML-compatible data as a workflow definition."""

    if not isinstance(data, dict):
        raise WorkflowLoadError(
            f"{source}: workflow document must be a YAML mapping, got "
            f"{type(data).__name__}"
        )
    try:
        return WorkflowDefinition.model_validate(data)
    except ValidationError as error:
        raise WorkflowLoadError(
            f"{source}: invalid workflow definition: {error}"
        ) from error


def load_workflow_text(
    document: str, *, source: str = "<memory>"
) -> WorkflowDefinition:
    """Parse and validate one versioned YAML workflow document."""

    data = _safe_load(document, source=source)
    return load_workflow_data(data, source=source)


def load_workflow(path: Path | str) -> WorkflowDefinition:
    """Read, safely parse, and statically validate one workflow YAML file."""

    resolved = Path(path).expanduser()
    try:
        document = resolved.read_text(encoding="utf-8")
    except OSError as error:
        raise WorkflowLoadError(
            f"{resolved}: cannot read workflow definition: {error}"
        ) from error
    return load_workflow_text(document, source=str(resolved))


__all__ = [
    "WorkflowLoadError",
    "load_workflow",
    "load_workflow_data",
    "load_workflow_text",
]
