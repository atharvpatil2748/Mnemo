# MNEMO — Phase 0–8 Full Repository / Architecture / Governance / Golden Corpus Audit

> **Date:** 2026-08-17 · **Branch:** `main` @ `f1b621e` · **Auditor mode:** INDEPENDENT, READ-ONLY (no production code, tests, ADRs, docs, or databases were modified by this audit)
> **Test baseline verified locally:** `1370 passed, 1 skipped, 90.46% coverage` (67s) — matches the claimed CI baseline.
> **Companion note:** `docs/audit_report.md` (untracked, earlier today) is a *repair* audit performed against a pre-`f46bed0` state; several of its claims are now stale and are assessed in §14.4.

---

## 1. Executive Summary

The **code** is in the best shape of the repository's history: the Phase 3–8 pipeline is fully implemented, PPTX parsing and CSV partitioning exist and are registered (`f46bed0`), the CodeChunker closure fix is present, all six MCP tools are validated, versions are synchronized at 0.23.0, and the full test suite is green.

The **committed Golden Corpus is not**. The checked-in database certifies, as `indexed`, a document (`server.js`, 59,851 bytes) of which **121 characters (0.2%) are actually indexed** — every major symbol in the file is empirically unretrievable via FTS (§11). The committed corpus also references parsed-IR files that are not committed, contains a document stuck in `indexing` (the local flip to `indexed` is uncommitted), and includes a PPTX deck whose slide semantics collapsed into a single chunk. None of this is caught by the 1,370 green tests, because no test asserts corpus completeness, plausibility, or lifecycle status. Governance documents nevertheless certify the corpus "fully consistent" and "release-ready."

A separate architecture violation exists in production code: the diversity reranker hard-codes the developer's personal Golden Corpus filenames and keyword signatures (including student names and roll numbers) inside `mnemo-core`.

**Verdict: BLOCKED BY P0/P1 FINDINGS** (1 × P0, 5 × P1, 7 × P2, 5 × P3, 4 × P4).

---

## 2. Scope, Method, and Evidence Classes

Investigations performed: full read of parsers/engine/chunkers/storage/retrieval/MCP code; direct SQL inspection of the committed (`git show HEAD:...`) and working-tree databases; hash-mapping of all 7 documents to `goldenDataset/` sources; live FTS retrieval probes; full test-suite run; ADR, roadmap, changelog, governance, README, CI, packaging, and git-state audits.

Evidence classes used throughout: **IMPLEMENTED** (code read), **TESTED** (test read/run), **VERIFIED** (executed against real data), **DOCUMENTED** (doc read), **INCONSISTENT**, **BROKEN**, **UNKNOWN**.

---

## 3. Phase 0–8 Certification Matrix

| Phase | Architecture | Implementation | Tests | Docs | Governance | Golden Corpus | CI | Final Verdict |
|---|---|---|---|---|---|---|---|---|
| 0 — Dev env / packaging | PASS | PASS | PASS | PASS w/ concern | PASS | n/a | PASS | **PASS WITH CONCERN** (mypy scope drift P3-14) |
| 1 — Core scaffolding | PASS | PASS | PASS | PASS | PASS | n/a | PASS | **PASS** |
| 2 — Storage layer | PASS | PASS | PASS | PASS | PASS | n/a | PASS | **PASS** |
| 3 — Parser system | PASS | PASS (PPTX now real) | PASS | **INCONSISTENT** (README omits PPTX) | PASS | **BROKEN** (server.js 2 chunks; ME361 1 slide) | PASS | **BLOCKED (corpus)** |
| 4 — Chunking engine | PASS | PASS | PASS | PASS | PASS | **BROKEN** (corpus built by pre-fix pipeline) | PASS | **BLOCKED (corpus)** |
| 5 — Embedding pipeline | PASS | PASS | PASS | PASS | PASS | Qdrant disabled by design | PASS | **PASS** |
| 6 — Retrieval pipeline | PASS | **INCONSISTENT** (hard-coded corpus signatures in reranker) | PASS | PASS | PASS | PASS (Gita retrievable) | PASS | **PASS WITH CONCERN (P1-6)** |
| 7 — REST/server | PASS | PASS | PASS | PASS | PASS | n/a | PASS | **PASS** |
| 8 — MCP / release | PASS | PASS | PASS | **INCONSISTENT** (roadmap header, release tag) | **INCONSISTENT** (certification vs corpus reality) | **BROKEN** | PASS | **BLOCKED (corpus + governance)** |

