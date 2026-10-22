from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_FIXTURES = REPOSITORY_ROOT / "fixtures" / "contracts"
VALID_FIXTURES = CONTRACT_FIXTURES / "valid"
INVALID_FIXTURES = CONTRACT_FIXTURES / "invalid"
SCHEMA_DIR = REPOSITORY_ROOT / "schemas"


def _snake_case(name: str) -> str:
    first = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", first).lower()


@pytest.fixture(scope="session")
def repository_root() -> Path:
    return REPOSITORY_ROOT


@pytest.fixture(scope="session")
def schema_dir() -> Path:
    return SCHEMA_DIR


@pytest.fixture(scope="session")
def valid_fixtures() -> dict[str, dict[str, Any]]:
    return {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(VALID_FIXTURES.glob("*.json"))
    }


@pytest.fixture(scope="session")
def snake_case() -> Callable[[str], str]:
    return _snake_case
