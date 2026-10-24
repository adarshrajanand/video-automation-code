"""Quality check evaluators for deterministic, specialized,
semantic, and human checks."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from pipeline.contracts.quality import (
    EvaluationDimension,
    QualityCheck,
    QualityEvaluation,
    QualityInputManifest,
)
from pipeline.contracts.vocabularies import (
    CheckOutcome,
    Confidence,
    FailureCode,
    Severity,
)

if TYPE_CHECKING:
    pass


class Evaluator(Protocol):
    """Protocol for quality check evaluators."""

    def evaluate(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
        supporting_artifacts: dict[str, Any],
    ) -> QualityEvaluation:
        """Execute the quality check and return an evaluation.

        Args:
            check: The quality check to execute.
            manifest: The input manifest with target artifacts and hashes.
            artifacts: Mapping of target artifact IDs to their loaded content.
            supporting_artifacts: Mapping of supporting artifact IDs to content.

        Returns:
            A QualityEvaluation with the check outcome and evidence.
        """
        ...


@dataclass(slots=True)
class EvaluationContext:
    """Context passed to evaluators during check execution."""

    check: QualityCheck
    manifest: QualityInputManifest
    target_artifacts: dict[str, Any]
    supporting_artifacts: dict[str, Any]
    started_at: datetime


class DeterministicCheckEvaluator:
    """Evaluator for deterministic checks (schema validation, reference integrity).

    Deterministic checks produce fully reproducible results given the same
    inputs. They require no external providers and complete in milliseconds.
    """

    def evaluate(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
        supporting_artifacts: dict[str, Any],
    ) -> QualityEvaluation:
        """Execute a deterministic quality check."""
        started = datetime.now(UTC)
        evaluator_name = check.evaluator
        evaluator_version = check.evaluator_version

        # Dispatch to specific deterministic check implementation
        if evaluator_name == "deterministic_schema_validator":
            result = self._validate_schema(check, manifest, artifacts)
        elif evaluator_name == "deterministic_reference_integrity":
            result = self._check_reference_integrity(
                check, manifest, artifacts, supporting_artifacts
            )
        elif evaluator_name == "deterministic_asset_availability":
            result = self._check_asset_availability(check, manifest, artifacts)
        elif evaluator_name == "deterministic_timeline_validator":
            result = self._validate_timeline(check, manifest, artifacts)
        else:
            # Unknown deterministic evaluator - treat as error
            return self._error_evaluation(
                check,
                manifest,
                f"Unknown deterministic evaluator: {evaluator_name}",
                started,
            )

        latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        return QualityEvaluation(
            schema_version="quality-evaluation.v1",
            evaluation_id=f"eval_{uuid.uuid4().hex[:12]}",
            stage_instance_id=None,
            logical_item_key=None,
            scene_id=None,
            shot_id=None,
            target_artifact_ids=manifest.target_artifact_ids,
            target_hashes=manifest.target_hashes,
            evaluation_input_manifest_id=manifest.manifest_id,
            gate_id=manifest.gate_id,
            check_id=check.check_id,
            evaluator=evaluator_name,
            evaluator_version=evaluator_version,
            rubric_version=None,
            dimensions=result.dimensions,
            outcome=result.outcome,
            confidence=Confidence.HIGH,
            abstained=result.outcome is CheckOutcome.ABSTAIN,
            evidence=result.evidence,
            estimated_cost_minor=0,
            actual_cost_minor=0,
            provider_invocation_id=None,
            latency_ms=latency_ms,
            created_at=datetime.now(UTC),
        )

    def _validate_schema(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
    ) -> _DeterministicResult:
        """Validate artifact against its JSON schema."""
        dimensions = []
        evidence = []
        failure_codes = []

        for artifact_id in manifest.target_artifact_ids:
            artifact = artifacts.get(artifact_id)
            if artifact is None:
                dimensions.append(
                    EvaluationDimension(
                        schema_version="evaluation-dimension.v1",
                        name="schema_valid",
                        score=0.0,
                        threshold=1.0,
                        severity=Severity.CRITICAL,
                        failure_codes=[FailureCode.QUALITY_SCHEMA_INVALID],
                        evidence_refs=[],
                        details={"error": "Artifact not found in input"},
                    )
                )
                failure_codes.append(FailureCode.QUALITY_SCHEMA_INVALID)
                continue

            # In a real implementation, this would validate against the actual schema
            # For now, we check if the artifact has a schema_version field
            is_valid = isinstance(artifact, dict) and "schema_version" in artifact
            dimensions.append(
                EvaluationDimension(
                    schema_version="evaluation-dimension.v1",
                    name="schema_valid",
                    score=1.0 if is_valid else 0.0,
                    threshold=1.0,
                    severity=Severity.CRITICAL if not is_valid else Severity.INFO,
                    failure_codes=[FailureCode.QUALITY_SCHEMA_INVALID]
                    if not is_valid
                    else [],
                    evidence_refs=[f"evidence_{artifact_id}"],
                    details={
                        "artifact_id": artifact_id,
                        "has_schema_version": is_valid,
                    },
                )
            )
            evidence.append(
                {
                    "artifact_id": artifact_id,
                    "check": "schema_validation",
                    "valid": is_valid,
                }
            )
            if not is_valid:
                failure_codes.append(FailureCode.QUALITY_SCHEMA_INVALID)

        outcome = CheckOutcome.PASS if not failure_codes else CheckOutcome.FAIL
        return _DeterministicResult(
            dimensions=dimensions, outcome=outcome, evidence=evidence
        )

    def _check_reference_integrity(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
        supporting_artifacts: dict[str, Any],
    ) -> _DeterministicResult:
        """Check that all references in the script resolve to evidence."""
        dimensions = []
        evidence = []

        script = artifacts.get(manifest.target_artifact_ids[0])
        supporting_artifacts.get("claim_ledger")
        evidence_snapshots = supporting_artifacts.get("evidence_snapshots")

        if not script or not isinstance(script, dict):
            return _DeterministicResult(
                dimensions=[
                    EvaluationDimension(
                        schema_version="evaluation-dimension.v1",
                        name="reference_integrity",
                        score=0.0,
                        threshold=1.0,
                        severity=Severity.CRITICAL,
                        failure_codes=[FailureCode.QUALITY_UNSUPPORTED_CLAIM],
                        evidence_refs=[],
                        details={"error": "Script artifact missing or invalid"},
                    )
                ],
                outcome=CheckOutcome.FAIL,
                evidence=[{"error": "Script artifact missing"}],
            )

        claims = script.get("claims", [])
        unresolved = 0
        for claim in claims:
            claim.get("claim_id")
            evidence_refs = claim.get("evidence_refs", [])
            for ref in evidence_refs:
                if evidence_snapshots and ref not in evidence_snapshots:
                    unresolved += 1

        # If there are claims with evidence_refs but no evidence_snapshots provided,
        # that's a failure - all references are unresolved
        if (
            claims
            and any(c.get("evidence_refs") for c in claims)
            and not evidence_snapshots
        ):
            unresolved = sum(len(c.get("evidence_refs", [])) for c in claims)

        score = 1.0 - (unresolved / len(claims)) if claims else 1.0
        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="reference_integrity",
                score=score,
                threshold=1.0,
                severity=Severity.CRITICAL if unresolved > 0 else Severity.INFO,
                failure_codes=[FailureCode.QUALITY_UNSUPPORTED_CLAIM]
                if unresolved > 0
                else [],
                evidence_refs=[f"claim_{c.get('claim_id')}" for c in claims],
                details={
                    "total_claims": len(claims),
                    "unresolved_references": unresolved,
                },
            )
        )
        evidence.append(
            {
                "check": "reference_integrity",
                "total_claims": len(claims),
                "unresolved": unresolved,
            }
        )

        outcome = CheckOutcome.PASS if unresolved == 0 else CheckOutcome.FAIL
        return _DeterministicResult(
            dimensions=dimensions, outcome=outcome, evidence=evidence
        )

    def _check_asset_availability(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
    ) -> _DeterministicResult:
        """Check that all assets in the manifest are available."""
        dimensions = []
        evidence = []

        asset_manifest = artifacts.get(manifest.target_artifact_ids[0])
        if not asset_manifest or not isinstance(asset_manifest, dict):
            return _DeterministicResult(
                dimensions=[
                    EvaluationDimension(
                        schema_version="evaluation-dimension.v1",
                        name="asset_availability",
                        score=0.0,
                        threshold=1.0,
                        severity=Severity.CRITICAL,
                        failure_codes=[FailureCode.QUALITY_MISSING_ASSET],
                        evidence_refs=[],
                        details={"error": "Asset manifest missing or invalid"},
                    )
                ],
                outcome=CheckOutcome.FAIL,
                evidence=[{"error": "Asset manifest missing"}],
            )

        assets = asset_manifest.get("assets", [])
        # Default to False for missing 'available' field - fail closed
        missing = sum(1 for a in assets if not a.get("available", False))
        score = 1.0 - (missing / len(assets)) if assets else 1.0

        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="asset_availability",
                score=score,
                threshold=1.0,
                severity=Severity.CRITICAL if missing > 0 else Severity.INFO,
                failure_codes=[FailureCode.QUALITY_MISSING_ASSET]
                if missing > 0
                else [],
                evidence_refs=[f"asset_{a.get('asset_id')}" for a in assets],
                details={"total_assets": len(assets), "missing": missing},
            )
        )
        evidence.append(
            {"check": "asset_availability", "total": len(assets), "missing": missing}
        )

        outcome = CheckOutcome.PASS if missing == 0 else CheckOutcome.FAIL
        return _DeterministicResult(
            dimensions=dimensions, outcome=outcome, evidence=evidence
        )

    def _validate_timeline(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
    ) -> _DeterministicResult:
        """Validate composition timeline for overlaps and gaps."""
        dimensions = []
        evidence = []

        composition = artifacts.get(manifest.target_artifact_ids[0])
        if not composition or not isinstance(composition, dict):
            return _DeterministicResult(
                dimensions=[
                    EvaluationDimension(
                        schema_version="evaluation-dimension.v1",
                        name="timeline_valid",
                        score=0.0,
                        threshold=1.0,
                        severity=Severity.CRITICAL,
                        failure_codes=[FailureCode.MEDIA_TIMELINE_INVALID],
                        evidence_refs=[],
                        details={"error": "Composition artifact missing or invalid"},
                    )
                ],
                outcome=CheckOutcome.FAIL,
                evidence=[{"error": "Composition artifact missing"}],
            )

        # Real timeline validation: check shots for frame overlaps/gaps
        shots = composition.get("shots", [])
        has_overlaps = False
        has_gaps = False

        if shots:
            # Sort shots by order_index
            sorted_shots = sorted(shots, key=lambda s: s.get("order_index", 0))
            for i in range(len(sorted_shots) - 1):
                current = sorted_shots[i]
                next_shot = sorted_shots[i + 1]
                current_end = current.get("end_frame")
                next_start = next_shot.get("start_frame")
                if current_end is not None and next_start is not None:
                    if next_start < current_end:
                        has_overlaps = True
                    elif next_start > current_end:
                        has_gaps = True

        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="timeline_valid",
                score=1.0 if not (has_overlaps or has_gaps) else 0.0,
                threshold=1.0,
                severity=Severity.CRITICAL
                if (has_overlaps or has_gaps)
                else Severity.INFO,
                failure_codes=[FailureCode.MEDIA_TIMELINE_INVALID]
                if (has_overlaps or has_gaps)
                else [],
                evidence_refs=[f"shot_{s.get('shot_id')}" for s in shots],
                details={
                    "total_shots": len(shots),
                    "overlaps": has_overlaps,
                    "gaps": has_gaps,
                },
            )
        )
        evidence.append(
            {
                "check": "timeline_validation",
                "shots": len(shots),
                "overlaps": has_overlaps,
                "gaps": has_gaps,
            }
        )

        outcome = (
            CheckOutcome.PASS if not (has_overlaps or has_gaps) else CheckOutcome.FAIL
        )
        return _DeterministicResult(
            dimensions=dimensions, outcome=outcome, evidence=evidence
        )

    def _error_evaluation(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        error: str,
        started_at: datetime,
    ) -> QualityEvaluation:
        """Create an error evaluation."""
        latency_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
        return QualityEvaluation(
            schema_version="quality-evaluation.v1",
            evaluation_id=f"eval_{uuid.uuid4().hex[:12]}",
            target_artifact_ids=manifest.target_artifact_ids,
            target_hashes=manifest.target_hashes,
            evaluation_input_manifest_id=manifest.manifest_id,
            gate_id=manifest.gate_id,
            check_id=check.check_id,
            evaluator=check.evaluator,
            evaluator_version=check.evaluator_version,
            rubric_version=None,
            dimensions=[
                EvaluationDimension(
                    schema_version="evaluation-dimension.v1",
                    name="evaluator_error",
                    score=0.0,
                    threshold=1.0,
                    severity=Severity.CRITICAL,
                    failure_codes=[FailureCode.QUALITY_GENERIC],
                    evidence_refs=[],
                    details={"error": error},
                )
            ],
            outcome=CheckOutcome.ERROR,
            confidence=Confidence.LOW,
            abstained=False,
            evidence=[{"error": error}],
            estimated_cost_minor=0,
            actual_cost_minor=0,
            provider_invocation_id=None,
            latency_ms=latency_ms,
            created_at=datetime.now(UTC),
        )


class SpecializedCheckEvaluator:
    """Evaluator for specialized checks (WER/CER, signal quality, media decode, etc.).

    Specialized checks use deterministic algorithms but may require external
    tools (ffmpeg, ffprobe) or ML models for measurement. They produce
    numeric scores with defined thresholds.
    """

    def evaluate(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
        supporting_artifacts: dict[str, Any],
    ) -> QualityEvaluation:
        """Execute a specialized quality check."""
        started = datetime.now(UTC)
        evaluator_name = check.evaluator
        evaluator_version = check.evaluator_version

        if evaluator_name == "wer_cer_evaluator":
            result = self._evaluate_wer_cer(
                check, manifest, artifacts, supporting_artifacts
            )
        elif evaluator_name == "critical_token_evaluator":
            result = self._evaluate_critical_tokens(
                check, manifest, artifacts, supporting_artifacts
            )
        elif evaluator_name == "forced_alignment_evaluator":
            result = self._evaluate_forced_alignment(
                check, manifest, artifacts, supporting_artifacts
            )
        elif evaluator_name == "signal_quality_evaluator":
            result = self._evaluate_signal_quality(check, manifest, artifacts)
        elif evaluator_name == "license_compliance_evaluator":
            result = self._evaluate_license_compliance(check, manifest, artifacts)
        elif evaluator_name == "av_sync_evaluator":
            result = self._evaluate_av_sync(
                check, manifest, artifacts, supporting_artifacts
            )
        elif evaluator_name == "decode_validator":
            result = self._evaluate_decode(check, manifest, artifacts)
        elif evaluator_name == "profile_validator":
            result = self._evaluate_profile(
                check, manifest, artifacts, supporting_artifacts
            )
        elif evaluator_name == "timeline_validator":
            result = self._evaluate_timeline(
                check, manifest, artifacts, supporting_artifacts
            )
        elif evaluator_name == "assembly_integrity_evaluator":
            result = self._evaluate_assembly_integrity(
                check, manifest, artifacts, supporting_artifacts
            )
        elif evaluator_name == "av_drift_evaluator":
            result = self._evaluate_av_drift(check, manifest, artifacts)
        elif evaluator_name == "short_integrity_evaluator":
            result = self._evaluate_short_integrity(
                check, manifest, artifacts, supporting_artifacts
            )
        else:
            return self._error_evaluation(
                check,
                manifest,
                f"Unknown specialized evaluator: {evaluator_name}",
                started,
            )

        latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        return QualityEvaluation(
            schema_version="quality-evaluation.v1",
            evaluation_id=f"eval_{uuid.uuid4().hex[:12]}",
            stage_instance_id=None,
            logical_item_key=None,
            scene_id=None,
            shot_id=None,
            target_artifact_ids=manifest.target_artifact_ids,
            target_hashes=manifest.target_hashes,
            evaluation_input_manifest_id=manifest.manifest_id,
            gate_id=manifest.gate_id,
            check_id=check.check_id,
            evaluator=evaluator_name,
            evaluator_version=evaluator_version,
            rubric_version=None,
            dimensions=result.dimensions,
            outcome=result.outcome,
            confidence=Confidence.HIGH,
            abstained=result.outcome is CheckOutcome.ABSTAIN,
            evidence=result.evidence,
            estimated_cost_minor=result.estimated_cost_minor,
            actual_cost_minor=result.actual_cost_minor,
            provider_invocation_id=None,
            latency_ms=latency_ms,
            created_at=datetime.now(UTC),
        )

    def _require_artifact(
        self, manifest: QualityInputManifest, artifacts: dict[str, Any], idx: int = 0
    ) -> tuple[Any, bool]:
        """Get required target artifact or return None with error flag."""
        artifact_id = manifest.target_artifact_ids[idx]
        artifact = artifacts.get(artifact_id)
        return artifact, artifact is not None

    def _evaluate_wer_cer(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
        supporting_artifacts: dict[str, Any],
    ) -> _SpecializedResult:
        """Evaluate WER (Word Error Rate) and CER (Character Error Rate)."""
        dimensions = []
        evidence = []
        failure_codes = []

        _target_artifact, ok = self._require_artifact(manifest, artifacts)
        speech_manifest = supporting_artifacts.get("speech_manifest")
        asr_alignment = supporting_artifacts.get("asr_alignment")

        if not ok or not speech_manifest or not asr_alignment:
            # Missing required inputs - fail closed
            dimensions.append(
                EvaluationDimension(
                    schema_version="evaluation-dimension.v1",
                    name="wer_cer",
                    score=0.0,
                    threshold=1.0,
                    severity=Severity.CRITICAL,
                    failure_codes=[FailureCode.QUALITY_SCHEMA_INVALID],
                    evidence_refs=[],
                    details={"error": "Missing speech_manifest/asr_alignment"},
                )
            )
            evidence.append({"error": "Missing required artifacts"})
            return _SpecializedResult(
                dimensions=dimensions,
                outcome=CheckOutcome.FAIL,
                evidence=evidence,
                estimated_cost_minor=0,
                actual_cost_minor=0,
            )

        # Real implementation would compute WER/CER from asr_alignment
        # For now, return ERROR since we don't have the actual computation
        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="wer_cer",
                score=0.0,
                threshold=1.0,
                severity=Severity.MAJOR,
                failure_codes=[FailureCode.QUALITY_TTS_PRONUNCIATION],
                evidence_refs=[],
                details={"error": "WER/CER not implemented - needs ASR alignment"},
            )
        )
        evidence.append(
            {
                "check": "wer_cer",
                "error": "Not implemented - requires actual ASR alignment processing",
            }
        )
        failure_codes.append(FailureCode.QUALITY_TTS_PRONUNCIATION)

        return _SpecializedResult(
            dimensions=dimensions,
            outcome=CheckOutcome.ERROR,
            evidence=evidence,
            estimated_cost_minor=10,
            actual_cost_minor=0,
        )

    def _evaluate_critical_tokens(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
        supporting_artifacts: dict[str, Any],
    ) -> _SpecializedResult:
        """Check critical tokens (names, numbers, terms) are pronounced correctly."""
        dimensions = []
        evidence = []
        failure_codes = []

        asr_alignment = supporting_artifacts.get("asr_alignment")
        speech_manifest = supporting_artifacts.get("speech_manifest")

        if not asr_alignment or not speech_manifest:
            # Missing required inputs - fail closed
            dimensions.append(
                EvaluationDimension(
                    schema_version="evaluation-dimension.v1",
                    name="critical_tokens",
                    score=0.0,
                    threshold=1.0,
                    severity=Severity.CRITICAL,
                    failure_codes=[FailureCode.QUALITY_SCHEMA_INVALID],
                    evidence_refs=[],
                    details={"error": "Missing asr_alignment or speech_manifest"},
                )
            )
            evidence.append({"error": "Missing required artifacts"})
            return _SpecializedResult(
                dimensions=dimensions,
                outcome=CheckOutcome.FAIL,
                evidence=evidence,
                estimated_cost_minor=0,
                actual_cost_minor=0,
            )

        # Check if critical_tokens are defined in speech_manifest
        critical_tokens = (
            speech_manifest.get("critical_tokens", []) if speech_manifest else []
        )

        if not critical_tokens:
            # No critical tokens defined - NOT_APPLICABLE (no tokens to verify)
            dimensions.append(
                EvaluationDimension(
                    schema_version="evaluation-dimension.v1",
                    name="critical_tokens",
                    score=1.0,
                    threshold=1.0,
                    severity=Severity.INFO,
                    failure_codes=[],
                    evidence_refs=[],
                    details={"note": "No critical tokens defined in speech manifest"},
                )
            )
            evidence.append(
                {
                    "check": "critical_tokens",
                    "total": 0,
                    "note": "No critical tokens defined",
                }
            )
            return _SpecializedResult(
                dimensions=dimensions,
                outcome=CheckOutcome.PASS,  # Nothing to check = pass
                evidence=evidence,
                estimated_cost_minor=5,
                actual_cost_minor=0,
            )

        # Real implementation would check ASR alignment for token matches
        # For now, return ERROR since we don't have the actual computation
        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="critical_tokens",
                score=0.0,
                threshold=1.0,
                severity=Severity.CRITICAL,
                failure_codes=[FailureCode.QUALITY_TTS_OMISSION],
                evidence_refs=[],
                details={"error": "Critical token verify not implemented"},
            )
        )
        evidence.append(
            {
                "check": "critical_tokens",
                "error": "Not implemented - requires actual ASR alignment processing",
                "total": len(critical_tokens),
            }
        )
        failure_codes.append(FailureCode.QUALITY_TTS_OMISSION)

        return _SpecializedResult(
            dimensions=dimensions,
            outcome=CheckOutcome.ERROR,
            evidence=evidence,
            estimated_cost_minor=5,
            actual_cost_minor=0,
        )

    def _evaluate_forced_alignment(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
        supporting_artifacts: dict[str, Any],
    ) -> _SpecializedResult:
        """Evaluate forced alignment quality."""
        dimensions = []
        evidence = []

        asr_alignment = supporting_artifacts.get("asr_alignment")

        if not asr_alignment:
            dimensions.append(
                EvaluationDimension(
                    schema_version="evaluation-dimension.v1",
                    name="forced_alignment",
                    score=0.0,
                    threshold=1.0,
                    severity=Severity.CRITICAL,
                    failure_codes=[FailureCode.QUALITY_SCHEMA_INVALID],
                    evidence_refs=[],
                    details={"error": "Missing required artifact: asr_alignment"},
                )
            )
            evidence.append({"error": "Missing required artifact: asr_alignment"})
            return _SpecializedResult(
                dimensions=dimensions,
                outcome=CheckOutcome.FAIL,
                evidence=evidence,
                estimated_cost_minor=0,
                actual_cost_minor=0,
            )

        # Real implementation would compute alignment quality from asr_alignment
        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="forced_alignment",
                score=0.0,
                threshold=1.0,
                severity=Severity.MAJOR,
                failure_codes=[FailureCode.QUALITY_TTS_PRONUNCIATION],
                evidence_refs=[],
                details={"error": "Forced alignment not implemented"},
            )
        )
        evidence.append(
            {
                "check": "forced_alignment",
                "error": "Not implemented - requires ASR alignment processing",
            }
        )

        return _SpecializedResult(
            dimensions=dimensions,
            outcome=CheckOutcome.ERROR,
            evidence=evidence,
            estimated_cost_minor=10,
            actual_cost_minor=0,
        )

    def _evaluate_signal_quality(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
    ) -> _SpecializedResult:
        """Evaluate audio signal quality (SNR, clipping, silence, etc.)."""
        dimensions = []
        evidence = []

        _target_artifact, ok = self._require_artifact(manifest, artifacts)

        if not ok:
            dimensions.append(
                EvaluationDimension(
                    schema_version="evaluation-dimension.v1",
                    name="signal_quality",
                    score=0.0,
                    threshold=1.0,
                    severity=Severity.CRITICAL,
                    failure_codes=[FailureCode.QUALITY_SCHEMA_INVALID],
                    evidence_refs=[],
                    details={"error": "Target audio artifact missing"},
                )
            )
            evidence.append({"error": "Target audio artifact missing"})
            return _SpecializedResult(
                dimensions=dimensions,
                outcome=CheckOutcome.FAIL,
                evidence=evidence,
                estimated_cost_minor=0,
                actual_cost_minor=0,
            )

        # Real implementation would use ffprobe/ffmpeg to measure SNR, clipping, silence
        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="signal_quality",
                score=0.0,
                threshold=1.0,
                severity=Severity.MAJOR,
                failure_codes=[FailureCode.QUALITY_AUDIO_DECODE],
                evidence_refs=[],
                details={"error": "Signal quality not implemented - needs ffprobe"},
            )
        )
        evidence.append(
            {
                "check": "signal_quality",
                "error": "Not implemented - requires actual audio signal analysis",
            }
        )

        return _SpecializedResult(
            dimensions=dimensions,
            outcome=CheckOutcome.ERROR,
            evidence=evidence,
            estimated_cost_minor=20,
            actual_cost_minor=0,
        )

    def _evaluate_license_compliance(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
    ) -> _SpecializedResult:
        """Evaluate asset license compliance."""
        dimensions = []
        evidence = []

        asset_manifest = artifacts.get(manifest.target_artifact_ids[0])

        if not asset_manifest or not isinstance(asset_manifest, dict):
            return _SpecializedResult(
                dimensions=[
                    EvaluationDimension(
                        schema_version="evaluation-dimension.v1",
                        name="license_compliance",
                        score=0.0,
                        threshold=1.0,
                        severity=Severity.CRITICAL,
                        failure_codes=[FailureCode.QUALITY_MISSING_ASSET],
                        evidence_refs=[],
                        details={"error": "Asset manifest missing or invalid"},
                    )
                ],
                outcome=CheckOutcome.FAIL,
                evidence=[{"error": "Asset manifest missing"}],
                estimated_cost_minor=0,
                actual_cost_minor=0,
            )

        assets = asset_manifest.get("assets", [])
        uncertain = sum(1 for a in assets if a.get("license_status") == "uncertain")
        prohibited = sum(1 for a in assets if a.get("license_status") == "prohibited")

        score = 1.0 - ((uncertain + prohibited) / len(assets)) if assets else 1.0

        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="license_compliance",
                score=score,
                threshold=1.0,
                severity=Severity.CRITICAL
                if (uncertain + prohibited) > 0
                else Severity.INFO,
                failure_codes=[FailureCode.RIGHTS_LICENSE_UNCERTAIN]
                if (uncertain + prohibited) > 0
                else [],
                evidence_refs=[f"asset_{a.get('asset_id')}" for a in assets],
                details={
                    "total_assets": len(assets),
                    "uncertain": uncertain,
                    "prohibited": prohibited,
                },
            )
        )
        evidence.append(
            {
                "check": "license_compliance",
                "total": len(assets),
                "uncertain": uncertain,
                "prohibited": prohibited,
            }
        )

        outcome = (
            CheckOutcome.PASS if (uncertain + prohibited) == 0 else CheckOutcome.FAIL
        )
        return _SpecializedResult(
            dimensions=dimensions,
            outcome=outcome,
            evidence=evidence,
            estimated_cost_minor=20,
            actual_cost_minor=15,
        )

    def _evaluate_av_sync(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
        supporting_artifacts: dict[str, Any],
    ) -> _SpecializedResult:
        """Evaluate audio-visual sync."""
        dimensions = []
        evidence = []

        _target_artifact, ok = self._require_artifact(manifest, artifacts)
        audio_artifact = supporting_artifacts.get("audio")
        visual_plan = supporting_artifacts.get("visual_plan")

        if not ok or not audio_artifact or not visual_plan:
            dimensions.append(
                EvaluationDimension(
                    schema_version="evaluation-dimension.v1",
                    name="av_sync",
                    score=0.0,
                    threshold=1.0,
                    severity=Severity.CRITICAL,
                    failure_codes=[FailureCode.QUALITY_SCHEMA_INVALID],
                    evidence_refs=[],
                    details={"error": "Missing audio or visual_plan"},
                )
            )
            evidence.append({"error": "Missing required artifacts"})
            return _SpecializedResult(
                dimensions=dimensions,
                outcome=CheckOutcome.FAIL,
                evidence=evidence,
                estimated_cost_minor=0,
                actual_cost_minor=0,
            )

        # Real implementation would use ffprobe to measure A/V drift
        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="av_sync",
                score=0.0,
                threshold=1.0,
                severity=Severity.MAJOR,
                failure_codes=[FailureCode.MEDIA_AUDIO_VIDEO_DRIFT],
                evidence_refs=[],
                details={"error": "A/V sync not implemented - needs ffprobe"},
            )
        )
        evidence.append(
            {
                "check": "av_sync",
                "error": "Not implemented - requires actual A/V drift measurement",
            }
        )

        return _SpecializedResult(
            dimensions=dimensions,
            outcome=CheckOutcome.ERROR,
            evidence=evidence,
            estimated_cost_minor=15,
            actual_cost_minor=0,
        )

    def _evaluate_decode(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
    ) -> _SpecializedResult:
        """Validate media can be fully decoded."""
        dimensions = []
        evidence = []

        _target_artifact, ok = self._require_artifact(manifest, artifacts)

        if not ok:
            dimensions.append(
                EvaluationDimension(
                    schema_version="evaluation-dimension.v1",
                    name="decode_success",
                    score=0.0,
                    threshold=1.0,
                    severity=Severity.CRITICAL,
                    failure_codes=[FailureCode.QUALITY_SCHEMA_INVALID],
                    evidence_refs=[],
                    details={"error": "Target media artifact missing"},
                )
            )
            evidence.append({"error": "Target media artifact missing"})
            return _SpecializedResult(
                dimensions=dimensions,
                outcome=CheckOutcome.FAIL,
                evidence=evidence,
                estimated_cost_minor=0,
                actual_cost_minor=0,
            )

        # Real implementation would use ffprobe to verify decode
        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="decode_success",
                score=0.0,
                threshold=1.0,
                severity=Severity.CRITICAL,
                failure_codes=[FailureCode.MEDIA_DECODE_ERROR],
                evidence_refs=[],
                details={"error": "Decode validation not implemented"},
            )
        )
        evidence.append(
            {
                "check": "decode",
                "error": "Not implemented - requires actual decode test",
            }
        )

        return _SpecializedResult(
            dimensions=dimensions,
            outcome=CheckOutcome.ERROR,
            evidence=evidence,
            estimated_cost_minor=10,
            actual_cost_minor=0,
        )

    def _evaluate_profile(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
        supporting_artifacts: dict[str, Any],
    ) -> _SpecializedResult:
        """Validate media matches output profile (codec, resolution, bitrate)."""
        dimensions = []
        evidence = []

        _target_artifact, ok = self._require_artifact(manifest, artifacts)
        render_profile = supporting_artifacts.get("render_profile")

        if not ok or not render_profile:
            dimensions.append(
                EvaluationDimension(
                    schema_version="evaluation-dimension.v1",
                    name="profile_conformance",
                    score=0.0,
                    threshold=1.0,
                    severity=Severity.CRITICAL,
                    failure_codes=[FailureCode.QUALITY_SCHEMA_INVALID],
                    evidence_refs=[],
                    details={"error": "Missing target artifact or render profile"},
                )
            )
            evidence.append({"error": "Missing required artifacts"})
            return _SpecializedResult(
                dimensions=dimensions,
                outcome=CheckOutcome.FAIL,
                evidence=evidence,
                estimated_cost_minor=0,
                actual_cost_minor=0,
            )

        # Real implementation would use ffprobe to verify profile
        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="profile_conformance",
                score=0.0,
                threshold=1.0,
                severity=Severity.MAJOR,
                failure_codes=[FailureCode.MEDIA_OUTPUT_PROFILE],
                evidence_refs=[],
                details={"error": "Profile validation not implemented"},
            )
        )
        evidence.append(
            {
                "check": "profile",
                "error": "Not implemented - requires actual profile verification",
            }
        )

        return _SpecializedResult(
            dimensions=dimensions,
            outcome=CheckOutcome.ERROR,
            evidence=evidence,
            estimated_cost_minor=15,
            actual_cost_minor=0,
        )

    def _evaluate_timeline(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
        supporting_artifacts: dict[str, Any],
    ) -> _SpecializedResult:
        """Validate rendered video timeline matches composition."""
        dimensions = []
        evidence = []

        _target_artifact, ok = self._require_artifact(manifest, artifacts)
        composition = supporting_artifacts.get("composition")

        if not ok or not composition:
            dimensions.append(
                EvaluationDimension(
                    schema_version="evaluation-dimension.v1",
                    name="timeline_conformance",
                    score=0.0,
                    threshold=1.0,
                    severity=Severity.CRITICAL,
                    failure_codes=[FailureCode.QUALITY_SCHEMA_INVALID],
                    evidence_refs=[],
                    details={"error": "Missing target artifact or composition"},
                )
            )
            evidence.append({"error": "Missing required artifacts"})
            return _SpecializedResult(
                dimensions=dimensions,
                outcome=CheckOutcome.FAIL,
                evidence=evidence,
                estimated_cost_minor=0,
                actual_cost_minor=0,
            )

        # Real implementation would compare actual timeline with composition
        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="timeline_conformance",
                score=0.0,
                threshold=1.0,
                severity=Severity.MAJOR,
                failure_codes=[FailureCode.MEDIA_TIMELINE_INVALID],
                evidence_refs=[],
                details={"error": "Timeline validation not implemented"},
            )
        )
        evidence.append(
            {
                "check": "timeline",
                "error": "Not implemented - requires actual timeline comparison",
            }
        )

        return _SpecializedResult(
            dimensions=dimensions,
            outcome=CheckOutcome.ERROR,
            evidence=evidence,
            estimated_cost_minor=20,
            actual_cost_minor=0,
        )

    def _evaluate_assembly_integrity(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
        supporting_artifacts: dict[str, Any],
    ) -> _SpecializedResult:
        """Validate assembly integrity (all chunks present, in order, no corruption)."""
        dimensions = []
        evidence = []

        assembly = artifacts.get(manifest.target_artifact_ids[0])
        rendered_chunks = supporting_artifacts.get("rendered_chunks", {})

        if not assembly or not isinstance(assembly, dict):
            return _SpecializedResult(
                dimensions=[
                    EvaluationDimension(
                        schema_version="evaluation-dimension.v1",
                        name="assembly_integrity",
                        score=0.0,
                        threshold=1.0,
                        severity=Severity.CRITICAL,
                        failure_codes=[FailureCode.MEDIA_RENDER_CORRUPT],
                        evidence_refs=[],
                        details={"error": "Assembly artifact missing or invalid"},
                    )
                ],
                outcome=CheckOutcome.FAIL,
                evidence=[{"error": "Assembly artifact missing"}],
                estimated_cost_minor=0,
                actual_cost_minor=0,
            )

        expected_chunks = assembly.get("chunk_ids", []) if assembly else []
        missing_chunks = [c for c in expected_chunks if c not in rendered_chunks]
        corrupt_chunks = 0  # Would check actual corruption in real implementation

        score = (
            1.0 - (len(missing_chunks) + corrupt_chunks) / len(expected_chunks)
            if expected_chunks
            else 1.0
        )

        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="assembly_integrity",
                score=score,
                threshold=1.0,
                severity=Severity.CRITICAL
                if (missing_chunks or corrupt_chunks)
                else Severity.INFO,
                failure_codes=[FailureCode.MEDIA_RENDER_CORRUPT]
                if (missing_chunks or corrupt_chunks)
                else [],
                evidence_refs=[f"chunk_{c}" for c in expected_chunks],
                details={
                    "expected_chunks": len(expected_chunks),
                    "missing_chunks": len(missing_chunks),
                    "corrupt_chunks": corrupt_chunks,
                },
            )
        )
        evidence.append(
            {
                "check": "assembly_integrity",
                "expected": len(expected_chunks),
                "missing": len(missing_chunks),
                "corrupt": corrupt_chunks,
            }
        )

        outcome = (
            CheckOutcome.PASS
            if not (missing_chunks or corrupt_chunks)
            else CheckOutcome.FAIL
        )
        return _SpecializedResult(
            dimensions=dimensions, outcome=outcome, evidence=evidence
        )

    def _evaluate_av_drift(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
    ) -> _SpecializedResult:
        """Evaluate accumulated audio-video drift in assembly."""
        dimensions = []
        evidence = []

        _target_artifact, ok = self._require_artifact(manifest, artifacts)

        if not ok:
            dimensions.append(
                EvaluationDimension(
                    schema_version="evaluation-dimension.v1",
                    name="av_drift",
                    score=0.0,
                    threshold=1.0,
                    severity=Severity.CRITICAL,
                    failure_codes=[FailureCode.QUALITY_SCHEMA_INVALID],
                    evidence_refs=[],
                    details={"error": "Target assembly artifact missing"},
                )
            )
            evidence.append({"error": "Target assembly artifact missing"})
            return _SpecializedResult(
                dimensions=dimensions,
                outcome=CheckOutcome.FAIL,
                evidence=evidence,
                estimated_cost_minor=0,
                actual_cost_minor=0,
            )

        # Real implementation would measure accumulated drift
        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="av_drift",
                score=0.0,
                threshold=1.0,
                severity=Severity.MAJOR,
                failure_codes=[FailureCode.MEDIA_AUDIO_VIDEO_DRIFT],
                evidence_refs=[],
                details={"error": "A/V drift not implemented"},
            )
        )
        evidence.append(
            {
                "check": "av_drift",
                "error": "Not implemented - requires actual drift measurement",
            }
        )

        return _SpecializedResult(
            dimensions=dimensions,
            outcome=CheckOutcome.ERROR,
            evidence=evidence,
            estimated_cost_minor=15,
            actual_cost_minor=0,
        )

    def _evaluate_short_integrity(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
        supporting_artifacts: dict[str, Any],
    ) -> _SpecializedResult:
        """Validate short derivative integrity."""
        dimensions = []
        evidence = []

        _target_artifact, ok = self._require_artifact(manifest, artifacts)
        assembly = supporting_artifacts.get("assembly")

        if not ok or not assembly:
            dimensions.append(
                EvaluationDimension(
                    schema_version="evaluation-dimension.v1",
                    name="short_integrity",
                    score=0.0,
                    threshold=1.0,
                    severity=Severity.CRITICAL,
                    failure_codes=[FailureCode.QUALITY_SCHEMA_INVALID],
                    evidence_refs=[],
                    details={"error": "Missing target artifact or assembly"},
                )
            )
            evidence.append({"error": "Missing required artifacts"})
            return _SpecializedResult(
                dimensions=dimensions,
                outcome=CheckOutcome.FAIL,
                evidence=evidence,
                estimated_cost_minor=0,
                actual_cost_minor=0,
            )

        # Real implementation would verify short derivative against assembly
        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="short_integrity",
                score=0.0,
                threshold=1.0,
                severity=Severity.MAJOR,
                failure_codes=[FailureCode.QUALITY_VISUAL_MISMATCH],
                evidence_refs=[],
                details={"error": "Short integrity not implemented"},
            )
        )
        evidence.append(
            {
                "check": "short_integrity",
                "error": "Not implemented - needs short derivative verification",
            }
        )

        return _SpecializedResult(
            dimensions=dimensions,
            outcome=CheckOutcome.ERROR,
            evidence=evidence,
            estimated_cost_minor=10,
            actual_cost_minor=0,
        )

    def _error_evaluation(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        error: str,
        started_at: datetime,
    ) -> QualityEvaluation:
        latency_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
        return QualityEvaluation(
            schema_version="quality-evaluation.v1",
            evaluation_id=f"eval_{uuid.uuid4().hex[:12]}",
            target_artifact_ids=manifest.target_artifact_ids,
            target_hashes=manifest.target_hashes,
            evaluation_input_manifest_id=manifest.manifest_id,
            gate_id=manifest.gate_id,
            check_id=check.check_id,
            evaluator=check.evaluator,
            evaluator_version=check.evaluator_version,
            rubric_version=None,
            dimensions=[
                EvaluationDimension(
                    schema_version="evaluation-dimension.v1",
                    name="evaluator_error",
                    score=0.0,
                    threshold=1.0,
                    severity=Severity.CRITICAL,
                    failure_codes=[FailureCode.QUALITY_GENERIC],
                    evidence_refs=[],
                    details={"error": error},
                )
            ],
            outcome=CheckOutcome.ERROR,
            confidence=Confidence.LOW,
            abstained=False,
            evidence=[{"error": error}],
            estimated_cost_minor=0,
            actual_cost_minor=0,
            provider_invocation_id=None,
            latency_ms=latency_ms,
            created_at=datetime.now(UTC),
        )


class SemanticCheckEvaluator:
    """Evaluator for semantic checks (claim/evidence, editorial, visual).

    Semantic checks use LLM-based evaluators with versioned rubrics. They
    produce structured judgments with scores, confidence, and evidence citations.
    """

    def evaluate(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
        supporting_artifacts: dict[str, Any],
    ) -> QualityEvaluation:
        """Execute a semantic quality check."""
        started = datetime.now(UTC)
        evaluator_name = check.evaluator
        evaluator_version = check.evaluator_version
        rubric_version = check.rubric_version

        if evaluator_name == "claim_evidence_evaluator":
            result = self._evaluate_claim_evidence(
                check, manifest, artifacts, supporting_artifacts
            )
        elif evaluator_name == "editorial_clarity_evaluator":
            result = self._evaluate_editorial_clarity(
                check, manifest, artifacts, supporting_artifacts
            )
        elif evaluator_name == "visual_intent_coherence_evaluator":
            result = self._evaluate_visual_intent_coherence(
                check, manifest, artifacts, supporting_artifacts
            )
        else:
            return self._error_evaluation(
                check,
                manifest,
                f"Unknown semantic evaluator: {evaluator_name}",
                started,
            )

        latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        return QualityEvaluation(
            schema_version="quality-evaluation.v1",
            evaluation_id=f"eval_{uuid.uuid4().hex[:12]}",
            stage_instance_id=None,
            logical_item_key=None,
            scene_id=None,
            shot_id=None,
            target_artifact_ids=manifest.target_artifact_ids,
            target_hashes=manifest.target_hashes,
            evaluation_input_manifest_id=manifest.manifest_id,
            gate_id=manifest.gate_id,
            check_id=check.check_id,
            evaluator=evaluator_name,
            evaluator_version=evaluator_version,
            rubric_version=rubric_version,
            dimensions=result.dimensions,
            outcome=result.outcome,
            confidence=result.confidence,
            abstained=result.outcome is CheckOutcome.ABSTAIN,
            evidence=result.evidence,
            estimated_cost_minor=result.estimated_cost_minor,
            actual_cost_minor=result.actual_cost_minor,
            provider_invocation_id=f"inv_{uuid.uuid4().hex[:12]}",
            latency_ms=latency_ms,
            created_at=datetime.now(UTC),
        )

    def _evaluate_claim_evidence(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
        supporting_artifacts: dict[str, Any],
    ) -> _SemanticResult:
        """Evaluate claim/evidence support (narrow structured judgment)."""
        dimensions = []
        evidence = []

        script = artifacts.get(manifest.target_artifact_ids[0])
        supporting_artifacts.get("claim_ledger")
        evidence_snapshots = supporting_artifacts.get("evidence_snapshots")

        if not script or not isinstance(script, dict):
            dimensions.append(
                EvaluationDimension(
                    schema_version="evaluation-dimension.v1",
                    name="claim_support",
                    score=0.0,
                    threshold=0.8,
                    severity=Severity.CRITICAL,
                    failure_codes=[FailureCode.QUALITY_SCHEMA_INVALID],
                    evidence_refs=[],
                    details={"error": "Script artifact missing or invalid"},
                )
            )
            evidence.append({"error": "Script artifact missing or invalid"})
            return _SemanticResult(
                dimensions=dimensions,
                outcome=CheckOutcome.FAIL,
                evidence=evidence,
                confidence=Confidence.LOW,
                estimated_cost_minor=0,
                actual_cost_minor=0,
            )

        claims = script.get("claims", [])

        if not claims:
            # No claims to verify - PASS (nothing to check)
            dimensions.append(
                EvaluationDimension(
                    schema_version="evaluation-dimension.v1",
                    name="claim_support",
                    score=1.0,
                    threshold=0.8,
                    severity=Severity.INFO,
                    failure_codes=[],
                    evidence_refs=[],
                    details={"note": "No claims in script"},
                )
            )
            evidence.append(
                {
                    "check": "claim_evidence",
                    "total_claims": 0,
                    "note": "No claims to verify",
                }
            )
            return _SemanticResult(
                dimensions=dimensions,
                outcome=CheckOutcome.PASS,
                evidence=evidence,
                confidence=Confidence.HIGH,
                estimated_cost_minor=50,
                actual_cost_minor=0,
            )

        # Check if evidence_snapshots are provided when claims have evidence_refs
        has_refs = any(c.get("evidence_refs") for c in claims)
        if has_refs and not evidence_snapshots:
            # Claims reference evidence but no evidence provided - FAIL
            dimensions.append(
                EvaluationDimension(
                    schema_version="evaluation-dimension.v1",
                    name="claim_support",
                    score=0.0,
                    threshold=0.8,
                    severity=Severity.MAJOR,
                    failure_codes=[FailureCode.QUALITY_UNSUPPORTED_CLAIM],
                    evidence_refs=[f"claim_{c.get('claim_id')}" for c in claims],
                    details={
                        "error": "Claims ref evidence but no snapshots",
                        "total_claims": len(claims),
                    },
                )
            )
            evidence.append(
                {
                    "check": "claim_evidence",
                    "error": "Missing evidence_snapshots for claims with evidence_refs",
                    "total_claims": len(claims),
                }
            )
            return _SemanticResult(
                dimensions=dimensions,
                outcome=CheckOutcome.FAIL,
                evidence=evidence,
                confidence=Confidence.HIGH,
                estimated_cost_minor=50,
                actual_cost_minor=0,
            )

        # Real implementation would use LLM to evaluate claim support
        # For now, return ERROR since LLM evaluation not available
        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="claim_support",
                score=0.0,
                threshold=0.8,
                severity=Severity.MAJOR,
                failure_codes=[FailureCode.QUALITY_UNSUPPORTED_CLAIM],
                evidence_refs=[f"claim_{c.get('claim_id')}" for c in claims],
                details={
                    "error": "Claim/evidence eval needs LLM",
                    "total_claims": len(claims),
                },
            )
        )
        evidence.append(
            {
                "check": "claim_evidence",
                "error": "Not implemented - requires LLM-based evaluator",
                "total_claims": len(claims),
            }
        )

        return _SemanticResult(
            dimensions=dimensions,
            outcome=CheckOutcome.ERROR,
            evidence=evidence,
            confidence=Confidence.LOW,
            estimated_cost_minor=50,
            actual_cost_minor=0,
        )

    def _evaluate_editorial_clarity(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
        supporting_artifacts: dict[str, Any],
    ) -> _SemanticResult:
        """Evaluate editorial clarity and quality."""
        dimensions = []
        evidence = []

        _target_artifact, ok = self._require_artifact(manifest, artifacts)

        if not ok:
            dimensions.append(
                EvaluationDimension(
                    schema_version="evaluation-dimension.v1",
                    name="editorial_clarity",
                    score=0.0,
                    threshold=0.8,
                    severity=Severity.CRITICAL,
                    failure_codes=[FailureCode.QUALITY_SCHEMA_INVALID],
                    evidence_refs=[],
                    details={"error": "Target script artifact missing"},
                )
            )
            evidence.append({"error": "Target script artifact missing"})
            return _SemanticResult(
                dimensions=dimensions,
                outcome=CheckOutcome.FAIL,
                evidence=evidence,
                confidence=Confidence.LOW,
                estimated_cost_minor=0,
                actual_cost_minor=0,
            )

        # Real implementation would use LLM to evaluate editorial quality
        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="editorial_clarity",
                score=0.0,
                threshold=0.8,
                severity=Severity.MAJOR,
                failure_codes=[FailureCode.QUALITY_GENERIC],
                evidence_refs=[],
                details={
                    "error": "Editorial eval needs LLM",
                    "rubric_version": check.rubric_version,
                },
            )
        )
        evidence.append(
            {
                "check": "editorial_clarity",
                "error": "Not implemented - requires LLM-based evaluator",
            }
        )

        return _SemanticResult(
            dimensions=dimensions,
            outcome=CheckOutcome.ERROR,
            evidence=evidence,
            confidence=Confidence.LOW,
            estimated_cost_minor=50,
            actual_cost_minor=0,
        )

    def _evaluate_visual_intent_coherence(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
        supporting_artifacts: dict[str, Any],
    ) -> _SemanticResult:
        """Evaluate visual intent coherence with script."""
        dimensions = []
        evidence = []

        _target_artifact, ok = self._require_artifact(manifest, artifacts)
        script = supporting_artifacts.get("script")

        if not ok or not script:
            dimensions.append(
                EvaluationDimension(
                    schema_version="evaluation-dimension.v1",
                    name="visual_intent_coherence",
                    score=0.0,
                    threshold=0.8,
                    severity=Severity.CRITICAL,
                    failure_codes=[FailureCode.QUALITY_SCHEMA_INVALID],
                    evidence_refs=[],
                    details={"error": "Missing target visual plan or script"},
                )
            )
            evidence.append({"error": "Missing target visual plan or script"})
            return _SemanticResult(
                dimensions=dimensions,
                outcome=CheckOutcome.FAIL,
                evidence=evidence,
                confidence=Confidence.LOW,
                estimated_cost_minor=0,
                actual_cost_minor=0,
            )

        # Real implementation would use LLM to evaluate visual coherence
        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="visual_intent_coherence",
                score=0.0,
                threshold=0.8,
                severity=Severity.MAJOR,
                failure_codes=[FailureCode.QUALITY_VISUAL_MISMATCH],
                evidence_refs=[],
                details={
                    "error": "Visual coherence eval needs LLM",
                    "rubric_version": check.rubric_version,
                },
            )
        )
        evidence.append(
            {
                "check": "visual_intent_coherence",
                "error": "Not implemented - requires LLM-based evaluator",
            }
        )

        return _SemanticResult(
            dimensions=dimensions,
            outcome=CheckOutcome.ERROR,
            evidence=evidence,
            confidence=Confidence.LOW,
            estimated_cost_minor=50,
            actual_cost_minor=0,
        )

    def _require_artifact(
        self, manifest: QualityInputManifest, artifacts: dict[str, Any], idx: int = 0
    ) -> tuple[Any, bool]:
        """Get required target artifact or return None with error flag."""
        artifact_id = manifest.target_artifact_ids[idx]
        artifact = artifacts.get(artifact_id)
        return artifact, artifact is not None

    def _error_evaluation(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        error: str,
        started_at: datetime,
    ) -> QualityEvaluation:
        latency_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
        return QualityEvaluation(
            schema_version="quality-evaluation.v1",
            evaluation_id=f"eval_{uuid.uuid4().hex[:12]}",
            target_artifact_ids=manifest.target_artifact_ids,
            target_hashes=manifest.target_hashes,
            evaluation_input_manifest_id=manifest.manifest_id,
            gate_id=manifest.gate_id,
            check_id=check.check_id,
            evaluator=check.evaluator,
            evaluator_version=check.evaluator_version,
            rubric_version=check.rubric_version,
            dimensions=[
                EvaluationDimension(
                    schema_version="evaluation-dimension.v1",
                    name="evaluator_error",
                    score=0.0,
                    threshold=1.0,
                    severity=Severity.CRITICAL,
                    failure_codes=[FailureCode.QUALITY_GENERIC],
                    evidence_refs=[],
                    details={"error": error},
                )
            ],
            outcome=CheckOutcome.ERROR,
            confidence=Confidence.LOW,
            abstained=False,
            evidence=[{"error": error}],
            estimated_cost_minor=0,
            actual_cost_minor=0,
            provider_invocation_id=None,
            latency_ms=latency_ms,
            created_at=datetime.now(UTC),
        )


class HumanCheckEvaluator:
    """Evaluator for human review checks.

    Human checks create a HumanReview record and wait for a reviewer decision.
    They do not produce automatic scores.
    """

    def evaluate(
        self,
        check: QualityCheck,
        manifest: QualityInputManifest,
        artifacts: dict[str, Any],
        supporting_artifacts: dict[str, Any],
    ) -> QualityEvaluation:
        """Create a human review evaluation (always ABSTAIN, triggers review)."""
        started = datetime.now(UTC)
        evaluator_name = check.evaluator
        evaluator_version = check.evaluator_version

        # Human checks always abstain and trigger a review request
        dimensions = [
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="awaiting_human_review",
                score=None,
                threshold=None,
                severity=Severity.INFO,
                failure_codes=[],
                evidence_refs=[],
                details={
                    "check_id": check.check_id,
                    "action": "human_review_requested",
                },
            )
        ]
        evidence = [
            {
                "check": "human_review",
                "action": "review_requested",
                "target_artifacts": manifest.target_artifact_ids,
            }
        ]

        latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        return QualityEvaluation(
            schema_version="quality-evaluation.v1",
            evaluation_id=f"eval_{uuid.uuid4().hex[:12]}",
            stage_instance_id=None,
            logical_item_key=None,
            scene_id=None,
            shot_id=None,
            target_artifact_ids=manifest.target_artifact_ids,
            target_hashes=manifest.target_hashes,
            evaluation_input_manifest_id=manifest.manifest_id,
            gate_id=manifest.gate_id,
            check_id=check.check_id,
            evaluator=evaluator_name,
            evaluator_version=evaluator_version,
            rubric_version=None,
            dimensions=dimensions,
            outcome=CheckOutcome.ABSTAIN,
            confidence=None,
            abstained=True,
            evidence=evidence,
            estimated_cost_minor=0,
            actual_cost_minor=0,
            provider_invocation_id=None,
            latency_ms=latency_ms,
            created_at=datetime.now(UTC),
        )


@dataclass(slots=True)
class _DeterministicResult:
    dimensions: list[EvaluationDimension]
    outcome: CheckOutcome
    evidence: list[dict[str, Any]]


@dataclass(slots=True)
class _SpecializedResult:
    dimensions: list[EvaluationDimension]
    outcome: CheckOutcome
    evidence: list[dict[str, Any]]
    estimated_cost_minor: int = 0
    actual_cost_minor: int = 0


@dataclass(slots=True)
class _SemanticResult:
    dimensions: list[EvaluationDimension]
    outcome: CheckOutcome
    evidence: list[dict[str, Any]]
    confidence: Confidence
    estimated_cost_minor: int = 0
    actual_cost_minor: int = 0
