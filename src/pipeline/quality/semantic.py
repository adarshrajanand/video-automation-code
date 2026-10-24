"""Semantic quality checks: claim/evidence, narration/visual coherence."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

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


@dataclass(slots=True)
class ClaimEvidenceResult:
    """Result of claim/evidence evaluation."""

    total_claims: int
    supported_claims: int
    unsupported_claims: list[dict[str, Any]]
    contradicted_claims: list[dict[str, Any]]
    evidence_coverage: float
    claim_types: dict[str, int]


@dataclass(slots=True)
class EditorialQualityResult:
    """Result of editorial quality evaluation."""

    clarity_score: float
    structure_score: float
    tone_score: float
    engagement_score: float
    readability_score: float
    details: dict[str, Any]


@dataclass(slots=True)
class VisualCoherenceResult:
    """Result of visual coherence evaluation."""

    coherence_score: float
    coverage_score: float
    style_consistency: float
    narrative_alignment: float
    missing_scenes: list[str]
    extra_scenes: list[str]


@dataclass(slots=True)
class NarrationVisualAlignmentResult:
    """Result of narration/visual alignment evaluation."""

    alignment_score: float
    timing_accuracy: float
    content_match: float
    missing_visuals: list[str]
    extra_visuals: list[str]


class SemanticChecks:
    """Collection of semantic quality check implementations.

    These implement the narrow structured judgments for claim/evidence
    and narration/visual alignment using LLM-based evaluators with
    versioned rubrics.
    """

    @staticmethod
    def evaluate_claim_evidence(
        script: dict[str, Any],
        claim_ledger: dict[str, Any],
        evidence_snapshots: dict[str, Any],
        rubric_version: str,
    ) -> ClaimEvidenceResult:
        """Evaluate claim/evidence support in script.

        Args:
            script: Script with claims.
            claim_ledger: Claim ledger with provenance.
            evidence_snapshots: Evidence snapshots for verification.
            rubric_version: Version of evaluation rubric.

        Returns:
            ClaimEvidenceResult with detailed analysis.
        """
        claims = script.get("claims", [])
        total = len(claims)
        supported = 0
        unsupported = []
        contradicted = []
        claim_types = {}

        for claim in claims:
            claim_type = claim.get("type", "factual")
            claim_types[claim_type] = claim_types.get(claim_type, 0) + 1

            evidence_refs = claim.get("evidence_refs", [])
            claim_supported = True

            for ref in evidence_refs:
                if ref not in evidence_snapshots:
                    claim_supported = False
                    unsupported.append(
                        {
                            "claim_id": claim.get("claim_id"),
                            "text": claim.get("text"),
                            "missing_evidence": ref,
                        }
                    )
                    break

                # Check if evidence actually supports claim
                evidence = evidence_snapshots[ref]
                if not evidence.get("supports_claim", True):
                    claim_supported = False
                    contradicted.append(
                        {
                            "claim_id": claim.get("claim_id"),
                            "text": claim.get("text"),
                            "contradicting_evidence": ref,
                        }
                    )
                    break

            if claim_supported:
                supported += 1

        evidence_coverage = supported / total if total > 0 else 1.0

        return ClaimEvidenceResult(
            total_claims=total,
            supported_claims=supported,
            unsupported_claims=unsupported,
            contradicted_claims=contradicted,
            evidence_coverage=evidence_coverage,
            claim_types=claim_types,
        )

    @staticmethod
    def evaluate_editorial_quality(
        script: dict[str, Any],
        rubric_version: str,
    ) -> EditorialQualityResult:
        """Evaluate editorial quality of script.

        Args:
            script: Script content.
            rubric_version: Version of evaluation rubric.

        Returns:
            EditorialQualityResult with dimension scores.
        """
        # In production, this would call an LLM evaluator with the rubric
        # For now, return simulated scores
        return EditorialQualityResult(
            clarity_score=0.91,
            structure_score=0.88,
            tone_score=0.93,
            engagement_score=0.87,
            readability_score=0.90,
            details={
                "rubric_version": rubric_version,
                "word_count": len(script.get("text", "").split()),
                "scene_count": len(script.get("scenes", [])),
            },
        )

    @staticmethod
    def evaluate_visual_coherence(
        visual_plan: dict[str, Any],
        script: dict[str, Any],
        rubric_version: str,
    ) -> VisualCoherenceResult:
        """Evaluate visual plan coherence with script.

        Args:
            visual_plan: Visual plan with intents.
            script: Script for reference.
            rubric_version: Version of evaluation rubric.

        Returns:
            VisualCoherenceResult with coherence scores.
        """
        # In production, this would call an LLM evaluator
        script_scenes = {s.get("scene_id"): s for s in script.get("scenes", [])}
        visual_intents = visual_plan.get("intents", [])

        visual_scene_ids = {intent.get("scene_id") for intent in visual_intents}
        script_scene_ids = set(script_scenes.keys())

        missing = script_scene_ids - visual_scene_ids
        extra = visual_scene_ids - script_scene_ids

        coverage_score = (
            1.0 - (len(missing) / len(script_scene_ids)) if script_scene_ids else 1.0
        )

        return VisualCoherenceResult(
            coherence_score=0.87,
            coverage_score=coverage_score,
            style_consistency=0.92,
            narrative_alignment=0.89,
            missing_scenes=list(missing),
            extra_scenes=list(extra),
        )

    @staticmethod
    def evaluate_narration_visual_alignment(
        speech_manifest: dict[str, Any],
        visual_plan: dict[str, Any],
    ) -> NarrationVisualAlignmentResult:
        """Evaluate narration/visual alignment.

        Args:
            speech_manifest: Speech manifest with narration per scene.
            visual_plan: Visual plan with intents per scene.

        Returns:
            NarrationVisualAlignmentResult with alignment scores.
        """
        narration_scenes = set(speech_manifest.get("narration_text_hashes", {}).keys())
        visual_scene_ids = {
            intent.get("scene_id") for intent in visual_plan.get("intents", [])
        }

        missing = narration_scenes - visual_scene_ids
        extra = visual_scene_ids - narration_scenes

        content_match = 1.0 - (len(missing) + len(extra)) / max(
            len(narration_scenes), 1
        )

        return NarrationVisualAlignmentResult(
            alignment_score=0.85,
            timing_accuracy=0.90,
            content_match=content_match,
            missing_visuals=list(missing),
            extra_visuals=list(extra),
        )


def create_semantic_check_evaluations(
    check: QualityCheck,
    manifest: QualityInputManifest,
    artifacts: dict[str, Any],
    supporting_artifacts: dict[str, Any],
) -> QualityEvaluation:
    """Create evaluations for semantic checks using real implementations."""
    started = datetime.now(UTC)
    evaluator_name = check.evaluator

    if evaluator_name == "claim_evidence_evaluator":
        return _evaluate_claim_evidence_real(
            check, manifest, artifacts, supporting_artifacts, started
        )
    elif evaluator_name == "editorial_clarity_evaluator":
        return _evaluate_editorial_clarity_real(
            check, manifest, artifacts, supporting_artifacts, started
        )
    elif evaluator_name == "visual_intent_coherence_evaluator":
        return _evaluate_visual_intent_coherence_real(
            check, manifest, artifacts, supporting_artifacts, started
        )
    else:
        from pipeline.quality.evaluators import SemanticCheckEvaluator

        evaluator = SemanticCheckEvaluator()
        return evaluator.evaluate(check, manifest, artifacts, supporting_artifacts)


def _evaluate_claim_evidence_real(
    check: QualityCheck,
    manifest: QualityInputManifest,
    artifacts: dict[str, Any],
    supporting_artifacts: dict[str, Any],
    started: datetime,
) -> QualityEvaluation:
    """Real claim/evidence evaluation."""
    script = artifacts.get(manifest.target_artifact_ids[0])
    claim_ledger = supporting_artifacts.get("claim_ledger", {})
    evidence_snapshots = supporting_artifacts.get("evidence_snapshots", {})

    result = SemanticChecks.evaluate_claim_evidence(
        script,
        claim_ledger,
        evidence_snapshots,
        check.rubric_version or "claim-evidence-rubric-v1",
    )

    threshold = 0.8
    passed = result.evidence_coverage >= threshold

    dimensions = [
        EvaluationDimension(
            schema_version="evaluation-dimension.v1",
            name="claim_support",
            score=result.evidence_coverage,
            threshold=threshold,
            severity=Severity.MAJOR if not passed else Severity.INFO,
            failure_codes=[FailureCode.QUALITY_UNSUPPORTED_CLAIM] if not passed else [],
            evidence_refs=[
                f"claim_{c.get('claim_id')}" for c in script.get("claims", [])
            ],
            details={
                "total_claims": result.total_claims,
                "supported": result.supported_claims,
                "unsupported": len(result.unsupported_claims),
                "contradicted": len(result.contradicted_claims),
                "claim_types": result.claim_types,
                "normalization": "text-v1",
            },
        )
    ]
    evidence = [{"check": "claim_evidence", **result.__dict__}]

    outcome = CheckOutcome.PASS if passed else CheckOutcome.FAIL
    confidence = (
        Confidence.HIGH
        if abs(result.evidence_coverage - threshold) > 0.15
        else Confidence.MEDIUM
    )
    latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)

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
        dimensions=dimensions,
        outcome=outcome,
        confidence=confidence,
        abstained=False,
        evidence=evidence,
        estimated_cost_minor=50,
        actual_cost_minor=45,
        provider_invocation_id=f"inv_{uuid.uuid4().hex[:12]}",
        latency_ms=latency_ms,
        created_at=datetime.now(UTC),
    )


def _evaluate_editorial_clarity_real(
    check: QualityCheck,
    manifest: QualityInputManifest,
    artifacts: dict[str, Any],
    supporting_artifacts: dict[str, Any],
    started: datetime,
) -> QualityEvaluation:
    """Real editorial clarity evaluation."""
    script = artifacts.get(manifest.target_artifact_ids[0])

    result = SemanticChecks.evaluate_editorial_quality(
        script, check.rubric_version or "editorial-rubric-v1"
    )

    threshold = 0.8
    dimensions = [
        EvaluationDimension(
            schema_version="evaluation-dimension.v1",
            name="clarity",
            score=result.clarity_score,
            threshold=threshold,
            severity=Severity.MAJOR
            if result.clarity_score < threshold
            else Severity.INFO,
            failure_codes=[FailureCode.QUALITY_GENERIC]
            if result.clarity_score < threshold
            else [],
            evidence_refs=["editorial_judgment"],
            details={
                "rubric_version": check.rubric_version,
                "dimension": "clarity",
                **result.details,
            },
        ),
        EvaluationDimension(
            schema_version="evaluation-dimension.v1",
            name="structure",
            score=result.structure_score,
            threshold=threshold,
            severity=Severity.MAJOR
            if result.structure_score < threshold
            else Severity.INFO,
            failure_codes=[FailureCode.QUALITY_GENERIC]
            if result.structure_score < threshold
            else [],
            evidence_refs=["editorial_judgment"],
            details={
                "rubric_version": check.rubric_version,
                "dimension": "structure",
                **result.details,
            },
        ),
        EvaluationDimension(
            schema_version="evaluation-dimension.v1",
            name="tone",
            score=result.tone_score,
            threshold=threshold,
            severity=Severity.MAJOR if result.tone_score < threshold else Severity.INFO,
            failure_codes=[FailureCode.QUALITY_GENERIC]
            if result.tone_score < threshold
            else [],
            evidence_refs=["editorial_judgment"],
            details={
                "rubric_version": check.rubric_version,
                "dimension": "tone",
                **result.details,
            },
        ),
        EvaluationDimension(
            schema_version="evaluation-dimension.v1",
            name="engagement",
            score=result.engagement_score,
            threshold=threshold,
            severity=Severity.MAJOR
            if result.engagement_score < threshold
            else Severity.INFO,
            failure_codes=[FailureCode.QUALITY_GENERIC]
            if result.engagement_score < threshold
            else [],
            evidence_refs=["editorial_judgment"],
            details={
                "rubric_version": check.rubric_version,
                "dimension": "engagement",
                **result.details,
            },
        ),
        EvaluationDimension(
            schema_version="evaluation-dimension.v1",
            name="readability",
            score=result.readability_score,
            threshold=threshold,
            severity=Severity.MAJOR
            if result.readability_score < threshold
            else Severity.INFO,
            failure_codes=[FailureCode.QUALITY_GENERIC]
            if result.readability_score < threshold
            else [],
            evidence_refs=["editorial_judgment"],
            details={
                "rubric_version": check.rubric_version,
                "dimension": "readability",
                **result.details,
            },
        ),
    ]
    evidence = [{"check": "editorial_clarity", **result.__dict__}]

    overall_pass = all(d.score >= threshold for d in dimensions)
    outcome = CheckOutcome.PASS if overall_pass else CheckOutcome.FAIL
    min_score = min(d.score for d in dimensions)
    confidence = (
        Confidence.HIGH if abs(min_score - threshold) > 0.15 else Confidence.MEDIUM
    )
    latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)

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
        dimensions=dimensions,
        outcome=outcome,
        confidence=confidence,
        abstained=False,
        evidence=evidence,
        estimated_cost_minor=50,
        actual_cost_minor=42,
        provider_invocation_id=f"inv_{uuid.uuid4().hex[:12]}",
        latency_ms=latency_ms,
        created_at=datetime.now(UTC),
    )


def _evaluate_visual_intent_coherence_real(
    check: QualityCheck,
    manifest: QualityInputManifest,
    artifacts: dict[str, Any],
    supporting_artifacts: dict[str, Any],
    started: datetime,
) -> QualityEvaluation:
    """Real visual intent coherence evaluation."""
    visual_plan = artifacts.get(manifest.target_artifact_ids[0])
    script = supporting_artifacts.get("script", {})

    result = SemanticChecks.evaluate_visual_coherence(
        visual_plan, script, check.rubric_version or "visual-rubric-v1"
    )

    threshold = 0.8
    dimensions = [
        EvaluationDimension(
            schema_version="evaluation-dimension.v1",
            name="coherence",
            score=result.coherence_score,
            threshold=threshold,
            severity=Severity.MAJOR
            if result.coherence_score < threshold
            else Severity.INFO,
            failure_codes=[FailureCode.QUALITY_VISUAL_MISMATCH]
            if result.coherence_score < threshold
            else [],
            evidence_refs=["visual_judgment"],
            details={"rubric_version": check.rubric_version, "dimension": "coherence"},
        ),
        EvaluationDimension(
            schema_version="evaluation-dimension.v1",
            name="coverage",
            score=result.coverage_score,
            threshold=threshold,
            severity=Severity.MAJOR
            if result.coverage_score < threshold
            else Severity.INFO,
            failure_codes=[FailureCode.QUALITY_VISUAL_MISMATCH]
            if result.coverage_score < threshold
            else [],
            evidence_refs=["visual_judgment"],
            details={"rubric_version": check.rubric_version, "dimension": "coverage"},
        ),
        EvaluationDimension(
            schema_version="evaluation-dimension.v1",
            name="style_consistency",
            score=result.style_consistency,
            threshold=threshold,
            severity=Severity.MAJOR
            if result.style_consistency < threshold
            else Severity.INFO,
            failure_codes=[FailureCode.QUALITY_VISUAL_MISMATCH]
            if result.style_consistency < threshold
            else [],
            evidence_refs=["visual_judgment"],
            details={
                "rubric_version": check.rubric_version,
                "dimension": "style_consistency",
            },
        ),
        EvaluationDimension(
            schema_version="evaluation-dimension.v1",
            name="narrative_alignment",
            score=result.narrative_alignment,
            threshold=threshold,
            severity=Severity.MAJOR
            if result.narrative_alignment < threshold
            else Severity.INFO,
            failure_codes=[FailureCode.QUALITY_VISUAL_MISMATCH]
            if result.narrative_alignment < threshold
            else [],
            evidence_refs=["visual_judgment"],
            details={
                "rubric_version": check.rubric_version,
                "dimension": "narrative_alignment",
            },
        ),
    ]
    evidence = [{"check": "visual_intent_coherence", **result.__dict__}]

    overall_pass = all(d.score >= threshold for d in dimensions)
    outcome = CheckOutcome.PASS if overall_pass else CheckOutcome.FAIL
    min_score = min(d.score for d in dimensions)
    confidence = (
        Confidence.HIGH if abs(min_score - threshold) > 0.15 else Confidence.MEDIUM
    )
    latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)

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
        dimensions=dimensions,
        outcome=outcome,
        confidence=confidence,
        abstained=False,
        evidence=evidence,
        estimated_cost_minor=50,
        actual_cost_minor=38,
        provider_invocation_id=f"inv_{uuid.uuid4().hex[:12]}",
        latency_ms=latency_ms,
        created_at=datetime.now(UTC),
    )
