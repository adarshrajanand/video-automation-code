# Contract Field Atlas

Generated from the live Pydantic contract registry. It lists every public
contract model, every field, its type, whether it is required, and its
default. The `Durable mapping` line shows the SQLite table and extracted
columns used by the repository layer, when the model has one.

- Contract models: **108**
- Fields: **1004**
- Repository-backed models: **33**

Regenerate from the repository root with:

```bash
uv run python scripts/generate_contract_atlas.py > CONTRACT_FIELD_ATLAS.md
```

> `schema_version` is a required literal discriminator and is shown once
> per model rather than repeated in the field table.

## Contents

- [Base and error models](#base-and-error-models) — 1 models
- [Configuration and run overrides](#configuration-and-run-overrides) — 2 models
- [Workflow definitions](#workflow-definitions) — 5 models
- [Runs, stages, attempts, manifests, recovery policies](#runs-stages-attempts-manifests-recovery-policies) — 8 models
- [Jobs and leases](#jobs-and-leases) — 2 models
- [Capability requests, results, execution and budget records](#capability-requests-results-execution-and-budget-records) — 8 models
- [Routing, resource placement, provider invocation](#routing-resource-placement-provider-invocation) — 6 models
- [Immutable artifacts, pointers, invalidation](#immutable-artifacts-pointers-invalidation) — 5 models
- [Quality checks, evaluations, gates, repair](#quality-checks-evaluations-gates-repair) — 7 models
- [Human review and publication](#human-review-and-publication) — 4 models
- [Events, outbox, inbox](#events-outbox-inbox) — 3 models
- [Policy and domain/channel profiles](#policy-and-domainchannel-profiles) — 4 models
- [Content package hierarchy and composition references](#content-package-hierarchy-and-composition-references) — 8 models
- [Renderer-neutral composition and manifests](#renderer-neutral-composition-and-manifests) — 12 models
- [Research, script, speech, and timing content](#research-script-speech-and-timing-content) — 11 models
- [Typed payloads exchanged with capabilities](#typed-payloads-exchanged-with-capabilities) — 22 models
- [Vocabulary values](#vocabulary-values)
- [Repository-backed models](#repository-backed-models)

## Base and error models

### `NormalizedError`

`schema_version`: `normalized-error.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `code` | `<enum 'FailureCode` | yes | required |
| `category` | `<enum 'FailureCategory` | yes | required |
| `retryable` | `bool` | yes | required |
| `reconciliation_required` | `bool` | no | `False` |
| `severity` | `<enum 'Severity` | no | `MAJOR` |
| `provider_status` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `message` | `str` | yes | required |
| `safe_details` | `ExtensionObject` | no | `PydanticUndefined` |

## Configuration and run overrides

### `RunOverrides`

`schema_version`: `run-overrides.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `locale` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `target_duration_seconds` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=1)])]]` | no | `null` |
| `variant_count` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=1)])]]` | no | `null` |
| `max_cost_minor` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=0)])]]` | no | `null` |
| `enabled_optional_stages` | `list[vocabularies.StageName]` | no | `PydanticUndefined` |
| `output_profile_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]] | None` | no | `null` |
| `quality_profile_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |

### `EffectiveConfig`

`schema_version`: `effective-config.v1`

**Durable mapping:** `effective_configs` (repository `EffectiveConfigRepository` in `execution.py`); keys `effective_config_id`; extracted columns `effective_config_id`, `config_hash`, `workflow_id`, `workflow_version`, `system_policy_version`, `domain_profile_id`, `domain_profile_version`, `channel_profile_id`, `channel_profile_version`, `snapshot_artifact_id`.

| Field | Type | Required | Default |
|---|---|---|---|
| `effective_config_id` | `str` | yes | required |
| `system_policy_version` | `str` | yes | required |
| `domain_profile_id` | `str` | yes | required |
| `domain_profile_version` | `str` | yes | required |
| `channel_profile_id` | `str` | yes | required |
| `channel_profile_version` | `str` | yes | required |
| `workflow_id` | `str` | yes | required |
| `workflow_version` | `str` | yes | required |
| `run_overrides` | `config.RunOverrides` | yes | required |
| `resolved_values` | `ExtensionObject` | no | `PydanticUndefined` |
| `source_map` | `dict[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)], Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `config_hash` | `str` | yes | required |
| `snapshot_artifact_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |

## Workflow definitions

### `InputSelector`

`schema_version`: `input-selector.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `kind` | `<enum 'InputSelectorKind` | yes | required |
| `dependency_node_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `artifact_types` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `selection_policy` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |

### `ConditionExpression`

`schema_version`: `condition-expression.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `operator` | `<enum 'ConditionOperator` | yes | required |
| `operands` | `list[ConditionOperand]` | no | `PydanticUndefined` |

### `CardinalityPolicy`

`schema_version`: `cardinality.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `mode` | `<enum 'CardinalityMode` | yes | required |
| `count` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=1)])]]` | no | `null` |
| `selection_policy` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `expected_manifest_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |

### `StageNode`

`schema_version`: `stage-node.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `node_id` | `str` | yes | required |
| `stage_name` | `<enum 'StageName` | yes | required |
| `depends_on` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `input_selector` | `workflow.InputSelector` | yes | required |
| `cardinality` | `workflow.CardinalityPolicy` | yes | required |
| `quality_gate_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `recovery_policy_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `enabled_when` | `workflow.ConditionExpression | None` | no | `null` |
| `implementation_version` | `str` | yes | required |

### `WorkflowDefinition`

`schema_version`: `workflow-definition.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `workflow_id` | `str` | yes | required |
| `version` | `str` | yes | required |
| `nodes` | `list[workflow.StageNode]` | yes | required |
| `policy_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |

## Runs, stages, attempts, manifests, recovery policies

### `WorkflowRun`

`schema_version`: `workflow-run.v1`

**Durable mapping:** `workflow_runs` (repository `WorkflowRunRepository` in `execution.py`); keys `run_id`; extracted columns `run_id`, `run_key`, `workflow_id`, `workflow_version`, `effective_config_id`, `effective_config_hash`, `status`, `content_package_id`, `created_at`, `updated_at`.

| Field | Type | Required | Default |
|---|---|---|---|
| `created_at` | `datetime.datetime` | yes | required |
| `updated_at` | `Optional[Annotated[datetime.datetime, BeforeValidator(func=<function _reject_numeric_datetime at >, json_schema_input_type=PydanticUndefined), AfterValidator(func=<function _ensure_utc at >)]]` | no | `null` |
| `run_id` | `str` | yes | required |
| `run_key` | `str` | yes | required |
| `workflow_id` | `str` | yes | required |
| `workflow_version` | `str` | yes | required |
| `effective_config_id` | `str` | yes | required |
| `effective_config_hash` | `str` | yes | required |
| `status` | `<enum 'RunStatus` | yes | required |
| `content_package_id` | `str` | yes | required |

### `RunCreateRequest`

`schema_version`: `run-create-request.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `run_key` | `str` | yes | required |
| `workflow_id` | `str` | yes | required |
| `workflow_version` | `str` | yes | required |
| `content_package_id` | `str` | yes | required |
| `effective_config_overrides` | `config.RunOverrides` | yes | required |
| `duplicate_policy` | `<enum 'DuplicatePolicy` | no | `RETURN_EXISTING` |

### `StageInstance`

`schema_version`: `stage-instance.v1`

**Durable mapping:** `stage_instances` (repository `StageInstanceRepository` in `execution.py`); keys `stage_instance_id`; extracted columns `stage_instance_id`, `run_id`, `node_id`, `logical_item_key`, `execution_status`, `acceptance_status`, `quality_gate_id`, `quality_gate_result_id`, `expected_input_manifest_id`, `active_attempt_id`, `created_at`, `updated_at`.

| Field | Type | Required | Default |
|---|---|---|---|
| `created_at` | `datetime.datetime` | yes | required |
| `updated_at` | `Optional[Annotated[datetime.datetime, BeforeValidator(func=<function _reject_numeric_datetime at >, json_schema_input_type=PydanticUndefined), AfterValidator(func=<function _ensure_utc at >)]]` | no | `null` |
| `stage_instance_id` | `str` | yes | required |
| `run_id` | `str` | yes | required |
| `node_id` | `str` | yes | required |
| `logical_item_key` | `str` | yes | required |
| `execution_status` | `<enum 'StageExecutionStatus` | yes | required |
| `acceptance_status` | `<enum 'AcceptanceStatus` | yes | required |
| `quality_gate_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `quality_gate_result_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `expected_input_manifest_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `active_attempt_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `accepted_output_artifact_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |

### `StageAttempt`

`schema_version`: `stage-attempt.v1`

**Durable mapping:** `stage_attempts` (repository `StageAttemptRepository` in `execution.py`); keys `attempt_id`; extracted columns `attempt_id`, `stage_instance_id`, `attempt_number`, `quality_regeneration_number`, `status`, `worker_id`, `lease_expires_at`, `started_at`, `finished_at`, `failure_code`.

| Field | Type | Required | Default |
|---|---|---|---|
| `attempt_id` | `str` | yes | required |
| `stage_instance_id` | `str` | yes | required |
| `attempt_number` | `int` | yes | required |
| `quality_regeneration_number` | `int` | no | `0` |
| `status` | `<enum 'AttemptStatus` | yes | required |
| `input_artifact_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `output_artifact_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `worker_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `lease_expires_at` | `Optional[Annotated[datetime.datetime, BeforeValidator(func=<function _reject_numeric_datetime at >, json_schema_input_type=PydanticUndefined), AfterValidator(func=<function _ensure_utc at >)]]` | no | `null` |
| `fencing_token` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=1)])]]` | no | `null` |
| `started_at` | `Optional[Annotated[datetime.datetime, BeforeValidator(func=<function _reject_numeric_datetime at >, json_schema_input_type=PydanticUndefined), AfterValidator(func=<function _ensure_utc at >)]]` | no | `null` |
| `finished_at` | `Optional[Annotated[datetime.datetime, BeforeValidator(func=<function _reject_numeric_datetime at >, json_schema_input_type=PydanticUndefined), AfterValidator(func=<function _ensure_utc at >)]]` | no | `null` |
| `failure_code` | `vocabularies.FailureCode | None` | no | `null` |
| `failure_message` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |

### `InputManifest`

`schema_version`: `input-manifest.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `manifest_id` | `str` | yes | required |
| `stage_instance_id` | `str` | yes | required |
| `expected_artifact_slots` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `resolved_artifact_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `expected_count` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=0)])]]` | no | `null` |
| `complete` | `bool` | no | `False` |
| `created_at` | `datetime.datetime` | yes | required |

### `RetryPolicy`

`schema_version`: `retry-policy.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `policy_id` | `str` | yes | required |
| `max_attempts` | `int` | yes | required |
| `initial_backoff_seconds` | `float` | yes | required |
| `max_backoff_seconds` | `float` | yes | required |
| `jitter_ratio` | `float` | yes | required |
| `retryable_categories` | `list[vocabularies.FailureCategory]` | no | `PydanticUndefined` |

### `RecoveryPolicy`

`schema_version`: `recovery-policy.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `policy_id` | `str` | yes | required |
| `retry_policy_id` | `str` | yes | required |
| `on_unknown_outcome` | `<enum 'UnknownOutcomeAction` | yes | required |
| `on_quality_failure` | `<enum 'QualityFailureAction` | yes | required |
| `on_repeated_failure` | `<enum 'RepeatedFailureAction` | yes | required |

### `RecoveryDecision`

`schema_version`: `recovery-decision.v1`

**Durable mapping:** `recovery_decisions` (repository `RecoveryDecisionRepository` in `control.py`); keys `recovery_decision_id`; extracted columns `recovery_decision_id`, `run_id`, `failed_attempt_id`, `action`, `created_at`.

| Field | Type | Required | Default |
|---|---|---|---|
| `recovery_decision_id` | `str` | yes | required |
| `run_id` | `str` | yes | required |
| `failed_attempt_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `action` | `<enum 'RecoveryAction` | yes | required |
| `target_stage_instance_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `target_artifact_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `reason_codes` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `created_at` | `datetime.datetime` | yes | required |

## Jobs and leases

### `Job`

`schema_version`: `job.v1`

**Durable mapping:** `jobs` (repository `JobRepository` in `execution.py`); keys `job_id`; extracted columns `job_id`, `attempt_id`, `queue_name`, `status`, `idempotency_key`, `available_at`, `claimed_by`, `lease_expires_at`, `delivery_count`.

| Field | Type | Required | Default |
|---|---|---|---|
| `job_id` | `str` | yes | required |
| `attempt_id` | `str` | yes | required |
| `queue_name` | `str` | yes | required |
| `status` | `<enum 'JobStatus` | yes | required |
| `idempotency_key` | `str` | yes | required |
| `available_at` | `datetime.datetime` | yes | required |
| `claimed_by` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `lease_expires_at` | `Optional[Annotated[datetime.datetime, BeforeValidator(func=<function _reject_numeric_datetime at >, json_schema_input_type=PydanticUndefined), AfterValidator(func=<function _ensure_utc at >)]]` | no | `null` |
| `delivery_count` | `int` | no | `0` |
| `fencing_token` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=1)])]]` | no | `null` |

### `Lease`

`schema_version`: `lease.v1`

**Durable mapping:** `leases` (repository `LeaseRepository` in `execution.py`); keys `job_id`, `fencing_token`; extracted columns `job_id`, `owner_id`, `fencing_token`, `acquired_at`, `expires_at`, `heartbeat_at`.

| Field | Type | Required | Default |
|---|---|---|---|
| `job_id` | `str` | yes | required |
| `owner_id` | `str` | yes | required |
| `fencing_token` | `int` | yes | required |
| `acquired_at` | `datetime.datetime` | yes | required |
| `expires_at` | `datetime.datetime` | yes | required |
| `heartbeat_at` | `Optional[Annotated[datetime.datetime, BeforeValidator(func=<function _reject_numeric_datetime at >, json_schema_input_type=PydanticUndefined), AfterValidator(func=<function _ensure_utc at >)]]` | no | `null` |

## Capability requests, results, execution and budget records

### `CapabilityRequirements`

`schema_version`: `capability-requirements.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `capability` | `str` | yes | required |
| `required_features` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `locale` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `quality_requirement` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `latency_requirement` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `data_classification` | `str` | no | `PUBLIC` |
| `cost_limit_minor` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=0)])]]` | no | `null` |

### `CapabilityRequest`

`schema_version`: `capability-request.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `capability_execution_id` | `str` | yes | required |
| `capability` | `str` | yes | required |
| `operation_version` | `str` | yes | required |
| `input_artifact_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `payload_fingerprint` | `str` | yes | required |
| `requirements` | `capabilities.CapabilityRequirements` | yes | required |
| `payload` | `ExtensionObject` | no | `PydanticUndefined` |
| `payload_schema_version` | `str` | yes | required |
| `runtime_context` | `ExtensionObject` | no | `PydanticUndefined` |
| `idempotency_key` | `str` | yes | required |

### `ExecutionContext`

`schema_version`: `execution-context.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `run_id` | `str` | yes | required |
| `stage_instance_id` | `str` | yes | required |
| `attempt_id` | `str` | yes | required |
| `effective_config_id` | `str` | yes | required |
| `correlation_id` | `str` | yes | required |
| `timeout_seconds` | `int` | yes | required |
| `allowed_data_classification` | `str` | yes | required |

