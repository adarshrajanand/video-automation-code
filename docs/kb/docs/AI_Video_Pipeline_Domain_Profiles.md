# AI Video Automation Pipeline — Domain and Channel Profiles

**Status:** Canonical policy design

**Purpose:** Make finance, software engineering, mathematics/physics, entertainment, and future channels use one platform while enforcing domain-appropriate quality and risk rules.

## 1. Profile model

```text
SystemPolicy
  ↓
DomainProfile
  ↓
ChannelProfile
  ↓
WorkflowDefinition
  ↓
RunOverrides
  ↓
EffectiveConfig
```

Profiles configure behavior. They do not fork the workflow engine, artifact graph, event model, renderer contract, or publishing infrastructure.

Every policy ID referenced by a profile resolves to a versioned, typed policy
document. The initial policy families are `SourcePolicy`, `ClaimPolicy`,
`QualityProfile`, `HumanReviewPolicy`, `AssetPolicy`, `BrandProfile`,
`VoiceProfile`, and `PublishingPolicy`. Unknown policy IDs, incompatible
versions, or policy payloads that cannot be validated are configuration errors;
an agent must not invent an untyped policy shape at runtime.

### 1.1 Deterministic merge semantics

Profile resolution is not an informal dictionary merge. The resolver applies layers in order and records the source version of every effective field:

1. scalar values: later layer replaces the earlier value;
2. maps: keys merge recursively unless the field declares replacement;
3. lists: replace by default; fields that support additive behavior declare it explicitly;
4. policy IDs: later layers may select a stricter compatible policy, never a weaker system policy;
5. `SystemPolicy.non_overridable_fields` cannot be changed by domain, channel, or run overrides;
6. human approval, data-classification restrictions, prohibited-content rules, and hard budget caps are non-overridable unless a new system policy version is loaded;
7. conflicting profile versions or unknown fields fail resolution rather than being ignored.

The result is an immutable `EffectiveConfig` snapshot with a canonical hash and source map. A run override can request a different target duration or number of variants, but cannot disable a required human gate or authorize a provider outside system policy.

Profile requirements affect topology through one of two explicit mechanisms:

1. a profile selects a separately validated `WorkflowDefinition`; or
2. a conditional `StageNode.enabled_when` has a declared alternate input path.

Removing a stage from `required_stages` does not by itself remove a node from a
workflow. A profile is invalid if a required stage is unreachable, if an enabled
node has an unavailable dependency output, or if disabling a stage leaves a
downstream selector without a valid input.

## 2. Shared profile contract

```yaml
schema_version: domain-profile.v1
profile_id: software_engineering_explainer_v1
version: "1.0"
content_mode: factual_explainer
default_locale: en-US
required_stages:
  - research
  - script_generation
  - visual_planning
  - speech_generation
   - composition
   - rendering
   - assembly
claim_policy_id: technical_claims_v1
source_policy_id: technical_sources_v1
quality_profile_id: software_explainer_high_bar_v1
human_review_policy_id: software_human_review_v1
asset_policy_id: mixed_media_v1
```

A `ChannelProfile` adds:

- audience;
- tone;
- target duration;
- visual grammar;
- brand assets;
- voice;
- pacing;
- title/thumbnail policy;
- output platforms;
- scheduling policy.

## 3. Shared content-mode concepts

Claims use explicit types:

```text
FACT
INFERENCE
OPINION
SPECULATION
FICTION
```

The profile decides which types require evidence. This avoids assuming every narrative sentence is a factual claim while still protecting consequential content.

## 4. Software engineering profile

### Main risks

- incorrect code;
- stale APIs or version assumptions;
- insecure recommendations;
- untested performance claims;
- misleading architecture diagrams;
- code that works only in an unstated environment.

### Required evidence

- version-pinned official documentation where possible;
- repository/commit references for examples;
- language/runtime version;
- dependency versions;
- reproducible command/environment;
- benchmark conditions for performance claims.

### Deterministic validators

- syntax parsing;
- formatting/linting;
- compilation/build;
- unit/integration tests in a sandbox;
- dependency/license checks;
- security/static analysis where appropriate;
- API/version existence;
- code block references in the script;
- diagram identifiers and references.

### Semantic checks

- code actually supports the narration;
- caveats and constraints are stated;
- security implications are not understated;
- version compatibility is accurate;
- examples are not presented as universal solutions.

### Human review triggers

- security/privacy claims;
- production outage or incident explanations;
- materially misleading benchmark claims;
- unresolved version conflict;
- final publication.

## 5. Finance education profile

### Main risks

- stale or incorrect numbers;
- unsupported causation;
- misleading investment implications;
- missing dates/currency/units;
- overconfident forecasts;
- source conflicts;
- regulatory/compliance concerns.

