# M4 Bhagavad Gita Golden-Corpus Verification

**Verdict:** PASS
**Executed:** 2026-08-13 06:07:57 UTC
**Mnemo:** v0.20.1 (`cdf598c0fc22bce74784586e871f7aa014a5c658`)
**Platform:** Windows 11, Python 3.12.10, Intel64 Family 6 Model 183

## Dataset and production path

- File: `goldenDataset/Bhagavad-gita-As-It-Is.pdf`
- Size: 66,135,830 bytes
- SHA-256: `ff112b0b056d303b792f6f2e68cbd73a89adf612fa9113f932446cdea7741583`
- Physical pages (PyMuPDF): 952
- Parser metadata pages: 952
- Encryption: none
- Path: `ParserRouter → PDFParser → DocumentCleaner → DocumentClassifier → DocumentCanonicalizer → ChunkerDispatcher → BookChunker`
- Canonical tokenizer: frozen offline `o200k_base` adapter from ADR-0015
- Chunk settings: target 400, configured maximum 500, effective maximum 500 tokens

The parser produced 6,512 canonical blocks, 69 extracted assets, and 95
`HeadingBlock` values. The classifier selected `DocType.BOOK` without a test
override. The registry resolved the production `BookChunker` through the V2
dispatcher slot.

## Hierarchy result

The final output contains 1,275 chunks. All are roots because the released
`BookChunker` explicitly advertises `supports_parent_child=False`; ADR-0015
allows such a strategy to emit multiple roots and forbids the dispatcher from
fabricating parent chunks. Authored hierarchy is carried by `heading_path`.

- Roots: 1,275
- Maximum `heading_path` depth: 3
- Chunks with a chapter path: 1,167
- Front/back-matter chunks: 108
- Empty `heading_path`: 0
- Invalid parents: 0
- Invalid sibling families: 0
- Chapter-boundary violations: 0
- Invalid source provenance: 0
- Invalid source-derived text: 0
- Short final chunks: 0
- Oversized final chunks: 0

Representative real extracted paths:

```text
Bhagavad-gita As It Is with pics!
  → CHAPTER ONE
    → Observing the Armies on the Battlefield of Kurukṣetra

Bhagavad-gita As It Is with pics!
  → CHAPTER ELEVEN
    → The Universal Form

Bhagavad-gita As It Is with pics!
  → CHAPTER EIGHTEEN
    → Conclusion—The Perfection of Renunciation
```

| Authored boundary | Chunks |
|---|---:|
| Front/back matter | 108 |
| CHAPTER ONE | 56 |
| CHAPTER TWO | 133 |
| CHAPTER THREE | 73 |
| CHAPTER FOUR | 82 |
| CHAPTER FIVE | 50 |
| CHAPTER SIX | 80 |
| CHAPTER SEVEN | 73 |
| CHAPTER EIGHT | 45 |
| CHAPTER NINE | 76 |
| CHAPTER TEN | 70 |
| CHAPTER ELEVEN | 79 |
| CHAPTER TWELVE | 35 |
| CHAPTER THIRTEEN | 61 |
| CHAPTER FOURTEEN | 41 |
| CHAPTER FIFTEEN | 41 |
| CHAPTER SIXTEEN | 41 |
| CHAPTER SEVENTEEN | 34 |
| CHAPTER EIGHTEEN | 97 |

## Determinism and performance

The same canonical 952-page document was dispatched twice with the same
document/version identity. Chunk count, IDs, text, source spans, heading paths,
parent IDs, and sibling tuples were identical.

| Stage | Seconds |
|---|---:|
| Parse/router | 21.117 |
| Clean | 18.815 |
| Classify | 0.001 |
| Asset persistence | 0.209 |
| Canonicalize | 0.014 |
| Chunk | 1.483 |
| Repeat chunk | 1.526 |
| Ingestion-to-chunks | 41.637 |

The roadmap target is **1,000 pages chunked in under 10 seconds**. The measured
document has 952 pages, not 1,000. Linear normalization of chunking alone is
1.557 seconds per 1,000 pages, so the measured run satisfies the target without
misstating the corpus size. Parsing and cleaning are reported separately and
are not part of that chunker-only target.

## Failures found and fixed

1. The classifier recognized numeric chapters but not the corpus's real
   `CHAPTER ONE` through `CHAPTER EIGHTEEN` headings. The classifier and
   BookChunker now accept common word-numbered chapters.
2. The PDF ToC uses `Table of Contents with clickable chapter links:` and
   `CHAPTER …! page` syntax. ToC detection now recognizes and excludes that
   source form.
3. Decorative images with no alt text occur between chapter labels and visual
   chapter titles. They previously ended pending hierarchy and allowed a title
   to replace its chapter. Non-emitting decorative images now preserve that
   source hierarchy.
4. The SurrealDB 2.x dependency exposes its asynchronous lifecycle through
   `AsyncSurreal` websocket connections. `SurrealDBStore` now adapts the frozen
   HTTP(S) configuration URL to the async WS(S) backend boundary.

Each fix has a focused regression test. No frozen Chunk contract or Phase 6
functionality was changed.

## Reproduction

```powershell
docker compose -f docker/docker-compose.yml up -d --wait qdrant surrealdb
.venv\Scripts\python.exe scripts/verify_phase_4_5_milestones.py m4
```

Machine-readable evidence is in
`docs/milestone-evidence/m4-bhagavad-gita.json`.