### `UsageRecord`

`schema_version`: `usage.v1`

**Durable mapping:** `usage_records` (repository `UsageRecordRepository` in `capabilities.py`); keys `usage_id`; extracted columns `usage_id`, `capability_execution_id`, `provider`, `model`, `estimated_cost_minor`, `actual_cost_minor`, `created_at`, `schema_version`, `payload`.

| Field | Type | Required | Default |
|---|---|---|---|
| `provider` | `str` | yes | required |
| `model` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `input_units` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=0)])]]` | no | `null` |
| `output_units` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=0)])]]` | no | `null` |
| `runtime_seconds` | `Optional[Annotated[float, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=0), AllowInfNan(allow_inf_nan=False)])]]` | no | `null` |
| `estimated_cost_minor` | `int` | no | `0` |
| `actual_cost_minor` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=0)])]]` | no | `null` |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `CapabilityResult`

`schema_version`: `capability-result.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `capability_execution_id` | `str` | yes | required |
| `status` | `<enum 'CapabilityResultStatus` | yes | required |
| `artifact_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |
| `usage` | `capabilities.UsageRecord | None` | no | `null` |
| `normalized_error` | `base.NormalizedError | None` | no | `null` |

### `CapabilityExecution`

`schema_version`: `capability-execution.v1`

**Durable mapping:** `capability_executions` (repository `CapabilityExecutionRepository` in `capabilities.py`); keys `capability_execution_id`; extracted columns `capability_execution_id`, `attempt_id`, `capability`, `status`, `idempotency_key`, `request_fingerprint`, `started_at`, `finished_at`.

| Field | Type | Required | Default |
|---|---|---|---|
| `capability_execution_id` | `str` | yes | required |
| `attempt_id` | `str` | yes | required |
| `capability` | `str` | yes | required |
| `operation_version` | `str` | yes | required |
| `implementation_version` | `str` | yes | required |
| `prompt_version` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `rubric_version` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `settings_hash` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', ascii_only=None)]]` | no | `null` |
| `tool_versions` | `dict[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)], Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `request_fingerprint` | `str` | yes | required |
| `idempotency_key` | `str` | yes | required |
| `routing_decision_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `resource_assignment_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `status` | `<enum 'CapabilityExecutionStatus` | yes | required |
| `input_artifact_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `output_artifact_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `started_at` | `Optional[Annotated[datetime.datetime, BeforeValidator(func=<function _reject_numeric_datetime at >, json_schema_input_type=PydanticUndefined), AfterValidator(func=<function _ensure_utc at >)]]` | no | `null` |
| `finished_at` | `Optional[Annotated[datetime.datetime, BeforeValidator(func=<function _reject_numeric_datetime at >, json_schema_input_type=PydanticUndefined), AfterValidator(func=<function _ensure_utc at >)]]` | no | `null` |
| `normalized_error` | `base.NormalizedError | None` | no | `null` |

### `IdempotencyRecord`

`schema_version`: `idempotency-record.v1`

**Durable mapping:** `idempotency_records` (repository `IdempotencyRecordRepository` in `control.py`); keys `idempotency_key`; extracted columns `idempotency_key`, `capability`, `request_fingerprint`, `provider`, `status`, `capability_execution_id`, `provider_invocation_id`, `provider_operation_id`, `created_at`, `completed_at`.

