"""Gold examples and evaluator harness for quality check validation."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pipeline.contracts.quality import (
    EvaluationDimension,
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
    from pipeline.quality.registry import QualityCheckRegistry


@dataclass(frozen=True, slots=True)
class GoldExample:
    """A gold-standard example for evaluator validation.

    Contains the input artifacts, the expected evaluation outcome,
    and the expected dimension scores. Used to validate that evaluators
    produce consistent, correct results.
    """

    schema_version: str = "gold-example.v1"
    example_id: str = field(default_factory=lambda: f"gold_{uuid.uuid4().hex[:12]}")
    check_id: str = ""
    evaluator: str = ""
    evaluator_version: str = ""
    rubric_version: str | None = None
    description: str = ""

    # Input artifacts (as JSON-serializable dicts)
    target_artifacts: dict[str, Any] = field(default_factory=dict)
    supporting_artifacts: dict[str, Any] = field(default_factory=dict)

    # Expected output
    expected_outcome: CheckOutcome = CheckOutcome.PASS
    expected_confidence: Confidence = Confidence.HIGH
    expected_dimensions: list[EvaluationDimension] = field(default_factory=list)
    expected_failure_codes: list[FailureCode] = field(default_factory=list)

    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    created_by: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "schema_version": self.schema_version,
            "example_id": self.example_id,
            "check_id": self.check_id,
            "evaluator": self.evaluator,
            "evaluator_version": self.evaluator_version,
            "rubric_version": self.rubric_version,
            "description": self.description,
            "target_artifacts": self.target_artifacts,
            "supporting_artifacts": self.supporting_artifacts,
            "expected_outcome": self.expected_outcome.value,
            "expected_confidence": self.expected_confidence.value,
            "expected_dimensions": [
                dim.model_dump(mode="json") for dim in self.expected_dimensions
            ],
            "expected_failure_codes": [fc.value for fc in self.expected_failure_codes],
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict) -> GoldExample:
        """Deserialize from dictionary."""
        data = data.copy()
        data["expected_outcome"] = CheckOutcome(data["expected_outcome"])
        data["expected_confidence"] = Confidence(data["expected_confidence"])
        data["expected_dimensions"] = [
            EvaluationDimension.model_validate(d) for d in data["expected_dimensions"]
        ]
        data["expected_failure_codes"] = [
            FailureCode(fc) for fc in data["expected_failure_codes"]
        ]
        data["created_at"] = datetime.fromisoformat(
            data["created_at"].replace("Z", "+00:00")
        )
        return cls(**data)

    def save(self, path: Path) -> None:
        """Save to JSON file."""
        path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path) -> GoldExample:
        """Load from JSON file."""
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


@dataclass(slots=True)
class HarnessResult:
    """Result of running an evaluator against a gold example."""

    example: GoldExample
    actual_evaluation: QualityEvaluation
    passed: bool
    mismatches: list[str] = field(default_factory=list)


class EvaluatorHarness:
    """Harness for validating evaluators against gold examples."""

    def __init__(self, registry: QualityCheckRegistry) -> None:
        self.registry = registry
        self._examples: dict[str, GoldExample] = {}

    def add_example(self, example: GoldExample) -> None:
        """Add a gold example to the harness."""
        if example.example_id in self._examples:
            raise ValueError(f"Example {example.example_id!r} already exists")
        self._examples[example.example_id] = example

    def load_examples_from_dir(self, directory: Path) -> int:
        """Load all gold examples from a directory."""
        count = 0
        for path in directory.glob("*.json"):
            try:
                example = GoldExample.load(path)
                self.add_example(example)
                count += 1
            except Exception as e:
                print(f"Warning: Failed to load {path}: {e}")
        return count

    def run_example(self, example_id: str) -> HarnessResult:
        """Run a single gold example against its evaluator."""
        example = self._examples.get(example_id)
        if example is None:
            raise KeyError(f"Example {example_id!r} not found")

        check = self.registry.get(example.check_id)
        evaluator = self.registry.get_evaluator(example.check_id)

        # Create manifest
        manifest = QualityInputManifest(
            schema_version="quality-input-manifest.v1",
            manifest_id=f"manifest_{uuid.uuid4().hex[:12]}",
            gate_id="test_gate",
            check_id=check.check_id,
            target_artifact_ids=list(example.target_artifacts.keys()),
            target_hashes={
                aid: self._compute_hash(content)
                for aid, content in example.target_artifacts.items()
            },
            supporting_artifact_ids=list(example.supporting_artifacts.keys()),
            created_at=datetime.now(UTC),
        )

        # Run evaluator
        actual = evaluator.evaluate(
            check=check,
            manifest=manifest,
            artifacts=example.target_artifacts,
            supporting_artifacts=example.supporting_artifacts,
        )

        # Compare results
        mismatches = self._compare(example, actual)
        passed = len(mismatches) == 0

        return HarnessResult(
            example=example,
            actual_evaluation=actual,
            passed=passed,
            mismatches=mismatches,
        )

    def run_all(self) -> list[HarnessResult]:
        """Run all gold examples."""
        return [self.run_example(eid) for eid in self._examples]

    def _compare(self, example: GoldExample, actual: QualityEvaluation) -> list[str]:
        """Compare expected vs actual evaluation."""
        mismatches = []

        # Check outcome
        if actual.outcome != example.expected_outcome:
            exp = example.expected_outcome.value
            act = actual.outcome.value
            mismatches.append(f"outcome: expected {exp}, got {act}")

        # Check confidence (if not abstained)
        if not actual.abstained and actual.confidence != example.expected_confidence:
            exp = example.expected_confidence.value
            act = actual.confidence.value
            mismatches.append(f"confidence: expected {exp}, got {act}")

        # Check dimensions
        expected_dims = {dim.name: dim for dim in example.expected_dimensions}
        actual_dims = {dim.name: dim for dim in actual.dimensions}

        for name, expected_dim in expected_dims.items():
            actual_dim = actual_dims.get(name)
            if actual_dim is None:
                mismatches.append(f"dimension {name!r}: missing in actual")
                continue

            exp_score = expected_dim.score
            act_score = actual_dim.score
            if (
                exp_score is not None
                and act_score is not None
                and abs(exp_score - act_score) > 0.05
            ):
                msg = (
                    f"dimension {name!r} score: "
                    f"expected {exp_score:.3f}, got {act_score:.3f}"
                )
                mismatches.append(msg)

            exp_thresh = expected_dim.threshold
            act_thresh = actual_dim.threshold
            if (
                exp_thresh is not None
                and act_thresh is not None
                and abs(exp_thresh - act_thresh) > 0.01
            ):
                msg = (
                    f"dimension {name!r} threshold: "
                    f"expected {exp_thresh:.3f}, got {act_thresh:.3f}"
                )
                mismatches.append(msg)

            if set(expected_dim.failure_codes) != set(actual_dim.failure_codes):
                exp_fc = sorted(expected_dim.failure_codes)
                act_fc = sorted(actual_dim.failure_codes)
                msg = (
                    f"dimension {name!r} failure_codes: expected {exp_fc}, got {act_fc}"
                )
                mismatches.append(msg)

        for name in actual_dims:
            if name not in expected_dims:
                mismatches.append(f"dimension {name!r}: unexpected in actual")

        # Check failure codes
        # Note: hard_failure_codes is on QualityGateResult, not QualityEvaluation
        # We check dimension failure_codes instead
        actual_codes = set()
        for dim in actual.dimensions:
            actual_codes.update(dim.failure_codes)
        exp_fc = sorted(example.expected_failure_codes)
        act_fc = sorted(actual_codes)
        if exp_fc != act_fc:
            mismatches.append(f"failure_codes: expected {exp_fc}, got {act_fc}")

        return mismatches

    def _compute_hash(self, content: Any) -> str:
        """Compute SHA256 hash of content."""
        import hashlib

        data = json.dumps(content, sort_keys=True).encode("utf-8")
        return hashlib.sha256(data).hexdigest()


def create_gold_examples_dir(path: Path) -> int:
    """Create a directory with gold examples for all built-in checks."""
    path.mkdir(parents=True, exist_ok=True)
    count = 0

    # Example for script_claim_evidence_v1
    example = GoldExample(
        check_id="script_claim_evidence_v1",
        evaluator="claim_evidence_evaluator",
        evaluator_version="1.0.0",
        rubric_version="claim-evidence-rubric-v1",
        description="All claims supported by evidence",
        target_artifacts={
            "artifact_script_v1": {
                "schema_version": "script.v1",
                "claims": [
                    {
                        "claim_id": "claim_1",
                        "text": "The sky is blue",
                        "evidence_refs": ["ev_1"],
                        "supported": True,
                    },
                    {
                        "claim_id": "claim_2",
                        "text": "Water boils at 100°C",
                        "evidence_refs": ["ev_2"],
                        "supported": True,
                    },
                ],
            }
        },
        supporting_artifacts={
            "claim_ledger": {"claims": []},
            "evidence_snapshots": {
                "ev_1": {
                    "source": "wikipedia",
                    "excerpt": "The sky appears blue due to Rayleigh scattering",
                },
                "ev_2": {
                    "source": "physics_textbook",
                    "excerpt": "Water boils at 100°C at standard pressure",
                },
            },
        },
        expected_outcome=CheckOutcome.PASS,
        expected_confidence=Confidence.HIGH,
        expected_dimensions=[
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="claim_support",
                score=1.0,
                threshold=0.8,
                severity=Severity.INFO,
                failure_codes=[],
                evidence_refs=["ev_1", "ev_2"],
                details={"total_claims": 2, "supported": 2, "normalization": "text-v1"},
            )
        ],
        expected_failure_codes=[],
        created_by="system",
        tags=["positive", "claim_evidence"],
    )
    example.save(path / "script_claim_evidence_v1_pass.json")
    count += 1

    # Example for script_claim_evidence_v1 with unsupported claim
    example_fail = GoldExample(
        check_id="script_claim_evidence_v1",
        evaluator="claim_evidence_evaluator",
        evaluator_version="1.0.0",
        rubric_version="claim-evidence-rubric-v1",
        description="One claim lacks evidence",
        target_artifacts={
            "artifact_script_v1": {
                "schema_version": "script.v1",
                "claims": [
                    {
                        "claim_id": "claim_1",
                        "text": "The sky is blue",
                        "evidence_refs": ["ev_1"],
                        "supported": True,
                    },
                    {
                        "claim_id": "claim_2",
                        "text": "Aliens built the pyramids",
                        "evidence_refs": ["ev_3"],
                        "supported": False,
                    },
                ],
            }
        },
        supporting_artifacts={
            "claim_ledger": {"claims": []},
            "evidence_snapshots": {
                "ev_1": {
                    "source": "wikipedia",
                    "excerpt": "The sky appears blue due to Rayleigh scattering",
                },
            },
        },
        expected_outcome=CheckOutcome.FAIL,
        expected_confidence=Confidence.HIGH,
        expected_dimensions=[
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="claim_support",
                score=0.5,
                threshold=0.8,
                severity=Severity.MAJOR,
                failure_codes=[FailureCode.QUALITY_UNSUPPORTED_CLAIM],
                evidence_refs=["ev_1", "ev_3"],
                details={"total_claims": 2, "supported": 1, "normalization": "text-v1"},
            )
        ],
        expected_failure_codes=[FailureCode.QUALITY_UNSUPPORTED_CLAIM],
        created_by="system",
        tags=["negative", "claim_evidence"],
    )
    example_fail.save(path / "script_claim_evidence_v1_fail.json")
    count += 1

    # Example for speech_wer_cer_v1
    example_wer = GoldExample(
        check_id="speech_wer_cer_v1",
        evaluator="wer_cer_evaluator",
        evaluator_version="1.0.0",
        description="Low WER and CER",
        target_artifacts={
            "artifact_audio_v1": {
                "schema_version": "audio.v1",
                "duration_seconds": 10.0,
            },
        },
        supporting_artifacts={
            "speech_manifest": {
                "schema_version": "speech-manifest.v1",
                "narration_text_hashes": {"scene_1": "abc123"},
                "critical_tokens": [
                    {"token_id": "tok_1", "text": "important", "matched": True}
                ],
            },
            "asr_alignment": {
                "schema_version": "asr-alignment.v1",
                "word_timestamps": [],
            },
        },
        expected_outcome=CheckOutcome.PASS,
        expected_confidence=Confidence.HIGH,
        expected_dimensions=[
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="wer",
                score=0.97,
                threshold=0.90,
                severity=Severity.INFO,
                failure_codes=[],
                evidence_refs=["wer_measurement"],
                details={"wer": 0.03, "threshold": 0.10, "normalization": "text-v1"},
            ),
            EvaluationDimension(
                schema_version="evaluation-dimension.v1",
                name="cer",
                score=0.99,
                threshold=0.95,
                severity=Severity.INFO,
                failure_codes=[],
                evidence_refs=["cer_measurement"],
                details={"cer": 0.01, "threshold": 0.05, "normalization": "text-v1"},
            ),
        ],
        expected_failure_codes=[],
        created_by="system",
        tags=["positive", "speech_quality"],
    )
    example_wer.save(path / "speech_wer_cer_v1_pass.json")
    count += 1

    return count
