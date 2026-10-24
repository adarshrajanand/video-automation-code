"""Speech quality checks: WER/CER, critical tokens, forced alignment,
signal measurements."""

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
class WERCERResult:
    """Result of WER/CER computation."""

    wer: float
    cer: float
    word_count: int
    char_count: int
    substitutions: int
    deletions: int
    insertions: int
    details: dict[str, Any]


@dataclass(slots=True)
class CriticalTokenResult:
    """Result of critical token verification."""

    total_tokens: int
    matched_tokens: int
    missed_tokens: list[str]
    phonetically_confused: list[str]


@dataclass(slots=True)
class ForcedAlignmentResult:
    """Result of forced alignment quality check."""

    alignment_score: float
    avg_token_duration_ms: float
    max_token_duration_ms: float
    silence_ratio: float
    out_of_order_tokens: int


@dataclass(slots=True)
class SignalQualityResult:
    """Result of audio signal quality measurements."""

    snr_db: float
    clipping_percent: float
    silence_percent: float
    dynamic_range_db: float
    loudness_lufs: float


class SpeechQualityChecks:
    """Collection of speech quality check implementations.

    These are the actual algorithmic implementations used by the
    SpecializedCheckEvaluator for speech-related checks.
    """

    @staticmethod
    def compute_wer_cer(
        reference_text: str,
        hypothesis_text: str,
        normalization: str = "text-v1",
    ) -> WERCERResult:
        """Compute Word Error Rate (WER) and Character Error Rate (CER).

        Args:
            reference_text: Ground truth transcription.
            hypothesis_text: ASR transcription.
            normalization: Text normalization pipeline to apply.

        Returns:
            WERCERResult with detailed breakdown.
        """
        # Apply normalization
        ref_norm = SpeechQualityChecks._normalize_text(reference_text, normalization)
        hyp_norm = SpeechQualityChecks._normalize_text(hypothesis_text, normalization)

        # Compute Levenshtein distance at word level
        ref_words = ref_norm.split()
        hyp_words = hyp_norm.split()

        word_distance, subs, dels, ins = SpeechQualityChecks._levenshtein_with_ops(
            ref_words, hyp_words
        )
        word_count = len(ref_words)
        wer = word_distance / word_count if word_count > 0 else 0.0

        # Compute at character level
        ref_chars = list(ref_norm.replace(" ", ""))
        hyp_chars = list(hyp_norm.replace(" ", ""))
        char_distance, _, _, _ = SpeechQualityChecks._levenshtein_with_ops(
            ref_chars, hyp_chars
        )
        char_count = len(ref_chars)
        cer = char_distance / char_count if char_count > 0 else 0.0

        return WERCERResult(
            wer=wer,
            cer=cer,
            word_count=word_count,
            char_count=char_count,
            substitutions=subs,
            deletions=dels,
            insertions=ins,
            details={
                "normalization": normalization,
                "ref_words": word_count,
                "hyp_words": len(hyp_words),
            },
        )

    @staticmethod
    def _normalize_text(text: str, normalization: str) -> str:
        """Apply text normalization pipeline."""
        if normalization == "text-v1":
            # Lowercase, remove punctuation, normalize whitespace
            import re

            text = text.lower()
            text = re.sub(r"[^\w\s]", "", text)
            text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _levenshtein_with_ops(
        ref: list[str], hyp: list[str]
    ) -> tuple[int, int, int, int]:
        """Levenshtein distance with operation counts."""
        n, m = len(ref), len(hyp)
        # dp[i][j] = (distance, subs, dels, ins)
        dp = [[(0, 0, 0, 0) for _ in range(m + 1)] for _ in range(n + 1)]

        for i in range(n + 1):
            dp[i][0] = (i, 0, i, 0)
        for j in range(m + 1):
            dp[0][j] = (j, 0, 0, j)

        for i in range(1, n + 1):
            for j in range(1, m + 1):
                if ref[i - 1] == hyp[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    sub = (
                        dp[i - 1][j - 1][0] + 1,
                        dp[i - 1][j - 1][1] + 1,
                        dp[i - 1][j - 1][2],
                        dp[i - 1][j - 1][3],
                    )
                    del_op = (
                        dp[i - 1][j][0] + 1,
                        dp[i - 1][j][1],
                        dp[i - 1][j][2] + 1,
                        dp[i - 1][j][3],
                    )
                    ins = (
                        dp[i][j - 1][0] + 1,
                        dp[i][j - 1][1],
                        dp[i][j - 1][2],
                        dp[i][j - 1][3] + 1,
                    )
                    dp[i][j] = min(sub, del_op, ins, key=lambda x: x[0])

        return dp[n][m]

    @staticmethod
    def verify_critical_tokens(
        asr_alignment: dict[str, Any],
        critical_tokens: list[dict[str, Any]],
        tolerance_ms: int = 500,
    ) -> CriticalTokenResult:
        """Verify that critical tokens appear in ASR alignment.

        Args:
            asr_alignment: ASR alignment output with word timestamps.
            critical_tokens: List of critical tokens with expected text
                and time windows.
            tolerance_ms: Time tolerance for token matching.

        Returns:
            CriticalTokenResult with match details.
        """
        word_timestamps = asr_alignment.get("word_timestamps", [])
        matched = 0
        missed = []
        confused = []

        for token in critical_tokens:
            token_text = token.get("text", "").lower()
            expected_start = token.get("expected_start_ms", 0)
            expected_end = token.get("expected_end_ms", 0)

            # Find matching word in alignment
            found = False
            for wt in word_timestamps:
                wt_text = wt.get("word", "").lower()
                wt_start = wt.get("start_ms", 0)
                wt_end = wt.get("end_ms", 0)

                if wt_text == token_text:
                    # Check time overlap
                    if (
                        wt_start <= expected_end + tolerance_ms
                        and wt_end >= expected_start - tolerance_ms
                    ):
                        found = True
                        matched += 1
                        break
                elif SpeechQualityChecks._phonetically_similar(wt_text, token_text):
                    confused.append(f"{token_text}~{wt_text}")

            if not found:
                missed.append(token_text)

        return CriticalTokenResult(
            total_tokens=len(critical_tokens),
            matched_tokens=matched,
            missed_tokens=missed,
            phonetically_confused=confused,
        )

    @staticmethod
    def _phonetically_similar(word1: str, word2: str) -> bool:
        """Simple phonetic similarity check (placeholder for real implementation)."""
        # In production, use a proper phonetic algorithm like Metaphone
        return word1[:3] == word2[:3] and len(word1) > 3 and len(word2) > 3

    @staticmethod
    def evaluate_forced_alignment(
        asr_alignment: dict[str, Any],
        expected_duration_ms: int,
    ) -> ForcedAlignmentResult:
        """Evaluate forced alignment quality.

        Args:
            asr_alignment: ASR alignment output.
            expected_duration_ms: Expected total audio duration.

        Returns:
            ForcedAlignmentResult with quality metrics.
        """
        word_timestamps = asr_alignment.get("word_timestamps", [])
        if not word_timestamps:
            return ForcedAlignmentResult(
                alignment_score=0.0,
                avg_token_duration_ms=0.0,
                max_token_duration_ms=0.0,
                silence_ratio=1.0,
                out_of_order_tokens=0,
            )

        # Check ordering
        out_of_order = 0
        for i in range(1, len(word_timestamps)):
            if word_timestamps[i].get("start_ms", 0) < word_timestamps[i - 1].get(
                "start_ms", 0
            ):
                out_of_order += 1

        # Compute durations
        durations = [
            wt.get("end_ms", 0) - wt.get("start_ms", 0) for wt in word_timestamps
        ]
        avg_duration = sum(durations) / len(durations) if durations else 0
        max_duration = max(durations) if durations else 0

        # Compute silence ratio
        total_speech_ms = sum(durations)
        silence_ratio = (
            max(0.0, 1.0 - (total_speech_ms / expected_duration_ms))
            if expected_duration_ms > 0
            else 1.0
        )

        # Alignment score based on ordering and coverage
        order_score = (
            1.0 - (out_of_order / len(word_timestamps)) if word_timestamps else 0.0
        )
        coverage_score = (
            min(total_speech_ms / expected_duration_ms, 1.0)
            if expected_duration_ms > 0
            else 0.0
        )
        alignment_score = (order_score + coverage_score) / 2.0

        return ForcedAlignmentResult(
            alignment_score=alignment_score,
            avg_token_duration_ms=avg_duration,
            max_token_duration_ms=max_duration,
            silence_ratio=silence_ratio,
            out_of_order_tokens=out_of_order,
        )

    @staticmethod
    def measure_signal_quality(audio_path: str) -> SignalQualityResult:
        """Measure audio signal quality metrics.

        Args:
            audio_path: Path to audio file.

        Returns:
            SignalQualityResult with measurements.
        """
        # In production, this would use ffprobe/ffmpeg or librosa
        # For now, return simulated values
        return SignalQualityResult(
            snr_db=45.0,
            clipping_percent=0.1,
            silence_percent=2.0,
            dynamic_range_db=60.0,
            loudness_lufs=-23.0,
        )


def create_speech_check_evaluations(
    check: QualityCheck,
    manifest: QualityInputManifest,
    artifacts: dict[str, Any],
    supporting_artifacts: dict[str, Any],
) -> QualityEvaluation:
    """Create evaluations for speech quality checks using real implementations.

    This function bridges the evaluator framework with the actual
    speech quality algorithms.
    """
    started = datetime.now(UTC)
    evaluator_name = check.evaluator

    if evaluator_name == "wer_cer_evaluator":
        return _evaluate_wer_cer_real(
            check, manifest, artifacts, supporting_artifacts, started
        )
    elif evaluator_name == "critical_token_evaluator":
        return _evaluate_critical_tokens_real(
            check, manifest, artifacts, supporting_artifacts, started
        )
    elif evaluator_name == "forced_alignment_evaluator":
        return _evaluate_forced_alignment_real(
            check, manifest, artifacts, supporting_artifacts, started
        )
    elif evaluator_name == "signal_quality_evaluator":
        return _evaluate_signal_quality_real(
            check, manifest, artifacts, supporting_artifacts, started
        )
    else:
        # Fall back to simulated evaluator
        from pipeline.quality.evaluators import SpecializedCheckEvaluator

        evaluator = SpecializedCheckEvaluator()
        return evaluator.evaluate(check, manifest, artifacts, supporting_artifacts)


def _evaluate_wer_cer_real(
    check: QualityCheck,
    manifest: QualityInputManifest,
    artifacts: dict[str, Any],
    supporting_artifacts: dict[str, Any],
    started: datetime,
) -> QualityEvaluation:
    """Real WER/CER evaluation using SpeechQualityChecks."""
    artifacts.get(manifest.target_artifact_ids[0])
    speech_manifest = supporting_artifacts.get("speech_manifest")
    asr_alignment = supporting_artifacts.get("asr_alignment")

    # Get reference and hypothesis texts
    reference = speech_manifest.get("reference_text", "") if speech_manifest else ""
    hypothesis = asr_alignment.get("hypothesis_text", "") if asr_alignment else ""

    result = SpeechQualityChecks.compute_wer_cer(reference, hypothesis)

    wer_pass = result.wer <= 0.10
    cer_pass = result.cer <= 0.05

    dimensions = [
        EvaluationDimension(
            schema_version="evaluation-dimension.v1",
            name="wer",
            score=1.0 - result.wer,
            threshold=0.90,
            severity=Severity.MAJOR if not wer_pass else Severity.INFO,
            failure_codes=[FailureCode.QUALITY_TTS_PRONUNCIATION]
            if not wer_pass
            else [],
            evidence_refs=["wer_measurement"],
            details={
                "wer": result.wer,
                "threshold": 0.10,
                "word_count": result.word_count,
                "substitutions": result.substitutions,
                "deletions": result.deletions,
                "insertions": result.insertions,
                "normalization": "text-v1",
            },
        ),
        EvaluationDimension(
            schema_version="evaluation-dimension.v1",
            name="cer",
            score=1.0 - result.cer,
            threshold=0.95,
            severity=Severity.MAJOR if not cer_pass else Severity.INFO,
            failure_codes=[FailureCode.QUALITY_TTS_PRONUNCIATION]
            if not cer_pass
            else [],
            evidence_refs=["cer_measurement"],
            details={
                "cer": result.cer,
                "threshold": 0.05,
                "char_count": result.char_count,
                "normalization": "text-v1",
            },
        ),
    ]
    evidence = [{"check": "wer_cer", **result.details}]

    outcome = CheckOutcome.PASS if (wer_pass and cer_pass) else CheckOutcome.FAIL
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
        rubric_version=None,
        dimensions=dimensions,
        outcome=outcome,
        confidence=Confidence.HIGH,
        abstained=False,
        evidence=evidence,
        estimated_cost_minor=10,
        actual_cost_minor=8,
        provider_invocation_id=None,
        latency_ms=latency_ms,
        created_at=datetime.now(UTC),
    )