| Field | Type | Required | Default |
|---|---|---|---|
| `idempotency_key` | `str` | yes | required |
| `capability` | `str` | yes | required |
| `operation_version` | `str` | yes | required |
| `request_fingerprint` | `str` | yes | required |
| `input_artifact_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `required_features` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `locale` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `provider` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `status` | `<enum 'IdempotencyStatus` | yes | required |
| `capability_execution_id` | `str` | yes | required |
| `provider_invocation_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `provider_operation_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `result_artifact_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `created_at` | `datetime.datetime` | yes | required |
| `completed_at` | `Optional[Annotated[datetime.datetime, BeforeValidator(func=<function _reject_numeric_datetime at >, json_schema_input_type=PydanticUndefined), AfterValidator(func=<function _ensure_utc at >)]]` | no | `null` |

### `BudgetReservation`

`schema_version`: `budget-reservation.v1`

**Durable mapping:** `budget_reservations` (repository `BudgetReservationRepository` in `control.py`); keys `reservation_id`; extracted columns `reservation_id`, `scope_type`, `scope_id`, `idempotency_key`, `estimated_cost_minor`, `reserved_cost_minor`, `actual_cost_minor`, `status`, `created_at`, `settled_at`.

| Field | Type | Required | Default |
|---|---|---|---|
| `reservation_id` | `str` | yes | required |
| `scope_type` | `<enum 'BudgetScopeType` | yes | required |
| `scope_id` | `str` | yes | required |
| `idempotency_key` | `str` | yes | required |
| `estimated_cost_minor` | `int` | yes | required |
| `reserved_cost_minor` | `int` | yes | required |
| `actual_cost_minor` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=0)])]]` | no | `null` |
| `status` | `<enum 'BudgetReservationStatus` | yes | required |
| `created_at` | `datetime.datetime` | yes | required |
| `settled_at` | `Optional[Annotated[datetime.datetime, BeforeValidator(func=<function _reject_numeric_datetime at >, json_schema_input_type=PydanticUndefined), AfterValidator(func=<function _ensure_utc at >)]]` | no | `null` |

## Routing, resource placement, provider invocation

### `RoutingContext`

`schema_version`: `routing-context.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `capability_request` | `capabilities.CapabilityRequest` | yes | required |
| `effective_config_hash` | `str` | yes | required |
| `provider_health` | `ExtensionObject` | no | `PydanticUndefined` |
| `provider_usage` | `ExtensionObject` | no | `PydanticUndefined` |
| `previous_results` | `list[ExtensionObject]` | no | `PydanticUndefined` |
| `attempt` | `int` | yes | required |
| `budget_remaining_minor` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=0)])]]` | no | `null` |

### `RoutingDecision`

`schema_version`: `routing-decision.v1`

**Durable mapping:** `routing_decisions` (repository `RoutingDecisionRepository` in `capabilities.py`); keys `routing_decision_id`; extracted columns `routing_decision_id`, `capability`, `implementation`, `implementation_version`, `provider`, `model`, `policy_version`, `attempt`, `data_classification`, `created_at`.

| Field | Type | Required | Default |
|---|---|---|---|
| `routing_decision_id` | `str` | yes | required |
| `capability` | `str` | yes | required |
| `implementation` | `str` | yes | required |
| `implementation_version` | `str` | yes | required |
| `provider` | `str` | yes | required |
| `model` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `provider_config_hash` | `str` | yes | required |
| `fallback_chain` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `policy_version` | `str` | yes | required |
| `reason_codes` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `candidate_exclusions` | `list[ExtensionObject]` | no | `PydanticUndefined` |
| `budget_context` | `ExtensionObject` | no | `PydanticUndefined` |
| `usage_context` | `ExtensionObject` | no | `PydanticUndefined` |
| `attempt` | `int` | yes | required |
| `data_classification` | `str` | yes | required |
| `paid_fallback_authorized` | `bool` | no | `False` |
| `created_at` | `datetime.datetime` | yes | required |

### `WorkloadRequirements`

`schema_version`: `workload-requirements.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `cpu_cores` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=1)])]]` | no | `null` |
| `memory_mb` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=1)])]]` | no | `null` |
| `vram_mb` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=1)])]]` | no | `null` |
| `expected_runtime_seconds` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=1)])]]` | no | `null` |
| `required_tools` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `data_classification` | `str` | no | `PUBLIC` |

### `ResourceConstraints`

`schema_version`: `resource-constraints.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `allowed_placement_classes` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `max_runtime_seconds` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=1)])]]` | no | `null` |
| `max_cost_minor` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=0)])]]` | no | `null` |
| `network_required` | `bool` | no | `False` |

### `ResourceAssignment`

`schema_version`: `resource-assignment.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `assignment_id` | `str` | yes | required |
| `placement_class` | `str` | yes | required |
| `worker_pool` | `str` | yes | required |
| `implementation_version` | `str` | yes | required |
| `constraints_hash` | `str` | yes | required |
| `created_at` | `datetime.datetime` | yes | required |

### `ProviderInvocation`

`schema_version`: `provider-invocation.v1`

**Durable mapping:** `provider_invocations` (repository `ProviderInvocationRepository` in `capabilities.py`); keys `invocation_id`; extracted columns `invocation_id`, `capability_execution_id`, `provider`, `operation_id`, `idempotency_key`, `request_fingerprint`, `status`, `started_at`, `finished_at`.

| Field | Type | Required | Default |
|---|---|---|---|
| `invocation_id` | `str` | yes | required |
| `capability_execution_id` | `str` | yes | required |
| `provider` | `str` | yes | required |
| `operation_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `idempotency_key` | `str` | yes | required |
| `request_fingerprint` | `str` | yes | required |
| `status` | `<enum 'ProviderInvocationStatus` | yes | required |
| `started_at` | `datetime.datetime` | yes | required |
| `finished_at` | `Optional[Annotated[datetime.datetime, BeforeValidator(func=<function _reject_numeric_datetime at >, json_schema_input_type=PydanticUndefined), AfterValidator(func=<function _ensure_utc at >)]]` | no | `null` |

## Immutable artifacts, pointers, invalidation

### `Artifact`

`schema_version`: `artifact.v1`

**Durable mapping:** `artifacts` (repository `ArtifactRepository` in `artifacts.py`); keys `artifact_id`; extracted columns `artifact_id`, `run_id`, `logical_slot`, `artifact_type`, `version`, `uri`, `sha256`, `size_bytes`, `media_type`, `producer_attempt_id`, `producer_version`, `config_hash`, `state`, `retention_class`, `created_at`.

| Field | Type | Required | Default |
|---|---|---|---|
| `artifact_id` | `str` | yes | required |
| `run_id` | `str` | yes | required |
| `logical_slot` | `str` | yes | required |
| `artifact_type` | `str` | yes | required |
| `version` | `int` | yes | required |
| `uri` | `str` | yes | required |
| `sha256` | `str` | yes | required |
| `size_bytes` | `int` | yes | required |
| `media_type` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `media_metadata` | `ExtensionObject` | no | `PydanticUndefined` |
| `producer_attempt_id` | `str` | yes | required |
| `producer_version` | `str` | yes | required |
| `input_artifact_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `config_hash` | `str` | yes | required |
| `state` | `<enum 'ArtifactState` | yes | required |
| `retention_class` | `str` | no | `intermediate` |
| `created_at` | `datetime.datetime` | yes | required |

### `ArtifactDependency`

`schema_version`: `artifact-dependency.v1`

**Durable mapping:** `artifact_dependencies` (repository `ArtifactDependencyRepository` in `artifacts.py`); keys `parent_artifact_id`, `child_artifact_id`; extracted columns `parent_artifact_id`, `child_artifact_id`, `dependency_type`.

| Field | Type | Required | Default |
|---|---|---|---|
| `parent_artifact_id` | `str` | yes | required |
| `child_artifact_id` | `str` | yes | required |
| `dependency_type` | `str` | yes | required |

### `ArtifactPointer`

`schema_version`: `artifact-pointer.v1`

**Durable mapping:** `artifact_pointers` (repository `ArtifactPointerRepository` in `artifacts.py`); keys `pointer_id`; extracted columns `pointer_id`, `run_id`, `logical_slot`, `artifact_id`, `pointer_type`, `active`, `updated_at`.

| Field | Type | Required | Default |
|---|---|---|---|
| `pointer_id` | `str` | yes | required |
| `run_id` | `str` | yes | required |
| `logical_slot` | `str` | yes | required |
| `artifact_id` | `str` | yes | required |
| `pointer_type` | `<enum 'ArtifactPointerType` | yes | required |
| `active` | `bool` | no | `True` |
| `updated_at` | `datetime.datetime` | yes | required |

### `InvalidationRequest`

`schema_version`: `invalidation-request.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `request_id` | `str` | yes | required |
| `root_artifact_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | yes | required |
| `reason` | `str` | yes | required |
| `scope` | `<enum 'InvalidationScope` | yes | required |
| `requested_by` | `str` | yes | required |

### `InvalidationResult`

`schema_version`: `invalidation-result.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `request_id` | `str` | yes | required |
| `invalidated_artifact_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | yes | required |
| `retained_artifact_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `created_at` | `datetime.datetime` | yes | required |

## Quality checks, evaluations, gates, repair

### `EvaluationDimension`

`schema_version`: `evaluation-dimension.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `name` | `str` | yes | required |
| `score` | `Optional[Annotated[float, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), AllowInfNan(allow_inf_nan=False)])]]` | no | `null` |
| `threshold` | `Optional[Annotated[float, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), AllowInfNan(allow_inf_nan=False)])]]` | no | `null` |
| `severity` | `<enum 'Severity` | no | `INFO` |
| `failure_codes` | `list[vocabularies.FailureCode]` | no | `PydanticUndefined` |
| `evidence_refs` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `details` | `ExtensionObject` | no | `PydanticUndefined` |

### `QualityCheck`

`schema_version`: `quality-check.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `check_id` | `str` | yes | required |
| `target_artifact_types` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | yes | required |
| `required_input_types` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `kind` | `<enum 'EvaluationKind` | yes | required |
| `evaluator` | `str` | yes | required |
| `evaluator_version` | `str` | yes | required |
| `rubric_version` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `required` | `bool` | no | `True` |
| `severity_if_failed` | `<enum 'Severity` | yes | required |
| `on_failure` | `<enum 'QualityFailureAction` | yes | required |
| `repair_scope` | `<enum 'RepairScope` | yes | required |

### `QualityInputManifest`

`schema_version`: `quality-input-manifest.v1`

**Durable mapping:** `quality_input_manifests` (repository `QualityInputManifestRepository` in `quality.py`); keys `manifest_id`; extracted columns `manifest_id`, `gate_id`, `check_id`, `created_at`.

