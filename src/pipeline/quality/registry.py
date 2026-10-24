"""Deterministic quality check registry with versioned checks."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pipeline.contracts.quality import QualityCheck
from pipeline.contracts.vocabularies import EvaluationKind

if TYPE_CHECKING:
    from pipeline.quality.evaluators import (
        DeterministicEvaluator,
        HumanEvaluator,
        SemanticEvaluator,
        SpecializedEvaluator,
    )


@dataclass(frozen=True, slots=True)
class _RegisteredCheck:
    """Internal wrapper for a registered quality check with its evaluator factory."""

    check: QualityCheck
    evaluator_factory: (
        DeterministicEvaluator
        | SpecializedEvaluator
        | SemanticEvaluator
        | HumanEvaluator
    )


class QualityCheckRegistry:
    """Thread-safe registry of versioned quality checks.

    Checks are registered by their ``check_id`` and can be retrieved for
    gate evaluation. The registry ensures deterministic lookup and prevents
    duplicate registration.
    """

    def __init__(self) -> None:
        self._checks: dict[str, _RegisteredCheck] = {}
        self._lock = threading.RLock()

    def register(
        self,
        check: QualityCheck,
        evaluator_factory: (
            DeterministicEvaluator
            | SpecializedEvaluator
            | SemanticEvaluator
            | HumanEvaluator
        ),
    ) -> None:
        """Register a quality check with its evaluator factory.

        Args:
            check: The quality check definition.
            evaluator_factory: Callable that creates an evaluator instance
                for this check. Must match the check's ``kind``.

        Raises:
            ValueError: If a check with the same ``check_id`` is already registered.
        """
        with self._lock:
            if check.check_id in self._checks:
                raise ValueError(
                    f"Quality check {check.check_id!r} is already registered"
                )
            self._checks[check.check_id] = _RegisteredCheck(
                check=check, evaluator_factory=evaluator_factory
            )

    def get(self, check_id: str) -> QualityCheck:
        """Get a quality check by ID.

        Args:
            check_id: The check identifier.

        Returns:
            The registered quality check.

        Raises:
            KeyError: If no check with the given ID is registered.
        """
        with self._lock:
            registered = self._checks.get(check_id)
            if registered is None:
                raise KeyError(f"Quality check {check_id!r} is not registered")
            return registered.check

    def get_evaluator(
        self, check_id: str
    ) -> (
        DeterministicEvaluator
        | SpecializedEvaluator
        | SemanticEvaluator
        | HumanEvaluator
    ):
        """Get the evaluator factory for a quality check.

        Args:
            check_id: The check identifier.

        Returns:
            The registered evaluator factory.

        Raises:
            KeyError: If no check with the given ID is registered.
        """
        with self._lock:
            registered = self._checks.get(check_id)
            if registered is None:
                raise KeyError(f"Quality check {check_id!r} is not registered")
            return registered.evaluator_factory

    def get_all(self) -> tuple[QualityCheck, ...]:
        """Return all registered checks in registration order."""
        with self._lock:
            return tuple(rc.check for rc in self._checks.values())

    def get_by_kind(self, kind: EvaluationKind) -> tuple[QualityCheck, ...]:
        """Return all checks of a specific evaluation kind."""
        with self._lock:
            return tuple(
                rc.check for rc in self._checks.values() if rc.check.kind is kind
            )

    def get_by_target_type(self, artifact_type: str) -> tuple[QualityCheck, ...]:
        """Return all checks that target a specific artifact type."""
        with self._lock:
            return tuple(
                rc.check
                for rc in self._checks.values()
                if artifact_type in rc.check.target_artifact_types
            )

    def resolve_checks_for_gate(
        self, gate_check_ids: tuple[str, ...]
    ) -> tuple[QualityCheck, ...]:
        """Resolve and return checks for a gate in the specified order.

        Args:
            gate_check_ids: Ordered tuple of check IDs from a gate policy.

        Returns:
            Tuple of quality checks in the same order.

        Raises:
            KeyError: If any check ID is not registered.
        """
        with self._lock:
            result = []
            for check_id in gate_check_ids:
                registered = self._checks.get(check_id)
                if registered is None:
                    raise KeyError(
                        f"Quality check {check_id!r} required by gate is not registered"
                    )
                result.append(registered.check)
            return tuple(result)

    def __contains__(self, check_id: str) -> bool:
        with self._lock:
            return check_id in self._checks

    def __len__(self) -> int:
        with self._lock:
            return len(self._checks)


_default_registry: QualityCheckRegistry | None = None
_default_registry_lock = threading.Lock()


def get_default_registry() -> QualityCheckRegistry:
    """Get the process-global default quality check registry.

    The default registry is lazily initialized and populated with the
    built-in quality checks on first access.
    """
    global _default_registry
    if _default_registry is None:
        with _default_registry_lock:
            if _default_registry is None:
                _default_registry = QualityCheckRegistry()
                _populate_default_registry(_default_registry)
    return _default_registry


def _populate_default_registry(registry: QualityCheckRegistry) -> None:
    """Populate the registry with built-in quality checks.

    This function is called once during lazy initialization of the
    default registry. It registers all deterministic, specialized,
    semantic, and human checks defined in the pipeline.
    """
    # Import evaluators here to avoid circular imports
    from pipeline.quality.evaluators import (
        DeterministicCheckEvaluator,
        HumanCheckEvaluator,
        SemanticCheckEvaluator,
        SpecializedCheckEvaluator,
    )

    # Deterministic checks - schema validation, reference integrity, etc.
    deterministic_evaluator = DeterministicCheckEvaluator()

    # Script quality checks
    registry.register(
        QualityCheck(
            schema_version="quality-check.v1",
            check_id="script_schema_v1",
            target_artifact_types=("script",),
            required_input_types=("script",),
            kind=EvaluationKind.DETERMINISTIC,
            evaluator="deterministic_schema_validator",
            evaluator_version="1.0.0",
            required=True,
            severity_if_failed="CRITICAL",
            on_failure="FAIL",
            repair_scope="NONE",
        ),
        deterministic_evaluator,
    )

    registry.register(
        QualityCheck(
            schema_version="quality-check.v1",
            check_id="claim_reference_integrity_v1",
            target_artifact_types=("script",),
            required_input_types=("script", "claim_ledger", "evidence_snapshots"),
            kind=EvaluationKind.DETERMINISTIC,
            evaluator="deterministic_reference_integrity",
            evaluator_version="1.0.0",
            required=True,
            severity_if_failed="CRITICAL",
            on_failure="FAIL",
            repair_scope="NONE",
        ),
        deterministic_evaluator,
    )

    registry.register(
        QualityCheck(
            schema_version="quality-check.v1",
            check_id="script_editorial_clarity_v1",
            target_artifact_types=("script",),
            required_input_types=("script",),
            kind=EvaluationKind.SEMANTIC,
            evaluator="editorial_clarity_evaluator",
            evaluator_version="1.0.0",
            rubric_version="editorial-rubric-v1",
            required=True,
            severity_if_failed="MAJOR",
            on_failure="REGENERATE",
            repair_scope="SCENE",
        ),
        SemanticCheckEvaluator(),
    )

    registry.register(
        QualityCheck(
            schema_version="quality-check.v1",
            check_id="script_claim_evidence_v1",
            target_artifact_types=("script",),
            required_input_types=("script", "claim_ledger", "evidence_snapshots"),
            kind=EvaluationKind.SEMANTIC,
            evaluator="claim_evidence_evaluator",
            evaluator_version="1.0.0",
            rubric_version="claim-evidence-rubric-v1",
            required=True,
            severity_if_failed="MAJOR",
            on_failure="REGENERATE",
            repair_scope="SCENE",
        ),
        SemanticCheckEvaluator(),
    )

    # Visual planning checks
    registry.register(
        QualityCheck(
            schema_version="quality-check.v1",
            check_id="visual_plan_schema_v1",
            target_artifact_types=("visual_plan",),
            required_input_types=("visual_plan",),
            kind=EvaluationKind.DETERMINISTIC,
            evaluator="deterministic_schema_validator",
            evaluator_version="1.0.0",
            required=True,
            severity_if_failed="CRITICAL",
            on_failure="FAIL",
            repair_scope="NONE",
        ),
        deterministic_evaluator,
    )

    registry.register(
        QualityCheck(
            schema_version="quality-check.v1",
            check_id="visual_intent_coherence_v1",
            target_artifact_types=("visual_plan",),
            required_input_types=("visual_plan", "script"),
            kind=EvaluationKind.SEMANTIC,
            evaluator="visual_intent_coherence_evaluator",
            evaluator_version="1.0.0",
            rubric_version="visual-rubric-v1",
            required=True,
            severity_if_failed="MAJOR",
            on_failure="REGENERATE",
            repair_scope="SCENE",
        ),
        SemanticCheckEvaluator(),
    )

    # Asset acquisition checks
    registry.register(
        QualityCheck(
            schema_version="quality-check.v1",
            check_id="asset_availability_v1",
            target_artifact_types=("asset_manifest",),
            required_input_types=("asset_manifest",),
            kind=EvaluationKind.DETERMINISTIC,
            evaluator="deterministic_asset_availability",
            evaluator_version="1.0.0",
            required=True,
            severity_if_failed="CRITICAL",
            on_failure="FAIL",
            repair_scope="NONE",
        ),
        deterministic_evaluator,
    )

    registry.register(
        QualityCheck(
            schema_version="quality-check.v1",
            check_id="asset_license_compliance_v1",
            target_artifact_types=("asset_manifest",),
            required_input_types=("asset_manifest",),
            kind=EvaluationKind.SPECIALIZED,
            evaluator="license_compliance_evaluator",
            evaluator_version="1.0.0",
            required=True,
            severity_if_failed="CRITICAL",
            on_failure="HUMAN_REVIEW",
            repair_scope="NONE",
        ),
        SpecializedCheckEvaluator(),
    )

    # Speech generation checks
    registry.register(
        QualityCheck(
            schema_version="quality-check.v1",
            check_id="speech_manifest_schema_v1",
            target_artifact_types=("speech_manifest",),
            required_input_types=("speech_manifest",),
            kind=EvaluationKind.DETERMINISTIC,
            evaluator="deterministic_schema_validator",
            evaluator_version="1.0.0",
            required=True,
            severity_if_failed="CRITICAL",
            on_failure="FAIL",
            repair_scope="NONE",
        ),
        deterministic_evaluator,
    )

    registry.register(
        QualityCheck(
            schema_version="quality-check.v1",
            check_id="speech_wer_cer_v1",
            target_artifact_types=("audio",),
            required_input_types=("audio", "speech_manifest", "asr_alignment"),
            kind=EvaluationKind.SPECIALIZED,
            evaluator="wer_cer_evaluator",
            evaluator_version="1.0.0",
            required=True,
            severity_if_failed="MAJOR",
            on_failure="REGENERATE",
            repair_scope="SCENE",
        ),
        SpecializedCheckEvaluator(),
    )

    registry.register(
        QualityCheck(
            schema_version="quality-check.v1",
            check_id="speech_critical_tokens_v1",
            target_artifact_types=("audio",),
            required_input_types=("audio", "speech_manifest", "asr_alignment"),
            kind=EvaluationKind.SPECIALIZED,
            evaluator="critical_token_evaluator",
            evaluator_version="1.0.0",
            required=True,
            severity_if_failed="CRITICAL",
            on_failure="REGENERATE",
            repair_scope="SCENE",
        ),
        SpecializedCheckEvaluator(),
    )

    registry.register(
        QualityCheck(
            schema_version="quality-check.v1",
            check_id="speech_forced_alignment_v1",
            target_artifact_types=("audio",),
            required_input_types=("audio", "speech_manifest", "asr_alignment"),
            kind=EvaluationKind.SPECIALIZED,
            evaluator="forced_alignment_evaluator",
            evaluator_version="1.0.0",
            required=True,
            severity_if_failed="MAJOR",
            on_failure="REGENERATE",
            repair_scope="SCENE",
        ),
        SpecializedCheckEvaluator(),
    )

    registry.register(
        QualityCheck(
            schema_version="quality-check.v1",
            check_id="speech_signal_quality_v1",
            target_artifact_types=("audio",),
            required_input_types=("audio",),
            kind=EvaluationKind.SPECIALIZED,
            evaluator="signal_quality_evaluator",
            evaluator_version="1.0.0",
            required=True,
            severity_if_failed="MINOR",
            on_failure="REGENERATE",
            repair_scope="ASSET",
        ),
        SpecializedCheckEvaluator(),
    )

    # Composition checks
    registry.register(
        QualityCheck(
            schema_version="quality-check.v1",
            check_id="composition_timeline_v1",
            target_artifact_types=("composition",),
            required_input_types=("composition",),
            kind=EvaluationKind.DETERMINISTIC,
            evaluator="deterministic_timeline_validator",
            evaluator_version="1.0.0",
            required=True,
            severity_if_failed="CRITICAL",
            on_failure="FAIL",
            repair_scope="NONE",
        ),
        deterministic_evaluator,
    )

    registry.register(
        QualityCheck(
            schema_version="quality-check.v1",
            check_id="composition_sync_v1",
            target_artifact_types=("composition",),
            required_input_types=("composition", "audio", "visual_plan"),
            kind=EvaluationKind.SPECIALIZED,
            evaluator="av_sync_evaluator",
            evaluator_version="1.0.0",
            required=True,
            severity_if_failed="MAJOR",
            on_failure="REGENERATE",
            repair_scope="SHOT",
        ),
        SpecializedCheckEvaluator(),
    )

    # Rendering checks
    registry.register(
        QualityCheck(
            schema_version="quality-check.v1",
            check_id="render_decode_v1",
            target_artifact_types=("rendered_video",),
            required_input_types=("rendered_video",),
            kind=EvaluationKind.SPECIALIZED,
            evaluator="decode_validator",
            evaluator_version="1.0.0",
            required=True,
            severity_if_failed="CRITICAL",
            on_failure="REGENERATE",
            repair_scope="SHOT",
        ),
        SpecializedCheckEvaluator(),
    )

    registry.register(
        QualityCheck(
            schema_version="quality-check.v1",
            check_id="render_profile_v1",
            target_artifact_types=("rendered_video",),
            required_input_types=("rendered_video", "render_profile"),
            kind=EvaluationKind.SPECIALIZED,
            evaluator="profile_validator",
            evaluator_version="1.0.0",
            required=True,
            severity_if_failed="MAJOR",
            on_failure="REGENERATE",
            repair_scope="SHOT",
        ),
        SpecializedCheckEvaluator(),
    )

    registry.register(
        QualityCheck(
            schema_version="quality-check.v1",
            check_id="render_timeline_v1",
            target_artifact_types=("rendered_video",),
            required_input_types=("rendered_video", "composition"),
            kind=EvaluationKind.SPECIALIZED,
            evaluator="timeline_validator",
            evaluator_version="1.0.0",
            required=True,
            severity_if_failed="MAJOR",
            on_failure="REGENERATE",
            repair_scope="SHOT",
        ),
        SpecializedCheckEvaluator(),
    )

    # Assembly checks
    registry.register(
        QualityCheck(
            schema_version="quality-check.v1",
            check_id="assembly_integrity_v1",
            target_artifact_types=("assembly",),
            required_input_types=("assembly", "rendered_chunks"),
            kind=EvaluationKind.SPECIALIZED,
            evaluator="assembly_integrity_evaluator",
            evaluator_version="1.0.0",
            required=True,
            severity_if_failed="CRITICAL",
            on_failure="REGENERATE",
            repair_scope="CUT",
        ),
        SpecializedCheckEvaluator(),
    )

    registry.register(
        QualityCheck(
            schema_version="quality-check.v1",
            check_id="assembly_audio_video_drift_v1",
            target_artifact_types=("assembly",),
            required_input_types=("assembly",),
            kind=EvaluationKind.SPECIALIZED,
            evaluator="av_drift_evaluator",
            evaluator_version="1.0.0",
            required=True,
            severity_if_failed="MAJOR",
            on_failure="REGENERATE",
            repair_scope="CUT",
        ),
        SpecializedCheckEvaluator(),
    )

    # Short derivative checks
    registry.register(
        QualityCheck(
            schema_version="quality-check.v1",
            check_id="short_derivative_integrity_v1",
            target_artifact_types=("short_video",),
            required_input_types=("short_video", "assembly"),
            kind=EvaluationKind.SPECIALIZED,
            evaluator="short_integrity_evaluator",
            evaluator_version="1.0.0",
            required=True,
            severity_if_failed="MAJOR",
            on_failure="REGENERATE",
            repair_scope="ASSET",
        ),
        SpecializedCheckEvaluator(),
    )

    # Human review gate (final publication)
    registry.register(
        QualityCheck(
            schema_version="quality-check.v1",
            check_id="human_publication_approval_v1",
            target_artifact_types=("assembly", "short_video"),
            required_input_types=("assembly", "short_video"),
            kind=EvaluationKind.HUMAN,
            evaluator="human_publication_reviewer",
            evaluator_version="1.0.0",
            required=True,
            severity_if_failed="CRITICAL",
            on_failure="FAIL",
            repair_scope="NONE",
        ),
        HumanCheckEvaluator(),
    )
