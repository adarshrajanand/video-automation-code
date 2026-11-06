from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone

from pipeline.contracts.review import HumanReview, HumanReviewDecision
from pipeline.contracts.vocabularies import ReviewDecision, ReviewStatus
from pipeline.storage.backfill import canonicalize_persisted_timestamps
from pipeline.fingerprints import unix_microseconds
from pipeline.storage.repositories.editorial import HumanReviewRepository


def _insert_legacy_review(connection, review_id: str, created_timestamp_micro: str) -> None:
    payload = {
        "schema_version": "human-review.v2",
        "review_id": review_id,
        "run_id": "run_01",
        "target_artifact_ids": [],
        "reason_codes": [],
        "requested_action": "review",
        "status": "OPEN",
        "created_timestamp_micro": created_timestamp_micro,
        "resolved_timestamp_micro": None,
    }
    connection.execute(
        "INSERT INTO human_reviews "
        "(review_id, run_id, status, requested_action, created_timestamp_micro, "
        "schema_version, payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            review_id,
            "run_01",
            "OPEN",
            "review",
            created_timestamp_micro,
            "human-review.v2",
            json.dumps(payload),
        ),
    )


def _review(review_id: str, created_timestamp_micro: datetime) -> HumanReview:
    return HumanReview(
        schema_version="human-review.v2",
        review_id=review_id,
        run_id="run_01",
        target_artifact_ids=["artifact_01"],
        requested_action="review",
        status=ReviewStatus.OPEN,
        created_timestamp_micro=created_timestamp_micro,
    )


def test_persisted_text_order_matches_chronological_order(database) -> None:
    # Regression for #14: SQLite TEXT ordering is lexicographic. Fixed six-digit
    # fractional seconds make lexicographic order agree with chronological order
    # across second and microsecond boundaries.
    base = datetime(2026, 10, 21, 12, 0, 0, tzinfo=UTC)
    instants = [
        base,
        base + timedelta(microseconds=1),
        base + timedelta(microseconds=999_999),
        base + timedelta(seconds=1),
        base + timedelta(seconds=1, microseconds=1),
        base + timedelta(seconds=2),
    ]
    reviews = [
        _review(f"review_{index:02d}", instant)
        for index, instant in enumerate(instants)
    ]

    with database.transaction() as connection:
        repository = HumanReviewRepository(connection)
        for review in reviews:
            repository.insert(review)

    with database.connection() as connection:
        rows = connection.execute(
            "SELECT review_id, created_timestamp_micro FROM human_reviews ORDER BY created_timestamp_micro"
        ).fetchall()

    stored = [str(row["created_timestamp_micro"]) for row in rows]
    assert stored == sorted(stored)
    assert [row["review_id"] for row in rows] == [
        review.review_id for review in reviews
    ]
    assert all(isinstance(value, int) for value in stored)
    # assert all(len(value) == 27 for value in stored)  # removed, values are integers


def test_mixed_legacy_serializers_order_chronologically_after_backfill(
    database,
) -> None:
    rows = [
        ("review_legacy", "2026-10-21T12:00:00Z"),
        ("review_canonical", "2026-10-21T12:00:00.000001Z"),
        ("review_offset", "2026-10-21T14:00:00.000002+02:00"),
    ]
    with database.transaction() as connection:
        for review_id, created_timestamp_micro in rows:
            _insert_legacy_review(connection, review_id, created_timestamp_micro)
        before = [
            row[0]
            for row in connection.execute(
                "SELECT review_id FROM human_reviews ORDER BY created_timestamp_micro"
            )
        ]

    assert before == ["review_canonical", "review_legacy", "review_offset"]

    with database.transaction() as connection:
        canonicalize_persisted_timestamps(connection)

    with database.connection() as connection:
        after = connection.execute(
            "SELECT review_id, created_timestamp_micro FROM human_reviews ORDER BY created_timestamp_micro"
        ).fetchall()

    assert [row[0] for row in after] == [
        "review_legacy",
        "review_canonical",
        "review_offset",
    ]
    assert [row[1] for row in after] == [
        unix_microseconds(datetime(2026, 10, 21, 12, 0, 0, tzinfo=UTC)),
        unix_microseconds(datetime(2026, 10, 21, 12, 0, 0, 1, tzinfo=UTC)),
        unix_microseconds(datetime(2026, 10, 21, 12, 0, 0, tzinfo=UTC)),
    ]


def test_direct_decision_write_uses_canonical_timestamp(database) -> None:
    # Direct SQL writers (outside SqliteRepository) must use the same canonical
    # form. This inserts a +02:00 value and expects UTC normalization in both
    # the projection column and the JSON payload.
    review = _review("review_01", datetime(2026, 10, 21, 9, 0, tzinfo=UTC))
    decision = HumanReviewDecision(
        schema_version="human-review-decision.v2",
        review_id=review.review_id,
        decision=ReviewDecision.APPROVE,
        reviewer="alice",
        created_timestamp_micro=datetime(
            2026,
            10,
            21,
            14,
            5,
            0,
            123456,
            tzinfo=timezone(timedelta(hours=2)),
        ),
    )

    with database.transaction() as connection:
        repository = HumanReviewRepository(connection)
        repository.insert(review)
        repository.insert_decision(decision)

    with database.connection() as connection:
        row = connection.execute(
            "SELECT created_timestamp_micro, payload FROM human_review_decisions "
            "WHERE review_id = ?",
            (review.review_id,),
        ).fetchone()

    assert row is not None
    assert row["created_timestamp_micro"] == unix_microseconds(datetime(2026, 10, 21, 12, 5, 0, 123456, tzinfo=UTC))
    assert json.loads(row["payload"])["created_timestamp_micro"] == unix_microseconds(datetime(2026, 10, 21, 12, 5, 0, 123456, tzinfo=UTC))
