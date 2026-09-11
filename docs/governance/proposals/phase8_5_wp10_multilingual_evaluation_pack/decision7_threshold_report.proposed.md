# Mnemo Phase 8.5 WP-10 Decision 7 — Proposed Evaluation and Threshold Contract

Status: **PROPOSAL — REQUIRES HUMAN/GOVERNANCE APPROVAL**  
Purpose: define the evidence that must exist before numeric multilingual retrieval thresholds can be frozen.  
This artifact is not implementation evidence, a threshold approval, or certification evidence.

## 1. Existing evidence inventory

| Artifact | Cases | Directions | Judgments | Metrics | Raw rankings retained? | Governed? | Reusable? | Reason |
|---|---:|---|---:|---|---|---|---|---|
| `scripts/phase8_5_11_benchmark_models.py` | 18 | en→en 5; en→mr 1; hi→en 5; hi→mr 1; mr→en 5; mr→mr 1 | 18 document-level expected targets | R@1, R@5, R@10, MRR, uncut single-relevant nDCG | No | No | Model-selection reproduction only | Exact query inventory and algorithm are reconstructable, but rankings and per-direction results were not retained. |
| `docs/reports/evaluation/PHASE_8_5_11_EVALUATION_REPORT.md` | 18 | Aggregate only | Summary only | Embedding and reranker aggregate metrics | No | Governance report, but not a frozen evaluation pack | Selection evidence only | Does not provide qrels, rankings, per-direction metrics, or certification thresholds. |
| `docs/changelog/entries/0073-phase-8-5-11-evaluation-and-model-benchmarks.md` | 18 | Aggregate only | Summary only | Reranker MRR/nDCG summary | No | Historical record | No numeric gate | Its reranker MRR/nDCG conflicts with the evaluation report. |
| `evaluation/phase8_5_wp16/behavioral_manifest.json` | 31 total; 5 multilingual-dependent | P85-B-16 through P85-B-20 | Behavioral expectations, not complete evidence qrels | Deterministic behavioral oracle fields | N/A—no external run | Governed behavioral manifest | Scenario mapping only | Supplies blind-agent prompts and behavioral requirements, not a ranked multilingual retrieval benchmark. |
| `evaluation/phase8_5_wp16/behavioral_manifest.schema.json` | Schema | N/A | Contract validation | N/A | N/A | Governed schema | Yes, for WP-16 validation | Does not define relevance grades or ranking thresholds. |
| `mnemo-core/tests/unit/test_multilingual.py` and related fixtures | Unit fixtures | Selected languages | Synthetic/fake assertions | Contract behavior, not retrieval quality | N/A | Test evidence | Regression only | Cannot support production quality thresholds. |
| `scratch/phase8_5_wp16/eval-20260828-01/multimodal_freeze_manifest.json` | 105 multimodal | Not multilingual directions | Multimodal targets | R@1/3/5/10 and MRR | Yes for its own cohort | Frozen multimodal evidence | No for Decision 7 | Different representations, models, cohort, and objective. |
| `scratch/phase8_5_wp16/eval-20260828-01/retrieval_benchmark_results.json` | 16 multimodal | Not multilingual directions | Multimodal targets | Multimodal retrieval metrics | Yes for its own cohort | Evaluation artifact | No for Decision 7 | Cannot be converted into multilingual thresholds. |

## 2. Reconstructed legacy 18-query cohort

The exact query inventory is retained in the proposed JSON manifest. Its canonical query-list SHA-256 is `c3466771f5af72e4efbd8b59172ee29e75655844b3cecc8fd2a216a3bcb72861`.

Candidate universe: all 44 evaluation documents. Each candidate was represented by its title plus the first 2,500 characters of concatenated canonical chunks. Each query had one expected document. The script calculated R@1, R@5, R@10, MRR, and an uncut single-relevant reciprocal-log nDCG value. It did not calculate R@3, nDCG@10 with graded qrels, or reranker pairwise accuracy.

| Direction | Existing cases | Current certification utility |
|---|---:|---|
| en→en | 5 | Insufficient |
| en→hi | 0 | None |
| en→mr | 1 | Insufficient |
| hi→en | 5 | Insufficient |
| hi→hi | 0 | None |
| hi→mr | 1 | Insufficient |
| mr→en | 5 | Insufficient |
| mr→hi | 0 | None |
| mr→mr | 1 | Insufficient |

