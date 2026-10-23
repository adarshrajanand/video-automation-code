"""Capability registry keyed by (capability, operation_version)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pipeline.capabilities.errors import create_normalized_error
from pipeline.capabilities.models import (
    CapabilityImplementation,
    CapabilityRegistration,
)
from pipeline.contracts.base import NormalizedError
from pipeline.contracts.vocabularies import FailureCode

if TYPE_CHECKING:
    from pipeline.capabilities.fake import FakeCapabilityProvider


@dataclass(frozen=True, slots=True)
class CapabilityKey:
    """Registry lookup key: (capability, operation_version)."""

    capability: str
    operation_version: str

    def __str__(self) -> str:
        return f"{self.capability}:{self.operation_version}"


class CapabilityRegistry:
    """Registry of capability implementations keyed by
    (capability, operation_version)."""

    def __init__(self) -> None:
        self._implementations: dict[CapabilityKey, list[CapabilityImplementation]] = {}
        self._fake_provider: FakeCapabilityProvider | None = None

    def register(self, registration: CapabilityRegistration) -> None:
        """Register a capability implementation."""
        key = CapabilityKey(
            capability=registration.capability,
            operation_version=registration.operation_version,
        )
        if key not in self._implementations:
            self._implementations[key] = []
        self._implementations[key].append(registration.implementation)

    def get(
        self,
        capability: str,
        operation_version: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        required_features: list[str] | None = None,
        locale: str | None = None,
    ) -> CapabilityImplementation | None:
        """Find a matching implementation, optionally filtered by
        provider/model/features/locale."""
        key = CapabilityKey(capability=capability, operation_version=operation_version)
        candidates = self._implementations.get(key, [])
        if not candidates:
            return None

        for impl in candidates:
            if provider is not None and impl.provider != provider:
                continue
            if model is not None and impl.model != model:
                continue
            if required_features is not None and not all(
                f in impl.declared_features for f in required_features
            ):
                continue
            if (
                locale is not None
                and impl.supported_locales
                and locale not in impl.supported_locales
            ):
                continue
            return impl

        # No filtered match; return first as fallback
        return candidates[0]

    def list_for_capability(
        self, capability: str, operation_version: str
    ) -> list[CapabilityImplementation]:
        """List all implementations for a capability/operation_version."""
        key = CapabilityKey(capability=capability, operation_version=operation_version)
        return list(self._implementations.get(key, []))

    def list_all(self) -> list[CapabilityImplementation]:
        """List all registered implementations."""
        result: list[CapabilityImplementation] = []
        for impls in self._implementations.values():
            result.extend(impls)
        return result

    def set_fake_provider(self, provider: FakeCapabilityProvider) -> None:
        """Set the fake provider for testing."""
        self._fake_provider = provider

    def get_fake_provider(self) -> FakeCapabilityProvider | None:
        """Get the fake provider if set."""
        return self._fake_provider


class CapabilityNotFoundError(Exception):
    """Raised when no capability implementation matches the request."""

    def __init__(
        self,
        capability: str,
        operation_version: str,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        self.capability = capability
        self.operation_version = operation_version
        self.provider = provider
        self.model = model
        parts = [
            f"capability={capability!r}",
            f"operation_version={operation_version!r}",
        ]
        if provider:
            parts.append(f"provider={provider!r}")
        if model:
            parts.append(f"model={model!r}")
        super().__init__(f"No capability implementation found for {', '.join(parts)}")

    def to_normalized_error(self) -> NormalizedError:
        """Convert to a NormalizedError for execution failure."""
        return create_normalized_error(
            FailureCode.CONFIG_UNKNOWN_STAGE,
            f"No capability implementation found for "
            f"{self.capability}:{self.operation_version}",
            safe_details={
                "capability": self.capability,
                "operation_version": self.operation_version,
                "provider": self.provider,
                "model": self.model,
            },
        )


class CapabilityRequirementMismatchError(Exception):
    """Raised when a capability implementation doesn't meet requirements."""

    def __init__(
        self,
        capability: str,
        operation_version: str,
        reason: str,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        self.capability = capability
        self.operation_version = operation_version
        self.reason = reason
        self.provider = provider
        self.model = model
        super().__init__(
            f"Capability requirement mismatch for "
            f"{capability}:{operation_version}: {reason}"
        )

    def to_normalized_error(self) -> NormalizedError:
        """Convert to a NormalizedError for execution failure."""
        return create_normalized_error(
            FailureCode.VALIDATION,
            f"Capability requirement mismatch: {self.reason}",
            safe_details={
                "capability": self.capability,
                "operation_version": self.operation_version,
                "reason": self.reason,
                "provider": self.provider,
                "model": self.model,
            },
        )


__all__ = [
    "CapabilityKey",
    "CapabilityNotFoundError",
    "CapabilityRegistry",
    "CapabilityRequirementMismatchError",
]
