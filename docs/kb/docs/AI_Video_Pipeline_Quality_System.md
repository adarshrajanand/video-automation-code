# AI Video Automation Pipeline — Quality System

**Status:** Canonical quality-control design

**Purpose:** Define quality as a measurable, versioned, parallel subsystem rather than a collection of uncalibrated final LLM scores.

## 1. Quality objective

The system should optimize for:

```text
low false acceptance of serious defects
+ acceptable false rejection
+ explainable decisions
+ useful targeted repair
+ bounded cost and latency
```

The primary production metric is:

```text
cost per accepted video
  = generation + evaluation + regeneration + compute + storage
    ------------------------------------------------------------
                    accepted videos
```

Do not optimize for the cheapest individual model call. A cheap judge that misses serious defects can allow expensive downstream work and reputational risk.

## 2. Quality architecture

```text
Artifact version + exact inputs
              ↓
      Quality check planner
              ↓
  ┌───────────┼───────────┐
  ▼           ▼           ▼
Deterministic Specialized Semantic
checks       measures     judges
  └───────────┼───────────┘
              ▼
       Escalation policy
              ▼
 Stronger judge / human review
              ▼
          Quality gate
              ▼
 PASS / REGENERATE / HUMAN_REVIEW / FAIL
```

The quality engine owns check execution and evidence formatting. The Workflow Engine owns the durable transition after the gate decision.

The normative fast-slice checks and gate membership are in
[`registries/quality_gates.yaml`](registries/quality_gates.yaml). This document
defines their semantics; it is not a second registry.

## 3. Quality object model

### 3.1 Quality check

A `QualityCheck` is one requirement or evaluator operation:

```yaml
schema_version: quality-check.v1
check_id: script_claim_evidence_v1
target_artifact_types: [script]
required_input_types:
  - script
  - claim_ledger
  - evidence_snapshots
kind: SEMANTIC
evaluator: claim_evidence_evaluator
evaluator_version: 1.0.0
rubric_version: claim-entailment-v1
severity_if_failed: MAJOR
on_failure: REGENERATE
repair_scope: SCENE
```

### 3.2 Quality gate policy

```yaml
schema_version: quality-gate-policy.v1
gate_id: script_gate_v1
version: "1.0"
required_check_ids:
  - script_schema_v1
  - claim_reference_integrity_v1
  - script_claim_evidence_v1
  - script_editorial_clarity_v1
hard_failure_codes:
  - QUALITY.SCHEMA_INVALID
  - QUALITY.UNSUPPORTED_CLAIM
  - POLICY.PROHIBITED_CONTENT
pass_thresholds: {clarity: 0.80, editorial_quality: 0.80}
human_review_thresholds: {clarity: 0.65, editorial_quality: 0.65}
max_regenerations: 2
after_max_regenerations: HUMAN_REVIEW
```

### 3.3 Evaluation result

A check outcome and a gate decision are different concepts. A check returns one
of `PASS`, `FAIL`, `ABSTAIN`, `ERROR`, or `NOT_APPLICABLE`. The gate aggregates
all required check outcomes into exactly one workflow action:
`PASS`, `REGENERATE`, `HUMAN_REVIEW`, or `FAIL`.

Every evaluation records:

- exact artifact IDs and hashes;
- target stage/scene/shot;
- check/evaluator/rubric version;
- model/provider/resource where applicable;
- dimension scores and thresholds;
- severity and failure codes;
- evidence references;
- confidence/abstention;
- latency and cost;
- check outcome;
- recommended repair scope.

## 4. Evaluation layers

### Layer 0 — Deterministic validation

Use code for properties that code can establish:

- schema and required fields;
- IDs and references;
- source/artifact existence;
- hashes and media integrity;
- dates, numbers, units, and arithmetic;
- duration, frame rate, dimensions, codec, sample rate;
- audio clipping, silence, loudness, peak levels;
- timeline ranges, overlaps, gaps, safe areas;
- caption bounds and timing;
- code syntax/compile/lint/test;
- mathematical symbolic/numeric/unit checks where tools support them;
- licensing metadata presence.

### Layer 1 — Specialized measurements

Use focused algorithms/models for:

- ASR transcript versus approved narration;
- WER/CER with domain normalization;
- forced alignment and speech rate;
- perceptual duplicate/similarity detection;
- image/video relevance features;
- visual artifact detection;
- source retrieval and excerpt matching;
- audio signal transitions;
- black/frozen-frame detection;
- code execution sandbox results.

### Layer 2 — Narrow semantic judgment

Use a relatively economical model for a single well-defined question:

- does evidence entail this claim?
- does the narration match the visual intent?
- is the idea distinct from a comparison set?
- is the script understandable to the target audience?
- is the selected short context sufficient?

### Layer 3 — Strong adjudication

Escalate only for:

- high-impact claims;
- disagreement between checks;
- low-confidence/abstention;
- borderline threshold results;
- difficult multimodal alignment;
- new model/prompt rollout;
- randomized accepted-output audits.

### Layer 4 — Human review

Use a durable review state for:

- unresolved material factual claims;
- licensing uncertainty;
- repeated repair failure;
- evaluator disagreement;
- high-risk finance/science/technical claims;
- final publication approval;
- cases outside evaluator scope.

## 5. Stage quality matrix