### Required evidence

- source snapshot and retrieval timestamp;
- as-of date for time-sensitive claims;
- primary/secondary source class;
- exact excerpt/figure reference;
- currency and unit normalization;
- source conflict record;
- clear distinction between fact, estimate, opinion, and scenario.

### Deterministic validators

- numeric/unit matching;
- date and freshness policy;
- arithmetic and percentage calculations;
- currency conversion metadata;
- source/excerpt existence;
- claim/evidence completeness;
- required caveat fields;
- prohibited advice/promise patterns where policy defines them.

### Semantic checks

- evidence entails the material claim;
- correlation is not presented as causation;
- uncertainty is proportionate;
- competing evidence is not omitted misleadingly;
- the narrative does not imply personalized advice;
- the headline/thumbnail does not overpromise.

### Human review triggers

- material financial claims;
- investment-return assertions;
- forecasts or recommendations;
- unresolved source conflict;
- outdated data near publication;
- legal/compliance uncertainty;
- final publication.

The initial fast validation should not publish finance content, but the profile and QC contract should be designed now so finance does not require a platform rewrite.

## 6. Mathematics and physics profile

### Main risks

- algebraic/derivation errors;
- incorrect assumptions;
- unit or dimensional inconsistency;
- numerical instability;
- incorrect physical interpretation;
- source attribution errors.

### Deterministic/specialized validators

- symbolic simplification;
- numerical substitution;
- dimensional analysis;
- unit conversion;
- range/boundary checks;
- simulation comparison;
- plot/data consistency;
- equation rendering and symbol references.

### Semantic checks

- assumptions are explicit;
- approximation scope is stated;
- analogy does not replace the derivation;
- the visual explanation matches the equation/model;
- uncertainty and limits are not hidden.

### Human review triggers

- novel or disputed interpretation;
- high-impact scientific claim;
- evaluator disagreement;
- unsupported simplification;
- final publication for specialized audiences.

## 7. Entertainment profile

### Main differences

Research and claim evidence may be optional for fictional or opinion-led content. The same system still needs:

- content mode and fiction markers;
- rights/IP provenance;
- continuity and character/asset consistency;
- narrative promise and pacing;
- audio/visual technical checks;
- safety and platform policy;
- human publication approval.

### Deterministic/specialized validators

- scene/shot continuity metadata;
- asset identity consistency;
- timing and captions;
- rights/provenance;
- duplicate/reuse patterns;
- render integrity.

### Semantic checks

- narrative coherence;
- audience fit;
- emotional/pacing intent;
- visual continuity;
- misleading packaging;
- policy/safety concerns.

The graph may skip research or claim-ledger substages, but it should not bypass artifact lineage or quality gates.

## 8. Channel profile example

```yaml
schema_version: channel-profile.v1
profile_id: us_en_software_explainer_v1
version: "1.0"
domain_profile_id: software_engineering_explainer_v1
locale: en-US
audience: adult_software_engineers
target_duration_seconds: 720
output_profile_ids: [landscape_1080p_30_v1, vertical_1080p_30_v1]
brand_profile_id: engineering_dark_v1
voice_profile_id: calm_precise_en_us_v1
publishing_policy_id: youtube_instagram_human_approval_v1
```

## 9. Profile validation

Before a run starts, validate:

- required stages are present;
- all configured quality gates exist;
- source policy is compatible with provider data policy;
- output profiles are supported;
- target duration is within stage/render limits;
- human-review requirements cannot be disabled by a run override;
- budget limits are no weaker than system policy;
- locale has compatible TTS/ASR/font providers;
- prohibited content rules are valid.

## 10. Localization

Localization branches from an approved canonical content package.

Preserve:

- source claim IDs;
- translation version;
- localized narration;
- voice/pronunciation policy;
- units/date/currency transformations;
- captions and timing;
- localized visual text;
- locale-specific QC.

Do not silently translate and alter the factual meaning of a claim. A localized claim change should create a new artifact and quality evaluation.

## 11. Profile implementation order

1. generic `factual_explainer` base;
2. software-engineering validation profile for the fast plan;
3. finance high-review profile;
4. mathematics/physics technical profile;
5. entertainment narrative profile;
6. channel-specific variants;
7. localized profiles.

## 12. Profile tests

- [ ] domain-required stages cannot be disabled accidentally;
- [ ] finance material claims trigger human review;
- [ ] software code examples invoke configured validators;
- [ ] math/physics checks require units/assumptions where policy says so;
- [ ] entertainment can omit research without weakening technical/provenance gates;
- [ ] channel overrides cannot exceed system budget;
- [ ] localization preserves claim lineage;
- [ ] profile changes produce a new effective configuration hash.
