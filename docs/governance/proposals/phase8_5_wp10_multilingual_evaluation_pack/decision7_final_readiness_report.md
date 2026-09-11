# MNEMO PHASE 8.5 — DECISION 7 FINAL GOVERNANCE READINESS REPORT

## 1. Executive verdict

Decision 7 remains **OPEN**. The proposed evaluation structure is complete enough for human review, but numeric multilingual quality floors are **NOT YET DEFENSIBLE**. Under the current gate, WP-10 implementation remains **NO-GO** until governance explicitly approves the pre-implementation contract and authorizes coding.

## 2. Authoritative requirements

- The Phase 8.5 plan requires per-direction live MCP metrics to meet pinned profile thresholds and report paths/fallback truthfully.
- ADR-0067 requires same/cross-language retrieval, original-source provenance, language/direction/latency evidence, and benchmark acceptance before validated claims.
- ADR-0070 requires a machine-readable governed evaluation pack, treats unmeasured capabilities as `UNVALIDATED`, and prohibits arbitrary pre-baseline quality numbers.
- The Phase 8.5 architecture requires balanced EN/HI/MR directions, transliteration, mixed script, OCR, negatives, human-reviewed judgments, Recall@k, MRR/nDCG, pairwise accuracy, attribution, grounding, language fidelity, and latency per direction.
- No reviewed document specifies sample counts, confidence method, relevance grades, exact nDCG formula, pairwise protocol, no-answer rates, bootstrap parameters, or numeric latency limits.

## 3. Existing evidence

The 18-query benchmark is an imbalanced model-selection cohort: en→en 5, en→hi 0, en→mr 1, hi→en 5, hi→hi 0, hi→mr 1, mr→en 5, mr→hi 0, mr→mr 1. It has one document target per query and no retained rankings, evidence qrels, per-direction output, confidence intervals, or certification floors.

Published BGE-M3 aggregate evidence is MRR 0.898 and legacy nDCG 0.924. Published BGE reranker summaries conflict: the evaluation report gives MRR 0.963/nDCG 0.972 while the changelog gives 0.926/0.941. The final raw-artifact search found no rankings that resolve the conflict.

## 4. Proposed evaluation contract

The package proposes an immutable 44-document source corpus plus authorized immutable canonical/OCR/Vision evidence, materialized later in a separate isolated evaluation snapshot. It defines nine primary directions, eleven secondary/behavioral cohorts, hidden candidate rankings during judgment, evidence-level qrels, strict provenance validity, reproducible metrics, uncertainty, threshold derivation, and zero-tolerance correctness gates.

No query, qrel, ranking, or result has been manufactured by this package.

## 5. Sample-size policy

**PROPOSED — REQUIRES HUMAN/GOVERNANCE APPROVAL:**

- Minimum provisional measurement: 30 answerable cases/direction.
- Certification evaluation target: 75 answerable cases/direction.
- Secondary targets: 20 per transliteration cohort; 30 mixed-script; 30 mixed-language; 20 per OCR language; 20 multilingual Vision; 30 negative/no-answer; 30 provenance/security.
- For an exact observed 90% rate with Wilson 95% lower bound above 80%, at least 70 cases are required. Different claims require different n.

The sample policy is not an architecture mandate and must be approved based on the intended claim strength and evaluation cost.

## 6. Qrels/judgment contract

Grades are 0 irrelevant, 1 partially supportive, and 2 directly relevant. Two independent language-qualified reviewers are proposed, with qualified adjudication and retention of the independent records. Correct notebook/document/version/evidence identity and content hash are mandatory; occurrence, derivation, and generation IDs are mandatory where applicable. Wrong authorization/provenance forces grade 0 and a correctness failure.

The strict schema is `multilingual_qrels.schema.json`. It forbids unknown fields and does not permit filesystem/storage/provider details.

## 7. Metric contract

- Recall@1/3/5/10: macro query recall over all valid grade-2 qrels.
- MRR: first valid grade-2 result, macro per direction.
- nDCG@10: gain `2^grade-1`, log2 discount, cutoff 10, ideal ranking from valid judged items.
- Pairwise accuracy: decisive human-judged strict pairs only.
- Invalid/unauthorized evidence: zero gain plus correctness failure.
- Ties: score descending, then authoritative evidence ID ascending.
- No-answer: excluded from ranking metrics; separately score false support and false publication.

## 8. Uncertainty contract

**PROPOSED — REQUIRES HUMAN/GOVERNANCE APPROVAL:** 95% Wilson intervals without continuity correction for binary proportions. MRR/nDCG and non-binary macro Recall use stratified percentile bootstrap over queries, direction-stratified, seed `8501007`, 10,000 resamples. Overlapping secondary tags are not treated as independent observations.

## 9. Threshold derivation procedure

Freeze corpus, queries, qrels, candidate universe, manifest, environment, and digests before candidate measurement. Keep candidate rankings hidden from authors/judges. Approve baselines and utility-floor methodology independently. Run baseline/candidate without changing the pack; retain raw rankings and resource evidence; calculate per-direction metrics and uncertainty; evaluate zero-tolerance gates; then approve or reject floors without choosing numbers merely to pass the observed candidate.

Model selection, implementation acceptance, Phase 8.5 verification, and certification thresholds remain separate.

## 10. Latency policy

No authoritative numeric latency gate exists. Proposed policy is reporting-only during implementation and conditional gating only after a hardware profile and limits are approved before measurement. Required reporting includes cold/warm P50/P95, batching, candidate count, reranker state, CPU/GPU/device, model residency, timeouts, and software identity. Numeric limits are **NOT YET DEFENSIBLE**.

