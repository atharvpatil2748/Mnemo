# Mnemo Phase 8.5 Architecture

> **Status:** CERTIFIED for the exact ADR-0076 production snapshot. This
> blueprint is interpreted through the current
> [single-production-path audit](../../reports/architecture/mnemo-v2-single-production-path-audit.md);
> intermediate activation and blocker language remains historical evidence.

*Advanced Retrieval, Multimodal Knowledge, and Multilingual Context*

**Status:** ARCHITECTURE ACCEPTED & IMPLEMENTED — 8.5.1–8.5.11 Implemented, Evaluated, and Governed

**Baseline:** Mnemo v0.25.0; Phases 0–8 remain frozen

**Scope:** Additive design for a new Phase 8.5 between MCP (Phase 8) and the Web UI (Phase 9)
**Normative force:** This blueprint does not supersede an ADR. ADR-0058 through
ADR-0071 are the accepted decision package governing implementation.

## Evidence legend

Current-state claims use these labels:

- **[CODE]** verified in the v0.25.0 implementation.
- **[ADR]** verified in an accepted ADR or active documentation.
- **[INFERRED]** a consequence of verified behavior that is not itself a frozen contract.
- **[PROPOSED]** an accepted Phase 8.5 design. Workstreams 8.5.1–8.5.11 are
  implemented, benchmarked, and governed. WP-15 selects the pinned candidate
  models through `config/model_profiles/phase8_5_profiles.toml`; operator model
  roots are private configuration and are never embedded in public metadata.

Historical changelogs and governance reports were used as implementation history, not as substitutes for current code. The principal frozen references are ADR-0001 through ADR-0057, with ADR-0008 superseded by ADR-0011 and ADR-0057 narrowly superseding ADR-0042’s pair construction and ordering.

---

## 1. Executive summary

**[CODE]** Mnemo already has strong foundations for Phase 8.5: immutable document/version/chunk identities, a generic content-addressed `Asset`, transient image extraction records, canonical `ImageBlock` occurrences, exact-version storage, sparse and optional dense retrieval, provenance-preserving fusion/reranking/context, persisted Final-QA snapshots, and read-only MCP transports.

**[CODE]** Original and extracted assets are catalogued with typed occurrences; optional OCR, vision analysis, and visual vectors are immutable governed derivations. Phase 8.5.6 adds typed ranked/exhaustive result sets, positional canonical lookup, bounded expansion, and representation-local orchestration. Phase 8.5.7 adds deterministic structured extraction and safe aggregation over exact-version canonical table projections. Phase 8.5.8 additively fuses authorized typed evidence with named vector-space provenance, builds bounded multimodal context, resolves typed citations, and publishes immutable Final-QA V2 snapshots with zero-generation replay. Phase 8.5.9 adds extensible language/script observations, capability-aware same/cross-language planning, derived translation/transliteration provenance, independent multilingual vector identities, bounded language-path fusion, and answer-language policy. Phase 8.5.10 adds a shared bounded delivery service, additive V2 HTTP routes, four additive MCP tools, native binary resources, signed continuation cursors, and truthful capability states. Phase 8.5.11 completed full evaluation, 3-candidate model benchmarks, and production profile selection (`phase8_5_models.toml`). V1 retrieval and Final-QA/citations remain unchanged.

**[CODE]** WP-15 makes profile activation reproducible. One strict tracked
document supplies exact provider/model/revision/dimension/trust/capability
identity; inline component configuration and environment leaf overrides resolve
into one immutable fingerprinted snapshot. Generation-backed V2 capabilities
activate only for the exact fingerprint. V1 embedding and reranker configuration
remain independent, and explicit `v1_only` and `disabled` profiles require no
Phase 8.5 model loading.

**[PROPOSED]** Phase 8.5 should be additive and use five coordinated pillars:

1. **Advanced retrieval orchestration:** typed intent routing into ranked, positional, exhaustive, structured, and aggregate execution paths with explicit completeness.
2. **Multimodal knowledge:** retain original document bytes and extracted assets; index immutable asset occurrences and versioned derived OCR/vision representations.
3. **Multimodal retrieval and context:** fuse typed text, asset, OCR, description, visual-vector, metadata, and structured evidence without flattening it into canonical `Chunk.text`.
4. **Client-controlled expansion:** bounded document, chunk, asset, and analysis retrieval through versioned REST/MCP contracts.
5. **Multilingual context:** script/language provenance, multilingual OCR, benchmark-selected multilingual dense/reranking providers, optional derived translations, and explicit answer-language policy.

**[PROPOSED]** The recommended vector architecture is hybrid: separate text and image collections by embedding family and index generation, with an optional shared multimodal collection only when a provider explicitly guarantees a shared space. Rank-based fusion combines incomparable score domains. Expensive work is opt-in, queued, cancellable, resumable, budgeted, and content-addressed.

---

## 2. Motivation

**[ADR]** Mnemo is a local-first knowledge engine whose outputs must remain attributable to exact source evidence. **[ADR]** Existing retrieval intentionally bounds every operation and refuses to claim completeness. **[CODE]** This is correct for conversational top-k QA but insufficient for requests such as “all occurrences,” “page 17,” “count rows satisfying a predicate,” or “look at these images.”

**[INFERRED]** Forcing these requests through semantic top-k search would produce plausible but dishonest answers. Flattening OCR or VLM descriptions into canonical chunks would erase the distinction between source truth and model-derived interpretation. Sending unbounded documents or assets to clients would introduce resource and disclosure hazards. Using an English cross-encoder for cross-language claims without evaluation would create an unverified capability.

Phase 8.5 exists to make these distinctions first-class before Phase 9 builds UI assumptions and before Phases 10–11 build background enrichment and cross-document reasoning on incomplete retrieval semantics.

---

## 3. Current Phase 0–8 architecture

### 3.1 Frozen identity and provenance

- **[ADR]** `Document`, `DocumentVersion`, `Chunk`, `Source`, `Asset`, `ImageBlock`, `Citation`, and their identity rules are frozen by ADR-0001 and successor contracts.
- **[ADR]** A `DocumentVersion` is the exact-version provenance boundary. A `Source` associates a notebook with a canonical document; it is not a filename/title surrogate.
- **[ADR]** A `Chunk` identity derives from exact version, source span, and text. Runtime retrieval metadata must not mutate its persisted text or identity.
- **[ADR]** `Asset` is already a storage-independent immutable binary record: UUID, MIME type, SHA-256 content hash, opaque storage URI, optional dimensions, and metadata.
- **[ADR]** `ImageBlock` is an occurrence in a `ParsedDocument` that references an `Asset`; page and bounding-box fields belong to the block occurrence.
- **[ADR]** Final-QA evidence retains the exact chain from raw retrieval through fusion, reranking, context, generation, citation, and immutable execution snapshot. ADR-0056 replay must perform zero regeneration.

### 3.2 Ingestion

**[CODE]** The current production path is parser routing → cleaner → deterministic classifier → transient-asset persistence → canonicalization → parsed IR → chunking → text embedding → SQLite/FTS and optional Qdrant indexing. Parsers are pure and synchronous; orchestration owns storage and permanent identities.

**[CODE]** Current image behavior:

| Format | Detection/extraction today | Provenance retained today | Current limitation |
|---|---|---|---|
| PDF | bounded embedded raster extraction | page, occurrence order, reliable bounding box | no OCR/rendering; the PDF image object may differ from pre-PDF source bytes |
| DOCX | ordered body drawing relationships, including repeated uses | body/inline order and relationship ID | headers, OLE, SmartArt, and unavailable geometry are not fabricated |
| PPTX | bounded slide picture relationships, including repeated uses | slide, shape order, relationship ID, alt text, EMU geometry | charts/SmartArt are not rendered; V1 remains text-only |
| XLSX | bounded worksheet drawing-image relationships | sheet, anchor cell range, drawing order, relationship ID | charts are not rendered; V1 remains text-only |
| HTML | data-URI images only | deterministic DOM-position occurrence and alt text | external/local references are deliberately not fetched by pure parser |
| Markdown | data-URI images only | deterministic block-position occurrence and alt text | external/local references are deliberately not fetched by pure parser |
| standalone image | exact supported raster/SVG bytes as one occurrence | standalone typed locator | no OCR/VLM; active/external SVG content rejected |

**[CODE]** `IngestionPipeline._persist_asset()` passes empty metadata to `put_asset`; `TransientAsset.page_number` is therefore not copied into the `Asset`. The occurrence still retains page/bounding-box data through `ImageBlock` where the parser emitted it.

**[CODE]** Chunkers can preserve image asset IDs in metadata for some semantic strategies, but image blocks without authored alt text often produce no searchable text. No generated description is substituted.

**[CODE]** New production ingestion retains uploaded bytes as an exact-version `DocumentBinaryReference`. Historical versions without authoritative bytes remain explicitly unavailable and are never reconstructed from chunks.

### 3.3 Embedding and storage

- **[CODE]** `EmbeddingProviderV1` accepts text only and returns a fixed-dimensional vector.
- **[CODE]** The active local configuration uses Ollama `nomic-embed-text`, dimension 768, with a SQLite content/model cache. Qdrant and SurrealDB are disabled locally.
- **[CODE]** Cache identity is `sha256(text)::model_name`; it has no provider revision, configuration, modality, normalization, or operation dimension.
- **[CODE]** Filesystem asset storage is content-addressed and verifies SHA-256 on read. Identical bytes converge on one asset identity.
- **[ADR]** Qdrant projections are derived and non-authoritative. Exact-version and notebook/source filtering occurs before bounded retrieval.

