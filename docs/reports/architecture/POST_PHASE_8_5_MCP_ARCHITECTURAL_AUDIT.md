# Post-Phase-8.5 MCP / Retrieval / Multimodal Architectural Audit

**Audit date:** 2026-08-26  
**Scope:** Current repository and isolated 44-document Phase 8.5.11 evaluation state  
**Mode:** Audit only; no production implementation, re-ingestion, model change, or database mutation  
**Verdict:** **NOT PRODUCTION-READY AS AN MCP-NATIVE KNOWLEDGE SYSTEM**

## 1. Executive summary

Mnemo's canonical ingestion, document identity, bounded document delivery, signed cursor mechanics, asset occurrence catalog, and occurrence-scoped authorization are substantially working. Direct MCP calls also work when the caller already knows the correct notebook, document, version, occurrence, and derivation identifiers.

The observed external-client failures are therefore not one retrieval bug. They are a mismatch between a capable internal Phase 8.5 domain layer and a much narrower, ID-addressed MCP surface:

- `search_all_notebooks` and `query_notebook` expose bounded V1 ranked text retrieval, not exhaustive, structured, multilingual, or multimodal retrieval.
- `get_document` supports forward cursor traversal, but neither its name nor schema teaches an unfamiliar LLM when traversal is mandatory, and it has no page/from-end selector.
- `get_asset` lists or delivers a known occurrence; it does not search images semantically.
- `get_image_analysis` requires derivation IDs that no MCP tool exposes or resolves.
- OCR, vision, visual-vector, multilingual, advanced, and structured facilities exist in core, but the current evaluation database has no active derived retrieval projections and the MCP server does not compose those services.
- Earlier tests proved direct call/schema conformance. They did not prove blind external-agent tool selection, natural-language occurrence discovery, or end-to-end multimodal reasoning.

The smallest correct response is not to replace canonical ingestion, chunks, models, or V1 retrieval. First fix the MCP contract and composition boundary additively; then populate/activate derived projections; only then evaluate higher-order multi-hop planning.

## 2. What happened after Codex credits were exhausted

The operator reports that Antigravity continued from the partially completed Phase 8.5.11 state. The resulting repository contains the final evaluation report, selected model profiles, direct MCP delivery tests, ADR-0072, and a manually orchestrated search-to-document traversal audit. Those artifacts are useful evidence, but authorship and completion history are not independently reconstructable from runtime behavior alone.

The important post-handoff change was ADR-0072: search results acquired `notebook_id`, while `get_document` and `get_document_chunk` acquired optional notebook auto-resolution. That repaired an identifier propagation defect and enabled a forced 29-call traversal of `manuscript.pdf`. It did not solve intent classification or teach external clients to choose that traversal.

## 3. What Antigravity completed

Repository evidence attributes the following to the post-handoff work:

- completion/reporting of the 44-document evaluation corpus;
- model candidate evaluation and selected profiles for BGE-M3, BGE reranker, CLIP, Tesseract, and Qwen2.5-VL;
- current 10-tool MCP surface and stdio/SSE direct-call validation;
- search result propagation of notebook/document/version identifiers;
- document notebook auto-resolution and ADR-0072;
- direct cursor traversal and error-path tests;
- final quality-gate reports.

Two reported conclusions do not survive reconciliation:

1. “MCP delivery conformance” means direct, pre-identified resource access, not natural-language discovery and orchestration.
2. “Production model profiles established” does not mean those profiles are composed into the live MCP retrieval path. The active V1 engine configuration still uses `nomic-embed-text` and `cross-encoder/ms-marco-MiniLM-L6-v2`; selected Phase 8.5 profiles are declarative and evaluation-script-facing.

The recorded Final-QA artifact also contradicts an unconditional production pass: the preserved benchmark shows incomplete question-level success and no zero-generation replay. Historical reports must remain historical; a separate behavioral report is warranted.

## 4. Current architecture

The current system has three materially different planes:

1. **Canonical V1 plane:** document/version/source/chunk identities, canonical text, FTS/title retrieval, optional dense retrieval, reranking, V1 query/Final-QA.
2. **Phase 8.5 derived plane:** asset occurrences, OCR, vision, visual embeddings, advanced/exhaustive retrieval models, structured retrieval, multilingual retrieval, and delivery services.
3. **MCP adapter plane:** six legacy knowledge tools plus four direct delivery tools.

