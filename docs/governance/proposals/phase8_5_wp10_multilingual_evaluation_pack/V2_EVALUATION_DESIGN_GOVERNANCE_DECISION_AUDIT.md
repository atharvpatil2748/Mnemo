# V2 Evaluation Design Governance Decision Audit

**Date:** 2026-09-02  
**Task:** Governed Evaluation Design Decision Audit — Read-Only Governance Audit  
**Scope:** Phase 8.5 WP-10 Decision 7 — 9-Direction Evaluation Design & Corpus Asymmetry  
**Auditor:** Antigravity Engineering (governed handoff)  
**Status:** **COMPLETE — READ-ONLY GOVERNANCE DECISION AUDIT**  
**Final Determination:** **GOVERNANCE ACTION REQUIRED — FORMAL CORPUS-CONSTRAINED POLICY MANDATED**  

---

## 1. Executive Determination

The latest evaluation readiness audit (`V2_GOVERNED_EVALUATION_PACK_READINESS_REPORT.md`) determined that the proposed 270-case evaluation pack is **NOT READY**. 

This decision audit investigated the root causes of that blockage across the governing documents:
- `multilingual_evaluation_contract.proposed.md`
- `multilingual_evaluation_manifest.proposed.json`
- `multilingual_threshold_contract.proposed.json`
- `MULTILINGUAL_EVALUATION_ARCHITECTURE.proposed.md`
- `FAILURE_TAXONOMY.proposed.json`
- `V2_POST_EVALUATION_DETERMINATION_AUDIT.md`

### Primary Finding:
The core problem is a direct conflict between an unapproved, proposed sample-size heuristic ($\ge 30$ cases per direction across all 9 directions) and the physical reality of the immutable 44-document Phase 8.5 evaluation corpus:
1. **Marathi Target Evidence:** Only **10 chunks** exist in the entire V2 database (`language_text_projection_rows_v2`), all originating from a single document (`manuscript.pdf`). Enforcing 30 cases each for `en->mr`, `hi->mr`, and `mr->mr` ($90$ queries total) requires an average query density of 9 queries per 500-character chunk, violating statistical case independence and creating severe risk of memorization/leakage.
2. **Hindi Target Evidence:** Only ~90 chunks containing Devanagari Hindi text exist across the entire V2 database (39 in `PHYSICS_JEE_ADVANCED.pdf`, 46 in `Bhagavad-gita`, 6 in `Atharv_Patil_240740.pdf`, and 2 in `Valmiki Ramayana`). Enforcing 30 cases each for `en->hi`, `hi->hi`, and `mr->hi` ($90$ queries total) forces extreme topical concentration on physics problem sets and scriptural commentary.
3. **English Target Evidence:** Abundant (~2,500 chunks across 38+ documents).

The repository lifecycle remains strictly preserved:
```text
DECLARED: PASS
IMPLEMENTED: PASS
CONFIGURED: PASS
BUILDABLE: PASS
READY: PASS
ACTIVE: PASS

EXPOSED: FALSE
EVALUATED: FALSE
VERIFIED: FALSE
CERTIFIED: FALSE
```

---

## 2. Sample-Size Policy Interpretation

### Question:
Is the $\ge 30$ cases/direction requirement:
- A. An immutable architectural requirement,
- B. A provisional governance proposal that can be amended by human approval, or
- C. A statistical recommendation whose applicability depends on available corpus evidence and case independence?

### Governing Language:
In `docs/governance/proposals/phase8_5_wp10_multilingual_evaluation_pack/multilingual_evaluation_manifest.proposed.json` (lines 108–112):
> `"sample_size_policy": {`  
> &nbsp;&nbsp;`"status": "proposed_requires_human_governance_approval",`  
> &nbsp;&nbsp;`"minimum_cases_per_direction": 30,`  
> &nbsp;&nbsp;`"certification_target_cases_per_direction": 50,`  
> &nbsp;&nbsp;`"rationale": "Thirty gives 3.33 percentage-point metric resolution and supports a provisional directional estimate; fifty gives 2-point resolution but still requires confidence intervals. Neither count is an existing architecture mandate."`  
> `}`

In `docs/governance/proposals/phase8_5_wp10_multilingual_evaluation_pack/multilingual_evaluation_contract.proposed.md` (lines 25, 59, 72):
> Line 25: `**PROPOSED — REQUIRES HUMAN/GOVERNANCE APPROVAL:** 75 answerable cases per direction for certification evaluation; 30 per direction is the minimum provisional measurement floor.`  
> Line 59: `The architecture mandates balanced per-direction evaluation but provides no numeric sample size or confidence requirement.`  
> Line 72: `All values above are **PROPOSED — REQUIRES HUMAN/GOVERNANCE APPROVAL**.`