### 3.4 Retrieval and Final QA

- **[CODE]** Planner intents are factual, comparative, exploratory, and synthesis. Modes are dense, sparse, hybrid, graph, and parent; graph/parent are not directly executable planner modes in the current multi-source orchestrator.
- **[CODE]** Each subquery is bounded to 1–100 results; global fusion is bounded to 1–100.
- **[ADR]** Sparse retrieval uses parameterized SQLite FTS5, exact-version metadata filters, raw `-bm25`, canonical title projection, and deterministic chunk-ID ties.
- **[ADR]** Multi-source retrieval uses unweighted RRF (`k=60`) because raw dense/sparse scores are not comparable.
- **[ADR]** Parent promotion is source-local and single-pass. Fusion and reranking retain the exact raw evidence graph.
- **[ADR]** ADR-0057 supplies canonical title text to the cross-encoder without changing `Chunk.text` and applies an exact-title-evidence ordering tier.
- **[ADR]** Context is text-only, token-bounded, and made of verbatim or derived compressed text items. It cannot carry original binary assets.
- **[ADR]** Persisted Final QA is complete-only and citation strict; preview query/stream paths are transient.

### 3.5 Server, MCP, and UI

- **[CODE]** FastAPI is a thin Layer-2 adapter over `KnowledgeEngine`; auth modes are none, API key, and JWT. There is no per-principal notebook ownership model.
- **[CODE]** The six frozen read-only MCP tools remain unchanged: `query_notebook`, `search_all_notebooks`, `list_notebooks`, `get_notebook_summary`, `get_source_insights`, and `get_timeline`.
- **[CODE]** Phase 8.5.10 appends `get_document`, `get_document_chunk`, `get_asset`, and `get_image_analysis`; WP-06 enriches occurrence inventory with authorized derivation descriptors, adds explicit/latest-ready/all analysis selection, and emits native image content only for complete recognizable raster media while partial media remains a provenance-bearing range resource.
- **[CODE]** WP-07 additively exposes canonical ranked/exhaustive evidence through `POST /v2/retrieval/evidence` and MCP `search_evidence`; ranked results remain bounded/unknown, exhaustive lexical enumeration uses signed snapshot continuation, and unavailable derived representations remain explicit rather than being treated as no-match or complete.
- **[CODE]** The React UI is only a development shell. Phase 9 functionality is planned, not implemented.

---

## 4. Historical gap analysis and current disposition

| Gap | Evidence | Consequence |
|---|---|---|
| V1 intent vocabulary is intentionally small | **[CODE]** Phase 8.5.6 adds additive typed ranked/exhaustive/positional plans | V1 remains frozen while advanced callers can express the broader contract |
| V1 has no completeness contract | **[CODE]** advanced, structured, multimodal, multilingual, and delivery results carry explicit completeness | top-k is not represented as exhaustive |
| V1 has no evidence cursor | **[CODE]** advanced retrieval and delivery use bounded signed snapshot cursors | exhaustive scans and expansion report termination/truncation |
| V1 has no structured executor | **[CODE]** Phase 8.5.7 provides an allowlisted typed executor over exact-version projections | authoritative aggregates do not rely on an LLM |
| V1 asset catalog was not queryable | **[CODE]** Phase 8.5.1/8.5.10 provide occurrence-scoped catalog lookup and bounded delivery | image inventory and authorization are explicit |
| Incomplete image extraction | **[CODE]** parser matrix above | slide/workbook and many document visuals are absent |
| Historical versions may lack source bytes | **[CODE]** new ingestion retains exact originals; unavailable historical bytes are never fabricated | lazy reparse is possible only when authoritative bytes exist |
| V1 does not consume derived OCR/vision/vector evidence | **[CODE]** independent derivations and advanced representation sources exist | V1 remains frozen; V2 orchestration keeps each representation typed |
| V1 candidates/context/citations are text-only | **[CODE]** Phase 8.5.8 adds typed multimodal candidates, context, citations, and immutable Final-QA V2 | derived evidence is not flattened into V1 |
| No bundled production OCR/VLM provider profile | **[CODE]** durable governance plus `OCRProviderV1` and `VisionProviderV1` operations are implemented; deployment provider selection/benchmarking remains pending | no implicit cloud/paid processing and no advertised OCR/VLM quality profile |
| V1 language metadata is weak | **[CODE]** Phase 8.5.9 adds extensible language/script/confidence/provider observations and derived transformations | concrete language directions remain unvalidated until 8.5.11 |
| V1 reranker is English-centric | **[CODE]** the frozen V1 MS MARCO MiniLM remains pinned; multilingual rerankers are provider-profile contracts | cross-language model quality is explicitly unverified |
| Asset transport | **[CODE]** bounded authorized HTTP/MCP document, occurrence, asset, and analysis delivery is implemented | Phase 9 may consume the frozen delivery contracts |
| Asset-aware authorization | **[CODE]** delivery resolves notebook → source → exact version → occurrence and never treats an asset ID/hash as authority | shared content-addressed bytes remain logically isolated |

### 4.1 Documentation observations

The audit found active-document drift that Phase 8.5 implementation must not inherit:

- **[CODE + documentation]** `mnemo-core/README.md` still describes v0.20.1 and says retrieval remains Phase 6, while the root README, current code, and v0.25.0 certification show Phases 0–8 complete.
- **[ADR + documentation]** `mnemo-server/README.md` describes `POST /v1/query` as full grounded/persisted citation generation and broadly calls search hybrid. ADR-0055 and current certification define `/v1/query` as transient preview, reserve persisted snapshots for `/final-qa`, and describe the certified local profile as sparse-only because Qdrant is disabled.
- **[CODE + documentation]** the living architecture’s broad boundary table lists OCR/layout analysis as an engine responsibility. The provider-neutral contract and governed operation now exist, while a benchmark-selected deployment provider and scanned-page rendering adapter remain explicit plugin/profile decisions.
- **[CODE]** `get_notebook_summary` and `get_source_insights` return persisted records; they do not currently generate fresh summaries/insights despite broad MCP prose that can be read otherwise.

These are objective documentation-reconciliation tasks for the eventual implementation phase. They are not evidence that the missing capabilities exist, and this planning-only task intentionally does not modify those active files.

---

## 5. Phase 8.5 goals

**[CODE]** Workstreams 8.5.1–8.5.10 now:

1. Route each request to an explicit retrieval execution family.
2. Provide deterministic exact, positional, structured, exhaustive, aggregate, cross-document, asset, and multimodal retrieval.
3. Report completeness as `complete`, `partial`, `truncated`, `bounded`, or `unknown` with reasons and continuation state.
4. Retain original document bytes for new versions and extract queryable visual assets with exact occurrence provenance.
5. Add optional OCR, vision analysis, and visual embeddings as immutable derived records.
6. Keep expensive analysis opt-in, budgeted, cached, queued, cancellable, resumable, and observable.
7. Deliver original assets—not only descriptions—to authorized REST/MCP/UI clients.
8. Add same-language and cross-language retrieval with benchmarked provider choices and preserved original language.
9. Preserve all Phase 0–8 identities, citations, snapshots, and transient/persisted API distinctions.
10. Establish measurable certification gates before Phase 9 consumes the new surface.

---

## 6. Non-goals

**[PROPOSED]** Phase 8.5 will not:

- turn Mnemo into an agent, web browser, code runner, or external action system;
- mutate canonical `Chunk.text` with OCR, translations, or model descriptions;
- make OCR, VLM, cloud processing, or visual embeddings mandatory at ingestion;
- claim exhaustive results from bounded top-k retrieval;
- make a generated image description authoritative over original pixels;
- automatically translate and replace source text;
- enable Qdrant or SurrealDB against deployment policy;
- implement Phase 10 notebook summaries, Phase 11 graph reasoning, or the complete Phase 9 UI;
- backfill missing old assets without exact original bytes;
- change ADR-0045 citation grammar or ADR-0056 replay semantics;
- select multilingual/visual models without reproducible evaluation.

---

## 7. Architecture principles

1. **Original artifacts are authoritative.** Binary bytes and source text are immutable facts; OCR, descriptions, translations, and embeddings are derived observations.
2. **Occurrence is distinct from content.** One content-addressed asset may occur multiple times, versions, pages, slides, sheets, or notebooks.
3. **No lossy flattening.** Typed candidates retain identity, modality, derivation, raw scores, and occurrence provenance through every boundary.
4. **Execution families are honest.** Ranked search, exhaustive scans, positional lookup, structured execution, and aggregation have separate contracts.
5. **Completeness is explicit.** Every retrieval response states what universe was searched, bounds applied, and whether more results exist.
6. **Existing V1 stays valid.** Add V2/additive contracts; do not widen frozen V1 models until a successor ADR says so.
7. **Scores remain source-local.** Use calibrated provider scores only inside their domains; use rank fusion across heterogeneous sources.
8. **Cost is consented.** No cloud or expensive local analysis without an explicit policy decision and budget.
9. **Authorization follows occurrences.** Access to a shared asset is granted only through an authorized document/source occurrence.
10. **Fail closed.** Unknown provenance, corrupt bytes, stale derivations, interrupted publication, and incomplete structured execution never masquerade as success.
11. **Local-first remains first-class.** Every capability can be absent; capability negotiation and typed status replace hidden fallback.
12. **Reproducibility is evidence.** Provider/model/revision/configuration/policy identities accompany every derived output.

---

## 8. Retrieval architecture

### 8.1 Typed planning

