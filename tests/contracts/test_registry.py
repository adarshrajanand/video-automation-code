from __future__ import annotations

import re
from typing import Literal, get_args

import pytest
from pydantic import BaseModel

from pipeline.contracts import CONTRACT_MODELS, PUBLIC_CONTRACTS
from pipeline.contracts.base import Contract
from pipeline.contracts.registry import (
    contract_schema_version,
    schema_file_name,
)

SCHEMA_VERSION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]*\.v[0-9]+$")


def test_public_registry_is_derived_from_the_declared_order() -> None:
    assert list(PUBLIC_CONTRACTS) == [model.__name__ for model in CONTRACT_MODELS]
    assert len({model.__name__ for model in CONTRACT_MODELS}) == len(CONTRACT_MODELS)


def test_registry_contains_the_fv02_contract_surface() -> None:
    assert len(PUBLIC_CONTRACTS) == 63


def test_every_public_contract_is_a_strict_concrete_contract() -> None:
    for name, model in PUBLIC_CONTRACTS.items():
        assert issubclass(model, Contract), name
        assert issubclass(model, BaseModel), name
        assert not getattr(model, "__abstractmethods__", frozenset()), name
        assert model.model_config.get("extra") == "forbid", name


@pytest.mark.parametrize("name", sorted(PUBLIC_CONTRACTS))
def test_every_public_contract_declares_one_literal_version(
    name: str,
) -> None:
    model = PUBLIC_CONTRACTS[name]
    field = model.model_fields.get("schema_version")
    assert field is not None

    values = get_args(field.annotation)
    assert len(values) == 1
    assert isinstance(values[0], str)
    assert field.annotation == Literal[values[0]]
    assert SCHEMA_VERSION_PATTERN.match(values[0])


def test_contract_schema_versions_are_unique() -> None:
    versions = [contract_schema_version(model) for model in CONTRACT_MODELS]

    assert len(versions) == len(set(versions))


def test_schema_file_names_are_stable_and_unique() -> None:
    assert schema_file_name(PUBLIC_CONTRACTS["Artifact"]) == ("Artifact.schema.json")
    names = {schema_file_name(model) for model in CONTRACT_MODELS}
    assert len(names) == len(CONTRACT_MODELS)
