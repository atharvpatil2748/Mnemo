# Phase 8.5.9 Gate Evidence

**Gate:** PASS  
**Scope:** Multilingual processing and retrieval foundation (ADR-0067)  
**Evidence date:** 2026-08-25

## Implementation

Phase 8.5.9 adds extensible normalized BCP-47 `LanguageCode` and ISO-15924
`ScriptCode` values; deterministic document/chunk/OCR/query language
observations with detector/config/input provenance; explicit uncertainty,
mixed-language, and mixed-script states; and Unicode-normalized and optional
Devanagari-to-Latin derived search representations that never mutate canonical
text.

Provider-neutral contracts cover detection, translation/transliteration,
multilingual embeddings, reranking, retrieval, storage, and Final-QA language
policy. Profiles expose provider/model/revision, named vector-space identity,
dimension/metric/normalization, supported language/script/direction sets, and
`SUPPORTED`, `UNSUPPORTED`, `UNAVAILABLE`, `DISABLED`, `POLICY_DENIED`,
`BUDGET_DENIED`, or `UNVALIDATED` state. No production model is selected.

`MultilingualRetrievalPlanner` records the query observation and selected
native sparse, named multilingual dense, optional translation, and optional
transliteration paths. `MultilingualRetrievalService` performs bounded RRF,
reauthorizes original V2 evidence, preserves source/document/version and
language-path provenance, rejects conflicting identities, supports an additive
reranker, and reports partial/truncated/empty completeness truthfully.

Derived translations/transliterations and multilingual embeddings use semantic
cache/derivation identities scoped by notebook, exact source evidence,
language direction, provider/model/revision/profile, preprocessing, and
generation. Expensive transformations adapt to `ProcessingManifest`; cloud
translation remains policy-denied without explicit consent. Final-QA language
policy delegates to the existing immutable V2 lifecycle, adds a fingerprinted
answer-language/untrusted-evidence instruction, retains strict `[source:N]`,
and cites the original evidence candidates.

## Storage and migration

SQLite schema v13 additively creates immutable `language_observations`,
`language_derivations`, and `multilingual_embeddings` tables with scoped
indexes, cache uniqueness, and payload hashes. Tests cover fresh creation,
v12 upgrade, repeated insertion, transaction rollback after an injected
migration failure, hash tampering, cache lookup, and cross-notebook/actor
isolation. `StorageInterfaceV1` is unchanged; `CompositeStorage` delegates only
through the additive multilingual contract.

## Security and governance

Tests cover cross-notebook candidate rejection, actor/notebook-scoped reads,
shared semantic cache isolation, cloud-egress consent denial/allow, unsupported
and unvalidated directions, malformed profiles/results, result bounds,
provider capability fallback, and translated prompt-injection separation.
Persisted identities/configuration use hashes rather than raw source text in
job manifests and diagnostics. Derived content remains untrusted and original
evidence remains authoritative.

## Executed evidence

```text
uv run pytest -q --no-cov mnemo-core/tests/unit/test_multilingual.py
18 passed

uv run pytest -q
1637 passed, 1 skipped, 8 warnings in 93.60s
Required test coverage of 90% reached. Total coverage: 90.05%

uv run ruff format --check .
307 files already formatted

uv run ruff check .
PASS

uv run mypy --strict mnemo-core/mnemo mnemo-server/mnemo_server plugins/email-ingestion/email_ingestion
Success: no issues found in 184 source files

uv build --package mnemo-core
uv build --package mnemo-server
uv build --package mnemo-email-ingestion
All source distributions and wheels built successfully (0.25.0)

git diff --check
PASS
```

## Compatibility and Golden Corpus

Canonical document/version/source/chunk identities and text, V1 FTS and text
embeddings, V1 retrieval/reranking/citations/Final-QA, ADR-0054 retry,
ADR-0056 replay, existing HTTP routes, six MCP tools, and Qdrant optionality are
unchanged. Phase 8.5.1–8.5.8 contracts remain additive and compatible.

The certified database was queried read-only and remains 15 documents, 15
versions, 15 sources, 1,514 chunks, 1,514 canonical FTS rows, 1,514 title rows,
zero orphan chunks, and ordered chunk-ID/text digest
`1997852deb381869d1ff72f511fa22b97bdea5287e5f6632ef1292405bbf4e66`.
No purge, re-ingestion, canonical mutation, embedding regeneration, or Qdrant
enablement occurred.

## Limitations and rollback

English/Hindi/Marathi deterministic fixtures validate the contract and all
same/cross-language directions; they do not certify real-provider quality.
Concrete detectors, embedding/reranker models, per-direction metrics, licenses,
and hardware profiles remain Phase 8.5.11 benchmark decisions. HTTP/MCP V2
delivery remains Phase 8.5.10 work.

Rollback disables multilingual profile composition and returns to the current
English/text profile. Schema-v13 records may remain dormant; canonical V1 data
is untouched.

## Verdict

`PHASE 8.5.9 GATE: PASS`