| Field | Type | Required | Default |
|---|---|---|---|
| `manifest_id` | `str` | yes | required |
| `gate_id` | `str` | yes | required |
| `check_id` | `str` | yes | required |
| `target_artifact_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | yes | required |
| `target_hashes` | `dict[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)], Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', ascii_only=None)]]` | yes | required |
| `supporting_artifact_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `policy_snapshot_artifact_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `created_at` | `datetime.datetime` | yes | required |

### `QualityGatePolicy`

`schema_version`: `quality-gate-policy.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `gate_id` | `str` | yes | required |
| `version` | `str` | yes | required |
| `required_check_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | yes | required |
| `hard_failure_codes` | `list[vocabularies.FailureCode]` | no | `PydanticUndefined` |
| `pass_thresholds` | `dict[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)], Annotated[float, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), AllowInfNan(allow_inf_nan=False)])]]` | no | `PydanticUndefined` |
| `human_review_thresholds` | `dict[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)], Annotated[float, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), AllowInfNan(allow_inf_nan=False)])]]` | no | `PydanticUndefined` |
| `max_regenerations` | `int` | no | `0` |
| `after_max_regenerations` | `<enum 'RepeatedFailureAction` | yes | required |

### `QualityEvaluation`

`schema_version`: `quality-evaluation.v1`

**Durable mapping:** `quality_evaluations` (repository `QualityEvaluationRepository` in `quality.py`); keys `evaluation_id`; extracted columns `evaluation_id`, `stage_instance_id`, `logical_item_key`, `scene_id`, `shot_id`, `gate_id`, `check_id`, `outcome`, `created_at`.

| Field | Type | Required | Default |
|---|---|---|---|
| `evaluation_id` | `str` | yes | required |
| `stage_instance_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `logical_item_key` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `scene_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `shot_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `target_artifact_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | yes | required |
| `target_hashes` | `dict[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)], Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', ascii_only=None)]]` | yes | required |
| `evaluation_input_manifest_id` | `str` | yes | required |
| `gate_id` | `str` | yes | required |
| `check_id` | `str` | yes | required |
| `evaluator` | `str` | yes | required |
| `evaluator_version` | `str` | yes | required |
| `rubric_version` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `dimensions` | `list[quality.EvaluationDimension]` | no | `PydanticUndefined` |
| `outcome` | `<enum 'CheckOutcome` | yes | required |
| `confidence` | `vocabularies.Confidence | None` | no | `null` |
| `abstained` | `bool` | no | `False` |
| `evidence` | `list[ExtensionObject]` | no | `PydanticUndefined` |
| `estimated_cost_minor` | `int` | no | `0` |
| `actual_cost_minor` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=0)])]]` | no | `null` |
| `provider_invocation_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `latency_ms` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=0)])]]` | no | `null` |
| `created_at` | `datetime.datetime` | yes | required |

### `QualityGateResult`

`schema_version`: `quality-gate-result.v1`

**Durable mapping:** `quality_gate_results` (repository `QualityGateResultRepository` in `quality.py`); keys `quality_gate_result_id`; extracted columns `quality_gate_result_id`, `gate_id`, `gate_version`, `stage_instance_id`, `logical_item_key`, `decision`, `policy_version`, `created_at`, `completed_at`.

| Field | Type | Required | Default |
|---|---|---|---|
| `quality_gate_result_id` | `str` | yes | required |
| `gate_id` | `str` | yes | required |
| `gate_version` | `str` | yes | required |
| `stage_instance_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `logical_item_key` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `target_artifact_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | yes | required |
| `target_hashes` | `dict[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)], Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', ascii_only=None)]]` | yes | required |
| `required_check_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | yes | required |
| `evaluation_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | yes | required |
| `decision` | `<enum 'GateDecision` | yes | required |
| `hard_failure_codes` | `list[vocabularies.FailureCode]` | no | `PydanticUndefined` |
| `repair_scope` | `vocabularies.RepairScope | None` | no | `null` |
| `policy_version` | `str` | yes | required |
| `created_at` | `datetime.datetime` | yes | required |
| `completed_at` | `Optional[Annotated[datetime.datetime, BeforeValidator(func=<function _reject_numeric_datetime at >, json_schema_input_type=PydanticUndefined), AfterValidator(func=<function _ensure_utc at >)]]` | no | `null` |

### `RepairPlan`

`schema_version`: `repair-plan.v1`

**Durable mapping:** `repair_plans` (repository `RepairPlanRepository` in `quality.py`); keys `repair_plan_id`; extracted columns `repair_plan_id`, `source_gate_result_id`, `invalidation_scope`, `created_at`.

| Field | Type | Required | Default |
|---|---|---|---|
| `repair_plan_id` | `str` | yes | required |
| `source_gate_result_id` | `str` | yes | required |
| `reason_codes` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | yes | required |
| `target_artifact_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `target_stage_instance_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `invalidation_scope` | `<enum 'RepairInvalidationScope` | yes | required |
| `max_attempts` | `int` | yes | required |
| `created_at` | `datetime.datetime` | yes | required |

## Human review and publication

### `HumanReview`

`schema_version`: `human-review.v1`

**Durable mapping:** `human_reviews` (repository `HumanReviewRepository` in `editorial.py`); keys `review_id`; extracted columns `review_id`, `run_id`, `stage_instance_id`, `gate_id`, `status`, `requested_action`, `created_at`, `resolved_at`.

| Field | Type | Required | Default |
|---|---|---|---|
| `review_id` | `str` | yes | required |
| `run_id` | `str` | yes | required |
| `stage_instance_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `gate_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `target_artifact_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | yes | required |
| `target_hashes` | `dict[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)], Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `reason_codes` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `requested_action` | `str` | yes | required |
| `status` | `<enum 'ReviewStatus` | yes | required |
| `created_at` | `datetime.datetime` | yes | required |
| `resolved_at` | `Optional[Annotated[datetime.datetime, BeforeValidator(func=<function _reject_numeric_datetime at >, json_schema_input_type=PydanticUndefined), AfterValidator(func=<function _ensure_utc at >)]]` | no | `null` |

### `HumanReviewDecision`

`schema_version`: `human-review-decision.v1`

**Durable mapping:** `human_review_decisions` (repository `HumanReviewDecisionRepository` in `editorial.py`); keys `decision_sequence`; extracted columns `decision_sequence`, `review_id`, `decision`, `reviewer`, `comments`, `target_hashes`, `created_at`.

| Field | Type | Required | Default |
|---|---|---|---|
| `review_id` | `str` | yes | required |
| `decision` | `<enum 'ReviewDecision` | yes | required |
| `comments` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `reviewer` | `str` | yes | required |
| `target_hashes` | `dict[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)], Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `created_at` | `datetime.datetime` | yes | required |

### `PublicationRequest`

`schema_version`: `publication-request.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `publication_request_id` | `str` | yes | required |
| `run_id` | `str` | yes | required |
| `cut_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | yes | required |
| `approved_artifact_hashes` | `dict[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)], Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', ascii_only=None)]]` | yes | required |
| `approval_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | yes | required |
| `platform` | `str` | yes | required |
| `metadata_artifact_id` | `str` | yes | required |
| `idempotency_key` | `str` | yes | required |

### `PublicationAttempt`

`schema_version`: `publication-attempt.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `publication_attempt_id` | `str` | yes | required |
| `publication_request_id` | `str` | yes | required |
| `status` | `<enum 'PublicationStatus` | yes | required |
| `external_publication_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `provider_operation_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `normalized_error` | `base.NormalizedError | None` | no | `null` |
| `started_at` | `Optional[Annotated[datetime.datetime, BeforeValidator(func=<function _reject_numeric_datetime at >, json_schema_input_type=PydanticUndefined), AfterValidator(func=<function _ensure_utc at >)]]` | no | `null` |
| `finished_at` | `Optional[Annotated[datetime.datetime, BeforeValidator(func=<function _reject_numeric_datetime at >, json_schema_input_type=PydanticUndefined), AfterValidator(func=<function _ensure_utc at >)]]` | no | `null` |

## Events, outbox, inbox

### `EventEnvelope`

`schema_version`: `event-envelope.v1`

**Durable mapping:** `workflow_events` (repository `WorkflowEventRepository` in `events.py`); keys `event_id`; extracted columns `event_id`, `event_type`, `run_id`, `stage_instance_id`, `attempt_id`, `correlation_id`, `causation_id`, `payload_schema_version`, `created_at`.

| Field | Type | Required | Default |
|---|---|---|---|
| `event_id` | `str` | yes | required |
| `event_type` | `<enum 'EventType` | yes | required |
| `run_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `stage_instance_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `attempt_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `correlation_id` | `str` | yes | required |
| `causation_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `payload_schema_version` | `str` | yes | required |
| `payload` | `ExtensionObject` | no | `PydanticUndefined` |
| `created_at` | `datetime.datetime` | yes | required |

### `OutboxMessage`

`schema_version`: `outbox-message.v1`

**Durable mapping:** `outbox_messages` (repository `OutboxMessageRepository` in `events.py`); keys `outbox_id`; extracted columns `outbox_id`, `event_id`, `status`, `delivery_attempts`, `available_at`, `claimed_by`, `claimed_at`, `lease_expires_at`, `delivered_at`.