| Stage | Deterministic/specialized | Semantic evaluator | Initial tier |
|---|---|---|---|
| Topic discovery | source accessibility, dates, duplicates, required metadata | relevance, freshness, audience fit | economical, escalate strong |
| Idea development | constraints, uniqueness, prohibited topics, diversity | usefulness, novelty, promise, feasibility | economical; strong shortlist |
| Research | URL/snapshot/excerpt, dates, numbers, source class | entailment, conflict, inference vs fact | tools + economical; strong high-impact |
| Script | schema, word/duration, IDs, references, banned content | clarity, coherence, editorial promise | economical + strong final |
| Visual planning | scene/shot coverage, timing, asset requirements, text bounds | visual storytelling, redundancy, misleading implications | economical; multimodal escalation |
| Asset acquisition | decode, resolution, aspect, duplicates, provenance | semantic match, entity/context correctness | CV/economical; strong ambiguity |
| Speech generation | decode, duration, clipping, silence, loudness, stream properties | naturalness, prosody, pronunciation | signal + ASR; strong exceptions |
| Composition | references, ranges, overlaps, safe areas, reconstructability | transitions and visual emphasis | deterministic; strong preview exceptions |
| Rendering | exit code, decode, dimensions, frames, audio, black/frozen frames | sampled visual defects | deterministic/CV; strong exceptions |
| Assembly | order, duration, A/V sync, loudness, continuity | flow, repetition, perceptual consistency | deterministic; strong exceptions |
| Shorts | source selection, context, aspect, captions, duration | hook/promise, context sufficiency, misleading crop | economical; strong ambiguity |
| Final review | complete technical/policy checklist | holistic content/editorial review | strong; frontier selective |
| Publishing | metadata/platform/rights/upload status | packaging alignment and tone | economical; strong ambiguity |

### 5.1 Evaluator classes and measurement contract

Every measurement is classified before implementation:

| Kind | Meaning | Typical examples | Gate use |
|---|---|---|---|
| `DETERMINISTIC` | A rule or program whose result is repeatable for the same versioned inputs | schema validation, hashes, frame ranges, duration, references | Hard gate when the rule represents a required invariant |
| `SPECIALIZED` | A fixed signal-processing algorithm or trained measurement model | WER, forced alignment, VMAF, DNSMOS, OCR, duplicate detection | Diagnostic or calibrated gate; record model/version and input requirements |
| `SEMANTIC` | A narrow probabilistic judgment about meaning, intent, or audience effect | claim entailment, visual relevance, context preservation | Categorical outcome with evidence, confidence, and abstention; never an unexplained aggregate score |
| `HUMAN` | A reviewer decision for risk or evaluator scope beyond validated automation | licensing uncertainty, material finance claim, final publication | Durable approval, repair, rejection, or escalation |

A fixed specialized model may be repeatable without being objective truth. A low
WER does not prove natural prosody; a high image-text similarity does not prove
factual correctness; and a high perceptual video score does not prove semantic
alignment. Every specialized or semantic evaluator therefore records:

- exact target artifact IDs and hashes;
- input/reference artifact IDs and hashes;
- evaluator implementation and version;
- model, provider, prompt, rubric, and configuration versions where applicable;
- raw metric values and units;
- normalization and preprocessing rules;
- threshold version;
- outcome: `PASS`, `FAIL`, `ABSTAIN`, `ERROR`, or `NOT_APPLICABLE`;
- confidence and evidence references;
- recommended repair scope;
- latency and cost.

Do not collapse dimensions into one universal quality score. A hard technical
failure, a factuality failure, and a soft pacing preference have different
actions even if they receive numerically similar scores.

### 5.2 Artifact measurement matrix

The following is the base measurement plan. Domain and channel profiles add
checks and thresholds; they do not remove required integrity and lineage checks.

| Artifact | Dimensions to measure | Deterministic | Specialized | Semantic / human |
|---|---|---|---|---|
| Topic/idea | source freshness, duplicates, constraints, audience, novelty, feasibility | required fields, dates, policy rules, duplicate keys | embedding similarity, diversity, freshness class | usefulness, promise, distinctiveness |
| Source/snapshot/evidence | retrieval integrity, excerpt integrity, authority, freshness, claim linkage | URL/snapshot/hash/excerpt/date/reference checks | source clustering, exact excerpt matching | entailment, conflict interpretation, source suitability |
| Claim ledger | claim type, evidence completeness, numbers, units, dates, uncertainty | IDs, arithmetic, units, dates, evidence graph | numeric extraction, unit/currency conversion | entailment, causation, caveat preservation |
| Script | schema, scene IDs, references, duration, pronunciation, policy | schema, IDs, word/duration bounds, claim references | readability, speech-rate estimate, duplication | clarity, coherence, audience fit, editorial promise |
| Visual plan | scene/shot coverage, timing, required/prohibited elements, asset requirements | structure, IDs, timing ranges, coverage | repetition and shot-duration statistics | narration-to-visual intent, misleading implication |
| Image/source asset | decode, dimensions, aspect, provenance, rights, text, duplicates | media/provenance/hash/OCR-required-text checks | blur/noise/artifacts, perceptual duplicate, object/OCR confidence | relevance, entity correctness, visual suitability; rights review |
| Speech/audio | decode, stream properties, duration, loudness, clipping, fidelity, timing, naturalness | decode, sample rate, channels, duration, peak, silence, boundaries | WER/CER, forced alignment, speech rate, speaker similarity, DNSMOS/NISQA/UTMOS | pronunciation, emphasis, prosody, voice continuity, listening audit |
| Composition | references, hierarchy, ranges, overlaps, gaps, safe areas, reconstructability | schema, graph, frame/timing, caption bounds, render-profile checks | font measurement, waveform/layout diagnostics | transition intent and visual emphasis |
| Render chunk | decode, frames, profile, audio, black/freeze, frame drops, artifacts | full decode, frame count, dimensions, codec, stream, black/freeze checks | VMAF/SSIM/LPIPS with reference, flicker and temporal checks | sampled visual defects and semantic frame errors |
| Assembled cut | chunk order, duration, sync, loudness, continuity, scene completeness | manifest/order/duration/A/V/loudness checks | drift, discontinuity, repetition, scene-boundary analysis | pacing, flow, narration-visual alignment, audience comprehension |
| Short derivative | source linkage, context, crop, aspect, captions, duration, policy | source hashes, vertical profile, caption bounds, timeline | crop/entity retention, duplicate/reuse, OCR | hook, context preservation, misleading omission |
| Final package | approvals, hashes, metadata, rights, platform profile, publication state | exact approved hashes, required metadata, idempotency, policy | platform/media preflight | title/thumbnail/content alignment and final review |

