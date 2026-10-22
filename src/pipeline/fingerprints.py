"""Deterministic canonical JSON serialization and SHA-256 fingerprints.

Canonicalization sorts mapping keys, normalizes UTC datetimes and decimals, and
rejects non-JSON values. Fingerprints hash canonical bytes and exclude common
secret-bearing keys by default so credentials cannot leak into persisted research
identifiers.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence, Set
from datetime import UTC, date, datetime, time
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel

SECRET_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "authorization",
        "client_secret",
        "credential",
        "credentials",
        "password",
        "private_key",
        "refresh_token",
        "secret",
        "session_token",
    }
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def canonical_datetime(value: datetime) -> str:
    """Return an ISO-8601 UTC representation with a ``Z`` suffix."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("canonical datetimes must be timezone-aware")
    normalized = value.astimezone(UTC).isoformat()
    if normalized.endswith("+00:00"):
        return normalized[:-6] + "Z"
    return normalized


def canonical_decimal(value: Decimal) -> str:
    """Return a lossless plain-string decimal without insignificant zeros."""

    if not value.is_finite():
        raise ValueError("canonical decimals must be finite")
    if value == 0:
        return "0"
    text = format(value.normalize(), "f")
    return "0" if text == "-0" else text


def _normalize(value: Any, *, exclude_keys: frozenset[str]) -> Any:
    if isinstance(value, BaseModel):
        return _normalize(
            value.model_dump(mode="python"),
            exclude_keys=exclude_keys,
        )
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return canonical_datetime(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("canonical JSON does not allow non-finite floats")
        return 0.0 if value == 0 else value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical JSON mapping keys must be strings")
            if key.casefold() in exclude_keys:
                continue
            normalized[key] = _normalize(item, exclude_keys=exclude_keys)
        return normalized
    if isinstance(value, Set):
        items = [_normalize(item, exclude_keys=exclude_keys) for item in value]
        return sorted(items, key=lambda item: canonical_json(item))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize(item, exclude_keys=exclude_keys) for item in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        raise TypeError("raw bytes must not be fingerprinted as canonical JSON")
    raise TypeError(f"unsupported canonical JSON value type: {type(value).__name__}")


def canonical_json(
    value: Any,
    *,
    exclude_keys: frozenset[str] = frozenset(),
) -> str:
    """Serialize a value to compact, key-sorted canonical JSON."""

    normalized = _normalize(value, exclude_keys=exclude_keys)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_bytes(
    value: Any,
    *,
    exclude_keys: frozenset[str] = frozenset(),
) -> bytes:
    """Return canonical JSON encoded as UTF-8 bytes."""

    return canonical_json(value, exclude_keys=exclude_keys).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    """Return the lowercase SHA-256 hex digest of raw bytes."""

    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    """Return the lowercase SHA-256 hex digest of UTF-8 text."""

    return sha256_bytes(text.encode("utf-8"))


def is_sha256_hex(value: str) -> bool:
    """Return true when ``value`` is a valid lowercase SHA-256 digest."""

    return _SHA256_PATTERN.match(value) is not None


def fingerprint(
    value: Any,
    *,
    exclude_keys: frozenset[str] = SECRET_FIELD_NAMES,
) -> str:
    """Return a deterministic SHA-256 fingerprint of canonical content.

    Common secret-bearing keys are excluded by default. Pass an explicit
    ``exclude_keys`` set to change the policy; an empty set disables redaction.
    """

    return sha256_bytes(canonical_bytes(value, exclude_keys=exclude_keys))


def model_fingerprint(
    model: BaseModel,
    *,
    exclude_keys: frozenset[str] = SECRET_FIELD_NAMES,
) -> str:
    """Return a deterministic fingerprint of a Pydantic model."""

    return fingerprint(model, exclude_keys=exclude_keys)


def file_sha256(path: Path) -> str:
    """Return the lowercase SHA-256 digest of a file's bytes."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "SECRET_FIELD_NAMES",
    "canonical_bytes",
    "canonical_datetime",
    "canonical_decimal",
    "canonical_json",
    "file_sha256",
    "fingerprint",
    "is_sha256_hex",
    "model_fingerprint",
    "sha256_bytes",
    "sha256_text",
]
