# Comprehensive retrieval-quality recovery report

Completed 2026-09-04T15:08:40.428166+00:00. Verdict: **FAIL — production-quality evaluation validity gates**. All 176 raw cohort records recovered/completed; this is not a claim of universally failed retrieval.

## A. Environment / configuration

{
  "database": "C:\\Users\\athar\\Desktop\\Mnemo\\data\\canonical_production\\mnemo_canonical.db",
  "database_sha256": "dc9e7fa2d1cb77f0e42ec3220377f74b1e2f98842acbfe487d1c7e6502fb2ada",
  "original_runner_sha256": "f6a1fd8befa87a14fdb3e701436e9d195775b9f20a686ff67c294ec8a64a59d3",
  "runtime_versions": {
    "python": "3.12.10 (tags/v3.12.10:0cc8128, Apr  8 2025, 12:21:36) [MSC v.1943 64 bit (AMD64)]",
    "platform": "Windows-11-10.0.26200-SP0",
    "packages": {
      "torch": "2.13.0",
      "transformers": "5.15.1",
      "sentence-transformers": "5.7.0",
      "numpy": "2.5.1",
      "mnemo-core": "0.25.0",
      "mnemo-server": "0.25.0",
      "httpx": "0.28.1"
    },
    "git_head": "31cdfb179a15fd96153071373641d24af0b815ed",
    "ollama_version": {
      "version": "0.33.2"
    },
    "ollama_tags": [
      {
        "name": "gemma4:e4b",
        "model": "gemma4:e4b",
        "modified_at": "2026-05-08T19:25:00.7543168+05:30",
        "size": 9608350718,
        "digest": "c6eb396dbd5992bbe3f5cdb947e8bbc0ee413d7c17e2beaae69f5d569cf982eb",
        "details": {
          "parent_model": "",
          "format": "gguf",
          "family": "gemma4",
          "families": [
            "gemma4"
          ],
          "parameter_size": "8.0B",
          "quantization_level": "Q4_K_M"
        },
        "capabilities": [
          "completion",
          "tools",
          "thinking"
        ]
      }
    ]
  },
  "config_sha256": "7d94649efe9540eac1abfc197769c0875f48161d4c9ec191b73560e97d499083",
  "embedding_artifact_sha256": "ff0b64210a6a2f3aa513879cc76e8fd7aaf426333678b83969eb3918daeb4693",
  "embedding_model": "BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181",
  "production_reranker": "cross-encoder/ms-marco-MiniLM-L6-v2@233902d25c440f23af6f7d6e94d2946bac0bee0a",
  "candidate_reranker": "BAAI/bge-reranker-v2-m3@953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
  "reranker_batch_size": 16,
  "top_k_candidates": 25,
  "rrf_k": 60,
  "inference_device": "cpu",
  "extractor": "ollama/gemma4:e4b",
  "compression_builder_hard_max": 200,
  "compression_evidence_hard_max": 120
}

Original PID21808 exited after checkpoint DQ41. No expensive completed cohort was restarted. Only DQ42–DQ70 were reranked. Ollama compression was run once on the original 12 selected canonical chunks, then unloaded before resuming CPU reranking. Windows event2004 recorded low virtual memory during overlap; exact process exit cause is not conclusively established.

Recovery wall time since first successful checkpoint: 5270.3 seconds. Compression measured call time: 71.777 seconds. This is measured elapsed time, not an ETA.

## B. Corpus integrity

5506 protected files compared byte-for-byte: unchanged. Canonical DB SHA-256: `dc9e7fa2d1cb77f0e42ec3220377f74b1e2f98842acbfe487d1c7e6502fb2ada`. Golden Dataset, manuscript.pdf, Ramayana, canonical index and hashed model snapshots were not modified by recovery. Full hashes are in the before/after JSON manifests.

Earlier 13:30 forensic DB hash differs from recovery-start bytes; DB mtime was 13:32, before original 16:40 runner. Recovery interval proven unchanged; full pre-Antigravity interval not proven.