The matrix is a measurement catalog, not an instruction to run every evaluator
on every artifact. The fast slice should implement the deterministic checks,
the required specialized checks, and only the narrow semantic checks listed in
the fast-validation acceptance criteria.

## 6. Hard gates versus scored dimensions

Do not average all scores.

### Hard gates

Any of these blocks acceptance:

- corrupted or undecodable media;
- missing required audio/video/caption stream;
- missing required source or asset provenance;
- unsupported material claim under domain policy;
- prohibited content;
- invalid output dimensions/codec/profile;
- unresolved high-impact evaluator disagreement;
- missing human approval where required;
- unauthorized paid spend;
- stale/incompatible input artifact.

### Scored dimensions

These may use calibrated thresholds:

- clarity;
- pacing;
- originality;
- visual relevance;
- naturalness;
- audience fit;
- narrative progression;
- packaging quality.

Scores need not share a universal meaning across evaluators. Store evaluator/rubric-specific thresholds.

## 7. Gate aggregation algorithm

Conceptual order:

```text
if any required check has ERROR or a critical hard-failure code:
    FAIL or REGENERATE according to the registered failure policy
elif any required check is missing or ABSTAIN:
    HUMAN_REVIEW or REGENERATE according to the gate policy
elif any required check is FAIL with a repair scope:
    REGENERATE
elif any required score is below its human-review threshold:
    HUMAN_REVIEW or REGENERATE according to the gate policy
elif all required checks are PASS and all pass thresholds hold:
    PASS
else:
    HUMAN_REVIEW
```

The gate must retain individual evaluations. A single aggregate number is not
enough to explain a decision. Missing evaluations are not treated as passing.
The gate result records the policy version, evaluation IDs, exact target hashes,
and the repair-generation count used for the decision.

### 7.1 Exact measurement protocol

Every evaluator follows the same sequence:

1. Resolve an immutable `QualityInputManifest` containing target and supporting
   artifact IDs and hashes.
2. Materialize inputs into a temporary workspace and verify every checksum.
3. Normalize inputs according to the evaluator version: text normalization,
   sample rate, channel layout, frame rate, color space, locale, or token rules.
4. Execute the pinned evaluator with a pinned configuration.
5. Store raw measurements, units, preprocessing metadata, and evidence files.
6. Derive the categorical outcome and repair scope from the versioned threshold
   policy; do not let the evaluator silently choose workflow transitions.
7. Cache only when the target hashes, supporting hashes, evaluator version,
   model/provider version, rubric, configuration, and threshold version match.

The evaluator may return a numeric measurement, but the persisted quality
result must also include the interpretation:

```json
{
  "metric_id": "audio.wer.v1",
  "raw_value": 0.031,
  "unit": "ratio",
  "normalization": "software-en-us-v1",
  "threshold_policy_version": "speech-gate-v1",
  "outcome": "PASS",
  "confidence": "HIGH",
  "evidence_refs": ["artifact://alignment/scene_03"],
  "repair_scope": "SCENE"
}
```

#### 7.1.1 Deterministic structural and media measurements

Use these procedures before any semantic evaluator:

