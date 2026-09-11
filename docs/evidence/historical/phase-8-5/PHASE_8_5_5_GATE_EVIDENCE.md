# Phase 8.5.5 Gate Evidence

**Workstream:** Vision analysis and visual embeddings  
**Decision:** ADR-0062, governed by ADR-0059, ADR-0060, ADR-0068, ADR-0071  
**Gate status:** PASS  
**Evidence date:** 2026-08-24

## Implementation

Phase 8.5.5 adds vision and image-vector capabilities strictly as immutable
derived data without widening `StorageInterfaceV1` or changing Phase 0–8
publication semantics:

- typed vision profiles, requests, capabilities, structured captions,
  observations, regions, entities, relations, language/confidence metadata,
  failures, results, and derivations;
- typed image-embedding profiles, requests, capabilities, vectors, provider
  metadata, and derivations with explicit dimensions, metric, normalization,
  and optional provider-declared shared-space identity;
- `VisionProviderV1`, `VisualEmbeddingProviderV1` (also exported under the
  ADR-0062 name `ImageEmbeddingProviderV1`), `VisionAssetReaderV1`, and
  `VisionStoreV1` additive protocols;
- deterministic SHA-256 cache and content/vector identities plus deterministic
  occurrence-scoped `AssetDerivation` identities;
- governed `VisionProcessingOperation` and
  `VisualEmbeddingProcessingOperation` handlers using the existing ADR-0060
  worker, leases, attempts, retry, cancellation, progress, cost ledger,
  consent, budgets, and resource admission;
- immutable SQLite vision and visual-vector records and an independent visual
  projection bound to the existing atomic index-generation lifecycle; and
- engine and `CompositeStorage` access through additive capabilities.

No concrete VLM or image-embedding provider is silently selected. Deterministic
contract fakes validate orchestration and persistence; real-provider quality
and deployment-profile selection remain later operational decisions.

## Identity, provenance, and cache

Vision identity binds notebook/document/version/occurrence, original asset ID
and SHA-256, media type, provider/model revision, profile, preprocessing,
analysis schema, prompt-template ID and hash, language hints, bounds, and
generation. Image-vector identity additionally binds dimensions, metric,
normalization, shared-space declaration, and optional source-vision
derivation. Meaningful mutations invalidate the identity while identical
requests converge.

All cache reads are notebook-authorized through the occurrence-to-source
relationship. A shared content hash or asset ID is not an authorization
capability. Every persisted result traces the exact document, version,
occurrence, asset, derivation, provider/model/profile, and generation.
Generated captions are labelled `derived_vision`; they never become canonical
document content.

## Provider, governance, recovery, and observability

- Capability checks enforce media, language, dimensions, pixels, response
  size, structured-result cardinality, geometry, confidence, vector dimension,
  metric, normalization, and shared-space declarations.
- Cloud/paid execution remains subject to explicit ADR-0060 trust, consent,
  and budget policy. Policy denial makes zero provider calls; no provider
  fallback occurs.
- Provider cancellation and caller cancellation mark derivations cancelled and
  prevent publication. Transient timeout is bounded by the job retry policy.
- A crash after immutable result persistence recovers an expired lease and
  replays the authorized cache with zero additional provider calls. A stale
  worker cannot complete through the underlying lease contract.
- Safe ledger metadata records provider/model/profile, counts, dimensions,
  metric/normalization, generation, cache outcome, and wall time. It excludes
  image bytes, captions, observations, vectors, prompts, secrets, and
  credentials.

## SQLite and visual-vector lifecycle

SQLite schema version **10** is an additive transactional migration from
schema v9. It adds `vision_results`, `visual_embeddings`, and
`visual_vector_projection_rows` with provenance/cache/generation indexes.
Fresh creation, repeated migration, v9 upgrade, and injected migration rollback
are tested.

Result writes are immutable, transactional, and require matching
`AssetDerivation` and occurrence provenance. Projection requires the immutable
stored vector and a matching `BUILDING` `visual_vector` generation. Profile,
provider/model revision, preprocessing, dimension, metric, normalization, and
space identity must match. Projection is idempotent; promotion and rollback use
the established atomic generation lifecycle. Qdrant is neither required nor
enabled.

## Security proof

Tests cover cross-notebook access, shared hashes across scopes, unauthorized
cache reads, cloud-consent denial, exact asset/hash/MIME validation, active SVG
rejection, malformed provenance/provider output, unsupported languages/media,
extreme pixels/dimensions, structured-output and UTF-8 byte bounds, invalid
geometry/confidence, wrong vector dimensions, NaN/Inf, normalization mismatch,
vector-hash mismatch, cancellation, timeout/retry, and image prompt-injection
content. Provider text remains untrusted evidence and cannot alter system
policy, authorization, tools, credentials, or storage behavior.

## Executed evidence

```text
uv run pytest mnemo-core/tests/unit/test_vision.py -q --no-cov
19 passed, 1 warning in 1.79s

uv run pytest -q
1527 passed, 1 skipped, 8 warnings in 76.95s
Required test coverage of 90% reached. Total coverage: 90.03%

uv run ruff format --check .
286 files already formatted

uv run ruff check .
All checks passed

uv run mypy --strict mnemo-core/mnemo mnemo-server/mnemo_server plugins/email-ingestion/email_ingestion
Success: no issues found in 167 source files

uv build --package mnemo-core
uv build --package mnemo-server
uv build --package mnemo-email-ingestion
All three package builds succeeded (0.25.0 artifacts)

git diff --check
Passed
```

## Phase 0–8 and Golden Corpus compatibility

The complete repository regression suite passed. Existing parsers, canonical
chunks, retrieval/RRF/reranking, canonical FTS and text embeddings, HTTP V1,
six MCP tools, citations, Final QA/replay, and optional Qdrant behavior are
unchanged by this workstream.

The certified corpus was verified using a read-only SQLite URI:

```text
documents=15, versions=15, sources=15
chunks=1514, fts_rows=1514, title_rows=1514
sha256(concatenated ordered chunk id + text)=1997852deb381869d1ff72f511fa22b97bdea5287e5f6632ef1292405bbf4e66
database last-write UTC=2026-08-20T15:17:19
```

No purge, re-ingestion, corpus content write, or Qdrant enablement was
performed.

## Known limitations and rollback

Phase 8.5.5 does not bundle or certify a concrete VLM/image-embedding provider,
model quality, multimodal retrieval/fusion, OCR/vision retrieval consumption,
multimodal Final QA, multilingual retrieval, or new HTTP/MCP delivery.
Synthetic deterministic providers certify contracts and orchestration only.

Rollback is non-destructive: stop/reject vision and image-embedding jobs,
disable provider profiles, and detach/retire visual-vector generations.
Immutable derivations may remain for audit while original assets and every
Phase 0–8 text path remain available.

## Verdict

**PHASE 8.5.5 GATE: PASS**