**[PROPOSED]** Introduce `AdvancedRetrievalPlanV1`, separate from frozen `RetrievalPlan`, with:

```text
request_id
normalized_query
query_language/script
intent: exact | ranked | structured | exhaustive | positional |
        cross_document | aggregate | multimodal | document_expand | asset
execution_family
hard_scope: notebook/source/document/version constraints
operations[]
bounds
required_capabilities
policy_versions
```

An `AdvancedQueryPlanner` performs:

1. transport/schema validation and hard scope construction;
2. deterministic parsing of explicit IDs, ranges, field predicates, quoted literals, filenames/titles, code symbols, and count/list operators;
3. conservative LLM classification only for ambiguous natural language;
4. capability validation;
5. emission of one typed plan—never direct retrieval.

Client-declared mode may narrow behavior but may not relax authorization or safety bounds. Low-confidence classification defaults to bounded ranked retrieval with `completeness=bounded`, not aggregation or exhaustive claims.

### 8.2 Exact retrieval

**[PROPOSED]** `ExactRetrievalInterfaceV1` searches normalized but non-semantic projections for:

- document/version/source/asset UUIDs and content hashes;
- canonical titles and explicitly retained source filenames;
- quoted text and exact normalized text spans;
- code symbols from a derived symbol index;
- dates, names, roll numbers, and structured values only where a typed field/index exists.

Exact results retain match field, normalization policy, exact offsets, version identity, and occurrence count. Literal values are parameterized; FTS terms remain escaped. “Exact” never means case/diacritic normalization unless the response names the applied normalization policy.

### 8.3 Ranked semantic retrieval

**[CODE]** Existing V1 dense/sparse/hybrid retrieval remains the text-chunk path. Phase 8.5.6 adds an adapter that wraps authorized V1 sparse output as typed `AdvancedRetrievalCandidate` records without changing V1 objects. It retains title, source/document/version/chunk identity, positional metadata, raw retrieval paths, parent-promotion provenance, fused rank, and deterministic final rank.

### 8.4 Structured retrieval

**[CODE]** WP-08 composes the versioned `StructuredQueryV1` intermediate
representation, active exact-version projection catalog, strict public compiler,
bounded execution, signed continuation, row/cell provenance, and shared HTTP/MCP
adapters. No arbitrary SQL crosses the public boundary, and a missing or stale
generation is unavailable rather than an empty complete dataset:

```text
dataset_ref(document_id, version_id, table_or_sheet_id)
select_fields[]
predicates[]        # typed operators and literals
group_by[]
aggregates[]
order_by[]
row_limit
```

Parsers emit a derived table catalog: table identity, headers, row ordinals, cell values/types/formulas, sheet/page/block provenance. A `StructuredRetrievalInterfaceV1` compiles only allowlisted IR operations to parameterized SQLite. It returns typed rows plus exact cell provenance. Unsupported ambiguity yields a validation request/error, not invented columns.

### 8.5 Exhaustive retrieval

**[PROPOSED]** Exhaustive retrieval is cursor-based scanning over an explicitly defined universe, never a large `top_k`:

```text
EvidencePage<T>:
  items
  next_cursor
  completeness
  searched_scope
  matched_so_far
  total_matches?       # only when cheaply/provably known
  applied_limits
  termination_reason?
  snapshot/index_generation
```

Ordering is deterministic by `(document_id, version_id, occurrence position, candidate_id)`, or by an explicitly requested stable field. A cursor binds query fingerprint, scope, index generation, last key, and expiry. Maximum page size is 100; maximum scan time, documents, rows, occurrences, and bytes are policy-controlled. `complete` is emitted only at terminal cursor on an unchanged snapshot.

### 8.6 Positional retrieval

**[PROPOSED]** `PositionalRetrievalInterfaceV1` resolves direct physical positions:

- page/slide/sheet and optional region;
- section/heading path;
- block ordinal or chunk range;
- paragraph immediately before/after a matched block;
- assets on a page, slide, sheet, or block.

It reads exact-version parsed IR and derived occurrence projections, preserves canonical order, and never invokes semantic ranking unless the anchor phrase itself requires discovery. “After X” is two steps: exact/ranked anchor selection, then deterministic adjacency in the same exact version; ambiguous anchors return alternatives.

### 8.7 Cross-document retrieval

**[PROPOSED]** Cross-document plans name or resolve a bounded target document set first, then retrieve per-document evidence under quotas. Results preserve per-document partitions before optional global fusion. This complements ADR-0048 diversity without changing ADR-0048’s existing behavior. Phase 11 graph traversal remains separate.

### 8.8 Aggregation

**[CODE]** Aggregation belongs to the structured execution layer, with the planner selecting it. It does not belong inside vector search or Final-QA synthesis. Phase 8.5.7 executes count, distinct count, sum, average, minimum, and maximum over typed exact-version table projections. Results carry candidate/row universes, typed missing/invalid states, inherited completeness, deterministic ordering, and exact source-cell provenance. No LLM computes authoritative aggregates.

### 8.9 Completeness semantics

**[PROPOSED]** Every advanced result uses:

| State | Meaning |
|---|---|
| `complete` | entire declared universe evaluated against a stable snapshot |
| `partial` | some partitions/providers failed; successful subset identified |
| `truncated` | matching sequence cut by a hard response/resource cap; continuation may exist |
| `bounded` | top-k or policy-bounded search; no completeness claim |
| `unknown` | backend cannot determine coverage or snapshot stability |

Existing V1 ranked retrieval maps to `bounded`. Fail-fast Phase-6 behavior remains unchanged; `partial` is available only to new contracts that explicitly enumerate failed partitions.

### 8.10 Candidate and provenance contract

**[PROPOSED]** A new immutable `EvidenceCandidateV1` carries:

```text
candidate_id
kind: chunk | asset_occurrence | ocr_span | vision_description |
      structured_row | structured_cell | metadata_record
document_id, version_id, source_ids, notebook_ids
physical_location
authoritative_ref
derived_representation_ref?
display_text?
raw_evidence[]       # provider, rank, raw score, match fields
fusion_rank/score?
completeness
```

Candidates are wrappers around canonical records; they do not replace `Chunk`, `Asset`, or `ScoredChunk`. Every conversion validates identity equality and copies all runtime provenance explicitly. Candidate projections and parent/occurrence promotion require the same regression discipline introduced after ADR-0057.

---

## 9. Multimodal architecture

**[PROPOSED]** The multimodal flow is:

```text
original document bytes
  -> pure format parser
  -> text/table blocks + transient asset occurrences
  -> content-addressed Asset bytes
  -> canonical ParsedDocument/ImageBlock
  -> derived asset-occurrence/table projections
  -> optional processing jobs
       -> OCR
       -> description/entities/chart interpretation
       -> visual embedding
       -> translation/language-normalized text
  -> independent derived indexes
  -> typed multimodal retrieval/fusion
  -> text and/or binary context bundle
  -> V2 answer/citation/snapshot boundary
```

Original bytes and parsed source blocks remain authoritative. Each derived representation can be deleted/rebuilt independently without changing document, version, chunk, source, or asset identity.

---

## 10. Asset model

### 10.1 Recommendation

**[ADR]** Do not create a second canonical binary model: reuse frozen `Asset` for immutable content-addressed bytes.

**[PROPOSED]** Add three records around it:

1. **`DocumentBinaryReference`** — binds an exact document version to its original uploaded bytes stored as an `Asset`, with role `original_document`.
2. **`AssetOccurrence`** — queryable exact-version occurrence derived from authoritative `ImageBlock`/parser structure:
   `occurrence_id`, `asset_id`, `document_id`, `version_id`, block ordinal, page/slide/sheet, bounding box/anchor, role, relationship/parent, source parser, and extraction policy version.
3. **`AssetDerivation`** — immutable output descriptor for OCR, description, entities, translation, or embedding: derivation ID, asset/occurrence scope, operation, provider/model/revision/config hash/prompt hash, input hashes, output reference, confidence summary, language/script, timestamps, and status.

`AssetOccurrence` should be canonicalized deterministically from exact source structure, but its SQLite catalog is a rebuildable projection of parsed IR. The same `asset_id` may have many occurrences. An analysis may be content-level (safe to reuse for identical pixels) or occurrence-level (required when page context, caption, crop, rotation, or surrounding text affects output); cache identity states which.

### 10.2 Invariants

- Asset bytes never change for an `asset_id`.
- Occurrence IDs include exact version and location identity.
- A derived record never overwrites alt text or original bytes.
- Width/height/byte size are verified from decoded bytes, not trusted container metadata.
- MIME is sniffed and compared with declared MIME.
- Deleting one source association does not delete shared assets.
- Asset garbage collection is reachability-based, separately authorized, and never part of parser rollback.

---

## 11. Image extraction

### 11.1 Parser responsibilities

**[PROPOSED]** Pure parsers continue to return raw blocks and transient bytes. Extend `TransientAsset` only through a versioned successor transport record (or parser metadata namespace) carrying width/height, byte size, occurrence role, rotation, crop, page/slide/sheet, bounding box/anchor, relationship ID, and parser-local parent correlation. Permanent IDs remain storage-owned.

### 11.2 Format plan

