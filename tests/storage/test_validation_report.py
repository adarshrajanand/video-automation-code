"""Wire-form regressions for the validation report JSON output.

Review 4501750820 found that ``ValidationReport`` renamed its timing keys to
``*_timestamp_micro`` but still wrote ISO strings. These tests exercise actual
generation through the database, not just the dataclass, so a regression in the
SQL projections is caught too.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from pipeline.contracts.vocabularies import AttemptStatus
from pipeline.fingerprints import unix_microseconds
from pipeline.report import ValidationReportGenerator
from pipeline.storage import (
    EffectiveConfigRepository,
    StageAttemptRepository,
    StageInstanceRepository,
    WorkflowRunRepository,
)

BASE_TIME = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def test_validation_report_wire_timestamps_are_integer_microseconds(
    database, records
) -> None:
    config = records.effective_config()
    run = records.run(config)
    succeeded_stage = records.stage_instance(run, suffix="01")
    succeeded_attempt = records.stage_attempt(succeeded_stage, suffix="01")
    failed_stage = records.stage_instance(
        run,
        suffix="02",
        node_id="speech",
    )
    failed_attempt = records.stage_attempt(
        failed_stage,
        suffix="02",
        status=AttemptStatus.FAILED,
    )
    with database.transaction() as connection:
        EffectiveConfigRepository(connection).insert(config)
        WorkflowRunRepository(connection).insert(run)
        StageInstanceRepository(connection).insert(succeeded_stage)
        StageInstanceRepository(connection).insert(failed_stage)
        StageAttemptRepository(connection).insert(succeeded_attempt)
        StageAttemptRepository(connection).insert(failed_attempt)

    report = ValidationReportGenerator(database).generate(run.run_id)
    payload = report.to_dict()

    assert payload["schema_version"] == "validation-report.v2"
    # ``generated_at`` now names its unit and carries an integer, matching the
    # rest of the persisted representation.
    assert payload["generated_timestamp_micro"] == unix_microseconds(
        report.generated_timestamp_micro
    )
    assert isinstance(payload["generated_timestamp_micro"], int)

    succeeded_timing = payload["stage_timings"][succeeded_stage.stage_instance_id]
    assert succeeded_timing["started_timestamp_micro"] == unix_microseconds(
        succeeded_attempt.started_timestamp_micro
    )
    assert succeeded_timing["finished_timestamp_micro"] == unix_microseconds(
        succeeded_attempt.finished_timestamp_micro
    )
    assert isinstance(succeeded_timing["started_timestamp_micro"], int)
    assert isinstance(succeeded_timing["finished_timestamp_micro"], int)

    # An unfinished attempt keeps a null ``finished_timestamp_micro`` instead of
    # falling back to a string sentinel.
    failed_timing = payload["stage_timings"][failed_stage.stage_instance_id]
    assert failed_timing["started_timestamp_micro"] == unix_microseconds(
        failed_attempt.started_timestamp_micro
    )
    assert failed_timing["finished_timestamp_micro"] is None

    # The CLI writes ``json.dumps(report.to_dict())``; prove the encoded wire
    # form survives a round trip without turning integers back into strings.
    decoded = json.loads(json.dumps(payload))
    assert isinstance(
        decoded["stage_timings"][succeeded_stage.stage_instance_id][
            "started_timestamp_micro"
        ],
        int,
    )
    assert isinstance(decoded["generated_timestamp_micro"], int)