Current read-only integrity audit: 67 documents, 67 versions, 68 notebook source memberships, 4026 chunks. Notebook-scoped totals may double-count the one shared document. No source/corpus/qrel/model change was made.

## C. Evaluation dataset/query inventory

Phase8.5:18 queries ×2 rerankers. Phase8.6:70 queries ×2 rerankers. All expected IDs present exactly once per cohort; query text unchanged. Results contain 176 records. Three Phase8.5 and 55 Phase8.6 query targets cannot match exactly one stored title; they are INVALID_EVALUATION_CASE/PROVENANCE_METADATA for quality attribution, not corpus-absence evidence.

No corrected qrels or metric substitutions were silently applied. Raw metrics below retain the original flawed title-match definition. The separately labelled unique-title subset is a sensitivity analysis, not a replacement full-corpus benchmark.

## D. Overall retrieval metrics

| Cohort | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| production | 88 | 0.1818 | 0.2159 | 0.2614 | 0.2048 | 0.2159 |
| candidate | 88 | 0.2386 | 0.3068 | 0.3068 | 0.2617 | 0.2728 |

Raw title-match diagnostics only. Production/candidate are separate 88-query populations, not 176 independent queries. Recall confidence intervals are stored in JSON; MRR is top25 reciprocal rank. nDCG@10 uses a single document target rather than graded evidence labels.

Supplemental identity-corrected R@1 salvage (same original filename judgments resolved through existing manifest SHA256, not modified qrels):

{
  "phase_8_5_production": {
    "n": 18,
    "recall_at_1": 0.5,
    "note": "Salvaged from persisted top1 chunk IDs and existing source-manifest hash identities. R@5/R@10/MRR/nDCG cannot be fully corrected because original full rankings were not retained. No inference or qrel change."
  },
  "phase_8_5_candidate": {
    "n": 18,
    "recall_at_1": 0.8888888888888888,
    "note": "Salvaged from persisted top1 chunk IDs and existing source-manifest hash identities. R@5/R@10/MRR/nDCG cannot be fully corrected because original full rankings were not retained. No inference or qrel change."
  },
  "phase_8_6_production": {
    "n": 70,
    "recall_at_1": 0.2714285714285714,
    "note": "Salvaged from persisted top1 chunk IDs and existing source-manifest hash identities. R@5/R@10/MRR/nDCG cannot be fully corrected because original full rankings were not retained. No inference or qrel change."
  },
  "phase_8_6_candidate": {
    "n": 70,
    "recall_at_1": 0.2714285714285714,
    "note": "Salvaged from persisted top1 chunk IDs and existing source-manifest hash identities. R@5/R@10/MRR/nDCG cannot be fully corrected because original full rankings were not retained. No inference or qrel change."
  }
}

## E. Phase 8.5 metrics

| Cohort | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| phase_8_5_production | 18 | 0.4444 | 0.5556 | 0.6111 | 0.5018 | 0.5209 |
| phase_8_5_candidate | 18 | 0.7222 | 0.7778 | 0.7778 | 0.7500 | 0.7573 |

## F. Phase 8.6 metrics

| Cohort | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| phase_8_6_production | 70 | 0.1143 | 0.1286 | 0.1714 | 0.1285 | 0.1374 |
| phase_8_6_candidate | 70 | 0.1143 | 0.1857 | 0.1857 | 0.1362 | 0.1483 |

## G. Language-wise metrics

Directions are existing query-pack labels, not inferred document languages. Exact-title target failures contaminate these numbers. No language is certified or declared unsupported.

### phase_8_5_production

| Cohort | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| en->en | 5 | 0.8000 | 0.8000 | 0.8000 | 0.8000 | 0.8000 |
| en->mr | 1 | 0.0000 | 1.0000 | 1.0000 | 0.5000 | 0.6309 |
| hi->en | 5 | 0.2000 | 0.2000 | 0.4000 | 0.2446 | 0.2631 |
| hi->mr | 1 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| mr->en | 5 | 0.2000 | 0.4000 | 0.4000 | 0.2618 | 0.2861 |
| mr->mr | 1 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