The domain plane is more capable than the adapter plane. The MCP adapter principally composes V1 `SearchService`/`QueryService` and direct `DeliveryService`; it does not expose the advanced, structured, multilingual, or multimodal retrieval services.

### Layer classification

| Layer | Classification | Evidence |
|---|---|---|
| Production ingestion | PASS | 44 documents, 44 versions/sources, 2,658 chunks and synchronized canonical FTS/title rows |
| Parsers/chunkers | PASS for canonical corpus | Current clean ingestion state; no evidence that current failures originate in chunking |
| Canonical FTS/title | PASS | 2,658/2,658/2,658 parity |
| V1 dense/reranking | DESIGN LIMITATION / operational dependency | Live MCP uses V1 configured models and required Ollama was unavailable during the one lightweight probe |
| Asset extraction | PASS | 464 occurrences retained with typed locators |
| OCR/Vision persistence | PARTIAL | 14 OCR results and 26 vision results, covering only a bounded subset |
| Derived index projections | BUG / INCOMPLETE COMPOSITION | OCR, visual-vector, multilingual, structured, and active-generation projection counts are zero |
| Advanced/exhaustive core | PASS as an internal typed foundation | Implemented and unit-tested, but not exposed by server/MCP |
| Structured core | PASS as an internal typed foundation | No populated projections or MCP contract |
| Multilingual core | PASS as an internal typed foundation | No multilingual embeddings or MCP composition in current database |
| Document delivery | PASS | Exact version, bounded blocks/original bytes, signed snapshot cursor |
| Cursor usability | API DESIGN DEFECT | Forward-only opaque continuation; weak descriptions; no positional/from-end access |
| Image delivery | BUG / DESIGN LIMITATION | Direct known-occurrence delivery works; discovery, analysis-ID resolution, and provenance-bearing binary delivery do not |
| MCP schema/descriptions | MAJOR USABILITY DEFECT | Ranked vs exhaustive and search vs traversal are not explained; no output schemas |
| External orchestration | NOT VALIDATED / BROKEN | Direct-call matrices used preselected IDs and tool chains |

## 5. Current MCP surface

The server exposes ten tools and one static capability resource, `mnemo://capabilities`.

| Tool | Intended purpose | Use when | Do not use when | Continuation/composition | LLM discoverability |
|---|---|---|---|---|---|
| `list_notebooks` | Enumerate notebooks | Finding a notebook scope | Finding document content | Keyset cursor, but unrelated to document traversal | Fair |
| `get_notebook_summary` | Notebook summary | A coarse overview is enough | Exact/exhaustive evidence is required | No retrieval chain guidance | Fair |
| `search_all_notebooks` | V1 ranked text search | Finding relevant canonical chunks/documents | “all,” numeric, exact end/page, or image-semantic requests | Returns IDs usable by delivery; no completeness/cursor contract | Poor: description says only “Full-text and semantic search” |
| `query_notebook` | V1 evidence retrieval and optional synthesis | Bounded question answering in one notebook | Exact traversal, exhaustive/structured, or multimodal requests | Top-k only; no declared completeness | Fair but over-broad wording |
| `get_source_insights` | Retrieve precomputed insights | A known source has insight records | Raw/full document or general search | No discovery guidance | Fair |
| `get_timeline` | Retrieve timeline events | Chronology for a known notebook | General exact traversal | Bounded list only | Fair |
| `get_document` | Deliver blocks or original bytes for an exact version | Exact/full/positional document reading after IDs are known | Semantic discovery | Cursor is merely “next blocks”; no repeat-until-complete instruction | Poor for end/full/page intent |
| `get_document_chunk` | Deliver one known canonical chunk | Exact chunk ID is already known | Document traversal | Good direct composition after search | Good for direct-ID use |
| `get_asset` | List occurrences for a known document or deliver one known occurrence | IDs are already known | Natural-language image search | Overloads inventory and binary delivery; cursor semantics undocumented | Poor |
| `get_image_analysis` | Deliver selected OCR/Vision derivations | Occurrence and derivation IDs are known | Discovering an image or latest analysis | Required derivation IDs are not discoverable via MCP | Broken composition |