| Field | Type | Required | Default |
|---|---|---|---|
| `outbox_id` | `str` | yes | required |
| `event_id` | `str` | yes | required |
| `event` | `events.EventEnvelope` | yes | required |
| `status` | `<enum 'OutboxStatus` | yes | required |
| `delivery_attempts` | `int` | no | `0` |
| `available_at` | `datetime.datetime` | yes | required |
| `claimed_by` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `claimed_at` | `Optional[Annotated[datetime.datetime, BeforeValidator(func=<function _reject_numeric_datetime at >, json_schema_input_type=PydanticUndefined), AfterValidator(func=<function _ensure_utc at >)]]` | no | `null` |
| `lease_expires_at` | `Optional[Annotated[datetime.datetime, BeforeValidator(func=<function _reject_numeric_datetime at >, json_schema_input_type=PydanticUndefined), AfterValidator(func=<function _ensure_utc at >)]]` | no | `null` |
| `delivered_at` | `Optional[Annotated[datetime.datetime, BeforeValidator(func=<function _reject_numeric_datetime at >, json_schema_input_type=PydanticUndefined), AfterValidator(func=<function _ensure_utc at >)]]` | no | `null` |

### `InboxReceipt`

`schema_version`: `inbox-receipt.v1`

**Durable mapping:** `inbox_receipts` (repository `InboxReceiptRepository` in `events.py`); keys `consumer_id`, `event_id`; extracted columns `consumer_id`, `event_id`, `status`, `processed_at`, `error_code`.

| Field | Type | Required | Default |
|---|---|---|---|
| `consumer_id` | `str` | yes | required |
| `event_id` | `str` | yes | required |
| `status` | `<enum 'InboxStatus` | yes | required |
| `processed_at` | `Optional[Annotated[datetime.datetime, BeforeValidator(func=<function _reject_numeric_datetime at >, json_schema_input_type=PydanticUndefined), AfterValidator(func=<function _ensure_utc at >)]]` | no | `null` |
| `error_code` | `vocabularies.FailureCode | None` | no | `null` |

## Policy and domain/channel profiles

### `BudgetPolicy`

`schema_version`: `budget-policy.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `policy_id` | `str` | yes | required |
| `version` | `str` | yes | required |
| `system_cap_minor` | `int` | yes | required |
| `monthly_cap_minor` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=0)])]]` | no | `null` |
| `default_run_cap_minor` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=0)])]]` | no | `null` |
| `default_stage_cap_minor` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=0)])]]` | no | `null` |
| `evaluation_cap_minor` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=0)])]]` | no | `null` |
| `paid_fallback_enabled` | `bool` | no | `False` |
| `reservation_required` | `bool` | no | `True` |

### `SystemPolicy`

`schema_version`: `system-policy.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `policy_id` | `str` | yes | required |
| `version` | `str` | yes | required |
| `max_parallelism` | `int` | yes | required |
| `max_retry_attempts` | `int` | yes | required |
| `budget_policy_id` | `str` | yes | required |
| `allowed_providers` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `non_overridable_fields` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |

### `DomainProfile`

`schema_version`: `domain-profile.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `profile_id` | `str` | yes | required |
| `version` | `str` | yes | required |
| `content_mode` | `str` | yes | required |
| `default_locale` | `str` | yes | required |
| `required_stages` | `list[vocabularies.StageName]` | yes | required |
| `optional_stages` | `list[vocabularies.StageName]` | no | `PydanticUndefined` |
| `source_policy_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `claim_policy_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `quality_profile_id` | `str` | yes | required |
| `human_review_policy_id` | `str` | yes | required |
| `asset_policy_id` | `str` | yes | required |

### `ChannelProfile`

`schema_version`: `channel-profile.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `profile_id` | `str` | yes | required |
| `version` | `str` | yes | required |
| `domain_profile_id` | `str` | yes | required |
| `locale` | `str` | yes | required |
| `audience` | `str` | yes | required |
| `target_duration_seconds` | `int` | yes | required |
| `output_profile_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | yes | required |
| `brand_profile_id` | `str` | yes | required |
| `voice_profile_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `publishing_policy_id` | `str` | yes | required |

## Content package hierarchy and composition references

### `ContentPackage`

`schema_version`: `content-package.v1`

**Durable mapping:** `content_packages` (repository `ContentPackageRepository` in `editorial.py`); keys `content_package_id`; extracted columns `content_package_id`, `production_idea_id`, `active_episode_id`.

| Field | Type | Required | Default |
|---|---|---|---|
| `content_package_id` | `str` | yes | required |
| `production_idea_id` | `str` | yes | required |
| `episode_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `active_episode_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |

### `Episode`

`schema_version`: `episode.v1`

**Durable mapping:** `episodes` (repository `EpisodeRepository` in `editorial.py`); keys `episode_id`; extracted columns `episode_id`, `content_package_id`, `script_artifact_id`, `version`.

| Field | Type | Required | Default |
|---|---|---|---|
| `episode_id` | `str` | yes | required |
| `content_package_id` | `str` | yes | required |
| `script_artifact_id` | `str` | yes | required |
| `sequence_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `cut_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `version` | `int` | yes | required |

### `Cut`

`schema_version`: `cut.v1`

**Durable mapping:** `cuts` (repository `CutRepository` in `editorial.py`); keys `cut_id`; extracted columns `cut_id`, `episode_id`, `kind`, `output_profile_id`, `selection_manifest_id`.

| Field | Type | Required | Default |
|---|---|---|---|
| `cut_id` | `str` | yes | required |
| `episode_id` | `str` | yes | required |
| `kind` | `<enum 'EditorialCutKind` | yes | required |
| `output_profile_id` | `str` | yes | required |
| `sequence_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `selection_manifest_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |

### `Sequence`

`schema_version`: `sequence.v1`

**Durable mapping:** `sequences` (repository `SequenceRepository` in `editorial.py`); keys `sequence_id`; extracted columns `sequence_id`, `episode_id`, `order_index`.

| Field | Type | Required | Default |
|---|---|---|---|
| `sequence_id` | `str` | yes | required |
| `episode_id` | `str` | yes | required |
| `order_index` | `int` | yes | required |
| `scene_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |

### `Scene`

`schema_version`: `scene.v1`

**Durable mapping:** `scenes` (repository `SceneRepository` in `editorial.py`); keys `scene_id`; extracted columns `scene_id`, `sequence_id`, `order_index`, `narration_artifact_id`.

| Field | Type | Required | Default |
|---|---|---|---|
| `scene_id` | `str` | yes | required |
| `sequence_id` | `str` | yes | required |
| `order_index` | `int` | yes | required |
| `narration_artifact_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `claim_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `shot_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |

### `Shot`

`schema_version`: `shot.v1`

**Durable mapping:** `shots` (repository `ShotRepository` in `editorial.py`); keys `shot_id`; extracted columns `shot_id`, `scene_id`, `order_index`, `start_frame`, `end_frame`.

| Field | Type | Required | Default |
|---|---|---|---|
| `shot_id` | `str` | yes | required |
| `scene_id` | `str` | yes | required |
| `order_index` | `int` | yes | required |
| `start_frame` | `int` | yes | required |
| `end_frame` | `int` | yes | required |
| `layer_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |

### `LayerInstance`

`schema_version`: `layer-instance.v1`

**Durable mapping:** `layer_instances` (repository `LayerInstanceRepository` in `editorial.py`); keys `layer_id`; extracted columns `layer_id`, `shot_id`, `kind`, `start_frame`, `end_frame`, `asset_instance_id`, `payload_artifact_id`, `z_index`.

| Field | Type | Required | Default |
|---|---|---|---|
| `layer_id` | `str` | yes | required |
| `shot_id` | `str` | yes | required |
| `kind` | `<enum 'LayerKind` | yes | required |
| `start_frame` | `int` | yes | required |
| `end_frame` | `int` | yes | required |
| `asset_instance_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `payload_artifact_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `z_index` | `int` | no | `0` |
| `properties` | `ExtensionObject` | no | `PydanticUndefined` |

### `CompositionRef`

`schema_version`: `composition-ref.v1`

**Durable mapping:** `composition_refs` (repository `CompositionRefRepository` in `editorial.py`); keys `composition_artifact_id`; extracted columns `composition_artifact_id`, `cut_id`, `render_profile_id`, `render_profile_hash`, `timebase`.

| Field | Type | Required | Default |
|---|---|---|---|
| `composition_artifact_id` | `str` | yes | required |
| `cut_id` | `str` | yes | required |
| `render_profile_id` | `str` | yes | required |
| `render_profile_hash` | `str` | yes | required |
| `timebase` | `str` | yes | required |

## Renderer-neutral composition and manifests

### `CompositionLayerSpec`

`schema_version`: `composition-layer-spec.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `layer_id` | `str` | yes | required |
| `kind` | `<enum 'LayerKind` | yes | required |
| `start_frame` | `int` | yes | required |
| `end_frame` | `int` | yes | required |
| `asset_instance_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `payload_artifact_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `z_index` | `int` | no | `0` |
| `properties` | `ExtensionObject` | no | `PydanticUndefined` |

### `CompositionShotSpec`

`schema_version`: `composition-shot-spec.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `shot_id` | `str` | yes | required |
| `order_index` | `int` | yes | required |
| `start_frame` | `int` | yes | required |
| `end_frame` | `int` | yes | required |
| `layer_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |

### `CompositionSceneSpec`

`schema_version`: `composition-scene-spec.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `scene_id` | `str` | yes | required |
| `order_index` | `int` | yes | required |
| `narration_artifact_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `shot_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `audio_track_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |

### `CompositionSequenceSpec`

`schema_version`: `composition-sequence-spec.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `sequence_id` | `str` | yes | required |
| `order_index` | `int` | yes | required |
| `scene_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |

### `CompositionAudioTrackSpec`

