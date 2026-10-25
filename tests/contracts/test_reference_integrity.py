from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pipeline.contracts import (
    Artifact,
    ArtifactDependency,
    CapabilityRequest,
    ContentPackage,
    EventEnvelope,
    HumanReview,
    InboxReceipt,
    InputManifest,
    InvalidationResult,
    OutboxMessage,
    QualityCheck,
    QualityEvaluation,
    QualityGateResult,
    QualityInputManifest,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "contracts" / "valid"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def test_artifact_cannot_depend_on_itself() -> None:
    payload = _fixture("artifact")
    payload["input_artifact_ids"] = [payload["artifact_id"]]

    with pytest.raises(ValidationError, match="must not list itself"):
        Artifact.model_validate(payload)


def test_artifact_dependency_endpoints_must_be_distinct() -> None:
    payload = _fixture("artifact_dependency")
    payload["parent_artifact_id"] = payload["child_artifact_id"]

    with pytest.raises(ValidationError, match="distinct artifact IDs"):
        ArtifactDependency.model_validate(payload)


def test_invalidation_result_partitions_artifacts() -> None:
    payload = _fixture("invalidation_result")
    payload["retained_artifact_ids"] = copy.deepcopy(
        payload["invalidated_artifact_ids"]
    )

    with pytest.raises(ValidationError, match="must be disjoint"):
        InvalidationResult.model_validate(payload)


def test_quality_input_hashes_must_cover_every_target() -> None:
    payload = _fixture("quality_input_manifest")
    payload["target_hashes"] = {}

    with pytest.raises(ValidationError, match="target_hashes keys"):
        QualityInputManifest.model_validate(payload)


def test_quality_evaluation_hashes_must_match_targets() -> None:
    payload = _fixture("quality_evaluation")
    payload["target_hashes"] = {}

    with pytest.raises(ValidationError, match="target_hashes keys"):
        QualityEvaluation.model_validate(payload)


def test_quality_evaluation_abstention_must_match_outcome() -> None:
    payload = _fixture("quality_evaluation")
    payload["outcome"] = "ABSTAIN"

    with pytest.raises(ValidationError, match="abstained must be true"):
        QualityEvaluation.model_validate(payload)


def test_semantic_quality_check_requires_a_rubric() -> None:
    payload = _fixture("quality_check")
    payload["rubric_version"] = None

    with pytest.raises(ValidationError, match="requires a rubric_version"):
        QualityCheck.model_validate(payload)


def test_gate_result_evaluations_must_be_unique() -> None:
    payload = _fixture("quality_gate_result")
    payload["evaluation_ids"] = [
        payload["evaluation_ids"][0],
        payload["evaluation_ids"][0],
    ]

    with pytest.raises(ValidationError, match="must not contain duplicates"):
        QualityGateResult.model_validate(payload)


def test_event_payload_must_contain_registered_references() -> None:
    payload = _fixture("event_envelope")
    payload["payload"] = {
        "run_id": "run_01",
        "stage_instance_id": "stage_speech_scene_01",
        "attempt_id": "attempt_speech_01",
    }

    with pytest.raises(ValidationError, match="missing required reference"):
        EventEnvelope.model_validate(payload)


def test_event_payload_schema_must_match_event_type() -> None:
    payload = _fixture("event_envelope")
    payload["payload_schema_version"] = "stage-started.v1"

    with pytest.raises(ValidationError, match="requires payload schema"):
        EventEnvelope.model_validate(payload)


def test_event_envelope_and_payload_run_ids_must_match() -> None:
    payload = _fixture("event_envelope")
    payload["run_id"] = "run_other"

    with pytest.raises(ValidationError, match="must match payload run_id"):
        EventEnvelope.model_validate(payload)


@pytest.mark.parametrize("field", ["stage_instance_id", "attempt_id"])
def test_event_envelope_references_must_match_payload(field: str) -> None:
    payload = _fixture("event_envelope")
    payload[field] = f"{field}_other"

    with pytest.raises(ValidationError, match=f"must match payload {field}"):
        EventEnvelope.model_validate(payload)


def test_outbox_message_event_id_must_match_nested_event() -> None:
    payload = _fixture("outbox_message")
    payload["event_id"] = "event_other"

    with pytest.raises(ValidationError, match="must match the nested event"):
        OutboxMessage.model_validate(payload)


def test_processed_inbox_receipt_requires_processed_at() -> None:
    payload = _fixture("inbox_receipt")
    payload["status"] = "PROCESSED"
    payload["processed_at"] = None

    with pytest.raises(ValidationError, match="requires processed_at"):
        InboxReceipt.model_validate(payload)


def test_content_package_active_episode_must_be_listed() -> None:
    payload = _fixture("content_package")
    payload["active_episode_id"] = "episode_other"

    with pytest.raises(ValidationError, match="active_episode_id must reference"):
        ContentPackage.model_validate(payload)


def test_complete_input_manifest_must_resolve_expected_count() -> None:
    payload = _fixture("input_manifest")
    payload["expected_count"] = 2

    with pytest.raises(ValidationError, match="exactly expected_count"):
        InputManifest.model_validate(payload)


def test_human_review_hashes_must_match_targets() -> None:
    payload = _fixture("human_review")
    payload["target_hashes"] = {
        "artifact_unknown": payload["target_hashes"][payload["target_artifact_ids"][0]]
    }

    with pytest.raises(ValidationError, match="target_hashes keys"):
        HumanReview.model_validate(payload)


def test_capability_request_and_requirements_must_agree() -> None:
    payload = _fixture("capability_request")
    payload["capability"] = "image_generation"

    with pytest.raises(ValidationError, match="must match the request capability"):
        CapabilityRequest.model_validate(payload)
