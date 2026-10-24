"""Human review management and CLI decision command."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pipeline.contracts.review import HumanReview, HumanReviewDecision
from pipeline.contracts.vocabularies import ReviewDecision, ReviewStatus
from pipeline.ids import deterministic_id

if TYPE_CHECKING:
    from pipeline.storage.database import Database


class HumanReviewError(Exception):
    """Error in human review operations."""

    pass


class HumanReviewNotFoundError(HumanReviewError):
    """Human review not found."""

    pass


class HumanReviewAlreadyResolvedError(HumanReviewError):
    """Human review already has a decision."""

    pass


class InvalidReviewDecisionError(HumanReviewError):
    """Invalid decision for the review state."""

    pass


@dataclass(slots=True)
class HumanReviewRequest:
    """Request to create a human review."""

    run_id: str
    stage_instance_id: str | None
    gate_id: str | None
    target_artifact_ids: list[str]
    target_hashes: dict[str, str]
    reason_codes: list[str]
    requested_action: str


class HumanReviewManager:
    """Manages human review lifecycle."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def create_review(self, request: HumanReviewRequest) -> HumanReview:
        """Create a new human review request.

        Args:
            request: The review request details.

        Returns:
            The created HumanReview record.
        """
        # Deterministic review ID based on request content
        review_id = deterministic_id(
            "review",
            request.run_id,
            request.stage_instance_id or "",
            request.gate_id or "",
            ",".join(sorted(request.target_artifact_ids)),
            ",".join(f"{k}:{v}" for k, v in sorted(request.target_hashes.items())),
            request.requested_action,
        )

        review = HumanReview(
            schema_version="human-review.v1",
            review_id=review_id,
            run_id=request.run_id,
            stage_instance_id=request.stage_instance_id,
            gate_id=request.gate_id,
            target_artifact_ids=request.target_artifact_ids,
            target_hashes=request.target_hashes,
            reason_codes=request.reason_codes,
            requested_action=request.requested_action,
            status=ReviewStatus.OPEN,
            created_at=datetime.now(UTC),
            resolved_at=None,
        )

        with self.database.transaction() as conn:
            from pipeline.storage.repositories.editorial import HumanReviewRepository

            try:
                HumanReviewRepository(conn).insert(review)
            except Exception:
                # If already exists (idempotent), fetch and return existing
                existing = HumanReviewRepository(conn).get(review_id)
                if existing:
                    return existing
                raise

        return review

    def get_review(self, review_id: str) -> HumanReview:
        """Get a human review by ID."""
        with self.database.connection() as conn:
            from pipeline.storage.repositories.editorial import HumanReviewRepository

            try:
                return HumanReviewRepository(conn).get(review_id)
            except Exception as e:
                from pipeline.storage.errors import NotFoundError

                if isinstance(e, NotFoundError):
                    raise HumanReviewNotFoundError(
                        f"Review {review_id!r} not found"
                    ) from e
                raise

    def list_reviews(
        self,
        run_id: str | None = None,
        status: ReviewStatus | None = None,
    ) -> list[HumanReview]:
        """List human reviews with optional filters."""
        with self.database.connection() as conn:
            from pipeline.storage.repositories.editorial import HumanReviewRepository

            return HumanReviewRepository(conn).list(run_id=run_id, status=status)

    def record_decision(
        self,
        review_id: str,
        decision: ReviewDecision,
        reviewer: str,
        comments: str | None = None,
    ) -> HumanReviewDecision:
        """Record a reviewer's decision.

        Args:
            review_id: The review to decide.
            decision: The reviewer's decision.
            reviewer: Reviewer identifier.
            comments: Optional reviewer comments.

        Returns:
            The recorded HumanReviewDecision.

        Raises:
            HumanReviewNotFoundError: If review doesn't exist.
            HumanReviewAlreadyResolvedError: If review already has a decision.
            InvalidReviewDecisionError: If decision is invalid for review state.
        """
        with self.database.transaction() as conn:
            from pipeline.storage.repositories.editorial import HumanReviewRepository

            repo = HumanReviewRepository(conn)
            try:
                review = repo.get(review_id)
            except Exception as e:
                from pipeline.storage.errors import NotFoundError

                if isinstance(e, NotFoundError):
                    raise HumanReviewNotFoundError(
                        f"Review {review_id!r} not found"
                    ) from e
                raise

            if review.status is not ReviewStatus.OPEN:
                raise HumanReviewAlreadyResolvedError(
                    f"Review {review_id!r} is already {review.status.value}"
                )

            # Validate decision
            valid_decisions = {
                ReviewDecision.APPROVE,
                ReviewDecision.REGENERATE_SCENE,
                ReviewDecision.REGENERATE_STAGE,
                ReviewDecision.REJECT,
            }
            if decision not in valid_decisions:
                raise InvalidReviewDecisionError(f"Invalid decision: {decision}")

            # Create decision record
            review_decision = HumanReviewDecision(
                schema_version="human-review-decision.v1",
                review_id=review_id,
                decision=decision,
                comments=comments,
                reviewer=reviewer,
                target_hashes=review.target_hashes,
                created_at=datetime.now(UTC),
            )

            # Update review status
            review_data = review.model_dump()
            review_data["status"] = ReviewStatus.RESOLVED
            review_data["resolved_at"] = datetime.now(UTC)
            review = HumanReview(**review_data)
            repo.update(review)
            repo.insert_decision(review_decision)

        return review_decision

    def get_decision(self, review_id: str) -> HumanReviewDecision | None:
        """Get the recorded decision for a review."""
        with self.database.connection() as conn:
            from pipeline.storage.repositories.editorial import HumanReviewRepository

            return HumanReviewRepository(conn).get_decision(review_id)