---

## 4. Phase 1 — Core Pipeline Boundary Matrix (code-traced)

| Boundary | Documented | ADR | Implementation | Tests | Verified | Issues |
|---|---|---|---|---|---|---|
| bytes → ParseResult | ✔ | 0011 | `ParserRouter.route` (`parsers/router.py:81`) | test_parser_router.py | ✔ | MIME fallback path is cross-platform-safe (libmagic optional) |
| ParseResult → cleaned | ✔ | 0012 | `DocumentCleaner.clean` (`cleaner/cleaner.py:26`) | test_cleaner.py | ✔ | prose `\s+→" "` collapse; code NFC-only — correct post-fix |
| cleaned → doc_type | ✔ | 0013, 0036 | `DocumentClassifier.classify` | test_classifier*.py | ✔ | CODE_EXTENSIONS superset unreachable (see P2 — router has no parsers for `.sh/.yaml/.toml/.ini/.css/.rb/.php`) |
| classified → ParsedDocument | ✔ | 0014 | `DocumentCanonicalizer` + `IngestionPipeline.ingest` (`ingestion/pipeline.py:35`) | test_document_canonicalizer.py, test_ingestion_pipeline.py | ✔ | asset persistence before canonicalize; dedup loads existing IR |
| ParsedDocument → ChunkDraft→Chunk | ✔ | 0015 | `ChunkerDispatcher.dispatch` (`chunkers/dispatcher.py:49`) | test_chunker_dispatcher.py | ✔ | oversized/short-parent/duplicate-identity guards all raise — fail-closed |
| Chunk → stores | ✔ | 0010 (hist.), composite | `CompositeStorage.upsert_chunks` (`storage/composite.py:368`) | test_composite_storage.py | ✔ | snapshot+compensator rollback; exact-version IR required (`_build_retrieval_projection`) |
| Storage → retrieval | ✔ | 0038–0048 | sparse/dense/fusion/parent/rerank/context/citation | per-module tests | ✔ (Gita) | reranker diversity uses hard-coded corpus signatures (P1-6) |
| Retrieval → MCP | ✔ | 0049 | `mcp/tools.py` (6 tools) | test_mcp_*.py | ✔ | read-only tool surface verified |

Determinism: chunk identity is `sha256(version_id, span, text)` (`dispatcher.py:19`); blob IDs are `uuid5(namespace, sha256)` (`filesystem.py:118`); canonical corpus IDs are UUIDv5. Random UUIDv4 appears only for notebook/source rows created by ad-hoc ingestion scripts.

---

## 5. Phase 2 — Parser Audit (all verified registered in `engine.py:461-485`)

| Format | Parser | Registered | Produces | Notes |
|---|---|---|---|---|
| PDF | `PDFParser` | ✔ `.pdf`, `application/pdf` | text/heading/table + assets | `import fitz` deprecated alias (P3-16) |
| DOCX | `DOCXParser` | ✔ | text/heading/list/image | |
| **PPTX** | `PPTXParser` (`parsers/pptx.py`, ADR-0036-aware) | ✔ `.pptx` + MIME | RawHeading/RawText/RawTable with `page_number=slide` | **Exists and registered** — contradicts prior audit report (P1-5); no notes extraction |
| Markdown | `MarkdownParser` | ✔ | heading/text/code/table + `parser.markdown.*` | |
| HTML | `HTMLParser` | ✔ | mixed raw blocks | |
| TXT/LOG | `PlainTextParser` | ✔ | RawTextBlock paragraphs | |
| Source code (15 exts) | `PlainTextParser` | ✔ | **RawCodeBlock** (post-fix) | `.sh/.yaml/.toml/.ini/.css/.rb/.php/.xml` advertised by classifier but **routable by no parser** (P2, UnsupportedError at router) |
| JSON | `JSONParser` | ✔ | RawCodeBlock | |
| CSV/TSV | `CSVParser` | ✔ | **partitioned** RawTableBlocks (≤400 est. tokens, ≤50 rows, header repeated) | partitioning present post-`f46bed0`; corpus CSV doc has 79 chunks — working |

