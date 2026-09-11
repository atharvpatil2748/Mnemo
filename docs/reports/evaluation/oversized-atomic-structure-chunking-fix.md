# Oversized Atomic Structure Chunking Fix

Status: **FOUR-DOCUMENT INTEGRATION PASS; CLEAN PHASE 8.6 REBUILD PENDING**  
Date: 2026-09-07

This report is a checkpoint, not a declaration that the full evaluation-notebook rebuild is ready. The complete `--full` orchestrator has not been rerun after the fix.

## Root cause

The canonical chunkers treated some semantic structures as atomic even when their rendered representation exceeded the governed 1,024-token chunk ceiling. Four Phase 8.6 sources exposed the same general defect through different structures:

- a PDF-extracted table row;
- an XLSX table row;
- a Markdown list;
- a Markdown table.

Failing closed was correct: truncation, omission, arbitrary character slicing, or raising the global token limit would have lost meaning or weakened the chunk contract. The missing behavior was deterministic subdivision below the oversized structure's existing semantic boundary.

## Implemented fix

The implementation adds a shared oversized-structure helper and integrates it with the existing generic and Markdown chunkers.

- Table rows are projected into ordered column groups while retaining matching header context.
- An individually oversized cell descends through paragraph, sentence, line, and finally word boundaries.
- Markdown lists split at root list-item boundaries and retain nested item metadata and order.
- Markdown tables split by data rows, repeat their header context, and use the table-row strategy if one row remains oversized.
- Every subdivision is deterministic, preserves the parent block span, records part metadata, and fails closed if an indivisible token cannot fit.
- Existing chunk behavior is unchanged when the original semantic unit already fits.

Implementation files:

- `mnemo-core/mnemo/chunkers/atomic_structures.py`
- `mnemo-core/mnemo/chunkers/generic.py`
- `mnemo-core/mnemo/chunkers/markdown.py`
- `mnemo-core/tests/unit/test_generic_chunker.py`
- `mnemo-core/tests/unit/test_markdown_chunker.py`

## Four-document production-pipeline validation

The user manually ran the real ingestion pipeline against a new isolated runtime:

`scratch/oversized-atomic-structure-validation/run-20260907T110302Z`

Its evidence file is:

`scratch/oversized-atomic-structure-validation/run-20260907T110302Z/ingestion-evidence.json`

Evidence SHA-256:

`f425995df457b9926b67909f79efc12f54327e3208ab0eb04f6930c5bc518059`

| Source | Original failing structure | Subdivision evidence | Result | Persisted chunks |
|---|---|---|---|---:|
| `dcfa97c8-e6e7-41d3-95d1-88dacb65e492.pdf` | table row | 1,164 tokens, 3 parts, conservation PASS | PASS | 1,081 |
| `ons_uk_consumer_price_inflation.xlsx` | table rows | 1,400 tokens to 4 parts and 1,347 tokens to 3 parts, conservation PASS | PASS | 1,665 |
| `pep8_python_style_guide.md` | Markdown list | 2,233 tokens, 6 parts, conservation PASS | PASS | 64 |
| `PHASE8_6_EVALUATION_REPORT.md` | Markdown table | 1,171 tokens, 3 parts, conservation PASS | PASS | 27 |

All four documents indexed successfully. The isolated database contains:

- 4 notebooks/documents/versions/sources as appropriate for the run;
- 2,837 chunks;
- 2,837 FTS rows;
- 2,837 title rows;
- 0 duplicate chunk IDs;
- 0 orphan chunks, versions, or occurrences;
- 0 stale or missing FTS rows;
- 0 orphan title rows.

The PDF retained 91 parsed image occurrences. The focused run therefore did not bypass its parser-level multimodal asset extraction.

A second user-executed ingestion completed successfully at:

`scratch/oversized-atomic-structure-validation/repeat-20260907T121044Z`

Its evidence SHA-256 is:

`73bf5386d2e8f564329074c6c1c071feef7c98ddeb92a737d9d90753f8ecdb95`

It reproduced the same notebook identity, four document/version identities, per-document chunk counts, 2,837 total chunks, FTS/title counts, parser block counts, and subdivision events. Runtime-created source membership UUIDs differ as expected.

