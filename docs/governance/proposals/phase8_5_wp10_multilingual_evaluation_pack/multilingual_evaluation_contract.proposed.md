# Proposed Multilingual Evaluation Contract v1

Status: **PROPOSED — REQUIRES HUMAN/GOVERNANCE APPROVAL**  
Scope: Mnemo Phase 8.5 WP-10 Decision 7  
This contract defines evaluation structure. It does not approve numeric performance floors, implement WP-10, or certify multilingual retrieval.

## 1. Corpus contract

The proposed evaluation corpus is `phase8.5-golden-44-plus-frozen-authorized-derived-evidence-v1`:

- 44 immutable source documents from the Phase 8.5 Evaluation Corpus.
- Source corpus digest: `78b414e77603fa1ded285ecfd77184f83badfde03b3b633154b097053b929a81`.
- Authorized canonical chunks at exact document versions.
- Eligible immutable OCR regions and Vision derivations from the frozen multimodal evidence state.
- Future transliteration/translation records may be evaluated only as labelled derivations retaining authoritative source lineage.
- V1 vectors, CLIP vectors, and BGE-M3 vectors remain distinct candidate spaces.
- The source corpus, frozen multimodal database, and freeze manifest are immutable inputs. Evaluation and future multilingual generations must use a separate isolated database.

The candidate universe must be frozen before measurement. It contains every authorized evidence item eligible for the evaluated retrieval path, not merely the items returned by a candidate system.

## 2. Query cohort contract

### Primary directional cohorts

**PROPOSED — REQUIRES HUMAN/GOVERNANCE APPROVAL:** 75 answerable cases per direction for certification evaluation; 30 per direction is the minimum provisional measurement floor.

| Direction | Purpose | Certification target | Answerable | Ranking metrics | Overlap |
|---|---|---:|---|---|---|
| EN→EN | Same-language English | 75 | Yes | Yes | Secondary tags allowed |
| EN→HI | English query, Hindi evidence | 75 | Yes | Yes | Secondary tags allowed |
| EN→MR | English query, Marathi evidence | 75 | Yes | Yes | Secondary tags allowed |
| HI→EN | Hindi query, English evidence | 75 | Yes | Yes | Secondary tags allowed |
| HI→HI | Same-language Hindi | 75 | Yes | Yes | Secondary tags allowed |
| HI→MR | Hindi query, Marathi evidence | 75 | Yes | Yes | Secondary tags allowed |
| MR→EN | Marathi query, English evidence | 75 | Yes | Yes | Secondary tags allowed |
| MR→HI | Marathi query, Hindi evidence | 75 | Yes | Yes | Secondary tags allowed |
| MR→MR | Same-language Marathi | 75 | Yes | Yes | Secondary tags allowed |

### Secondary cohorts

| Cohort | Purpose | Target | Answerable | Ranking metrics | Overlap | Evidence |
|---|---|---:|---|---|---|---|
| Hindi transliteration→Hindi | Latin transliteration retrieval | 20 | Yes | Yes | Yes | Canonical/OCR |
| Marathi transliteration→Marathi | Latin transliteration retrieval | 20 | Yes | Yes | Yes | Canonical/OCR |
| Mixed script | Latin + Devanagari path fidelity | 30 | Yes | Yes | Yes | Any authorized |
| Mixed language | Multi-language query handling | 30 | Yes | Yes | Yes | Any authorized |
| Hindi OCR | Hindi evidence from OCR | 20 | Yes | Yes | Yes | OCR region |
| Marathi OCR | Marathi evidence from OCR | 20 | Yes | Yes | Yes | OCR region |
| Multilingual Vision | Language evidence from Vision output | 20 | Yes | Yes | Yes | Vision derivation |
| Canonical text | Preserve canonical retrieval | 270; at least 30/direction | Yes | Yes | Yes | Canonical chunk |
| Negative/no-answer | Unsupported-evidence behavior | 30 | No | No; separate rates | No | Frozen universe reviewed |
| Provenance/security | Scope and lineage correctness | 30 | Mixed | No; correctness gate | Yes | Any authorized |
| WP-16 P85-B-16–20 | Behavioral traceability | 5 | Yes | No; behavioral oracle | Yes | Canonical/OCR |

