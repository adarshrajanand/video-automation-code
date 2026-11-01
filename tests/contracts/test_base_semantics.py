from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Literal

import pytest
from pydantic import ValidationError

from pipeline.contracts import (
    Artifact,
    Contract,
    LayerInstance,
    MetadataContract,
    NormalizedError,
    RunOverrides,
    StageInstance,
    WorkflowRun,
)


def _copy(payload: dict) -> dict:
    return {key: value for key, value in payload.items()}


def test_contract_requires_a_schema_version() -> None:
    with pytest.raises(ValidationError, match="schema_version"):
        Contract.model_validate({})


def test_unknown_core_fields_are_rejected(valid_fixtures) -> None:
    payload = _copy(valid_fixtures["run_overrides"])
    payload["unexpected"] = True

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RunOverrides.model_validate(payload)


def test_missing_required_fields_are_rejected(valid_fixtures) -> None:
    payload = _copy(valid_fixtures["workflow_run"])
    payload.pop("run_id")

    with pytest.raises(ValidationError, match="Field required"):
        WorkflowRun.model_validate(payload)


def test_schema_versions_are_literal_and_checked(valid_fixtures) -> None:
    payload = _copy(valid_fixtures["run_overrides"])
    payload["schema_version"] = "run-overrides.v2"

    with pytest.raises(ValidationError, match=r"run-overrides\.v1"):
        RunOverrides.model_validate(payload)


def test_strict_ids_reject_non_strings(valid_fixtures) -> None:
    payload = _copy(valid_fixtures["workflow_run"])
    payload["run_id"] = 42

    with pytest.raises(ValidationError, match="valid string"):
        WorkflowRun.model_validate(payload)


def test_strict_ids_reject_blank_values(valid_fixtures) -> None:
    payload = _copy(valid_fixtures["workflow_run"])
    payload["run_id"] = "   "

    with pytest.raises(ValidationError):
        WorkflowRun.model_validate(payload)


def test_naive_datetimes_are_rejected(valid_fixtures) -> None:
    payload = _copy(valid_fixtures["workflow_run"])
    payload["created_at"] = "2026-10-21T12:00:00"
    payload["updated_at"] = None

    with pytest.raises(ValidationError, match="timezone-aware"):
        WorkflowRun.model_validate(payload)


def test_numeric_datetime_timestamps_are_rejected(valid_fixtures) -> None:
    payload = _copy(valid_fixtures["workflow_run"])
    payload["created_at"] = 1761076800
    payload["updated_at"] = None

    with pytest.raises(ValidationError, match="not numeric timestamps"):
        WorkflowRun.model_validate(payload)


def test_datetimes_are_normalized_to_utc(valid_fixtures) -> None:
    payload = _copy(valid_fixtures["workflow_run"])
    payload["created_at"] = "2026-10-21T14:00:00+02:00"
    payload["updated_at"] = "2026-10-21T12:10:00Z"

    run = WorkflowRun.model_validate(payload)

    assert run.created_at == datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
    assert run.created_at.utcoffset() == timedelta(0)


def test_updated_at_cannot_precede_created_at(valid_fixtures) -> None:
    payload = _copy(valid_fixtures["workflow_run"])
    payload["created_at"] = "2026-10-21T11:00:00Z"
    payload["updated_at"] = "2026-10-21T10:00:00Z"

    with pytest.raises(ValidationError, match="updated_at must not be earlier"):
        WorkflowRun.model_validate(payload)


@pytest.mark.parametrize(
    "digest",
    [
        "F" * 64,
        "a" * 63,
        "a" * 65,
        "g" * 64,
    ],
)
def test_sha256_fields_require_lowercase_hex(valid_fixtures, digest: str) -> None:
    payload = _copy(valid_fixtures["artifact"])
    payload["sha256"] = digest

    with pytest.raises(ValidationError):
        Artifact.model_validate(payload)


def test_sha256_fields_reject_non_strings(valid_fixtures) -> None:
    payload = _copy(valid_fixtures["artifact"])
    payload["sha256"] = hashlib.sha256(b"x").digest()

    with pytest.raises(ValidationError):
        Artifact.model_validate(payload)


def test_enum_strings_are_accepted_and_unknown_values_rejected(
    valid_fixtures,
) -> None:
    payload = _copy(valid_fixtures["stage_instance"])
    payload["execution_status"] = "SUCCEEDED"
    assert StageInstance.model_validate(payload).execution_status.value == ("SUCCEEDED")

    payload["execution_status"] = "DONE"
    with pytest.raises(ValidationError, match="Input should be"):
        StageInstance.model_validate(payload)


def test_assignments_are_revalidated(valid_fixtures) -> None:
    run = WorkflowRun.model_validate(valid_fixtures["workflow_run"])

    with pytest.raises(ValidationError, match="Input should be"):
        run.status = "DONE"


def test_extension_fields_accept_nested_json(valid_fixtures) -> None:
    payload = _copy(valid_fixtures["layer_instance"])
    payload["properties"] = {
        "fit": "cover",
        "opacity": 0.75,
        "crop": {"x": 0, "y": 1, "width": 1920},
        "masks": ["subject", None, 3],
    }

    layer = LayerInstance.model_validate(payload)

    assert layer.properties["crop"] == {"x": 0, "y": 1, "width": 1920}


def test_extension_fields_do_not_relax_core_fields(valid_fixtures) -> None:
    payload = _copy(valid_fixtures["layer_instance"])
    payload["unexpected"] = {"anything": True}

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        LayerInstance.model_validate(payload)


def test_metadata_contract_allows_explicit_extension_fields() -> None:
    class DiagnosticRecord(MetadataContract):
        schema_version: Literal["diagnostic-record.v1"]
        value: int

    record = DiagnosticRecord.model_validate(
        {"schema_version": "diagnostic-record.v1", "value": 1, "extra": "ok"}
    )

    assert record.model_extra == {"extra": "ok"}


def test_normalized_error_requires_matching_failure_category(
    valid_fixtures,
) -> None:
    payload = _copy(valid_fixtures["normalized_error"])
    payload["category"] = "INTERNAL"

    with pytest.raises(ValidationError, match="belongs to category"):
        NormalizedError.model_validate(payload)