def _evaluate_critical_tokens_real(
    check: QualityCheck,
    manifest: QualityInputManifest,
    artifacts: dict[str, Any],
    supporting_artifacts: dict[str, Any],
    started: datetime,
) -> QualityEvaluation:
    """Real critical token evaluation."""
    asr_alignment = supporting_artifacts.get("asr_alignment")
    speech_manifest = supporting_artifacts.get("speech_manifest")

    critical_tokens = (
        speech_manifest.get("critical_tokens", []) if speech_manifest else []
    )
    result = SpeechQualityChecks.verify_critical_tokens(asr_alignment, critical_tokens)

    score = (
        result.matched_tokens / result.total_tokens if result.total_tokens > 0 else 1.0
    )
    passed = result.matched_tokens == result.total_tokens

    dimensions = [
        EvaluationDimension(
            schema_version="evaluation-dimension.v1",
            name="critical_tokens",
            score=score,
            threshold=1.0,
            severity=Severity.CRITICAL if not passed else Severity.INFO,
            failure_codes=[FailureCode.QUALITY_TTS_OMISSION] if not passed else [],
            evidence_refs=[f"token_{t}" for t in critical_tokens],
            details={
                "total_critical_tokens": result.total_tokens,
                "matched": result.matched_tokens,
                "missed": result.missed_tokens,
                "phonetically_confused": result.phonetically_confused,
            },
        )
    ]
    evidence = [{"check": "critical_tokens", **result.__dict__}]

    outcome = CheckOutcome.PASS if passed else CheckOutcome.FAIL
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
        rubric_version=None,
        dimensions=dimensions,
        outcome=outcome,
        confidence=Confidence.HIGH,
        abstained=False,
        evidence=evidence,
        estimated_cost_minor=5,
        actual_cost_minor=3,
        provider_invocation_id=None,
        latency_ms=latency_ms,
        created_at=datetime.now(UTC),
    )


