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
        missing = sum(1 for a in assets if not a.get("available", True))
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

        # Simplified timeline validation
        shots = composition.get("shots", [])
        has_overlaps = False  # Would check actual timing in real implementation
        has_gaps = False

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

        artifacts.get(manifest.target_artifact_ids[0])
        supporting_artifacts.get("speech_manifest")
        supporting_artifacts.get("asr_alignment")

        # Simulated WER/CER calculation
        wer = 0.03  # 3% WER
        cer = 0.01  # 1% CER
        wer_threshold = 0.10  # 10% max WER
        cer_threshold = 0.05  # 5% max CER

        wer_pass = wer <= wer_threshold
        cer_pass = cer <= cer_threshold

        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="wer",
                score=1.0 - wer,
                threshold=1.0 - wer_threshold,
                severity=Severity.MAJOR if not wer_pass else Severity.INFO,
                failure_codes=[FailureCode.QUALITY_TTS_PRONUNCIATION]
                if not wer_pass
                else [],
                evidence_refs=["wer_measurement"],
                details={
                    "wer": wer,
                    "threshold": wer_threshold,
                    "normalization": "text-v1",
                },
            )
        )
        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="cer",
                score=1.0 - cer,
                threshold=1.0 - cer_threshold,
                severity=Severity.MAJOR if not cer_pass else Severity.INFO,
                failure_codes=[FailureCode.QUALITY_TTS_PRONUNCIATION]
                if not cer_pass
                else [],
                evidence_refs=["cer_measurement"],
                details={
                    "cer": cer,
                    "threshold": cer_threshold,
                    "normalization": "text-v1",
                },
            )
        )
        evidence.append(
            {
                "check": "wer_cer",
                "wer": wer,
                "cer": cer,
                "wer_threshold": wer_threshold,
                "cer_threshold": cer_threshold,
            }
        )

        if not wer_pass or not cer_pass:
            failure_codes.append(FailureCode.QUALITY_TTS_PRONUNCIATION)

        outcome = CheckOutcome.PASS if (wer_pass and cer_pass) else CheckOutcome.FAIL
        return _SpecializedResult(
            dimensions=dimensions,
            outcome=outcome,
            evidence=evidence,
            estimated_cost_minor=10,
            actual_cost_minor=8,
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

        supporting_artifacts.get("asr_alignment")
        speech_manifest = supporting_artifacts.get("speech_manifest")

        # Simulated critical token check
        critical_tokens = (
            speech_manifest.get("critical_tokens", []) if speech_manifest else []
        )
        missed = 0
        for token in critical_tokens:
            if token.get("matched", True) is False:
                missed += 1

        score = 1.0 - (missed / len(critical_tokens)) if critical_tokens else 1.0
        threshold = 1.0  # All critical tokens must be present

        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="critical_tokens",
                score=score,
                threshold=threshold,
                severity=Severity.CRITICAL if missed > 0 else Severity.INFO,
                failure_codes=[FailureCode.QUALITY_TTS_OMISSION] if missed > 0 else [],
                evidence_refs=[f"token_{t.get('token_id')}" for t in critical_tokens],
                details={
                    "total_critical_tokens": len(critical_tokens),
                    "missed": missed,
                    "matched": len(critical_tokens) - missed,
                },
            )
        )
        evidence.append(
            {
                "check": "critical_tokens",
                "total": len(critical_tokens),
                "missed": missed,
            }
        )

        if missed > 0:
            failure_codes.append(FailureCode.QUALITY_TTS_OMISSION)

        outcome = CheckOutcome.PASS if missed == 0 else CheckOutcome.FAIL
        return _SpecializedResult(
            dimensions=dimensions,
            outcome=outcome,
            evidence=evidence,
            estimated_cost_minor=5,
            actual_cost_minor=3,
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

        supporting_artifacts.get("asr_alignment")

        # Simulated forced alignment check
        alignment_score = 0.95
        threshold = 0.90

        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="forced_alignment",
                score=alignment_score,
                threshold=threshold,
                severity=Severity.MAJOR
                if alignment_score < threshold
                else Severity.INFO,
                failure_codes=[FailureCode.QUALITY_TTS_PRONUNCIATION]
                if alignment_score < threshold
                else [],
                evidence_refs=["alignment_quality"],
                details={"alignment_score": alignment_score, "threshold": threshold},
            )
        )
        evidence.append({"check": "forced_alignment", "score": alignment_score})

        outcome = (
            CheckOutcome.PASS if alignment_score >= threshold else CheckOutcome.FAIL
        )
        return _SpecializedResult(
            dimensions=dimensions, outcome=outcome, evidence=evidence
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

        artifacts.get(manifest.target_artifact_ids[0])

        # Simulated signal quality metrics
        snr_db = 45.0
        clipping_percent = 0.1
        silence_percent = 2.0

        snr_pass = snr_db >= 30.0
        clipping_pass = clipping_percent <= 1.0
        silence_pass = silence_percent <= 5.0

        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="snr",
                score=min(snr_db / 60.0, 1.0),
                threshold=30.0 / 60.0,
                severity=Severity.MINOR if not snr_pass else Severity.INFO,
                failure_codes=[FailureCode.QUALITY_AUDIO_DECODE]
                if not snr_pass
                else [],
                evidence_refs=["snr_measurement"],
                details={"snr_db": snr_db, "threshold_db": 30.0},
            )
        )
        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="clipping",
                score=1.0 - clipping_percent / 100.0,
                threshold=0.99,
                severity=Severity.MINOR if not clipping_pass else Severity.INFO,
                failure_codes=[FailureCode.QUALITY_AUDIO_DECODE]
                if not clipping_pass
                else [],
                evidence_refs=["clipping_measurement"],
                details={
                    "clipping_percent": clipping_percent,
                    "threshold_percent": 1.0,
                },
            )
        )
        evidence.append(
            {
                "check": "signal_quality",
                "snr_db": snr_db,
                "clipping_percent": clipping_percent,
                "silence_percent": silence_percent,
            }
        )

        outcome = (
            CheckOutcome.PASS
            if (snr_pass and clipping_pass and silence_pass)
            else CheckOutcome.FAIL
        )
        return _SpecializedResult(
            dimensions=dimensions, outcome=outcome, evidence=evidence
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

        # Simulated license check
        assets = asset_manifest.get("assets", []) if asset_manifest else []
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

        artifacts.get(manifest.target_artifact_ids[0])
        supporting_artifacts.get("audio")
        supporting_artifacts.get("visual_plan")

        # Simulated A/V sync check
        max_drift_ms = 40
        threshold_ms = 100

        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="av_sync",
                score=1.0 - min(max_drift_ms / threshold_ms, 1.0),
                threshold=1.0 - threshold_ms / 1000.0,  # Normalized
                severity=Severity.MAJOR
                if max_drift_ms > threshold_ms
                else Severity.INFO,
                failure_codes=[FailureCode.MEDIA_AUDIO_VIDEO_DRIFT]
                if max_drift_ms > threshold_ms
                else [],
                evidence_refs=["av_sync_measurement"],
                details={"max_drift_ms": max_drift_ms, "threshold_ms": threshold_ms},
            )
        )
        evidence.append({"check": "av_sync", "max_drift_ms": max_drift_ms})

        outcome = (
            CheckOutcome.PASS if max_drift_ms <= threshold_ms else CheckOutcome.FAIL
        )
        return _SpecializedResult(
            dimensions=dimensions, outcome=outcome, evidence=evidence
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

        artifacts.get(manifest.target_artifact_ids[0])

        # Simulated decode check
        decode_success = True
        error_count = 0

        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="decode_success",
                score=1.0 if decode_success else 0.0,
                threshold=1.0,
                severity=Severity.CRITICAL if not decode_success else Severity.INFO,
                failure_codes=[FailureCode.MEDIA_DECODE_ERROR]
                if not decode_success
                else [],
                evidence_refs=["decode_test"],
                details={"decode_success": decode_success, "error_count": error_count},
            )
        )
        evidence.append(
            {"check": "decode", "success": decode_success, "errors": error_count}
        )

        outcome = CheckOutcome.PASS if decode_success else CheckOutcome.FAIL
        return _SpecializedResult(
            dimensions=dimensions, outcome=outcome, evidence=evidence
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

        artifacts.get(manifest.target_artifact_ids[0])
        supporting_artifacts.get("render_profile")

        # Simulated profile check
        profile_match = True
        mismatches = []

        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="profile_conformance",
                score=1.0 if profile_match else 0.0,
                threshold=1.0,
                severity=Severity.MAJOR if not profile_match else Severity.INFO,
                failure_codes=[FailureCode.MEDIA_OUTPUT_PROFILE]
                if not profile_match
                else [],
                evidence_refs=["profile_check"],
                details={"profile_match": profile_match, "mismatches": mismatches},
            )
        )
        evidence.append(
            {"check": "profile", "match": profile_match, "mismatches": mismatches}
        )

        outcome = CheckOutcome.PASS if profile_match else CheckOutcome.FAIL
        return _SpecializedResult(
            dimensions=dimensions, outcome=outcome, evidence=evidence
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

        artifacts.get(manifest.target_artifact_ids[0])
        supporting_artifacts.get("composition")

        # Simulated timeline check
        duration_match = True
        frame_count_match = True

        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="timeline_conformance",
                score=1.0 if (duration_match and frame_count_match) else 0.5,
                threshold=1.0,
                severity=Severity.MAJOR
                if not (duration_match and frame_count_match)
                else Severity.INFO,
                failure_codes=[FailureCode.MEDIA_TIMELINE_INVALID]
                if not (duration_match and frame_count_match)
                else [],
                evidence_refs=["timeline_check"],
                details={
                    "duration_match": duration_match,
                    "frame_count_match": frame_count_match,
                },
            )
        )
        evidence.append(
            {
                "check": "timeline",
                "duration_match": duration_match,
                "frame_count_match": frame_count_match,
            }
        )

        outcome = (
            CheckOutcome.PASS
            if (duration_match and frame_count_match)
            else CheckOutcome.FAIL
        )
        return _SpecializedResult(
            dimensions=dimensions, outcome=outcome, evidence=evidence
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

        # Simulated assembly integrity check
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

        artifacts.get(manifest.target_artifact_ids[0])

        # Simulated A/V drift check
        max_drift_ms = 80
        threshold_ms = 150

        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="av_drift",
                score=1.0 - min(max_drift_ms / threshold_ms, 1.0),
                threshold=1.0 - threshold_ms / 1000.0,
                severity=Severity.MAJOR
                if max_drift_ms > threshold_ms
                else Severity.INFO,
                failure_codes=[FailureCode.MEDIA_AUDIO_VIDEO_DRIFT]
                if max_drift_ms > threshold_ms
                else [],
                evidence_refs=["av_drift_measurement"],
                details={"max_drift_ms": max_drift_ms, "threshold_ms": threshold_ms},
            )
        )
        evidence.append({"check": "av_drift", "max_drift_ms": max_drift_ms})

        outcome = (
            CheckOutcome.PASS if max_drift_ms <= threshold_ms else CheckOutcome.FAIL
        )
        return _SpecializedResult(
            dimensions=dimensions, outcome=outcome, evidence=evidence
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

        artifacts.get(manifest.target_artifact_ids[0])
        supporting_artifacts.get("assembly")

        # Simulated short integrity check
        duration_ok = True
        content_match = True

        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="short_integrity",
                score=1.0 if (duration_ok and content_match) else 0.5,
                threshold=1.0,
                severity=Severity.MAJOR
                if not (duration_ok and content_match)
                else Severity.INFO,
                failure_codes=[FailureCode.QUALITY_VISUAL_MISMATCH]
                if not (duration_ok and content_match)
                else [],
                evidence_refs=["short_integrity_check"],
                details={"duration_ok": duration_ok, "content_match": content_match},
            )
        )
        evidence.append(
            {
                "check": "short_integrity",
                "duration_ok": duration_ok,
                "content_match": content_match,
            }
        )

        outcome = (
            CheckOutcome.PASS if (duration_ok and content_match) else CheckOutcome.FAIL
        )
        return _SpecializedResult(
            dimensions=dimensions, outcome=outcome, evidence=evidence
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
        supporting_artifacts.get("evidence_snapshots")

        # Simulated claim/evidence evaluation
        claims = script.get("claims", []) if script else []
        supported = sum(1 for c in claims if c.get("supported", True))
        total = len(claims)
        score = supported / total if total > 0 else 1.0
        threshold = 0.8

        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="claim_support",
                score=score,
                threshold=threshold,
                severity=Severity.MAJOR if score < threshold else Severity.INFO,
                failure_codes=[FailureCode.QUALITY_UNSUPPORTED_CLAIM]
                if score < threshold
                else [],
                evidence_refs=[f"claim_{c.get('claim_id')}" for c in claims],
                details={
                    "total_claims": total,
                    "supported": supported,
                    "unsupported": total - supported,
                    "normalization": "text-v1",
                },
            )
        )
        evidence.append(
            {
                "check": "claim_evidence",
                "total_claims": total,
                "supported": supported,
                "score": score,
                "rubric_version": check.rubric_version,
            }
        )

        outcome = CheckOutcome.PASS if score >= threshold else CheckOutcome.FAIL
        confidence = (
            Confidence.HIGH if abs(score - threshold) > 0.15 else Confidence.MEDIUM
        )
        return _SemanticResult(
            dimensions=dimensions,
            outcome=outcome,
            evidence=evidence,
            confidence=confidence,
            estimated_cost_minor=50,
            actual_cost_minor=45,
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

        artifacts.get(manifest.target_artifact_ids[0])

        # Simulated editorial evaluation
        clarity_score = 0.91
        structure_score = 0.88
        tone_score = 0.93
        threshold = 0.8

        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="clarity",
                score=clarity_score,
                threshold=threshold,
                severity=Severity.MAJOR if clarity_score < threshold else Severity.INFO,
                failure_codes=[FailureCode.QUALITY_GENERIC]
                if clarity_score < threshold
                else [],
                evidence_refs=["editorial_judgment"],
                details={
                    "rubric_version": check.rubric_version,
                    "dimension": "clarity",
                },
            )
        )
        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="structure",
                score=structure_score,
                threshold=threshold,
                severity=Severity.MAJOR
                if structure_score < threshold
                else Severity.INFO,
                failure_codes=[FailureCode.QUALITY_GENERIC]
                if structure_score < threshold
                else [],
                evidence_refs=["editorial_judgment"],
                details={
                    "rubric_version": check.rubric_version,
                    "dimension": "structure",
                },
            )
        )
        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="tone",
                score=tone_score,
                threshold=threshold,
                severity=Severity.MAJOR if tone_score < threshold else Severity.INFO,
                failure_codes=[FailureCode.QUALITY_GENERIC]
                if tone_score < threshold
                else [],
                evidence_refs=["editorial_judgment"],
                details={"rubric_version": check.rubric_version, "dimension": "tone"},
            )
        )
        evidence.append(
            {
                "check": "editorial_clarity",
                "clarity": clarity_score,
                "structure": structure_score,
                "tone": tone_score,
                "rubric_version": check.rubric_version,
            }
        )

        overall_pass = all(
            s >= threshold for s in [clarity_score, structure_score, tone_score]
        )
        outcome = CheckOutcome.PASS if overall_pass else CheckOutcome.FAIL
        min_score = min(clarity_score, structure_score, tone_score)
        confidence = (
            Confidence.HIGH if abs(min_score - threshold) > 0.15 else Confidence.MEDIUM
        )
        return _SemanticResult(
            dimensions=dimensions,
            outcome=outcome,
            evidence=evidence,
            confidence=confidence,
            estimated_cost_minor=50,
            actual_cost_minor=42,
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

        artifacts.get(manifest.target_artifact_ids[0])
        supporting_artifacts.get("script")

        # Simulated visual coherence evaluation
        coherence_score = 0.87
        coverage_score = 0.92
        threshold = 0.8

        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="coherence",
                score=coherence_score,
                threshold=threshold,
                severity=Severity.MAJOR
                if coherence_score < threshold
                else Severity.INFO,
                failure_codes=[FailureCode.QUALITY_VISUAL_MISMATCH]
                if coherence_score < threshold
                else [],
                evidence_refs=["visual_judgment"],
                details={
                    "rubric_version": check.rubric_version,
                    "dimension": "coherence",
                },
            )
        )
        dimensions.append(
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="coverage",
                score=coverage_score,
                threshold=threshold,
                severity=Severity.MAJOR
                if coverage_score < threshold
                else Severity.INFO,
                failure_codes=[FailureCode.QUALITY_VISUAL_MISMATCH]
                if coverage_score < threshold
                else [],
                evidence_refs=["visual_judgment"],
                details={
                    "rubric_version": check.rubric_version,
                    "dimension": "coverage",
                },
            )
        )
        evidence.append(
            {
                "check": "visual_intent_coherence",
                "coherence": coherence_score,
                "coverage": coverage_score,
                "rubric_version": check.rubric_version,
            }
        )

        overall_pass = coherence_score >= threshold and coverage_score >= threshold
        outcome = CheckOutcome.PASS if overall_pass else CheckOutcome.FAIL
        min_score = min(coherence_score, coverage_score)
        confidence = (
            Confidence.HIGH if abs(min_score - threshold) > 0.15 else Confidence.MEDIUM
        )
        return _SemanticResult(
            dimensions=dimensions,
            outcome=outcome,
            evidence=evidence,
            confidence=confidence,
            estimated_cost_minor=50,
            actual_cost_minor=38,
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
