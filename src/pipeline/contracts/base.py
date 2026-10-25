"""Shared contract bases, scalar types, and normalized failure records.

Core records are strict: unknown fields are rejected, scalar types are not
coerced, identifiers are non-empty, timestamps are timezone-aware and
normalized to UTC, and SHA-256 fields use lowercase hexadecimal digests.
Arbitrary JSON is permitted only through the explicit extension fields declared
by individual contracts; it is never accepted for core state transitions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    model_validator,
)

from pipeline.contracts.vocabularies import (
    FAILURE_CODE_CATEGORIES,
    FailureCategory,
    FailureCode,
    Severity,
)

# Explicit JSON extension boundary. Values are valid JSON scalars/arrays/objects,
# not arbitrary Python objects. These fields are diagnostic or operation-specific
# and must never control core workflow transitions.
type ExtensionObject = dict[str, JsonValue]
type ExtensionArray = list[JsonValue]

NonEmptyStr = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=1,
        max_length=512,
        pattern=r"^\S(?:.*\S)?$",
    ),
]

OpaqueId = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=1,
        max_length=256,
        pattern=r"^\S+$",
    ),
]

Sha256Hex = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    ),
]

NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
PositiveInt = Annotated[int, Field(strict=True, ge=1)]
NonNegativeFloat = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
FiniteFloat = Annotated[float, Field(strict=True, allow_inf_nan=False)]
UnitInterval = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
StrictBoolean = Annotated[bool, Field(strict=True)]


def _reject_numeric_datetime(value: object) -> object:
    if isinstance(value, (bool, int, float)):
        raise ValueError(
            "datetimes must be ISO-8601 strings or datetime objects, "
            "not numeric timestamps"
        )
    return value


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetimes must be timezone-aware and normalize to UTC")
    return value.astimezone(UTC)


UTCDateTime = Annotated[
    datetime,
    BeforeValidator(_reject_numeric_datetime),
    AfterValidator(_ensure_utc),
]


class Contract(BaseModel):
    """Strict base for every durable contract.

    Concrete contracts override ``schema_version`` with a literal value so the
    serialized shape is versioned and validated before use.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    schema_version: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9.-]*\.v[0-9]+$",
    )


class MetadataContract(Contract):
    """Contract base for records with explicitly allowed extension metadata.

    Only use this base for records whose additional fields are known to be
    diagnostic or provider-specific. Core workflow state must stay on
    ``Contract`` with ``extra="forbid"``.
    """

    model_config = ConfigDict(extra="allow")


class UTCRecord(Contract):
    """Contract base for records with created/updated UTC audit timestamps."""

    created_at: UTCDateTime
    updated_at: UTCDateTime | None = None

    @model_validator(mode="after")
    def _validate_timestamp_order(self) -> UTCRecord:
        if self.updated_at is not None and self.updated_at < self.created_at:
            raise ValueError("updated_at must not be earlier than created_at")
        return self


class NormalizedError(Contract):
    """Provider- and stage-neutral failure explanation.

    ``category`` must agree with the canonical category registered for
    ``code``. Reconciliation is explicit so unknown external outcomes cannot be
    mistaken for clean failures.
    """

    schema_version: Literal["normalized-error.v1"]
    code: FailureCode
    category: FailureCategory
    retryable: StrictBoolean
    reconciliation_required: StrictBoolean = False
    severity: Severity = Severity.MAJOR
    provider_status: NonEmptyStr | None = None
    message: NonEmptyStr
    safe_details: ExtensionObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_code_category(self) -> NormalizedError:
        expected = FAILURE_CODE_CATEGORIES[self.code]
        if self.category is not expected:
            raise ValueError(
                f"failure code {self.code.value!r} belongs to category "
                f"{expected.value!r}, not {self.category.value!r}"
            )
        return self


__all__ = [
    "Contract",
    "ExtensionArray",
    "ExtensionObject",
    "FiniteFloat",
    "MetadataContract",
    "NonEmptyStr",
    "NonNegativeFloat",
    "NonNegativeInt",
    "NormalizedError",
    "OpaqueId",
    "PositiveInt",
    "Sha256Hex",
    "StrictBoolean",
    "UTCDateTime",
    "UTCRecord",
    "UnitInterval",
]