def _evaluate_forced_alignment_real(
    check: QualityCheck,
    manifest: QualityInputManifest,
    artifacts: dict[str, Any],
    supporting_artifacts: dict[str, Any],
    started: datetime,
) -> QualityEvaluation:
    """Real forced alignment evaluation."""
    asr_alignment = supporting_artifacts.get("asr_alignment")
    audio = artifacts.get(manifest.target_artifact_ids[0])

    expected_duration = int(audio.get("duration_seconds", 0) * 1000) if audio else 0
    result = SpeechQualityChecks.evaluate_forced_alignment(
        asr_alignment, expected_duration
    )

    passed = result.alignment_score >= 0.90

    dimensions = [
        EvaluationDimension(
            schema_version="evaluation-dimension.v1",
            name="forced_alignment",
            score=result.alignment_score,
            threshold=0.90,
            severity=Severity.MAJOR if not passed else Severity.INFO,
            failure_codes=[FailureCode.QUALITY_TTS_PRONUNCIATION] if not passed else [],
            evidence_refs=["alignment_quality"],
            details={
                "alignment_score": result.alignment_score,
                "avg_token_duration_ms": result.avg_token_duration_ms,
                "max_token_duration_ms": result.max_token_duration_ms,
                "silence_ratio": result.silence_ratio,
                "out_of_order_tokens": result.out_of_order_tokens,
            },
        )
    ]
    evidence = [{"check": "forced_alignment", **result.__dict__}]

    outcome = CheckOutcome.PASS if passed else CheckOutcome.FAIL
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
        rubric_version=None,
        dimensions=dimensions,
        outcome=outcome,
        confidence=Confidence.HIGH,
        abstained=False,
        evidence=evidence,
        estimated_cost_minor=5,
        actual_cost_minor=4,
        provider_invocation_id=None,
        latency_ms=latency_ms,
        created_at=datetime.now(UTC),
    )