Format breakdown:

| Cohort | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| .csv | 3 | 0.3333 | 0.6667 | 1.0000 | 0.4583 | 0.5820 |
| .js | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| .pdf | 9 | 0.4444 | 0.5556 | 0.5556 | 0.5174 | 0.5145 |
| .pptx | 3 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

### phase_8_5_candidate

| Cohort | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| en->en | 5 | 0.6000 | 0.8000 | 0.8000 | 0.7000 | 0.7262 |
| en->mr | 1 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| hi->en | 5 | 0.8000 | 0.8000 | 0.8000 | 0.8000 | 0.8000 |
| hi->mr | 1 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| mr->en | 5 | 0.6000 | 0.6000 | 0.6000 | 0.6000 | 0.6000 |
| mr->mr | 1 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

Format breakdown:

| Cohort | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| .csv | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| .js | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| .pdf | 9 | 0.7778 | 0.8889 | 0.8889 | 0.8333 | 0.8479 |
| .pptx | 3 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

### phase_8_6_production

| Cohort | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| en->en | 8 | 0.2500 | 0.3750 | 0.3750 | 0.3125 | 0.3289 |
| en->hi | 15 | 0.1333 | 0.1333 | 0.2000 | 0.1496 | 0.1571 |
| en->mr | 15 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| hi->hi | 15 | 0.2667 | 0.2667 | 0.4000 | 0.2833 | 0.3087 |
| mr->mr | 17 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

Format breakdown:

| Cohort | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| .csv | 1 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| .docx | 1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| .html | 34 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| .json | 1 | 0.0000 | 1.0000 | 1.0000 | 0.5000 | 0.6309 |
| .md | 1 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| .pdf | 28 | 0.2143 | 0.2143 | 0.3214 | 0.2319 | 0.2495 |
| .pptx | 2 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| .xlsx | 2 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

### phase_8_6_candidate

| Cohort | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| en->en | 8 | 0.2500 | 0.3750 | 0.3750 | 0.2917 | 0.3125 |
| en->hi | 15 | 0.1333 | 0.2667 | 0.2667 | 0.1667 | 0.1908 |
| en->mr | 15 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| hi->hi | 15 | 0.2667 | 0.4000 | 0.4000 | 0.3133 | 0.3345 |
| mr->mr | 17 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

Format breakdown:

| Cohort | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| .csv | 1 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| .docx | 1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| .html | 34 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| .json | 1 | 0.0000 | 1.0000 | 1.0000 | 0.3333 | 0.5000 |
| .md | 1 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| .pdf | 28 | 0.2143 | 0.3571 | 0.3571 | 0.2571 | 0.2814 |
| .pptx | 2 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| .xlsx | 2 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

Unique-title-target subset only (not corrected whole-corpus quality):

| Cohort | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| phase_8_5_production | 15 | 0.5333 | 0.6667 | 0.7333 | 0.6021 | 0.6251 |
| phase_8_5_candidate | 15 | 0.8667 | 0.9333 | 0.9333 | 0.9000 | 0.9087 |
| phase_8_6_production | 15 | 0.5333 | 0.6000 | 0.8000 | 0.5996 | 0.6412 |
| phase_8_6_candidate | 15 | 0.5333 | 0.8667 | 0.8667 | 0.6356 | 0.6919 |

## H. Multimodal metrics

619 visual embedding rows, 619 OCR derivations, 619 Vision derivations; 620 occurrences and 589 unique catalog assets. Every examined row has consistent occurrence/asset/document/version/derivation linkage. One occurrence lacks all three representations; its exact identity is preserved in the audit JSON. This is not 100% representation coverage.

CLIP-versus-OCR-versus-Vision retrieval quality: **NOT_MEASURED**. Original runner retrieves text NPZ/FTS chunks, not independent multimodal sources. Image-derived combined text does not prove a visual route succeeded. No OCR/Vision/CLIP inference was rerun.

## I. Reranker analysis