The tools define input schemas but no explicit output schemas. Important response invariants—provenance, completeness, truncation, cursor binding, and next-step guidance—are therefore visible only after a successful call.

## 6. Verified working components

- Canonical 44-document ingestion and indexed lifecycle.
- Exact document/version/source identities and search result identity propagation.
- Direct canonical chunk retrieval.
- Forward, bounded document-block traversal with signed snapshot cursors.
- Original-byte document delivery with MIME, hash, size, completeness, and cursor metadata.
- Asset occurrence storage, deterministic identity, typed location, and direct authorization.
- Direct binary retrieval for a known occurrence within configured bounds.
- Direct OCR/vision delivery when valid occurrence and derivation IDs are supplied.
- Stdio and SSE MCP initialization/tool discovery.
- Invalid UUID, missing-resource, cursor tampering, and notebook mismatch handling in tested direct paths.

## 7. Verified broken components

- Natural-language exact document traversal is not reliably discoverable from tool metadata.
- There is no semantic image/asset search MCP operation.
- The inventory-to-analysis chain cannot discover derivation IDs.
- Image responses discard the delivery attribution/completeness/hash/cursor envelope.
- A bounded partial image can be emitted as raw `ImageContent`, which may be undecodable and gives the client no continuation information.
- Standalone images have no canonical text chunks and therefore cannot be discovered through V1 text search.
- OCR/vision/visual embeddings are not broadly generated and have no active retrieval projections in the current evaluation database.
- Advanced/exhaustive, structured, multilingual, and multimodal retrieval are not exposed through MCP.
- Selected Phase 8.5 model profiles are not the live V1 MCP retrieval configuration.
- The previous evaluation's direct-call matrix did not test blind tool choice or multi-step external-agent success.

## 8. Root-cause analysis

| Symptom | Immediate cause | Root layer | Local bug or architecture change? |
|---|---|---|---|
| Last page answered from search chunks | Search sounds sufficient; document traversal contract is implicit | MCP descriptions/schema/orchestration | Local additive contract fix, then optional positional API enhancement |
| Cursor not followed | Cursor description lacks obligation and goal semantics | MCP API usability | Local bug |
| Asset inventory found but image question fails | Inventory is not semantic discovery; binary/analysis require IDs | MCP composition + missing derived retrieval binding | Both local API bugs and additive adapter architecture |
| Analysis cannot be called naturally | Derivation IDs are required but not returned by inventory or resolvable as “latest authorized” | MCP schema | Local contract bug |
| “All matches” incomplete | V1 search is top-k and reports no completeness | Wrong API abstraction | Expose existing exhaustive core additively |
| CPI comparisons unreliable | No MCP structured-query contract and no populated table projection | Adapter + projection lifecycle | Additive architectural integration |
| Cross-language retrieval unreliable | Live MCP does not use multilingual service/profile; DB has zero multilingual embeddings | Composition/configuration | Integration defect, not chunking evidence |
| Image-language questions fail | Only 14 OCR occurrences, zero OCR FTS, no multimodal search tool | Processing/indexing/adapter | Integration and coverage defect |
| Multi-document completeness unreliable | Top-k per call does not establish corpus coverage | Retrieval contract/orchestration | Expose exhaustive scope now; dynamic multi-hop later |

## 9. MCP tool discoverability audit

The interface is adequate for a human developer holding IDs and reading implementation docs. It is not self-teaching for a new LLM.

Critical omissions are:

- no “when not to use search” language;
- no declaration that search/query are ranked top-k and non-exhaustive;
- no explicit instruction to follow `next_cursor` until `null` for full/end traversal;
- no description of cursor snapshot binding or completeness values;
- no positional selection (`page_number`, ordinal range, section, from-end/reverse);
- no output schema;
- no semantic asset-search operation;
- no tool that lists or resolves derivations for an occurrence;
- no advertised tool chains or next-action hints;
- capability discovery reports delivery capabilities, not retrieval modes and index readiness.

Blaming the client is therefore unsupported. The client is making a plausible choice from an ambiguous tool set.