Query authors and judges must not see candidate rankings. Exact identifiers may appear only when the natural task genuinely requires exact lookup. No query may encode an expected tool name, result rank, or hidden oracle.

## 3. Sample-size contract

The architecture mandates balanced per-direction evaluation but provides no numeric sample size or confidence requirement.

| n/direction | Rate resolution | Worst-case normal 95% half-width | Wilson lower if 100% observed | Wilson lower if 90% observed | Suitable claim |
|---:|---:|---:|---:|---:|---|
| 10 | 10.0% | 31.0% | 72.2% | 59.6% | Smoke evidence only |
| 20 | 5.0% | 21.9% | 83.9% | 69.9% | Weak directional estimate |
| 30 | 3.33% | 17.9% | 88.6% | 74.4% | Proposed provisional floor |
| 40 | 2.5% | 15.5% | 91.2% | 77.0% | Better estimate; still broad |
| 50 | 2.0% | 13.9% | 92.9% | 78.6% | Stable point estimate, weak lower-bound claim |
| 60 | 1.67% | 12.7% | 94.0% | 79.9% | Nearly supports 90% observed / 80% lower claim |
| 75 | 1.33% | 11.3% | 95.1% | 82.0% | Proposed certification target |
| 100 | 1.0% | 9.8% | 96.3% | 82.6% | Stronger but more expensive |

All values above are **PROPOSED — REQUIRES HUMAN/GOVERNANCE APPROVAL**. Exact-rate examples under Wilson 95% intervals:

- 35/35 supports a lower bound just above 90%.
- 63/70 (90%) supports a lower bound just above 80%.
- 133/140 (95%) supports a lower bound just above 90%.
- 68/85 (80%) supports a lower bound just above 70%.

These examples describe sample requirements for hypothetical claims; they do not establish the claims or thresholds.

## 4. Judgment contract

Evidence-level grades:

- `0`: irrelevant or invalid.
- `1`: partially supportive/contextual.
- `2`: directly relevant/supporting.

The normative record shape is [multilingual_qrels.schema.json](multilingual_qrels.schema.json).

Requirements:

1. Two independent reviewers judge every record.
2. Reviewer competency must jointly cover query and evidence languages.
3. Reviewers must not see candidate rankings or scores.
4. Agreement may be recorded directly; disagreement becomes `disputed` and requires a qualified adjudicator.
5. The adjudicated record supersedes reviewer disagreement but does not delete the independent records.
6. Correct notebook, document, version, evidence ID, and source-content hash are mandatory.
7. Occurrence/derivation/source-generation IDs are mandatory when applicable.
8. Wrong version, occurrence, derivation lineage, authorization, or provenance forces grade 0 and may trigger a zero-tolerance failure.
9. Every valid grade-2 evidence item in the frozen candidate universe must be enumerated for Recall calculations.
10. Same-document/wrong-section evidence is judged by support, never by document identity alone.

No qrel may contain filesystem paths, storage URIs, provider secrets, or protected content beyond the minimum evidence identity and content hash.

## 5. Metric contract

### Recall@1/3/5/10

For answerable query `q` with valid grade-2 set `R_q` and first-`k` unique returned evidence IDs `S_q,k`:

`Recall@k(q) = |R_q ∩ S_q,k| / |R_q|`.

Report macro mean over queries, separately per direction. Grade 1 does not count in Recall. Missing or invalid results contribute zero.

### MRR

`RR(q) = 1/rank` for the first valid grade-2 item, otherwise zero. Report macro mean over answerable queries per direction.

### nDCG@10

- Gain: `2^grade - 1` for valid grades 0, 1, 2.
- Invalid/unauthorized evidence gain: zero.
- Discount at one-based rank `r`: `1/log2(r+1)`.
- Cutoff: 10.
- Ideal DCG: sort all valid judged items by grade descending, using the same cutoff.
- Query nDCG is `DCG@10 / IDCG@10`; answerable queries with zero returned gain score zero.
- Report macro mean per direction.

