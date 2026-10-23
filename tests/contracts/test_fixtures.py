from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pipeline.contracts.registry import PUBLIC_CONTRACTS

CONTRACT_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "contracts"
INVALID_FIXTURES = CONTRACT_FIXTURES / "invalid"
VALID_FIXTURES = CONTRACT_FIXTURES / "valid"

INVALID_MANIFEST = json.loads(
    (CONTRACT_FIXTURES / "invalid_manifest.json").read_text(encoding="utf-8")
)
INVALID_CASES = INVALID_MANIFEST["invalid"]

REQUIRED_INVALID_CASES = {
    "unknown_core_field",
    "missing_schema_version",
    "wrong_schema_version",
    "missing_required_field",
    "invalid_enum",
    "naive_datetime",
    "bad_sha256",
    "duplicate_ids",
    "artifact_self_dependency",
    "quality_target_hash_missing",
    "quality_target_hash_unknown",
    "quality_abstained_mismatch",
    "quality_gate_duplicate_evaluations",
    "quality_semantic_missing_rubric",
    "event_missing_payload_reference",
    "event_payload_schema_mismatch",
    "event_run_id_mismatch",
    "outbox_event_id_mismatch",
    "lease_time_order",
    "workflow_duplicate_nodes",
    "workflow_missing_dependency",
    "workflow_cycle",
    "workflow_unknown_stage",
    "workflow_unknown_gate",
    "workflow_unknown_recovery",
    "workflow_invalid_cardinality",
    "workflow_selector_unknown_dependency",
    "stage_attempt_zero_number",
    "input_manifest_count_mismatch",
    "job_negative_delivery_count",
    "invalidation_overlap",
    "review_target_hash_mismatch",
    "content_package_active_missing",
    "shot_invalid_range",
    "routing_context_zero_attempt",
    "capability_requirements_mismatch",
    "idempotency_time_order",
    "source_ref_bad_kind",
    "source_snapshot_bad_range",
    "evidence_bad_range",
    "claim_bad_type",
    "visual_intent_bad_purpose",
    "duration_policy_bad_range",
    "script_scene_duplicate_claims",
    "script_duplicate_scenes",
    "audio_timing_bad_order",
    "research_input_bad_range",
    "research_output_duplicate_sources_payload",
    "script_generation_input_bad_duration",
    "script_generation_output_bad_scene_count_payload",
    "visual_planning_input_duplicate_scenes_payload",
    "visual_planning_output_duplicate_intents_payload",
    "speech_manifest_duplicate_audio_ids",
    "speech_manifest_hash_count_mismatch",
    "speech_manifest_unknown_scene_in_hashes",
    "speech_generation_input_duplicate_scenes",
    "speech_generation_input_narration_count_mismatch",
    "speech_generation_input_unknown_scene_in_narration",
    "speech_generation_output_duplicate_audio_ids",
    "speech_generation_output_hash_count_mismatch",
    "asr_alignment_output_duplicate_audio_timing_ids",
    "asr_alignment_output_duplicate_word_timestamp_ids",
    "word_timestamp_bad_order",
}


def test_valid_fixture_coverage_matches_the_public_registry(
    snake_case,
) -> None:
    expected = {snake_case(model_name): model_name for model_name in PUBLIC_CONTRACTS}
    actual = {path.stem: path for path in VALID_FIXTURES.glob("*.json")}

    assert set(actual) == set(expected), {
        "missing": sorted(set(expected) - set(actual)),
        "unexpected": sorted(set(actual) - set(expected)),
    }


@pytest.mark.parametrize("model_name", sorted(PUBLIC_CONTRACTS))
def test_every_public_contract_has_a_valid_fixture(
    model_name: str,
    snake_case,
) -> None:
    path = VALID_FIXTURES / f"{snake_case(model_name)}.json"
    assert path.is_file()

    model = PUBLIC_CONTRACTS[model_name]
    payload = json.loads(path.read_text(encoding="utf-8"))
    validated = model.model_validate_json(path.read_text(encoding="utf-8"))

    assert validated.model_dump(mode="json") == payload
    assert validated.schema_version == payload["schema_version"]


@pytest.mark.parametrize("model_name", sorted(PUBLIC_CONTRACTS))
def test_unknown_core_fields_are_rejected_for_every_contract(
    model_name: str,
    snake_case,
) -> None:
    model = PUBLIC_CONTRACTS[model_name]
    payload = copy.deepcopy(
        json.loads(
            (VALID_FIXTURES / f"{snake_case(model_name)}.json").read_text(
                encoding="utf-8"
            )
        )
    )
    payload["unexpected_core_field"] = True

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        model.model_validate(payload)


@pytest.mark.parametrize("model_name", sorted(PUBLIC_CONTRACTS))
def test_wrong_schema_versions_are_rejected_for_every_contract(
    model_name: str,
    snake_case,
) -> None:
    model = PUBLIC_CONTRACTS[model_name]
    payload = json.loads(
        (VALID_FIXTURES / f"{snake_case(model_name)}.json").read_text(encoding="utf-8")
    )
    payload["schema_version"] = "wrong-contract.v999"

    with pytest.raises(ValidationError):
        model.model_validate(payload)


def _required_field_cases() -> list[tuple[str, str]]:
    return [
        (model_name, field_name)
        for model_name, model in PUBLIC_CONTRACTS.items()
        for field_name, field in model.model_fields.items()
        if field.is_required()
    ]


@pytest.mark.parametrize(("model_name", "field_name"), _required_field_cases())
def test_required_fields_are_enforced(
    model_name: str,
    field_name: str,
    snake_case,
) -> None:
    model = PUBLIC_CONTRACTS[model_name]
    payload = json.loads(
        (VALID_FIXTURES / f"{snake_case(model_name)}.json").read_text(encoding="utf-8")
    )
    del payload[field_name]

    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_invalid_manifest_declares_every_invalid_fixture() -> None:
    files = {f"invalid/{path.name}" for path in INVALID_FIXTURES.glob("*.json")}
    declared = {case["fixture"] for case in INVALID_CASES}

    assert INVALID_MANIFEST["schema_version"] == "contract-fixtures.v1"
    assert declared == files
    assert len(declared) == len(INVALID_CASES)


def test_invalid_manifest_covers_required_contract_failures() -> None:
    names = {
        case["fixture"].removeprefix("invalid/").removesuffix(".json")
        for case in INVALID_CASES
    }

    assert names >= REQUIRED_INVALID_CASES


@pytest.mark.parametrize(
    "case",
    INVALID_CASES,
    ids=[case["fixture"] for case in INVALID_CASES],
)
def test_invalid_fixture_is_rejected_with_the_expected_error(
    case: dict[str, str],
) -> None:
    model = PUBLIC_CONTRACTS[case["model"]]
    path = CONTRACT_FIXTURES / case["fixture"]

    with pytest.raises(ValidationError) as captured:
        model.model_validate_json(path.read_text(encoding="utf-8"))

    assert captured.value.error_count() >= 1
    assert case["error_contains"] in str(captured.value)