## 10. Full-document retrieval audit

Direct traversal works. The prior `manuscript.pdf` evidence reached 116 blocks in 29 calls, ended with `completeness=complete`, and returned `next_cursor=null`.

The external-agent experience fails because:

1. search is described broadly and appears cheaper/more relevant;
2. `get_document` does not advertise exact traversal intents;
3. the caller must first identify the correct version;
4. “last” requires forward traversal from block zero;
5. no schema rule says a truncated response is insufficient for the user's answer;
6. no output schema makes the continuation contract visible before calling.

This is primarily an MCP contract/usability defect, not a parser, chunker, or cursor-integrity defect.

## 11. Cursor/pagination audit

The signed cursor is a strong internal design: it binds a snapshot, prevents tampering, enforces bounds, and communicates `completeness`/`next_cursor` in block delivery.

External shortcomings:

- forward-only traversal makes “last page/paragraph” O(number of blocks);
- no exact page or ordinal-range request;
- `max_items` and `max_bytes` have no defaults/maximums in the MCP schema descriptions;
- “next blocks” does not explain that the cursor must be supplied unchanged;
- page numbers are payload metadata, not selectable parameters;
- there is no explicit stable snapshot/version narrative in the tool description;
- original and block modes have different envelopes and naming conventions.

Recommendation: retain the signed cursor implementation. Add descriptive invariants immediately, then add an additive positional/range retrieval contract rather than teaching every LLM to scan whole documents.

## 12. Image/asset retrieval audit

The asset catalog is healthy as a provenance store, not as a search index. The current database contains 464 occurrences and 469 catalog assets overall. Current image-occurrence content resolves to 433 distinct hashes; this does not match the historical report's 434 claim and should be reconciled without rewriting that report.

`get_asset` has two unrelated modes:

- without `occurrence_id`: list known-document occurrences;
- with `occurrence_id`: deliver bytes.

Neither mode can answer “which image shows the milling machine?” The former requires document IDs; the latter requires occurrence ID. The binary `ImageContent` drops the otherwise available attribution, locator, hash, completeness, total size, and continuation cursor.

Standalone images are especially undiscoverable: they need no canonical textual chunks, and the current MCP search does not query visual embeddings or vision descriptions.

## 13. OCR/VLM audit

The current isolated database contains:

- 14 OCR results and 14 OCR regions;
- 26 vision results;
- 76 generic asset derivations;
- 0 OCR projection rows/FTS content rows;
- 0 visual-vector projection rows;
- 0 active index generations.

Thus OCR/VLM persistence has been demonstrated for a small evaluation cohort, but searchable coverage has not. `get_image_analysis` can deliver a known derivation, but the MCP surface neither returns available derivation IDs with inventory nor supports “latest valid authorized analysis.”

Provider benchmarking quality and end-to-end client usability are different tests. The former does not establish the latter.

## 14. Multilingual audit

The selected BGE-M3 and reranker profiles were benchmarked by scripts, but the live V1 MCP engine remains configured with the V1 English-oriented embedding/reranker path. The current database contains zero multilingual embeddings and zero language derivations.

Consequences:

- exact Unicode lexical matching may work when canonical source text is present;
- English-to-Hindi/Marathi and reverse semantic retrieval are not proven live through MCP;
- Marathi/Hindi OCR evidence is not retrievable because OCR FTS is empty;
- model installation/configuration alone is not end-to-end integration.

No evidence implicates canonical chunking as the primary failure.

## 15. Multimodal audit

The complete natural-language chain is broken at discovery and indexing:

```text
natural-language image query
  -> no MCP multimodal/asset search
  -> no active OCR/visual projection
  -> occurrence ID not discovered
  -> derivation IDs not discovered
  -> direct delivery tools cannot be composed
```

For a manually selected occurrence, original bytes and selected analyses can be delivered. That is direct multimodal delivery, not multimodal retrieval. Only a small fraction of 464 occurrences has OCR/vision/embedding records, so even a new search adapter would currently have incomplete coverage and must report that explicitly.

## 16. Exhaustive-query audit

