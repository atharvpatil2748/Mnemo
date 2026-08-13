# Phase 4–5 Milestone Verification

**Date:** 2026-08-13
**M4:** VERIFIED
**M5:** VERIFIED
**Release created:** NO

## Acceptance summary

| Milestone | Real acceptance evidence | Verdict |
|---|---|---|
| M4 | 952-page Bhagavad Gita → production parser/cleaner/classifier/canonicalizer/dispatcher/BookChunker → 1,275 deterministic chunks, all 18 chapters, zero hierarchy/provenance violations | PASS |
| M5 | First 1,000 real M4 chunks → cache/Ollama (`nomic-embed-text`, 768d) → CompositeStorage/QdrantStore → 1,000-point independent read-back | PASS |

Detailed reports:

- `docs/milestone-m4-bhagavad-gita-report.md`
- `docs/milestone-m5-ollama-qdrant-report.md`
- `docs/milestone-evidence/m4-bhagavad-gita.json`
- `docs/milestone-evidence/m5-ollama-qdrant.json`

## Implementation corrections

- Expanded BOOK/chapter recognition to real word-numbered chapter headings.
- Recognized the golden PDF's clickable ToC syntax.
- Preserved chapter-title hierarchy across decorative, non-emitting images.
- Updated the SurrealDB backend to the installed async client lifecycle while
  retaining the public HTTP(S) configuration contract.
- Added focused regressions and an opt-in real-service pytest acceptance test.
- Added `scripts/verify_phase_4_5_milestones.py` as the repeatable evidence runner.

No Chunk redesign, named vectors, Module 5.4, retrieval, or other Phase 6 work
was introduced.

## Verification gates

| Gate | Result |
|---|---|
| Focused regressions | 48 passed, 1 live test skipped by default |
| Full pytest | 762 passed, 1 skipped |
| Coverage | 90.11% (required 90%) |
| `ruff format --check .` | PASS — 136 files formatted |
| `ruff check .` | PASS |
| Scoped strict mypy used by pre-commit | PASS |
| Raw `mypy .` | Existing unrelated `scratch/test_docx_images.py` annotations fail; changed production/acceptance files pass |
| `pre-commit run --all-files` | PASS |
| Core/server package builds | PASS |
| `twine check` for v0.20.1 artifacts | PASS |
| UI production build | PASS |
| Remote CI | NOT RUN |

Pytest emitted an ignored Windows temp-directory cleanup warning after its zero
exit code; test and coverage results were already complete and successful.

## Commands

```powershell
.venv\Scripts\python.exe scripts/verify_phase_4_5_milestones.py all
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.venv\Scripts\ruff.exe format --check .
.venv\Scripts\ruff.exe check .
.venv\Scripts\pre-commit.exe run --all-files
uv build --package mnemo-core
uv build --package mnemo-server
.venv\Scripts\python.exe -m twine check dist/mnemo_core-0.20.1* dist/mnemo_server-0.20.1*
pnpm --dir mnemo-ui build
```

## Performance criteria

- M4 1,000-page chunking target: PASS by measured 952-page run; 1.483 seconds
  actual and 1.557 seconds linearly normalized to 1,000 pages.
- M5 mandatory 1,000-chunk milestone: PASS at 27.280 seconds and 36.66 chunks/s.
- Phase 5 10,000-chunk/5-minute benchmark: **NOT EXECUTED**, because only real
  corpus chunks were permitted and the corpus produced 1,275 chunks.

## Historical release status

The implementation baseline remains v0.20.1. This verification does not move
or alter v0.19.0, v0.20.0, or v0.20.1 and does not create a version, tag,
release, or pull request.
