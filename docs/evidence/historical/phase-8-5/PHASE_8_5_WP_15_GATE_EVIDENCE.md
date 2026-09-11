# Phase 8.5 WP-15 Gate Evidence

**Status:** COMPLETE (2026-08-28)

## Objective and boundary

The authoritative WP-15 objective is to establish one reproducible active
Phase 8.5 model profile without changing V1 defaults. This gate implements the
configuration/profile work in tasks 15.1–15.7. It does not add a second runtime,
observability framework, recovery state machine, WP-16 blind-agent validation,
WP-17 final certification, or Phase 11 behavior.

## Implemented contract

- Added strict `mnemo.model-profiles/1` TOML and JSON Schema contracts.
- Pinned provider, model, immutable revision, license, vector dimensions/
  metric/normalization, preprocessing, trust, language/script/modality, and
  public resource ceilings for the selected candidate components.
- Implemented deterministic precedence: environment leaf, inline component,
  selected profile document, then unchanged V1 defaults.
- Added `ModelProfileRegistryV1` and an immutable SHA-256-identified active
  snapshot owned by `Phase85RuntimeV1`; no parallel capability registry exists.
- Required exact revision identity for every enabled V2 model component.
- Bound generation-backed capability readiness to the exact resolved profile
  fingerprint. Missing or mismatched bindings fail closed as
  `profile_generation_unbound` or `profile_generation_mismatch`.
- Added feature/transport gating and explicit `v1_only` and `disabled` profiles.
- Added redacted active profile and component identities to the existing
  capability discovery document. Profile paths, model roots, credentials,
  environment values, and secrets are not serialized.
- Moved the repository configuration to a tracked profile selection while
  retaining the existing V1 LLM, embedding, and reranker sections unchanged.
- Added an operator migration, activation, rollback, and V1-only runbook.

The tracked local profile is labeled `candidate`; this gate does not promote it
to certified.

## Files changed for WP-15

Production/configuration:

- `config/model_profiles/phase8_5_profiles.toml`
- `config/model_profiles/model_profile.schema.json`
- `mnemo.toml`
- `mnemo-core/mnemo/config.py`
- `mnemo-core/mnemo/interfaces/model_profiles.py`
- `mnemo-core/mnemo/interfaces/phase85.py`
- `mnemo-core/mnemo/interfaces/__init__.py`
- `mnemo-core/mnemo/phase85/profiles.py`
- `mnemo-core/mnemo/phase85/models.py`
- `mnemo-core/mnemo/phase85/projections.py`
- `mnemo-core/mnemo/phase85/runtime.py`
- `mnemo-core/mnemo/phase85/__init__.py`
- `mnemo-core/mnemo/__init__.py`
- `mnemo-server/mnemo_server/schemas/capabilities_v2.py`
- `mnemo-server/mnemo_server/services/capabilities_v2.py`

Tests:

- `mnemo-core/tests/unit/test_model_profiles.py`
- `mnemo-core/tests/unit/test_config.py`
- `mnemo-core/tests/unit/test_phase85_runtime.py`
- `mnemo-core/tests/unit/test_projection_generations.py`
- `mnemo-server/tests/test_capabilities_v2.py`

Governance/documentation:

- `docs/governance/historical/PHASE_8_5_COMPLETE_IMPLEMENTATION_PLAN.md`
- `docs/evidence/historical/phase-8-5/PHASE_8_5_WP_15_GATE_EVIDENCE.md`
- `docs/runbooks/production/PHASE_8_5_WP_15_PROFILE_RUNBOOK.md`
- `docs/governance/contracts/phase8_5_capability_matrix.json`
- `docs/adr/active/ADR-0074-phase-8-5-runtime-and-profile-activation.md`
- `docs/architecture/current/phase8.5_architecture.md`
- `docs/changelog/entries/0084-phase-8-5-wp-15-model-profile-activation.md`

## Focused and regression evidence

Focused registry/config/runtime/capability validation:

```text
uv run pytest --no-cov -q
  mnemo-core/tests/unit/test_model_profiles.py
  mnemo-core/tests/unit/test_config.py
  mnemo-core/tests/unit/test_phase85_runtime.py
  mnemo-server/tests/test_capabilities_v2.py
54 passed
```

Affected engine/projection/server configuration and authorization regression:

```text
uv run pytest --no-cov -q
  mnemo-core/tests/unit/test_engine.py
  mnemo-core/tests/unit/test_projection_generations.py
  mnemo-server/tests/test_server_system.py
  mnemo-server/tests/test_server_config.py
  mnemo-server/tests/test_server_auth.py
62 passed
```

Affected MCP/server/governance contract regression:

```text
uv run pytest --no-cov -q
  mnemo-server/tests/test_mcp_wp03_contracts.py
  mnemo-server/tests/test_mcp_server.py
  mnemo-server/tests/test_mcp_tools.py
  mnemo-server/tests/test_server_app.py
  tests/governance/test_phase8_5_wp00_contracts.py
45 passed
```

Governance contract suite independently: `8 passed`. The capability matrix
validated against its JSON Schema and the MCP contract parsed and passed its
governance assertions.

The focused commands intentionally use `--no-cov`: the repository enforces a
global 90% threshold which cannot be satisfied by a narrow subsystem selection.
The full coverage gate remains WP-17. A preliminary focused run without
`--no-cov` executed all selected tests successfully but exited on that global
threshold; it is not counted as a passing command.

## Static and repository validation

- Ruff format/check on affected production and focused test modules: PASS.
- Strict mypy on nine affected production modules: PASS, no issues.
- Governance JSON/schema validation: PASS.
- `git diff --check`: PASS.

The only test warning was the local pytest cache/temporary-directory permission
warning on Windows. It did not change test outcomes.

## Database, corpus, and provider state

WP-15 introduced no database schema or migration. No ingestion, projection
build, provider/model download, external inference, benchmark, Golden Corpus
write, or evaluation-corpus write was performed for this gate. Existing dirty
workspace database/corpus artifacts predate this work and were neither opened
for mutation nor claimed as WP-15 output.

## Definition of Done

- [x] Strict versioned profile registry/file schema.
- [x] Explicit deterministic precedence.
- [x] Exact provider/model/revision/dimension/trust/capability identity.
- [x] Immutable runtime-owned profile snapshot and fingerprint.
- [x] Exact profile/generation readiness binding.
- [x] Missing, stale, inactive, and mismatched generation behavior remains
  fail-closed through existing lifecycle checks.
- [x] Operator model-root path removes personal-path ambiguity and stays private.
- [x] Redacted HTTP/MCP capability profile metadata.
- [x] V1-only and disabled startup profiles.
- [x] V1 provider defaults and behavior remain separate.
- [x] Operator migration/rollback documentation.
- [x] Focused, affected regression, static, governance, and diff validation.

WP-15 is COMPLETE. WP-16 behavioral verification and WP-17 final Phase 8.5
quality/certification gates remain pending.