`schema_version`: `composition-audio-track-spec.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `audio_track_id` | `str` | yes | required |
| `kind` | `Literal['VOICE', 'MUSIC', 'EFFECT', 'AMBIENCE']` | yes | required |
| `start_frame` | `int` | yes | required |
| `end_frame` | `int` | yes | required |
| `audio_artifact_id` | `str` | yes | required |
| `volume` | `float` | no | `1.0` |
| `fade_in_frames` | `int` | no | `0` |
| `fade_out_frames` | `int` | no | `0` |

### `CompositionAuthoringSpec`

`schema_version`: `composition-authoring-spec.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `schema_version_id` | `str` | yes | required |
| `input_artifact_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `input_artifact_hashes` | `dict[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)], Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `effective_config_hash` | `str` | yes | required |
| `renderer_version` | `str` | yes | required |
| `fonts_version` | `str` | yes | required |
| `template_version` | `str` | yes | required |
| `timebase` | `str` | yes | required |
| `frame_rate` | `int` | yes | required |
| `random_seed` | `int` | yes | required |

### `CompositionSpec`

`schema_version`: `render-manifest.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `composition_artifact_id` | `str` | yes | required |
| `cut_id` | `str` | yes | required |
| `render_profile_id` | `str` | yes | required |
| `render_profile_hash` | `str` | yes | required |
| `timebase` | `str` | yes | required |
| `frame_rate` | `int` | yes | required |
| `width` | `int` | yes | required |
| `height` | `int` | yes | required |
| `duration_frames` | `int` | yes | required |
| `authoring` | `composition.CompositionAuthoringSpec` | yes | required |
| `sequences` | `list[composition.CompositionSequenceSpec]` | no | `PydanticUndefined` |
| `scenes` | `list[composition.CompositionSceneSpec]` | no | `PydanticUndefined` |
| `shots` | `list[composition.CompositionShotSpec]` | no | `PydanticUndefined` |
| `layers` | `list[composition.CompositionLayerSpec]` | no | `PydanticUndefined` |
| `audio_tracks` | `list[composition.CompositionAudioTrackSpec]` | no | `PydanticUndefined` |

### `ResolvedArtifactRef`

`schema_version`: `resolved-artifact-ref.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `artifact_id` | `str` | yes | required |
| `artifact_type` | `str` | yes | required |
| `uri` | `str` | yes | required |
| `sha256` | `str` | yes | required |
| `size_bytes` | `int` | yes | required |
| `media_type` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `media_metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `RenderProfile`

`schema_version`: `render-profile.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `render_profile_id` | `str` | yes | required |
| `name` | `str` | yes | required |
| `width` | `int` | yes | required |
| `height` | `int` | yes | required |
| `frame_rate` | `int` | yes | required |
| `video_codec` | `str` | no | `libx264` |
| `video_bitrate_kbps` | `int` | no | `8000` |
| `audio_codec` | `str` | no | `aac` |
| `audio_bitrate_kbps` | `int` | no | `192` |
| `audio_sample_rate` | `int` | no | `48000` |
| `pixel_format` | `str` | no | `yuv420p` |
| `color_space` | `str` | no | `bt709` |
| `profile` | `str` | no | `high` |
| `level` | `str` | no | `4.1` |
| `preset` | `str` | no | `medium` |
| `crf` | `int` | no | `18` |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `RenderChunkManifest`

`schema_version`: `render-chunk-manifest.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `chunk_id` | `str` | yes | required |
| `composition_artifact_id` | `str` | yes | required |
| `render_profile_id` | `str` | yes | required |
| `start_frame` | `int` | yes | required |
| `end_frame` | `int` | yes | required |
| `output_artifact_id` | `str` | yes | required |
| `output_uri` | `str` | yes | required |
| `output_sha256` | `str` | yes | required |
| `output_size_bytes` | `int` | yes | required |
| `duration_frames` | `int` | yes | required |
| `frame_checksums` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `renderer_version` | `str` | yes | required |
| `render_started_at` | `datetime.datetime` | yes | required |
| `render_finished_at` | `datetime.datetime` | yes | required |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `AssemblyManifest`

`schema_version`: `assembly-manifest.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `assembly_artifact_id` | `str` | yes | required |
| `cut_id` | `str` | yes | required |
| `composition_artifact_id` | `str` | yes | required |
| `render_profile_id` | `str` | yes | required |
| `chunk_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `chunk_manifest_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `total_duration_frames` | `int` | yes | required |
| `continuity_checks_passed` | `bool` | no | `True` |
| `continuity_failures` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `output_artifact_id` | `str` | yes | required |
| `output_uri` | `str` | yes | required |
| `output_sha256` | `str` | yes | required |
| `output_size_bytes` | `int` | yes | required |
| `assembler_version` | `str` | yes | required |
| `assembled_at` | `datetime.datetime` | yes | required |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `ShortSelectionManifest`

`schema_version`: `short-selection-manifest.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `selection_manifest_id` | `str` | yes | required |
| `cut_id` | `str` | yes | required |
| `source_composition_artifact_id` | `str` | yes | required |
| `target_render_profile_id` | `str` | yes | required |
| `selected_scene_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `selected_shot_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `safe_area` | `ExtensionObject` | no | `PydanticUndefined` |
| `vertical_composition` | `bool` | no | `True` |
| `target_aspect_ratio` | `str` | no | `9:16` |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

## Research, script, speech, and timing content

### `SourceRef`

`schema_version`: `source-ref.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `source_id` | `str` | yes | required |
| `kind` | `<enum 'SourceKind` | yes | required |
| `uri` | `str` | yes | required |
| `title` | `str` | yes | required |
| `author` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `published_at` | `Optional[Annotated[datetime.datetime, BeforeValidator(func=<function _reject_numeric_datetime at >, json_schema_input_type=PydanticUndefined), AfterValidator(func=<function _ensure_utc at >)]]` | no | `null` |
| `retrieved_at` | `datetime.datetime` | yes | required |
| `content_hash` | `str` | yes | required |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `SourceSnapshot`

`schema_version`: `source-snapshot.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `snapshot_id` | `str` | yes | required |
| `source_ref_id` | `str` | yes | required |
| `content` | `str` | yes | required |
| `content_hash` | `str` | yes | required |
| `token_count` | `int` | yes | required |
| `language` | `str` | no | `en` |
| `extracted_at` | `datetime.datetime` | yes | required |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `Evidence`

`schema_version`: `evidence.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `evidence_id` | `str` | yes | required |
| `snapshot_id` | `str` | yes | required |
| `claim_id` | `str` | yes | required |
| `text_span` | `str` | yes | required |
| `start_offset` | `int` | yes | required |
| `end_offset` | `int` | yes | required |
| `confidence` | `float` | yes | required |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `Claim`

`schema_version`: `claim.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `claim_id` | `str` | yes | required |
| `text` | `str` | yes | required |
| `claim_type` | `Literal['FACTUAL', 'NUMERIC', 'QUOTE', 'DEFINITION', 'CAUSAL']` | yes | required |
| `source_ref_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `evidence_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `confidence` | `float` | yes | required |
| `tags` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `VisualIntent`

`schema_version`: `visual-intent.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `visual_intent_id` | `str` | yes | required |
| `scene_id` | `str` | yes | required |
| `description` | `str` | yes | required |
| `purpose` | `Literal['ESTABLISHING', 'ILLUSTRATIVE', 'EVIDENCE', 'DATA_VIZ', 'TRANSITION', 'BRANDING']` | yes | required |
| `elements` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `overlays` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `provenance_requirements` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `timing_hint_seconds` | `Optional[Annotated[float, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=0), AllowInfNan(allow_inf_nan=False)])]]` | no | `null` |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `DurationPolicy`

`schema_version`: `duration-policy.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `policy_id` | `str` | yes | required |
| `target_total_seconds` | `int` | yes | required |
| `min_scene_seconds` | `int` | no | `3` |
| `max_scene_seconds` | `int` | no | `30` |
| `words_per_minute` | `int` | no | `150` |
| `pause_seconds_per_comma` | `float` | no | `0.2` |
| `pause_seconds_per_period` | `float` | no | `0.5` |
| `intro_outro_seconds` | `int` | no | `5` |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `ScriptScene`

`schema_version`: `script-scene.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `scene_id` | `str` | yes | required |
| `script_id` | `str` | yes | required |
| `order_index` | `int` | yes | required |
| `narration` | `str` | yes | required |
| `claim_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `visual_intent_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `estimated_duration_seconds` | `int` | yes | required |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `Script`

`schema_version`: `script.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `script_id` | `str` | yes | required |
| `episode_id` | `str` | yes | required |
| `title` | `str` | yes | required |
| `outline` | `str` | yes | required |
| `scenes` | `list[content.ScriptScene]` | no | `PydanticUndefined` |
| `claim_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `evidence_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `source_ref_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `visual_intent_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `duration_policy_id` | `str` | yes | required |
| `total_estimated_duration_seconds` | `int` | yes | required |
| `word_count` | `int` | yes | required |
| `language` | `str` | no | `en` |
| `created_at` | `datetime.datetime` | yes | required |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `AudioTiming`

`schema_version`: `audio-timing.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `audio_timing_id` | `str` | yes | required |
| `speech_manifest_id` | `str` | yes | required |
| `script_version` | `str` | yes | required |
| `scene_id` | `str` | yes | required |
| `audio_artifact_id` | `str` | yes | required |
| `narration_text_hash` | `str` | yes | required |
| `word_timestamps` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `sample_rate` | `int` | no | `24000` |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `SpeechManifest`

`schema_version`: `speech-manifest.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `speech_manifest_id` | `str` | yes | required |
| `script_id` | `str` | yes | required |
| `script_version` | `str` | yes | required |
| `strategy` | `<enum 'SpeechStrategy` | yes | required |
| `master_audio_artifact_id` | `str` | yes | required |
| `scene_audio_artifact_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `voice_config_hash` | `str` | yes | required |
| `narration_text_hashes` | `dict[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)], Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `alignment_artifact_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `total_duration_seconds` | `int` | yes | required |
| `sample_rate` | `int` | no | `24000` |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `WordTimestamp`

`schema_version`: `word-timestamp.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `word_timestamp_id` | `str` | yes | required |
| `audio_timing_id` | `str` | yes | required |
| `word` | `str` | yes | required |
| `start_frames` | `int` | yes | required |
| `end_frames` | `int` | yes | required |
| `confidence` | `float` | yes | required |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

