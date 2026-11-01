"""Normalized error factory and failure code/category helpers."""

from __future__ import annotations

from pipeline.contracts.base import NormalizedError
from pipeline.contracts.vocabularies import (
    FAILURE_CODE_CATEGORIES,
    FailureCategory,
    FailureCode,
    Severity,
)

# Failure categories that are retryable by default
RETRYABLE_CATEGORIES: frozenset[FailureCategory] = frozenset(
    {
        FailureCategory.TRANSIENT,
        FailureCategory.RATE_LIMIT,
        FailureCategory.QUOTA,
    }
)

# Failure categories that require reconciliation (not just retry)
RECONCILIATION_REQUIRED_CATEGORIES: frozenset[FailureCategory] = frozenset(
    {
        FailureCategory.UNKNOWN_OUTCOME,
    }
)

# Failure codes that require reconciliation even if category doesn't
RECONCILIATION_REQUIRED_CODES: frozenset[FailureCode] = frozenset(
    {
        FailureCode.TIMEOUT_UNKNOWN,
    }
)


def category_for_code(code: FailureCode) -> FailureCategory:
    """Get the FailureCategory for a FailureCode from the canonical map."""
    return FAILURE_CODE_CATEGORIES[code]


def is_retryable_category(category: FailureCategory) -> bool:
    """Check if a FailureCategory is retryable by default."""
    return category in RETRYABLE_CATEGORIES


def is_retryable_code(code: FailureCode) -> bool:
    """Check if a FailureCode is retryable by default."""
    return is_retryable_category(category_for_code(code))


def requires_reconciliation_category(category: FailureCategory) -> bool:
    """Check if a FailureCategory requires reconciliation."""
    return category in RECONCILIATION_REQUIRED_CATEGORIES


def requires_reconciliation_code(code: FailureCode) -> bool:
    """Check if a FailureCode requires reconciliation."""
    return code in RECONCILIATION_REQUIRED_CODES or requires_reconciliation_category(
        category_for_code(code)
    )


def create_normalized_error(
    code: FailureCode,
    message: str,
    *,
    provider_status: str | None = None,
    safe_details: dict[str, object] | None = None,
    severity: Severity = Severity.MAJOR,
) -> NormalizedError:
    """Create a NormalizedError from a FailureCode with automatic
    category/retryable/reconciliation.

    Args:
        code: The registered failure code.
        message: Human-readable error message.
        provider_status: Optional provider-specific status string.
        safe_details: Optional safe-to-log details (no secrets, no PII).
        severity: Error severity level.

    Returns:
        A NormalizedError with category, retryable, and reconciliation_required
        derived from the canonical FAILURE_CODE_CATEGORIES map.
    """
    category = category_for_code(code)
    retryable = is_retryable_category(category)
    reconciliation_required = requires_reconciliation_code(code)

    return NormalizedError(
        schema_version="normalized-error.v1",
        code=code.value,
        category=category.value,
        retryable=retryable,
        reconciliation_required=reconciliation_required,
        severity=severity.value,
        provider_status=provider_status,
        message=message,
        safe_details=safe_details or {},
    )


def create_normalized_error_from_exception(
    exc: Exception,
    *,
    default_code: FailureCode = FailureCode.INTERNAL,
    provider_status: str | None = None,
    safe_details: dict[str, object] | None = None,
    severity: Severity = Severity.MAJOR,
) -> NormalizedError:
    """Create a NormalizedError from an exception, inferring code when possible.

    This is a fallback for unexpected exceptions during capability execution.
    The default code is INTERNAL (category INTERNAL, not retryable).
    """
    return create_normalized_error(
        code=default_code,
        message=f"{type(exc).__name__}: {exc}",
        provider_status=provider_status,
        safe_details=safe_details,
        severity=severity,
    )


__all__ = [
    "RECONCILIATION_REQUIRED_CATEGORIES",
    "RECONCILIATION_REQUIRED_CODES",
    "RETRYABLE_CATEGORIES",
    "category_for_code",
    "create_normalized_error",
    "create_normalized_error_from_exception",
    "is_retryable_category",
    "is_retryable_code",
    "requires_reconciliation_category",
    "requires_reconciliation_code",
]