### Audit Determination:
The $\ge 30$ cases/direction requirement is **B. A provisional governance proposal that can be amended by human approval** AND **C. A statistical recommendation based on metric resolution**.

The governing text explicitly declares:
> **"Neither count is an existing architecture mandate."**

It is **NOT** an immutable architectural requirement. Human governance holds full authority to modify, stratify, or approve directional sample sizes that align with actual corpus evidence.

---

## 3. Corpus-Constraint Policy

### Question:
Does the governance framework contain an explicit mechanism for:
- corpus-constrained cohorts,
- insufficient-evidence directions,
- minimum-evidence exceptions,
- directional exclusions,
- stratified reporting,
- confidence intervals under smaller $n$, or
- separate capability-vs-certification evaluation?

### Audit Findings:
1. **Capability vs Semantic Retrieval Distinction:**  
   `MULTILINGUAL_EVALUATION_ARCHITECTURE.proposed.md` Section 4 explicitly distinguishes query classes:
   - *Class 1: Language capability/routing:* proves a declared language/script can be represented and routed; excluded from Recall/MRR/nDCG.
   - *Class 2: Semantic retrieval quality:* requires a topic/entity and adjudicated evidence; the only class used for ranking metrics.
2. **Unvalidated Direction State:**  
   `MULTILINGUAL_EVALUATION_ARCHITECTURE.proposed.md` Section 5 explicitly provides:
   > *"per-edge state remains `UNVALIDATED` when no governed qrels exist. This supports many languages without generalizing an anchor edge's score to unmeasured directions."*
3. **Statistical Scaling under Small $n$:**  
   `multilingual_evaluation_contract.proposed.md` Section 3 establishes Wilson 95% lower bounds for smaller sample sizes:
   - $n=10$: Rate resolution 10.0%, Wilson lower bound if 100% observed = 72.2% ("Smoke evidence only").
   - $n=20$: Rate resolution 5.0%, Wilson lower bound if 100% observed = 83.9% ("Weak directional estimate").
   - $n=30$: Rate resolution 3.33%, Wilson lower bound if 100% observed = 88.6% ("Proposed provisional floor").

### Explicit Ruling:
**NO GOVERNED EXCEPTION MECHANISM FOUND.**

While the framework recognizes `UNVALIDATED` directional states, defines smaller-$n$ Wilson intervals, and distinguishes capability from semantic ranking, **no operational rule currently exists that formally authorizes an automatic reduction of the 30-case floor specifically for corpus-starved target directions**. Creating such an exception requires an explicit, approved human governance decision.

---

## 4. Case-Independence Interpretation

### Question:
What does the evaluation contract mean by an "answerable case", and are multiple queries targeting the same evidence chunk permitted as independent statistical observations?

### Governing Language:
In `multilingual_evaluation_contract.proposed.md`:
- Line 51: `Negative/no-answer: Unsupported-evidence behavior (30 target; Answerable: No; Ranking metrics: No; separate rates)`
- Line 110: `For answerable query q with valid grade-2 set R_q and first-k unique returned evidence IDs S_q,k... Report macro mean over answerable queries per direction.`
- Line 154: `Secondary cohorts are reported independently; overlapping tags do not create additional independent observations.`

In `multilingual_evaluation_manifest.proposed.json`:
- Line 171: `"no_answer_queries": "excluded from Recall/MRR/nDCG and scored separately for unsupported evidence claims and publication"`
- Line 174: `"confidence_intervals": "Wilson 95% intervals for proportions; deterministic stratified bootstrap 95% intervals for MRR and nDCG@10 with frozen seed and resample count to be approved"`

### Audit Determination:
1. **Meaning of "Answerable Case":** An answerable case is a query for which at least one valid, authorized grade-2 supporting evidence item exists in the frozen candidate universe, in contrast to negative/unsupported queries where no supporting evidence exists.
2. **Multiple Queries Against the Same Chunk:**  
   The contract does **not** explicitly prohibit authoring multiple queries that target different factual aspects of the same document or chunk. However, classical evaluation methodology and the mandated Wilson/bootstrap interval models assume that evaluation cases represent **statistically independent observations**.
