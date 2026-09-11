# Phase 8.5.4 Gate Evidence

**Workstream:** OCR derivations  
**Decision:** ADR-0061, governed by ADR-0059, ADR-0060, ADR-0068, ADR-0071  
**Gate status:** PASS  
**Evidence date:** 2026-08-24

## Implementation

Phase 8.5.4 adds OCR strictly as immutable derived data without widening
`StorageInterfaceV1` or changing Phase 0–8 publication semantics:

- typed `OCRProfile`, `OCRRequest`, `OCRResult`, `OCRRegion`, language,
  confidence, failure, capability, provider-metadata, derivation, detector, and
  evidence-reference models;
- `OCRProviderV1`, `OCRAssetReaderV1`, and `OCRStoreV1` additive protocols;
- a versioned conservative scanned-page detector for text-native, image-only,
  mixed, blank, unsupported, malformed, and unknown pages;
- deterministic SHA-256 cache/result identities and occurrence-scoped
  deterministic derivation/region identities;
- an `OCRProcessingOperation` executed only through the ADR-0060 worker,
  leases, attempts, progress, consent, budgets, resource admission, retry,
  cancellation, usage ledger, and crash recovery;
- immutable SQLite OCR results, ordered regions, language observations,
  explicit failures, and an independent generation-aware OCR FTS projection;
- exact original document/version/occurrence/asset/derivation/region provenance
  for every derived evidence reference; and
- engine and `CompositeStorage` delegation through additive protocols.

No concrete OCR provider is silently selected. `OCRProviderV1` is verified
with deterministic contract fakes; provider accuracy benchmarking and a
deployment profile remain explicit later operational decisions.

## Identity, completeness, and provenance

OCR cache identity binds the authorized notebook/document/version occurrence,
original asset ID and SHA-256, media type, provider/model revision, profile,
preprocessing digest, language hints, selected pages, limits, and index
generation. Semantically identical requests converge; meaningful mutations
invalidate the identity.

Results support `COMPLETE`, `PARTIAL`, `FAILED`, and `UNAVAILABLE`. Partial
results retain both successful ordered regions and typed page failures. Failed
or unavailable results cannot enter the projection. Geometry and confidence
are explicitly unavailable when a provider does not supply them; coordinates
are never fabricated. OCR text is labelled `derived_ocr` and untrusted.

## Provider, job, cache, and governance proof

- Provider capabilities declare media, language/script, page/pixel, geometry,
  confidence, and cancellation support.
- The operation verifies occurrence authorization, exact asset/hash/MIME,
  decoded-pixel/output/byte/time limits, capability compatibility, and provider
  result provenance before publication.
- Cloud work remains subject to explicit ADR-0060 trust/consent/budget policy;
  policy denial performs zero provider calls.
- Provider timeout is classified for bounded retry; retry exhaustion is
  terminal. Cancellation before execution or publication prevents publication
  and marks the derivation cancelled.
- A crash after immutable derivation commit replays from the authorized cache
  after lease recovery with zero additional provider calls.
- Cache lookup is notebook-authorized; a shared content hash is not an access
  capability.

## SQLite and projection

SQLite schema version **9** is an additive transactional migration from schema
v8. It adds `ocr_results`, `ocr_regions`, `ocr_language_observations`,
`ocr_failures`, `ocr_projection_rows`, and an independent `ocr_fts` virtual
table plus provenance/generation indexes. Fresh creation, repeated migration,
v8 upgrade, and injected migration rollback are tested.

Result and projection writes are transactional. Results are immutable and
must match an authorized `AssetDerivation`. Only stored `COMPLETE`/`PARTIAL`
results can project into a matching `BUILDING` `ocr_text` generation; repeated
projection is idempotent. Promotion uses the existing atomic generation
lifecycle. Canonical FTS and embeddings are untouched.

## Security and observability

Tests cover unauthorized notebook access, shared hashes across scopes, active
SVG rejection, malformed provenance, hash/MIME changes, unsupported language,
unsupported geometry/confidence, extreme pixel count, bounded bytes/output,
provider timeout, cancellation, invalid provider payloads, unsafe reason codes,
and OCR instruction-injection text. Recognized text is stored only as untrusted
derived evidence and is absent from logs and cost ledger metadata.

Safe usage accounting records provider/model/profile, pages and regions,
success/failure counts, languages/scripts, confidence availability, cache
hit/miss, wall time, attempt ID, and completeness—never document bytes, OCR
text, prompts, credentials, or secrets.

## Executed evidence

```text
uv run pytest mnemo-core/tests/unit/test_ocr.py -q --no-cov
9 passed, 1 warning in 2.16s

uv run pytest -q
1508 passed, 1 skipped, 8 warnings in 76.32s
Required test coverage of 90% reached. Total coverage: 90.08%

uv run ruff format --check .
281 files already formatted

uv run ruff check .
All checks passed

uv run mypy --strict mnemo-core/mnemo mnemo-server/mnemo_server plugins/email-ingestion/email_ingestion
Success: no issues found in 163 source files

uv build --package mnemo-core
uv build --package mnemo-server
uv build --package mnemo-email-ingestion
All three package builds succeeded

git diff --check
Passed
```

## Phase 0–8 and Golden Corpus compatibility

The complete repository regression suite passed. Existing V1 parsers/chunks,
retrieval/RRF/reranking, canonical FTS and embeddings, HTTP routes, six MCP
tools, citations, Final QA/replay, and optional Qdrant behavior were not
changed by this workstream.

The certified corpus was inspected read-only after implementation:

```text
documents=15, versions=15, sources=15
chunks=1514, fts_rows=1514, title_rows=1514
sha256(concatenated ordered chunk id + text)=1997852deb381869d1ff72f511fa22b97bdea5287e5f6632ef1292405bbf4e66
database last-write UTC=2026-08-20T15:17:19.0379067Z
```

No purge, re-ingestion, corpus write, or Qdrant enablement was performed.

## Known limitations and rollback

Phase 8.5.4 does not bundle or certify the recognition quality of a concrete
OCR engine. It does not add page rendering, VLM, visual embeddings, OCR-derived
dense vectors, V1/V2 OCR retrieval consumption, multilingual retrieval, or new
HTTP/MCP delivery. The data model is script/language capable, but no
multilingual retrieval claim is made.

Rollback is non-destructive: stop/reject OCR jobs and detach the OCR generation
alias/provider. Immutable OCR records may remain for audit while original
assets and all Phase 0–8 text paths remain available.

## Verdict

**PHASE 8.5.4 GATE: PASS**