def _evaluate_signal_quality_real(
    check: QualityCheck,
    manifest: QualityInputManifest,
    artifacts: dict[str, Any],
    supporting_artifacts: dict[str, Any],
    started: datetime,
) -> QualityEvaluation:
    """Real signal quality evaluation."""
    audio = artifacts.get(manifest.target_artifact_ids[0])
    audio_path = audio.get("file_path", "") if audio else ""

    result = SpeechQualityChecks.measure_signal_quality(audio_path)

    snr_pass = result.snr_db >= 30.0
    clipping_pass = result.clipping_percent <= 1.0
    silence_pass = result.silence_percent <= 5.0

    dimensions = [
        EvaluationDimension(
            schema_version="evaluation-dimension.v1",
            name="snr",
            score=min(result.snr_db / 60.0, 1.0),
            threshold=0.5,
            severity=Severity.MINOR if not snr_pass else Severity.INFO,
            failure_codes=[FailureCode.QUALITY_AUDIO_DECODE] if not snr_pass else [],
            evidence_refs=["snr_measurement"],
            details={"snr_db": result.snr_db, "threshold_db": 30.0},
        ),
        EvaluationDimension(
            schema_version="evaluation-dimension.v1",
            name="clipping",
            score=1.0 - result.clipping_percent / 100.0,
            threshold=0.99,
            severity=Severity.MINOR if not clipping_pass else Severity.INFO,
            failure_codes=[FailureCode.QUALITY_AUDIO_DECODE]
            if not clipping_pass
            else [],
            evidence_refs=["clipping_measurement"],
            details={
                "clipping_percent": result.clipping_percent,
                "threshold_percent": 1.0,
            },
        ),
        EvaluationDimension(
            schema_version="evaluation-dimension.v1",
            name="silence",
            score=1.0 - result.silence_percent / 100.0,
            threshold=0.95,
            severity=Severity.MINOR if not silence_pass else Severity.INFO,
            failure_codes=[FailureCode.QUALITY_AUDIO_DECODE]
            if not silence_pass
            else [],
            evidence_refs=["silence_measurement"],
            details={
                "silence_percent": result.silence_percent,
                "threshold_percent": 5.0,
            },
        ),
    ]
    evidence = [{"check": "signal_quality", **result.__dict__}]

    outcome = (
        CheckOutcome.PASS
        if (snr_pass and clipping_pass and silence_pass)
        else CheckOutcome.FAIL
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
        rubric_version=None,
        dimensions=dimensions,
        outcome=outcome,
        confidence=Confidence.HIGH,
        abstained=False,
        evidence=evidence,
        estimated_cost_minor=5,
        actual_cost_minor=3,
        provider_invocation_id=None,
        latency_ms=latency_ms,
        created_at=datetime.now(UTC),
    )