3. **Saturation Hazard:**  
   Generating 30 queries for `en->mr`, 30 for `hi->mr`, and 30 for `mr->mr` against only 10 Marathi chunks results in an average query density of **9 queries per chunk**. If an indexer or reranker scores a chunk favorably or unfavorably, all 9 queries are correlated. Treating them as 90 independent statistical observations is **scientifically invalid and misleading**.
4. **Governed Status:** Case independence at the query-evidence level is **NOT GOVERNED / UNRESOLVED IN THE CONTRACT**.

---

## 5. Corpus Expansion Rules

### Question:
Does the governance framework permit adding evaluation-only documents outside the immutable golden corpus?

### Governing Language:
In `multilingual_evaluation_contract.proposed.md` Section 1:
> `The proposed evaluation corpus is phase8.5-golden-44-plus-frozen-authorized-derived-evidence-v1:`  
> `- 44 immutable source documents from the Phase 8.5 Evaluation Corpus.`  
> `- Source corpus digest: 78b414e77603fa1ded285ecfd77184f83badfde03b3b633154b097053b929a81.`  
> `- The source corpus, frozen multimodal database, and freeze manifest are immutable inputs. Evaluation and future multilingual generations must use a separate isolated database.`

### Distinct Corpus Concepts in Governance:

| Action Category | Governed Status | Architectural Impact |
|---|:---:|---|
| **Modifying the Golden Corpus** | **STRICTLY PROHIBITED** | Breaks frozen digest `78b414e7...`; violates immutable test invariants. |
| **Replacing Protected Evidence** | **STRICTLY PROHIBITED** | Breaks verified SHA-256 hashes of `manuscript.pdf` and `Ramayana...pdf`. |
| **Adding a Separate Evaluation Corpus** | **NOT YET GOVERNED** | Permissible only under a separate proposal; requires building, verifying, and activating a completely new V2 database artifact with a new vector space and alias set. |
| **Creating a Future V2 Generation** | **REQUIRES HUMAN APPROVAL** | The V2 database `build-20260831-01` is frozen. Ingesting new documents requires advancing the generation lifecycle and creating a new build run. |

---

## 6. QREL Governance

### Mandatory Requirements under `multilingual_qrels.schema.json`:
1. **Evidence-Level Specificity:** Every judgment must record exact opaque UUIDs for `notebook_id`, `document_id`, `version_id`, and `evidence_id`, along with `source_content_hash`. Document filename alone is invalid.
2. **Relevance Scale:** Exactly three ordinal grades:
   - `0`: Irrelevant or invalid provenance.
   - `1`: Partially supportive / contextual.
   - `2`: Directly relevant / supporting.
3. **Dual Independent Review:** Minimum 2 independent human reviewers (`minItems: 2`). Reviewers must record `reviewer_id` and certified language competencies (`reviewer_languages`).
4. **Blinded Evaluation:** Reviewers must evaluate candidate support without seeing system rankings, scores, or retrieval engine identities.
5. **Adjudication Procedure:** When independent reviewers agree, status is `agreed`. When they disagree, status becomes `disputed` and requires a designated `adjudicator_id` to emit an `adjudicated` record.
6. **No-Answer Control Cases:** 30 unanswerable queries required to measure false-support rates.

### Readiness Audit:
- **Technically Supported:** The storage model (`LanguageEvidenceReferenceV3`), projection rows, candidate builders, and JSON schemas fully support all evidence-level QREL fields.
- **Requiring Human Governance / Execution:** Authoring query texts, provisioning qualified bilingual human evaluators, conducting blinded dual review, and adjudicating disputes. **Zero human QREL records exist in the repository.**

---

## 7. Threshold Governance

### Questions:
- Can thresholds be approved now?
- Who/what is authorized to approve thresholds?
- Must thresholds exist before evaluation?
- Can thresholds be different by direction?
- Do smaller cohorts require uncertainty intervals?

### Audit Findings:
1. **Can thresholds be approved now?** **NO.** Antigravity / automated agents are explicitly forbidden from inventing numeric thresholds.
2. **Authority:** Thresholds can only be approved by **human governance** (system architect / project steering committee).
3. **Timing Invariant:** In `multilingual_evaluation_manifest.proposed.json` line 191:
   > *"approve utility floors independently of the observed winning score; freeze thresholds and evidence digests before VERIFIED or CERTIFIED lifecycle claims"*  
   Thresholds **must exist before evaluation** and cannot be retrofitted to match measured scores.
