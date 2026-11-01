from __future__ import annotations

import inspect
from enum import StrEnum

import pipeline.contracts.vocabularies as vocabularies


def _enum_classes() -> list[type[StrEnum]]:
    return [
        value
        for _, value in inspect.getmembers(vocabularies, inspect.isclass)
        if issubclass(value, StrEnum) and value is not StrEnum
    ]


def test_every_vocabulary_member_has_a_unique_non_empty_value() -> None:
    assert _enum_classes()

    for enum_type in _enum_classes():
        values = [member.value for member in enum_type]
        assert values, enum_type.__name__
        assert all(values), enum_type.__name__
        assert len(values) == len(set(values)), enum_type.__name__


def test_stage_names_match_the_stage_set() -> None:
    values = {member.value for member in vocabularies.StageName}

    assert values == vocabularies.STAGE_NAMES
    assert len(values) == 16


def test_every_failure_code_has_a_category() -> None:
    codes = set(vocabularies.FailureCode)

    assert set(vocabularies.FAILURE_CODE_CATEGORIES) == codes
    assert len(set(vocabularies.FAILURE_CODE_CATEGORIES.values())) == len(
        vocabularies.FailureCategory
    )


def test_every_event_type_has_exactly_one_payload_schema() -> None:
    event_types = set(vocabularies.EventType)
    schemas = vocabularies.EVENT_PAYLOAD_SCHEMAS

    assert set(schemas) == event_types
    assert len(set(schemas.values())) == len(event_types)
    assert all(schema.endswith(".v1") for schema in schemas.values())


def test_every_payload_schema_declares_required_fields() -> None:
    required = vocabularies.EVENT_PAYLOAD_REQUIRED_FIELDS

    assert set(required) == set(vocabularies.EVENT_PAYLOAD_SCHEMAS.values())
    for schema, fields in required.items():
        assert fields, schema
        assert all(field for field in fields), schema
        assert "run_id" in fields, schema


def test_quality_gate_and_policy_ids_are_registered() -> None:
    assert "script_gate_v1" in vocabularies.QUALITY_GATE_IDS
    assert "default_recovery_v1" in vocabularies.RECOVERY_POLICY_IDS
    assert "default_retry_v1" in vocabularies.RETRY_POLICY_IDS


def test_enum_values_preserve_declaration_order() -> None:
    assert vocabularies.enum_values(vocabularies.SpeechStrategy) == (
        "CONTINUOUS",
        "SCENE_SEGMENTED",
    )
