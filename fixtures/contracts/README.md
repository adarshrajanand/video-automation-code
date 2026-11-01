# Contract fixtures

Deterministic JSON fixtures for the FV-02 Pydantic contracts.

## Layout

- `valid/<snake_case_model>.json` — one valid instance for every model in
  `pipeline.contracts.PUBLIC_CONTRACTS`.
- `invalid/<case>.json` — deliberately invalid payloads. Each file is paired with
  its expected model and error substring in `invalid_manifest.json`.
- `invalid_manifest.json` — machine-readable index consumed by
  `tests/contracts/test_fixtures.py`.

## Rules

- Keep fixture timestamps timezone-aware and normalized to UTC (`Z` suffix).
- Use lowercase 64-character SHA-256 digests for hash fields.
- Keep IDs and hashes deterministic across regenerations.
- Update `invalid_manifest.json` whenever an invalid fixture is added, renamed,
  or its expected error changes.
- Do not add runtime or credential-bearing data. These files are committed.

Valid fixtures are checked by `uv run pytest tests/contracts`. JSON Schemas are
derived from the models, not from fixtures:

```bash
uv run python -m pipeline contracts export-schemas --check
```
