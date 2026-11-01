"""Failure classification and bounded retry backoff.

Retry behavior is policy-driven. A failure code maps to one canonical category,
the caller's :class:`~pipeline.contracts.execution.RetryPolicy` decides whether
that category is retryable, and unknown external outcomes always take the
reconciliation branch instead of a blind paid retry.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from pipeline.contracts.execution import RecoveryPolicy, RetryPolicy
from pipeline.contracts.vocabularies import (
    FAILURE_CODE_CATEGORIES,
    FailureCategory,
    FailureCode,
    RepeatedFailureAction,
    UnknownOutcomeAction,
)
from pipeline.fingerprints import canonical_json, sha256_text

DEFAULT_RETRY_POLICY_ID: Final[str] = "default_retry_v1"
DEFAULT_RECOVERY_POLICY_ID: Final[str] = "default_recovery_v1"


class FailureAction(StrEnum):
    """Durable recovery action selected for one failed attempt."""

    RETRY = "RETRY"
    RECONCILE = "RECONCILE"
    FAIL = "FAIL"
    WAIT_HUMAN = "WAIT_HUMAN"


@dataclass(frozen=True, slots=True)
class RetryDecision:
    """Typed classification result for one execution failure."""

    action: FailureAction
    failure_code: FailureCode
    category: FailureCategory
    attempt_number: int
    backoff_seconds: float = 0.0
    reason: str = ""
    retry_exhausted: bool = False

    @property
    def retryable(self) -> bool:
        return self.action is FailureAction.RETRY


def default_retry_policy() -> RetryPolicy:
    """Return the local fast-slice retry policy."""

    return RetryPolicy(
        schema_version="retry-policy.v1",
        policy_id=DEFAULT_RETRY_POLICY_ID,
        max_attempts=3,
        initial_backoff_seconds=1.0,
        max_backoff_seconds=30.0,
        jitter_ratio=0.2,
        retryable_categories=[
            FailureCategory.TRANSIENT,
            FailureCategory.RATE_LIMIT,
        ],
    )


def default_recovery_policy() -> RecoveryPolicy:
    """Return the local fast-slice recovery policy."""

    return RecoveryPolicy(
        schema_version="recovery-policy.v1",
        policy_id=DEFAULT_RECOVERY_POLICY_ID,
        retry_policy_id=DEFAULT_RETRY_POLICY_ID,
        on_unknown_outcome=UnknownOutcomeAction.RECONCILE,
        on_quality_failure="REGENERATE",
        on_repeated_failure=RepeatedFailureAction.HUMAN_REVIEW,
    )


def deterministic_jitter(*parts: object) -> float:
    """Return a stable unit-interval jitter value derived from ``parts``.

    Production callers may inject a random unit value instead. The deterministic
    default makes retry timing reproducible in tests without suppressing jitter
    in real runs.
    """

    if not parts:
        raise ValueError("deterministic jitter requires at least one input")
    digest = sha256_text(canonical_json(list(parts)))
    return int(digest[:16], 16) / float(1 << 64)


def bounded_backoff_seconds(
    attempt_number: int,
    *,
    initial_backoff_seconds: float,
    max_backoff_seconds: float,
    jitter_ratio: float,
    jitter_value: float | None = None,
) -> float:
    """Return one bounded exponential backoff delay with injected jitter.

    ``attempt_number`` is one-based. The unjittered delay doubles from the
    initial value and is capped at ``max_backoff_seconds``. A symmetric jitter
    fraction of ``[-jitter_ratio, +jitter_ratio]`` is applied, then the final
    value is clamped to the same policy bounds. Passing ``jitter_value`` makes
    the result deterministic for fault tests.
    """

    if attempt_number < 1:
        raise ValueError("attempt_number must be at least 1")
    if initial_backoff_seconds < 0 or max_backoff_seconds < 0:
        raise ValueError("backoff bounds must be non-negative")
    if max_backoff_seconds < initial_backoff_seconds:
        raise ValueError("max_backoff_seconds must not be below the initial delay")
    if not 0 <= jitter_ratio <= 1:
        raise ValueError("jitter_ratio must be within [0, 1]")
    unit = (
        deterministic_jitter(attempt_number, initial_backoff_seconds)
        if jitter_value is None
        else jitter_value
    )
    if not 0 <= unit <= 1:
        raise ValueError("jitter_value must be within [0, 1]")

    base = min(
        initial_backoff_seconds * (2 ** (attempt_number - 1)),
        max_backoff_seconds,
    )
    jittered = base * (1.0 + jitter_ratio * (2.0 * unit - 1.0))
    return round(min(max(jittered, 0.0), max_backoff_seconds), 6)


def retry_backoff_seconds(
    attempt_number: int,
    policy: RetryPolicy,
    *,
    jitter_value: float | None = None,
) -> float:
    """Return bounded backoff for one retry-policy attempt."""

    return bounded_backoff_seconds(
        attempt_number,
        initial_backoff_seconds=policy.initial_backoff_seconds,
        max_backoff_seconds=policy.max_backoff_seconds,
        jitter_ratio=policy.jitter_ratio,
        jitter_value=jitter_value,
    )


def classify_failure(
    failure_code: FailureCode,
    attempt_number: int,
    *,
    retry_policy: RetryPolicy | None = None,
    recovery_policy: RecoveryPolicy | None = None,
    jitter_value: float | None = None,
) -> RetryDecision:
    """Classify one failure into retry, reconciliation, review, or failure.

    Unknown outcomes never retry implicitly. Confirmation/validation failures
    outside the policy's retryable categories are permanent for the unchanged
    input and fail without creating a replacement attempt.
    """

    policy = retry_policy or default_retry_policy()
    recovery = recovery_policy or default_recovery_policy()
    if attempt_number < 1:
        raise ValueError("attempt_number must be at least 1")

    category = FAILURE_CODE_CATEGORIES[failure_code]
    retryable = category in policy.retryable_categories

    if category is FailureCategory.UNKNOWN_OUTCOME:
        action = _unknown_outcome_action(recovery.on_unknown_outcome)
        return RetryDecision(
            action=action,
            failure_code=failure_code,
            category=category,
            attempt_number=attempt_number,
            backoff_seconds=(
                retry_backoff_seconds(
                    attempt_number,
                    policy,
                    jitter_value=jitter_value,
                )
                if action is FailureAction.RETRY
                else 0.0
            ),
            reason="UNKNOWN_OUTCOME:" + action.value,
        )

    if retryable and attempt_number < policy.max_attempts:
        return RetryDecision(
            action=FailureAction.RETRY,
            failure_code=failure_code,
            category=category,
            attempt_number=attempt_number,
            backoff_seconds=retry_backoff_seconds(
                attempt_number, policy, jitter_value=jitter_value
            ),
            reason="RETRYABLE:" + category.value,
        )

    if retryable:
        action = (
            FailureAction.WAIT_HUMAN
            if recovery.on_repeated_failure is RepeatedFailureAction.HUMAN_REVIEW
            else FailureAction.FAIL
        )
        return RetryDecision(
            action=action,
            failure_code=failure_code,
            category=category,
            attempt_number=attempt_number,
            reason="RETRY_EXHAUSTED:" + category.value,
            retry_exhausted=True,
        )

    return RetryDecision(
        action=FailureAction.FAIL,
        failure_code=failure_code,
        category=category,
        attempt_number=attempt_number,
        reason="NON_RETRYABLE:" + category.value,
    )


def _unknown_outcome_action(action: UnknownOutcomeAction) -> FailureAction:
    return {
        UnknownOutcomeAction.RECONCILE: FailureAction.RECONCILE,
        UnknownOutcomeAction.RETRY: FailureAction.RETRY,
        UnknownOutcomeAction.WAIT_HUMAN: FailureAction.WAIT_HUMAN,
        UnknownOutcomeAction.FAIL: FailureAction.FAIL,
    }[action]


__all__ = [
    "DEFAULT_RECOVERY_POLICY_ID",
    "DEFAULT_RETRY_POLICY_ID",
    "FailureAction",
    "RetryDecision",
    "bounded_backoff_seconds",
    "classify_failure",
    "default_recovery_policy",
    "default_retry_policy",
    "deterministic_jitter",
    "retry_backoff_seconds",
]