`search_all_notebooks` is a ranked top-k API with `top_k <= 100`. Its returned `total` is the returned-list length, not a corpus match count. It has no scope-exhaustion proof, continuation cursor, searched-representation list, or completeness state. It cannot guarantee “all.”

The core already contains an `AdvancedRetrievalService` with explicit ranked/exhaustive semantics and bounded cursors. The immediate architectural correction is to expose that contract through an additive MCP tool—not to stretch V1 search or raise top-k arbitrarily.

## 17. Structured/numeric-query audit

Core structured retrieval supports typed filtering, sorting, grouping, and aggregation, but the current database has zero structured table projections and cells, and MCP exposes no structured-query tool.

Therefore `CPI > 8.9`, ranges, sorting, grouping, and comparison against another student's CPI cannot be guaranteed. Semantic top-k retrieval can locate a table but cannot provide completeness or safe numeric evaluation. Required work belongs to the structured projection plus structured MCP adapter layer, not to an LLM prompt workaround.

## 18. Multi-document audit

The existing identifiers are adequate to compose multiple direct retrievals manually. Bounded comparisons over a few known documents are possible. Complete comparisons across “every document” are not guaranteed because document discovery is ranked and non-exhaustive.

The response provenance is adequate at canonical search/chunk boundaries after ADR-0072, but insufficient for assets because binary delivery discards its envelope. A complete comparison needs explicit corpus scope, exhaustive enumeration, per-document traversal/completeness, and bounded join/aggregation semantics.

## 19. Multi-hop audit

Not every failure belongs to Phase 11.

**Fix now in the Phase 8.5 adapter boundary:**

- ranked/non-exhaustive labels and “when not to use” descriptions;
- cursor-following instructions and positional document access;
- occurrence/derivation discovery;
- provenance-bearing image delivery;
- exposure of already-implemented exhaustive, structured, multilingual, and multimodal contracts;
- truthful capability/index-readiness reporting.

**Genuinely later multi-hop responsibility:**

- dynamic decomposition of open-ended questions;
- iterative joins across unknown documents/modalities;
- evidence-gap detection followed by replanning;
- long-running agent policies and strategy selection.

Phase 11 should orchestrate explicit capabilities; it should not compensate for missing or misleading capabilities.

## 20. Query-intent to tool-chain matrix

| User intent | Correct tool chain | Currently discoverable? | Works now? |
|---|---|---:|---:|
| Find relevant text | `search_all_notebooks` | Yes | Yes, ranked V1 only |
| Exact known chunk | search -> `get_document_chunk` | Mostly | Yes |
| Exact paragraph | search -> `get_document` blocks -> traverse | No | Only manually |
| Last page/paragraph | search -> document traversal to terminal cursor | No | Mechanically yes; agent behavior no |
| Entire document | search -> repeat `get_document` until complete, or bounded original | Weak | Only manually/bounded |
| Exact page N | positional document retrieval | No | No direct operation |
| List images in known document | search -> `get_asset` inventory | Weak | Yes with IDs |
| Retrieve known image | inventory -> `get_asset(occurrence_id)` | Weak | Yes, but metadata envelope is lost |
| Understand known image | inventory -> resolve analyses -> `get_image_analysis` | No | Broken: derivation IDs undiscoverable |
| Find image by description | multimodal/asset semantic search -> delivery | No | No |
| All matches | advanced exhaustive search -> cursor | No | Core only, not MCP |
| Numeric filter/aggregate | structured projection -> structured query | No | No live projection/tool |
| Cross-document bounded comparison | ranked/exhaustive discovery -> retrieve each -> compare | Weak | Partial only |
| Complete corpus comparison | exhaustive enumeration -> per-document completeness -> aggregate | No | No |
| Hindi/Marathi semantic query | multilingual retrieval profile -> typed results | No | Not integrated/indexed |
| Image plus Marathi OCR | multimodal search -> occurrence -> OCR/VLM -> delivery | No | No end-to-end path |

## 21. Architecture risks

