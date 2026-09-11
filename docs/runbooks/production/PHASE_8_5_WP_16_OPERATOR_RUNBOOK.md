# Phase 8.5 WP-16 Blind External-Client Runbook

## Purpose

This procedure records real blind behavior from an MCP client. Passing harness
unit tests or direct service/API calls is not external-agent evidence.

The governed manifest is
`evaluation/phase8_5_wp16/behavioral_manifest.json`. Never send its `oracle`
objects, expected tool chains, fixture identities, or expected answers to the
client. The client receives only one scenario's `prompt`, the ordinary MCP tool
list/schemas/descriptions, capability metadata it chooses to request, and tool
results.

## Preconditions

1. Work from an isolated writable copy of the Phase 8.5 evaluation database and
   blob store whose source is opened read-only and checksum-pinned. Never point a
   behavioral client at the frozen Golden Corpus or source evaluation DB.
2. Confirm required projection generations are READY and ACTIVE for the exact
   selected WP-15 profile fingerprint. Unavailable generations are recorded as
   unavailable; they are never fabricated or promoted for this run.
3. Record client name/version, model/revision, MCP transport, Mnemo configuration
   fingerprint, capability snapshot identity, run ID, and tool-call budget.
4. Store protected transcripts outside published documentation. Published
   summaries use `redact_transcript` and contain hashes/metrics, not source text,
   prompts, evidence, opaque IDs, paths, cursors, or credentials.

The prepared local candidate used for the 2026-08-28 closure attempt is
`scratch/phase8_5_wp16/eval-20260828-01`. Its preparation command is:

```powershell
$env:PYTHONPATH = "mnemo-core;mnemo-server"
.venv\Scripts\python.exe scripts/phase8_5_16_prepare_evaluation.py `
  --database scratch/phase8_5_wp16/eval-20260828-01/mnemo.db `
  --files scratch/phase8_5_wp16/eval-20260828-01/files `
  --config scratch/phase8_5_wp16/eval-20260828-01/mnemo.wp16.toml `
  --source-checksum d70f58198e2f5d2d5d1dcff3a23bcc86681d7a924bb5d3d1fc24fba39f318b71 `
  --output scratch/phase8_5_wp16/eval-20260828-01/preparation-evidence.json
```

The command projects only canonical IR and persisted OCR/Vision/visual evidence.
It does not build missing multilingual embeddings, invoke providers, or ingest.
Do not start client execution unless `get_capabilities` succeeds and reports the
scenario-required generation/provider states truthfully.

Before starting either transport, point the existing operator controls at the
already verified local caches; do not copy model files into the repository:

```powershell
$env:MNEMO_PHASE85_MODEL_ROOT = "<operator-owned-phase85-model-root>"
$env:HF_HOME = "<operator-owned-huggingface-root>"
$env:HUGGINGFACE_HUB_CACHE = "<operator-owned-huggingface-hub-cache>"
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
$env:OLLAMA_MODELS = "<operator-owned-ollama-model-root>"
```

The local closure preflight found the models but still reported multilingual
retrieval inactive: no production multilingual provider implementation is
composed and the isolated database has no language-derivation or multilingual-
embedding source rows. Do not execute or score multilingual scenarios as PASS
until a later governed build closes that dependency.

## Validate the manifest

```powershell
uv run python scripts/phase8_5_16_behavioral.py `
  --manifest evaluation/phase8_5_wp16/behavioral_manifest.json `
  --schema evaluation/phase8_5_wp16/behavioral_manifest.schema.json
```

## Client matrix

Run every scenario through both MCP transports and at least two genuine external
clients. The intended release-candidate matrix is:

| Client | Transport 1 | Transport 2 |
|---|---|---|
| ChatGPT with the normal Mnemo MCP connection | stdio | SSE |
| Antigravity with the normal Mnemo MCP connection | stdio | SSE |

If a client cannot use one transport, record `TRANSPORT_FAILURE`; do not replace
it with a direct Python call. Do not tell either client which tool to select.

## Per-scenario capture

Capture a `mnemo.behavioral-transcript/1` document containing the tool list,
tool calls and arguments, structured tool results, final answer, claimed
completeness, token/cost metadata, and whether the bounded call budget was
exhausted. The protected transcript may contain evidence required by the oracle
and must remain access-controlled.

Score it without printing protected content:

```powershell
uv run python scripts/phase8_5_16_behavioral.py `
  --manifest evaluation/phase8_5_wp16/behavioral_manifest.json `
  --scenario-id P85-B-01 `
  --transcript C:\isolated-evidence\chatgpt-stdio-P85-B-01.json
```

The output contains only the redacted transcript summary and deterministic
verdict. Retain the protected source transcript so findings remain auditable.

## Acceptance

- Execute cases P85-B-01 through P85-B-31 for each supported client/model and
  both transports.
- P0 cases require zero false-completeness, authorization, and provenance
  failures.
- Report selection, follow-up chain, identifier propagation, cursor completion,
  answer, provenance, completeness, bounds/cost, and security separately.
- An API-correct result is not an agent-selection pass.
- Do not collapse client/model results into one score.
- Do not mark WP-16 complete until at least two real external clients have
  executed the governed manifest and the required thresholds pass.

## Failure handling

Classify every failure using `FailureCode`. Reproduce it, locate the ownership
boundary, make only generic contract/runtime corrections permitted by the
accepted architecture, and rerun the smallest affected scenario. Never add
fixture names, expected answers, hidden IDs, or scenario-specific routing to MCP
metadata.