The read-only comparator subsequently returned `DETERMINISTIC_REPEATABILITY_PASS`. Both databases produced the same canonical chunk digest:

`df3193e4ede24d332d5454266d7357c9e77937e6756d73f969d0de99401e7ef1`

All comparisons passed: chunk count, chunk IDs, ordering, exact semantic text, canonical token counts, provenance/metadata, and canonical digest. The largest resulting chunk was 1,018 tokens against the unchanged 1,024-token ceiling.

## Contract results

| Contract | Status | Evidence |
|---|---|---|
| Four formerly failing sources | PASS | All four completed through the real ingestion pipeline |
| Content conservation | PASS for encountered subdivisions | Every subdivision emitted `content_conservation=PASS`; focused unit tests also reconstruct source/cells |
| Token ceiling | PASS for persisted focused-run chunks | Ingestion validation completed with the unchanged 1,024-token ceiling |
| Provenance | PASS at focused pipeline level | Document/version/source identities persisted; zero orphan records; subdivision metadata is attached by the owning chunkers |
| Deterministic algorithm, unit level | PASS | Focused chunker tests repeat construction and compare outputs |
| Deterministic full-pipeline repeat | PASS | Exact comparison of 2,837 chunks; identical digest, IDs, order, text, token counts, and provenance/metadata |
| Normal-document regression | PASS at focused unit-test level | Previously executed focused suite: 47 passed; Ruff passed |
| Clean Phase 8.6 rebuild | PENDING | Must be run only after full-pipeline repeatability validation |
| Clean Phase 8.5 rebuild | PENDING | Must follow successful Phase 8.6 validation |
| Complete atomic `--full` rebuild | NOT RUN | Intentionally withheld |

## Production safety

The focused validation wrote only beneath its isolated scratch runtime. A post-run read-only hash check confirmed the protected production database remains:

- path: `scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db`
- SHA-256 before: `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`
- SHA-256 after: `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`
- size: 189,804,544 bytes
- unchanged: **YES**

Ollama configuration/models, BGE-M3, the production reranker, production activation, and production certification were not modified by this validation.

## Remaining validation sequence

1. Run a clean Phase 8.6-only rebuild.
2. Validate all 24 sources, embeddings, FTS5, multimodal records, integrity, and foreign keys.
3. Only after Phase 8.6 passes should Phase 8.5 and then the complete atomic `--full` orchestrator be run.

## Current decision

`OVERSIZED_ATOMIC_STRUCTURE_FIX_PASS` is not issued yet because the required clean Phase 8.6 rebuild has not completed.

`PRODUCTION_PIPELINE_REINDEX_READY` is not issued because the complete `--full` command has not been tested successfully after this change.

## Phase 8.6 clean-rebuild attempt

Run `run-20260907T125348Z` completed ingestion of all 24 sources. The four formerly failing structures all used the governed subdivision path successfully. The later multimodal phase failed before publication on Vision occurrence `5ee910ba-c786-5d3a-938a-0151700e0357`, an extracted image from PDF page 89.

A read-only one-image probe established the exact provider failure: `qwen2.5vl:latest` returned an empty caption on every attempt for a low-information, nearly uniform light-blue page image. The provider correctly refused to persist an invalid empty `VisionCaption`.

The evaluation Vision prompt contract is now revised additively from `mnemo-vision-safe/v1` to `mnemo-vision-safe/v2`. V2 requires a non-empty caption in both the JSON schema and prompt, explicitly directs the model to describe blank/uniform/decorative content as `No discernible visual content.`, requires an array for observations, and binds the exact prompt/schema material into the profile digest. It does not invent a caption in code and continues to fail closed if the model violates the contract.

Focused validation passed:

- two prompt/schema contract tests passed (`--no-cov` was used because repository-wide coverage is not meaningful for the two-test selection);
- the real retained occurrence passed through `qwen2.5vl:latest` with prompt `mnemo-vision-safe/v2`;
- prompt digest: `bbd58cdf04fe06896273d72e04abad133262cbf48f6ecd7c676bac9db4637a53`;
- caption: `A gradient background transitioning from light blue at the top to white at the bottom.`;
- two factual observations were returned as the required array;
- result: `VISION_PROBE_PASS`.

The pytest cache warning was non-functional: Windows denied writing `.pytest_cache`, but both tests executed and passed.