Malformed inputs: empty bytes, bad zip, no-slide pptx, invalid UTF-8, invalid CSV all raise `ContractValidationError` (tested). Deterministic. `.ppt` (legacy binary) is classified SLIDES but has **no parser** → UnsupportedError (documented gap, P3).

---

## 6. Phase 3 — Code Chunking

- 9 language specs (py/js/ts/tsx/go/rust/java/c/cpp) with declaration/container/import/call type sets; aliases + extension map.
- `_is_local_value_declaration` performs the full ancestor walk for closures/arrow funcs/lambdas (`chunkers/code.py:506-550`) — the `f46bed0` fix is present.
- Malformed AST → `UnsupportedError` (`root.has_error`); atomic declaration > max → `UnsupportedError`; indistinguishable duplicate identities → `UnsupportedError`. Fail-closed throughout.
- **Corpus evidence:** `server.js` in the DB carries only two `lexical_declaration` chunks (the `require()` lines) — the corpus was built by the **pre-fix** pipeline and was never re-ingested after the fix (see §11, P0-1).

---

## 7. Phase 4 — Cleaner / Classifier / Canonicalizer

- Cleaner: type-dispatched; code/math NFC-only preserving newlines; prose whitespace-collapsed; header/footer suppression only for multi-page repetitive text; ordinals re-assigned. No information-loss boundary beyond intended header/footer dedup.
- Classifier: pure, deterministic, extension + heading heuristics; owns ADR-0036 slide metadata (`parser.slide.*`).
- Canonicalizer + `IngestionPipeline`: assets persisted (uuid5 content-addressed) before canonicalization; IR published to filesystem store; dedup short-circuits to existing IR (raises `IntegrityError` if the IR file is missing — which is exactly what the committed corpus triggers for two documents, §11).

---

## 8. Phase 5 — Chunker Contract & Silent-Loss Audit

All 9 chunkers reviewed. Loss mechanisms found:

| Mechanism | Location | Condition | Detected? | Verdict |
|---|---|---|---|---|
| Short-leaf removal (<15 tokens) | `dispatcher.py:88` | leaf drafts under 15 tokens dropped | by design; IntegrityError only if a short draft has children | **intended**, but contributes to silent reduction when upstream parsing is broken |
| Oversized atomic block | all chunkers | table/equation/slide/declaration > max | `UnsupportedError` — fail-closed | OK |
| `_reduce_text`/`_word_split` | generic.py | only splits; never drops | — | OK |
| Empty/alt-less image blocks | generic.py `_block_units` | `alt_text is None` → skipped | silent, by design | OK (no text to index) |
| Header/footer filter | cleaner.py | repeated text on >50% of pages | silent, by design | OK |
| **Catastrophic reduction upstream** | parser→chunker interface | broken parsing yields 1–2 declarations for a huge file | **NOT detected anywhere** — no plausibility invariant (P2-7, known and deferred) | **GAP — realized in the committed corpus (P0-1)** |
| `except Exception: pass` | `mcp/tools.py:447` (doc title lookup), `parsers/router.py:70` (magic fallback) | benign fallbacks | logged/none | P4 |

CSV partitioning: header repeated per partition; padding to max width; partition budget 400 est. tokens with 1024 hard max — **no partition can overflow**; row reconstruction is lossless (verified against corpus: 79 chunks, headers in every partition).

---

## 9. Phase 6 — Storage / Ingestion Integrity

Verified in code and against both databases:

- SQLite schema v4 with FK cascades, FTS5 external-content + AI/AD/AU triggers, WAL; transactions use `BEGIN IMMEDIATE`.
- Composite multi-backend write: projection build → snapshots → SQL write → Qdrant write with compensating rollback; deletes idempotent and retry-safe.
- Integrity measured on committed **and** local DB: orphan chunks **0**, orphan versions **0**, duplicate chunk IDs **0**, FTS↔chunks **1111 = 1111** in sync.
- Inconsistencies that **are** possible and **present**: lifecycle status can remain `indexing` forever after a crashed ingestion (committed Gita doc — P1-3); committed DB references parsed IR that is not committed (P1-2); direct manual DB edits bypass all compensators (the uncommitted local status flip proves this path is in use).

---

## 10. Phase 7 — Retrieval & MCP

