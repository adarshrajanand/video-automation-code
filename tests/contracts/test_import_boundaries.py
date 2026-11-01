from __future__ import annotations

import ast
from pathlib import Path

CONTRACT_SOURCE = Path(__file__).resolve().parents[2] / "src" / "pipeline" / "contracts"

ALLOWED_IMPORT_ROOTS = {
    "__future__",
    "dataclasses",
    "datetime",
    "enum",
    "json",
    "os",
    "pathlib",
    "pydantic",
    "pipeline",
    "re",
    "typing",
}

FORBIDDEN_IMPORT_ROOTS = {
    "aiohttp",
    "http",
    "httpx",
    "openai",
    "requests",
    "socket",
    "sqlalchemy",
    "sqlite3",
    "subprocess",
    "urllib",
}


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            roots.add(node.module.split(".", 1)[0])
    return roots


def test_contract_modules_have_no_provider_or_persistence_imports() -> None:
    modules = sorted(CONTRACT_SOURCE.glob("*.py"))
    assert modules

    for path in modules:
        roots = _imported_roots(path)
        assert not roots & FORBIDDEN_IMPORT_ROOTS, (path.name, roots)
        assert roots <= ALLOWED_IMPORT_ROOTS, (path.name, roots)