| Measurement | Procedure | Typical result |
|---|---|---|
| Schema validity | Deserialize with the pinned contract/schema version and reject unknown required-field violations | `PASS` or `QUALITY.SCHEMA_INVALID` |
| Reference integrity | Resolve every ID through the repository and verify expected type, run scope, and active/accepted status | `PASS` or missing-reference failure |
| Content identity | Compute SHA-256 over immutable bytes or canonical serialized payload; record algorithm and canonicalization | `sha256`, size, media metadata |
| Duration | Read container and stream durations; compare actual to policy using `abs(actual - expected) <= max(abs_tol, rel_tol * expected)` | actual duration, delta, outcome |
| Frame ranges | Check `0 <= start_frame < end_frame <= duration_frames`; sort siblings and detect forbidden overlap/gap | invalid ranges, overlap/gap evidence |
| Media profile | Use `ffprobe` JSON to inspect codec, dimensions, FPS, timebase, stream count, sample rate, channels, and duration | profile result and raw probe record |
| Caption safe area | Resolve text with the exact font/style, measure the rendered bounding box, and verify it lies inside the profile safe rectangle | overflow/overlap evidence |
| Black/frozen frames | Decode sampled and boundary frames; calculate black-pixel ratio and perceptual/frame difference across a configured run length | candidate intervals and severity |
| A/V sync | Compare audio/video PTS and duration; for narration, compare aligned scene audio intervals to composition frame intervals | drift in frames/ms |
| Loudness | Measure integrated loudness, loudness range, short-term loudness, and true peak using a pinned BS.1770/EBU R128 implementation | LUFS/LRA/true-peak values |
| Provenance | Require source/provider/license/retrieval or generation fields according to source type | complete/incomplete provenance |

Illustrative read-only probe commands are acceptable in implementation notes,
but the production evaluator should use a library or pinned subprocess wrapper
that records its exact version:

```bash
ffprobe -v error -show_format -show_streams -of json input.mp4
ffmpeg -i input.wav -af ebur128=peak=true -f null -
```

Thresholds such as black-pixel ratio, frozen-frame duration, sync tolerance,
and loudness range are profile data. They must be calibrated against valid and
defective fixtures, not copied as universal constants.

#### 7.1.2 Text, claims, and script measurements

##### Exact numeric, date, and unit validation

1. Extract candidate numbers, currencies, units, percentages, and dates from
   both the source evidence and the generated claim/script.
2. Normalize formatting: separators, signs, Unicode minus, currency symbols,
   unit aliases, date formats, and locale conventions.
3. Convert to a canonical unit/currency representation while retaining the
   original text and conversion metadata.
4. Compare values using a policy-defined exact or tolerance comparison.
5. Emit the source span, generated span, normalized values, and delta.

Do not use an LLM to decide whether `12.5%` equals `0.125`, whether two dates
are the same, or whether a unit conversion is arithmetically valid.

##### Claim-evidence entailment

Pass the evaluator a small evidence bundle, not an unbounded research dump:

```text
claim_id
claim_text
claim_type
importance
source_id
snapshot_id
exact_excerpt
as_of_date
known_conflicts
```

Require the evaluator to return one of:

```text
ENTAILED
PARTIALLY_ENTAILED
CONTRADICTED
INSUFFICIENT_EVIDENCE
ABSTAIN
```

It must cite the supporting or contradicting excerpt spans. A strong judge is
used only for material claims, disagreement, or low-confidence results. A
second model is an escalation path, not proof that the first model was right.

##### Script clarity and coherence

Use a versioned rubric with separate categorical dimensions rather than one
score:

```text
clarity: CLEAR | MINOR_ISSUE | UNCLEAR | ABSTAIN
coherence: COHERENT | LOCAL_BREAK | STRUCTURAL_BREAK | ABSTAIN
promise: FULFILLED | PARTIAL | MISSED | ABSTAIN
redundancy: NONE | ACCEPTABLE | EXCESSIVE | ABSTAIN
```

The evaluator receives the script, audience/channel profile, target duration,
and claim/evidence summary. It must identify the sentence or scene supporting
the result. Calibrate the rubric against human labels by scene, not only at
whole-script level.

#### 7.1.3 Speech and audio measurements

##### Transcript fidelity

1. Produce an ASR transcript with a pinned model and locale configuration.
2. Normalize approved narration and ASR text separately for punctuation,
   whitespace, numbers, acronyms, units, names, and accepted pronunciation
   variants.
3. Compute word error rate:

```text
WER = (substitutions + deletions + insertions) / reference_word_count
```

4. Also compute CER where tokenization is unreliable.
5. Separately calculate recall/precision for critical tokens:
   technical names, numbers, units, code identifiers, and claim terms.
6. Store the edit alignment, not just the final ratio.

WER is diagnostic. A scene can have a low WER and still have a wrong emphasis,
bad pronunciation, or unnatural pause. Critical-token failure should be able to
fail or escalate even when aggregate WER passes.

##### Forced alignment and timing

1. Align approved narration tokens to the audio using a pinned ASR/forced-
   alignment implementation.
2. Convert timestamps to the render profile's frame/timebase.
3. Verify token intervals are monotonic and inside the scene interval.
4. Compare actual scene duration with the script duration policy.
5. Record drift, unaligned spans, and confidence.

##### Naturalness, noise, and voice consistency

- Run a fixed non-intrusive speech-quality model on fixed-length windows and
  aggregate median and low-percentile results; record window size, sample rate,
  model version, and aggregation rule.
- Measure speech rate, pause lengths, pitch/energy statistics, and clipping with
  signal tools; compare against the voice/channel profile rather than a global
  threshold.
- Compare speaker embeddings between reference voice samples and scene windows
  using cosine similarity; calibrate the threshold separately for the chosen
  voice/model and locale.
- Use human listening labels for prosody, emphasis, technical pronunciation,
  and scene-to-scene continuity. Automatic speech-quality models are screening
  signals, not a substitute for those labels.

#### 7.1.4 Image and video measurements