| Format | Phase 8.5 extraction plan |
|---|---|
| PDF | retain current embedded image extraction; add page-render assets only for OCR/visual workflows, distinguish embedded object from rendered page, preserve matrix/rotation/crop |
| DOCX | traverse document body/run/drawing order and relationships; distinguish inline vs anchored drawing; retain relationship and approximate anchor; do not claim page number unless layout engine supplies it |
| PPTX | parse slide relationships/drawing tree; extract raster/SVG media, charts and diagram previews; retain slide number, shape order, transform/bounding box, relationship and alt/title text |
| XLSX | parse drawing anchors, images and charts per worksheet; retain sheet, cell anchor/range, pixel dimensions and chart source reference; do not evaluate external links |
| HTML | keep data-URI support; optionally resolve packaged/local resources in an orchestration acquisition stage under an allowed root; pure parser never performs network fetch |
| Markdown | same as HTML; resolve uploaded bundle paths outside the parser with traversal protection and content hashing |
| PNG/JPEG/WebP/GIF/TIFF/BMP/SVG | add a standalone-image parser producing one authoritative image occurrence; animated formats retain animation metadata and policy-selected frame handling |

Unsupported embedded objects are recorded as typed omissions with reason, not silently ignored. Extraction limits include container entries, total decompressed bytes, per-asset bytes/pixels, nesting depth, page/slide count, and decode time.

### 11.3 Original document retention

**[PROPOSED]** New ingestion persists uploaded bytes through content-addressed asset storage before parsing and writes `DocumentBinaryReference` only after the document/version claim succeeds. This enables reproducible reparse and asset backfill. It does not change document content hash.

Existing v0.25.0 documents remain valid. If exact original bytes are unavailable, their asset status is `source_bytes_unavailable`; they are not reparsed from old IR. A user may re-supply bytes, and Mnemo accepts them only when SHA-256 equals the exact `DocumentVersion.content_hash`.

---

## 12. OCR

### 12.1 Scanned-PDF detection

**[PROPOSED]** Use a versioned page-level detector, not a filename or whole-document guess. Initial policy for calibration:

- usable normalized extracted text below 32 characters; and
- raster coverage at least 50% of page area, or one dominant full-page image; and
- no reliable vector text layer.

A document is `scan_likely` when at least 80% of non-empty pages meet the rule, and `mixed` otherwise when at least one does. These thresholds are proposed defaults requiring corpus calibration and an ADR; detector evidence is persisted so the decision is reproducible.

Status must distinguish `digital`, `mixed`, `scan_likely`, `detection_failed`, and `unknown`. Empty extraction from a scan-likely page produces a visible `ocr_available`/`ocr_required` status, never an ordinary empty document.

### 12.2 Provider contract

**[PROPOSED]** `OCRProviderV1` accepts immutable image bytes/reference plus bounded options and returns:

```text
OCRResult:
  asset/occurrence identity
  ordered pages/regions/spans
  exact recognized text
  language/script candidates and confidence
  word/line bounding boxes and confidence where supported
  provider/model/revision/configuration
  preprocessing identity
  input/output hashes
  warnings/omissions
```

OCR is independent from parsing and may operate per page or selected image. It supports local/cloud providers through registry lifecycle hooks. Preprocessing (deskew, rotate, crop, contrast) is a derived pipeline whose configuration participates in cache identity. OCR output is immutable derived data and indexed separately; it never replaces `ImageBlock` or source text.

### 12.3 Failure semantics

Per-asset outcomes are `pending`, `running`, `succeeded`, `partial`, `failed`, `cancelled`, or `unsupported`. Partial results enumerate failed pages/regions. Provider absence is typed and does not fail base ingestion. Retries are bounded by job policy, not provider-hidden loops. Cancellation stops scheduling new pages and preserves only complete immutable page outputs.

---

## 13. Vision-language analysis

**[CODE]** `VisionProviderV1` accepts an authorized original image occurrence,
a bounded operation profile, and a strict structured result schema. The
provider-neutral contract is capability checked and separately consented:

- concise description;
- visual entities/objects;
- chart/table/diagram interpretation;
- deep visual comparison/reasoning.

Every `VisionResult` records provider, model, revision, profile and prompt hash,
preprocessing, exact occurrence/version/asset provenance, schema generation,
timestamp, and optional confidence/language/geometry. Raw provider
chain-of-thought is neither requested nor persisted.

Source alt text, OCR text, and generated description remain distinct fields. Generated text is tagged `untrusted_derived_evidence`; retrieval and prompts treat it as evidence, never instructions. VLM outputs cannot authorize actions, expand scope, or override system prompts.

---

## 14. Visual embeddings

### 14.1 Provider contracts

**[CODE]** The text-only `EmbeddingProviderV1` remains frozen. Phase 8.5.5 adds
an independent contract (the ADR-name alias is also exported):

```text
VisualEmbeddingProviderV1.embed_image(asset) -> validated vector + provenance
ImageEmbeddingProviderV1 = VisualEmbeddingProviderV1
```

Capabilities declare modalities, fixed dimensions, shared-space ID, preprocessing, maximum pixels/bytes/batch, multilingual text support, normalized-output semantics, and provider lifecycle. Model identity includes revision and preprocessing, not only display name.

### 14.2 Recommended index topology

**[CODE]** Phase 8.5.5 establishes independent image-vector generations in
SQLite and preserves the **hybrid separate indexes** contract:

- retain the current text-chunk collection;
- create image collections per image embedding space/model/index generation;
- optionally create one shared multimodal collection only for providers that explicitly guarantee text/image comparability;
- store OCR/descriptions/translations in text-derived indexes, not the canonical chunk collection;
- fuse ranks across collections rather than comparing raw vector scores.

This avoids forcing unrelated dimensions/spaces into one Qdrant collection, permits provider replacement and local/cloud mixing, and preserves current deployments. A shared space can improve text-to-image recall but is a provider capability, not a system assumption.

Vector payloads include asset occurrence, exact version, authorized notebook/source memberships, derivation identity, model/index generation, page/slide/sheet, and content hash. The canonical SQLite catalog remains authoritative; Qdrant remains rebuildable and optional.

---

## 15. Multimodal retrieval

### 15.1 Retrieval sources

**[CODE]** A multimodal plan may invoke:

- canonical text sparse/dense retrieval;
- OCR sparse/dense retrieval;
- description sparse/dense retrieval;
- visual nearest-neighbor retrieval;
- exact asset/title/MIME/location metadata retrieval;
- structured chart/table catalog retrieval.

Each invocation returns typed source-local evidence. Duplicate candidates merge only when their authoritative occurrence identity matches; related text and image occurrences may be linked but not deduplicated into one identity.

### 15.2 Fusion and reranking

Use bounded RRF across incomparable ranked streams, retaining every raw rank/score/provider. Modality-aware reranking receives an explicit representation:

- text candidates: canonical title + canonical chunk text under ADR-0057;
- OCR/description: derived text plus derivation label and original occurrence metadata;
- image candidates: original pixels or provider-supported image features plus title/location;
- structured candidates: schema/headers plus selected row/cell values.

No text-only cross-encoder is asked to score raw images. The additive
`MultimodalCandidateRerankerV1` receives typed candidates. A missing modality
reranker yields the declared RRF fallback; registered failure is surfaced, not
swallowed.

### 15.3 Diversity and context

Diversity operates after relevance and can constrain document, modality, page/slide, and near-duplicate asset groups. It must not erase exact-title, exact-field, or exact-position evidence. The selected result retains omitted candidates and reasons.

Existing `ContextBuildResult` remains text-only. `MultimodalContextBuildResultV1`
contains bounded rendered items and ordered opaque asset references; original
bytes are not embedded in prompts. Token, byte, pixel, and image-count budgets
are accounted separately.

### 15.4 Citations and Final QA

ADR-0045 citations point to chunks and cannot truthfully represent image-only evidence. **[CODE]** Multimodal persisted QA uses additive `EvidenceCitationV2` and `FinalQAV2` contracts that can cite:

- exact chunk span;
- asset occurrence and original bytes;
- OCR/vision derivation plus original occurrence;
- structured cell/range.

The original asset remains the primary evidence; derived outputs are included in the citation snapshot. Marker grammar may remain `[source:N]`, but resolution maps to a typed evidence item. V2 immutable execution snapshots must serialize the entire multimodal context and derivation provenance; V1 replay remains byte-for-byte unaffected.

---

## 16. MCP context expansion

### 16.1 Recommended tools

**[PROPOSED]** Add four read-only tools because they expose distinct bounded resources:

| Tool | Purpose |
|---|---|
| `get_document` | bounded exact-version document/page/slide/section expansion |
| `get_document_chunk` | one chunk or bounded contiguous chunk range with provenance |
| `get_asset` | original authorized asset bytes and occurrence metadata |
| `get_image_analysis` | selected immutable OCR/description/entity derivations |

Add `search_multimodal` only after the typed candidate API is stable and clients need direct multimodal discovery. Avoid separate `search_images` if it would duplicate `search_multimodal(modalities=[image])`.

### 16.2 MCP resources and content

Expose immutable resource URIs such as:

```text
mnemo://documents/{document_id}/versions/{version_id}
mnemo://chunks/{chunk_id}
mnemo://assets/{asset_id}?occurrence_id=...
mnemo://asset-analyses/{derivation_id}
```

`get_asset` returns MCP `ImageContent` only for a complete recognizable supported raster image. A truncated or malformed image is an opaque `EmbeddedResource` range with original MIME, total length, hash, cursor, and exact occurrence provenance; clients never receive a byte prefix mislabeled as a complete image. Binary content uses protocol-native base64 only at the transport boundary. The server’s resource listing may remain empty unless authorized pagination is defined; direct resource reads still validate notebook scope.

### 16.3 Multiple images