- **P0:** The server can advertise a production MCP connection while its natural-language multimodal, multilingual, structured, and exhaustive paths are not exposed or indexed.
- **P1:** Domain features and adapter features are certified together despite different readiness levels.
- **P1:** Selected provider profiles are not composed into live retrieval, creating configuration illusion.
- **P1:** ADR-0072 modified frozen `StorageInterfaceV1`, contrary to the additive Phase 8.5 rule. The capability is useful, but it should have used an additive relationship/authorization protocol.
- **P1:** The binary image path loses provenance and bounded-delivery state.
- **P2:** Generic delivery names overload distinct intent classes.
- **P2:** Forward traversal is inefficient for positional requests and invites premature stopping.

## 22. API design risks

- Search and answer tools do not declare completeness limitations.
- No output schema means clients cannot plan around returned identifiers or cursors before execution.
- Tool descriptions omit negative guidance and required chains.
- `get_asset` conflates inventory and delivery.
- `get_image_analysis` exposes storage-oriented derivation IDs rather than an agent-oriented selection contract.
- Capability discovery reports configured feature states rather than per-index readiness and coverage.
- No document/asset discovery resource templates exist; only a capability resource is listed.
- Optional notebook auto-resolution improves ergonomics but obscures the authorization path and must remain fail-closed.

## 23. Security/authorization risks

The occurrence-scoped authorization and signed cursor design should be retained. No direct cross-notebook leak was established in this audit.

Risks requiring targeted regression coverage:

- auto-resolution must not reveal existence through distinguishable errors;
- shared content hashes must never authorize another occurrence;
- “latest derivation” resolution must be occurrence- and notebook-scoped;
- cursor continuation must reauthorize and remain bound to immutable snapshot identity;
- image responses must carry provenance without exposing filesystem/storage URIs;
- truncated binary delivery must not emit invalid partial media as if complete;
- capability discovery must not disclose unauthorized corpus inventory;
- derived search caches must be notebook/occurrence scoped.

## 24. Recommended fixes

1. **P0: correct external claims and capability truthfulness.** Separate direct delivery readiness from search/orchestration readiness.
2. **P0: repair binary delivery envelope.** Never return partial image bytes as a complete image; preserve attribution, hash, completeness, and continuation in MCP resource metadata.
3. **P1: improve existing tool descriptions/schemas additively.** State ranked/non-exhaustive behavior, “when not to use,” cursor obligations, stable snapshot rules, and output structure.
4. **P1: make analysis discoverable.** Asset inventory should expose authorized available derivations, or analysis retrieval should resolve a typed latest/profile selection without accepting arbitrary IDs.
5. **P1: expose semantic asset/multimodal search.** Bind existing typed candidate services; keep search distinct from delivery and analysis.
6. **P1: expose advanced exhaustive and structured retrieval.** Use existing core contracts and explicit completeness; do not mutate V1 tools.
7. **P1: activate governed derived projections.** OCR, visual, multilingual, and structured indexes need generation lifecycle, coverage reporting, and atomic promotion before advertising support.
8. **P1: compose certified model profiles into additive V2 services.** Preserve V1 defaults/contracts.
9. **P2: add positional document delivery.** Page/slide/ordinal/range/from-end selectors with bounded responses and signed snapshot cursors.
10. **P2: add agent-behavior contract tests.** Start from tool metadata and a natural-language intent; do not preselect IDs/tool chains.
11. **P2: replace ADR-0072's V1 storage-interface mutation with an additive protocol in the implementation phase, retaining behavior and compatibility shims temporarily.

## 25. Recommended MCP API redesign

Do not rename or break the ten existing tools. Add clearer aliases/capabilities and deprecate only after measured client adoption.

Recommended additive intent-oriented surface:

- `search_knowledge`: explicitly ranked, canonical text/title search.
- `search_evidence`: advanced ranked or exhaustive search with representation scope, coverage, cursor, and diagnostics.
- `query_structured`: typed filters, comparisons, sorting, grouping, aggregates, and completeness.
- `search_assets`: semantic/metadata image occurrence discovery returning occurrence and available derivation selectors.
- `retrieve_document_blocks`: exact version plus page/ordinal/range/from-end selectors and continuation.
- `retrieve_asset`: original authorized binary with a provenance-bearing resource envelope.
- `retrieve_asset_analysis`: occurrence plus modality/profile selector; server resolves an authorized immutable derivation.