## Typed payloads exchanged with capabilities

### `ResearchInputPayload`

`schema_version`: `research-input.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `topic` | `str` | yes | required |
| `focus_areas` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `source_kinds` | `list[vocabularies.SourceKind]` | no | `PydanticUndefined` |
| `max_sources` | `int` | no | `10` |
| `max_tokens_per_source` | `int` | no | `8000` |
| `language` | `str` | no | `en` |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `ResearchOutputPayload`

`schema_version`: `research-output.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `source_ref_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `source_snapshot_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `claim_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `evidence_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `source_count` | `int` | no | `0` |
| `claim_count` | `int` | no | `0` |
| `evidence_count` | `int` | no | `0` |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `ScriptGenerationInputPayload`

`schema_version`: `script-generation-input.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `topic` | `str` | yes | required |
| `outline` | `str` | yes | required |
| `claim_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `evidence_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `source_ref_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `duration_policy_id` | `str` | yes | required |
| `target_audience` | `str` | no | `general` |
| `tone` | `str` | no | `informative` |
| `language` | `str` | no | `en` |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `ScriptGenerationOutputPayload`

`schema_version`: `script-generation-output.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `script_id` | `str` | yes | required |
| `scene_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `visual_intent_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `total_estimated_duration_seconds` | `int` | yes | required |
| `word_count` | `int` | yes | required |
| `scene_count` | `int` | yes | required |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `VisualPlanningInputPayload`

`schema_version`: `visual-planning-input.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `script_id` | `str` | yes | required |
| `scene_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `visual_intent_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `style_guidance` | `str` | no | `documentary_cinematic` |
| `color_palette` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `null` |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `VisualPlanningOutputPayload`

`schema_version`: `visual-planning-output.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `visual_intent_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `shot_plan_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `asset_requirement_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `scene_count` | `int` | yes | required |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `SpeechGenerationInputPayload`

`schema_version`: `speech-generation-input.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `script_id` | `str` | yes | required |
| `script_version` | `str` | yes | required |
| `scene_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `strategy` | `<enum 'SpeechStrategy` | yes | required |
| `voice_config` | `ExtensionObject` | no | `PydanticUndefined` |
| `narration_texts` | `dict[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)], Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `language` | `str` | no | `en` |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `SpeechGenerationOutputPayload`

`schema_version`: `speech-generation-output.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `speech_manifest_id` | `str` | yes | required |
| `master_audio_artifact_id` | `str` | yes | required |
| `scene_audio_artifact_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `voice_config_hash` | `str` | yes | required |
| `narration_text_hashes` | `dict[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)], Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=64, max_length=64, pattern='^[0-9a-f]{64}$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `total_duration_seconds` | `int` | yes | required |
| `sample_rate` | `int` | no | `24000` |
| `scene_count` | `int` | yes | required |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `TTSAdapterInputPayload`

`schema_version`: `tts-adapter-input.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `narration_text` | `str` | yes | required |
| `voice_id` | `str` | yes | required |
| `provider` | `str` | yes | required |
| `model` | `str` | yes | required |
| `voice_config` | `ExtensionObject` | no | `PydanticUndefined` |
| `sample_rate` | `int` | no | `24000` |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `TTSAdapterOutputPayload`

`schema_version`: `tts-adapter-output.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `audio_artifact_id` | `str` | yes | required |
| `voice_id` | `str` | yes | required |
| `provider` | `str` | yes | required |
| `model` | `str` | yes | required |
| `voice_config_hash` | `str` | yes | required |
| `narration_text_hash` | `str` | yes | required |
| `duration_seconds` | `float` | yes | required |
| `sample_rate` | `int` | yes | required |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `ASRAlignmentInputPayload`

`schema_version`: `asr-alignment-input.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `audio_artifact_id` | `str` | yes | required |
| `narration_text` | `str` | yes | required |
| `language` | `str` | no | `en` |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `ASRAlignmentOutputPayload`

`schema_version`: `asr-alignment-output.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `alignment_artifact_id` | `str` | yes | required |
| `audio_timing_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `word_timestamp_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `asr_transcript` | `str` | yes | required |
| `narration_text_hash` | `str` | yes | required |
| `confidence` | `float` | yes | required |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `AudioQCInputPayload`

`schema_version`: `audio-qc-input.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `audio_artifact_id` | `str` | yes | required |
| `expected_narration_text` | `str` | yes | required |
| `target_loudness_lufs` | `float` | no | `-24.0` |
| `target_peak_db` | `float` | no | `-1.0` |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `AudioQCOutputPayload`

`schema_version`: `audio-qc-output.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `audio_artifact_id` | `str` | yes | required |
| `measured_loudness_lufs` | `float` | yes | required |
| `measured_peak_db` | `float` | yes | required |
| `loudness_pass` | `bool` | yes | required |
| `peak_pass` | `bool` | yes | required |
| `fidelity_pass` | `bool` | yes | required |
| `narration_text_hash` | `str` | yes | required |
| `omitted_phrases` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `changed_phrases` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=512, pattern='^\\S(?:.*\\S)?$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `CompositionInputPayload`

`schema_version`: `composition-input.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `cut_id` | `str` | yes | required |
| `script_id` | `str` | yes | required |
| `speech_manifest_id` | `str` | yes | required |
| `visual_intent_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `asset_instance_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `render_profile_id` | `str` | yes | required |
| `duration_policy_id` | `str` | yes | required |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `CompositionOutputPayload`

`schema_version`: `composition-output.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `composition_artifact_id` | `str` | yes | required |
| `cut_id` | `str` | yes | required |
| `render_profile_id` | `str` | yes | required |
| `sequence_count` | `int` | yes | required |
| `scene_count` | `int` | yes | required |
| `shot_count` | `int` | yes | required |
| `layer_count` | `int` | yes | required |
| `audio_track_count` | `int` | yes | required |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `RenderingInputPayload`