- Retrieval stack implemented per ADR-0038–0048; version-aware sparse filters; deterministic RRF fusion; parent promotion; cross-encoder with pinned snapshot validation (license/activation/position checks).
- MCP: exactly 6 read-only tools; JSON schemas with bounds (top_k 1–100); strict UUID parsing → `ContractValidationError`; unknown IDs → `NotFoundError`; unknown tool → `ValueError`; stdio + SSE transports tested; security-isolation test asserts no mutation/exec tools. **Tool code verdict: PASS.**
- Gita retrieval verified by tests (Karma-yoga, BG 3.8/2.47 Sanskrit, negative unanswerable case) — sparse path works against the real corpus.
- **`reranker.py:489-578`**: `_detect_query_relevant_sources` embeds a `doc_signatures` dict keyed by the developer's personal filenames (`Atharv_Patil_RESUME_SDE.pdf`, `server.js`, `Y24_CPI.csv`, …) with hand-picked keywords (incl. a student name and roll number). The ADR-0048 "diversity-aware ordering" is therefore corpus-overfit production logic, not a general algorithm; for any other corpus only the `score ≥ 0.50` heuristic applies. **P1-6 (architecture violation + personal data in code).**

---

## 11. GOLDEN CORPUS CERTIFICATION (committed state at HEAD, cross-checked against working tree)

Identity contract: canonical IDs are UUIDv5 (deterministic); the six re-ingested docs' *source* rows are UUIDv4 (script-created) — documents/versions/notebook remain v5. Hard-coded test IDs (`test_mcp_golden_corpus.py:43-45`) match the DB. **Canonical-identity contract: PASS.**

| Document | Source OK | Hash OK | Identity OK | Indexed | Chunks OK | No Loss | FTS OK | Retrieval OK | Metadata OK | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| Bhagavad-gita-As-It-Is.pdf | ✔ | ✔ | ✔ v5 | **committed: `indexing`; local: `indexed` (uncommitted flip)** | 1000 ✔ | ✔ (1.28M chars) | ✔ | ✔ (tests) | ✔ pages/headings | **WARNING — lifecycle stuck in committed state (P1-3)** |
| server.js | ✔ | ✔ | ✔ v5 | ✔ (both) | **2 chunks / 121 chars of 59,851 B** | **FAIL — 99.8% loss** | sync but empty of real symbols | **FAIL — `validateWhisperOutput`, `startTelegramListener`, `pcmToWav`, `analyzeScreen` → 0 FTS hits (verified live)** | chunker meta consistent | **CRITICAL (P0-1)** |
| Y24_CPI.csv | ✔ | ✔ | ✔ v5 | ✔ | 79 ✔ | ✔ rows reconstructable | ✔ | ✔ | ✔ headers per partition | **FAIL — parsed IR `2190addb…ir.json` absent from repo AND disk (P1-2)** |
| Coordinator Application.pptx | ✔ | ✔ | ✔ v5 | ✔ | 20 ✔ (21 slides) | ✔ | ✔ | ✔ slide numbers | **PASS** (IR committed) |
| ME361_L1….pptx | ✔ | ✔ | ✔ v5 | ✔ | **1 chunk** | text present (3.9K chars) but boundaries lost | ✔ | partial | **IR: 42 blocks, all `page_number=None`, all `parser.slide.number=1` → whole deck collapsed to one slide — ADR-0036 violated in corpus (P1-4)** |
| ME333 LabReport.docx | ✔ | ✔ | ✔ v5 | ✔ | 6 ✔ | ✔ | ✔ | ✔ | **PASS** (IR committed) |
| Resume.pdf | ✔ | ✔ | ✔ v5 | ✔ | 3 ✔ | ✔ | ✔ | ✔ | **PASS** (IR committed) |

Additional corpus-state findings:
- `files/parsed/c42eccba/…ir.json` (server.js current version, referenced by **committed** DB) exists **only untracked** → clean checkout lacks it.
- `files/parsed/d16f586e/…ir.json` is an **orphan** IR with no DB row (debris of an abandoned re-ingestion).
- Consequence of P1-2: on a clean checkout, `CompositeStorage._build_retrieval_projection` for the CSV/server.js versions raises `IntegrityError("cannot index chunks without exact-version parsed IR")` — the committed corpus is not re-indexable from a fresh clone.

