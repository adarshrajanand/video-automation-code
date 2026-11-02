"""Render the public contract field atlas as Markdown.

The source of truth is the live Pydantic registry, not a hand-maintained list.
Run from the repository root:

    uv run python scripts/generate_contract_atlas.py > CONTRACT_FIELD_ATLAS.md
"""

from __future__ import annotations

import inspect
import re
from enum import StrEnum
from typing import get_args

from pipeline.contracts import CONTRACT_MODELS, vocabularies

MODULE_TITLES: dict[str, str] = {
    "base": "Base and error models",
    "config": "Configuration and run overrides",
    "workflow": "Workflow definitions",
    "execution": "Runs, stages, attempts, manifests, recovery policies",
    "jobs": "Jobs and leases",
    "capabilities": "Capability requests, results, execution and budget records",
    "routing": "Routing, resource placement, provider invocation",
    "artifacts": "Immutable artifacts, pointers, invalidation",
    "quality": "Quality checks, evaluations, gates, repair",
    "review": "Human review and publication",
    "events": "Events, outbox, inbox",
    "profiles": "Policy and domain/channel profiles",
    "editorial": "Content package hierarchy and composition references",
    "composition": "Renderer-neutral composition and manifests",
    "content": "Research, script, speech, and timing content",
    "capability_payloads": "Typed payloads exchanged with capabilities",
}

REPOSITORY_MODULES: tuple[str, ...] = (
    "artifacts",
    "capabilities",
    "control",
    "editorial",
    "events",
    "execution",
    "quality",
)


def module_of(model: type) -> str:
    """Return the short contract module name for one model."""

    return model.__module__.rsplit(".", 1)[-1]


def type_text(annotation: object) -> str:
    """Render a field annotation without noisy ``typing`` prefixes.

    CPython embeds object addresses in default ``repr`` output for functions and
    validators, for example ``<function _ensure_utc at 0x7f...>``. Dropping the
    address keeps the atlas byte-identical across processes and machines.
    """

    text = str(annotation)
    text = re.sub(r"(?<= at )0x[0-9a-fA-F]+", "", text)
    return (
        text.replace("typing.", "")
        .replace("pipeline.contracts.", "")
        .replace("<class '", "")
        .replace("'>", "")
    )


def default_text(field: object) -> str:
    """Render a field default as compact Markdown."""

    if field.is_required():  # type: ignore[attr-defined]
        return "required"
    default = field.default  # type: ignore[attr-defined]
    if hasattr(default, "value"):
        default = default.value
    if default is None:
        return "`null`"
    if isinstance(default, str):
        return f"`{default}`"
    if isinstance(default, list) and not default:
        return "`[]`"
    if isinstance(default, dict) and not default:
        return "`{}`"
    return f"`{default!r}`"


def repository_map() -> dict[type, tuple[type, str]]:
    """Map contract models to the repository that persists them."""

    mapping: dict[type, tuple[type, str]] = {}
    for module_name in REPOSITORY_MODULES:
        module = __import__(
            f"pipeline.storage.repositories.{module_name}",
            fromlist=["unused"],
        )
        for _, candidate in inspect.getmembers(module, inspect.isclass):
            name = getattr(candidate, "__name__", "")
            if not name.endswith("Repository"):
                continue
            if not hasattr(candidate, "table") or not hasattr(candidate, "model"):
                continue
            mapping[candidate.model] = (candidate, module_name)
    return mapping


def anchor(title: str) -> str:
    """Return the GitHub-style anchor for a section title."""

    return (
        title.lower()
        .replace(" ", "-")
        .replace(",", "")
        .replace("/", "")
        .replace("(", "")
        .replace(")", "")
    )


def render() -> str:
    """Return the complete Markdown atlas."""

    rows: list[tuple[type, str]] = []
    for model in CONTRACT_MODELS:
        schema = get_args(model.model_fields["schema_version"].annotation)
        rows.append((model, schema[0] if schema else "?"))

    repos = repository_map()
    lines: list[str] = [
        "# Contract Field Atlas",
        "",
        "Generated from the live Pydantic contract registry. It lists every public",
        "contract model, every field, its type, whether it is required, and its",
        "default. The `Durable mapping` line shows the SQLite table and extracted",
        "columns used by the repository layer, when the model has one.",
        "",
        f"- Contract models: **{len(CONTRACT_MODELS)}**",
        (f"- Fields: **{sum(len(model.model_fields) for model in CONTRACT_MODELS)}**"),
        f"- Repository-backed models: **{len(repos)}**",
        "",
        "Regenerate from the repository root with:",
        "",
        "```bash",
        "uv run python scripts/generate_contract_atlas.py > CONTRACT_FIELD_ATLAS.md",
        "```",
        "",
        "> `schema_version` is a required literal discriminator and is shown once",
        "> per model rather than repeated in the field table.",
        "",
        "## Contents",
        "",
    ]

    for module_name, title in MODULE_TITLES.items():
        count = sum(1 for model, _ in rows if module_of(model) == module_name)
        if count:
            lines.append(f"- [{title}](#{anchor(title)}) — {count} models")
    lines.extend(
        [
            "- [Vocabulary values](#vocabulary-values)",
            "- [Repository-backed models](#repository-backed-models)",
            "",
        ]
    )

    for module_name, title in MODULE_TITLES.items():
        models = [
            (model, schema) for model, schema in rows if module_of(model) == module_name
        ]
        if not models:
            continue
        lines.extend([f"## {title}", ""])
        for model, schema_version in models:
            lines.extend(
                [
                    f"### `{model.__name__}`",
                    "",
                    f"`schema_version`: `{schema_version}`",
                    "",
                ]
            )
            if model in repos:
                repo, repo_module = repos[model]
                columns = ", ".join(f"`{column}`" for column in repo.columns)
                keys = ", ".join(f"`{column}`" for column in repo.key_columns)
                lines.extend(
                    [
                        (
                            f"**Durable mapping:** `{repo.table}` (repository "
                            f"`{repo.__name__}` in `{repo_module}.py`); keys {keys}; "
                            f"extracted columns {columns}."
                        ),
                        "",
                    ]
                )
            lines.extend(
                [
                    "| Field | Type | Required | Default |",
                    "|---|---|---|---|",
                ]
            )
            for field_name, field in model.model_fields.items():
                if field_name == "schema_version":
                    continue
                required = "yes" if field.is_required() else "no"
                lines.append(
                    f"| `{field_name}` | `{type_text(field.annotation)}` | "
                    f"{required} | {default_text(field)} |"
                )
            lines.append("")

    lines.extend(["## Vocabulary values", ""])
    for name, candidate in sorted(vars(vocabularies).items()):
        if not inspect.isclass(candidate):
            continue
        if not issubclass(candidate, StrEnum):
            continue
        if candidate.__module__ != vocabularies.__name__:
            continue
        values = ", ".join(f"`{member.value}`" for member in candidate)
        lines.append(f"- **`{name}`**: {values}")
    lines.append("")

    lines.extend(
        [
            "## Repository-backed models",
            "",
            "| Contract | Table | Repository | Key columns |",
            "|---|---|---|---|",
        ]
    )
    for model, (repo, _) in sorted(repos.items(), key=lambda item: item[1][0].table):
        keys = ", ".join(f"`{column}`" for column in repo.key_columns)
        lines.append(
            f"| `{model.__name__}` | `{repo.table}` | `{repo.__name__}` | {keys} |"
        )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    print(render())