##### Image-text and visual-intent relevance

1. Convert the visual intent into required elements, prohibited elements, and a
   short semantic description.
2. Run closed-vocabulary detectors/OCR for required exact elements where
   possible.
3. Compute image-text embedding similarity for ranking and anomaly detection.
4. Ask a VLM a narrow question about the actual image/frame:

```text
Does this frame contain the required element X?
Does it contain prohibited element Y?
Does it imply a claim or causal relationship not supported by the narration?
```

5. Require evidence such as bounding boxes, OCR spans, or frame references.
6. Escalate entity ambiguity or misleading implications to a stronger judge or
   human review.

Embedding similarity is not a factuality check. It can rank candidate assets,
but it must not by itself approve an asset representing a specific person,
product, event, or technical operation.

##### Reference-based perceptual video quality

Use VMAF/SSIM/PSNR/LPIPS only when a trusted reference exists and the videos
are aligned in resolution, FPS, timebase, crop, and duration:

1. validate reference/output alignment;
2. run the pinned metric model;
3. retain per-frame values and aggregate mean, median, low percentile, and
   worst-window values;
4. inspect the worst windows rather than accepting the mean alone.

If no reference exists, skip reference metrics rather than inventing a fake
reference. Use technical checks, no-reference artifact detectors, temporal
checks, and sampled VLM review instead.

##### Temporal consistency and generated-video checks

1. Sample frames at fixed intervals plus all scene/cut/overlay boundaries.
2. Detect repeated/frozen frames using frame differences and perceptual hashes.
3. Measure optical-flow discontinuities and abrupt identity/geometry changes.
4. Run fixed prompt-specific VLM checks for subject identity, spatial
   relationships, motion intent, and visual continuity.
5. Store per-scene/per-shot results; do not reduce the entire video to one score.

Distribution metrics such as FVD belong in provider/model benchmark reports,
where fixed sample counts, seeds, and datasets are controlled. They are not a
single-video publication gate.

#### 7.1.5 Composition, assembly, and short measurements

- Composition validators operate directly on the structured manifest: check
  parent containment, frame intervals, required layers, caption boxes, audio
  tracks, and reconstructability.
- Assembly validators compare the immutable expected chunk manifest with the
  ordered chunks, then inspect duration, PTS continuity, loudness transitions,
  and audio/video drift.
- Short-context evaluators receive the source transcript/claim bundle and the
  selected short transcript/frames. They return `PRESERVED`,
  `MISSING_CRITICAL_CONTEXT`, `MISLEADING`, or `ABSTAIN`, with the omitted or
  distorted claim IDs.
- Final packaging checks compare title, description, thumbnail, captions, and
  exact approved artifacts. A semantic judge may assess packaging alignment,
  but it cannot override hash, rights, profile, or human-approval failures.

#### 7.1.6 Metric definitions and aggregation rules

When a named metric is used, record what it actually computes:

| Metric | Computation | Direction and aggregation |
|---|---|---|
| WER | Token edit distance: `(S + D + I) / N`, where `S` is substitution, `D` deletion, `I` insertion, and `N` reference-token count | Lower is better; report overall value plus critical-token recall and per-scene worst values |
| CER | Character-level edit distance divided by reference-character count | Lower is better; use when word tokenization is unstable |
| CLIPScore-style relevance | Cosine similarity between normalized image/frame and text embeddings from pinned encoders | Higher is more similar; use for ranking/anomaly detection, not factual acceptance |
| LPIPS | Learned distance between deep feature representations of aligned reference/output images or frames | Lower is more perceptually similar; aggregate mean and worst windows |
| SSIM/PSNR | Full-reference structural/luma or signal comparison on aligned frames | Higher is better; diagnostic for encoding/regression, not semantic quality |
| VMAF | Full-reference learned video-quality prediction per frame/window | Higher is better; retain per-frame values, median, low percentile, and worst-window values |
| FVD | Distance between distributions of learned video features over a fixed generated/reference set | Lower is better; compare systems/datasets, never one production cut |
| Speaker similarity | Cosine similarity between reference and evaluated speaker embeddings | Higher is more similar; calibrate per speaker/model/locale |
| Optical-flow continuity | Compare flow vectors and motion statistics across adjacent frames or shot boundaries | Large discontinuities are candidates; inspect against intended cuts |
| MOS | Human ratings on a defined scale, commonly 1–5, with annotator instructions | Higher is better; report mean/median and confidence interval, not only mean |
| Pairwise preference | Human or model choice between candidate A and B for one defined criterion | Report win rate with sample size and confidence interval |
| Calibration | Compare evaluator probabilities/scores to verified labels using confusion matrix, precision/recall, false-pass rate, false-reject rate, and calibration error | Select thresholds for the required safety target, not maximum correlation alone |

For continuous metrics, store at least the mean, median, low percentile, high
percentile, and worst-window value when the artifact has temporal or scene
structure. A mean can hide one unacceptable scene. For human or probabilistic
labels, store sample size, label status, confidence interval where possible,
and the exact rubric.

## 8. Script and factuality quality

### Claim ledger

Each material claim should carry:

- claim text;
- claim type: fact, inference, opinion, speculation, fiction;
- importance/severity;
- evidence IDs;
- source class;
- exact excerpt/snapshot reference;
- as-of date;
- units/numbers where applicable;
- support status;
- unresolved/conflict notes.

