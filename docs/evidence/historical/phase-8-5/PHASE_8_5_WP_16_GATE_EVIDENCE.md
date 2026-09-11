# Phase 8.5 WP-16 Gate Evidence

**Status:** PARTIAL (2026-08-28)

## Scope and evidence rule

WP-16 must prove that autonomous external clients select and compose public MCP
tools from metadata alone. Internal unit tests, direct service calls, and forced
tool chains are not behavioral passes. WP-17 final certification remains out of
scope.

## Implemented evaluation infrastructure

- Added the strict `mnemo.behavioral-manifest/1` JSON contract and JSON Schema.
- Encoded authoritative cases P85-B-01 through P85-B-31 with P0/P1 priority,
  bounded call budgets, private tool/provenance/completeness/error oracles, and
  no hidden IDs or chains in client-visible prompts.
- Added a bounded `BlindAgentEvaluator` which sends clients only the natural
  prompt, normal MCP tool metadata, and prior public tool results.
- Added an independent oracle for ordered tool families, forbidden tools,
  opaque cursor continuation, terminal completeness, false-completeness claims,
  provenance fields, safe denial codes, answer digests, resource-loop limits,
  and path/secret-shaped leakage.
- Added the complete WP-16 failure taxonomy.
- Added an adapter over initialized MCP `ClientSession` instances, usable for
  stdio and SSE without a parallel tool implementation.
- Added protected machine-readable transcripts with tool/cursor/result/answer/
  token/cost fields and a publishable redactor that removes prompts, arguments,
  results, answers, cursors, and opaque identifiers.
- Added a command-line manifest validator and transcript scorer plus an operator
  runbook for two-client/two-transport execution.

## Contract defects remediated

Focused inspection found two generic MCP guidance contradictions:

1. `search_evidence` said both that semantic image discovery was unsupported and
   that OCR/Vision/visual representations should be used for image evidence.
   The negative guidance now distinguishes semantic image discovery from direct
   original-binary delivery and gates it on advertised ready representations.
2. `run_final_qa_v2` implied `search_evidence` was the only valid predecessor.
   Its workflow now names the governed exact, structured, asset, analysis, and
   evidence paths without adding scenario-specific routing.

The multi-document description was also reconciled with WP-11's single
aggregate CursorCodecV2 continuation.

## Evaluation corpus and isolated preparation state

The configured source evaluation database was opened using SQLite URI `mode=ro`
and fingerprinted before copying:

- source: `scratch/phase8_5_11/eval-20260825-02/mnemo.db`
- SHA-256: `d70f58198e2f5d2d5d1dcff3a23bcc86681d7a924bb5d3d1fc24fba39f318b71`
- disposable copy: `scratch/phase8_5_wp16/eval-20260828-01`
- copied filesystem-store entries: 982

The source state was:

| Item | Count |
|---|---:|
| documents | 44 |
| document versions | 44 |
| canonical chunks | 2,658 |
| asset occurrences | 464 |
| OCR results | 14 |
| Vision results | 26 |
| visual embeddings | 16 |
| index generations | 0 |
| active index generations | 0 |
| structured table projections | 0 |
| vision-text projection rows | 0 |
| language-text projection rows | 0 |
| multilingual embeddings | 0 |
| visual-vector projection rows | 0 |

`scripts/phase8_5_16_prepare_evaluation.py` then used canonical parsed IR and
already-persisted derivations only. It performed zero ingestion and zero
provider calls. Its checksum guard requires the pristine source digest above.
The isolated post-build state is:

| Item | Count/state |
|---|---:|
| documents / versions / chunks | 44 / 44 / 2,658 |
| active / total index generations | 48 / 48 |
| structured table projections | 105 |
| OCR projection rows | 14 |
| Vision-text projection rows | 26 |
| visual-vector projection rows | 16 |
| language-text projection rows | 0 |
| multilingual embeddings | 0 |
| profile fingerprint | `e335cdbe14e65eafe21fe0c3eb7ee0a12aaeb11524076f207a16d9ca046828ff` |