**Golden Corpus verdict: NOT CERTIFIABLE.** "All data is correctly indexed" is false for server.js; the corpus is a hybrid built by ad-hoc scripts (v4 source IDs, pre-fix parser output), not a product of the production pipeline.

---

## 12. Phase 8 — Release / Version Audit

- Active versions uniformly **0.23.0**: root, mnemo-core (`_version.py`), mnemo-server, email-ingestion plugin, mnemo-ui `package.json`, test assertions. **No stale active version strings found.** Historical 0.21/0.22 references are confined to changelog history (legitimate).
- **No `v0.23.0` git tag exists** (latest tag `v0.22.0`) despite changelog 0060 declaring the release (P2-11).
- Working tree is dirty in corpus state: modified `data/manual-gita-qa/mnemo.db`, untracked IR dirs, untracked `scratch_head.db`/`scratch_orig.db` at repo root (not gitignored — `scratch/` is, root-level scratch files are not), untracked stale `docs/audit_report.md`.

---

## 13. ADR Audit (33 ADRs inventoried; contradictions searched)

| ADR | Contract | Implementation | Tests | Status | Consistent? |
|---|---|---|---|---|---|
| 0001–0008 (domain, interfaces, config, engine, graph, dedup, images, sqlite…) | core contracts | ✔ | ✔ | Accepted (some superseded by later numbering per docs) | ✔ |
| 0011 raw parse boundary | transient RawBlocks, no identity in parsers | ✔ all parsers pure | ✔ | Accepted | ✔ |
| 0012 cleaner / 0013 classifier / 0014 canonicalization | pure boundaries | ✔ | ✔ | Accepted | ✔ |
| 0015 chunking V2 | drafts + dispatcher-owned identity | ✔ `compute_chunk_id` | ✔ | Accepted | ✔ |
| 0016/0017 email/resume boundaries | plugin/parser semantics | ✔ (email plugin) | ✔ | Accepted | ✔ |
| 0036 slides semantics | per-slide metadata, fail-closed grouping | ✔ code; **corpus ME361 IR violates per-slide intent** (all slides = 1) | ✔ unit | Accepted | ✔ code / **corpus violated** |
| 0037 documentation / 0038–0048 retrieval chain | deterministic fusion→citation | ✔ | ✔ | Accepted | ✔ **except** 0048 diversity (hard-coded signatures, P1-6) |
| 0049–0051 server/MCP REST | Layer-2 adapter | ✔ | ✔ | Accepted | ✔ |