### Deterministic checks

- source snapshot exists;
- excerpt reference resolves;
- numbers and units match where extractable;
- dates and as-of dates are present for time-sensitive claims;
- every material claim has evidence or explicit non-fact type;
- citations are not duplicated incorrectly;
- script claim IDs resolve;
- no unsupported source IDs are invented by a model.

### Semantic checks

- evidence entails the specific claim rather than a related topic;
- script does not convert correlation into causation;
- caveats are preserved;
- competing sources are represented;
- confidence and uncertainty match the evidence;
- the script does not overstate a source.

For finance, unresolved material claims should normally become human review or be removed/rephrased, not automatically passed by a second model.

## 9. Audio quality

### Deterministic/audio checks

- file decodes;
- expected sample rate/channels;
- duration within policy;
- no truncation or abrupt ending;
- no excessive silence;
- no clipping;
- loudness/peak within profile;
- all required scene audio exists;
- scene boundaries are monotonic;
- ASR transcript can be normalized and compared.

### ASR fidelity

Normalize carefully for:

- punctuation;
- numbers;
- acronyms;
- names;
- units;
- locale-specific spelling;
- pronunciation variants.

WER is diagnostic, not a complete naturalness measure. A good ASR result does not prove good prosody.

### Human/semantic audio checks

Escalate suspicious scenes for:

- robotic cadence;
- awkward emphasis;
- mispronounced technical terms;
- unnatural pauses;
- scene-to-scene voice inconsistency;
- inappropriate locale/accent.

## 10. Visual and composition quality

The visual evaluator must see the actual selected frames or video, not only the text plan.

Check:

- visual supports the narration’s intended meaning;
- specific entities are not replaced by misleading generic visuals;
- visual does not imply an unsupported action or causal relationship;
- required visual elements appear;
- visual repetition is controlled;
- text is readable and inside safe areas;
- transitions do not create unintended semantic or technical defects;
- generated/stock media provenance is preserved.

Use targeted frame sampling around cuts, transitions, overlays, detected anomalies, and scene boundaries in addition to evenly spaced samples.

## 11. Gold set and evaluator harness

### Gold example sources

1. deterministic invalid fixtures;
2. controlled defect injection;
3. real pipeline outputs;
4. human-reviewed examples;
5. disputed/ambiguous examples whose expected action is `HUMAN_REVIEW`.

Controlled defects include:

- changed numeric claim;
- removed source excerpt;
- unsupported causal phrase;
- omitted TTS sentence;
- mispronounced name;
- irrelevant visual;
- misleading entity visual;
- caption timing shift;
- black/frozen frame;
- A/V drift;
- missing asset;
- invalid license metadata.

### Example record

```json
{
  "example_id": "script_fact_001",
  "capability": "claim_evidence_verification",
  "input_artifact_ids": ["script_01", "evidence_01"],
  "expected": {
    "decision": "FAIL",
    "failure_codes": ["NUMERIC_CONTRADICTION"],
    "severity": "MAJOR"
  },
  "label_source": "controlled_defect",
  "review_status": "VERIFIED",
  "split": "development"
}
```

Use `VERIFIED`, `PROVISIONAL`, and `DISPUTED` label statuses. Only verified labels should support definitive benchmark claims.

### Reference benchmarks and metric scope

Existing metrics are building blocks, not a replacement for the pipeline's own
gold set:

