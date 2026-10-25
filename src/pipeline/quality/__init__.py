"""Quality gate, repair, and human approval system (FV-10).

This package provides the quality assurance subsystem for the video pipeline.
It implements a multi-layered quality assurance system with:

- **Deterministic checks**: Schema validation, reference integrity, asset availability,
  timeline validation (fast, reproducible, no external dependencies)
- **Specialized checks**: WER/CER evaluation, critical token verification,
  forced alignment, signal quality, license compliance, A/V sync,
  media decode, profile validation, timeline validation, assembly integrity,
  A/V drift, short derivative integrity (algorithmic, may use ffprobe)
- **Semantic checks**: Claim/evidence support, editorial clarity, visual intent
  coherence (LLM-based, require rubric version)
- **Human review**: Manual approval gates for subjective quality judgments

The quality system operates on a **three-zone threshold model**:
- **PASS zone**: score >= pass_threshold → automatic pass
- **HUMAN_REVIEW zone**: review_threshold <= score < pass_threshold → human review
- **FAIL zone**: score < review_threshold (or pass_threshold
  if no review threshold) -> FAIL

Quality gates aggregate evaluations from multiple checks and apply policies
to produce gate decisions: PASS, FAIL, REGENERATE, or HUMAN_REVIEW.

The system integrates with the execution engine via repair plans and
human review management, enabling automated regeneration loops and
human-in-the-loop quality control.

Key Components:
- **QualityCheckRegistry**: Versioned registry of quality checks with evaluators
- **QualityGate**: Orchestrates evaluation of all checks for a gate
- **QualityPipeline**: Full pipeline orchestrating checks, repair, and human review
- **RepairPlanner**: Creates targeted repair plans from gate failures
- **HumanReviewManager**: Manages human review lifecycle
- **QualityReportGenerator**: Generates aggregate quality reports
- **ThresholdRegistry**: Manages pass/review thresholds with recalibration

Versioning: All checks, gates, and policies are explicitly versioned.
Rubric versions control semantic evaluator behavior.
"""

from __future__ import annotations

from pipeline.quality.gate import QualityGate, evaluate_gate
from pipeline.quality.human_review import HumanReviewManager, request_human_review
from pipeline.quality.pipeline import QualityPipeline, run_quality_pipeline
from pipeline.quality.registry import QualityCheckRegistry, get_default_registry
from pipeline.quality.repair import RepairPlanner, create_repair_plan
from pipeline.quality.report import QualityReportGenerator, generate_quality_report

__all__ = [
    "HumanReviewManager",
    "QualityCheckRegistry",
    "QualityGate",
    "QualityPipeline",
    "QualityReportGenerator",
    "RepairPlanner",
    "create_repair_plan",
    "evaluate_gate",
    "generate_quality_report",
    "get_default_registry",
    "request_human_review",
    "run_quality_pipeline",
]
