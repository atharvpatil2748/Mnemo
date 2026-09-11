# Changelog: Phase 8.5.11 — Full Evaluation, Model Benchmarking, and Production Profile Governance

- **Release Date:** 2026-08-26
- **Module:** Phase 8.5.11 (Evaluation & Model Certification)
- **Baseline:** v0.25.0
- **Governing ADRs:** ADR-0058 through ADR-0071

---

## 1. Overview

Phase 8.5.11 delivers the complete evaluation, clean-room production ingestion verification, hardware benchmarking of candidate model families, and governance for Mnemo's advanced multimodal and multilingual retrieval foundations.

---

## 2. Key Accomplishments

### A. Clean Production Ingestion & Deep Image Census
- **Corpus Scope:** 44 isolated evaluation documents (192.6 MB) spanning PDF, PPTX, DOCX, XLSX, CSV, JS, PY, Markdown, HTML, text, and standalone images.
- **Deep Image Audit:** Full byte-level extraction verified **464 total image occurrences** across 11 container documents and 8 standalone image files, resolving to **434 distinct cryptographic SHA-256 binaries**.
- **Ingestion Truth:** 2,658 canonical chunks, 2,658 SQLite FTS5 rows, 2,658 title projections, 0 duplicate/orphan occurrence records.

### B. Hardware Model Benchmarking (Intel i7-13700HX + RTX 4060 8GB)
- **Multilingual Embeddings:**
  - `BAAI/bge-m3` (1024-dim, 560M params) — **Winner / Production Default** (MRR 0.898, nDCG 0.924).
  - `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384-dim, MRR 0.764).
  - `intfloat/multilingual-e5-small` (384-dim, MRR 0.787).
- **Multilingual Rerankers:**
  - `BAAI/bge-reranker-v2-m3` — **Winner / Production Default** (MRR 0.926, nDCG 0.941; resolved title-disambiguation conflicts).
  - `PMJAi/bert-base-multilingual-cased-reranker` (MRR 0.822).
  - `PMJAi/distilbert-base-multilingual-cased-sl_200-reranker` (MRR 0.796).
- **Visual Embeddings:**
  - `openai/clip-vit-large-patch14` (768-dim) — **Winner / Production Default** (MRR 0.881).
  - `openai/clip-vit-base-patch32` (512-dim, MRR 0.655).
  - `openai/clip-vit-base-patch16` (512-dim, MRR 0.774).
- **Vision-Language Model (VLM) Research & Benchmark:**
  - Identified 100% visual blindness defect in `gemma4:e4b` ("No image was provided").
  - Executed 14-image local benchmark:
    - `qwen2.5vl:latest` (8.3B Q4_K_M) — **58.5 / 60.0 (97.5%) — Winner / Recommended Default** (verbatim multi-script OCR, zero visual hallucinations, stable 5.3 GB VRAM footprint).
    - `llava:7b` (36.5 / 60.0 — failed Devanagari, hallucinated machinery on line drawings).
    - `llama3.2-vision:11b` (0.0 / 60.0 — crashed Ollama Windows runtime on mllama architecture).

### C. Storage Topology & Model Isolation
- Established external, non-volatile model storage on D: drive:
  - `D:\Ollama\models` with persistent `OLLAMA_MODELS` environment variable and NTFS directory junction `C:\Users\athar\.ollama\models <<===>> D:\Ollama\models`.
  - `D:\Mnemo\phase8.5.11-models\` for Hugging Face transformer caches and Tesseract language data.
- Configured additive production profiles in `phase8_5_models.toml`.

### D. Software Quality Gates
- **Server API & MCP Tests:** 258 passed (100% PASS).
- **Static Analysis:** Ruff linter & formatter 100% clean across 309 files.
- **Type Safety:** Strict mypy 100% clean across 187 source files.
- **Builds:** 3 distribution packages (`mnemo-core`, `mnemo-server`, `mnemo-email-ingestion`) built in `dist/`.
- **Golden Corpus Integrity:** Certified 15-document baseline verified completely untouched.
