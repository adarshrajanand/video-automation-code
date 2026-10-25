"""Capability executor with idempotency, budget guard, and persistence."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pipeline.capabilities.errors import create_normalized_error
from pipeline.capabilities.fake import FakeCapabilityProvider
from pipeline.capabilities.models import (
    CapabilityExecutionInput,
    CapabilityExecutionOutput,
)
from pipeline.capabilities.registry import (
    CapabilityRegistry,
)
from pipeline.contracts.base import NormalizedError
from pipeline.contracts.capabilities import (
    BudgetReservation,
    BudgetReservationStatus,
    BudgetScopeType,
    CapabilityExecution,
    CapabilityExecutionStatus,
    CapabilityRequest,
    CapabilityResult,
    CapabilityResultStatus,
    ExecutionContext,
    IdempotencyRecord,
    IdempotencyStatus,
)
from pipeline.contracts.routing import (
    ResourceAssignment,
    RoutingDecision,
)
from pipeline.contracts.vocabularies import (
    FailureCode,
    Severity,
)
from pipeline.fingerprints import canonical_datetime
from pipeline.ids import deterministic_id
from pipeline.storage.database import Database
from pipeline.storage.errors import NotFoundError
from pipeline.storage.repositories.capabilities import (
    BudgetReservationRepository,
    CapabilityExecutionRepository,
    ProviderInvocationRepository,
    RoutingDecisionRepository,
    UsageRecordRepository,
)
from pipeline.storage.repositories.control import IdempotencyRecordRepository

if TYPE_CHECKING:
    pass


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Result of a capability execution attempt."""

    execution_output: CapabilityExecutionOutput
    idempotency_record: IdempotencyRecord
    budget_reservation: BudgetReservation | None = None


@dataclass(frozen=True, slots=True)
class ExecutionError:
    """Error from a capability execution attempt."""

    normalized_error: NormalizedError
    idempotency_record: IdempotencyRecord | None = None
    budget_reservation: BudgetReservation | None = None


class _BudgetCheckResult:
    """Internal result of budget check and optional reservation."""

    def __init__(
        self,
        *,
        allowed: bool,
        reservation: BudgetReservation | None = None,
        error: NormalizedError | None = None,
    ) -> None:
        self.allowed = allowed
        self.reservation = reservation
        self.error = error