def cli_human_review_decide(
    database: Database,
    review_id: str,
    decision: str,
    reviewer: str,
    comments: str | None = None,
) -> HumanReviewDecision:
    """CLI handler for human review decision command.

    Args:
        database: Database connection.
        review_id: Review ID to decide.
        decision: Decision string (APPROVE, REGENERATE_SCENE, REGENERATE_STAGE, REJECT).
        reviewer: Reviewer identifier.
        comments: Optional comments.

    Returns:
        The recorded decision.

    Raises:
        HumanReviewError: If the decision cannot be recorded.
    """
    try:
        decision_enum = ReviewDecision(decision)
    except ValueError as err:
        valid = ", ".join(d.value for d in ReviewDecision)
        raise HumanReviewError(
            f"Invalid decision: {decision}. Must be one of: {valid}"
        ) from err

    manager = HumanReviewManager(database)
    return manager.record_decision(
        review_id=review_id,
        decision=decision_enum,
        reviewer=reviewer,
        comments=comments,
    )


def request_human_review(
    database: Database,
    run_id: str,
    target_artifact_ids: list[str],
    target_hashes: dict[str, str],
    reason_codes: list[str],
    requested_action: str,
    stage_instance_id: str | None = None,
    gate_id: str | None = None,
) -> HumanReview:
    """Convenience function to request human review.

    Args:
        database: The database connection.
        run_id: The workflow run ID.
        target_artifact_ids: List of artifact IDs under review.
        target_hashes: Content hashes of target artifacts.
        reason_codes: Failure codes triggering the review.
        requested_action: The action being requested (e.g., "review_quality_gate").
        stage_instance_id: Optional stage instance ID.
        gate_id: Optional gate ID.

    Returns:
        The created HumanReview record.
    """
    manager = HumanReviewManager(database)
    return manager.create_review(
        HumanReviewRequest(
            run_id=run_id,
            stage_instance_id=stage_instance_id,
            gate_id=gate_id,
            target_artifact_ids=target_artifact_ids,
            target_hashes=target_hashes,
            reason_codes=reason_codes,
            requested_action=requested_action,
        )
    )