All built generations have complete coverage and active aliases. The prepared
database checksum is
`5d85c28d7ed44d3d66c50b5d0961332063c1da276c04cdc73fb1921e4409cf61`.
The exact pinned BGE-M3, BGE reranker, and CLIP snapshots were subsequently
located in the existing operator-owned model cache and loaded offline at their
frozen revisions and dimensions. The existing Ollama model store was also
reused; `gemma4:e4b`, `nomic-embed-text`, and pinned `qwen2.5vl:latest`
completed bounded local readiness calls. No provider or model substitution was
made. The isolated database still has zero language derivations, language-text
rows, and multilingual embeddings. Repository inspection also found no
production `LanguageTransformationProviderV1` or
`MultilingualEmbeddingProviderV1` implementation/composition, so the governed
language generations cannot be built truthfully from the available source
rows. WP-10 cross-language cases therefore remain unavailable.

## Executed validation

Harness/schema/oracle/mutation suite:

```text
uv run pytest --no-cov -q mnemo-server/tests/test_wp16_behavioral_harness.py
9 passed
```

The manifest CLI validated all 31 scenario IDs against the tracked schema.

Affected MCP protocol, stdio subprocess, SSE lifecycle/authentication,
capability, WP-03 contract, and WP-14 security regression:

```text
28 passed
```

Affected MCP delivery/retrieval/structured/Final-QA regression:

```text
54 passed
```

These 91 passing functional/protocol tests plus 8 governance contract tests
produce 99 unique passing tests. The final combined harness/governance command
reported 17 passed (the 9 harness tests were a deliberate final rerun). None is
counted as a blind-agent scenario pass.

Closure-pass focused validation added:

```text
pytest --no-cov -q
  mnemo-server/tests/test_wp16_behavioral_harness.py
  mnemo-core/tests/unit/test_projection_generations.py
  mnemo-server/tests/test_mcp_conformance.py
  mnemo-server/tests/test_mcp_sse.py
  tests/governance/test_phase8_5_wp00_contracts.py
40 passed
```

The preparation evidence assertions passed for source checksum, zero provider/
ingestion calls, 48 active generations, and exact structured/OCR/Vision/visual/
language row counts. The manifest CLI again validated all 31 IDs. These checks
do not count as blind-agent scenario executions.

Model-reuse closure preflight (2026-08-28):

- exact offline Hugging Face config/tokenizer/model loads passed for BGE-M3,
  BGE reranker, CLIP, and the existing V1 cross-encoder cache;
- bounded local Ollama readiness passed for Gemma, Qwen2.5-VL, and Nomic;
- direct engine initialization reached READY, and runtime readiness reported no
  unavailable required capabilities;
- real HTTP `/v2/capabilities`, MCP stdio `get_capabilities`, and MCP SSE
  `get_capabilities` returned `mnemo.capabilities/1` with runtime ready and no
  operator-path leakage;
- stdio and SSE each advertised the same 14 tools;
- a production-path incompatibility found during HTTP startup was corrected by
  making `AdvancedRetrievalService` satisfy its existing runtime protocol; the
  focused advanced-retrieval/harness/governance regression reported 56 passed;
- manifest/schema validation again reported 31 scenarios; Ruff check, strict
  mypy on the affected production module, governance tests, source checksum,
  and `git diff --check` passed. These are preflight results only.

## External-client execution

| Client | Availability | Actual blind result |
|---|---|---|
| ChatGPT desktop | Installed/running | NOT EXECUTED. The available Windows automation safety contract explicitly prohibits automating the ChatGPT desktop UI. No transcript was fabricated. |
| Antigravity IDE | Installed and launchable | NOT EXECUTED. Inspection reached the IDE, but the target was occluded/intercepted by the prohibited ChatGPT surface before a safe prompt could be submitted; no MCP connection or transcript was proven. |

No external-client selection rate, answer score, or BUG 1–10 result is claimed.

## MCP transport discovery against the isolated copy

Real initialized MCP client sessions were opened against both transports using
the isolated configuration:

| Transport | Handshake | Advertised tools | Runtime capability call |
|---|---|---:|---|
| stdio subprocess | PASS (`mnemo-mcp`) | 14/14 | PASS: `mnemo.capabilities/1`, runtime ready |
| SSE (`/sse`) | PASS (`mnemo-mcp`) | 14/14 | PASS: `mnemo.capabilities/1`, runtime ready |