The legacy target-language labels also depend on a small hard-coded source-language map: only `manuscript.pdf` was labelled Marathi; all other targets were treated as English. Consequently, the cohort is not a complete human-reviewed language-direction benchmark.

## 3. Missing evidence

- Human-reviewed, evidence-level qrels for all nine directions.
- Any cases for en→hi, hi→hi, and mr→hi.
- Adequate sample sizes in the remaining six directions.
- Transliteration, mixed-script, mixed-language, OCR-language, Vision-language, and no-answer cohorts.
- Complete authorized evidence identities and derivation lineage in every qrel.
- Frozen candidate universe and evidence snapshot digest.
- Retained raw rankings and scores for baseline, embedder, fusion, and reranker stages.
- Per-direction metrics with uncertainty intervals.
- Human-approved utility floors independent of observed candidate scores.
- A resolved source-of-truth for the conflicting reranker MRR/nDCG summaries.
- Frozen latency hardware/environment and a latency policy if latency is to gate acceptance.

## 4. Proposed cohort policy

The primary benchmark must contain all nine ordered directions: en→en, en→hi, en→mr, hi→en, hi→hi, hi→mr, mr→en, mr→hi, and mr→mr.

**PROPOSED — REQUIRES HUMAN/GOVERNANCE APPROVAL:** use at least 30 cases per direction for a provisional implementation-quality estimate and target 50 cases per direction for certification evaluation. Secondary tags may overlap primary directional cases. Negative/no-answer cases do not replace answerable directional cases.

Secondary minimum proposals:

| Cohort | Proposed minimum | May overlap directional cases? |
|---|---:|---|
| Hindi transliteration→Hindi | 20 | Yes |
| Marathi transliteration→Marathi | 20 | Yes |
| Mixed script | 30 | Yes |
| Mixed language | 30 | Yes |
| Hindi OCR evidence | 20 | Yes |
| Marathi OCR evidence | 20 | Yes |
| Vision-derived multilingual evidence | 20 | Yes |
| Negative/no-answer | 30 | No |

These counts are governance proposals, not existing architecture mandates. At n=5, 10, 20, 30, and 50, a binary rate changes in increments of 20, 10, 5, 3.33, and 2 percentage points respectively. For a perfect observed rate, Wilson 95% lower bounds are approximately 0.566, 0.722, 0.839, 0.886, and 0.929. If the desired condition were an observed 0.90 rate with a Wilson lower bound of at least 0.80, approximately 62 cases would be needed. The intended claim strength must therefore be approved before the final sample size is frozen.

## 5. Proposed judgment contract

Use an evidence-level, three-grade relevance scheme:

- `2`: directly relevant/supporting evidence.
- `1`: partially supportive/contextual evidence.
- `0`: irrelevant evidence.

Relevance is valid only when notebook, document, version, and authoritative evidence identity are correct. Occurrence, derivation, and source-generation identities are mandatory when applicable. Wrong scope, version, occurrence, derivation lineage, stale generation, or unauthorized evidence has zero gain and is also a zero-tolerance correctness failure.

Every answerable query must enumerate all relevant authorized evidence items in the frozen candidate universe. Two independent reviewers who cover the query and evidence languages must judge each case; disagreements require adjudication. Same-document/wrong-section evidence is graded by actual support, not document identity.

## 6. Proposed metric definitions

- **Recall@k:** per answerable query, unique valid grade-2 relevant evidence retrieved in the first k divided by all valid grade-2 qrels; macro-average queries.
- **MRR:** reciprocal rank of the first valid grade-2 item; zero if none; macro-average answerable queries.
- **nDCG@10:** gain `2^grade - 1`, log2(rank+1) discount, cutoff 10, divided by ideal DCG@10. Invalid evidence has zero gain.
- **Reranker pairwise accuracy:** correct strict orderings divided by explicit, decisive, human-judged candidate pairs. Ties and unjudged pairs are excluded.
- **Ties:** stable ordering by score descending, then authoritative evidence UUID ascending.
- **Missing results:** zero gain and zero recall.
- **Multiple relevant items:** all valid qrels contribute to recall and ideal ranking.
- **No-answer queries:** excluded from answerable-query ranking metrics and scored separately by unsupported-evidence and grounded-publication false-positive rates.

Report Wilson 95% intervals for proportions. Report deterministic stratified-bootstrap 95% intervals for MRR and nDCG@10 only after the bootstrap seed and resample count are governance-approved and frozen.

## 7. Numeric evidence and threshold status