Requests accept ordered occurrence IDs or a positional selector (“all images on slide 3”), with defaults `max_assets=3`, hard maximum 10, per-asset 10 MiB, total 25 MiB, and total decoded-pixel policy. Limits are proposed defaults requiring ADR acceptance. Ordering follows explicit request order, then physical occurrence order. Partial delivery identifies every omitted/failed asset; it never substitutes a description for unavailable original bytes.

---

## 17. Full-document retrieval

**[PROPOSED]** `DocumentExpansionRequestV1` requires document and exact version (or resolves current version once and returns it), plus one selector:

- full logical document;
- page/slide/sheet range;
- heading/section;
- block/chunk range;
- asset-inclusive representation.

Limits are multi-dimensional:

| Dimension | Default | Proposed hard ceiling |
|---|---:|---:|
| text tokens | 16,000 | 100,000 |
| serialized bytes | 2 MiB | 10 MiB |
| pages/slides | 25 | 100 |
| chunks | 100 | 500 |
| assets | 3 | 10 |
| total asset bytes | 10 MiB | 25 MiB |

The lowest reached limit terminates the page with `truncated` and a continuation cursor. A “full” request means scan the full declared exact version across pages, not return it in one payload. Cursors bind exact version, selector, representation options, next ordinal, query fingerprint, and index/IR schema version. No cursor grants authority.

Response content is typed blocks rather than one flattened string. Each item includes original block ordinal/type/page/bbox/language, chunk IDs overlapping it, asset occurrence references, and derivation availability. Binary inclusion is opt-in.

### 17.1 Phase 9 UI contract

**[PROPOSED]** Phase 8.5 freezes backend DTOs and interaction states that the planned Phase 9 UI consumes. A source detail view shows an asset summary such as “23 images detected” and provides:

- a paginated, virtualized thumbnail inventory in physical occurrence order;
- filters for page/slide/sheet, MIME, dimensions, role, language, and processing state;
- separate OCR, description, entity-analysis, and visual-embedding states;
- original byte/hash/MIME/dimensions/location provenance;
- local/cloud/hybrid provider and model selection constrained by capabilities;
- a preflight cost/compute/cache manifest;
- analyze selected/all, cancel, resume, and retry controls;
- progress by assets/pages plus typed partial failures;
- a detail viewer that displays the original asset alongside authored alt text, OCR spans/boxes, generated description, confidence, provider/model/revision, and derivation timestamp.

The UI must visually distinguish **original**, **authored**, and **generated** information. It never rewrites the original preview with OCR/VLM output, never assumes a failed analysis makes the asset unavailable, and never performs provider calls directly. Asset bytes and analysis records come only through authorized Layer-2 APIs. Active formats are sandboxed/rasterized or offered as downloads according to server policy. Accessibility requires keyboard navigation, meaningful authored/generated alt-text labeling, zoom/pan, high-contrast OCR overlays, and non-color-only state indicators.

---

## 18. Multilingual architecture

### 18.1 Ingestion and language identity

**[CODE]** Current block-level `langdetect` is deterministic via a fixed seed, but document-level parser language is commonly `en`, and there is no script/confidence provenance.

**[CODE]** Derived `LanguageObservation` records provide:

```text
scope(document/block/ocr-span/derived-text)
BCP-47 language candidates
ISO 15924 script candidates
confidence
detector/model/revision/configuration
input hash
mixed-language spans
```

Do not mutate source text. Short/ambiguous content remains `undetermined`. Code, identifiers, and numbers can be `zxx`/language-neutral. OCR selects language packs from script detection plus user hints, never filename inference.

### 18.2 Sparse retrieval

**[CODE]** The existing FTS index remains unchanged. Phase 8.5.9 exposes Unicode-normalized and optional Devanagari-to-Latin derived sparse representations behind language-path source contracts; selected paths are fused by bounded RRF and retain explicit provenance. Deployment-specific analyzer generations use the additive generation lifecycle. Transliteration is derived and never shown as source text.

### 18.3 Dense retrieval and reranking

**[CODE]** Provider-neutral multilingual embedding/reranker profiles expose named vector-space, dimension, metric, normalization, revision, language/script coverage, and capability state. **[PROPOSED]** Benchmark, rather than immediately select, multilingual model families. Candidate embedding families include BGE-M3, multilingual E5, Jina multilingual embeddings, and GTE multilingual; candidate rerankers include multilingual BGE and multilingual cross-encoders. The evaluation must pin revision, license, dimension, context length, preprocessing, quantization, RAM/VRAM, CPU latency, and supported languages.

The current 768-dimensional index is not silently reinterpreted. A new model uses a new embedding-space ID and collection generation. During migration, old and new text indexes may run side-by-side and fuse ranks. Fallback to current English retrieval is disclosed as capability degradation, not multilingual success.

### 18.4 Cross-language retrieval

**[CODE]** Capability-aware cross-language plans can combine:

1. multilingual dense retrieval in a certified shared language space;
2. optional query translation/transliteration streams with independent evidence;
3. original-language sparse matches;
4. multilingual reranking over original query/candidate plus optional derived translation.

Every result states which path produced it. Translation cannot replace the original candidate text or title.

### 18.5 Generation and answer language

**[CODE]** Answer policy defaults to the user query language when the configured synthesizer profile supports it; otherwise it returns a typed capability failure or an explicitly allowed fallback language. Quotations remain in original language. Optional translations are labeled. `[source:N]` markers remain ASCII and unchanged across scripts.

### 18.6 Evaluation

Build balanced same-language and cross-language sets for Hindi, Marathi, and English first, including Devanagari/Latin transliteration, mixed-script titles, exact identifiers, OCR, long prose, and negative controls. Report Recall@k, MRR/nDCG, reranker pairwise accuracy, document attribution, answer grounding, citation resolution, language fidelity, and latency per direction (hi→en, en→mr, mr→hi, and same-language baselines).

---

## 19. Cost and compute governance

**[PROPOSED]** Introduce a unified `ProcessingManifest` before expensive work:

```text
operation(s)
asset/page counts and byte/pixel estimates
provider mode: local | cloud | hybrid
provider/model/revision
estimated monetary range and currency
estimated CPU/GPU time and memory class
cache hits/misses/unknown
maximum authorized spend/time/resources
data-egress classification
consent identity and expiry
```

Operations—OCR, description, visual embedding, entity analysis, deep reasoning, translation, multilingual embedding—are independently selectable. “Analyze all” resolves to a manifest and requires confirmation when cloud egress or configured thresholds are crossed. Estimates are explicitly non-binding ranges; hard budgets are enforced before each dispatch.

Phase 8.5 requires a durable `ProcessingJobStoreV1` and worker contract because synchronous HTTP ingestion is unsuitable for VLM/OCR batches. This deliberately advances a narrow job foundation before Phase 10; Phase 10 should consume/extend the same contract rather than build an incompatible SurrealDB-only queue. Jobs support claim lease, heartbeat, progress, cancellation, retry policy, resume cursor, terminal failure, and idempotent operation keys.

Cloud providers receive only authorized assets/regions. Secrets remain in provider configuration and never enter fingerprints, manifests returned to clients, cache keys, logs, or derivation payloads.

---

## 20. Storage and migration

### 20.1 Additive stores

**[PROPOSED]** Do not change `StorageInterfaceV1`. Add composition-owned facilities:

- `AssetCatalogStoreV1` for document binary refs and occurrence projections;
- `DerivedRepresentationStoreV1` for immutable derivations and statuses;
- `StructuredContentStoreV1` for table/symbol/position projections;
- `AdvancedRetrievalStoreV1` for cursor scans and completeness snapshots;
- `ProcessingJobStoreV1` for durable work;
- modality-specific vector index adapters.

SQLite stores authoritative association/status rows and derived searchable text. Filesystem stores original and derived binary payloads content-addressably. Qdrant stores rebuildable vectors. No large binary is placed in SQLite JSON.

### 20.2 Proposed schema families

```text
document_binary_references
asset_occurrences
asset_derivations
asset_derivation_outputs
structured_datasets / structured_fields / structured_rows / structured_cells
language_observations
processing_jobs / processing_attempts
advanced_index_generations
```

Foreign keys target exact documents/versions/assets where safe. Content-addressed assets shared across versions are not cascade-deleted by one occurrence. Derived outputs use write-once `(input_identity, operation, provider, model_revision, config_hash, schema_version)` uniqueness. Mutable job headers point to immutable attempt/output records.

### 20.3 Cache identity

At minimum:

```text
domain_separator + schema_version + asset_hash/crop_hash + occurrence_context_hash?
+ operation + provider + model + model_revision + configuration_hash
+ prompt/preprocessing/policy hash + output_schema
```

OCR/VLM/translation caches use immutable result payloads. Visual-vector caches include dimension, normalization, preprocessing, and shared-space ID. Model/config changes invalidate only matching derived outputs. A cache hit is verified against input/output hashes before use.

### 20.4 v0.25.0 migration

1. Transactionally create additive tables/index-generation records; rollback leaves v0.25.0 unchanged.
2. Build `asset_occurrences` from existing parsed IR without re-ingestion.
3. Mark missing original-document bytes explicitly.
4. Preserve all existing chunks, FTS/title rows, embeddings, Qdrant points, citations, and Final-QA snapshots.
5. For versions with exact source bytes later re-supplied, verify content hash and run opt-in asset backfill; do not change the version identity.
6. Build derived indexes lazily per capability/job. Never block normal text retrieval on optional analysis.
7. Maintain index generation aliases for atomic cutover and rollback.
8. Feature flags expose extraction, OCR, VLM, visual vectors, advanced retrieval, and multilingual paths independently.