The advertised names were identical and included `get_document`, `get_asset`,
`get_image_analysis`, `search_evidence`, `query_structured`,
`run_final_qa_v2`, and `get_capabilities`. The HTTP `/v2/capabilities` route also
returned the same schema and runtime-readiness state. Capability metadata
contains no operator model path. This is transport discovery evidence, not
blind-agent scenario evidence. Optional advanced/multilingual states remain
truthfully inactive where provider/service/generation dependencies are absent.

## Scenario status

- Cases 1–31: manifest/oracle defined and schema-validated.
- Cases 1–31 through real ChatGPT: not executed.
- Cases 1–31 through real Antigravity: not executed.
- Same manifest through stdio and SSE external-client sessions: not executed.
- Original BUG 1–10: not behaviorally re-certified.

Scenario dependency state after isolated preparation:

- P85-B-01–06, 28–29, and 31: canonical evidence exists; external-client run is
  blocked by runtime/provider readiness and unavailable client automation.
- P85-B-07–15 and 30: structured projections are active; external-client run is
  blocked by runtime/provider readiness and unavailable client automation.
- P85-B-16–19: blocked additionally by absent multilingual generations/models.
- P85-B-20–25 and 27: OCR/Vision/visual projections are active; external-client
  run is blocked by runtime/provider readiness and unavailable client automation.
- P85-B-26: canonical asset occurrences exist; external-client run is blocked by
  runtime/provider readiness and unavailable client automation.

No scenario has an execution transcript or behavioral verdict.

## Original bug regression status

| Bug | State | Evidence boundary |
|---|---|---|
| 1 — last page uses exact traversal | UNVERIFIED | no genuine client transcript |
| 2 — full document reaches terminal cursor | UNVERIFIED | no genuine client transcript |
| 3 — semantic image discovery | UNVERIFIED | projection ready; no client transcript |
| 4 — actual image reaches client vision | UNVERIFIED | no client image transcript |
| 5 — CPI threshold uses structured query | UNVERIFIED | projection ready; no client transcript |
| 6 — CPI deterministic comparison | UNVERIFIED | projection ready; no client transcript |
| 7 — cross-document document-set path | UNVERIFIED | no genuine client transcript |
| 8 — every occurrence is exhaustive | UNVERIFIED | no genuine client transcript |
| 9 — English/Hindi/Marathi retrieval | BLOCKED | multilingual generation/model absent |
| 10 — mixed image and multilingual chain | BLOCKED | multilingual generation/model absent |

## Static validation

- Ruff format/check on the preparation command, harness, tests, scorer, and
  changed MCP contract:
  PASS.
- Strict mypy on the preparation command, harness, and scorer: PASS.
- Manifest JSON Schema validation: PASS.
- Affected MCP/governance contracts: PASS.
- `git diff --check`: PASS.

## Safety and compatibility

No Golden Corpus, source evaluation database, or authoritative corpus file was
modified. The disposable copy was projection-built as explicitly required.
There was no ingestion, migration, corpus inference, benchmark, or paid/cloud
API call. Exact model artifacts were reused from the operator-owned D: caches;
one-token local readiness calls were made for the required Ollama generation
roles and one bounded embedding call verified 768 dimensions. Redundant BGE
snapshots created during the interrupted provisioning attempt were moved to the
Recycle Bin after their exact D: equivalents loaded successfully. No existing
D: artifact was deleted. Two unsuccessful disposable preparation attempts are
retained under `scratch/phase8_5_wp16` for diagnosis and are not runtime inputs.
Existing 14 MCP tool names and V1 behavior remain unchanged.

## Remaining mandatory blockers

1. Implement/compose the already frozen multilingual transformation and
   embedding provider contracts, then build complete immutable language-text
   and multilingual-vector generations from real authorized source rows. Model
   availability is no longer the blocker; provider composition and absent
   derivation/embedding source rows are.
2. Execute cases 1–31 blindly through both MCP transports with at least two real
   external clients.
3. Retain protected transcripts and publish redacted per-client/model metrics.
4. Meet required thresholds with zero P0 false-completeness, authorization, and
   provenance failures; remediate and rerun any evidenced contract defects.

WP-16 remains PARTIAL. Phase 8.5 is not behaviorally verified or certified.