Each tool should declare an output schema, “use when,” “do not use when,” completeness guarantees, bounds, and recommended next steps. The capability resource should report `SUPPORTED`, `DISABLED`, `UNAVAILABLE`, and coverage/generation readiness separately.

## 26. Phase 8.5 versus Phase 11 responsibility boundary

Phase 8.5 already defines the necessary typed evidence, exhaustive, structured, multilingual, multimodal, delivery, provenance, and completeness foundations. Exposing and composing them is Phase 8.5 closure work.

Phase 11 should add an adaptive agent that chooses among those explicit contracts, performs iterative retrieval, detects missing evidence, and executes multi-hop plans. It should not encode hidden knowledge of cursor fields or storage IDs, nor should it infer completeness from top-k results.

## 27. Minimal targeted test plan

Run these after the approved implementation, using one fixture per behavior before any full suite:

1. Blind-tool-selection evaluation for “last paragraph” using only MCP tool metadata.
2. Exact `manuscript.pdf` last-page traversal and new positional selector equivalence.
3. Full-document traversal with interruption/resume, tampered cursor, and version change.
4. Standalone-image description search -> occurrence -> binary -> analysis.
5. Embedded PDF/PPTX image search with locator and duplicate-occurrence preservation.
6. Inventory -> analysis without pre-supplied derivation IDs.
7. Oversized image/document delivery: no undecodable partial media, explicit continuation.
8. Exhaustive “all occurrences” with complete, truncated, unavailable-index, and resumed states.
9. Structured CPI ground-truth query with filters, range, sort, and count.
10. One EN/HI/MR lexical case and one cross-language case in each direction.
11. Marathi-in-image OCR/VLM retrieval with provenance through delivery.
12. Bounded two-document comparison and complete corpus-wide source enumeration.
13. Cross-notebook shared-hash, cursor replay, derivation selection, and capability leakage tests.
14. Existing ten-tool schema snapshots and six V1 behavioral regressions.

No re-ingestion or model benchmark is needed to diagnose these adapter issues. Derived projection tests should use an isolated copied/evaluation database.

## 28. Priority classification

### P0 — blocks production

- Production readiness claims exceed externally usable MCP capability.
- Partial binary image delivery can be surfaced without completeness/provenance.
- Natural-language multimodal discovery is absent despite advertised multimodal delivery.

### P1 — major capability defect

- No exhaustive/structured/multilingual/multimodal MCP retrieval bindings.
- No active derived projections in the current evaluation database.
- No analysis derivation discovery.
- Certified model profiles are not composed into the live additive retrieval path.
- ADR-0072 changed a frozen storage interface.
- Historical evaluation conclusions conflict with retained QA/census artifacts.

### P2 — usability/composability issue

- Weak search/document/cursor descriptions and no output schemas.
- No page/from-end/range selection.
- `get_asset` overloads inventory and delivery.
- Provenance is dropped from native image content.
- No behavioral tool-selection regression suite.

### P3 — improvement

- Intent-oriented aliases, next-action hints, richer capability resource, and deprecation plan.

## 29. What should not be changed

- Canonical document, version, source, chunk, text, and identity contracts.
- Current parser/chunker behavior without new loss evidence.
- Canonical V1 FTS/title index semantics.
- Existing six V1 MCP tools or V1 HTTP behavior.
- Content-addressed asset identity or occurrence-scoped authorization.
- Signed cursor/snapshot binding and fail-closed bounds.
- Qdrant optionality.
- The 15-document Golden Corpus or 44-document evaluation corpus.
- Selected models merely to compensate for missing adapter composition.
- Retrieval scores or corpus-specific ranking rules.
- Tunnel/transport architecture; stdio/SSE connectivity is not the root cause.

## 30. Recommended implementation sequence

1. Freeze a behavioral contract and truthful capability matrix.
2. Fix image/resource envelope correctness and derivation discovery.
3. Improve descriptions and add output schemas without breaking tool names.
4. Add positional document retrieval while retaining cursor semantics.
5. Expose existing advanced/exhaustive retrieval with explicit completeness.
6. Expose structured query and populate an isolated structured projection.
7. Wire governed OCR/vision/visual/multilingual projections and report coverage.
8. Add semantic asset/multimodal search, separate from delivery and analysis.
9. Compose selected profiles into additive V2 services, leaving V1 untouched.
10. Run the targeted external-agent matrix, then broader regression/security gates.
11. Only after those pass, begin Phase 11 multi-hop orchestration work.

