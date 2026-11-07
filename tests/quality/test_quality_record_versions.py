"""Wire-format versioning for quality artifacts outside SQLite.

Review 4501750689 found that ``gold-example`` and ``threshold-record`` changed
their timestamp keys/values while keeping the v1 schema version, so previously
saved files failed with ``KeyError``. These tests pin the v2 wire shape and the
explicit v1 -> v2 conversion on load.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pipeline.fingerprints import (
    datetime_from_unix_microseconds,
    unix_microseconds,
)
from pipeline.quality.gold import (
    GOLD_EXAMPLE_SCHEMA_VERSION,
    GoldExample,
)
from pipeline.quality.report import QualityReport
from pipeline.quality.thresholds import (
    THRESHOLD_RECORD_SCHEMA_VERSION,
    ThresholdRecord,
)

CREATED = datetime(2026, 10, 21, 9, 0, 0, 123456, tzinfo=UTC)
UPDATED = datetime(2026, 10, 21, 10, 30, 0, 654321, tzinfo=UTC)


def _gold_example() -> GoldExample:
    return GoldExample(
        check_id="check_demo",
        evaluator="demo_evaluator",
        evaluator_version="1.0.0",
        created_timestamp_micro=CREATED,
    )


def _threshold_record() -> ThresholdRecord:
    return ThresholdRecord(
        gate_id="gate_demo",
        check_id="check_demo",
        dimension_name="technical_quality",
        created_timestamp_micro=CREATED,
        updated_timestamp_micro=UPDATED,
    )


def _to_v1(
    dictionary: dict,
    *,
    version: str,
    timestamps: tuple[tuple[str, str], ...],
) -> dict:
    """Rewrite a v2 dictionary into the pre-change v1 wire shape."""

    legacy = dict(dictionary)
    legacy["schema_version"] = version
    for legacy_key, current_key in timestamps:
        value = legacy.pop(current_key)
        legacy[legacy_key] = datetime_from_unix_microseconds(value).isoformat()
    return legacy


def test_gold_example_dict_v1_upgrades_to_v2() -> None:
    current = _gold_example()

    loaded = GoldExample.from_dict(
        _to_v1(
            current.to_dict(),
            version="gold-example.v1",
            timestamps=(("created_at", "created_timestamp_micro"),),
        )
    )

    assert loaded.schema_version == GOLD_EXAMPLE_SCHEMA_VERSION
    assert loaded.created_timestamp_micro == CREATED
    assert loaded.to_dict()["created_timestamp_micro"] == unix_microseconds(CREATED)


def test_gold_example_file_v1_upgrades_to_v2(tmp_path: Path) -> None:
    path = tmp_path / "example.json"
    path.write_text(
        json.dumps(
            _to_v1(
                _gold_example().to_dict(),
                version="gold-example.v1",
                timestamps=(("created_at", "created_timestamp_micro"),),
            )
        ),
        encoding="utf-8",
    )

    loaded = GoldExample.load(path)

    assert loaded.schema_version == GOLD_EXAMPLE_SCHEMA_VERSION
    assert loaded.created_timestamp_micro == CREATED


def test_threshold_record_dict_v1_upgrades_to_v2() -> None:
    current = _threshold_record()

    loaded = ThresholdRecord.from_dict(
        _to_v1(
            current.to_dict(),
            version="threshold-record.v1",
            timestamps=(
                ("created_at", "created_timestamp_micro"),
                ("updated_at", "updated_timestamp_micro"),
            ),
        )
    )

    assert loaded.schema_version == THRESHOLD_RECORD_SCHEMA_VERSION
    assert loaded.created_timestamp_micro == CREATED
    assert loaded.updated_timestamp_micro == UPDATED
    assert loaded.to_dict()["updated_timestamp_micro"] == unix_microseconds(UPDATED)


def test_threshold_record_round_trips_through_v2_dict() -> None:
    current = _threshold_record()

    loaded = ThresholdRecord.from_dict(current.to_dict())

    assert loaded == current


def test_unknown_gold_example_version_is_rejected_with_guidance() -> None:
    payload = _gold_example().to_dict()
    payload["schema_version"] = "gold-example.v99"

    with pytest.raises(ValueError, match="unsupported gold example schema_version"):
        GoldExample.from_dict(payload)


def test_quality_report_wire_shape_is_v2_with_integer_timestamp() -> None:
    report = QualityReport(generated_at=CREATED)

    payload = report.to_dict()

    assert payload["schema_version"] == "quality-report.v2"
    assert payload["generated_timestamp_micro"] == unix_microseconds(CREATED)
    assert "generated_at" not in payload
