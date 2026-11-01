"""Tests for capability registry and fake provider fixes."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from pipeline.capabilities import (
    CapabilityExecutionInput,
    CapabilityNotFoundError,
    CapabilityRegistry,
    CapabilityRequirementMismatchError,
    FakeCapabilityProvider,
    create_success_outcome,
)
from pipeline.capabilities.models import (
    CapabilityImplementation,
    CapabilityRegistration,
    ScriptedOutcome,
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
from pipeline.storage.migrations import MigrationRunner
from pipeline.storage.repositories.execution import (
    EffectiveConfigRepository,
    StageAttemptRepository,
    StageInstanceRepository,
    WorkflowRunRepository,
)


@pytest.fixture
def registry() -> CapabilityRegistry:
    """Create a capability registry."""
    return CapabilityRegistry()


@pytest.fixture
def fake_provider(registry: CapabilityRegistry) -> FakeCapabilityProvider:
    """Create a fake capability provider."""
    return FakeCapabilityProvider(registry)


@pytest.fixture
def database(tmp_path) -> Database:
    """Create a test database with migrations applied."""
    db_path = tmp_path / "test.sqlite3"
    database = Database(db_path)
    MigrationRunner(database).migrate()
    return database


@pytest.fixture
def base_setup(database: Database) -> dict:
    """Create base database records for capability execution."""
    run_id = deterministic_id("run", "test_run")
    stage_instance_id = deterministic_id("stage", run_id)
    attempt_id = deterministic_id("attempt", stage_instance_id)
    effective_config_id = deterministic_id("config", run_id)
    correlation_id = deterministic_id("corr", run_id)

    with database.transaction() as conn:
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
def base_routing_decision(base_setup: dict) -> RoutingDecision:
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


def _make_impl(
    capability: str,
    operation_version: str,
    provider: str,
    model: str | None = None,
    declared_features: list[str] | None = None,
    supported_locales: list[str] | None = None,
) -> CapabilityImplementation:
    """Create a test capability implementation."""
    return CapabilityImplementation(
        schema_version="capability-implementation.v1",
        implementation_id=deterministic_id(
            "impl", capability, operation_version, provider
        ),
        capability=capability,
        operation_version=operation_version,
        implementation_version="1.0.0",
        provider=provider,
        model=model,
        declared_features=declared_features or [],
        supported_locales=supported_locales or [],
        data_classification="PUBLIC",
        estimated_cost_minor=100,
        max_latency_seconds=30,
        requires_network=False,
        config_hash="0" * 64,
    )


class TestRegistryGet:
    """Tests for CapabilityRegistry.get behavior."""

    def test_get_exact_provider_match(self, registry: CapabilityRegistry) -> None:
        """get returns the exact provider match when several implementations exist."""
        impl1 = _make_impl("test_cap", "v1", "provider_a")
        impl2 = _make_impl("test_cap", "v1", "provider_b")
        impl3 = _make_impl("test_cap", "v1", "provider_c")

        registry.register(
            CapabilityRegistration(
                schema_version="capability-registration.v1",
                capability="test_cap",
                operation_version="v1",
                implementation=impl1,
            )
        )
        registry.register(
            CapabilityRegistration(
                schema_version="capability-registration.v1",
                capability="test_cap",
                operation_version="v1",
                implementation=impl2,
            )
        )
        registry.register(
            CapabilityRegistration(
                schema_version="capability-registration.v1",
                capability="test_cap",
                operation_version="v1",
                implementation=impl3,
            )
        )

        # Exact provider match
        result = registry.get("test_cap", "v1", provider="provider_b")
        assert result.provider == "provider_b"
        assert result.implementation_id == impl2.implementation_id

    def test_get_exact_feature_match(self, registry: CapabilityRegistry) -> None:
        """get returns the exact feature match when several implementations exist."""
        impl1 = _make_impl(
            "test_cap", "v1", "provider_a", declared_features=["feature_x"]
        )
        impl2 = _make_impl(
            "test_cap", "v1", "provider_a", declared_features=["feature_y"]
        )
        impl3 = _make_impl(
            "test_cap",
            "v1",
            "provider_a",
            declared_features=["feature_x", "feature_y"],
        )

        registry.register(
            CapabilityRegistration(
                schema_version="capability-registration.v1",
                capability="test_cap",
                operation_version="v1",
                implementation=impl1,
            )
        )
        registry.register(
            CapabilityRegistration(
                schema_version="capability-registration.v1",
                capability="test_cap",
                operation_version="v1",
                implementation=impl2,
            )
        )
        registry.register(
            CapabilityRegistration(
                schema_version="capability-registration.v1",
                capability="test_cap",
                operation_version="v1",
                implementation=impl3,
            )
        )

        # Request feature_x - should match impl1 or impl3 (first match)
        result = registry.get("test_cap", "v1", required_features=["feature_x"])
        assert "feature_x" in result.declared_features

        # Request both feature_x and feature_y - should match impl3
        result = registry.get(
            "test_cap", "v1", required_features=["feature_x", "feature_y"]
        )
        assert set(result.declared_features) == {"feature_x", "feature_y"}

    def test_get_exact_locale_match(self, registry: CapabilityRegistry) -> None:
        """get returns the exact locale match when several implementations exist."""
        impl1 = _make_impl("test_cap", "v1", "provider_a", supported_locales=["en-US"])
        impl2 = _make_impl("test_cap", "v1", "provider_a", supported_locales=["fr-FR"])
        impl3 = _make_impl(
            "test_cap",
            "v1",
            "provider_a",
            supported_locales=["en-US", "fr-FR"],
        )

        registry.register(
            CapabilityRegistration(
                schema_version="capability-registration.v1",
                capability="test_cap",
                operation_version="v1",
                implementation=impl1,
            )
        )
        registry.register(
            CapabilityRegistration(
                schema_version="capability-registration.v1",
                capability="test_cap",
                operation_version="v1",
                implementation=impl2,
            )
        )
        registry.register(
            CapabilityRegistration(
                schema_version="capability-registration.v1",
                capability="test_cap",
                operation_version="v1",
                implementation=impl3,
            )
        )

        # Request en-US - should match impl1 or impl3 (first match)
        result = registry.get("test_cap", "v1", locale="en-US")
        assert "en-US" in result.supported_locales

        # Request fr-FR - should match impl2 or impl3
        result = registry.get("test_cap", "v1", locale="fr-FR")
        assert "fr-FR" in result.supported_locales

    def test_get_exact_model_match(self, registry: CapabilityRegistry) -> None:
        """get returns the exact model match when several implementations exist."""
        impl1 = _make_impl("test_cap", "v1", "provider_a", model="model_x")
        impl2 = _make_impl("test_cap", "v1", "provider_a", model="model_y")

        registry.register(
            CapabilityRegistration(
                schema_version="capability-registration.v1",
                capability="test_cap",
                operation_version="v1",
                implementation=impl1,
            )
        )
        registry.register(
            CapabilityRegistration(
                schema_version="capability-registration.v1",
                capability="test_cap",
                operation_version="v1",
                implementation=impl2,
            )
        )

        result = registry.get("test_cap", "v1", model="model_y")
        assert result.model == "model_y"

    def test_get_raises_capability_not_found_error(
        self, registry: CapabilityRegistry
    ) -> None:
        """get raises CapabilityNotFoundError for unknown capability/version."""
        with pytest.raises(CapabilityNotFoundError) as exc_info:
            registry.get("unknown_cap", "v1")

        assert exc_info.value.capability == "unknown_cap"
        assert exc_info.value.operation_version == "v1"

        with pytest.raises(CapabilityNotFoundError) as exc_info:
            registry.get("test_cap", "unknown_version")

        assert exc_info.value.capability == "test_cap"
        assert exc_info.value.operation_version == "unknown_version"

    def test_get_raises_requirement_mismatch_provider(
        self, registry: CapabilityRegistry
    ) -> None:
        """get raises CapabilityRequirementMismatchError for unsupported provider."""
        impl = _make_impl("test_cap", "v1", "provider_a")
        registry.register(
            CapabilityRegistration(
                schema_version="capability-registration.v1",
                capability="test_cap",
                operation_version="v1",
                implementation=impl,
            )
        )

        with pytest.raises(CapabilityRequirementMismatchError) as exc_info:
            registry.get("test_cap", "v1", provider="provider_b")

        assert exc_info.value.capability == "test_cap"
        assert exc_info.value.operation_version == "v1"
        assert "provider=" in exc_info.value.reason

    def test_get_raises_requirement_mismatch_model(
        self, registry: CapabilityRegistry
    ) -> None:
        """get raises CapabilityRequirementMismatchError for unsupported model."""
        impl = _make_impl("test_cap", "v1", "provider_a", model="model_x")
        registry.register(
            CapabilityRegistration(
                schema_version="capability-registration.v1",
                capability="test_cap",
                operation_version="v1",
                implementation=impl,
            )
        )

        with pytest.raises(CapabilityRequirementMismatchError) as exc_info:
            registry.get("test_cap", "v1", model="model_y")

        assert "model=" in exc_info.value.reason

    def test_get_raises_requirement_mismatch_features(
        self, registry: CapabilityRegistry
    ) -> None:
        """get raises CapabilityRequirementMismatchError for unsupported features."""
        impl = _make_impl(
            "test_cap", "v1", "provider_a", declared_features=["feature_x"]
        )
        registry.register(
            CapabilityRegistration(
                schema_version="capability-registration.v1",
                capability="test_cap",
                operation_version="v1",
                implementation=impl,
            )
        )

        with pytest.raises(CapabilityRequirementMismatchError) as exc_info:
            registry.get("test_cap", "v1", required_features=["feature_y"])

        assert "required_features=" in exc_info.value.reason

    def test_get_raises_requirement_mismatch_locale(
        self, registry: CapabilityRegistry
    ) -> None:
        """get raises CapabilityRequirementMismatchError for unsupported locale."""
        impl = _make_impl("test_cap", "v1", "provider_a", supported_locales=["en-US"])
        registry.register(
            CapabilityRegistration(
                schema_version="capability-registration.v1",
                capability="test_cap",
                operation_version="v1",
                implementation=impl,
            )
        )

        with pytest.raises(CapabilityRequirementMismatchError) as exc_info:
            registry.get("test_cap", "v1", locale="fr-FR")

        assert "locale=" in exc_info.value.reason

    def test_get_returns_capability_implementation_not_optional(
        self, registry: CapabilityRegistry
    ) -> None:
        """get returns CapabilityImplementation (not Optional)."""
        impl = _make_impl("test_cap", "v1", "provider_a")
        registry.register(
            CapabilityRegistration(
                schema_version="capability-registration.v1",
                capability="test_cap",
                operation_version="v1",
                implementation=impl,
            )
        )

        result = registry.get("test_cap", "v1")
        # Type checker should infer CapabilityImplementation, not Optional
        assert isinstance(result, CapabilityImplementation)
        assert result is not None


class TestFakeProviderExceptions:
    """Tests for FakeCapabilityProvider exception handling."""

    def test_fake_provider_raises_named_builtin_exception(
        self,
        fake_provider: FakeCapabilityProvider,
        base_setup: dict,
        base_routing_decision: RoutingDecision,
    ) -> None:
        """Fake provider raises the named builtin exception."""
        payload = {"test": "data"}
        fingerprint = sha256_text(json.dumps(payload, sort_keys=True))

        outcome = ScriptedOutcome(
            schema_version="scripted-outcome.v1",
            status="SUCCEEDED",
            artifact_ids=[],
            metadata={},
            raise_exception=True,
            exception_type="ValueError",
            exception_message="Test error message",
        )
        fake_provider.register_outcome(fingerprint, outcome)

        request = _create_request(
            capability="test_cap",
            operation_version="v1",
            payload=payload,
            payload_schema_version="test.v1",
            idempotency_key=deterministic_id("idem", "test_exception"),
        )
        context = _create_context(base_setup)
        routing_decision = base_routing_decision.model_copy(
            update={"capability": "test_cap"}
        )

        with pytest.raises(ValueError) as exc_info:
            fake_provider.execute(
                CapabilityExecutionInput(
                    schema_version="capability-execution-input.v1",
                    request=request,
                    context=context,
                    routing_decision=routing_decision,
                )
            )
        assert str(exc_info.value) == "Test error message"

    def test_fake_provider_unknown_exception_type_fails_clearly(
        self,
        fake_provider: FakeCapabilityProvider,
        base_setup: dict,
        base_routing_decision: RoutingDecision,
    ) -> None:
        """Unknown exception types fail with clear ValueError."""
        payload = {"test": "data"}
        fingerprint = sha256_text(json.dumps(payload, sort_keys=True))

        outcome = ScriptedOutcome(
            schema_version="scripted-outcome.v1",
            status="SUCCEEDED",
            artifact_ids=[],
            metadata={},
            raise_exception=True,
            exception_type="NonExistentException",
            exception_message="Should fail",
        )
        fake_provider.register_outcome(fingerprint, outcome)

        request = _create_request(
            capability="test_cap",
            operation_version="v1",
            payload=payload,
            payload_schema_version="test.v1",
            idempotency_key=deterministic_id("idem", "test_unknown_exception"),
        )
        context = _create_context(base_setup)
        routing_decision = base_routing_decision.model_copy(
            update={"capability": "test_cap"}
        )

        with pytest.raises(ValueError) as exc_info:
            fake_provider.execute(
                CapabilityExecutionInput(
                    schema_version="capability-execution-input.v1",
                    request=request,
                    context=context,
                    routing_decision=routing_decision,
                )
            )
        assert "Invalid exception_type" in str(exc_info.value)
        assert "NonExistentException" in str(exc_info.value)

    def test_fake_provider_non_exception_type_fails_clearly(
        self,
        fake_provider: FakeCapabilityProvider,
        base_setup: dict,
        base_routing_decision: RoutingDecision,
    ) -> None:
        """Non-BaseException types (e.g., builtin functions) fail with
        clear ValueError."""
        payload = {"test": "data"}
        fingerprint = sha256_text(json.dumps(payload, sort_keys=True))

        outcome = ScriptedOutcome(
            schema_version="scripted-outcome.v1",
            status="SUCCEEDED",
            artifact_ids=[],
            metadata={},
            raise_exception=True,
            exception_type="print",  # builtin function, not exception
            exception_message="Should fail",
        )
        fake_provider.register_outcome(fingerprint, outcome)

        request = _create_request(
            capability="test_cap",
            operation_version="v1",
            payload=payload,
            payload_schema_version="test.v1",
            idempotency_key=deterministic_id("idem", "test_non_exception"),
        )
        context = _create_context(base_setup)
        routing_decision = base_routing_decision.model_copy(
            update={"capability": "test_cap"}
        )

        with pytest.raises(ValueError) as exc_info:
            fake_provider.execute(
                CapabilityExecutionInput(
                    schema_version="capability-execution-input.v1",
                    request=request,
                    context=context,
                    routing_decision=routing_decision,
                )
            )
        assert "Invalid exception_type" in str(exc_info.value)
        assert "print" in str(exc_info.value)


class TestFakeProviderDeterministicIds:
    """Tests for deterministic IDs in FakeCapabilityProvider."""

    def test_two_instances_same_operation_id_and_artifact_ids(
        self,
        registry: CapabilityRegistry,
        base_setup: dict,
        base_routing_decision: RoutingDecision,
    ) -> None:
        """Two independent FakeCapabilityProvider instances produce the
        same operation ID and default/success artifact IDs for the same
        request/execution.
        """
        payload = {"test": "data"}
        sha256_text(json.dumps(payload, sort_keys=True))
        idempotency_key = deterministic_id("idem", "test_deterministic")

        # Create first provider instance
        provider1 = FakeCapabilityProvider(registry)
        request1 = _create_request(
            capability="test_cap",
            operation_version="v1",
            payload=payload,
            payload_schema_version="test.v1",
            idempotency_key=idempotency_key,
        )
        context1 = _create_context(base_setup)
        routing_decision1 = base_routing_decision.model_copy(
            update={"capability": "test_cap"}
        )

        output1 = provider1.execute(
            CapabilityExecutionInput(
                schema_version="capability-execution-input.v1",
                request=request1,
                context=context1,
                routing_decision=routing_decision1,
            )
        )

        # Create second provider instance (independent)
        provider2 = FakeCapabilityProvider(registry)
        request2 = _create_request(
            capability="test_cap",
            operation_version="v1",
            payload=payload,
            payload_schema_version="test.v1",
            idempotency_key=idempotency_key,
        )
        context2 = _create_context(base_setup)
        routing_decision2 = base_routing_decision.model_copy(
            update={"capability": "test_cap"}
        )

        output2 = provider2.execute(
            CapabilityExecutionInput(
                schema_version="capability-execution-input.v1",
                request=request2,
                context=context2,
                routing_decision=routing_decision2,
            )
        )

        # Same operation ID (deterministic from fingerprint)
        assert (
            output1.provider_invocation.operation_id
            == output2.provider_invocation.operation_id
        )

        # Same default artifact IDs (deterministic from fingerprint)
        assert output1.result.artifact_ids == output2.result.artifact_ids

        # Same invocation ID (deterministic from execution_id)
        assert (
            output1.provider_invocation.invocation_id
            == output2.provider_invocation.invocation_id
        )

    def test_default_artifact_ids_are_scoped_to_request_fingerprint(
        self,
        fake_provider: FakeCapabilityProvider,
        base_setup: dict,
        base_routing_decision: RoutingDecision,
    ) -> None:
        """Different fake requests must not share the same default artifact ID."""
        context = _create_context(base_setup)
        routing_decision = base_routing_decision.model_copy(
            update={"capability": "test_cap"}
        )

        outputs = []
        for payload in ({"test": "one"}, {"test": "two"}):
            request = _create_request(
                capability="test_cap",
                operation_version="v1",
                payload=payload,
                payload_schema_version="test.v1",
                idempotency_key=deterministic_id("idem", str(payload)),
            )
            outputs.append(
                fake_provider.execute(
                    CapabilityExecutionInput(
                        schema_version="capability-execution-input.v1",
                        request=request,
                        context=context,
                        routing_decision=routing_decision,
                    )
                )
            )

        assert outputs[0].result.artifact_ids != outputs[1].result.artifact_ids

    def test_create_success_outcome_deterministic_artifact_ids(self) -> None:
        """create_success_outcome produces deterministic artifact IDs."""
        outcome1 = create_success_outcome()
        outcome2 = create_success_outcome()

        assert outcome1.artifact_ids == outcome2.artifact_ids
        # Should be deterministic_id based, not uuid
        assert outcome1.artifact_ids[0].startswith("artifact_")

    def test_registered_outcome_preserves_artifact_ids(
        self,
        fake_provider: FakeCapabilityProvider,
        base_setup: dict,
        base_routing_decision: RoutingDecision,
    ) -> None:
        """Registered outcomes preserve their explicit artifact IDs."""
        payload = {"test": "data"}
        fingerprint = sha256_text(json.dumps(payload, sort_keys=True))

        custom_artifact = "my_custom_artifact_01"
        outcome = create_success_outcome(artifact_ids=[custom_artifact])
        fake_provider.register_outcome(fingerprint, outcome)

        request = _create_request(
            capability="test_cap",
            operation_version="v1",
            payload=payload,
            payload_schema_version="test.v1",
            idempotency_key=deterministic_id("idem", "test_custom_artifact"),
        )
        context = _create_context(base_setup)
        routing_decision = base_routing_decision.model_copy(
            update={"capability": "test_cap"}
        )

        output = fake_provider.execute(
            CapabilityExecutionInput(
                schema_version="capability-execution-input.v1",
                request=request,
                context=context,
                routing_decision=routing_decision,
            )
        )

        assert output.result.artifact_ids == [custom_artifact]
