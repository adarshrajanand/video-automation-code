-- FV-03 initial durable schema.
--
-- Every table stores the canonical Pydantic contract as a JSON payload plus
-- extracted identity, status, and timestamp columns used for uniqueness,
-- lookup, and indexes. Contract semantics remain in the payload; extracted
-- columns are projections and must not be treated as a second contract.

CREATE TABLE effective_configs (
    effective_config_id TEXT PRIMARY KEY,
    config_hash TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    workflow_version TEXT NOT NULL,
    system_policy_version TEXT NOT NULL,
    domain_profile_id TEXT NOT NULL,
    domain_profile_version TEXT NOT NULL,
    channel_profile_id TEXT NOT NULL,
    channel_profile_version TEXT NOT NULL,
    snapshot_artifact_id TEXT,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE INDEX idx_effective_configs_hash
    ON effective_configs (config_hash);

CREATE TABLE workflow_runs (
    run_id TEXT PRIMARY KEY,
    run_key TEXT NOT NULL UNIQUE,
    workflow_id TEXT NOT NULL,
    workflow_version TEXT NOT NULL,
    effective_config_id TEXT NOT NULL,
    effective_config_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    content_package_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    FOREIGN KEY (effective_config_id)
        REFERENCES effective_configs (effective_config_id)
);

CREATE INDEX idx_workflow_runs_status
    ON workflow_runs (status, created_at);
CREATE INDEX idx_workflow_runs_effective_config
    ON workflow_runs (effective_config_id);

CREATE TABLE stage_instances (
    stage_instance_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    logical_item_key TEXT NOT NULL,
    execution_status TEXT NOT NULL,
    acceptance_status TEXT NOT NULL,
    quality_gate_id TEXT,
    quality_gate_result_id TEXT,
    expected_input_manifest_id TEXT,
    active_attempt_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    UNIQUE (run_id, node_id, logical_item_key),
    FOREIGN KEY (run_id) REFERENCES workflow_runs (run_id)
);

CREATE INDEX idx_stage_instances_run_status
    ON stage_instances (run_id, execution_status);

CREATE TABLE stage_attempts (
    attempt_id TEXT PRIMARY KEY,
    stage_instance_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    quality_regeneration_number INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    worker_id TEXT,
    lease_expires_at TEXT,
    started_at TEXT,
    finished_at TEXT,
    failure_code TEXT,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    UNIQUE (stage_instance_id, attempt_number),
    FOREIGN KEY (stage_instance_id)
        REFERENCES stage_instances (stage_instance_id)
);

CREATE INDEX idx_stage_attempts_stage
    ON stage_attempts (stage_instance_id, attempt_number);
CREATE INDEX idx_stage_attempts_status
    ON stage_attempts (status);

CREATE TABLE jobs (
    job_id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL,
    queue_name TEXT NOT NULL,
    status TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    available_at TEXT NOT NULL,
    claimed_by TEXT,
    lease_expires_at TEXT,
    delivery_count INTEGER NOT NULL DEFAULT 0,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    FOREIGN KEY (attempt_id) REFERENCES stage_attempts (attempt_id)
);

CREATE INDEX idx_jobs_status_available
    ON jobs (status, available_at);
CREATE INDEX idx_jobs_lease_expires
    ON jobs (lease_expires_at);

CREATE TABLE leases (
    job_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    fencing_token INTEGER NOT NULL,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    heartbeat_at TEXT,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (job_id, fencing_token),
    FOREIGN KEY (job_id) REFERENCES jobs (job_id)
);

CREATE INDEX idx_leases_job_expires
    ON leases (job_id, expires_at);

CREATE TABLE idempotency_records (
    idempotency_key TEXT PRIMARY KEY,
    capability TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    provider TEXT,
    status TEXT NOT NULL,
    capability_execution_id TEXT NOT NULL,
    provider_invocation_id TEXT,
    provider_operation_id TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE INDEX idx_idempotency_status
    ON idempotency_records (status);
CREATE INDEX idx_idempotency_capability_execution
    ON idempotency_records (capability_execution_id);

CREATE TABLE budget_reservations (
    reservation_id TEXT PRIMARY KEY,
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    estimated_cost_minor INTEGER NOT NULL,
    reserved_cost_minor INTEGER NOT NULL,
    actual_cost_minor INTEGER,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    settled_at TEXT,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    UNIQUE (idempotency_key, scope_type, scope_id)
);

CREATE INDEX idx_budget_reservations_scope
    ON budget_reservations (scope_type, scope_id, status);

CREATE TABLE artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    logical_slot TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    version INTEGER NOT NULL,
    uri TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    media_type TEXT,
    producer_attempt_id TEXT NOT NULL,
    producer_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    state TEXT NOT NULL,
    retention_class TEXT NOT NULL,
    created_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    UNIQUE (run_id, logical_slot, version),
    FOREIGN KEY (run_id) REFERENCES workflow_runs (run_id)
);

CREATE INDEX idx_artifacts_run_slot_state
    ON artifacts (run_id, logical_slot, state);
CREATE INDEX idx_artifacts_sha256
    ON artifacts (sha256);

CREATE TABLE artifact_dependencies (
    parent_artifact_id TEXT NOT NULL,
    child_artifact_id TEXT NOT NULL,
    dependency_type TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (parent_artifact_id, child_artifact_id),
    FOREIGN KEY (parent_artifact_id) REFERENCES artifacts (artifact_id),
    FOREIGN KEY (child_artifact_id) REFERENCES artifacts (artifact_id)
);

CREATE INDEX idx_artifact_dependencies_child
    ON artifact_dependencies (child_artifact_id);

CREATE TABLE artifact_pointers (
    pointer_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    logical_slot TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    pointer_type TEXT NOT NULL,
    active INTEGER NOT NULL CHECK (active IN (0, 1)),
    updated_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES workflow_runs (run_id),
    FOREIGN KEY (artifact_id) REFERENCES artifacts (artifact_id)
);

CREATE UNIQUE INDEX uq_artifact_pointers_active
    ON artifact_pointers (run_id, logical_slot, pointer_type)
    WHERE active = 1;
CREATE INDEX idx_artifact_pointers_lookup
    ON artifact_pointers (run_id, logical_slot, pointer_type, active);

CREATE TABLE input_manifests (
    manifest_id TEXT PRIMARY KEY,
    stage_instance_id TEXT NOT NULL,
    expected_count INTEGER,
    complete INTEGER NOT NULL CHECK (complete IN (0, 1)),
    created_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    FOREIGN KEY (stage_instance_id)
        REFERENCES stage_instances (stage_instance_id)
);

CREATE INDEX idx_input_manifests_stage
    ON input_manifests (stage_instance_id);

CREATE TABLE quality_checks (
    check_id TEXT PRIMARY KEY,
    evaluator TEXT NOT NULL,
    evaluator_version TEXT NOT NULL,
    required INTEGER NOT NULL CHECK (required IN (0, 1)),
    on_failure TEXT NOT NULL,
    repair_scope TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE quality_gate_policies (
    gate_id TEXT NOT NULL,
    version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (gate_id, version)
);

CREATE TABLE quality_input_manifests (
    manifest_id TEXT PRIMARY KEY,
    gate_id TEXT NOT NULL,
    check_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE INDEX idx_quality_input_manifests_gate
    ON quality_input_manifests (gate_id, check_id);

CREATE TABLE quality_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    stage_instance_id TEXT,
    logical_item_key TEXT,
    scene_id TEXT,
    shot_id TEXT,
    gate_id TEXT NOT NULL,
    check_id TEXT NOT NULL,
    outcome TEXT NOT NULL,
    created_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE INDEX idx_quality_evaluations_stage
    ON quality_evaluations (stage_instance_id, created_at);
CREATE INDEX idx_quality_evaluations_gate
    ON quality_evaluations (gate_id, check_id);

CREATE TABLE quality_gate_results (
    quality_gate_result_id TEXT PRIMARY KEY,
    gate_id TEXT NOT NULL,
    gate_version TEXT NOT NULL,
    stage_instance_id TEXT,
    logical_item_key TEXT,
    decision TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE INDEX idx_quality_gate_results_stage
    ON quality_gate_results (stage_instance_id, created_at);
CREATE INDEX idx_quality_gate_results_gate
    ON quality_gate_results (gate_id, decision);

CREATE TABLE repair_plans (
    repair_plan_id TEXT PRIMARY KEY,
    source_gate_result_id TEXT NOT NULL,
    invalidation_scope TEXT NOT NULL,
    created_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE INDEX idx_repair_plans_source
    ON repair_plans (source_gate_result_id);

CREATE TABLE human_reviews (
    review_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    stage_instance_id TEXT,
    gate_id TEXT,
    status TEXT NOT NULL,
    requested_action TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE INDEX idx_human_reviews_status
    ON human_reviews (status, created_at);

CREATE TABLE human_review_decisions (
    decision_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    created_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    FOREIGN KEY (review_id) REFERENCES human_reviews (review_id)
);

CREATE INDEX idx_human_review_decisions_review
    ON human_review_decisions (review_id, created_at);

CREATE TABLE publication_requests (
    publication_request_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE INDEX idx_publication_requests_run
    ON publication_requests (run_id);

CREATE TABLE publication_attempts (
    publication_attempt_id TEXT PRIMARY KEY,
    publication_request_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    FOREIGN KEY (publication_request_id)
        REFERENCES publication_requests (publication_request_id)
);

CREATE INDEX idx_publication_attempts_request
    ON publication_attempts (publication_request_id, status);

CREATE TABLE workflow_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    run_id TEXT,
    stage_instance_id TEXT,
    attempt_id TEXT,
    correlation_id TEXT NOT NULL,
    causation_id TEXT,
    payload_schema_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE INDEX idx_workflow_events_run
    ON workflow_events (run_id, created_at);
CREATE INDEX idx_workflow_events_type
    ON workflow_events (event_type, created_at);

CREATE TABLE outbox_messages (
    outbox_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    delivery_attempts INTEGER NOT NULL DEFAULT 0,
    available_at TEXT NOT NULL,
    claimed_by TEXT,
    claimed_at TEXT,
    lease_expires_at TEXT,
    delivered_at TEXT,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    FOREIGN KEY (event_id) REFERENCES workflow_events (event_id)
);

CREATE INDEX idx_outbox_messages_status
    ON outbox_messages (status, available_at);

CREATE TABLE inbox_receipts (
    consumer_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    status TEXT NOT NULL,
    processed_at TEXT,
    error_code TEXT,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (consumer_id, event_id),
    FOREIGN KEY (event_id) REFERENCES workflow_events (event_id)
);

CREATE INDEX idx_inbox_receipts_status
    ON inbox_receipts (status, processed_at);

CREATE TABLE routing_decisions (
    routing_decision_id TEXT PRIMARY KEY,
    capability TEXT NOT NULL,
    implementation TEXT NOT NULL,
    implementation_version TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT,
    policy_version TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    data_classification TEXT NOT NULL,
    created_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE INDEX idx_routing_decisions_capability
    ON routing_decisions (capability, created_at);
CREATE INDEX idx_routing_decisions_provider
    ON routing_decisions (provider, model);

CREATE TABLE capability_executions (
    capability_execution_id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL,
    capability TEXT NOT NULL,
    status TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    FOREIGN KEY (attempt_id) REFERENCES stage_attempts (attempt_id)
);

CREATE INDEX idx_capability_executions_attempt
    ON capability_executions (attempt_id, status);
CREATE INDEX idx_capability_executions_idempotency
    ON capability_executions (idempotency_key);

CREATE TABLE provider_invocations (
    invocation_id TEXT PRIMARY KEY,
    capability_execution_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    operation_id TEXT,
    idempotency_key TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    FOREIGN KEY (capability_execution_id)
        REFERENCES capability_executions (capability_execution_id)
);

CREATE INDEX idx_provider_invocations_execution
    ON provider_invocations (capability_execution_id, status);

CREATE TABLE usage_records (
    usage_id TEXT PRIMARY KEY,
    capability_execution_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT,
    estimated_cost_minor INTEGER NOT NULL DEFAULT 0,
    actual_cost_minor INTEGER,
    created_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    FOREIGN KEY (capability_execution_id)
        REFERENCES capability_executions (capability_execution_id)
);

CREATE INDEX idx_usage_records_execution
    ON usage_records (capability_execution_id);
CREATE INDEX idx_usage_records_provider
    ON usage_records (provider, model);

CREATE TABLE recovery_decisions (
    recovery_decision_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    failed_attempt_id TEXT,
    action TEXT NOT NULL,
    created_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES workflow_runs (run_id)
);

CREATE INDEX idx_recovery_decisions_run
    ON recovery_decisions (run_id, created_at);

CREATE TABLE content_packages (
    content_package_id TEXT PRIMARY KEY,
    production_idea_id TEXT NOT NULL,
    active_episode_id TEXT,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE episodes (
    episode_id TEXT PRIMARY KEY,
    content_package_id TEXT NOT NULL,
    script_artifact_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    FOREIGN KEY (content_package_id)
        REFERENCES content_packages (content_package_id)
);

CREATE INDEX idx_episodes_package
    ON episodes (content_package_id);

CREATE TABLE cuts (
    cut_id TEXT PRIMARY KEY,
    episode_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    output_profile_id TEXT NOT NULL,
    selection_manifest_id TEXT,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    FOREIGN KEY (episode_id) REFERENCES episodes (episode_id)
);

CREATE INDEX idx_cuts_episode
    ON cuts (episode_id);

CREATE TABLE sequences (
    sequence_id TEXT PRIMARY KEY,
    episode_id TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    FOREIGN KEY (episode_id) REFERENCES episodes (episode_id)
);

CREATE INDEX idx_sequences_episode
    ON sequences (episode_id, order_index);

CREATE TABLE scenes (
    scene_id TEXT PRIMARY KEY,
    sequence_id TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    narration_artifact_id TEXT,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    FOREIGN KEY (sequence_id) REFERENCES sequences (sequence_id)
);

CREATE INDEX idx_scenes_sequence
    ON scenes (sequence_id, order_index);

CREATE TABLE shots (
    shot_id TEXT PRIMARY KEY,
    scene_id TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    start_frame INTEGER NOT NULL,
    end_frame INTEGER NOT NULL,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    CHECK (end_frame > start_frame),
    FOREIGN KEY (scene_id) REFERENCES scenes (scene_id)
);

CREATE INDEX idx_shots_scene
    ON shots (scene_id, order_index);

CREATE TABLE layer_instances (
    layer_id TEXT PRIMARY KEY,
    shot_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    start_frame INTEGER NOT NULL,
    end_frame INTEGER NOT NULL,
    asset_instance_id TEXT,
    payload_artifact_id TEXT,
    z_index INTEGER NOT NULL DEFAULT 0,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    CHECK (end_frame > start_frame),
    FOREIGN KEY (shot_id) REFERENCES shots (shot_id)
);

CREATE INDEX idx_layer_instances_shot
    ON layer_instances (shot_id, z_index);

CREATE TABLE composition_refs (
    composition_artifact_id TEXT PRIMARY KEY,
    cut_id TEXT NOT NULL,
    render_profile_id TEXT NOT NULL,
    render_profile_hash TEXT NOT NULL,
    timebase TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    FOREIGN KEY (cut_id) REFERENCES cuts (cut_id)
);

CREATE INDEX idx_composition_refs_cut
    ON composition_refs (cut_id);