Rollback disables new capabilities and reselects the previous index generation. Canonical/derived new records remain harmless and can be garbage-collected later; no downgrade rewrites frozen records.

---

## 21. Security

### 21.1 Binary and container safety

**[PROPOSED]** Enforce MIME sniffing, extension/MIME consistency policy, byte/pixel/frame/page limits, decompressed-size and compression-ratio limits, archive entry/path validation, recursion limits, parser/decode timeouts in isolated workers, and memory/CPU quotas. Reject external entity resolution, macros, OLE execution, external workbook links, SVG scripts/external loads, PDF embedded-file execution, and metadata-triggered network access.

Image decoders and document parsers run with no network, a read-only input, controlled temp directory, restricted filesystem, and process isolation for high-risk formats. Decompression bombs are rejected before full decode where possible.

### 21.2 Prompt injection and derived data

OCR text, image text, QR content, VLM descriptions, translations, alt text, and document metadata are untrusted evidence. They cannot become system/user instructions, tool calls, provider configuration, URLs to fetch, or retrieval scope changes. Prompts delimit them as data. VLM providers have no tools. Generated descriptions are never promoted to trusted metadata.

### 21.3 Authorization and disclosure

WP-14 operationalizes one server-owned principal boundary. HTTP authentication
claims and the server-created MCP principal become `PrincipalContextV1`; public
DTO fields cannot override them. `DocumentScopeResolverV1` then resolves an
explicit or unique authorized notebook/source/document/version association.
Zero and cross-scope associations use the same non-enumerating failure, while
multiple associations require an explicit notebook. The resolver is additive:
`StorageInterfaceV1` retains its frozen pre-ADR-0072 method set and concrete
stores may keep source-association helpers for compatibility.

An asset UUID alone is insufficient authorization. Every asset read resolves at least one occurrence connected to an authenticated principal’s authorized notebook/source/document version. Shared content-addressed assets remain physically deduplicated but logically isolated. Multi-asset requests validate every occurrence independently and do not leak which unauthorized IDs exist.

Responses set safe MIME/content-disposition, disable sniffing, and sanitize filenames. SVG and active formats are downloaded or rasterized by policy rather than rendered inline. Range requests and resource URLs are short-lived and scope-bound. Logs never contain bytes, OCR text, descriptions, prompts, tokens, or secrets by default.

### 21.4 Structured query safety

Only a typed allowlisted query IR is compiled to parameterized SQL. No raw SQL, column expression, filesystem path, regex with uncontrolled complexity, or arbitrary function enters from clients. Scan/aggregation budgets and cancellation are enforced in the database operation.

---

## 22. Observability

**[PROPOSED]** Emit structured, content-free events and metrics:

- assets detected/extracted/omitted by format and reason;
- original bytes retained and occurrence projection lag;
- scanned-page detector outcomes;
- OCR/VLM/translation/image-embedding latency, queue delay, retries, failures, cancellations;
- cache hits/misses/corruption/invalidation by operation/model;
- processed pixels/pages/assets and local CPU/GPU time;
- estimated and actual provider cost where available;
- retrieval intent/execution family, invocation counts, candidate counts, completeness, truncation reason;
- per-modality retrieval/fusion/rerank latency and fallback;
- language/script/direction, without source text;
- MCP document/asset requests, bytes returned, omissions, auth failures;
- stale/missing derivations and index-generation health.

Trace IDs propagate ingestion → job → derivation → index → retrieval → context → Final QA while IDs are access-controlled and no evidence text is logged. Cardinality is bounded by using provider/model families and reason codes rather than asset/chunk IDs as metric labels.

---

## 23. Performance

### 23.1 Workload separation

Base text ingestion stays fast. Original-byte retention and cheap image extraction may run inline under limits; OCR, VLM, translations, and image embeddings run in durable background jobs. Page rendering is demand-driven and cached. Operations batch by provider/model and use bounded concurrency.

### 23.2 Budgets

Benchmark independently:

- parse/extract documents per second and peak memory;
- pages/assets/pixels per second for OCR/VLM;
- embedding items/pixels per second and cache reuse;
- SQLite projection growth and query latency;
- Qdrant collection size/build/search latency per modality;
- fusion/reranking latency by candidate count;
- MCP serialization/base64 overhead and payload limits;
- CPU-only and representative local-GPU profiles.

No architecture target is certified until measured. The existing Phase-13 20M-chunk target remains future work; Phase 8.5 adds representative asset ratios and multilingual/multimodal queries to that benchmark plan.

### 23.3 Resource controls

Workers use per-operation semaphores, batch ceilings, leases, cancellation checks between units, bounded temp storage, and backpressure. Interactive exact/positional retrieval has priority over enrichment. Deep visual reasoning has the lowest default priority. Memory estimates include decoded pixels, not only compressed bytes.

---

## 24. Testing

### 24.1 Retrieval certification

- exact literals/IDs/titles/symbols/dates with normalization negatives;
- ranked semantic regression against the v0.25.0 corpus;
- structured rows/cells, types, formulas, predicates, and aggregates;
- exhaustive pagination, cursor replay, snapshot change, termination, and completeness states;
- positional page/slide/sheet/adjacency and ambiguous anchors;
- cross-document quotas and attribution;
- multimodal fusion, missing modalities, score-domain isolation, provenance preservation, diversity, and deterministic ties;
- content-only queries prove title/asset logic does not dominate unrelated evidence.

### 24.2 Ingestion and assets

Fixtures cover PDF embedded images and scanned pages; DOCX inline/anchored images; PPTX pictures/charts/diagrams; XLSX anchors/charts; HTML/Markdown data and packaged-local references; standalone PNG/JPEG/WebP/GIF/TIFF/SVG; duplicate assets; repeated occurrences; corrupt media; and unsupported objects. Assertions cover original bytes/hash, occurrence order/location, dimensions/MIME, exact version, omitted-item reports, and no meaningful text regression.

### 24.3 Derived analysis

Test multilingual OCR text/boxes/confidence, partial pages, preprocessing identity, VLM schema and prompt provenance, visual embeddings/dimensions/shared-space declaration, cache reuse, model/config invalidation, provider failures, retries, timeouts, cancellation, crash/resume, budgets, and zero optional work without consent.

### 24.4 Provenance and Final QA

Prove:

```text
original bytes -> Asset -> AssetOccurrence -> DocumentVersion -> Source/Notebook
             -> Derivation -> RetrievalEvidence -> ContextItem
             -> EvidenceCitationV2 -> immutable execution snapshot/replay
```

Replay performs zero provider calls and returns exact typed provenance. Failed compliance publishes nothing. V1 Final-QA snapshots remain decodable and unchanged.

### 24.5 MCP/HTTP/UI

Test bounds/cursors/ranges, MIME/binary content, multiple images and order, malformed/unknown/unauthorized IDs, cross-notebook isolation, active-content handling, payload truncation, disconnect/cancellation, and client compatibility. UI tests cover inventory/status, consent manifest, progress/cancel/retry, original image rendering, provenance, and inaccessible assets.

### 24.6 Multilingual evaluation

Use human-reviewed original-language judgments, cross-language directions, transliteration, mixed scripts, OCR, exact identifiers, no-answer controls, and citation preservation. Publish per-language metrics rather than one aggregate that hides regressions.

### 24.7 Quality baseline

All existing Phase 0–8 tests remain green; coverage stays at least 90%; Ruff, strict mypy, package/frontend/Docker builds, migration rollback, security corpus, live HTTP/MCP transports, and reproducible offline fixtures are mandatory.

---

## 25. ADR package

The accepted successor package is independently reviewable and preserves
historical decisions:

| ADR | Decision |
|---|---|
| ADR-0058 | advanced retrieval completeness and result sets |
| ADR-0059 | original document assets and occurrence provenance |
| ADR-0060 | durable processing jobs and cost governance |
| ADR-0061 | OCR and derived text representations |
| ADR-0062 | vision analysis and visual embedding spaces |
| ADR-0063 | structured retrieval and safe aggregation |
| ADR-0064 | multimodal evidence, context, and Final QA V2 |
| ADR-0065 | bounded document expansion and resource delivery |
| ADR-0066 | MCP document and asset capability expansion |
| ADR-0067 | multilingual retrieval and derived translation |
| ADR-0068 | asset authorization and provider trust boundaries |
| ADR-0069 | Phase 8.5 HTTP API and UI capability contract |
| ADR-0070 | evaluation and certification governance |
| ADR-0071 | additive migration and index-generation lifecycle |

The formal contradiction review is recorded in
`docs/reports/architecture/PHASE_8_5_ARCHITECTURAL_CONTRADICTION_AUDIT.md`. Historical
ADRs remain unchanged. The next available ADR number is ADR-0072.

---

## 26. Frozen-phase compatibility

### 26.1 Must not change

- `Document`, `DocumentVersion`, `Source`, `Chunk`, `Asset`, `ImageBlock`, and existing UUID/hash identity contracts.
- Canonical `Chunk.text`, source spans, parent/sibling structure, and exact-version filters.
- Raw sparse/dense score provenance, RRF evidence, title-aware reranking, and V1 bounded retrieval behavior.
- ADR-0043 text context, ADR-0044 first-pass generation, case-sensitive `[source:N]`, ADR-0045 citation snapshots, ADR-0054 one corrective retry.
- ADR-0055 persisted-vs-preview distinction and ADR-0056 immutable replay/conflict/crash safety.
- Existing six MCP tools and their read-only behavior.
- Storage V1 behavior, Qdrant optionality, local sparse-only honesty, and Golden Corpus correctness.

