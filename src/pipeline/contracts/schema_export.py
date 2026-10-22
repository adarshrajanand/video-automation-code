"""Deterministic JSON Schema export for every public contract.

Exported files are committed under ``schemas/`` and checked in CI with
``python -m pipeline contracts export-schemas --check``. The manifest records a
content hash for each schema so browser/editor tooling can also detect drift.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.contracts.registry import (
    PUBLIC_CONTRACTS,
    contract_schema_version,
    schema_file_name,
)
from pipeline.fingerprints import sha256_bytes

MANIFEST_FILE = "manifest.json"
MANIFEST_VERSION = "1"
SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
GENERATED_BY = "python -m pipeline contracts export-schemas"
_SCHEMA_SUFFIX = ".schema.json"


@dataclass(frozen=True, slots=True)
class SchemaExportResult:
    """Outcome of one schema export or drift check."""

    output_dir: Path
    written: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    drifted: tuple[str, ...] = ()
    extra: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not (self.missing or self.drifted or self.extra)


def build_schema(model_name: str) -> dict[str, Any]:
    """Build one deterministic JSON Schema document."""

    model = PUBLIC_CONTRACTS[model_name]
    schema = model.model_json_schema(mode="validation")
    schema["$id"] = f"urn:pipeline:contract:{model_name}"
    schema["$schema"] = SCHEMA_DIALECT
    schema["x-contract-schema-version"] = contract_schema_version(model)
    return schema


def render_schema_bytes(model_name: str) -> bytes:
    """Render one schema file exactly as committed."""

    return (
        json.dumps(
            build_schema(model_name),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _build_manifest(schema_bytes: dict[str, bytes]) -> bytes:
    contracts = []
    for model_name in sorted(PUBLIC_CONTRACTS):
        model = PUBLIC_CONTRACTS[model_name]
        contracts.append(
            {
                "model": model_name,
                "schema_file": schema_file_name(model),
                "schema_version": contract_schema_version(model),
                "sha256": sha256_bytes(schema_bytes[model_name]),
            }
        )
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "schema_dialect": SCHEMA_DIALECT,
        "generated_by": GENERATED_BY,
        "public_contract_count": len(contracts),
        "contracts": contracts,
    }
    return (
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def render_all_schemas() -> dict[str, bytes]:
    """Return every expected file name and its exact committed bytes."""

    schema_bytes = {
        model_name: render_schema_bytes(model_name) for model_name in PUBLIC_CONTRACTS
    }
    files = {
        schema_file_name(PUBLIC_CONTRACTS[model_name]): content
        for model_name, content in schema_bytes.items()
    }
    files[MANIFEST_FILE] = _build_manifest(schema_bytes)
    return files


def default_schema_dir() -> Path:
    """Resolve the repository ``schemas/`` directory from the current project."""

    configured = os.environ.get("PIPELINE_SCHEMA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    here = Path.cwd().resolve()
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate / "schemas"
    return Path(__file__).resolve().parents[3] / "schemas"


def export_schemas(output_dir: Path) -> SchemaExportResult:
    """Write every schema and the manifest, removing stale schema files."""

    rendered = render_all_schemas()
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in rendered.items():
        (output_dir / name).write_bytes(content)
    extra = tuple(
        sorted(
            path.name
            for path in output_dir.glob(f"*{_SCHEMA_SUFFIX}")
            if path.name not in rendered
        )
    )
    for name in extra:
        (output_dir / name).unlink()
    return SchemaExportResult(output_dir=output_dir, written=tuple(sorted(rendered)))


def check_schemas(output_dir: Path) -> SchemaExportResult:
    """Compare committed files against freshly rendered schemas."""

    rendered = render_all_schemas()
    missing: list[str] = []
    drifted: list[str] = []
    for name, content in rendered.items():
        path = output_dir / name
        if not path.is_file():
            missing.append(name)
        elif path.read_bytes() != content:
            drifted.append(name)
    extra = tuple(
        sorted(
            path.name
            for path in output_dir.glob(f"*{_SCHEMA_SUFFIX}")
            if path.name not in rendered
        )
    )
    return SchemaExportResult(
        output_dir=output_dir,
        missing=tuple(sorted(missing)),
        drifted=tuple(sorted(drifted)),
        extra=extra,
    )


__all__ = [
    "GENERATED_BY",
    "MANIFEST_FILE",
    "MANIFEST_VERSION",
    "SCHEMA_DIALECT",
    "SchemaExportResult",
    "build_schema",
    "check_schemas",
    "default_schema_dir",
    "export_schemas",
    "render_all_schemas",
    "render_schema_bytes",
]