| Evidence | R@1 | R@5 | R@10 | MRR | nDCG | Status |
|---|---:|---:|---:|---:|---:|---|
| BGE-M3 selection report | 0.833 | 1.000 | 1.000 | 0.898 | 0.924 | Model-selection evidence only |
| BGE reranker evaluation report | 0.944 | 1.000 | 1.000 | 0.963 | 0.972 | Model-selection evidence; raw output absent |
| BGE reranker changelog | Not stated | Not stated | Not stated | 0.926 | 0.941 | Conflicting historical summary |
| Frozen multimodal benchmark | 0.638 | 0.819 | 0.848 | 0.7163 | Not stated | Not a multilingual baseline or threshold |

The reranker contradiction is unresolved: no retained raw multilingual benchmark output or per-query rankings were found in `scratch/`, `reports/`, `evaluation/`, benchmark scripts, or logs. Neither pair of MRR/nDCG numbers may be selected as authoritative without rerunning the frozen legacy cohort after the production adapter exists or locating independently verifiable raw output.

**NUMERIC CERTIFICATION THRESHOLD CANNOT YET BE FROZEN FROM EXISTING EVIDENCE.**

The legacy aggregate selection scores may be used only as adapter-reproducibility smoke expectations where their definitions match. They must not become directional certification floors.

## 8. Proposed threshold structure

| Cohort/direction | R@1 min | R@5 min | R@10 min | MRR min | nDCG@10 min | Status |
|---|---|---|---|---|---|---|
| en→en | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | Governed qrels and measurements required |
| en→hi | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | No existing cases |
| en→mr | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | One existing case |
| hi→en | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | Five existing cases |
| hi→hi | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | No existing cases |
| hi→mr | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | One existing case |
| mr→en | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | Five existing cases |
| mr→hi | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | No existing cases |
| mr→mr | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | One existing case |
| Transliteration | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | Cohort absent |
| Mixed script/language | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | Cohort absent |
| OCR language | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | Cohort absent |
| Vision language | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | NOT YET DEFENSIBLE | Cohort absent |
| Reranker pairwise accuracy | — | — | — | — | — | NOT YET DEFENSIBLE — judged pairs absent |
| No-answer false-support/publication | — | — | — | — | — | Numeric threshold pending; correctness violations remain zero-tolerance |
| Latency | — | — | — | — | — | Report-only until hardware-specific policy approved |

## 9. Threshold derivation procedure

1. Human/governance approval freezes the manifest schema, sample-size claim, judgment scheme, metric definitions, candidate universe, and evaluator procedure.
2. Create and independently review the queries and qrels without observing candidate-system rankings.
3. Freeze corpus, query, and judgment digests before candidate measurement.
4. After the production implementation exists, run frozen baseline and candidate profiles against the identical pack; retain raw rankings, stage scores, errors, resource data, and per-direction metrics.
5. Calculate confidence intervals and analyze directional and secondary cohorts separately.
6. Approve utility floors independently of the observed winning score. Avoid choosing a floor merely to pass the measured candidate.
7. Freeze numeric thresholds and their evidence digests before any `VERIFIED` or `CERTIFIED` lifecycle claim.

## 10. Zero-tolerance correctness gates

The following have an allowed count of zero and are not tradeable against retrieval quality: authorization leakage, cross-notebook leakage, cross-version leakage, provenance corruption, canonical-text mutation, false completeness, fabricated language claims, Hindi/Marathi inference from script alone, vector-space mixing, model revision mismatch, vector dimension mismatch, partial generation activation, network fallback, unlabeled translation/transliteration, OCR/Vision represented as original, frozen multimodal mutation, and Golden Dataset mutation.

## 11. Approval boundary

Before coding, governance may approve the *evaluation contract structure* and authorize creation/adjudication of its queries and qrels. It cannot truthfully approve numeric certification thresholds from current evidence. Coding should remain blocked under the stated Decision 7 gate unless governance explicitly freezes either:

1. a pre-implementation utility-floor methodology plus provisional implementation gates, with numeric certification floors deferred until blinded post-implementation measurement; or
2. a complete human-reviewed evaluation pack and numeric floors established using an independent pre-implementation baseline.

The exact outstanding approvals are: sample size and claim strength; secondary-cohort minima; relevance grades and adjudication; bootstrap seed/resample count; candidate universe; no-answer policy; latency policy/hardware; threshold-setting methodology; and whether provisional coding may start before numeric certification floors are populated.