4. **Directional Variation:** **PERMITTED.** The schema allows distinct thresholds per direction (e.g., higher floors for monolingual `en->en` and lower provisional floors for difficult cross-lingual edges like `mr->en`).
5. **Uncertainty Reporting:** **MANDATORY.** Section 6 of the evaluation contract mandates reporting 95% Wilson score intervals and stratified bootstrap intervals, particularly where sample sizes are small.

---

## 8. Option A Analysis: Expand Evaluation Corpus Separately

Keep $\ge 30$ cases/direction; create a separate evaluation corpus with 20+ new Marathi and Hindi documents.

- **Governance Compatibility:** **MODERATE.** Preserves golden corpus immutability by using a separate evaluation namespace, but requires drafting and approving a new Corpus Expansion Contract.
- **Statistical Defensibility:** **HIGH.** Provides sufficient chunk density (60+ chunks per language) to support 30 independent queries per direction without saturation.
- **Effect on Golden Corpus:** **ZERO.** Golden corpus remains untouched at `78b414e7...`.
- **Implementation Cost:** **VERY HIGH.** Requires document sourcing, copyright clearance, ingestion, OCR/Vision pipeline runs, text projection, BGE-M3 dense/sparse embedding generation, vector indexing, alias activation, and database verification.
- **Evaluation Coverage:** **FULL.** All 9 directions reach $n \ge 30$.
- **Risk of Misleading Conclusions:** **LOW.** Genuine evaluation over diverse documents.
- **Prerequisites:** Ingestion tooling, pipeline execution, new database build, dual-reviewer human QREL authoring.
- **Can reach EVALUATED?** Yes.
- **Can reach CERTIFIED?** Yes.

---

## 9. Option B Analysis: Formally Governed Corpus-Constrained Policy

Keep the frozen 44-document corpus; establish an approved governance policy adjusting directional sample sizes to match physical evidence availability (e.g., 10 cases for Marathi targets = 1 query per chunk; 30 cases for English targets).

- **Governance Compatibility:** **HIGH (with Human Governance Approval).** Aligns evaluation directly with the existing frozen artifact.
- **Statistical Defensibility:** **MODERATE.** For Marathi targets ($n=10$), rate resolution is 10.0% and Wilson 95% lower bounds are wide (72.2% at 100% observed). Statistically sound only if explicitly reported with confidence intervals and labeled as provisional.
- **Effect on Golden Corpus:** **ZERO.** No changes to corpus or database.
- **Implementation Cost:** **LOW.** Uses existing frozen `mnemo.db` (build `20260831-01`).
- **Evaluation Coverage:** **COMPLETE FOR AVAILABLE EVIDENCE.** Covers all 10 Marathi chunks and ~90 Hindi chunks without artificial duplication.
- **Risk of Misleading Conclusions:** **LOW TO MODERATE.** Low if reported with Wilson intervals; misleading only if 10 cases are claimed to represent "comprehensive certification".
- **Prerequisites:** Human governance amendment approving the corpus-constrained policy and thresholds; dual-reviewer QREL authoring for the tailored cases.
- **Can reach EVALUATED?** **YES (Provisional EVALUATED: PASS).**
- **Can reach CERTIFIED?** **NO.** Certification requires 75 cases/direction.

---

## 10. Option C Analysis: Postpone Formal Evaluation

Use the 18-case cohort solely as an internal smoke test; postpone all formal evaluation until a future phase.

- **Governance Compatibility:** **HIGH.** Does not alter contracts or make unwarranted claims.
- **Statistical Defensibility:** **N/A.** No claims made.
- **Effect on Golden Corpus:** **ZERO.**
- **Implementation Cost:** **ZERO.**
- **Evaluation Coverage:** **NONE.** Repository remains uncertified and unevaluated.
- **Risk of Misleading Conclusions:** **ZERO.**
- **Prerequisites:** None.
- **Can reach EVALUATED?** **NO.** Lifecycle remains `EVALUATED: FALSE`.
- **Can reach CERTIFIED?** **NO.**

---

## 11. Option D Analysis: Hybrid Stratified Directional Policy

Formally evaluate abundant directions (`en->en`, `hi->en`, `mr->en`) at $n=30$; evaluate Hindi targets at $n=30$ across available Devanagari chunks; evaluate Marathi targets at $n=10$ (census over all 10 chunks); mark Marathi target certification as `UNVALIDATED / DEFERRED`.