Both model revisions and original batch16 are recorded. The same contextual text renderer is used, but full application parity fails. Raw cohort changes are paired on existing queries, yet title mismatch prevents a reliable full quality conclusion. No human decisive-pair labels exist here; pairwise reranker accuracy remains UNVERIFIED.

## J. ContextBuilder statistics

Original cohort E2E:10 attempted,0 completed. All fail constructing evidence=() before ContextBuilder; not a compression success/failure denominator. Historical logs verify all-verbatim inclusion, compression-failure omission, tight-budget omission, and fixed-overhead fail-closed behavior. Earlier logs calling graceful omission a compression PASS are not accepted as compression success.

Current controlled12-target builds: 1 target included compressed; 3 valid summaries omitted by budget; 2 failed compressions followed by graceful omission; 6 builds aborted. Successful prefix VERBATIM items are distinct from compression success.

## K. Compression statistics

{
  "n": 12,
  "attempts": 12,
  "successes": 4,
  "failures": 8,
  "compression_attempt_rate": 1.0,
  "compression_success_rate": 0.3333333333333333,
  "compression_failure_rate": 0.6666666666666666,
  "compression_omission_rate": 0.16666666666666666,
  "compression_omission_definition": "Failed compression followed by observed ContextBuilder omission / compression attempts; aborted builds are not graceful omissions.",
  "failed_compression_omissions": 2,
  "successful_compression_budget_omissions": 3,
  "included_compressed": 1,
  "strict_token_reduction_successes": 1,
  "success_definition": "Schema/semantic-text/token contract accepted, not an independent factual-quality judgment. Inclusion and strict token reduction are reported separately.",
  "aborted_builds": 6,
  "total_call_seconds": 71.77713969999786,
  "failure_types": {
    "HTTPStatusError": 1,
    "ValueError": 5,
    "graceful_validation_omission": 2
  }
}

Attempt rate denominator=12 targets. Success/failure/failed-compression omission rates denominator=12 attempts. Schema validity, output-token counts, errors and retained semantic summaries are in per-chunk records. Failed API calls have unknown output count, not zero generated tokens. No automatic retry was used to improve the baseline.

Only one of four accepted summaries strictly reduced token count; the other three were equal/longer than input and omitted by budget. Contract acceptance is not proof of useful compression or factual faithfulness.

Five outputs of125–197 tokens pass the builder’s200-token check but violate CompressionEvidence’s120-token limit, causing uncaught ValueError rather than graceful omission. One HTTP500 abort also occurred. Outputs exceeding200 and malformed JSON take graceful validation-omission paths. Three valid short summaries did not fit the deliberately constrained budget; a valid summary is not necessarily included.

The original12 samples include two script buckets and three sizes. Script buckets must not be relabelled as English/Hindi/Marathi. Known manuscript chunks retain their source identities, but this benchmark does not provide independently labelled per-language success rates.

Supplemental source-language grouping uses existing query-pack declarations bound through manifest SHA256, not independent language detection. Small samples; no language-wide inference:

{
  "UNRESOLVED": {
    "n": 3,
    "successes": 2,
    "included": 0
  },
  "en": {
    "n": 3,
    "successes": 1,
    "included": 1
  },
  "hi": {
    "n": 1,
    "successes": 0,
    "included": 0
  },
  "mr": {
    "n": 5,
    "successes": 1,
    "included": 0
  }
}

## L. End-to-end grounded-answer results

Recovered historical task-17133.log verifies3 VERBATIM +1 COMPRESSED,39-token gemma4:e4b summary, and GroundedAnswerGenerator status=generated with45 answer tokens and a source citation. This is one controlled fixture demonstration, not answer-accuracy measurement. Original comprehensive10 E2E cases are harness failures; no claim of10 successful grounded answers is made.

## M. Failure taxonomy