## 11. Reranker contradiction

The 0.963/0.972 versus 0.926/0.941 contradiction remains unresolved. Governance must either locate independently verifiable raw output or authorize a reproduction run of the exact frozen legacy cohort after the adapter exists, retaining raw rankings and environment identity. Neither historical pair is an approved floor.

## 12. Pre-implementation freeze matrix

| Item | Can freeze now? | Evidence required | Approval required? |
|---|---|---|---|
| Corpus definition | Yes | Digests and immutable source/evidence identities | Yes |
| Query cohort structure | Yes | Architecture and corpus feasibility review | Yes |
| Sample size | As proposal | Claim-strength/statistical review | Yes |
| Qrels schema | Yes | Schema and adversarial review | Yes |
| Metric definitions | Yes | Independent calculation review | Yes |
| Uncertainty methodology | Yes as proposal | Statistical review | Yes |
| Zero-tolerance gates | Yes | Security/provenance review | Yes |
| No-answer policy | Yes as proposal | Evaluation/security review | Yes |
| Latency reporting policy | Yes | Operator/hardware review | Yes |
| Numeric latency gate | No | Frozen hardware baseline | POST-IMPLEMENTATION |
| Threshold-setting procedure | Yes | Governance approval | Yes |
| Directional numeric floors | No | Governed pack and independent baseline/candidate measurements | POST-IMPLEMENTATION |
| Certification outcome | No | Complete approved evidence | POST-IMPLEMENTATION |

## 13. Human approval checklist

The normative checklist is `governance_approval_checklist.md`. It requires decisions on corpus, counts, query construction, qrels, reviewer/adjudication policy, candidate universe, every metric, no-answer handling, uncertainty/bootstrap settings, latency, threshold derivation, numeric floors, WP-16 criteria, zero-tolerance gates, reranker conflict, and explicit permission to implement WP-10.

## 14. WP-10 readiness

| Requirement | Current state | Proposed resolution | Blocking? |
|---|---|---|---|
| Decision 1 — source reference | FROZEN | Preserve LanguageEvidenceReferenceV2 | No |
| Decision 2 — BGE preprocessing | FROZEN | Preserve query/document preprocessing identities | No |
| Decision 3 — embedding protocol | FROZEN | Preserve MultilingualEmbeddingProviderV2 design | No |
| Decision 4 — detector | FROZEN | Preserve conservative EN/HI/MR detector | No |
| Decision 5 — generations | FROZEN | Preserve named identities and lifecycle | No |
| Decision 6 — reranker truncation | FROZEN | Preserve 256-token pair policy | No |
| Decision 7 — quality thresholds | OPEN | Approve this evaluation structure; construct qrels; derive independent floors | **Yes** |
| Decision 8 — dense backend | FROZEN | Preserve bounded SQLite exact-cosine BGE-M3 space | No |

Can WP-10 implementation begin now? **NO.** The currently stated governance gate remains in force.

## 15. Exact next action

1. Human reviewers inspect all eight package artifacts.
2. Governance approves or amends the contract, counts, qrels, metrics, uncertainty, latency, and threshold procedure.
3. Create the actual natural-language queries and evidence qrels through blinded, independent human review.
4. Freeze corpus/query/qrels/candidate-universe digests.
5. Decide explicitly whether approved structure plus predeclared post-implementation floor derivation is sufficient to authorize WP-10 coding.
6. If authorized, implement WP-10 in a separate task without modifying frozen multimodal inputs.
7. After implementation, run the frozen evaluation, retain raw evidence, derive/approve numeric floors, execute WP-16 cases, and determine verification/certification separately.

Answers:

- **A. What can governance freeze today?** Corpus/cohort structure, proposed sample counts, query/qrels rules, metrics, uncertainty, no-answer and latency reporting policies, threshold procedure, and zero-tolerance gates.
- **B. What cannot be frozen today?** Evidence-derived numeric directional, reranker, no-answer, latency, verification, and certification floors.
- **C. What artifacts must a human approve?** The contract Markdown/schema, qrels schema, threshold proposal, manifest template, approval checklist, and readiness report.
- **D. What dataset must be created?** A human-reviewed, evidence-level, immutable pack with 75 proposed cases in each of nine directions plus approved secondary/negative cohorts and full provenance qrels.
- **E. What must happen before coding?** At minimum, explicit governance approval of the pre-implementation contract and explicit permission to code; under a strict fully-frozen Decision 7 interpretation, the actual governed query/qrel pack and threshold method must also be frozen.
- **F. What happens after coding?** Frozen-pack execution, retained rankings, uncertainty, independent floor approval, live MCP/WP-16 verification, and zero-tolerance review.
- **G. When can Decision 7 become fully frozen?** When the governed dataset exists and actual numeric floors are approved through the non-circular procedure. Certification remains later.
- **H. When can WP-10 move from NO-GO to GO?** Only when the designated governance authority signs the checklist item granting implementation permission under an approved Decision 7 contract.

## 16. Final GO/NO-GO

**DECISION 7: STRUCTURE READY FOR HUMAN APPROVAL; NUMERIC FLOORS OPEN.**

**WP-10 IMPLEMENTATION: NO-GO.**

No implementation, model loading, embedding generation, multilingual generation, activation, ingestion, database mutation, MCP change, or authoritative governance modification was performed.