### 26.2 Safe extension points

- existing generic `Asset`, `ImageBlock`, `TransientAsset`, blob-store methods, metadata namespaces, parser capabilities, registry and startup hooks;
- additive interfaces/facilities composed by `KnowledgeEngine`;
- new derived SQLite projections and Qdrant collections;
- plugin capability families with independent interface versions;
- new REST/MCP tools/DTOs/resources under explicit successor ADRs;
- Phase 9 UI plans before implementation;
- Phase 10 job design, provided the roadmap is reconciled prospectively.

### 26.3 Compatibility mechanism

V1 text retrieval/Final QA remains default. Phase 8.5 capabilities negotiate explicitly and can be disabled independently. V2 results wrap or reference V1 provenance rather than reinterpret it. Old snapshots, citations, chunks, FTS, embeddings, and clients require no rewrite.

---

## 27. Future-phase compatibility

- **Phase 9 UI:** consume stable asset inventory, job, provenance, and bounded binary APIs; avoid inventing client-only processing state.
- **Phase 10 jobs/enrichment:** reuse `ProcessingJobStoreV1`, derivation/cache records, and progress events. Roadmap’s SurrealDB-only queue assumption should become one provider option, not the contract.
- **Phase 10 summaries/session memory:** may consume OCR/derived text only when explicitly selected and must cite original occurrence plus derivation.
- **Phase 11 graph reasoning:** visual/OCR entities can feed graph extraction as untrusted derived evidence with occurrence provenance. Advanced cross-document partitions provide inputs without preempting graph traversal.
- **Phase 12 plugins:** OCR, advanced layout, VLM, visual embedding, and provider adapters fit versioned plugin families; plugin SDK compatibility tests include modality and resource constraints.
- **Phase 13 hardening:** add multimodal/multilingual throughput, decompression defenses, job observability, cost telemetry, collection growth, and MCP payload benchmarks.

Making original-byte retention and occurrence provenance foundational is justified. Making OCR/VLM/visual embeddings mandatory is not: they remain optional derived capabilities.

---

## 28. Implementation roadmap

| Stage | Objective and dependencies | Affected modules/contracts | Tests and acceptance | Rollback |
|---|---|---|---|---|
| 0 | Accept ADRs and freeze evaluation corpora | docs/ADR/governance only | contradiction review through ADR-0057 | no runtime impact |
| 1 | Original-byte retention and asset catalog | parser transport V2, ingestion, filesystem, SQLite, `AssetCatalogStoreV1` | migration fresh/old/rollback; exact hashes and occurrences | disable feature; retain additive rows |
| 2 | Complete image extraction | PDF/DOCX/PPTX/XLSX/HTML/MD/standalone parsers | format matrix, bombs, ordering/location, no text regression | per-parser feature flags/prior parser priority |
| 3 | Durable jobs and governance | job store/worker, server DTOs, progress events, consent manifests | claim/concurrency/crash/cancel/resume/budget/security | stop workers; base ingestion unaffected |
| 4 | OCR and scanned-document flow | detector, `OCRProviderV1`, derivation store, OCR index | multilingual scans, partial/failure/cache/invalidation | disable OCR indexes/provider |
| 5 | VLM and visual embeddings | vision/image embedding providers, asset analysis API, modality collections | provenance, prompt safety, dimensions, provider lifecycle | detach new collection aliases |
| 6 | Advanced exact/positional/structured/exhaustive retrieval | planner V2, structured/position stores, completeness/cursors | exhaustive termination, aggregates, injection, bounds | retain V1 query paths |
| 7 | Multimodal candidates/fusion/context/FinalQA V2 | evidence candidate, fusion/reranker, context bundle, citation/snapshot V2 | full provenance, grounding, replay zero-call | feature flag V2; V1 unchanged |
| 8 | Multilingual retrieval | language observations, indexes, benchmark-selected providers, translation derivations | per-direction evaluation and regressions | keep current English/text collections |
| 9 | MCP/HTTP expansion | new thin routes, four tools/resources, auth/binary delivery | protocol/live clients, payload and isolation tests | do not advertise capabilities |
| 10 | Phase 9 UI contract implementation | UI inventory/viewer/job controls/settings | accessibility, original-vs-derived display, cancellation | hide Phase 8.5 views |
| 11 | Certification and staged rollout | all layers | exit gates below, Golden plus multimodal/multilingual corpus | revert feature flags/index aliases |

Each stage updates active docs only after implementation and executable validation. No stage bumps a release until all its required gates are green.

### 28.1 Stage deliverable details

1. **Contracts and evaluation.** Affects ADRs, architecture, governance, and fixtures only. New interfaces/models/storage/API/MCP/UI: none. Dependencies: accepted contradiction analysis through ADR-0057. Tests: schema examples and adversarial design review. Migration: none. Acceptance: every responsibility and supersession is unambiguous. Rollback: withdraw proposed ADRs before acceptance.
2. **Asset/version foundation.** Affects core models only through additive records, ingestion composition, filesystem, SQLite, and server source DTOs. Introduces `DocumentBinaryReference`, `AssetOccurrence`, `AssetCatalogStoreV1`, and occurrence inventory APIs; no MCP tool yet. Dependencies: asset-lifecycle ADR. Tests: fresh/upgrade/rollback, repeat occurrences, shared assets, exact-hash re-supply, authorization. Migration: additive tables and IR backfill. Acceptance: original/occurrence provenance and zero Phase-0–8 identity drift. Rollback: disable original retention/catalog reads.
3. **Extraction coverage.** Affects parser implementations/fixtures and canonicalization adapters. Introduces parser-transport V2 fields, not a new canonical asset. API adds extraction status/omission details; UI contract adds inventory states. Dependencies: Stage 2. Tests: all format/security fixtures. Migration: opt-in exact-byte reparse. Acceptance: supported visuals extracted or explicitly omitted. Rollback: parser priority/feature flags.
4. **Jobs and governance.** Affects core additive job facility, SQLite, server routes/events, provider configuration, and planned UI controls. Introduces job/attempt/manifest/consent records and `ProcessingJobStoreV1`; MCP remains read-only without job mutation initially. Dependencies: job/cost ADR. Tests: leases, concurrent claims, crash, retry, cancel/resume, hard budgets. Migration: job tables only. Acceptance: no duplicate or unauthorized expensive operation. Rollback: stop workers; retain records.
5. **OCR.** Affects OCR plugin family, scanned-page detector, derivation store/index, analysis API, MCP analysis read, and UI overlays. Introduces `OCRProviderV1`, `OCRResult`, and language observations. Dependencies: Stages 2–4. Tests: scripts, boxes, confidence, partial pages, cache and injection. Migration: lazy job scheduling. Acceptance: original assets unchanged and every OCR token attributable. Rollback: detach OCR indexes/providers.
6. **Vision and image vectors.** Affects VLM/image-embedding plugin families, Qdrant modality collections, derivation API/MCP, and UI. Introduces `VisionAnalysisProviderV1`, `ImageEmbeddingProviderV1`, optional `MultimodalEmbeddingProviderV1`. Dependencies: Stages 2–4. Tests: schemas, dimensions, shared-space claims, cost/security/cache. Migration: lazy derived collections. Acceptance: correct space identity and no mandatory cloud work. Rollback: collection alias/provider disable.
7. **Advanced non-semantic retrieval.** Affects planner V2, SQLite structured/position projections, server query V2 DTOs, and bounded document expansion. Introduces exact/positional/structured/exhaustive interfaces, completeness/page/cursor records. Dependencies: Stages 1–3. Tests: exactness, aggregate correctness, cursor stability, injection and bounds. Migration: table/symbol/position projections. Acceptance: “all” and counts are provably complete or explicitly not. Rollback: V1 routes remain default.
8. **Multimodal retrieval and QA.** Affects typed candidates, fusion/reranking, multimodal context, citation/final-QA V2, immutable snapshots, and thin server binding. Introduces multimodal evidence/citation/execution models. Dependencies: Stages 5–7. Tests: modality fusion, provenance, citation compliance, publication order, crash/concurrency/replay. Migration: new snapshot schema family; old snapshots unchanged. Acceptance: grounded image claims and zero-call replay. Rollback: disable V2 binding.
9. **Multilingual retrieval.** Affects language observations, sparse derived indexes, embedding/reranker providers, planner/query language policy, and answer policy. Introduces no canonical text mutation. Dependencies: benchmark corpus and Stages 5–8. Tests: per-language/direction metrics, transliteration, OCR and negatives. Migration: side-by-side index generation. Acceptance: published thresholds per direction. Rollback: retain current English/text index.
10. **MCP/HTTP delivery.** Affects Layer-2 routes/resources/tools only plus service adapters. Introduces the four tools and corresponding versioned REST endpoints; UI API client consumes them. Dependencies: stable Stages 2, 5, 7, and 8 contracts. Tests: live stdio/SSE, binary MIME, cursors, limits, authorization, malformed IDs and disconnects. Migration: none beyond earlier stages. Acceptance: protocol/client matrix green. Rollback: stop advertising new capabilities.
11. **UI implementation and certification.** Affects Phase 9 frontend components/API client plus all certification docs and CI. New domain interfaces/models/storage: none. Dependencies: all prior stages. Tests: accessibility, visual distinction, progress/cancel, full regression, live deployment, security/performance/cost gates. Migration: operator rollout only. Acceptance: Section 29. Rollback: hide UI features and revert index aliases while retaining source records.

---

## 29. Certification gates

Phase 8.5 is complete only when all applicable gates have evidence:

