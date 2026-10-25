"""Tests for FV-08 audio capabilities: speech_generation, tts_adapter,
asr_alignment, audio_qc."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from pipeline.capabilities import (
    CapabilityExecutor,
    CapabilityRegistry,
    ExecutionError,
    ExecutionResult,
    FakeCapabilityProvider,
    create_asr_alignment_success_outcome,
    create_audio_qc_failure_outcome,
    create_audio_qc_success_outcome,
    create_speech_generation_success_outcome,
    create_tts_adapter_success_outcome,
)
from pipeline.contracts.capabilities import (
    CapabilityRequest,
    CapabilityRequirements,
    ExecutionContext,
)
from pipeline.contracts.config import EffectiveConfig, RunOverrides
from pipeline.contracts.execution import StageAttempt, StageInstance, WorkflowRun
from pipeline.contracts.routing import RoutingDecision
from pipeline.contracts.vocabularies import (
    AttemptStatus,
    RunStatus,
    StageExecutionStatus,
)
from pipeline.fingerprints import sha256_text
from pipeline.ids import deterministic_id
from pipeline.storage import Database
from pipeline.storage.repositories.execution import (
    EffectiveConfigRepository,
    StageAttemptRepository,
    StageInstanceRepository,
    WorkflowRunRepository,
)


@pytest.fixture
def database(tmp_path):
    """Create a test database with migrations applied."""
    db_path = tmp_path / "test.sqlite3"
    database = Database(db_path)
    from pipeline.storage.migrations import MigrationRunner

    MigrationRunner(database).migrate()
    return database


@pytest.fixture
def registry():
    """Create a capability registry."""
    return CapabilityRegistry()


@pytest.fixture
def fake_provider(registry):
    """Create a fake capability provider."""
    return FakeCapabilityProvider(registry)


@pytest.fixture
def executor(database, registry, fake_provider):
    """Create a capability executor."""
    return CapabilityExecutor(database, registry, fake_provider)


@pytest.fixture
def base_setup(database):
    """Create base database records for capability execution."""
    run_id = deterministic_id("run", "test_run")
    stage_instance_id = deterministic_id("stage", run_id)
    attempt_id = deterministic_id("attempt", stage_instance_id)
    effective_config_id = deterministic_id("config", run_id)
    correlation_id = deterministic_id("corr", run_id)

    # Create required database records
    with database.transaction() as conn:
        # Create effective config
        effective_config = EffectiveConfig(
            schema_version="effective-config.v1",
            effective_config_id=effective_config_id,
            config_hash="0" * 64,
            workflow_id="test_workflow",
            workflow_version="1.0",
            system_policy_version="1.0",
            domain_profile_id="test_domain",
            domain_profile_version="1.0",
            channel_profile_id="test_channel",
            channel_profile_version="1.0",
            run_overrides=RunOverrides(schema_version="run-overrides.v1"),
            snapshot_artifact_id=None,
        )
        EffectiveConfigRepository(conn).insert(effective_config)

        # Create workflow run
        workflow_run = WorkflowRun(
            schema_version="workflow-run.v1",
            run_id=run_id,
            run_key=f"test_run:{run_id}",
            workflow_id="test_workflow",
            workflow_version="1.0",
            effective_config_id=effective_config_id,
            effective_config_hash="0" * 64,
            status=RunStatus.RUNNING,
            content_package_id=deterministic_id("package", run_id),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        WorkflowRunRepository(conn).insert(workflow_run)

        # Create stage instance
        stage_instance = StageInstance(
            schema_version="stage-instance.v1",
            stage_instance_id=stage_instance_id,
            run_id=run_id,
            node_id="test_node",
            logical_item_key="test_item",
            execution_status=StageExecutionStatus.RUNNING,
            acceptance_status="NOT_REQUIRED",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        StageInstanceRepository(conn).insert(stage_instance)

        # Create stage attempt
        stage_attempt = StageAttempt(
            schema_version="stage-attempt.v1",
            attempt_id=attempt_id,
            stage_instance_id=stage_instance_id,
            attempt_number=1,
            status=AttemptStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        StageAttemptRepository(conn).insert(stage_attempt)

    return {
        "run_id": run_id,
        "stage_instance_id": stage_instance_id,
        "attempt_id": attempt_id,
        "effective_config_id": effective_config_id,
        "correlation_id": correlation_id,
    }


@pytest.fixture
def base_routing_decision(base_setup):
    """Create a base routing decision."""
    capability_execution_id = deterministic_id("capexec", base_setup["attempt_id"])
    routing_decision_id = deterministic_id("route", capability_execution_id)
    return RoutingDecision(
        schema_version="routing-decision.v1",
        routing_decision_id=routing_decision_id,
        capability="test",
        implementation="fake",
        implementation_version="1.0.0",
        provider="fake",
        model="deterministic-fixture",
        provider_config_hash="0" * 64,
        fallback_chain=[],
        policy_version="1.0",
        reason_codes=["test"],
        candidate_exclusions=[],
        budget_context={},
        usage_context={},
        attempt=1,
        data_classification="PUBLIC",
        paid_fallback_authorized=False,
        created_at=datetime.now(UTC),
    )


def _create_request(
    capability: str,
    operation_version: str,
    payload: dict,
    payload_schema_version: str,
    idempotency_key: str,
) -> CapabilityRequest:
    """Create a capability request with the given payload."""
    payload_fingerprint = sha256_text(json.dumps(payload, sort_keys=True))
    return CapabilityRequest(
        schema_version="capability-request.v1",
        capability_execution_id=deterministic_id("capexec", idempotency_key),
        capability=capability,
        operation_version=operation_version,
        input_artifact_ids=[],
        payload_fingerprint=payload_fingerprint,
        requirements=CapabilityRequirements(
            schema_version="capability-requirements.v1",
            capability=capability,
        ),
        payload=payload,
        payload_schema_version=payload_schema_version,
        runtime_context={},
        idempotency_key=idempotency_key,
    )


def _create_context(ctx: dict) -> ExecutionContext:
    """Create an execution context."""
    return ExecutionContext(
        schema_version="execution-context.v1",
        run_id=ctx["run_id"],
        stage_instance_id=ctx["stage_instance_id"],
        attempt_id=ctx["attempt_id"],
        effective_config_id=ctx["effective_config_id"],
        correlation_id=ctx["correlation_id"],
        timeout_seconds=300,
        allowed_data_classification="PUBLIC",
    )


class TestSpeechGenerationCapability:
    """Tests for the speech_generation capability."""

    def test_speech_generation_continuous_strategy(
        self, executor, base_setup, base_routing_decision, fake_provider
    ):
        """Test speech_generation with CONTINUOUS strategy."""
        payload = {
            "script_id": "script_01",
            "script_version": "v1.0",
            "scene_ids": ["scene_01", "scene_02", "scene_03"],
            "strategy": "CONTINUOUS",
            "voice_config": {
                "provider": "elevenlabs",
                "model": "v2",
                "voice_id": "narrator_deep_male",
            },
            "narration_texts": {
                "scene_01": (
                    "The Arctic is warming four times faster than the global average."
                ),
                "scene_02": ("Satellite data shows accelerating ice loss since 1979."),
                "scene_03": ("Rising seas threaten coastal communities worldwide."),
            },
            "language": "en",
            "metadata": {},
        }

        fake_provider.register_outcome(
            sha256_text(json.dumps(payload, sort_keys=True)),
            create_speech_generation_success_outcome(
                scene_count=3, strategy="CONTINUOUS"
            ),
        )

        request = _create_request(
            capability="speech_generation",
            operation_version="v1",
            payload=payload,
            payload_schema_version="speech-generation-input.v1",
            idempotency_key=deterministic_id("idem", "speech_gen_continuous"),
        )
        context = _create_context(base_setup)
        routing_decision = base_routing_decision.model_copy(
            update={
                "capability": "speech_generation",
                "routing_decision_id": deterministic_id(
                    "route", "speech_gen_continuous"
                ),
            }
        )

        result = executor.execute(request, context, routing_decision)
        assert isinstance(result, ExecutionResult)
        assert result.execution_output.result.status.value == "SUCCEEDED"
        assert (
            len(result.execution_output.result.artifact_ids) >= 5
        )  # manifest + master + 3 scene audios
        assert "manifest_01" in result.execution_output.result.artifact_ids
        assert "audio_master_01" in result.execution_output.result.artifact_ids

    def test_speech_generation_scene_segmented_strategy(
        self, executor, base_setup, base_routing_decision, fake_provider
    ):
        """Test speech_generation with SCENE_SEGMENTED strategy."""
        payload = {
            "script_id": "script_01",
            "script_version": "v1.0",
            "scene_ids": ["scene_01", "scene_02", "scene_03"],
            "strategy": "SCENE_SEGMENTED",
            "voice_config": {
                "provider": "elevenlabs",
                "model": "v2",
                "voice_id": "narrator_deep_male",
            },
            "narration_texts": {
                "scene_01": (
                    "The Arctic is warming four times faster than the global average."
                ),
                "scene_02": ("Satellite data shows accelerating ice loss since 1979."),
                "scene_03": ("Rising seas threaten coastal communities worldwide."),
            },
            "language": "en",
            "metadata": {},
        }

        fake_provider.register_outcome(
            sha256_text(json.dumps(payload, sort_keys=True)),
            create_speech_generation_success_outcome(
                scene_count=3, strategy="SCENE_SEGMENTED"
            ),
        )

        request = _create_request(
            capability="speech_generation",
            operation_version="v1",
            payload=payload,
            payload_schema_version="speech-generation-input.v1",
            idempotency_key=deterministic_id("idem", "speech_gen_segmented"),
        )
        context = _create_context(base_setup)
        routing_decision = base_routing_decision.model_copy(
            update={
                "capability": "speech_generation",
                "routing_decision_id": deterministic_id(
                    "route", "speech_gen_segmented"
                ),
            }
        )

        result = executor.execute(request, context, routing_decision)
        assert isinstance(result, ExecutionResult)
        assert result.execution_output.result.status.value == "SUCCEEDED"
        assert len(result.execution_output.result.artifact_ids) >= 5
        assert "manifest_01" in result.execution_output.result.artifact_ids
        assert "audio_master_01" in result.execution_output.result.artifact_ids


class TestTTSAdapterCapability:
    """Tests for the tts_adapter capability."""

    def test_tts_adapter_success(
        self, executor, base_setup, base_routing_decision, fake_provider
    ):
        """Test tts_adapter with successful outcome."""
        payload = {
            "narration_text": (
                "The Arctic is warming four times faster than the global average."
            ),
            "voice_id": "narrator_deep_male",
            "provider": "elevenlabs",
            "model": "v2",
            "voice_config": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
            "sample_rate": 24000,
            "metadata": {},
        }

        fake_provider.register_outcome(
            sha256_text(json.dumps(payload, sort_keys=True)),
            create_tts_adapter_success_outcome(),
        )

        request = _create_request(
            capability="tts_adapter",
            operation_version="v1",
            payload=payload,
            payload_schema_version="tts-adapter-input.v1",
            idempotency_key=deterministic_id("idem", "tts_adapter"),
        )
        context = _create_context(base_setup)
        routing_decision = base_routing_decision.model_copy(
            update={
                "capability": "tts_adapter",
                "routing_decision_id": deterministic_id("route", "tts_adapter"),
            }
        )

        result = executor.execute(request, context, routing_decision)
        assert isinstance(result, ExecutionResult)
        assert result.execution_output.result.status.value == "SUCCEEDED"
        assert "audio_tts_01" in result.execution_output.result.artifact_ids


class TestASRAlignmentCapability:
    """Tests for the asr_alignment capability."""

    def test_asr_alignment_success(
        self, executor, base_setup, base_routing_decision, fake_provider
    ):
        """Test asr_alignment with successful outcome."""
        payload = {
            "audio_artifact_id": "audio_scene_01",
            "narration_text": (
                "The Arctic is warming four times faster than the global average."
            ),
            "language": "en",
            "metadata": {
                "asr_model": "whisper_large_v3",
            },
        }

        fake_provider.register_outcome(
            sha256_text(json.dumps(payload, sort_keys=True)),
            create_asr_alignment_success_outcome(scene_count=3),
        )

        request = _create_request(
            capability="asr_alignment",
            operation_version="v1",
            payload=payload,
            payload_schema_version="asr-alignment-input.v1",
            idempotency_key=deterministic_id("idem", "asr_alignment"),
        )
        context = _create_context(base_setup)
        routing_decision = base_routing_decision.model_copy(
            update={
                "capability": "asr_alignment",
                "routing_decision_id": deterministic_id("route", "asr_alignment"),
            }
        )

        result = executor.execute(request, context, routing_decision)
        assert isinstance(result, ExecutionResult)
        assert result.execution_output.result.status.value == "SUCCEEDED"
        assert "alignment_01" in result.execution_output.result.artifact_ids
        # Check for audio_timing and word_timestamp artifacts
        audio_timing_count = sum(
            1
            for a in result.execution_output.result.artifact_ids
            if a.startswith("audio_timing_")
        )
        word_ts_count = sum(
            1
            for a in result.execution_output.result.artifact_ids
            if a.startswith("word_ts_")
        )
        assert audio_timing_count == 3
        assert word_ts_count == 15  # 5 words per scene * 3 scenes


class TestAudioQCCapability:
    """Tests for the audio_qc capability."""

    def test_audio_qc_pass(
        self, executor, base_setup, base_routing_decision, fake_provider
    ):
        """Test audio_qc with fidelity pass."""
        payload = {
            "audio_artifact_id": "audio_scene_01",
            "expected_narration_text": (
                "The Arctic is warming four times faster than the global average."
            ),
            "target_loudness_lufs": -24.0,
            "target_peak_db": -1.0,
            "metadata": {},
        }

        fake_provider.register_outcome(
            sha256_text(json.dumps(payload, sort_keys=True)),
            create_audio_qc_success_outcome(fidelity_pass=True),
        )

        request = _create_request(
            capability="audio_qc",
            operation_version="v1",
            payload=payload,
            payload_schema_version="audio-qc-input.v1",
            idempotency_key=deterministic_id("idem", "audio_qc_pass"),
        )
        context = _create_context(base_setup)
        routing_decision = base_routing_decision.model_copy(
            update={
                "capability": "audio_qc",
                "routing_decision_id": deterministic_id("route", "audio_qc_pass"),
            }
        )

        result = executor.execute(request, context, routing_decision)
        assert isinstance(result, ExecutionResult)
        assert result.execution_output.result.status.value == "SUCCEEDED"
        assert "qc_report_01" in result.execution_output.result.artifact_ids
        # Check metadata for fidelity_pass
        assert result.execution_output.result.metadata.get("fidelity_pass") is True

    def test_audio_qc_fail_detects_omitted_changed_phrases(
        self, executor, base_setup, base_routing_decision, fake_provider
    ):
        """Test audio_qc failure detects omitted/changed phrases."""
        payload = {
            "audio_artifact_id": "audio_scene_01",
            "expected_narration_text": (
                "The Arctic is warming four times faster than the global average."
            ),
            "target_loudness_lufs": -24.0,
            "target_peak_db": -1.0,
            "metadata": {},
        }

        fake_provider.register_outcome(
            sha256_text(json.dumps(payload, sort_keys=True)),
            create_audio_qc_failure_outcome(),
        )

        request = _create_request(
            capability="audio_qc",
            operation_version="v1",
            payload=payload,
            payload_schema_version="audio-qc-input.v1",
            idempotency_key=deterministic_id("idem", "audio_qc_fail"),
        )
        context = _create_context(base_setup)
        routing_decision = base_routing_decision.model_copy(
            update={
                "capability": "audio_qc",
                "routing_decision_id": deterministic_id("route", "audio_qc_fail"),
            }
        )

        result = executor.execute(request, context, routing_decision)
        assert isinstance(result, ExecutionError)
        assert result.normalized_error is not None


class TestAllFailureCategories:
    """Tests that all failure categories are exercised for audio capabilities."""

    @pytest.mark.parametrize(
        "capability,payload_schema_version,factory_name",
        [
            (
                "speech_generation",
                "speech-generation-input.v1",
                "create_speech_generation_success_outcome",
            ),
            (
                "tts_adapter",
                "tts-adapter-input.v1",
                "create_tts_adapter_success_outcome",
            ),
            (
                "asr_alignment",
                "asr-alignment-input.v1",
                "create_asr_alignment_success_outcome",
            ),
            ("audio_qc", "audio-qc-input.v1", "create_audio_qc_success_outcome"),
        ],
    )
    def test_all_failure_categories_for_audio_capabilities(
        self,
        executor,
        base_setup,
        base_routing_decision,
        fake_provider,
        capability,
        payload_schema_version,
        factory_name,
    ):
        """Test that all failure categories can be simulated for audio capabilities."""
        from pipeline.capabilities import (
            outcome_authentication_failure,
            outcome_authorization_failure,
            outcome_budget_exceeded,
            outcome_configuration,
            outcome_human_review,
            outcome_internal,
            outcome_media_integrity,
            outcome_permanent_provider,
            outcome_policy,
            outcome_quality_failure,
            outcome_quota_exceeded,
            outcome_rate_limit,
            outcome_timeout_unknown,
            outcome_transient_provider,
            outcome_validation_failure,
        )

        # Base payload for each capability
        base_payloads = {
            "speech_generation": {
                "script_id": "script_01",
                "script_version": "v1.0",
                "scene_ids": ["scene_01"],
                "strategy": "CONTINUOUS",
                "voice_config": {
                    "provider": "elevenlabs",
                    "model": "v2",
                    "voice_id": "test",
                },
                "narration_texts": {"scene_01": "Test narration."},
                "language": "en",
                "metadata": {},
            },
            "tts_adapter": {
                "narration_text": "Test narration.",
                "voice_id": "test",
                "provider": "elevenlabs",
                "model": "v2",
                "voice_config": {},
                "sample_rate": 24000,
                "metadata": {},
            },
            "asr_alignment": {
                "audio_artifact_id": "audio_01",
                "narration_text": "Test narration.",
                "language": "en",
                "metadata": {},
            },
            "audio_qc": {
                "audio_artifact_id": "audio_01",
                "expected_narration_text": "Test narration.",
                "target_loudness_lufs": -24.0,
                "target_peak_db": -1.0,
                "metadata": {},
            },
        }

        payload = base_payloads[capability]

        failure_factories = {
            "validation": outcome_validation_failure,
            "authentication": outcome_authentication_failure,
            "authorization": outcome_authorization_failure,
            "rate_limit": outcome_rate_limit,
            "quota": outcome_quota_exceeded,
            "transient": outcome_transient_provider,
            "permanent": outcome_permanent_provider,
            "timeout_unknown": outcome_timeout_unknown,
            "media": outcome_media_integrity,
            "quality": outcome_quality_failure,
            "budget": outcome_budget_exceeded,
            "configuration": outcome_configuration,
            "human_review": outcome_human_review,
            "policy": outcome_policy,
            "internal": outcome_internal,
        }

        for failure_name, factory in failure_factories.items():
            fake_provider.register_outcome(
                sha256_text(json.dumps(payload, sort_keys=True)),
                factory(),
            )

            request = _create_request(
                capability=capability,
                operation_version="v1",
                payload=payload,
                payload_schema_version=payload_schema_version,
                idempotency_key=deterministic_id(
                    "idem", f"{capability}_{failure_name}"
                ),
            )
            context = _create_context(base_setup)
            routing_decision = base_routing_decision.model_copy(
                update={
                    "capability": capability,
                    "routing_decision_id": deterministic_id(
                        "route", f"{capability}_{failure_name}"
                    ),
                }
            )

            result = executor.execute(request, context, routing_decision)
            assert isinstance(result, ExecutionError)
            assert result.normalized_error is not None, (
                f"{capability}/{failure_name} should have normalized error"
            )


class TestIdempotency:
    """Tests for idempotent execution of audio capabilities."""

    def test_speech_generation_idempotent_replay(
        self, executor, base_setup, base_routing_decision, fake_provider
    ):
        """Test that repeated speech_generation execution returns cached result."""
        payload = {
            "script_id": "script_01",
            "script_version": "v1.0",
            "scene_ids": ["scene_01"],
            "strategy": "CONTINUOUS",
            "voice_config": {
                "provider": "elevenlabs",
                "model": "v2",
                "voice_id": "test",
            },
            "narration_texts": {"scene_01": "Test narration."},
            "language": "en",
            "metadata": {},
        }

        fake_provider.register_outcome(
            sha256_text(json.dumps(payload, sort_keys=True)),
            create_speech_generation_success_outcome(scene_count=1),
        )

        request = _create_request(
            capability="speech_generation",
            operation_version="v1",
            payload=payload,
            payload_schema_version="speech-generation-input.v1",
            idempotency_key=deterministic_id("idem", "speech_gen_idempotent"),
        )
        context = _create_context(base_setup)
        routing_decision = base_routing_decision.model_copy(
            update={
                "capability": "speech_generation",
                "routing_decision_id": deterministic_id(
                    "route", "speech_gen_idempotent"
                ),
            }
        )

        # First execution
        result1 = executor.execute(request, context, routing_decision)
        assert isinstance(result1, ExecutionResult)
        assert result1.execution_output.result.status.value == "SUCCEEDED"

        # Second execution with same idempotency key
        result2 = executor.execute(request, context, routing_decision)
        assert isinstance(result2, ExecutionResult)
        assert result2.execution_output.result.status.value == "SUCCEEDED"
        # Should return same artifacts (idempotent replay)
        assert (
            result1.execution_output.result.artifact_ids
            == result2.execution_output.result.artifact_ids
        )


class TestContinuousAndSceneSegmentedEquivalence:
    """Tests that CONTINUOUS and SCENE_SEGMENTED strategies produce
    equivalent scene timing."""

    def test_both_strategies_produce_scene_addressable_timing(
        self, executor, base_setup, base_routing_decision, fake_provider
    ):
        """Both strategies should resolve to scene-addressable audio artifacts."""
        # CONTINUOUS strategy
        continuous_payload = {
            "script_id": "script_01",
            "script_version": "v1.0",
            "scene_ids": ["scene_01", "scene_02"],
            "strategy": "CONTINUOUS",
            "voice_config": {
                "provider": "elevenlabs",
                "model": "v2",
                "voice_id": "test",
            },
            "narration_texts": {
                "scene_01": "First scene narration.",
                "scene_02": "Second scene narration.",
            },
            "language": "en",
            "metadata": {},
        }

        fake_provider.register_outcome(
            sha256_text(json.dumps(continuous_payload, sort_keys=True)),
            create_speech_generation_success_outcome(
                scene_count=2, strategy="CONTINUOUS"
            ),
        )

        continuous_request = _create_request(
            capability="speech_generation",
            operation_version="v1",
            payload=continuous_payload,
            payload_schema_version="speech-generation-input.v1",
            idempotency_key=deterministic_id("idem", "speech_gen_continuous_equiv"),
        )
        continuous_context = _create_context(base_setup)
        continuous_routing = base_routing_decision.model_copy(
            update={
                "capability": "speech_generation",
                "routing_decision_id": deterministic_id(
                    "route", "speech_gen_continuous_equiv"
                ),
            }
        )

        continuous_result = executor.execute(
            continuous_request, continuous_context, continuous_routing
        )
        assert isinstance(continuous_result, ExecutionResult)
        assert continuous_result.execution_output.result.status.value == "SUCCEEDED"

        # SCENE_SEGMENTED strategy
        segmented_payload = {
            "script_id": "script_01",
            "script_version": "v1.0",
            "scene_ids": ["scene_01", "scene_02"],
            "strategy": "SCENE_SEGMENTED",
            "voice_config": {
                "provider": "elevenlabs",
                "model": "v2",
                "voice_id": "test",
            },
            "narration_texts": {
                "scene_01": "First scene narration.",
                "scene_02": "Second scene narration.",
            },
            "language": "en",
            "metadata": {},
        }

        fake_provider.register_outcome(
            sha256_text(json.dumps(segmented_payload, sort_keys=True)),
            create_speech_generation_success_outcome(
                scene_count=2, strategy="SCENE_SEGMENTED"
            ),
        )

        segmented_request = _create_request(
            capability="speech_generation",
            operation_version="v1",
            payload=segmented_payload,
            payload_schema_version="speech-generation-input.v1",
            idempotency_key=deterministic_id("idem", "speech_gen_segmented_equiv"),
        )
        segmented_context = _create_context(base_setup)
        segmented_routing = base_routing_decision.model_copy(
            update={
                "capability": "speech_generation",
                "routing_decision_id": deterministic_id(
                    "route", "speech_gen_segmented_equiv"
                ),
            }
        )

        segmented_result = executor.execute(
            segmented_request, segmented_context, segmented_routing
        )
        assert isinstance(segmented_result, ExecutionResult)
        assert segmented_result.execution_output.result.status.value == "SUCCEEDED"

        # Both should produce master audio and per-scene audio artifacts
        continuous_artifacts = set(
            continuous_result.execution_output.result.artifact_ids
        )
        segmented_artifacts = set(segmented_result.execution_output.result.artifact_ids)

        assert "audio_master_01" in continuous_artifacts
        assert "audio_master_01" in segmented_artifacts
        assert "audio_scene_01" in continuous_artifacts
        assert "audio_scene_01" in segmented_artifacts
        assert "audio_scene_02" in continuous_artifacts
        assert "audio_scene_02" in segmented_artifacts