### Reranker pairwise accuracy

`correct decisive orderings / all explicit decisive human-judged pairs`. Only pairs with a strict human preference count; ties and unjudged pairs are excluded. Report candidate counts and pair counts.

### Stable ordering

Sort by score descending, then authoritative evidence ID ascending. Deduplicate by authoritative evidence identity before metric calculation.

### No-answer metrics

No-answer cases are excluded from Recall/MRR/nDCG. Report separately:

- False-support rate: fraction of no-answer queries returning any item represented as support.
- False-publication rate: fraction publishing a grounded answer despite no valid supporting evidence.

## 6. Uncertainty contract

**PROPOSED — REQUIRES HUMAN/GOVERNANCE APPROVAL:**

- Confidence level: 95%.
- Recall@k, pairwise accuracy, and no-answer rates: Wilson score intervals without continuity correction. For macro Recall values that are not binary because multiple qrels exist, additionally report stratified query bootstrap intervals.
- MRR and nDCG@10: percentile bootstrap over queries, stratified by direction.
- Bootstrap seed: `8501007`.
- Resamples: `10000`.
- Secondary cohorts are reported independently; overlapping tags do not create additional independent observations.

## 7. Threshold derivation contract

1. Freeze the source corpus/evidence snapshot.
2. Freeze query texts and cohort membership.
3. Complete independent judgments and adjudication.
4. Keep candidate rankings hidden from query authors and judges.
5. Freeze manifest, query, qrels, environment, and candidate-universe digests.
6. Approve baseline systems and utility-floor methodology before measuring the candidate.
7. Run baseline and candidate implementations against the identical pack.
8. Retain raw rankings, scores, stage attribution, errors, latency, and environment identity.
9. Calculate per-direction and secondary-cohort metrics and uncertainty.
10. Compare with independently approved floors; do not tune floors to make the observed winner pass.
11. Evaluate zero-tolerance correctness/security gates independently.
12. Approve or reject verification/certification with immutable evidence.

Threshold classes remain distinct:

- Model selection: historical 18-query evidence only.
- Implementation acceptance: functional/provider/lifecycle/boundedness plus approved provisional quality floors when available.
- Phase 8.5 verification: post-implementation live MCP directional evidence.
- Certification: final approved numeric floors, confidence treatment, behavioral evidence, and zero correctness failures.

Actual numeric quality floors are **NOT YET DEFENSIBLE**.

## 8. Latency contract

The architecture requires latency reporting and eventually agreed hardware profiles, but it supplies no numeric P50/P95 gate.

Proposed policy:

- Implementation stage: reporting only.
- Verification/certification: conditional hard gate only after hardware profile and numeric limits are approved before measurement.
- Report P50/P95 separately for cold load, warm embed/search, reranker-disabled, and reranker-enabled paths.
- Record batch size, candidate count, CPU/GPU/device, quantization, thread count, timeout count, software lock digest, and whether the model was already resident.
- A timeout is a failed request, never silently omitted from latency reporting.

Numeric latency limits remain **NOT YET DEFENSIBLE**.

## 9. Failure contract

Failure occurs when any approved numeric floor is missed, required cohort/evidence is absent, raw rankings are not retained, or uncertainty cannot be reproduced. Any zero-tolerance violation fails the gate regardless of retrieval quality.

The zero-tolerance gates are authorization/cross-scope leakage, provenance corruption, canonical mutation, false completeness, fabricated language claims, script-only HI/MR inference, vector-space mixing, model/dimension mismatch, partial activation, network fallback, unlabelled transformations, original/derived confusion, frozen multimodal mutation, and Golden Dataset mutation.

## 10. Approval boundary

Governance can freeze today: corpus definition, cohort structure, proposed counts, query-construction rules, qrels schema, reviewer/adjudication procedure, metrics, uncertainty method, threshold-setting process, no-answer policy, latency reporting fields, and zero-tolerance gates.

Governance cannot freeze today: evidence-derived directional performance floors, pairwise accuracy floor, no-answer numeric rate, latency maximums, or certification success. These require the approved pack and post-implementation measurements.