No circular supersession; no implementation-evolved-without-ADR found beyond the reranker signature table (which contradicts ADR-0048's generality, P1-6). Numbering gaps (0007, 0009, 0010 as ADR files vs changelog numbering) are historical naming drift only.

---

## 14. Documentation / Governance

1. **Architecture v2 (`mnemo_architecture_v2.md`)**: baseline paragraph accurately describes Phases 0–8 complete, six MCP tools, disabled-backend semantics. Matches code. PASS.
2. **Roadmap (`mnemo_engineering_roadmap.md`)**: **internally contradictory** — header states "Current baseline: … Phase 5 Modules 5.1–5.3 are implemented … **Phase 6 has not started**" while the Phase 8 section states "Complete and certified at v0.23.0" (P2-9).
3. **Changelog 0060**: declares v0.23.0 released; tag missing (P2-11); test count 1,354 is historical-at-release vs 1,370 now (acceptable historical reference).
4. **`docs/audit_report.md` (untracked)**: stale on three counts — claims PPTX has "no built-in parser" (false since `f46bed0`), claims server.js re-ingested with 43 chunks (actual committed and local DB: **2**), reports 1,321 tests (now 1,370). Its §12 "prepared commit" was superseded by `f46bed0`. Treat as historical; do not rely on it (P1-5).
5. **README**: parsing table omits PPTX and CSV partitioning though both are implemented (P2-12); quality-gate commands differ from CI (no `--strict`, no plugins path in README example). Otherwise accurate; badges at 0.23.0.
6. **Governance (`PHASE_8_FINAL_RECONCILIATION_AUDIT.md`)**: claims "CERTIFIED & RELEASE-READY … fully consistent" and cites corpus-verifiable behaviors. Given P0-1/P1-2/P1-3/P1-4 in the *committed* corpus, the certification claim is **not supported by repository evidence** (P1-5).

---

## 15. Test Quality

- Strengths: contract-style tests; deterministic-identity tests; negative/malformed-input coverage per parser; MCP conformance, SSE, CLI, security-isolation tests; golden tests use canonical v5 IDs (restored per `f1b621e`) — reproducible from clean checkout (DB + assets committed).
- Weaknesses (all realized by this audit):
  - **No corpus plausibility test** — a 59 KB file indexed as 2 chunks/121 chars passes everywhere (P0-1 enabler).
  - **No lifecycle-status assertion** on corpus documents — `indexing` vs `indexed` both green (P1-3 enabler).
  - **No corpus completeness test** for parsed-IR presence (P1-2 enabler).
  - Golden tests `pytest.skip` when the DB is absent — silent skip path in degraded environments (P3-15).
  - Coverage gate margin is 0.46 pp.

---

## 16. CI/CD

`ci.yml`: ruff format+check, `mypy --strict` over all three packages, tokenizer provisioning, full pytest, three wheel builds, frontend (pnpm format/lint/typecheck/test/build), three Docker builds + compose config validation. Strong. Gaps: no security scanning (pip-audit/npm audit), no golden-corpus integrity job (see §15), validate.bat's mypy scope differs from CI (P3-14).

---

## 17. Security

- Blob store is content-addressed (`uuid5(sha256)`); no user-controlled path segments; atomic writes with Windows retry. No traversal.
- Upload endpoint streams with size cap (`routers/sources.py`).
- Auth: JWT with algorithm allow-list (HS256/384/512), constant-time compares, minimal exempt paths.
- MCP surface: read-only, UUID-validated, bounded — verified by tests.
- **P2-8**: PPTX/DOCX parsing uses `zipfile` + `xml.etree.ElementTree` with **no decompression-ratio/size caps** (zip bomb) and expat-based entity expansion (billion-laughs class) — acceptable for a local-first trusted-input tool, but a documented hardening gap.
- Committed `mnemo.toml` contains SurrealDB `root/root` defaults (local-only service; P4).

---

## 18. Performance / Scale (evidence-based, not benchmarked)

- `_handle_list_notebooks` performs N+1 `list_sources(limit=1000)` per notebook; `get_source_insights` fetches ≤1000 insights then filters in Python (P2-10).
- `CodeChunker` computes `called_by` via O(n²) cross-scan of declarations.
- SQLite has appropriate indexes; FTS external-content triggers avoid duplicate storage.
- 1,000-page Gita (1000 chunks) ingests and retrieves fine; corpus scale is tiny relative to the 20M-chunk architectural target (unbenchmarkable here — Phase 13).

---

## 19. Clean-Checkout Reproducibility

Install/build/test/MCP/quality-gates: **reproducible** (uv.lock + pnpm-lock committed and enforced `--locked`/`--frozen-lockfile`; CI proves it).
Corpus: **NOT fully reproducible** — committed DB references IR files absent from git (P1-2); golden tests exercise search fine (they never touch the missing IR), so CI stays green while the corpus remains incomplete. Local-state dependencies found: modified DB + untracked IR (working tree), root-level scratch DBs, committed `mnemo.toml` pointing at the QA corpus, empty local `architecture/` dir.

---

## 20. Master Evidence Matrix (condensed to decision-relevant rows)

| Area | Status | Evidence | Severity | Location |
|---|---|---|---|---|
| Golden Corpus content completeness | **CRITICAL** | server.js 59,851 B → 2 chunks/121 chars; 4/4 probed symbols 0 FTS hits | P0 | `data/manual-gita-qa/mnemo.db` (HEAD + local) |
| Corpus IR completeness | BUG | committed DB refs `2190addb`/`c42eccba` IRs; `2190addb` absent everywhere, `c42eccba` untracked | P1 | git ls-files vs documents table |
| Lifecycle integrity | BUG | Gita `indexing` at HEAD; local flip uncommitted; tests green both ways | P1 | documents.status |
| Slide semantics in corpus | BUG | ME361 IR: 42 blocks, all slide.number=1, page_number=None → 1 chunk | P1 | `files/parsed/52de3ce8/…ir.json` |
| Governance certification | INCONSISTENT | "fully consistent/release-ready" vs above | P1 | `docs/governance/PHASE_8_…`, `docs/audit_report.md` |
| ADR-0048 generality | INCONSISTENT | hard-coded personal `doc_signatures` | P1 | `retrieval/reranker.py:489-578` |
| Catastrophic-reduction invariant | WARNING | none exists; realized in corpus | P2 | dispatcher/pipeline |
| Zip/XML DoS surface | WARNING | no caps in pptx/docx parsing | P2 | `parsers/pptx.py`, `docx.py` |
| Roadmap header | INCONSISTENT | "Phase 6 has not started" vs Phase 8 certified | P2 | roadmap lines 20-27 |
| README formats | WARNING | PPTX/CSV-partitioning omitted | P2 | README capability table |
| MCP N+1 / Python filtering | PASS w/ CONCERN | capped at 1000 | P2 | `mcp/tools.py` |
| Release hygiene | WARNING | no v0.23.0 tag; root scratch DBs unignored | P2 | git tags / status |
| classifier/router extension mismatch | WARNING | `.sh/.yaml/...` classifiable but unroutable | P2 | `classifier.py:23` vs `engine.py:479` |
| Everything else (phases 0,1,2,5,7 code; MCP tools; versioning; CI; packaging) | PASS | see §3–§16 | — | — |

---

## 21. Critical Issue List

### P0 — Critical
1. **Committed Golden Corpus certifies near-total data loss as `indexed`.** `server.js` (sha256-verified against `goldenDataset/server.js`, 59,851 B) is indexed as 2 chunks totaling 121 characters (two `require()` lines). Live FTS probes: `validateWhisperOutput`/`startTelegramListener`/`pcmToWav`/`analyzeScreen` → **0 hits**; present in HEAD-committed **and** local DB. Root cause: corpus built by the pre-`f46bed0` parser; never re-ingested; no invariant detects it. The prior audit's contrary claim (43 chunks) matches no database that exists in the repository.

### P1 — High
2. **Committed corpus is not re-materializable**: DB references parsed IR `2190addb…` (Y24_CPI) that exists neither in git nor on disk, and `c42eccba…` (server.js) that exists only untracked; `CompositeStorage._build_retrieval_projection` raises `IntegrityError` for these versions on a clean checkout. Orphan IR `d16f586e…` has no DB row.
3. **Lifecycle status unguarded & committed-stuck**: Gita is `indexing` in the committed corpus; the local repair (`indexed`) is an uncommitted manual DB edit; the full suite is green against both states.
4. **ME361 deck violates ADR-0036 in the corpus**: all 42 blocks carry `page_number=None`/slide 1 → the entire lecture is a single chunk; semantic slide boundaries not preserved (Coordinator pptx, by contrast, has 21 proper slides).
5. **Governance/certification documents contradict repository evidence**: Phase-8 reconciliation audit ("CERTIFIED & RELEASE-READY … fully consistent") and the untracked `docs/audit_report.md` (claims: no PPTX parser; 43-chunk server.js) are both falsified by committed state.
6. **Hard-coded personal corpus signatures in production reranker** (`reranker.py:489-578`): ADR-0048 diversity ordering is overfit to the developer's personal documents; includes personal data (student name, roll number) in core code; behavior for any other corpus silently degrades to a score threshold.

### P2 — Medium
7. No catastrophic-reduction invariant (known, deferred, now realized as P0-1).
8. Zip-bomb / entity-expansion DoS surface in PPTX/DOCX parsing (no ratio/size caps; expat-based ET).
9. Roadmap header contradicts roadmap body (Phase 6 "not started" vs Phase 8 certified).
10. MCP `list_notebooks` N+1 source queries; `get_source_insights` over-fetches then filters in Python.
11. Release hygiene: no `v0.23.0` tag; untracked `scratch_head.db`/`scratch_orig.db` at root (unignored); stale untracked audit report.
12. README capability table omits implemented PPTX parser and CSV partitioning; README gate commands differ from CI.
13. Classifier `CODE_EXTENSIONS` advertises `.sh/.yaml/.yml/.toml/.ini/.css/.rb/.php` that no registered parser can route (UnsupportedError) — dead/misleading contract.

### P3 — Low
14. `validate.bat` / pre-commit / CI mypy scopes differ; `scripts/` verifiers not wired into CI.
15. Golden-corpus tests `pytest.skip` on missing DB (silent-skip risk).
16. `import fitz` deprecated alias in `pdf.py` (use `pymupdf`).
17. `.ppt` classified SLIDES but unparseable; governance test counts (1,354) vs current (1,370) drift; empty local `architecture/` directory.

### P4 — Informational
18. `list_sources`/`list_insights` hard cap 1000 inside MCP tools (silent truncation beyond).
19. `except Exception: pass` around document-title lookup in `get_notebook_summary` (benign fallback).
20. SurrealDB `root/root` defaults committed in `mnemo.toml` (local-only service).
21. Coverage margin over gate is 0.46 pp.

---

## 22. Mandatory Findings Categories — Answers

1. **Architecture consistency:** PASS except reranker signature table (P1-6). 2. **ADR consistency:** PASS except ADR-0036 violated *in corpus data* (P1-4) and ADR-0048 generality (P1-6). 3. **Governance consistency:** FAIL (P1-5). 4. **README consistency:** PASS WITH CONCERN (P2-12). 5. **Changelog consistency:** PASS (historical counts acceptable). 6. **Roadmap consistency:** FAIL (P2-9). 7. **Code correctness:** PASS (post-`f46bed0`). 8. **Test correctness:** PASS execution / FAIL protection power (§15). 9. **Golden Corpus correctness:** FAIL (P0-1, P1-2/3/4). 10. **Database integrity:** structural PASS / lifecycle FAIL. 11. **Chunking correctness:** code PASS; corpus FAIL. 12. **Parser correctness:** PASS (PPTX real; minor gaps P3/P2-13). 13. **Retrieval correctness:** PASS for indexed content; server.js unretrievable (P0-1). 14. **MCP correctness:** PASS. 15. **Packaging correctness:** PASS. 16. **CI correctness:** PASS with gaps (§16). 17. **Security:** PASS WITH CONCERN (P2-8). 18. **Performance:** PASS at current scale; N+1 notes. 19. **Reproducibility:** code PASS / corpus FAIL. 20. **Documentation accuracy:** PASS WITH CONCERN. 21. **Version consistency:** PASS (0.23.0 uniform; tag missing P2-11). 22. **Git hygiene:** WARNING (dirty corpus state, root scratch files). 23. **Technical debt:** reranker overfit; deferred invariant; scratch-script-built corpus. 24. **Remaining ambiguities:** why the corpus was rebuilt post-audit with the pre-fix parser; whether the Gita status flip was authorized. 25. **Remaining risks:** any future ingestion reproducing P0-1 silently until an invariant exists.

---

## 23. FINAL VERDICT

# MNEMO PHASE 0–8 AUDIT — BLOCKED BY P0/P1 FINDINGS

- **Total findings:** 21 (numbered above) · **P0: 1** · **P1: 5** · **P2: 7** · **P3: 4** · **P4: 4**
- **Phases requiring attention:** Phase 3/4 (corpus re-ingestion through the *current* pipeline), Phase 8 (governance retraction/amendment, tag), Phase 6 (reranker generalization).
- **Golden Corpus verdict:** NOT CERTIFIABLE — 1 of 7 documents catastrophically reduced and empirically unretrievable; corpus IR incomplete in git; lifecycle stuck in committed state.
- **Architecture verdict:** PASS WITH CONCERN (one corpus-overfit production module).
- **ADR verdict:** PASS (violations are in data and one module, not in the contracts).
- **Documentation verdict:** PASS WITH CONCERN (roadmap header, README formats).
- **Production-quality verdict (code):** PASS. **(corpus/governance):** FAIL.
- **Reproducibility verdict:** code PASS / corpus FAIL.
- **MCP verdict:** PASS (tool surface, schemas, transports, security isolation all verified).

**Blocking path to re-certification (report only — nothing was modified):** re-ingest server.js, Y24_CPI.csv, and ME361 through the current production pipeline (which demonstrably produces 79-chunk CSV partitions and 21-slide PPTX structure), commit the resulting IR files, resolve the Gita lifecycle status through the pipeline rather than a manual edit, add corpus plausibility/IR-presence/lifecycle-status test invariants, generalize the reranker's source-relevance detection, correct the roadmap header and README table, tag v0.23.0 — then re-run this audit.
