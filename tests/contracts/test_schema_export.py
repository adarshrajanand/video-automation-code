from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.cli import main
from pipeline.contracts.registry import (
    PUBLIC_CONTRACTS,
    contract_schema_version,
    schema_file_name,
)
from pipeline.contracts.schema_export import (
    GENERATED_BY,
    MANIFEST_FILE,
    MANIFEST_VERSION,
    SCHEMA_DIALECT,
    check_schemas,
    export_schemas,
    render_all_schemas,
    render_schema_bytes,
)
from pipeline.fingerprints import sha256_bytes


def test_schema_rendering_is_deterministic() -> None:
    first = render_all_schemas()
    second = render_all_schemas()

    assert first == second
    assert len(first) == len(PUBLIC_CONTRACTS) + 1


def test_every_schema_is_valid_json_with_stable_identity() -> None:
    rendered = render_all_schemas()
    ids = set()

    for model_name, model in PUBLIC_CONTRACTS.items():
        schema = json.loads(rendered[schema_file_name(model)])

        assert schema["$id"] == f"urn:pipeline:contract:{model_name}"
        assert schema["$id"] not in ids
        ids.add(schema["$id"])
        assert schema["$schema"] == SCHEMA_DIALECT
        assert schema["x-contract-schema-version"] == contract_schema_version(model)
        assert schema["additionalProperties"] is False


def test_manifest_matches_rendered_files(schema_dir: Path) -> None:
    rendered = render_all_schemas()
    manifest = json.loads(rendered[MANIFEST_FILE])
    contracts = manifest["contracts"]

    assert manifest["manifest_version"] == MANIFEST_VERSION
    assert manifest["schema_dialect"] == SCHEMA_DIALECT
    assert manifest["generated_by"] == GENERATED_BY
    assert manifest["public_contract_count"] == len(PUBLIC_CONTRACTS)
    assert [entry["model"] for entry in contracts] == sorted(PUBLIC_CONTRACTS)

    for entry in contracts:
        model = PUBLIC_CONTRACTS[entry["model"]]
        content = rendered[schema_file_name(model)]

        assert entry["schema_file"] == schema_file_name(model)
        assert entry["schema_version"] == contract_schema_version(model)
        assert entry["sha256"] == sha256_bytes(content)


def test_committed_schemas_match_the_generator(schema_dir: Path) -> None:
    rendered = render_all_schemas()

    for name, content in rendered.items():
        assert (schema_dir / name).read_bytes() == content
    assert check_schemas(schema_dir).ok

    committed = {path.name for path in schema_dir.glob("*.schema.json")}
    assert committed == {schema_file_name(model) for model in PUBLIC_CONTRACTS.values()}


def test_schema_file_bytes_end_with_one_newline() -> None:
    content = render_schema_bytes("Artifact")

    assert content.endswith(b"\n")
    assert not content.endswith(b"\n\n")


def test_export_writes_all_files_and_check_detects_drift(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "schemas"

    result = export_schemas(output_dir)

    assert result.ok
    assert len(result.written) == len(PUBLIC_CONTRACTS) + 1
    assert check_schemas(output_dir).ok

    schema_path = output_dir / schema_file_name(PUBLIC_CONTRACTS["Artifact"])
    schema_path.write_text("{}\n", encoding="utf-8")
    drift = check_schemas(output_dir)
    assert not drift.ok
    assert drift.drifted == (schema_path.name,)

    (output_dir / "Stale.schema.json").write_text("{}\n", encoding="utf-8")
    stale = check_schemas(output_dir)
    assert not stale.ok
    assert stale.extra == ("Stale.schema.json",)

    (output_dir / MANIFEST_FILE).unlink()
    missing = check_schemas(output_dir)
    assert not missing.ok
    assert missing.missing == (MANIFEST_FILE,)


def test_export_removes_only_stale_schema_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "schemas"
    output_dir.mkdir()
    stale = output_dir / "Old.schema.json"
    stale.write_text("{}", encoding="utf-8")
    unrelated = output_dir / "notes.txt"
    unrelated.write_text("keep", encoding="utf-8")

    export_schemas(output_dir)

    assert not stale.exists()
    assert unrelated.is_file()


def test_cli_check_passes_for_committed_schemas(
    schema_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            [
                "contracts",
                "export-schemas",
                "--check",
                "--output-dir",
                str(schema_dir),
            ]
        )
        == 0
    )
    assert "up to date" in capsys.readouterr().out


def test_cli_check_reports_drift_and_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            [
                "contracts",
                "export-schemas",
                "--check",
                "--output-dir",
                str(tmp_path / "missing"),
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert "drift detected" in captured.err
    assert "missing:" in captured.err
    assert "export-schemas" in captured.err


def test_cli_export_writes_schemas(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output_dir = tmp_path / "exported"

    assert (
        main(
            [
                "contracts",
                "export-schemas",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 0
    )

    assert "Exported" in capsys.readouterr().out
    assert check_schemas(output_dir).ok
