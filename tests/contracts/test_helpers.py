from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

import pytest

from pipeline.fingerprints import (
    SECRET_FIELD_NAMES,
    canonical_bytes,
    canonical_datetime,
    canonical_decimal,
    canonical_json,
    file_sha256,
    fingerprint,
    is_sha256_hex,
    model_fingerprint,
    sha256_bytes,
    sha256_text,
)
from pipeline.ids import (
    PREFIX_PATTERN,
    deterministic_id,
    idempotency_key,
    new_id,
    run_key,
)


class Colour(StrEnum):
    RED = "red"


def test_canonical_json_sorts_keys_and_normalizes_values() -> None:
    value = {
        "z": {Colour.RED, "blue"},
        "a": datetime(2026, 10, 21, 14, 0, tzinfo=timezone(timedelta(hours=2))),
        "n": Decimal("001.2300"),
        "zero": -0.0,
        "flag": True,
        "none": None,
    }

    assert canonical_json(value) == (
        '{"a":"2026-10-21T12:00:00Z","flag":true,"n":"1.23",'
        '"none":null,"z":["blue","red"],"zero":0.0}'
    )


def test_canonical_json_is_independent_of_mapping_insertion_order() -> None:
    first = {"b": [2, 3], "a": {"y": 1, "x": 0}}
    second = {"a": {"x": 0, "y": 1}, "b": [2, 3]}

    assert canonical_json(first) == canonical_json(second)


def test_canonical_json_redacts_secret_keys_recursively() -> None:
    payload = {
        "api_key": "super-secret",
        "nested": {"Authorization": "Bearer x", "safe": "visible"},
        "items": [{"client_secret": "hidden", "value": 1}],
    }

    rendered = canonical_json(payload, exclude_keys=SECRET_FIELD_NAMES)

    assert "super-secret" not in rendered
    assert "Bearer x" not in rendered
    assert "hidden" not in rendered
    assert "visible" in rendered


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        b"raw",
        {1: "non-string-key"},
        object(),
    ],
)
def test_canonical_json_rejects_unsupported_values(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        canonical_json(value)


def test_canonical_datetime_requires_timezone() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        canonical_datetime(datetime(2026, 10, 21, 12, 0))


def test_canonical_datetime_normalizes_offsets() -> None:
    value = datetime(
        2026, 10, 21, 14, 30, tzinfo=timezone(timedelta(hours=2, minutes=30))
    )

    assert canonical_datetime(value) == "2026-10-21T12:00:00Z"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("001.2300"), "1.23"),
        (Decimal("-0.000"), "0"),
        (Decimal("1000"), "1000"),
        (Decimal("0.00000100"), "0.000001"),
    ],
)
def test_canonical_decimal_is_lossless(value: Decimal, expected: str) -> None:
    assert canonical_decimal(value) == expected


def test_canonical_decimal_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError, match="finite"):
        canonical_decimal(Decimal("NaN"))


def test_canonical_bytes_is_utf8_encoded_canonical_json() -> None:
    assert canonical_bytes({"b": 2, "a": "é"}) == ('{"a":"é","b":2}'.encode())


def test_fingerprint_is_stable_and_content_sensitive() -> None:
    first = fingerprint({"b": 2, "a": 1})
    second = fingerprint({"a": 1, "b": 2})

    assert first == second
    assert is_sha256_hex(first)
    assert fingerprint({"a": 1, "b": 3}) != first


def test_fingerprint_redacts_secrets_by_default() -> None:
    without_secret = {"value": 1}
    with_secret = {"value": 1, "api_key": "hidden"}

    assert fingerprint(with_secret) == fingerprint(without_secret)
    assert fingerprint(with_secret, exclude_keys=frozenset()) != fingerprint(
        without_secret, exclude_keys=frozenset()
    )


def test_sha256_helpers() -> None:
    digest = sha256_bytes(b"abc")

    assert digest == sha256_text("abc")
    assert digest == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert is_sha256_hex(digest)
    assert not is_sha256_hex(digest.upper())
    assert not is_sha256_hex("abc")


def test_file_sha256(tmp_path: Path) -> None:
    path = tmp_path / "content.bin"
    path.write_bytes(b"abc")

    assert file_sha256(path) == sha256_text("abc")


def test_model_fingerprint_matches_model_payload(valid_fixtures) -> None:
    from pipeline.contracts import RunOverrides

    payload = valid_fixtures["run_overrides"]
    model = RunOverrides.model_validate(payload)

    assert model_fingerprint(model) == fingerprint(payload)


def test_deterministic_ids_are_stable_and_prefixed() -> None:
    first = deterministic_id("run", "content-package", 1)
    second = deterministic_id("run", "content-package", 1)

    assert first == second
    assert first.startswith("run_")
    assert len(first) == len("run_") + 32
    assert deterministic_id("run", "content-package", 2) != first
    assert deterministic_id("run", {"b": 2, "a": 1}) == deterministic_id(
        "run", {"a": 1, "b": 2}
    )


def test_deterministic_ids_require_at_least_one_part() -> None:
    with pytest.raises(ValueError, match="at least one input"):
        deterministic_id("run")


@pytest.mark.parametrize(
    "prefix",
    ["", "Run", "1run", "run-id", "run id", "_run", "a" * 33],
)
def test_id_prefixes_are_validated(prefix: str) -> None:
    assert PREFIX_PATTERN.match(prefix) is None
    with pytest.raises(ValueError, match="ID prefixes"):
        deterministic_id(prefix, "value")


def test_new_id_uses_requested_prefix_and_random_bytes() -> None:
    value = new_id("run", random_bytes=8)

    assert value.startswith("run_")
    assert len(value) == len("run_") + 16
    assert value != new_id("run", random_bytes=8)


@pytest.mark.parametrize("random_bytes", [0, 7, 33])
def test_new_id_rejects_out_of_range_random_bytes(random_bytes: int) -> None:
    with pytest.raises(ValueError, match="between 8 and 32"):
        new_id("run", random_bytes=random_bytes)


def test_run_keys_are_stable_for_one_logical_trigger() -> None:
    first = run_key("content-package", "2026-10-21")

    assert first == run_key("content-package", "2026-10-21")
    assert first != run_key("content-package", "2026-10-22")
    assert first.startswith("rk_")


def test_idempotency_keys_include_a_slugged_operation() -> None:
    first = idempotency_key("Speech Generation", "scene_01")

    assert first.startswith("idem_speech_generation_")
    assert first == idempotency_key("Speech Generation", "scene_01")
    assert first != idempotency_key("Speech Generation", "scene_02")


@pytest.mark.parametrize("operation", ["", "   ", "!!!"])
def test_idempotency_keys_require_an_operation(operation: str) -> None:
    with pytest.raises(ValueError):
        idempotency_key(operation, "value")


def test_canonical_payload_round_trips_through_json(valid_fixtures) -> None:
    payload = valid_fixtures["workflow_run"]

    assert json.loads(canonical_json(payload)) == payload


def test_utc_fixture_datetimes_are_normalized(valid_fixtures) -> None:
    for payload in valid_fixtures.values():
        for key, value in payload.items():
            if key.endswith("_at") and isinstance(value, str):
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                assert parsed.tzinfo is not None
                assert parsed.utcoffset() == timedelta(0)