class CapabilityExecutor:
    """Executes capability requests with idempotency, budget guard, and persistence.

    The executor:
    - Accepts a CapabilityRequest, ExecutionContext, and explicit
      routing/implementation selection
    - Checks the durable idempotency record before invoking anything
    - Records RoutingDecision, CapabilityExecution, ProviderInvocation,
      CapabilityResult, and UsageRecord
    - Enforces cost_limit_minor/budget guard before invocation
    - Uses explicit transactions and never holds a write transaction
      open across fake invocation
    """

    def __init__(
        self,
        database: Database,
        registry: CapabilityRegistry,
        fake_provider: FakeCapabilityProvider | None = None,
    ) -> None:
        self._database = database
        self._registry = registry
        self._fake_provider = fake_provider or FakeCapabilityProvider(registry)

    def execute(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
        routing_decision: RoutingDecision,
        resource_assignment: ResourceAssignment | None = None,
        *,
        budget_reservation_repo: BudgetReservationRepository | None = None,
    ) -> ExecutionResult | ExecutionError:
        """Execute a capability request.

        Args:
            request: The capability request to execute.
            context: Execution context with run/stage/attempt IDs.
            routing_decision: The routing decision selecting implementation/provider.
            resource_assignment: Optional resource assignment.
            budget_reservation_repo: Optional budget reservation repository
            for cost limit enforcement.

        Returns:
            ExecutionResult on success, ExecutionError on failure.

        Raises:
            CapabilityNotFoundError: If no implementation matches.
            CapabilityRequirementMismatchError: If implementation doesn't
            meet requirements.
        """
        # ATOMIC IDEMPOTENCY CLAIM + BUDGET RESERVATION (single transaction)
        # Order: idempotency check -> budget check/reserve -> insert routing/execution
        # If budget fails, the whole transaction rolls back; idempotency stays in prior
        # state
        execution_id = request.capability_execution_id
        fingerprint = request.payload_fingerprint
        idempotency_key = request.idempotency_key

        budget_reservation: BudgetReservation | None = None

        with self._database.transaction(immediate=True) as conn:
            idempotency_repo = IdempotencyRecordRepository(conn)

            # Get or create idempotency record
            existing_record = self._get_or_create_idempotency_record(
                idempotency_repo, request, routing_decision
            )

            # Validate idempotency key is not reused for a different request
            if existing_record.capability != request.capability:
                msg = (
                    f"Idempotency key {idempotency_key!r} already used for capability "
                    f"{existing_record.capability!r}, cannot reuse for "
                    f"{request.capability!r}"
                )
                error = create_normalized_error(
                    FailureCode.VALIDATION,
                    msg,
                    safe_details={"idempotency_key": idempotency_key},
                )
                return ExecutionError(
                    normalized_error=error, idempotency_record=existing_record
                )

            if existing_record.request_fingerprint != fingerprint:
                exp = existing_record.request_fingerprint[:16]
                got = fingerprint[:16]
                msg = (
                    f"Idempotency key {idempotency_key!r} has different request "
                    f"fingerprint (expected {exp}..., got {got}...)"
                )
                error = create_normalized_error(
                    FailureCode.VALIDATION,
                    msg,
                    safe_details={"idempotency_key": idempotency_key},
                )
                return ExecutionError(
                    normalized_error=error, idempotency_record=existing_record
                )

            # Handle replay cases
            if existing_record.status == IdempotencyStatus.SUCCEEDED:
                return self._replay_completed(
                    request, context, routing_decision, existing_record
                )
            if existing_record.status in (
                IdempotencyStatus.IN_FLIGHT,
                IdempotencyStatus.UNKNOWN,
            ):
                return self._replay_in_flight_or_unknown(
                    request, context, routing_decision, existing_record
                )

            # At this point, status is RESERVED, FAILED, or RECONCILED
            # We will proceed with a new attempt

            # BUDGET CHECK AND RESERVATION (within same transaction)
            budget_result = self._check_and_reserve_budget(
                conn=conn,
                request=request,
                routing_decision=routing_decision,
                context=context,
                idempotency_key=idempotency_key,
                budget_reservation_repo=budget_reservation_repo,
            )
            if not budget_result.allowed:
                # Budget check failed; update idempotency to FAILED and return error
                failed_record = existing_record.model_copy(
                    update={
                        "status": IdempotencyStatus.FAILED,
                        "completed_at": canonical_datetime(datetime.now(UTC)),
                    }
                )
                idempotency_repo.update(failed_record)
                return ExecutionError(
                    normalized_error=budget_result.error,
                    idempotency_record=failed_record,
                )
            budget_reservation = budget_result.reservation

            # INSERT ROUTING DECISION AND CAPABILITY EXECUTION
            routing_repo = RoutingDecisionRepository(conn)
            with suppress(Exception):
                routing_repo.insert(routing_decision)

            capability_execution = CapabilityExecution(
                schema_version="capability-execution.v1",
                capability_execution_id=execution_id,
                attempt_id=context.attempt_id,
                capability=request.capability,
                operation_version=request.operation_version,
                implementation_version=routing_decision.implementation_version,
                prompt_version=None,
                rubric_version=None,
                settings_hash=routing_decision.provider_config_hash,
                tool_versions={},
                request_fingerprint=fingerprint,
                idempotency_key=idempotency_key,
                routing_decision_id=routing_decision.routing_decision_id,
                resource_assignment_id=resource_assignment.assignment_id
                if resource_assignment
                else None,
                status=CapabilityExecutionStatus.PENDING,
                input_artifact_ids=request.input_artifact_ids,
                output_artifact_ids=[],
                started_at=None,
                finished_at=None,
                normalized_error=None,
            )

            exec_repo = CapabilityExecutionRepository(conn)
            with suppress(Exception):
                exec_repo.insert(capability_execution)

            # Update idempotency to IN_FLIGHT with new execution ID
            in_flight_record = existing_record.model_copy(
                update={
                    "status": IdempotencyStatus.IN_FLIGHT,
                    "capability_execution_id": execution_id,
                    "provider": routing_decision.provider,
                    "provider_invocation_id": None,
                    "provider_operation_id": None,
                    "result_artifact_ids": [],
                }
            )
            idempotency_repo.update(in_flight_record)

        # EXECUTE THE CAPABILITY (outside transaction to avoid holding write lock)
        try:
            execution_input = CapabilityExecutionInput(
                schema_version="capability-execution-input.v1",
                request=request,
                context=context,
                routing_decision=routing_decision,
                resource_assignment=resource_assignment,
            )
            output = self._fake_provider.execute(execution_input)
        except Exception as exc:
            return self._handle_execution_exception(
                request,
                context,
                routing_decision,
                in_flight_record,
                budget_reservation,
                exc,
            )

        # PERSIST RESULTS IN A TRANSACTION
        final_status = self._map_result_status_to_idempotency(output.result.status)
        completed_at = canonical_datetime(datetime.now(UTC))

        settled_reservation: BudgetReservation | None = None

        with self._database.transaction() as conn:
            # Update capability execution
            exec_repo = CapabilityExecutionRepository(conn)
            exec_repo.update(output.capability_execution)

            # Record provider invocation
            if output.provider_invocation:
                inv_repo = ProviderInvocationRepository(conn)
                inv_repo.insert(output.provider_invocation)

            # Record usage
            if output.usage_record:
                usage_repo = UsageRecordRepository(conn)
                usage_repo.insert(output.usage_record, execution_id)

            # SETTLE OR RELEASE BUDGET RESERVATION
            if budget_reservation is not None:
                settled_reservation = self._settle_budget_reservation(
                    conn=conn,
                    reservation=budget_reservation,
                    output=output,
                    result_status=output.result.status,
                    completed_at=completed_at,
                )

            # Update idempotency record
            final_record = in_flight_record.model_copy(
                update={
                    "status": final_status,
                    "provider_invocation_id": output.provider_invocation.invocation_id
                    if output.provider_invocation
                    else None,
                    "provider_operation_id": output.provider_invocation.operation_id
                    if output.provider_invocation
                    else None,
                    "result_artifact_ids": output.result.artifact_ids,
                    "completed_at": completed_at,
                }
            )
            idempotency_repo = IdempotencyRecordRepository(conn)
            idempotency_repo.update(final_record)

        # RETURN RESULT OR ERROR
        if output.result.status == CapabilityResultStatus.SUCCEEDED:
            return ExecutionResult(
                execution_output=output,
                idempotency_record=final_record,
                budget_reservation=settled_reservation,
            )
        else:
            return ExecutionError(
                normalized_error=output.result.normalized_error
                or create_normalized_error(
                    FailureCode.INTERNAL,
                    f"Capability execution failed with status {output.result.status}",
                ),
                idempotency_record=final_record,
                budget_reservation=settled_reservation,
            )

    # ------------------------------------------------------------------------
    # Idempotency helpers
    # ------------------------------------------------------------------------

    def _get_or_create_idempotency_record(
        self,
        repo: IdempotencyRecordRepository,
        request: CapabilityRequest,
        routing_decision: RoutingDecision,
    ) -> IdempotencyRecord:
        """Get existing idempotency record or create a new one in RESERVED state.

        Catches only NotFoundError; any other exception propagates.
        """
        try:
            return repo.get(request.idempotency_key)
        except NotFoundError:
            # Create new record in RESERVED state
            record = IdempotencyRecord(
                schema_version="idempotency-record.v1",
                idempotency_key=request.idempotency_key,
                capability=request.capability,
                operation_version=request.operation_version,
                request_fingerprint=request.payload_fingerprint,
                input_artifact_ids=request.input_artifact_ids,
                required_features=request.requirements.required_features or [],
                locale=request.requirements.locale,
                provider=routing_decision.provider,
                status=IdempotencyStatus.RESERVED,
                capability_execution_id=request.capability_execution_id,
                provider_invocation_id=None,
                provider_operation_id=None,
                result_artifact_ids=[],
                created_at=canonical_datetime(datetime.now(UTC)),
                completed_at=None,
            )
            repo.insert(record)
            return record

    def _replay_completed(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
        routing_decision: RoutingDecision,
        record: IdempotencyRecord,
    ) -> ExecutionResult:
        """Return prior result for completed idempotent replay.

        Validates that the request matches the original execution parameters
        to prevent replay with different parameters.
        """
        # Validate that the request matches the original execution
        if record.operation_version != request.operation_version:
            msg = (
                f"Idempotency key {record.idempotency_key!r} was used for "
                f"operation version {record.operation_version!r}, cannot replay "
                f"with {request.operation_version!r}"
            )
            error = create_normalized_error(
                FailureCode.VALIDATION,
                msg,
                safe_details={"idempotency_key": record.idempotency_key},
            )
            return ExecutionError(normalized_error=error, idempotency_record=record)

        if record.input_artifact_ids != request.input_artifact_ids:
            msg = (
                f"Idempotency key {record.idempotency_key!r} was used for "
                f"different input artifacts"
            )
            error = create_normalized_error(
                FailureCode.VALIDATION,
                msg,
                safe_details={"idempotency_key": record.idempotency_key},
            )
            return ExecutionError(normalized_error=error, idempotency_record=record)

        if set(record.required_features) != set(
            request.requirements.required_features or []
        ):
            msg = (
                f"Idempotency key {record.idempotency_key!r} was used for "
                f"different required features"
            )
            error = create_normalized_error(
                FailureCode.VALIDATION,
                msg,
                safe_details={"idempotency_key": record.idempotency_key},
            )
            return ExecutionError(normalized_error=error, idempotency_record=record)

        if record.locale != request.requirements.locale:
            msg = (
                f"Idempotency key {record.idempotency_key!r} was used for "
                f"locale {record.locale!r}, cannot replay with "
                f"{request.requirements.locale!r}"
            )
            error = create_normalized_error(
                FailureCode.VALIDATION,
                msg,
                safe_details={"idempotency_key": record.idempotency_key},
            )
            return ExecutionError(normalized_error=error, idempotency_record=record)

        # Fetch the prior capability execution and result
        with self._database.connection() as conn:
            exec_repo = CapabilityExecutionRepository(conn)
            prior_execution = exec_repo.get(record.capability_execution_id)

        # Build a synthetic output from the prior result
        result = CapabilityResult(
            schema_version="capability-result.v1",
            capability_execution_id=prior_execution.capability_execution_id,
            status=CapabilityResultStatus.SUCCEEDED,
            artifact_ids=record.result_artifact_ids,
            metadata={},
            usage=None,
            normalized_error=None,
        )

        output = CapabilityExecutionOutput(
            schema_version="capability-execution-output.v1",
            capability_execution=prior_execution,
            provider_invocation=None,
            result=result,
            usage_record=None,
        )

        return ExecutionResult(
            execution_output=output,
            idempotency_record=record,
        )

    def _replay_in_flight_or_unknown(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
        routing_decision: RoutingDecision,
        record: IdempotencyRecord,
    ) -> ExecutionError:
        """Handle in-flight or unknown idempotency - do not blindly re-invoke."""
        if record.status == IdempotencyStatus.IN_FLIGHT:
            error = create_normalized_error(
                FailureCode.TRANSIENT_PROVIDER,
                "Capability execution already in flight",
                safe_details={"idempotency_key": record.idempotency_key},
            )
        else:  # UNKNOWN
            error = create_normalized_error(
                FailureCode.TIMEOUT_UNKNOWN,
                "Prior capability execution has unknown outcome, "
                "reconciliation required",
                safe_details={"idempotency_key": record.idempotency_key},
            )
        return ExecutionError(normalized_error=error, idempotency_record=record)

    # ------------------------------------------------------------------------
    # Budget enforcement
    # ------------------------------------------------------------------------

    def _check_and_reserve_budget(
        self,
        *,
        conn,
        request: CapabilityRequest,
        routing_decision: RoutingDecision,
        context: ExecutionContext,
        idempotency_key: str,
        budget_reservation_repo: BudgetReservationRepository | None,
    ) -> _BudgetCheckResult:
        """Check budget limit and create/reserve a budget reservation.

        Returns _BudgetCheckResult with allowed=True and reservation,
        or allowed=False with a NormalizedError.
        """
        cost_limit = request.requirements.cost_limit_minor
        if cost_limit is None:
            return _BudgetCheckResult(allowed=True)

        # Budget enforcement requires a budget reservation repository
        if budget_reservation_repo is None:
            error = create_normalized_error(
                FailureCode.POLICY_BUDGET_EXCEEDED,
                "cost_limit_minor is set but budget_reservation_repo is not provided; "
                "cannot enforce budget limit",
                safe_details={"cost_limit_minor": cost_limit},
                severity=Severity.CRITICAL,
            )
            return _BudgetCheckResult(allowed=False, error=error)

        # Get estimated cost from routing decision budget context
        budget_context = routing_decision.budget_context or {}
        estimated_raw = budget_context.get("estimated_cost_minor")
        if estimated_raw is None:
            error = create_normalized_error(
                FailureCode.VALIDATION,
                "budget_context.estimated_cost_minor is required "
                "when cost_limit_minor is set",
                safe_details={"cost_limit_minor": cost_limit},
                severity=Severity.CRITICAL,
            )
            return _BudgetCheckResult(allowed=False, error=error)
        try:
            estimated = int(estimated_raw)
        except (TypeError, ValueError):
            error = create_normalized_error(
                FailureCode.VALIDATION,
                f"budget_context.estimated_cost_minor must be a non-negative integer, "
                f"got {estimated_raw!r}",
                safe_details={"estimated_cost_minor": estimated_raw},
                severity=Severity.CRITICAL,
            )
            return _BudgetCheckResult(allowed=False, error=error)

        if estimated < 0:
            error = create_normalized_error(
                FailureCode.VALIDATION,
                "budget_context.estimated_cost_minor must be non-negative",
                safe_details={"estimated_cost_minor": estimated_raw},
                severity=Severity.CRITICAL,
            )
            return _BudgetCheckResult(allowed=False, error=error)

        # Determine budget scope
        scope_type_raw = budget_context.get("budget_scope_type")
        if scope_type_raw is None:
            scope_type_raw = BudgetScopeType.RUN.value
        try:
            scope_type = BudgetScopeType(scope_type_raw)
        except ValueError:
            error = create_normalized_error(
                FailureCode.VALIDATION,
                f"Invalid budget_scope_type {scope_type_raw!r}; "
                f"must be one of {[s.value for s in BudgetScopeType]}",
                safe_details={"budget_scope_type": scope_type_raw},
            )
            return _BudgetCheckResult(allowed=False, error=error)

        scope_id = budget_context.get("budget_scope_id")
        if scope_id is None:
            if scope_type == BudgetScopeType.RUN:
                scope_id = context.run_id
            elif scope_type == BudgetScopeType.STAGE:
                scope_id = context.stage_instance_id
            elif scope_type == BudgetScopeType.CAPABILITY:
                scope_id = request.capability
            else:  # SYSTEM, MONTH
                scope_id = "global"
        if scope_id is None:
            error = create_normalized_error(
                FailureCode.VALIDATION,
                f"Cannot determine budget scope_id for scope_type {scope_type.value}",
                safe_details={"scope_type": scope_type.value},
            )
            return _BudgetCheckResult(allowed=False, error=error)

        # Create a budget repository bound to this transaction's connection
        budget_repo = BudgetReservationRepository(conn)

        # Sum committed costs for this scope (exclude RELEASED)
        committed_minor = 0
        for res in budget_repo.list_for_scope(scope_type.value, scope_id):
            if res.status == BudgetReservationStatus.RELEASED:
                continue
            if res.status == BudgetReservationStatus.SETTLED:
                actual = res.actual_cost_minor
                reserved = res.reserved_cost_minor
                cost = actual if actual is not None else reserved
            else:  # RESERVED, UNKNOWN
                cost = res.reserved_cost_minor
            committed_minor += cost

        # Check if we already have a reservation for this idempotency key/scope
        existing_reservation = budget_repo.get_by_scope(
            idempotency_key, scope_type.value, scope_id
        )

        if existing_reservation is not None:
            # Reuse existing reservation; don't double-count it in committed
            if existing_reservation.status != BudgetReservationStatus.RELEASED:
                if existing_reservation.status == BudgetReservationStatus.SETTLED:
                    existing_cost = (
                        existing_reservation.actual_cost_minor
                        if existing_reservation.actual_cost_minor is not None
                        else existing_reservation.reserved_cost_minor
                    )
                else:
                    existing_cost = existing_reservation.reserved_cost_minor
                committed_minor -= existing_cost

            # If existing reservation is RELEASED, we'll create a new one below
            # For other statuses, we update the existing one
            if existing_reservation.status != BudgetReservationStatus.RELEASED:
                if committed_minor + estimated > cost_limit:
                    msg = (
                        f"Budget exceeded: committed {committed_minor} + "
                        f"estimated {estimated} > limit {cost_limit} "
                        f"(scope {scope_type.value}:{scope_id})"
                    )
                    error = create_normalized_error(
                        FailureCode.POLICY_BUDGET_EXCEEDED,
                        msg,
                        safe_details={
                            "committed_minor": committed_minor,
                            "estimated_minor": estimated,
                            "limit_minor": cost_limit,
                            "scope_type": scope_type.value,
                            "scope_id": scope_id,
                        },
                        severity="CRITICAL",
                    )
                    return _BudgetCheckResult(allowed=False, error=error)

                # Update existing reservation
                updated = existing_reservation.model_copy(
                    update={
                        "status": BudgetReservationStatus.RESERVED,
                        "estimated_cost_minor": estimated,
                        "reserved_cost_minor": estimated,
                        "actual_cost_minor": None,
                        "settled_at": None,
                    }
                )
                budget_repo.update(updated)
                return _BudgetCheckResult(allowed=True, reservation=updated)

        # No existing reservation; check cumulative limit
        if committed_minor + estimated > cost_limit:
            msg = (
                f"Budget exceeded: committed {committed_minor} + estimated {estimated} "
                f"> limit {cost_limit} (scope {scope_type.value}:{scope_id})"
            )
            error = create_normalized_error(
                FailureCode.POLICY_BUDGET_EXCEEDED,
                msg,
                safe_details={
                    "committed_minor": committed_minor,
                    "estimated_minor": estimated,
                    "limit_minor": cost_limit,
                    "scope_type": scope_type.value,
                    "scope_id": scope_id,
                },
                severity=Severity.CRITICAL,
            )
            return _BudgetCheckResult(allowed=False, error=error)

        # Create new deterministic reservation
        reservation_id = deterministic_id(
            "bres", idempotency_key, scope_type.value, scope_id
        )
        new_reservation = BudgetReservation(
            schema_version="budget-reservation.v1",
            reservation_id=reservation_id,
            scope_type=scope_type,
            scope_id=scope_id,
            idempotency_key=idempotency_key,
            estimated_cost_minor=estimated,
            reserved_cost_minor=estimated,
            actual_cost_minor=None,
            status=BudgetReservationStatus.RESERVED,
            created_at=canonical_datetime(datetime.now(UTC)),
            settled_at=None,
        )
        budget_repo.insert(new_reservation)
        return _BudgetCheckResult(allowed=True, reservation=new_reservation)

    def _settle_budget_reservation(
        self,
        *,
        conn,
        reservation: BudgetReservation,
        output: CapabilityExecutionOutput,
        result_status: CapabilityResultStatus,
        completed_at: str,
    ) -> BudgetReservation:
        """Settle or release a budget reservation based on execution outcome."""
        budget_repo = BudgetReservationRepository(conn)

        # Determine final status and actual cost
        if result_status == CapabilityResultStatus.SUCCEEDED:
            # Succeeded: settle with actual cost if available, else estimated
            rec = output.usage_record
            actual_cost = rec.actual_cost_minor if rec else None
            if actual_cost is None:
                rec_est = rec.estimated_cost_minor if rec else None
                actual_cost = (
                    rec_est if rec_est is not None else reservation.estimated_cost_minor
                )
            final_status = BudgetReservationStatus.SETTLED
        elif result_status == CapabilityResultStatus.FAILED:
            # Definite failure: release the reservation
            final_status = BudgetReservationStatus.RELEASED
            actual_cost = None
        else:  # UNKNOWN
            # Timeout/unknown: mark UNKNOWN, keep reserved amount as actual
            final_status = BudgetReservationStatus.UNKNOWN
            rec = output.usage_record
            rec_est = rec.estimated_cost_minor if rec else None
            actual_cost = (
                rec_est if rec_est is not None else reservation.reserved_cost_minor
            )

        settled = reservation.model_copy(
            update={
                "status": final_status,
                "actual_cost_minor": actual_cost,
                "settled_at": (
                    completed_at
                    if final_status == BudgetReservationStatus.SETTLED
                    else None
                ),
            }
        )
        budget_repo.update(settled)
        return settled

    def _handle_execution_exception(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
        routing_decision: RoutingDecision,
        idempotency_record: IdempotencyRecord,
        budget_reservation: BudgetReservation | None,
        exc: Exception,
    ) -> ExecutionError:
        """Handle exception during capability execution."""
        from pipeline.capabilities.errors import create_normalized_error_from_exception

        normalized_error = create_normalized_error_from_exception(exc)
        completed_at = canonical_datetime(datetime.now(UTC))

        # Update records in transaction
        with self._database.transaction() as conn:
            # Update capability execution
            exec_repo = CapabilityExecutionRepository(conn)
            failed_execution = CapabilityExecution(
                schema_version="capability-execution.v1",
                capability_execution_id=request.capability_execution_id,
                attempt_id=context.attempt_id,
                capability=request.capability,
                operation_version=request.operation_version,
                implementation_version=routing_decision.implementation_version,
                prompt_version=None,
                rubric_version=None,
                settings_hash=routing_decision.provider_config_hash,
                tool_versions={},
                request_fingerprint=request.payload_fingerprint,
                idempotency_key=request.idempotency_key,
                routing_decision_id=routing_decision.routing_decision_id,
                resource_assignment_id=None,
                status=CapabilityExecutionStatus.FAILED,
                input_artifact_ids=request.input_artifact_ids,
                output_artifact_ids=[],
                started_at=completed_at,
                finished_at=completed_at,
                normalized_error=normalized_error,
            )
            exec_repo.update(failed_execution)

            # Release or mark UNKNOWN budget reservation
            settled_reservation: BudgetReservation | None = None
            if budget_reservation is not None:
                settled_reservation = self._settle_budget_reservation(
                    conn=conn,
                    reservation=budget_reservation,
                    output=None,  # type: ignore[arg-type]
                    result_status=CapabilityResultStatus.FAILED
                    if "timeout" not in str(exc).lower()
                    else CapabilityResultStatus.UNKNOWN,
                    completed_at=completed_at,
                )

            # Update idempotency to FAILED or UNKNOWN
            final_status = (
                IdempotencyStatus.UNKNOWN
                if "timeout" in str(exc).lower()
                else IdempotencyStatus.FAILED
            )
            updated_record = idempotency_record.model_copy(
                update={
                    "status": final_status,
                    "completed_at": completed_at,
                }
            )
            idempotency_repo = IdempotencyRecordRepository(conn)
            idempotency_repo.update(updated_record)

        return ExecutionError(
            normalized_error=normalized_error,
            idempotency_record=updated_record,
            budget_reservation=settled_reservation,
        )

    def _map_result_status_to_idempotency(
        self, status: CapabilityResultStatus
    ) -> IdempotencyStatus:
        """Map CapabilityResultStatus to IdempotencyStatus."""
        if status == CapabilityResultStatus.SUCCEEDED:
            return IdempotencyStatus.SUCCEEDED
        if status == CapabilityResultStatus.FAILED:
            return IdempotencyStatus.FAILED
        return IdempotencyStatus.UNKNOWN


__all__ = [
    "CapabilityExecutor",
    "ExecutionError",
    "ExecutionResult",
]
