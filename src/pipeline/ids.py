"""Opaque prefixed ID, run-key, and idempotency-key helpers.

Callers must treat the returned strings as opaque. The helper structure is a
convenience for readability and debuggability, not an API for parsing meaning
back out of an ID or key.
"""

from __future__ import annotations

import re
import secrets
from typing import Any, Final

from pipeline.fingerprints import canonical_json, sha256_text

PREFIX_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_SLUG_PATTERN: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")
_ID_DIGEST_LENGTH: Final[int] = 32


def _validate_prefix(prefix: str) -> None:
    if PREFIX_PATTERN.match(prefix) is None:
        raise ValueError(
            "ID prefixes must start with a lowercase letter and contain only "
            "lowercase letters, digits, and underscores (maximum 32 characters)"
        )


def _digest_parts(parts: tuple[Any, ...]) -> str:
    if not parts:
        raise ValueError("deterministic IDs and keys require at least one input")
    return sha256_text(canonical_json(list(parts)))[:_ID_DIGEST_LENGTH]


def deterministic_id(prefix: str, *parts: Any) -> str:
    """Return a stable prefixed ID derived from canonical input parts."""

    _validate_prefix(prefix)
    return f"{prefix}_{_digest_parts(parts)}"


def new_id(prefix: str, *, random_bytes: int = 12) -> str:
    """Return a new random opaque prefixed ID.

    Random IDs are for runtime records only. Deterministic fixtures and
    fingerprints must use :func:`deterministic_id` or explicit values instead.
    """

    _validate_prefix(prefix)
    if not 8 <= random_bytes <= 32:
        raise ValueError("random_bytes must be between 8 and 32")
    return f"{prefix}_{secrets.token_hex(random_bytes)}"


def run_key(*parts: Any) -> str:
    """Return a stable run key for a logical trigger identity.

    The key identifies the intended logical run; retries of the same trigger may
    reuse it, while a deliberately different run must include different parts.
    """

    return f"rk_{_digest_parts(parts)}"


def idempotency_key(operation: str, *parts: Any) -> str:
    """Return a stable idempotency key for one logical operation.

    Transport retries reuse the same key. Deliberate regeneration must use a new
    artifact version or a distinct ``parts`` input.
    """

    if not operation:
        raise ValueError("idempotency operations require a non-empty name")
    slug = _SLUG_PATTERN.sub("_", operation.strip().casefold()).strip("_")
    if not slug:
        raise ValueError("idempotency operation names must contain alphanumerics")
    return f"idem_{slug}_{_digest_parts((operation, *parts))}"


__all__ = [
    "PREFIX_PATTERN",
    "deterministic_id",
    "idempotency_key",
    "new_id",
    "run_key",
]