1. **Compatibility:** all Phase 0–8 suites and live text retrieval/Final-QA/MCP behavior pass unchanged.
2. **Migration:** fresh, v0.25.0 upgrade, idempotency, rollback, interrupted migration, and index rollback pass without corpus re-ingestion.
3. **Asset integrity:** bytes/hash/MIME/dimensions and every occurrence provenance link are independently verified; zero unauthorized or orphan occurrences.
4. **Format extraction:** certified image fixtures pass for every supported container and standalone type; omissions are typed.
5. **OCR/VLM:** provider/model/config provenance, cache reuse/invalidation, partial/failure/cancel/resume, and original-vs-derived separation pass.
6. **Visual vectors:** every indexed occurrence maps to the correct model space/dimension/generation; missing/stale vectors are detected.
7. **Retrieval correctness:** exact, ranked, positional, structured, aggregate, cross-document, and multimodal benchmark thresholds are met with no corpus-specific rules.
8. **Completeness:** exhaustive pages prove stable termination; forced truncation/partial/unknown cases report honestly.
9. **Multilingual:** per-language and cross-language thresholds pass; original text and citations remain authoritative.
10. **Final QA V2:** multimodal answers are grounded, cite typed evidence, enforce compliance, publish safely, and replay with zero provider calls.
11. **MCP/HTTP:** live transports, all old/new tools/routes, binary resources, bounds, malformed IDs, authorization, cancellation, and compatibility pass.
12. **Security:** malicious containers/images/SVG/PDFs, bombs, prompt injection, SQL injection, path traversal, cross-notebook leakage, and secret/log leakage tests pass.
13. **Cost governance:** no expensive/cloud operation runs without policy/consent; hard budgets, estimates, cache state, cancellation, and audit events are verified.
14. **Performance:** agreed CPU/GPU profiles meet published latency/throughput/memory/payload targets; no unmeasured target is claimed.
15. **Reproducibility:** pinned providers/models/revisions, offline fixtures, deterministic projections/cursors, and rebuilds produce equivalent identities/results.
16. **Quality:** pytest zero failures and ≥90% coverage, Ruff, strict mypy, package/frontend/Docker builds, diff checks, and GitHub Actions pass.
17. **Documentation:** active architecture, roadmap, README, APIs, MCP, security, governance, changelog, and operator docs match runtime truth.

---

## 30. Risks and mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| VLM/OCR output treated as source truth | P0 | immutable derivation labels, original asset in every citation, untrusted-evidence prompts |
| Cross-notebook asset leakage through shared hash | P0 | authorize occurrence path, never asset ID alone; indistinguishable not-found responses |
| Citation/snapshot provenance flattened | P0 | V2 typed evidence and immutable snapshot; V1 untouched |
| Exhaustive top-k falsely labeled complete | P0 | separate cursor contract and stable snapshot completeness rules |
| Archive/image decompression exhaustion | P0/P1 | preflight limits, isolated workers, decoded-pixel/decompressed-byte quotas |
| Structured query injection or wrong aggregate | P0/P1 | typed IR, parameterized compiler, row universe and completeness evidence |
| Provider cost/data egress without consent | P1 | manifest, consent, hard budgets, deployment policy, audit event |
| Job duplicate work or partial publication | P1 | idempotency keys, leases, immutable outputs, conditional transitions |
| Embedding-space score misuse | P1 | separate collections, declared space IDs, rank fusion |
| Multilingual quality overclaimed | P1 | per-direction benchmarks and capability negotiation |
| Old corpus lacks original bytes/new assets | P2 | explicit unavailable status; exact-hash re-supply; no fabricated backfill |
| Index/storage growth | P2 | lazy processing, generation lifecycle, retention/GC policy, quotas |
| Phase 10 queue conflict | P2 | accept common job-store ADR and update roadmap prospectively |
| UI hides original-vs-derived distinction | P2 | mandatory labeling/provenance and interaction tests |
| Model/provider churn | P2 | revision/config identities, side-by-side generations, narrow invalidation |

---

## 31. Open implementation-profile decisions

The architectural responsibilities are accepted. The following selections need
benchmark, security, or operator-profile evidence during implementation:

1. **Provider/model profiles:** select OCR, VLM, visual embedding,
   multilingual embedding, and reranker revisions only after benchmark, license,
   hardware, trust, and migration review.
2. **Hard transport/resource ceilings:** establish byte/token/page/slide/asset/
   pixel limits and operator override ranges through security/performance tests.
3. **Cloud deployment policy:** define approved providers/regions, data classes,
   retention terms, pre-authorized budgets, and organization consent policy;
   silent cloud fallback remains prohibited.
4. **Language thresholds:** publish acceptance thresholds separately for each
   English/Hindi/Marathi same-language and cross-language direction.
5. **Retention periods:** set policy for originals, derivations, jobs, cursors,
   superseded generations, and audit events.
6. **Shared multimodal space:** enable only if a benchmark winner proves a
   compatible shared space and safe migration; otherwise use separate indexes.

### Architectural decision summary

| Decision | Recommendation | Why | Alternatives | Governing ADR |
|---|---|---|---|---|
| Asset model | reuse `Asset`; add version refs, occurrences, derivations | preserves frozen identity and separates content/location/interpretation | replace Asset; encode in Chunk metadata | ADR-0059 |
| Image storage | content-addressed filesystem; SQLite catalog | existing integrity and dedup | SQLite BLOB; provider object store | ADR-0059/0071 |
| Original documents | retain as asset for new versions | reproducible reparse/migration | depend on external source path | ADR-0059 |
| OCR | independent optional provider/job | derived, cacheable, multilingual | parser-integrated mandatory OCR | ADR-0061 |
| VLM | independent profile-based provider | explicit cost/security/provenance | one implicit description pass | ADR-0062 |
| Visual embeddings | separate interface and spaces | avoids breaking text provider | widen text V1 | ADR-0062 |
| Multimodal index | hybrid separate collections; optional shared space | portability and safe migration | one universal collection | ADR-0062/0071 |
| Fusion | typed candidates + rank fusion | raw scores incomparable | normalized score mixing | ADR-0064 |
| Context | multimodal bundle alongside text V1 | bytes need separate budgets | flatten to text | ADR-0064 |
| Citations | Evidence Citation V2 | image/derived provenance is not a Chunk | reuse ADR-0045 rows | ADR-0064 |
| Full document MCP | cursor-bounded typed blocks | controlled expansion | unlimited text dump | ADR-0065/0066 |
| Asset MCP | native image/resource content with occurrence auth | delivers ground truth | descriptions only | ADR-0066 |
| Context limits | tokens + bytes + pages + assets + pixels | no single unit controls resources | token-only | ADR-0064/0065 |
| Structured queries | typed IR → parameterized SQLite | exact aggregates and safety | LLM over sampled chunks | ADR-0063 |
| Exhaustive search | stable cursor and completeness | honest “all” semantics | very large top-k | ADR-0058 |
| Language detection | derived BCP-47/script observations | preserves uncertainty/provenance | overwrite parser language | ADR-0067 |
| Multilingual models | benchmark then pin | quality/license/hardware vary | select by marketing claim | ADR-0067/0070 |
| Translation | optional immutable derivation | original remains authoritative | replace original with English | ADR-0067 |
| Cache | content/operation/provider/revision/config identity | narrow invalidation and reuse | model-name-only cache | ADR-0060/0062 |
| Processing queue | durable provider-neutral jobs | crash/cancel/resume/cost control | synchronous HTTP work | ADR-0060 |
| Cost governance | manifest, consent, hard budgets | local-first and cloud safety | hidden fallback | ADR-0060/0068 |
| Authorization | authorize through occurrence/notebook scope | shared hashes must not leak | asset-ID bearer access | ADR-0068 |
| UI | original + derived side-by-side | epistemic clarity | description-only view | ADR-0069 |

---

### Closing recommendation

**[PROPOSED]** Implement Phase 8.5 as additive facilities, V2 evidence/context/
citation contracts, independent derived indexes, and opt-in job capabilities.
The implementation order is asset/version provenance → durable jobs/governance
→ extraction → derivations → advanced retrieval/completeness → multimodal
context/citations → MCP/HTTP → multilingual benchmarking → UI contract and
certification.

The architecture is accepted through ADR-0058–ADR-0071. Workstreams 8.5.1
through 8.5.11 are completely implemented, benchmarked, and governed. Phase 8.5.1
asset retention/provenance, Phase 8.5.2 bounded parser extraction, Phase 8.5.3 durable
processing/governance, Phase 8.5.4 provider-neutral multi-script OCR derivations (Tesseract en/hi/mr),
Phase 8.5.5 provider-neutral vision analysis and visual embedding derivations,
Phase 8.5.6 ranked/exhaustive retrieval, positional canonical access, bounded expansion,
signed cursors, and truthful completeness, Phase 8.5.7 deterministic structured extraction
and safe aggregation over exact-version table projections, Phase 8.5.8 typed fusion,
bounded multimodal context, evidence citations, strict citation compliance, and immutable
Final-QA V2 snapshots/replay, Phase 8.5.9 multilingual retrieval with BGE-M3 and BGE-reranker-v2-m3,
Phase 8.5.10 bounded HTTP/MCP delivery (258/258 server tests passed), and Phase 8.5.11 full-scale
evaluation and model benchmarking across 3 candidate families are certified. Production profiles
are pinned in `phase8_5_models.toml` and model assets are isolated on the D: drive. Phase 8.5
foundations are fully prepared for the Phase 9 Web UI.
