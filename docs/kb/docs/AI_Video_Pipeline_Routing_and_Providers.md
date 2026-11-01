# AI Video Automation Pipeline — Routing and Providers

**Status:** Canonical capability/routing design

**Purpose:** Define how stages request capabilities, how eligible implementations are selected, and how provider/model choices can evolve without changing stage code.

## 1. Separate decisions

Do not build one opaque super-router. These are separate decisions:

```text
1. Workflow readiness: may this stage run?
2. Capability routing: which implementation/provider/model can do it?
3. Resource placement: where should it execute?
4. Budget authorization: is the expected spend allowed?
5. Quality gating: is the result acceptable?
```

They may share context and policy data but require separate contracts and audit records.

## 2. Capability boundary

A stage requests a capability rather than naming a vendor:

```python
class Capability(Protocol):
    capability_id: str
    operation_version: str

    def execute(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
    ) -> CapabilityResult:
        ...
```

Examples:

```text
structured_text_generation
claim_evidence_verification
speech_generation
speech_recognition
image_generation
video_generation
visual_asset_search
visual_alignment_evaluation
audio_quality_evaluation
composition_render
technical_media_validation
publishing
```

The capability contract is stable even if the implementation is a direct API call, local model, tool-using agent, subprocess, or remote service.

## 3. Provider registry

The registry is data, not a large conditional statement.

```yaml
providers:
  - id: local_speech_example
    implementation: adapters.speech_generation.local_example
    capabilities: [speech_generation]
    implementation_version: 1.0.0
    locales: [en-US]
    quality_class: experimental
    cost_class: local
    data_classes: [PUBLIC, INTERNAL]
    supports_idempotency: true
    supports_reconciliation: false
    resource_requirements:
      cpu: 4
      ram_gb: 8
      vram_gb: 0
```

A provider record must include enough information to determine eligibility:

- capability support;
- supported features/locales;
- data policy/classification;
- implementation/config version;
- quality evidence/reference benchmark;
- quota state/source/refresh time;
- health observations;
- cost model;
- latency expectations;
- idempotency/reconciliation behavior;
- resource requirements.

## 4. Routing algorithm

```text
candidate providers
    ↓
capability compatibility
    ↓
hard feature constraints
    ↓
locale/language
    ↓
data-policy eligibility
    ↓
credentials/configuration
    ↓
minimum validated quality
    ↓
health and availability
    ↓
quota and budget authorization
    ↓
previous-result constraints
    ↓
policy scoring
    ↓
primary decision + explicit fallback chain
```

Hard constraints remove candidates. Scores must not compensate for a hard violation.

### Initial router behavior

The first router should be intentionally simple:

- one configured provider per capability;
- fake providers for tests;
- explicit eligibility checks;
- paid fallback disabled unless policy enables it;
- routing decision persisted;
- normalized provider error returned.

Do not implement learned routing or complex health scoring before a benchmark demonstrates the need.

## 5. Budget and quota policy

Budget policy must distinguish:

- system hard cap;
- monthly cap;
- run cap;
- stage cap;
- optional evaluation budget;
- reserved versus actual spend;
- free-tier quota versus paid spend;
- provider-reported cost versus estimated cost.

When quota is exhausted, valid actions are:

1. another eligible provider;
2. defer until reset;
3. reduce optional work if policy permits;
4. pause and notify;
5. explicitly authorized paid fallback within remaining budget;
6. fail with a clear policy reason.

The system must never silently switch to paid execution.

## 6. Provider adapters

An adapter owns:

- SDK/API invocation;
- authentication/configuration;
- provider request/response translation;
- provider operation ID;
- provider-specific retries where safe;
- provider status/reconciliation;
- usage/cost normalization;
- sensitive payload handling;
- normalized errors.

An adapter must not:

- update workflow state;
- bypass quality gates;
- select unrelated providers;
- publish without a capability request;
- write arbitrary artifacts outside the ArtifactStore protocol.

## 7. External side-effect protocol

Before a provider call:

1. create `CapabilityExecution` and `ProviderInvocation` records;
2. calculate stable idempotency key;
3. create or reuse `IdempotencyRecord`;
4. reserve estimated budget if required, atomically against every applicable scope;
5. persist selected route and data policy;
6. call adapter.

After a successful call:

1. retain provider operation ID;
2. normalize usage/cost;
3. validate result;
4. store immutable artifacts;
5. commit result, idempotency status, and actual cost;
6. settle or release the budget reservation in the same authoritative transaction.

After timeout:

1. mark provider invocation `UNKNOWN`;
2. query status by operation/idempotency key if supported;
3. inspect local artifacts;
4. leave the budget reservation in `UNKNOWN` until the outcome is resolved;
5. retry only under explicit policy.

## 8. Resource broker

Resource placement is an extension point with this conceptual contract:

```python
class ResourceBroker(Protocol):
    def place(
        self,
        workload: WorkloadRequirements,
        constraints: ResourceConstraints,
        budget: BudgetContext,
    ) -> ResourceAssignment:
        ...
```

Consider:

- CPU/RAM/VRAM;
- startup/model-load time;
- expected useful runtime;
- artifact transfer size/cost;
- interruption tolerance;
- network/data restrictions;
- concurrency/quotas;
- total cost including retries;
- whether the workload is local, persistent CPU, burst GPU, or notebook batch.

Initial resource placement can be a static local assignment as described in the
[Local Infrastructure Profile](AI_Video_Pipeline_Local_Infrastructure_Profile.md).
Keep the decision separate so a future render worker or GPU model worker does
not alter stage contracts.

## 9. Data policy

For each provider, record:

- permitted data classifications;
- retention/training terms;
- regional constraints;
- raw request/response logging rules;
- credential scope and rotation;
- whether source snapshots may be sent;
- whether financial/private content is allowed.

Unknown terms mean the provider is ineligible for the affected data classification until reviewed.

## 10. Benchmarking

Benchmark per capability and task, not per vendor reputation.

### Generation capabilities

Measure:

- schema validity;
- semantic quality;
- factual support;
- revision success;
- diversity where relevant;
- latency;
- cost;
- failure/retry rate.

### Evaluation capabilities

Measure:

- false-pass rate;
- false-reject rate;
- severe defect recall;
- abstention rate;
- human agreement;
- incremental value;
- latency/cost.

### Media capabilities

Measure:

- output integrity;
- timing accuracy;
- perceptual quality;
- startup/model load;
- useful runtime;
- transfer time;
- GPU utilization;
- cost per accepted artifact.

Record benchmark date and provider terms. Prices and quotas are mutable data, not architecture guarantees.

## 11. Fallback chains

Fallback chains are explicit and bounded:

```yaml
capability: speech_generation
policy_version: speech-routing-v1
fallback:
  - local_speech_example
  - hosted_speech_example
paid_fallback_authorized: false
on_exhaustion: PAUSE
```

A fallback may be rejected if it changes voice identity, language, data policy, quality class, or artifact semantics beyond what the stage policy allows.

## 12. Provider health

Health observations may include:

- recent success/failure rate;
- timeout rate;
- rate-limit errors;
- observed latency;
- quota remaining/confidence;
- provider status;
- stale credential/configuration;
- quality regression from benchmark or production audits.

Health data should influence eligibility or scoring only after the observation semantics and stale-data behavior are defined.

## 13. Routing records

Every route persists:

- capability;
- implementation/provider/model;
- provider config hash;
- policy version;
- candidate exclusions;
- reason codes;
- fallback chain;
- budget/usage context;
- attempt number;
- data classification;
- timestamp.

This makes cost and quality analysis possible after a model/provider changes.

## 14. Initial provider rollout

1. fake adapter for every capability used by tests;
2. one real text-generation adapter;
3. one real TTS adapter;
4. local/fixture media adapter;
5. one ASR/evaluation implementation;
6. benchmark alternatives;
7. add router candidates only when an alternative has evidence;
8. enable paid fallbacks only through explicit configuration.

## 15. Provider test checklist

- [ ] adapter normalizes success and all expected failure classes;
- [ ] secrets are not logged;
- [ ] request fingerprint is stable;
- [ ] idempotency key is reused for safe retry;
- [ ] provider operation ID is stored;
- [ ] timeout enters unknown/reconciliation path;
- [ ] usage/cost is persisted;
- [ ] data policy is checked before the call;
- [ ] paid fallback policy is enforced;
- [ ] malformed output is rejected before artifact acceptance;
- [ ] provider can be replaced without stage import changes.