`schema_version`: `rendering-input.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `composition_artifact_id` | `str` | yes | required |
| `render_profile_id` | `str` | yes | required |
| `chunk_spec` | `Literal['COMPLETE_CUT', 'CHUNKED']` | no | `COMPLETE_CUT` |
| `chunk_frame_ranges` | `list[tuple[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=0)])], Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Strict(strict=True), Ge(ge=1)])]]]` | no | `PydanticUndefined` |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `RenderingOutputPayload`

`schema_version`: `rendering-output.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `composition_artifact_id` | `str` | yes | required |
| `render_profile_id` | `str` | yes | required |
| `chunk_manifest_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `complete_cut_artifact_id` | `Optional[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `null` |
| `chunked` | `bool` | no | `False` |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `AssemblyInputPayload`

`schema_version`: `assembly-input.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `composition_artifact_id` | `str` | yes | required |
| `render_profile_id` | `str` | yes | required |
| `chunk_manifest_ids` | `list[Annotated[str, StringConstraints(strip_whitespace=True, to_upper=None, to_lower=None, strict=True, min_length=1, max_length=256, pattern='^\\S+$', ascii_only=None)]]` | no | `PydanticUndefined` |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `AssemblyOutputPayload`

`schema_version`: `assembly-output.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `assembly_artifact_id` | `str` | yes | required |
| `cut_id` | `str` | yes | required |
| `composition_artifact_id` | `str` | yes | required |
| `render_profile_id` | `str` | yes | required |
| `output_artifact_id` | `str` | yes | required |
| `continuity_checks_passed` | `bool` | yes | required |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `ShortDerivativeInputPayload`

`schema_version`: `short-derivative-input.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `cut_id` | `str` | yes | required |
| `source_composition_artifact_id` | `str` | yes | required |
| `target_render_profile_id` | `str` | yes | required |
| `selection_manifest_id` | `str` | yes | required |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

### `ShortDerivativeOutputPayload`

`schema_version`: `short-derivative-output.v1`

| Field | Type | Required | Default |
|---|---|---|---|
| `short_cut_artifact_id` | `str` | yes | required |
| `selection_manifest_id` | `str` | yes | required |
| `target_render_profile_id` | `str` | yes | required |
| `output_artifact_id` | `str` | yes | required |
| `metadata` | `ExtensionObject` | no | `PydanticUndefined` |

## Vocabulary values

- **`AcceptanceStatus`**: `NOT_REQUIRED`, `PENDING`, `PASSED`, `REGENERATE`, `HUMAN_REVIEW`, `FAILED`
- **`ArtifactPointerType`**: `CURRENT`, `ACCEPTED`, `PUBLISHED`
- **`ArtifactState`**: `GENERATED`, `ACCEPTED`, `SUPERSEDED`, `INVALIDATED`, `DELETED`
- **`AttemptStatus`**: `CREATED`, `CLAIMED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `UNKNOWN`, `CANCELLED`
- **`BudgetReservationStatus`**: `RESERVED`, `SETTLED`, `RELEASED`, `UNKNOWN`
- **`BudgetScopeType`**: `SYSTEM`, `MONTH`, `RUN`, `STAGE`, `CAPABILITY`
- **`CapabilityExecutionStatus`**: `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `UNKNOWN`
- **`CapabilityResultStatus`**: `SUCCEEDED`, `FAILED`, `UNKNOWN`
- **`CardinalityMode`**: `one_to_one`, `one_to_many`, `many_to_one`, `many_to_many`
- **`CheckOutcome`**: `PASS`, `FAIL`, `ABSTAIN`, `ERROR`, `NOT_APPLICABLE`
- **`ConditionOperator`**: `ALWAYS`, `ALL`, `ANY`, `EQUALS`, `IN`, `GREATER_THAN`, `EXISTS`
- **`Confidence`**: `LOW`, `MEDIUM`, `HIGH`
- **`DuplicatePolicy`**: `RETURN_EXISTING`, `REJECT`, `CREATE_NEW`
- **`EditorialCutKind`**: `LONG_FORM`, `SHORT`
- **`EvaluationKind`**: `DETERMINISTIC`, `SPECIALIZED`, `SEMANTIC`, `HUMAN`
- **`EventType`**: `workflow.created`, `workflow.started`, `stage.ready`, `stage.claimed`, `stage.started`, `stage.succeeded`, `stage.failed`, `stage.unknown`, `artifact.created`, `artifact.invalidated`, `quality.requested`, `quality.evaluated`, `repair.requested`, `human_review.requested`, `human_review.completed`, `workflow.paused`, `workflow.resumed`, `workflow.completed`, `workflow.failed`, `publish.requested`, `publish.completed`
- **`FailureCategory`**: `VALIDATION`, `AUTHENTICATION`, `AUTHORIZATION`, `RATE_LIMIT`, `QUOTA`, `TRANSIENT`, `PERMANENT`, `UNKNOWN_OUTCOME`, `MEDIA`, `QUALITY`, `BUDGET`, `CONFIGURATION`, `HUMAN_REVIEW`, `POLICY`, `INTERNAL`
- **`FailureCode`**: `EXEC.VALIDATION`, `EXEC.AUTHENTICATION`, `EXEC.AUTHORIZATION`, `EXEC.RATE_LIMIT`, `EXEC.QUOTA`, `EXEC.TRANSIENT_PROVIDER`, `EXEC.PERMANENT_PROVIDER`, `EXEC.INTERNAL`, `EXEC.TIMEOUT_UNKNOWN`, `MEDIA.DECODE_ERROR`, `MEDIA.OUTPUT_PROFILE`, `MEDIA.TIMELINE_INVALID`, `MEDIA.TECHNICAL_INTEGRITY`, `QUALITY.SCHEMA_INVALID`, `QUALITY.GENERIC`, `QUALITY.UNSUPPORTED_CLAIM`, `QUALITY.NUMERIC_CONTRADICTION`, `QUALITY.TTS_OMISSION`, `QUALITY.TTS_PRONUNCIATION`, `QUALITY.VISUAL_MISMATCH`, `QUALITY.MISSING_ASSET`, `QUALITY.PROVENANCE_MISSING`, `QUALITY.CAPTION_OVERFLOW`, `QUALITY.AUDIO_DECODE`, `MEDIA.RENDER_CORRUPT`, `MEDIA.AUDIO_VIDEO_DRIFT`, `QUALITY.REPEATED_FAILURE`, `RIGHTS.LICENSE_UNCERTAIN`, `HUMAN.REVIEW_REQUIRED`, `POLICY.BUDGET_EXCEEDED`, `POLICY.PROHIBITED_CONTENT`, `CONFIG.UNKNOWN_STAGE`
- **`GateDecision`**: `PASS`, `REGENERATE`, `HUMAN_REVIEW`, `FAIL`
- **`IdempotencyStatus`**: `RESERVED`, `IN_FLIGHT`, `SUCCEEDED`, `FAILED`, `UNKNOWN`, `RECONCILED`
- **`InboxStatus`**: `RECEIVED`, `PROCESSED`, `IGNORED`, `FAILED`
- **`InputSelectorKind`**: `RUN_INPUT`, `DEPENDENCY_OUTPUTS`, `MANIFEST`, `POINTERS`
- **`InvalidationScope`**: `artifact`, `scene`, `subgraph`, `workflow`
- **`JobStatus`**: `READY`, `CLAIMED`, `ACKED`, `RETRY`, `DEAD_LETTER`, `CANCELLED`
- **`LayerKind`**: `VIDEO`, `IMAGE`, `SHAPE`, `CHART`, `CODE`, `TEXT`, `CAPTION`, `AUDIO_VOICE`, `AUDIO_MUSIC`, `AUDIO_EFFECT`, `MASK`, `TRANSITION`
- **`OutboxStatus`**: `PENDING`, `CLAIMED`, `DELIVERED`, `FAILED`
- **`ProviderInvocationStatus`**: `STARTED`, `SUCCEEDED`, `FAILED`, `UNKNOWN`
- **`PublicationStatus`**: `PENDING`, `STARTED`, `SUCCEEDED`, `FAILED`, `UNKNOWN`
- **`QualityFailureAction`**: `REGENERATE`, `HUMAN_REVIEW`, `FAIL`
- **`RecoveryAction`**: `RESUME`, `RETRY`, `RECONCILE`, `REGENERATE`, `WAIT_HUMAN`, `FAIL`
- **`RepairInvalidationScope`**: `ARTIFACT`, `SCENE`, `SUBGRAPH`, `WORKFLOW`
- **`RepairScope`**: `NONE`, `LAYER`, `ASSET`, `SHOT`, `SCENE`, `STAGE`, `CUT`, `SUBGRAPH`, `WORKFLOW`
- **`RepeatedFailureAction`**: `HUMAN_REVIEW`, `FAIL`
- **`ReviewDecision`**: `APPROVE`, `REGENERATE_SCENE`, `REGENERATE_STAGE`, `REJECT`
- **`ReviewStatus`**: `OPEN`, `ASSIGNED`, `RESOLVED`, `EXPIRED`, `CANCELLED`
- **`RunStatus`**: `CREATED`, `RUNNING`, `WAITING_HUMAN`, `WAITING_RETRY`, `COMPLETED`, `FAILED`, `CANCELLED`
- **`Severity`**: `INFO`, `MINOR`, `MAJOR`, `CRITICAL`
- **`SourceKind`**: `STOCK`, `PUBLIC_DOMAIN`, `GENERATED`, `PROCEDURAL`, `USER_SUPPLIED`
- **`SpeechStrategy`**: `CONTINUOUS`, `SCENE_SEGMENTED`
- **`StageExecutionStatus`**: `PENDING`, `READY`, `CLAIMED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `WAITING_HUMAN`, `WAITING_RETRY`, `CANCELLED`, `UNKNOWN`, `INVALIDATED`
- **`StageName`**: `manual_topic`, `topic_discovery`, `idea_development`, `research`, `script_generation`, `visual_planning`, `asset_acquisition`, `speech_generation`, `composition`, `rendering`, `assembly`, `short_derivative`, `technical_content_review`, `human_approval`, `publishing`, `analytics_learning`
- **`UnknownOutcomeAction`**: `RECONCILE`, `RETRY`, `WAIT_HUMAN`, `FAIL`

## Repository-backed models

| Contract | Table | Repository | Key columns |
|---|---|---|---|
| `ArtifactDependency` | `artifact_dependencies` | `ArtifactDependencyRepository` | `parent_artifact_id`, `child_artifact_id` |
| `ArtifactPointer` | `artifact_pointers` | `ArtifactPointerRepository` | `pointer_id` |
| `Artifact` | `artifacts` | `ArtifactRepository` | `artifact_id` |
| `BudgetReservation` | `budget_reservations` | `BudgetReservationRepository` | `reservation_id` |
| `CapabilityExecution` | `capability_executions` | `CapabilityExecutionRepository` | `capability_execution_id` |
| `CompositionRef` | `composition_refs` | `CompositionRefRepository` | `composition_artifact_id` |
| `ContentPackage` | `content_packages` | `ContentPackageRepository` | `content_package_id` |
| `Cut` | `cuts` | `CutRepository` | `cut_id` |
| `EffectiveConfig` | `effective_configs` | `EffectiveConfigRepository` | `effective_config_id` |
| `Episode` | `episodes` | `EpisodeRepository` | `episode_id` |
| `HumanReviewDecision` | `human_review_decisions` | `HumanReviewDecisionRepository` | `decision_sequence` |
| `HumanReview` | `human_reviews` | `HumanReviewRepository` | `review_id` |
| `IdempotencyRecord` | `idempotency_records` | `IdempotencyRecordRepository` | `idempotency_key` |
| `InboxReceipt` | `inbox_receipts` | `InboxReceiptRepository` | `consumer_id`, `event_id` |
| `Job` | `jobs` | `JobRepository` | `job_id` |
| `LayerInstance` | `layer_instances` | `LayerInstanceRepository` | `layer_id` |
| `Lease` | `leases` | `LeaseRepository` | `job_id`, `fencing_token` |
| `OutboxMessage` | `outbox_messages` | `OutboxMessageRepository` | `outbox_id` |
| `ProviderInvocation` | `provider_invocations` | `ProviderInvocationRepository` | `invocation_id` |
| `QualityEvaluation` | `quality_evaluations` | `QualityEvaluationRepository` | `evaluation_id` |
| `QualityGateResult` | `quality_gate_results` | `QualityGateResultRepository` | `quality_gate_result_id` |
| `QualityInputManifest` | `quality_input_manifests` | `QualityInputManifestRepository` | `manifest_id` |
| `RecoveryDecision` | `recovery_decisions` | `RecoveryDecisionRepository` | `recovery_decision_id` |
| `RepairPlan` | `repair_plans` | `RepairPlanRepository` | `repair_plan_id` |
| `RoutingDecision` | `routing_decisions` | `RoutingDecisionRepository` | `routing_decision_id` |
| `Scene` | `scenes` | `SceneRepository` | `scene_id` |
| `Sequence` | `sequences` | `SequenceRepository` | `sequence_id` |
| `Shot` | `shots` | `ShotRepository` | `shot_id` |
| `StageAttempt` | `stage_attempts` | `StageAttemptRepository` | `attempt_id` |
| `StageInstance` | `stage_instances` | `StageInstanceRepository` | `stage_instance_id` |
| `UsageRecord` | `usage_records` | `UsageRecordRepository` | `usage_id` |
| `EventEnvelope` | `workflow_events` | `WorkflowEventRepository` | `event_id` |
| `WorkflowRun` | `workflow_runs` | `WorkflowRunRepository` | `run_id` |

