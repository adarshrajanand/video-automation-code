#!/usr/bin/env python3
"""Run the repository's documentation-only validation checks.

The validator is intentionally read-only. It checks the Markdown knowledge base,
the normative YAML registries, and the current Git diff without executing any
documented Python example or contacting external URLs.

Usage:

    python3 scripts/validate_docs.py

PyYAML is required for the registry checks. Install the documented dependency
before running this script in a fresh environment:

    python3 -m pip install -r requirements-docs.txt
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import unquote, urlsplit

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - exercised by setup diagnostics
    yaml = None  # type: ignore[assignment]


REGISTRY_NAMES = (
    "stages.yaml",
    "events.yaml",
    "failure_codes.yaml",
    "fast_workflow.yaml",
    "quality_gates.yaml",
    "recovery.yaml",
)

FENCE_LINE = re.compile(r"^( {0,3})([`~]{3,})(.*)$")
HEADING_LINE = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)\s*$")
MARKDOWN_LINK = re.compile(
    r"(?<!!)\[[^\]]+\]\(\s*(<[^>]*>|[^)\s]+)(?:\s+[^)]*)?\)"
)
EVENT_NAME = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")
FAILURE_CODE = re.compile(r"^[A-Z][A-Z0-9_]*\.[A-Z0-9_]+$")


@dataclass
class Fence:
    """One Markdown fenced code block and its source lines."""

    marker: str
    length: int
    info: str
    opening_line: int
    content: list[tuple[int, str]] = field(default_factory=list)


def relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def markdown_files(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*.md") if ".git" not in path.parts
    )


def registry_paths(root: Path) -> list[Path]:
    directory = root / "kb" / "docs" / "registries"
    return [directory / name for name in REGISTRY_NAMES]


def parse_fences(path: Path, root: Path, errors: list[str]) -> list[Fence]:
    """Parse Markdown fences and report unclosed or malformed fences."""

    lines = path.read_text(encoding="utf-8").splitlines()
    blocks: list[Fence] = []
    active: Fence | None = None

    for line_number, line in enumerate(lines, start=1):
        match = FENCE_LINE.match(line)
        if active is None:
            if match is None:
                continue
            marker = match.group(2)
            if len(set(marker)) != 1:
                errors.append(
                    f"{relative(path, root)}:{line_number}: mixed Markdown fence markers"
                )
                continue
            info = match.group(3).strip()
            if marker[0] == "`" and "`" in info:
                errors.append(
                    f"{relative(path, root)}:{line_number}: backtick fence info contains a backtick"
                )
            active = Fence(marker[0], len(marker), info, line_number)
            continue

        if match is not None and match.group(2)[0] == active.marker:
            closing_marker = match.group(2)
            closing_suffix = match.group(3)
            if len(closing_marker) >= active.length and not closing_suffix.strip():
                blocks.append(active)
                active = None
                continue

        active.content.append((line_number, line))

    if active is not None:
        errors.append(
            f"{relative(path, root)}:{active.opening_line}: unclosed "
            f"{active.marker * active.length} fence"
        )
        blocks.append(active)

    return blocks


def check_markdown_fences(root: Path, errors: list[str]) -> None:
    for path in markdown_files(root):
        parse_fences(path, root, errors)


def check_fenced_python(root: Path, errors: list[str]) -> None:
    for path in markdown_files(root):
        blocks = parse_fences(path, root, errors)
        for block in blocks:
            language = block.info.split()[0].lower() if block.info else ""
            if language not in {"python", "py"} or not block.content:
                continue
            source = "\n".join(line for _, line in block.content)
            try:
                ast.parse(source, filename=relative(path, root), mode="exec")
            except SyntaxError as exc:
                source_line = block.opening_line + (exc.lineno or 1)
                location = f"{relative(path, root)}:{source_line}"
                if exc.offset is not None:
                    location += f":{exc.offset}"
                errors.append(f"{location}: invalid fenced Python: {exc.msg}")


def check_internal_links(root: Path, errors: list[str]) -> None:
    for path in markdown_files(root):
        blocks = parse_fences(path, root, errors)
        fenced_lines = {
            line_number
            for block in blocks
            for line_number, _ in block.content
        }
        fenced_lines.update(block.opening_line for block in blocks)
        lines = path.read_text(encoding="utf-8").splitlines()

        for line_number, line in enumerate(lines, start=1):
            if line_number in fenced_lines:
                continue
            for match in MARKDOWN_LINK.finditer(line):
                target = match.group(1).strip()
                if target.startswith("<") and target.endswith(">"):
                    target = target[1:-1]
                parsed = urlsplit(target)
                if parsed.scheme or parsed.netloc:
                    continue

                target_path = Path(unquote(parsed.path)) if parsed.path else path
                if target_path.is_absolute():
                    resolved = target_path.resolve()
                else:
                    resolved = (path.parent / target_path).resolve()
                try:
                    resolved.relative_to(root.resolve())
                except ValueError:
                    errors.append(
                        f"{relative(path, root)}:{line_number}: internal link escapes repository: {target}"
                    )
                    continue
                if not resolved.is_file():
                    errors.append(
                        f"{relative(path, root)}:{line_number}: missing internal link target: {target}"
                    )
                    continue

                if parsed.fragment and resolved.suffix.lower() == ".md":
                    anchors = markdown_anchors(resolved, root)
                    fragment = unquote(parsed.fragment).lower()
                    if fragment not in anchors:
                        errors.append(
                            f"{relative(path, root)}:{line_number}: missing Markdown anchor "
                            f"'{parsed.fragment}' in {relative(resolved, root)}"
                        )


def markdown_anchors(path: Path, root: Path) -> set[str]:
    """Return GitHub-style heading anchors, excluding fenced code blocks."""

    blocks = parse_fences(path, root, [])
    fenced_lines = {
        line_number
        for block in blocks
        for line_number, _ in block.content
    }
    fenced_lines.update(block.opening_line for block in blocks)
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if line_number in fenced_lines:
            continue
        match = HEADING_LINE.match(line)
        if match is None:
            continue
        text = re.sub(r"<[^>]+>", "", match.group(2))
        slug = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
        slug = re.sub(r"\s+", "-", slug)
        occurrence = counts.get(slug, 0)
        counts[slug] = occurrence + 1
        anchors.add(slug if occurrence == 0 else f"{slug}-{occurrence}")
    return anchors


class UniqueKeyLoader(yaml.SafeLoader if yaml is not None else object):
    """PyYAML loader that rejects duplicate mapping keys."""


if yaml is not None:

    def construct_unique_mapping(loader: Any, node: Any, deep: bool = False) -> dict[Any, Any]:
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in mapping:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found duplicate key {key!r}",
                    key_node.start_mark,
                )
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping

    UniqueKeyLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_unique_mapping,
    )


def load_registry(path: Path, root: Path, errors: list[str]) -> dict[str, Any]:
    if not path.is_file():
        errors.append(f"missing registry file: {relative(path, root)}")
        return {}
    if yaml is None:
        errors.append(
            "YAML validation requires PyYAML; install it with "
            "'python3 -m pip install -r requirements-docs.txt'"
        )
        return {}
    try:
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = ""
        if mark is not None:
            location = f":{mark.line + 1}:{mark.column + 1}"
        errors.append(f"{relative(path, root)}{location}: invalid YAML: {exc}")
        return {}
    if not isinstance(data, dict) or not data:
        errors.append(f"{relative(path, root)}: YAML root must be a non-empty mapping")
        return {}
    return data


def mapping_items(value: Any, label: str, path: Path, root: Path, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{relative(path, root)}: {label} must be a mapping")
        return {}
    return value


def list_items(value: Any, label: str, path: Path, root: Path, errors: list[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        errors.append(f"{relative(path, root)}: {label} must be a list")
        return []
    items: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"{relative(path, root)}: {label}[{index}] must be a mapping")
        else:
            items.append(item)
    return items


def check_unique_ids(
    items: Iterable[dict[str, Any]],
    key: str,
    label: str,
    path: Path,
    root: Path,
    errors: list[str],
) -> set[str]:
    values: set[str] = set()
    for index, item in enumerate(items):
        value = item.get(key)
        if not isinstance(value, str) or not value:
            errors.append(f"{relative(path, root)}: {label}[{index}] needs string {key!r}")
            continue
        if value in values:
            errors.append(f"{relative(path, root)}: duplicate {label} {value!r}")
        values.add(value)
    return values


def check_yaml_registries(root: Path, errors: list[str]) -> None:
    for path in registry_paths(root):
        data = load_registry(path, root, errors)
        if data and not isinstance(data.get("schema_version"), str):
            errors.append(f"{relative(path, root)}: schema_version must be a string")
        if data and not isinstance(data.get("version"), str):
            errors.append(f"{relative(path, root)}: version must be a string")


def check_registry_consistency(root: Path, errors: list[str]) -> None:
    """Validate registry shapes and references between the six registries."""

    paths = {name: root / "kb" / "docs" / "registries" / name for name in REGISTRY_NAMES}
    before_loading = len(errors)
    registries = {
        name: load_registry(path, root, errors)
        for name, path in paths.items()
    }
    if len(errors) != before_loading:
        return

    stage_path = paths["stages.yaml"]
    stage_items = list_items(
        registries["stages.yaml"].get("stages"),
        "stages",
        stage_path,
        root,
        errors,
    )
    stage_names = check_unique_ids(stage_items, "stage_name", "stage", stage_path, root, errors)
    aliases: dict[str, str] = {}
    for index, item in enumerate(stage_items):
        raw_aliases = item.get("aliases", [])
        if not isinstance(raw_aliases, list) or not all(isinstance(alias, str) for alias in raw_aliases):
            errors.append(f"{relative(stage_path, root)}: stages[{index}].aliases must be a list of strings")
            continue
        for alias in raw_aliases:
            if alias in stage_names and alias != item.get("stage_name"):
                errors.append(
                    f"{relative(stage_path, root)}: stage alias {alias!r} collides with a canonical stage"
                )
            previous = aliases.get(alias)
            if previous is not None and previous != item.get("stage_name"):
                errors.append(
                    f"{relative(stage_path, root)}: stage alias {alias!r} points to both "
                    f"{previous!r} and {item.get('stage_name')!r}"
                )
            aliases[alias] = str(item.get("stage_name"))

    event_path = paths["events.yaml"]
    event_items = list_items(
        registries["events.yaml"].get("events"),
        "events",
        event_path,
        root,
        errors,
    )
    event_types = check_unique_ids(event_items, "event_type", "event", event_path, root, errors)
    payload_schemas = mapping_items(
        registries["events.yaml"].get("payload_schemas"),
        "payload_schemas",
        event_path,
        root,
        errors,
    )
    for index, item in enumerate(event_items):
        event_type = item.get("event_type")
        if isinstance(event_type, str) and not EVENT_NAME.fullmatch(event_type):
            errors.append(f"{relative(event_path, root)}: events[{index}] has invalid event_type {event_type!r}")
        schema = item.get("payload_schema_version")
        if schema not in payload_schemas:
            errors.append(
                f"{relative(event_path, root)}: event {event_type!r} references missing payload schema {schema!r}"
            )
    for schema_name, schema in payload_schemas.items():
        if not isinstance(schema_name, str) or not isinstance(schema, dict):
            errors.append(f"{relative(event_path, root)}: payload schema entries must map names to mappings")
        elif not isinstance(schema.get("required"), list):
            errors.append(f"{relative(event_path, root)}: payload schema {schema_name!r} needs a required list")

    failure_path = paths["failure_codes.yaml"]
    failure_items = list_items(
        registries["failure_codes.yaml"].get("codes"),
        "codes",
        failure_path,
        root,
        errors,
    )
    failure_codes = check_unique_ids(failure_items, "code", "failure code", failure_path, root, errors)
    for index, item in enumerate(failure_items):
        code = item.get("code")
        if isinstance(code, str) and not FAILURE_CODE.fullmatch(code):
            errors.append(f"{relative(failure_path, root)}: codes[{index}] has invalid code {code!r}")
    failure_aliases = mapping_items(
        registries["failure_codes.yaml"].get("aliases"),
        "aliases",
        failure_path,
        root,
        errors,
    )
    for alias, target in failure_aliases.items():
        if target not in failure_codes:
            errors.append(
                f"{relative(failure_path, root)}: failure alias {alias!r} targets unknown code {target!r}"
            )

    recovery_path = paths["recovery.yaml"]
    recovery_data = registries["recovery.yaml"]
    retry_policy = mapping_items(recovery_data.get("retry_policy"), "retry_policy", recovery_path, root, errors)
    recovery_policy = mapping_items(
        recovery_data.get("recovery_policy"),
        "recovery_policy",
        recovery_path,
        root,
        errors,
    )
    retry_policy_id = retry_policy.get("policy_id")
    recovery_policy_id = recovery_policy.get("policy_id")
    retry_categories = {"TRANSIENT", "RATE_LIMIT", "QUOTA"}
    configured_categories = retry_policy.get("retryable_categories", [])
    if not isinstance(configured_categories, list) or not set(configured_categories) <= retry_categories:
        errors.append(
            f"{relative(recovery_path, root)}: retryable_categories contains an unsupported category"
        )
    for field_name in ("on_unknown_outcome", "on_quality_failure", "on_repeated_failure"):
        if recovery_policy.get(field_name) not in {"RECONCILE", "REGENERATE", "HUMAN_REVIEW", "FAIL", "PAUSE"}:
            errors.append(
                f"{relative(recovery_path, root)}: recovery_policy.{field_name} has an unsupported action"
            )

    quality_path = paths["quality_gates.yaml"]
    quality_data = registries["quality_gates.yaml"]
    defaults = mapping_items(quality_data.get("check_defaults"), "check_defaults", quality_path, root, errors)
    check_items = list_items(quality_data.get("checks"), "checks", quality_path, root, errors)
    check_ids = check_unique_ids(check_items, "check_id", "quality check", quality_path, root, errors)
    check_actions = {"FAIL", "REGENERATE", "HUMAN_REVIEW"}
    check_kinds = {"DETERMINISTIC", "SEMANTIC", "SPECIALIZED", "HUMAN"}
    repair_scopes = {"NONE", "LAYER", "ASSET", "SHOT", "SCENE", "STAGE", "CUT", "SUBGRAPH", "WORKFLOW"}
    for index, item in enumerate(check_items):
        materialized = {**defaults, **item}
        if materialized.get("kind") not in check_kinds:
            errors.append(f"{relative(quality_path, root)}: checks[{index}] has an unsupported kind")
        if materialized.get("on_failure") not in check_actions:
            errors.append(f"{relative(quality_path, root)}: checks[{index}] has an unsupported on_failure action")
        if materialized.get("repair_scope") not in repair_scopes:
            errors.append(f"{relative(quality_path, root)}: checks[{index}] has an unsupported repair_scope")
        if materialized.get("kind") == "SEMANTIC" and not materialized.get("rubric_version"):
            errors.append(f"{relative(quality_path, root)}: semantic check {item.get('check_id')!r} needs rubric_version")

    gate_items = list_items(quality_data.get("gates"), "gates", quality_path, root, errors)
    gate_ids = check_unique_ids(gate_items, "gate_id", "quality gate", quality_path, root, errors)
    for index, gate in enumerate(gate_items):
        required = gate.get("required_check_ids", [])
        hard_failures = gate.get("hard_failure_codes", [])
        if not isinstance(required, list) or not set(required) <= check_ids:
            errors.append(f"{relative(quality_path, root)}: gates[{index}] references an unknown quality check")
        if not isinstance(hard_failures, list) or not set(hard_failures) <= failure_codes:
            errors.append(f"{relative(quality_path, root)}: gates[{index}] references an unknown failure code")
        if gate.get("after_max_regenerations") not in {"HUMAN_REVIEW", "FAIL"}:
            errors.append(f"{relative(quality_path, root)}: gates[{index}] has an unsupported after_max_regenerations action")

    workflow_path = paths["fast_workflow.yaml"]
    workflow_data = registries["fast_workflow.yaml"]
    nodes = list_items(workflow_data.get("nodes"), "nodes", workflow_path, root, errors)
    node_ids = check_unique_ids(nodes, "node_id", "workflow node", workflow_path, root, errors)
    policy_ids = workflow_data.get("policy_ids", [])
    if not isinstance(policy_ids, list):
        errors.append(f"{relative(workflow_path, root)}: policy_ids must be a list")
        policy_ids = []
    recovery_ids = {recovery_policy_id} if isinstance(recovery_policy_id, str) else set()
    retry_ids = {retry_policy_id} if isinstance(retry_policy_id, str) else set()
    if not set(policy_ids) <= recovery_ids:
        errors.append(f"{relative(workflow_path, root)}: policy_ids references an unknown recovery policy")

    dependencies: dict[str, list[str]] = {}
    for index, node in enumerate(nodes):
        node_id = node.get("node_id")
        if not isinstance(node_id, str):
            continue
        stage_name = node.get("stage_name")
        if stage_name not in stage_names:
            if stage_name in aliases:
                errors.append(
                    f"{relative(workflow_path, root)}: nodes[{index}] uses alias {stage_name!r}; use canonical stage name {aliases[stage_name]!r}"
                )
            else:
                errors.append(f"{relative(workflow_path, root)}: nodes[{index}] references unknown stage {stage_name!r}")
        depends_on = node.get("depends_on", [])
        if not isinstance(depends_on, list) or not all(isinstance(dep, str) for dep in depends_on):
            errors.append(f"{relative(workflow_path, root)}: node {node_id!r} needs a list of dependency node IDs")
            depends_on = []
        elif not set(depends_on) <= node_ids:
            errors.append(f"{relative(workflow_path, root)}: node {node_id!r} references an unknown dependency")
        dependencies[node_id] = depends_on
        gate_id = node.get("quality_gate_id")
        if gate_id is not None and gate_id not in gate_ids:
            errors.append(f"{relative(workflow_path, root)}: node {node_id!r} references unknown quality gate {gate_id!r}")
        recovery_id = node.get("recovery_policy_id")
        if recovery_id not in recovery_ids:
            errors.append(f"{relative(workflow_path, root)}: node {node_id!r} references unknown recovery policy {recovery_id!r}")

    visit_state: dict[str, int] = {}

    def visit(node_id: str) -> None:
        state = visit_state.get(node_id, 0)
        if state == 1:
            errors.append(f"{relative(workflow_path, root)}: workflow dependency cycle includes {node_id!r}")
            return
        if state == 2:
            return
        visit_state[node_id] = 1
        for dependency in dependencies.get(node_id, []):
            visit(dependency)
        visit_state[node_id] = 2

    for node_id in node_ids:
        visit(node_id)

    readme = root / "kb" / "docs" / "README.md"
    if readme.is_file():
        readme_text = readme.read_text(encoding="utf-8")
        for name in REGISTRY_NAMES:
            if f"registries/{name}" not in readme_text:
                errors.append(f"{relative(readme, root)}: normative registry {name!r} is not listed")


def check_git_diff(root: Path, errors: list[str]) -> None:
    for command in (("git", "diff", "--check"), ("git", "diff", "--cached", "--check")):
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
        if result.returncode:
            output = (result.stdout + result.stderr).strip()
            errors.append(f"{' '.join(command)} failed:\n{output}")


def run_check(name: str, check: Callable[[Path, list[str]], None], root: Path, errors: list[str]) -> None:
    before = len(errors)
    check(root, errors)
    if len(errors) == before:
        print(f"PASS {name}")
    else:
        print(f"FAIL {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (default: directory containing scripts/)",
    )
    parser.add_argument(
        "--skip-git-diff",
        action="store_true",
        help="skip both working-tree and staged git diff whitespace checks",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    errors: list[str] = []

    checks: list[tuple[str, Callable[[Path, list[str]], None]]] = [
        ("balanced Markdown fences", check_markdown_fences),
        ("valid YAML in kb/docs/registries/", check_yaml_registries),
        ("valid fenced Python examples", check_fenced_python),
        ("canonical registry/reference consistency", check_registry_consistency),
        ("internal Markdown links", check_internal_links),
    ]
    if not args.skip_git_diff:
        checks.append(("git diff --check", check_git_diff))

    for name, check in checks:
        run_check(name, check, root, errors)

    errors = list(dict.fromkeys(errors))
    if errors:
        print("\nDocumentation validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("\nDocumentation validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