{
  "phase_8_5_production": {
    "NONE": 8,
    "OTHER": 2,
    "RETRIEVAL_DENSE": 1,
    "RERANKER": 4,
    "PROVENANCE_METADATA": 3
  },
  "phase_8_5_candidate": {
    "OTHER": 1,
    "NONE": 13,
    "RETRIEVAL_DENSE": 1,
    "PROVENANCE_METADATA": 3
  },
  "phase_8_6_production": {
    "PROVENANCE_METADATA": 55,
    "NONE": 8,
    "RERANKER": 5,
    "RETRIEVAL_DENSE": 2
  },
  "phase_8_6_candidate": {
    "PROVENANCE_METADATA": 55,
    "NONE": 8,
    "OTHER": 3,
    "RETRIEVAL_DENSE": 2,
    "RERANKER": 2
  }
}

Each record retains original classification plus conservative recovery attribution. Invalid exact-title targets are PROVENANCE_METADATA; observable reranker demotions are RERANKER; unresolved causes remain OTHER. Language directions alone never establish MULTILINGUAL_REPRESENTATION failure. Missing multimodal route measurement is a limitation, not fabricated failed-query evidence.

## N. Before/after comparison

No retrieval/ContextBuilder optimization or production fix was made. Only recovery/checkpointing and the broken compression harness input were repaired. Existing30-query Phase8.6 baselines and prior differently matched title/filename evaluations are not numerically comparable to this70-query run. No causal retrieval-quality regression can be concluded from these raw metrics. A concrete local ContextBuilder contract regression is demonstrated: the existing diff raises the builder limit120->200 while CompressionEvidence stays120; five real outputs125–197 abort under that inconsistent contract.

Validation:6 recovery-reporting tests passed;34 Ollama/grounded-answer unit tests passed; current ContextBuilder suite27 passed/7 failed. These are pre-existing workspace behaviors, not recovery-code regressions. Focused-suite global coverage also fails separately (23.48% vs90%). Recovery helpers pass compileall and Ruff F/E9. git diff --check finds pre-existing trailing whitespace in mnemo-core/mnemo/models/chunks.py:65.

## O. Remaining known limitations

- 55/70 Phase8.6 and 3/18 Phase8.5 exact-title target identities invalid
- No complete production application-path parity
- No independent CLIP/OCR/Vision route quality metrics
- Original full top25 rankings and per-stage timings not persisted for first three cohorts/first41 candidate queries
- No new human adjudication, language inference, or qrel edits
- Compression script buckets do not independently identify Hindi versus Marathi
- No matched before/after evaluation establishes a retrieval-quality regression; the separate compression token-limit contract inconsistency is demonstrated
- Reranker pairwise accuracy unverified; generated-answer correctness not human-scored

## P. Exact root causes

1. Original runner saves only at end and references out-of-scope context_stats/e2e_results; candidate per-query records were omitted. Checkpoints preserved completed work before the process exited.
2. Original filename judgments compared against embedded metadata titles produce impossible matches.
3. Original E2E harness passes empty FusionEvidence.
4. Original Phase6 passes Chunk instead of RerankedChunkResult.
5. Production compression limits disagree (builder200 versus model120); uncaught ValueError aborts builds.
6. Windows logged low virtual memory while original CPU reranking and separate Ollama compression overlapped; exact exit cause remains unproven.
7. Original evaluator bypasses the production retrieval application/authorization/alias path, preventing the requested parity claim.

## Q. Final verdict

**FAIL** for acceptance as a production retrieval-quality/regression evaluation. Recovery and bookkeeping are complete; raw measurements, all176 query records,12 real compression trials and row-level multimodal audits are preserved. The raw scores must not be presented as validated whole-corpus quality. Next work requires a separately authorized, identity-grounded production-path evaluation; no such rerun was started.

Final JSON: `C:\Users\athar\Desktop\Mnemo\scratch\comprehensive_evaluation_results.json`

Report: `C:\Users\athar\Desktop\Mnemo\docs\reports\evaluation\COMPREHENSIVE_RETRIEVAL_QUALITY_EVALUATION_REPORT.md`

EXPOSED/VERIFIED/CERTIFIED were not advanced. No alias promotion or index rebuild occurred.