## 31. Explicit answers to the twelve audit questions

**Q1 — Why does ChatGPT choose search instead of traversal?**  
Because search is broadly described as full-text/semantic retrieval, while `get_document` does not identify last/full/exact-location intents or mandate cursor continuation. Search is the rational first choice from the exposed metadata.

**Q2 — Is the cursor schema explicit enough?**  
No. It says only “pagination cursor for next blocks.” It omits repeat-until-complete rules, snapshot binding, truncation obligations, positional semantics, and output schema.

**Q3 — Why can inventory retrieval still fail to answer about an image?**  
Inventory proves occurrence storage, not semantic discovery or model-readable analysis. The client still needs occurrence selection, bytes, and derivation IDs; those steps are not composed, and derived indexes are empty.

**Q4 — Is `get_asset` semantic image retrieval?**  
No. It is direct inventory/delivery after document or occurrence identity is known.

**Q5 — Can an external LLM discover the correct occurrence from natural language?**  
Not generally. It may enumerate a known document's assets, but there is no semantic asset search, and standalone images are absent from canonical text search.

**Q6 — Can the system guarantee exhaustive results?**  
Not through current MCP search/query tools. They are bounded top-k and expose no completeness proof. The internal advanced service can model bounded exhaustive retrieval but is not exposed.

**Q7 — Can it correctly execute `CPI > 8.9`?**  
Not with a guarantee. The structured core exists, but there are no populated structured projections or MCP structured-query contract. V1 semantic retrieval is unsuitable for complete numeric filtering.

**Q8 — Can it perform complete multi-document comparisons?**  
Only bounded manual comparisons over already identified documents. Complete corpus comparisons are not guaranteed.

**Q9 — Are multilingual retrieval and OCR end-to-end working?**  
No. Candidate models and some derivations were evaluated, but the live MCP path is V1, multilingual embeddings and OCR projections are empty, and no multilingual/multimodal MCP retrieval tool exists.

**Q10 — What is Phase 11 versus an immediate bug?**  
Immediate: descriptions, cursor usability, derivation discovery, binary provenance, and exposing existing exhaustive/structured/multimodal services. Phase 11: adaptive decomposition, iterative joins, replanning, and open-ended multi-hop strategy.

**Q11 — Does MCP expose the right abstractions?**  
It exposes useful low-level direct delivery primitives but not the complete agent-facing abstractions for exhaustive, structured, multilingual, or multimodal discovery. The abstraction boundary is incomplete.

**Q12 — What would an MCP-native design change?**  
Keep immutable identities, provenance, authorization, and bounded delivery; make intent explicit in tool names/descriptions, declare output/completeness contracts, separate discovery from delivery from analysis, expose typed exhaustive/structured/multimodal searches, provide positional document access, and make capability/index readiness truthful and machine-readable.

## Audit evidence and constraints

- Static inspection: MCP tool definitions/handlers, server resource registration, V1 search composition, delivery service, advanced/structured/multilingual services, configuration, ADR-0072, and Phase 8.5.11 governance reports.
- Read-only database inspection: 44 documents, 44 versions, 44 sources, 2,658 chunks, 2,658 FTS rows, 2,658 title rows, 464 occurrences, 14 OCR results, 26 vision results, 16 visual embeddings, and zero active derived retrieval projections/generations.
- Reused targeted evidence: 29-call direct document traversal, 21 MCP delivery/tool tests, stdio direct-call matrix, retained model/QA artifacts.
- One lightweight live engine probe could not initialize because the configured Ollama service was unavailable; no model service was started because static and persisted evidence already distinguished the hypotheses.
- No production code, database, corpus, model, embedding, tunnel, or MCP configuration was changed during this audit. The 15-document Golden Corpus was not opened or mutated; its last certified read-only counts remain 15/15/15 and 1,514 canonical chunk/FTS/title rows.

**AUDIT STATUS: COMPLETE — IMPLEMENTATION APPROVAL REQUIRED FOR FIXES**
