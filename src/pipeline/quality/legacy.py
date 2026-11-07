"""Helpers for reading quality artifacts written before the timestamp change.

Gold examples and threshold records are standalone JSON files, so the SQLite
reset policy cannot upgrade them. Their v1 wire format stored ISO-8601 text under
``created_at``/``updated_at``; v2 stores integer microseconds under
``*_timestamp_micro``. These helpers convert the old text form on load so saved
files keep working (review 4501750689).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pipeline.fingerprints import unix_microseconds


def microseconds_from_legacy_iso(value: Any, *, field_name: str) -> int:
    """Convert a v1 ISO-8601 timestamp to exact integer microseconds."""

    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if not isinstance(value, str):
        raise ValueError(
            f"{field_name} must be ISO-8601 text in a v1 file, "
            f"found {type(value).__name__}"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} is not ISO-8601: {value!r}") from error
    if parsed.tzinfo is None:
        # Legacy files were written from timezone-aware UTC values; treat a
        # missing offset as UTC rather than silently interpreting local time.
        parsed = parsed.replace(tzinfo=UTC)
    return unix_microseconds(parsed)


__all__ = ["microseconds_from_legacy_iso"]