- **Governance Compatibility:** **VERY HIGH.** Directly utilizes `MULTILINGUAL_EVALUATION_ARCHITECTURE.proposed.md` Section 5 (`UNVALIDATED` directional state policy).
- **Statistical Defensibility:** **HIGH.** Full statistical power ($n=30$, 3.33% resolution) where evidence permits; exact census ($n=10$, 1 query/chunk) where evidence is constrained.
- **Effect on Golden Corpus:** **ZERO.**
- **Implementation Cost:** **MODERATE.** Requires authoring $30 \times 6 + 10 \times 3 = 210$ queries and human QRELs across existing frozen database chunks.
- **Evaluation Coverage:** **BALANCED.** Evaluates 100% of English, Hindi, and Marathi evidence in the corpus.
- **Risk of Misleading Conclusions:** **LOW.** Discloses directional confidence intervals and explicit scope boundaries.
- **Prerequisites:** Human governance approval of the Stratified Directional Policy and directional thresholds; dual-reviewer QREL authoring.
- **Can reach EVALUATED?** **YES (Governed EVALUATED: PASS for Phase 8.5 scope).**
- **Can reach CERTIFIED?** **PARTIAL.** Certification granted only for validated directional edges.

---

## 12. Recommended Governance Path

### Recommendation: **OPTION D (Hybrid Stratified Directional Policy)**

Option D is the most scientifically defensible, truthful, and realistic path forward for the following reasons:

1. **Truthful Statistical Interpretation:** It eliminates the artificial saturation of forcing 90 queries onto 10 Marathi chunks. Each Marathi chunk is tested with exactly 1 high-quality, human-adjudicated query per direction ($n=10$ for `en->mr`, $n=10$ for `hi->mr`, $n=10$ for `mr->mr`).
2. **Full Exploitation of Abundant Evidence:** English target directions (`en->en`, `hi->en`, `mr->en`) achieve the full $\ge 30$-case provisional floor.
3. **Transparent Reporting:** Wilson score intervals and stratified bootstrap intervals are reported for all directions, allowing human governance to observe the exact statistical precision of each edge.
4. **Preservation of Immutability:** Requires zero modifications to the 44-document golden corpus, zero changes to `mnemo.db`, and zero alias mutations.
5. **Clear Separation of Lifecycle Gates:** Authorizes `EVALUATED: PASS` for the governed Phase 8.5 scope while cleanly holding `CERTIFIED` at `FALSE` until future multi-document corpus expansion occurs.

---

## 13. Human Decisions Required

The following explicit decisions cannot be made autonomously by AI agents and require formal human governance sign-off:

| Decision ID | Required Governance Action | Governing Reference |
|---|---|---|
| **DEC-8.5-EVAL-01** | Approve the **Stratified Directional Sample Size Policy** (Option D: $n=30$ for English/Hindi targets; $n=10$ census for Marathi targets) amending the uniform 30-case proposal. | `multilingual_evaluation_manifest.proposed.json` line 109 |
| **DEC-8.5-EVAL-02** | Approve the **Directional Quality Threshold Floors** independently of observed model scores (e.g., Recall@1 $\ge 0.80$, MRR $\ge 0.80$ for provisional pass). | `multilingual_threshold_contract.proposed.json` line 3 |
| **DEC-8.5-EVAL-03** | Authorize the **Human Dual-Reviewer Adjudication Workflow** and appoint qualified bilingual evaluators for English, Hindi, and Marathi. | `multilingual_evaluation_contract.proposed.md` Section 4 |
| **DEC-8.5-EVAL-04** | Formally freeze the populated QREL dataset SHA-256 digest before authorizing execution of the candidate run. | `multilingual_evaluation_contract.proposed.md` Section 7 |

---

## 14. Explicit Blockers

Until the human decisions above are rendered, the following concrete blockers prevent evaluation execution:
1. **Unapproved Sample-Size Amendment:** Governance has not yet formally amended the uniform $\ge 30$ cases/direction policy.
2. **Unapproved Thresholds:** `threshold_contract.status` remains `"not_yet_defensible"`.
3. **Missing Human QREL Judgments:** Zero dual-reviewed, adjudicated `mnemo.multilingual-qrel/1` records exist on disk.

---

## 15. Lifecycle State

The repository lifecycle remains strictly preserved:

```text
DECLARED: PASS
IMPLEMENTED: PASS
CONFIGURED: PASS
BUILDABLE: PASS
READY: PASS
ACTIVE: PASS

EXPOSED: FALSE
EVALUATED: FALSE
VERIFIED: FALSE
CERTIFIED: FALSE
```
