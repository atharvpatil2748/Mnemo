# ADR-0070: Phase 8.5 Evaluation and Certification Governance

- **Status:** Accepted
- **Implementation:** Complete — Candidate Benchmarks Governed & Production Profiles Selected
- **Date:** 2026-08-24 (Updated 2026-08-26)
- **Extends:** ADR-0010 and existing Phase 0–8 governance
- **Supersedes:** Nothing

## Context

Multimodal, structured, exhaustive, multilingual, job, and binary-delivery
claims need evidence beyond unit tests and the frozen 15-document corpus.

## Problem

Changing the certified corpus or selecting models by marketing claims would
hide regressions and make completeness/language assertions unverifiable.

## Decision

Preserve the Phase 0–8 Golden Corpus and its baselines. Add a versioned Phase
8.5 evaluation pack containing synthetic/adversarial and distributable
fixtures: standalone images, scanned PDFs, image-rich PDF/PPTX/DOCX/XLSX,
tables with known aggregates, positional/page/slide cases, multilingual
English/Hindi/Marathi and cross-language pairs, duplicate images, malicious
containers, and bounded full-document cases.

Each fixture has a machine-readable expectation manifest covering identities,
structure, provenance, retrieval targets, completeness, aggregates, citation
evidence, authorization, resource budgets, and permitted nondeterminism.
Provider/model profiles are certified per hardware/trust configuration and
language direction. Unmeasured capability is `UNVALIDATED`, never PASS.

Gates require Phase 0–8 regression, migrations, assets/extraction, jobs,
OCR/VLM/vectors, advanced retrieval/completeness, structured results,
multilingual metrics, Final QA V2 replay, HTTP/MCP, security, performance/cost,
quality/builds, documentation, and actual CI.

## Alternatives

- Expand/replace the Golden Corpus: rejected because frozen evidence must stay
  comparable.
- One aggregate quality score: rejected because it hides weak modalities and
  language directions.
- Mock-only certification: rejected for provider and protocol behavior.

## Consequences

Certification is more expensive but claims are reproducible and scoped. Model
changes require targeted recertification and regression.

## Compatibility

Existing tests, coverage gate, Golden Corpus, and release governance remain.
The Phase 8.5 pack is additive and independently versioned.

## Migration

No runtime migration. Fixture licenses, hashes, manifests, and expected results
are reviewed before inclusion.

## Security implications

Fixtures contain no real secrets/personal data, malicious samples are safely
stored/isolated, and cloud evaluation requires consent/budget controls.

## Testing requirements

The decision itself requires manifest-schema validation, deterministic fixture
builds, mutation tests, benchmark repeatability, false-completeness negatives,
and CI/local parity.

## Observability

Publish profile IDs, metrics, sample counts, confidence intervals where useful,
hardware, model revisions, failures, and gate evidence; no source contents.

## Rollback/recovery

Withdraw a faulty evaluation-pack version without changing historical reports;
affected capability returns to `UNVALIDATED`.

## Future-phase impact

Phases 9–13 inherit capability/profile evidence and add UI, reasoning, plugin,
and production-scale cohorts without rewriting Phase 8.5 history.

## Explicit non-goals

This ADR does not set arbitrary quality numbers before baselines are measured.

## Current evaluation status

The Phase 8.5.11 local evaluation provisioned and benchmarked three multilingual
embedding candidates (`BAAI/bge-m3`, `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`,
`intfloat/multilingual-e5-small`), three multilingual reranker candidates
(`BAAI/bge-reranker-v2-m3`, `PMJAi/bert-base-multilingual-cased-reranker`,
`PMJAi/distilbert-base-multilingual-cased-sl_200-reranker`), and three visual embedding
candidates (`openai/clip-vit-large-patch14`, `openai/clip-vit-base-patch32`,
`openai/clip-vit-base-patch16`).

Hardware benchmarks identified:
- **Multilingual Embedding Winner:** `BAAI/bge-m3` (1024-dim, 560M params)
- **Multilingual Reranker Winner:** `BAAI/bge-reranker-v2-m3`
- **Visual Embedding Winner:** `openai/clip-vit-large-patch14` (768-dim)
- **VLM Grounding Winner:** `qwen2.5vl:latest` (8.3B Q4_K_M, 97.5% score on 14-image benchmark with 100% grounding, verbatim multi-script OCR, diagram comprehension, stable 5.3 GB VRAM footprint) replacing the failed `gemma4:e4b` model (which exhibited 100% visual blindness).

Production defaults are pinned in `phase8_5_models.toml` and model assets are stored on the dedicated D: drive (`D:\Mnemo\phase8.5.11-models` and `D:\Ollama\models`). Complete evidence is recorded in `../governance/PHASE_8_5_11_EVALUATION_REPORT.md` and `../governance/VLM_MODEL_SELECTION_INDEPENDENT_BENCHMARK.md`.