| Metric/benchmark | Use here | Do not use it for |
|---|---|---|
| [VMAF](https://github.com/Netflix/vmaf) | Full-reference encoded-video/perceptual degradation when a trusted aligned reference exists | Semantic correctness or a no-reference generated-video gate |
| [VBench](https://arxiv.org/abs/2311.17982) and [VBench-2.0](https://arxiv.org/abs/2502.09552) | Prompt-specific dimensions for generated-video benchmarking and evaluator design | One aggregate publication score for an arbitrary production cut |
| [FVD](https://arxiv.org/abs/1812.01717) | Distribution-level comparison of generated-video systems with fixed datasets/seeds | Acceptance of one individual video |
| [DNSMOS](https://github.com/microsoft/DNS-Challenge) and [VoiceMOS](https://arxiv.org/abs/2609.13792) | Non-intrusive or learned speech-quality screening and model/provider comparison | Definitive pronunciation, prosody, or editorial acceptance |
| [CLIPScore](https://arxiv.org/abs/2104.08718) | Image/text or frame/text relevance ranking and anomaly detection | Entity truth, rights, causal correctness, or factuality |
| [LPIPS](https://richzhang.github.io/PerceptualSimilarity/) | Learned perceptual difference when a reference image/frame exists | Semantic relevance without a reference |
| [BERTScore](https://arxiv.org/abs/1904.09675) | Text similarity and revision/comparison diagnostics | Claim entailment or factual correctness by itself |

The benchmark date, implementation version, model weights, preprocessing, and
threshold calibration must be persisted with every result. A benchmark score
without its input protocol is not reproducible evidence.

### Evaluation metrics

- false-pass rate;
- false-reject rate;
- defect recall by severity;
- precision of repair recommendation;
- human/judge agreement;
- abstention/escalation rate;
- incremental value of each evaluator;
- latency and cost;
- repeat-failure rate;
- cost per accepted artifact/video.

Keep development and holdout examples separate. Do not tune a judge repeatedly against the holdout set.

## 12. Model-tier policy

Use capability tiers rather than fixed brand names:

| Tier | Use |
|---|---|
| Economical/small | extraction, narrow classification, routine semantic match, schema repair |
| Strong/medium | nuanced editorial judgment, evidence reasoning, multimodal exceptions |
| Frontier/high-capability | high-impact ambiguity, disagreement, complex multimodal adjudication, sampled audits |

The router should choose the least expensive eligible tier that meets the measured false-pass requirement. A stronger model is not automatically an independent judge if it shares the same blind spots or evidence omissions.

### 12.1 Threshold calibration and the meaning of “good enough”

There is no universal correct threshold for WER, VMAF, CLIPScore, DNSMOS,
LPIPS, an LLM score, or any other learned measurement. A threshold is an
operating point selected for one metric version, artifact population, domain,
channel, locale, and risk policy.

The threshold process is:

```text
verified labels and defect taxonomy
        ↓
development/calibration set
        ↓
select operating point using risk and cost
        ↓
freeze threshold and evaluator versions
        ↓
evaluate once on untouched holdout set
        ↓
approve, revise, or retain human review
```

Do not choose a threshold from the mean score of the gold set. A good threshold
must distinguish valid and defective examples, protect against serious
false-passes, and keep false-rejection/regeneration cost within policy.

#### Dataset split and label requirements

The benchmark must contain both known-good and known-defective examples. Split
by topic, episode, source, scene, provider, and near-duplicate family so that a
slightly modified copy cannot appear in both calibration and holdout sets.

Use at least:

```text
development/calibration set  - choose thresholds and tune prompts
holdout set                  - final untouched measurement
challenge set                - adversarial and out-of-distribution cases
production audit set         - sampled accepted outputs after release
```

Every defect label records severity, expected action, repair scope, label source,
and whether the label is `VERIFIED`, `PROVISIONAL`, or `DISPUTED`. Critical
defect examples may be deliberately oversampled for calibration, but reported
production prevalence and deployment estimates must remain separate.

#### Threshold policy by evaluator kind

| Evaluator | Threshold rule |
|---|---|
| `DETERMINISTIC` | Use the contract or media-profile invariant. Required integrity failures have zero tolerance unless the profile explicitly defines a tolerance. |
| `SPECIALIZED` continuous metric | Sweep thresholds on the development set, compute confusion/cost metrics, choose an operating point, then freeze it before holdout evaluation. |
| `SEMANTIC` score/probability | Use three zones: automatic pass, escalation/review, and regenerate/fail. Calibrate probability-like outputs against verified human labels; arbitrary judge scores are ranking signals until calibrated. |
| `HUMAN` | Do not replace the decision with a numeric threshold. Define reviewer instructions, required evidence, quorum/adjudication, and an audit rule. |

For a metric where higher is better:

```text
score >= pass_threshold       → PASS
review_threshold <= score < pass_threshold
                               → HUMAN_REVIEW or stronger evaluator
score < review_threshold      → REGENERATE or FAIL
```

For a defect metric where lower is better, reverse the comparisons. The gray
zone is intentional: uncertainty should create an explicit review/escalation,
not an accidental pass.

#### Risk and cost objective

Select the threshold using an explicit cost matrix:

```text
expected_cost(t)
  = false_pass_cost(t)
  + false_reject_cost(t)
  + human_review_cost(t)
  + regeneration_cost(t)
  + delay_or_publication_cost(t)
```

For a material finance claim or a serious audio omission:

```text
false_pass_cost >>> false_reject_cost
```

The threshold should therefore be conservative and send borderline cases to
human review. For a minor pacing preference, false rejection may cost more than
false acceptance, so the metric may be used for ranking rather than blocking.

#### Initial fast-slice policy hypotheses

These are starting targets for the software-engineering explainer. They are not
universal defaults and must be confirmed by the gold-set results:

| Risk | Initial policy hypothesis |
|---|---|
| Critical deterministic defect | Zero tolerance: a known violation blocks acceptance |
| Critical semantic defect | No automatic pass until the critical false-pass target is demonstrated; otherwise escalate to human review |
| Major semantic defect | Target high defect recall and a bounded false-pass rate; the domain profile sets the exact target |
| Minor/editorial preference | Use for ranking, repair suggestion, or audit before making it a hard gate |
| Final publication | Human approval remains mandatory regardless of evaluator score |

For a critical semantic gate, an initial target may be a false-pass rate at or
below 1% with a one-sided 95% confidence bound, provided the holdout contains
enough independent critical cases. If the set is too small to support that
claim, the system must not auto-pass the case; it should escalate and collect
more labels.

If zero false-passes are observed among `n` independent critical examples, the
approximate one-sided 95% upper bound for the true false-pass rate is:

```text
1 - 0.05 ** (1 / n)
```

Illustrative planning values:

| Independent critical examples | Approximate upper bound with zero observed false-passes |
|---:|---:|
| 100 | 2.95% |
| 300 | 0.99% |
| 500 | 0.60% |

These bounds are only meaningful when examples are genuinely independent and
represent the deployment population. Repeated variants of one scene do not
provide the same evidence as independent topics, sources, voices, or episodes.

#### Definition of “good enough”

A metric is ready for automatic gating only when all of these are true:

1. It measures the intended property rather than a convenient proxy.
2. Its preprocessing, evaluator version, and threshold are reproducible.
3. The threshold was chosen on development data and evaluated on untouched
   holdout data.
4. Critical false-pass risk is below the declared policy target with uncertainty
   reported.
5. Relevant domains, locales, voices, providers, and artifact lengths are
   represented or explicitly excluded from scope.
6. Its abstention/escalation behavior is defined.
7. Its repair-scope recommendation is measured, not assumed.
8. Its cost and latency are justified by the defects it catches.
9. Known blind spots have a stronger evaluator or human-review path.

If these conditions are not met, the metric may still be used for ranking,
triage, anomaly detection, candidate selection, or review prioritization, but
not as an automatic acceptance gate.

#### Threshold record

Persist one versioned threshold record for every gated metric:

```text
metric_id
evaluator_version
model/provider/version
dataset_version
domain_profile_id
channel_profile_id
locale_or_voice_profile
direction                  # higher_is_better or lower_is_better
pass_threshold
review_threshold
critical_false_pass_target
false_reject_target
development_size
holdout_size
challenge_size
holdout_results
confidence_interval
known_blind_spots
approved_by
approved_at
review_due_at
```

#### Recalibration triggers

Recalibrate when any of these changes:

- evaluator code, model weights, prompt, rubric, or preprocessing;
- provider, voice, locale, channel, or domain profile;
- artifact duration, resolution, or media format distribution;
- critical defect taxonomy;
- observed production false-pass or human-disagreement rate;
- accepted-output audit discovers a new blind spot.

Do not silently change a threshold. A threshold change creates a new policy
version and should be evaluated on the same holdout protocol before promotion.

## 13. Escalation policy

Escalate when:

- confidence is low;
- evidence is missing or conflicting;
- a material claim is unresolved;
- evaluators disagree;
- score is close to threshold;
- defect severity is high;
- input is outside the evaluator’s validated scope;
- the evaluator/model/prompt is new;
- an accepted-output audit samples the result.

Escalation may mean retrieving evidence, running a specialized measurement, using a stronger judge, regenerating, or requesting a human. It should not reflexively mean another LLM call.

## 14. Repair mapping

| Failure code | Preferred repair scope |
|---|---|
| `QUALITY.SCHEMA_INVALID` | script artifact |
| `QUALITY.UNSUPPORTED_CLAIM` | claim/script scene |
| `QUALITY.NUMERIC_CONTRADICTION` | claim/script scene and descendants |
| `QUALITY.TTS_OMISSION` | audio scene and descendants |
| `QUALITY.TTS_PRONUNCIATION` | audio scene and descendants |
| `QUALITY.VISUAL_MISMATCH` | shot/asset and descendants |
| `QUALITY.MISSING_ASSET` | asset/shot and descendants |
| `QUALITY.CAPTION_OVERFLOW` | layer/scene composition |
| `MEDIA.TIMELINE_INVALID` | composition and render descendants |
| `MEDIA.RENDER_CORRUPT` | affected render chunk |
| `MEDIA.AUDIO_VIDEO_DRIFT` | assembly/master |
| `RIGHTS.LICENSE_UNCERTAIN` | asset replacement or human review |
| `QUALITY.REPEATED_FAILURE` | human review or policy failure |

## 15. QC storage and caching

Evaluation caching is safe only when the key includes all evaluation-relevant inputs:

```text
target artifact IDs and hashes
+ evaluator version
+ rubric version
+ model/provider version
+ relevant configuration hash
+ evidence artifact hashes
```

Reuse evaluations for unchanged artifacts. Invalidate them when any relevant input or evaluator/rubric version changes.

Preserve metadata and evaluation records longer than expensive intermediate binaries.

## 16. Initial quality implementation

The first quality package should implement:

1. schema/contract validators;
2. artifact/reference integrity;
3. source/claim/reference integrity;
4. audio decode/duration/loudness/ASR checks;
5. composition timeline checks;
6. render decode/profile/frame checks;
7. one narrow script/evidence or visual-alignment semantic evaluator;
8. gate policy and repair mapping;
9. human-review persistence;
10. evaluator fixture harness.

Do not implement a large judge matrix without a benchmark harness.

## 17. Quality operations and audits

Run random audits of outputs that passed inexpensive checks. Otherwise the system only learns about failures already detected by its first layer.

For each evaluator/model/prompt/rubric change:

1. run the development set;
2. run the holdout set;
3. inspect serious false passes;
4. compare cost/latency/escalation;
5. shadow-run on real outputs;
6. canary if policy permits;
7. retain rollback version;
8. record the production decision.

## 18. Quality checklist for every new stage

- [ ] What is the artifact being judged?
- [ ] Which properties are deterministic?
- [ ] Which specialized measurements exist?
- [ ] What narrow semantic question remains?
- [ ] What evidence must the evaluator receive?
- [ ] Which failures are hard gates?
- [ ] What is the repair scope?
- [ ] What is the escalation condition?
- [ ] Which model tier is the starting hypothesis?
- [ ] What gold examples and injected defects exist?
- [ ] How are false passes measured?
- [ ] How are results cached and invalidated?
- [ ] Which human decision is required?
