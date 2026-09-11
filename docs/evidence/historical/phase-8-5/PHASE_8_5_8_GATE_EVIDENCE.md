# Phase 8.5.8 Gate Evidence

**Gate:** READY FOR REVIEW  
**Scope:** Multimodal retrieval, context, citations, and Final-QA V2 (ADR-0064)  
**Evidence date:** 2026-08-25

## Implementation

Phase 8.5.8 adds immutable `EvidenceCandidateV2` records for canonical chunks,
document ranges, positional evidence, original assets, OCR regions, vision
observations, visual-vector matches, structured rows/cells, and aggregates.
Every candidate retains notebook/source/document/version scope, authoritative
identity, original-versus-derived provenance, occurrence/derivation/generation
identity, locator, retrieval score components, title evidence, completeness,
and parent-promotion state.

`MultimodalFusionReranker` performs deterministic bounded RRF over ranked
streams without comparing raw scores from incompatible vector spaces. Visual
signals require a named vector space. Optional modality-aware reranking and
relevance-aware document/modality diversity retain every score and provenance
component. Conflicting duplicate provenance and registered reranker failures
fail closed.

`MultimodalContextBuilder` reauthorizes every item, rejects cross-notebook
evidence, checks derived generation activity, negotiates explicit provider
capability states, and enforces item/token/byte/asset/asset-byte/pixel budgets.
It passes opaque authorized resource handles rather than binary bytes and marks
all document, OCR, image, and structured content as untrusted evidence.

`FinalQAV2Orchestrator` reuses exact case-sensitive `[source:N]` validation,
the ADR-0054 single corrective retry, token preflight, retained context, and
same provider/model contract. Publication uses ADR-0056 states, an atomic
publication claim, immutable validated/published snapshots, typed citations,
fingerprint conflicts, resumable validated/assistant-published states, and
zero-generation replay. Invalid answers are never published or cited.

## Storage and migration

SQLite schema v12 additively creates `final_qa_v2_executions`,
`final_qa_v2_snapshots`, and `evidence_citations_v2`. Snapshots and citations
are hash-checked and immutable. Migration evidence covers fresh creation, v11
upgrade, repeated migration, transaction rollback after an injected statement
failure, and CompositeStorage delegation. No V1 table is changed.

## Security and recovery evidence

Focused tests cover cross-notebook/occurrence authorization, stale generations,
shared typed provenance, incompatible or unnamed vector spaces, conflicting
deduplication, malformed candidates/snapshots/provider results, prompt
injection in OCR/image/structured content, context/result explosion bounds,
capability disabled/unavailable/policy/budget outcomes, citation mapping,
snapshot tampering, retry exhaustion, crash resume, concurrent claims, and
replay conflicts. Diagnostics contain counts, kinds, bounds, completeness, and
opaque identities only; no evidence text, image bytes, vectors, prompts,
credentials, or provider reasoning is logged.

## Executed evidence

```text
uv run pytest -q --no-cov mnemo-core/tests/unit/test_multimodal.py
19 passed

Focused migration/security/regression matrix
126 passed

uv run pytest -q
1619 passed, 1 skipped, 8 warnings in 141.37s
Required test coverage of 90% reached. Total coverage: 90.08%

uv run ruff format --check .
302 files already formatted

uv run ruff check .
PASS

uv run mypy --strict mnemo-core/mnemo mnemo-server/mnemo_server plugins/email-ingestion/email_ingestion
Success: no issues found in 180 source files

uv build --package mnemo-core
uv build --package mnemo-server
uv build --package mnemo-email-ingestion
All source distributions and wheels built successfully (0.25.0)

git diff --check
PASS
```

The gate is not a release and performs no commit, push, tag, or version change.

## Compatibility and limitations

`StorageInterfaceV1`, canonical identities/text, V1 FTS/embeddings/retrieval,
V1 citations/Final-QA, `/v1/query`, `/v1/query/stream`, existing HTTP routes,
the six MCP tools, and Qdrant optionality are unchanged. Phase 8.5.1–8.5.7
contracts remain additive and compatible.

The certified Golden Corpus was inspected through a read-only SQLite URI. Its
canonical baseline remains 15 documents, 15 versions, 15 sources, 1,514
chunks, 1,514 canonical FTS rows, 1,514 title rows, zero orphan chunks, and
ordered chunk-ID/text digest
`1997852deb381869d1ff72f511fa22b97bdea5287e5f6632ef1292405bbf4e66`.
No purge, re-ingestion, canonical mutation, embedding regeneration, or Qdrant
enablement occurred. Additive schema v12 is present without V2 execution rows.

No concrete multimodal provider quality profile, multilingual retrieval,
versioned HTTP/MCP V2 delivery, binary asset delivery, or Phase 9 UI is claimed.
Rollback disables V2 composition while retaining immutable schema-v12 records;
V1 remains active.

## Verdict

`PHASE 8.5.8 GATE: READY FOR REVIEW`
