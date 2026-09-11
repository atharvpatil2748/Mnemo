# Mnemo Phase 8.6 — Evaluation Corpus Expansion Decision Register
**Path:** `docs/governance/proposals/phase8_6_format_diverse_multilingual_evaluation_corpus/PHASE8_6_EVALUATION_CORPUS_EXPANSION_DECISION_REGISTER.md`  
**Date:** September 2, 2026  
**Status:** PROPOSED — ALL DECISIONS PENDING HUMAN GOVERNANCE REVIEW  
**Authority:** Mnemo Human Architecture & Governance Committee

---

## Executive Summary

This register formally documents the sixteen (16) architectural, governance, and licensing decisions required to authorize, acquire, structure, build, and evaluate the **Phase 8.6 Format-Diverse Multilingual Evaluation Corpus**.

All decisions are strictly recorded as **PENDING HUMAN GOVERNANCE REVIEW**. In accordance with repository safety rules, no engineering agent may mark these decisions as approved or proceed with external downloads or ingestion prior to formal human authorization.

---

## Summary Matrix of Decisions

| Decision ID | Area | Core Question | Recommended Option | Status |
| :--- | :--- | :--- | :--- | :---: |
| **DEC-P8.6-01** | Architecture | Authorize a separate Phase 8.6 Format-Diverse Multilingual Evaluation Corpus? | Option A: Establish separate Phase 8.6 expansion | **PENDING** |
| **DEC-P8.6-02** | Namespace | Corpus directory naming and namespace? | Option A: `evaluationDataset/Phase 8.6 Format-Diverse Multilingual Evaluation Corpus` | **PENDING** |
| **DEC-P8.6-03** | Immutability | How to preserve the Phase 8.5 Golden Corpus boundary? | Option A: Strict physical and cryptographic freeze | **PENDING** |
| **DEC-P8.6-04** | Acquisition | External source acquisition protocol and governance? | Option A: Pre-approved whitelist with dual sign-off | **PENDING** |
| **DEC-P8.6-05** | Licensing | Licensing and evaluation use verification standards? | Option A: Verified Open/Public Domain only with officer sign-off | **PENDING** |
| **DEC-P8.6-06** | Hindi Targets | Minimum Hindi evidence requirement and document pool? | Option A: $\ge 5$ diverse documents, $\ge 150$ chunks, $n=30$ target | **PENDING** |
| **DEC-P8.6-07** | Marathi Targets | Marathi corpus expansion strategy? | Option B: Acquire 3-5 Marathi docs to transition to $n=30$ | **PENDING** |
| **DEC-P8.6-08** | Foreign Languages | Policy for admitting additional languages beyond en/hi/mr? | Option A: Formal 9-stage admission pipeline on demand | **PENDING** |
| **DEC-P8.6-09** | Anti-Confounding | Clustering mitigation and anti-confounding rules? | Option A: Proposed 20% chunk cap per document, 3+ domains | **PENDING** |
| **DEC-P8.6-10** | Case Authoring | Query authoring and non-duplication rules? | Option A: Re-enforce Phase 8.5 policy with blinded authoring | **PENDING** |
| **DEC-P8.6-11** | QREL Reviewers | Human QREL adjudicator competency requirements? | Option A: Dual native/fluent speakers + 3rd adjudicator | **PENDING** |
| **DEC-P8.6-12** | Thresholds | Threshold contract derivation and approval process? | Option A: Post-pilot human governance sign-off | **PENDING** |
| **DEC-P8.6-13** | Contamination | Benchmark contamination and evaluation independence? | Option A: Strict separation of smoke, dev, and eval corpora | **PENDING** |
| **DEC-P8.6-14** | Generation | Storage and generation identity for expanded corpus? | Option A: New isolated build run, DB, and generation IDs | **PENDING** |
| **DEC-P8.6-15** | Lifecycle | Lifecycle state management across Phase 8.5 and Phase 8.6? | Option A: Decoupled lifecycle tracking per phase | **PENDING** |
| **DEC-P8.6-16** | Acquisition Auth | Granting final execution authorization to download data? | Option A: Block downloads until DEC-P8.6-01 through 06 approved | **PENDING** |

---

## Detailed Decision Records

### DEC-P8.6-01: Establishment of Phase 8.6 Format-Diverse Multilingual Evaluation Corpus
- **Question:** Should Mnemo establish a new, separately governed Phase 8.6 specifically dedicated to expanding evaluation evidence for multilingual retrieval?
- **Recommended Option:** **Option A — Establish Phase 8.6 as a dedicated Evaluation Corpus Expansion phase.**
- **Alternative Options:**
  - *Option B:* Modify the existing Phase 8.5 Golden Corpus by injecting new Hindi documents.
  - *Option C:* Force evaluation on Phase 8.5 by lowering Hindi sample size to $n=1$.
  - *Option D:* Synthetically generate Hindi passages using LLMs and inject them into V2.
- **Rationale:** Forensic inspection of the frozen Phase 8.5 V2 database proved that only **one single coherent Hindi text chunk** exists. Option B violates the byte-for-byte immutability of the Golden Corpus and invalidates prior baselines. Option C produces statistically meaningless evaluation ($n=1$). Option D manufactures synthetic hallucinated evidence. Establishing Phase 8.6 provides an honest, auditable, scientifically sound expansion path.
- **Evidence:** `V2_GOVERNED_CASE_INVENTORY_PREPARATION_REPORT.md` Section 5.
- **Owner / Authority:** Human Architecture & Governance Committee.
- **Status:** **PENDING HUMAN GOVERNANCE REVIEW**

---

### DEC-P8.6-02: Corpus Naming and Directory Namespace
- **Question:** Under what directory and namespace should the expansion corpus reside?
- **Recommended Option:** **Option A — `evaluationDataset/Phase 8.6 Format-Diverse Multilingual Evaluation Corpus/`**
- **Alternative Options:**
  - *Option B:* `goldenDataset/Phase 8.6 Expansion/` (Risks confusing Golden Corpus with expansion corpus).
  - *Option C:* `data/evaluation_expansion/` (Lacks explicit phase tracking).
- **Rationale:** Clear naming under `evaluationDataset/` prevents any confusion with `goldenDataset/`, making it impossible for automated ingestion scripts to accidentally mutate or cross-contaminate the historical Phase 8.5 corpus.
- **Evidence:** `PHASE8_6_EVALUATION_CORPUS_SCHEMA.proposed.json`.
- **Owner / Authority:** Repository Maintainer / Engineering Lead.
- **Status:** **PENDING HUMAN GOVERNANCE REVIEW**

---

### DEC-P8.6-03: Golden Corpus Boundary and Immutability
- **Question:** How shall the repository guarantee the complete immutability of the Phase 8.5 Golden Corpus?
- **Recommended Option:** **Option A — Strict physical, cryptographic, and pipeline freeze.**
- **Alternative Options:**
  - *Option B:* Soft convention without automated CI hash verification.
- **Rationale:** All 4 protected hashes (`manuscript.pdf`, `Valmiki Ramayana...pdf`, `mnemo.db`, `Active Alias Digest`) must be asserted in all CI workflows. Any change to `goldenDataset/` causes an immediate build failure.
- **Evidence:** Pre-check assertion script `scratch/verify_case_inventory.py`.
- **Owner / Authority:** Quality Assurance & Governance Lead.
- **Status:** **PENDING HUMAN GOVERNANCE REVIEW**

---

### DEC-P8.6-04: External Source Acquisition Protocol
- **Question:** What protocol must be followed before acquiring external documents for Phase 8.6?
- **Recommended Option:** **Option A — Formal pre-acquisition manifest with dual review before downloading.**
- **Alternative Options:**
  - *Option B:* Autonomous scraping by AI agents without pre-approval.
  - *Option C:* Ad-hoc manual downloading without provenance tracking.
- **Rationale:** Uncontrolled web scraping risks ingesting proprietary, toxic, low-quality, or contaminated text. A curated candidate list ensures complete provenance, verifiable URLs, and strict legal compliance.
- **Evidence:** `PHASE8_6_CORPUS_ADMISSION_POLICY.proposed.md` Section 2.
- **Owner / Authority:** Legal / Governance Officer.
- **Status:** **PENDING HUMAN GOVERNANCE REVIEW**

---

### DEC-P8.6-05: Licensing and Evaluation Use Verification
- **Question:** What license types and proof of evaluation permissions are mandatory for candidate documents?
- **Recommended Option:** **Option A — Verified Public Domain, CC0, CC-BY 4.0, or Open Government Data License only, certified by a human reviewer.**
- **Alternative Options:**
  - *Option B:* Assume all web-accessible PDFs are permissible under fair use.
  - *Option C:* Exclude all external documents and use only synthetic data.
- **Rationale:** Option B creates unacceptable legal liability. Option C harms retrieval evaluation fidelity. Open licenses guarantee unrestricted evaluation and benchmark publication rights.
- **Evidence:** `PHASE8_6_CORPUS_ADMISSION_POLICY.proposed.md` Section 2.3.
- **Owner / Authority:** Repository Legal / Governance Officer.
- **Status:** **PENDING HUMAN GOVERNANCE REVIEW**

---

### DEC-P8.6-06: Minimum Hindi Evidence Requirement & Sizing
- **Question:** What is the minimum target evidence requirement to establish a valid Hindi evaluation cohort?
- **Recommended Option:** **Option A — Ingest 5 to 10 distinct, substantive Hindi documents yielding $\ge 150$ eligible semantic chunks, supporting $n=30$ independent cases per direction ($90$ queries total).**
- **Alternative Options:**
  - *Option B:* Ingest 1 large Hindi book (e.g. Premchand novel) yielding 50 chunks (Concentration risk).
  - *Option C:* Settle for $n=10$ census using Ramayana foreword and fragmented OCR.
- **Rationale:** Ingesting 5 to 10 documents across literature, science, history, and administration ensures domain diversity and allows enforcing the 20% document-capping rule ($\le 6$ queries per document), eliminating domain confounding.
- **Evidence:** `V2_GOVERNED_CASE_INVENTORY_PREPARATION_REPORT.md` Section 5.
- **Owner / Authority:** Multilingual NLP / Evaluation Lead.
- **Status:** **PENDING HUMAN GOVERNANCE REVIEW**

---

### DEC-P8.6-07: Marathi Target Corpus Expansion Strategy
- **Question:** Should Marathi target evidence also be expanded in Phase 8.6, or remain strictly at the 10-chunk census?
- **Recommended Option:** **Option B — Acquire 3 to 5 diverse Marathi documents to expand Marathi evidence to $\ge 60$ chunks, allowing Marathi cohorts to transition from $n=10$ census to $n=30$ standard provisional.**
- **Alternative Options:**
  - *Option A:* Leave Marathi unchanged ($n=10$ census in `manuscript.pdf`).
  - *Option C:* Expand Marathi only if foreign languages are added.
- **Rationale:** While the 10-chunk census in `manuscript.pdf` is legally valid under Option D, expanding Marathi to $n=30$ standard provisional creates perfect symmetry across all three languages (English 30, Hindi 30, Marathi 30 across all 9 directions = 270 answerable cases).
- **Evidence:** `HYBRID_STRATIFIED_EVALUATION_CONTRACT_AMENDMENT.proposed.md`.
- **Owner / Authority:** Multilingual NLP / Evaluation Lead.
- **Status:** **PENDING HUMAN GOVERNANCE REVIEW**

---

### DEC-P8.6-08: Foreign Language Extension Protocol
- **Question:** How shall additional foreign languages (e.g. French, Spanish, Tamil, German) be admitted in the future?
- **Recommended Option:** **Option A — Reusable 9-stage onboarding pipeline executed on-demand per language.**
- **Alternative Options:**
  - *Option B:* Ad-hoc language additions without formal governance.
  - *Option C:* Freeze the repository to en/hi/mr permanently.
- **Rationale:** The 9-stage admission pipeline provides a repeatable, governed protocol for expanding into new languages without scope creep or compromise of evidence quality.
- **Evidence:** `PHASE8_6_CORPUS_ADMISSION_POLICY.proposed.md` Section 3.3.
- **Owner / Authority:** Architecture Committee.
- **Status:** **PENDING HUMAN GOVERNANCE REVIEW**

---

### DEC-P8.6-09: Clustering Mitigation and Anti-Confounding Rules
- **Question:** What rules govern target sampling to mitigate document concentration and semantic overlap?
- **Recommended Option:** **Option A — Enforce maximum 20% target allocation per document as a proposed concentration limit ($\le 6$ targets per doc for $n=30$), minimum 3 distinct domains, and zero duplicate query semantics, recognizing that chunks mitigate clustering rather than guaranteeing textbook i.i.d. independence.**
- **Alternative Options:**
  - *Option B:* Random sampling with replacement across chunks.
  - *Option C:* No document capping.
- **Rationale:** Mitigates single-document domination and concentration bias across language cohorts, while acknowledging that chunks from the same document exhibit intra-cluster correlation.
- **Evidence:** `PHASE8_6_CORPUS_ADMISSION_POLICY.proposed.md` Section 5.
- **Owner / Authority:** Evaluation Statistics Lead.
- **Status:** **PENDING HUMAN GOVERNANCE REVIEW**

---

### DEC-P8.6-10: Case Authoring and Blinded Formulation Policy
- **Question:** How shall queries be authored to avoid evaluation leakage?
- **Recommended Option:** **Option A — Queries must be authored blind to model retrieval rankings, grounded strictly in source semantic assertions, and validated against negative controls.**
- **Alternative Options:**
  - *Option B:* Allow authoring queries by reviewing top-ranked model outputs.
- **Rationale:** Reviewing model rankings during query authoring introduces severe benchmark contamination and circular validation.
- **Evidence:** `CASE_AUTHORING_POLICY.proposed.md`.
- **Owner / Authority:** Evaluation Lead.
- **Status:** **PENDING HUMAN GOVERNANCE REVIEW**

---

### DEC-P8.6-11: Human QREL Adjudicator Competency Requirements
- **Question:** What qualifications are mandatory for human QREL reviewers?
- **Recommended Option:** **Option A — Dual independent human reviews by native/fluent speakers in the relevant language, with mandatory third-reviewer adjudication in case of grade discordance. Zero automated LLM judgments.**
- **Alternative Options:**
  - *Option B:* Use LLM-as-a-judge for QREL generation.
  - *Option C:* Single reviewer without adjudication.
- **Rationale:** LLM-generated QRELs create systemic evaluation bias, circular hallucination, and fail regulatory audit standards.
- **Evidence:** `mnemo.models.multilingual_evaluation.EvidenceQrelV2`.
- **Owner / Authority:** Human Governance & Ethics Board.
- **Status:** **PENDING HUMAN GOVERNANCE REVIEW**

---

### DEC-P8.6-12: Threshold Contract Derivation and Approval
- **Question:** How and when shall numeric performance thresholds for Phase 8.6 be established?
- **Recommended Option:** **Option A — Thresholds remain strictly `NOT YET DEFENSIBLE` until pilot evaluation data is collected, analyzed, and approved by human governance.**
- **Alternative Options:**
  - *Option B:* Let AI agents invent numeric thresholds prior to evaluation.
  - *Option C:* Back-fit thresholds to match observed model scores.
- **Rationale:** Back-fitting thresholds to model scores is scientifically fraudulent. Inventing numbers without statistical justification violates repository governance.
- **Evidence:** `multilingual_threshold_contract.proposed.json`.
- **Owner / Authority:** Human Governance Board.
- **Status:** **PENDING HUMAN GOVERNANCE REVIEW**

---

### DEC-P8.6-13: Benchmark Contamination & Evaluation Independence
- **Question:** How to prevent data leakage between development/debugging workflows and formal evaluation?
- **Recommended Option:** **Option A — Absolute segregation: the 18-case cohort is permanently designated as an adapter smoke test; Phase 8.6 evaluation queries are held in administrative escrow as an operational governance procedure; no adapter tuning on evaluation queries is permitted.**
- **Alternative Options:**
  - *Option B:* Use the same queries for both dev and test.
- **Rationale:** Strict separation guarantees genuine evaluation integrity without claiming automated runtime escrow features.
- **Evidence:** `V2_POST_EVALUATION_DETERMINATION_AUDIT.md`.
- **Owner / Authority:** Architecture Committee.
- **Status:** **PENDING HUMAN GOVERNANCE REVIEW**

---

### DEC-P8.6-14: Storage, Generation, and Database Isolation
- **Question:** Should the expansion corpus be ingested into the existing V2 database or a new isolated build?
- **Recommended Option:** **Option A — A new isolated build run (`build-phase9-01`), new generation UUIDs, new alias set, and a dedicated database (`scratch/phase9_expansion/mnemo.db`).**
- **Alternative Options:**
  - *Option B:* Mutate the current active V2 database in `scratch/phase8_5_full_multilingual_v2/`.
- **Rationale:** Mutating the existing V2 database breaks historical auditability and invalidates Phase 8.5 active alias digests.
- **Evidence:** `V2_DATABASE_ARTIFACT_IDENTITY.json`.
- **Owner / Authority:** Storage & Infrastructure Lead.
- **Status:** **PENDING HUMAN GOVERNANCE REVIEW**

---

### DEC-P8.6-15: Repository Lifecycle State Management
- **Question:** How shall lifecycle states be tracked across Phase 8.5 and Phase 8.6?
- **Recommended Option:** **Option A — Decoupled lifecycle tracking. Phase 8.5 remains frozen at `ACTIVE: PASS`, `EVALUATED: FALSE`. Phase 8.6 initiates independently at `DECLARED: PASS`.**
- **Alternative Options:**
  - *Option B:* Advance Phase 8.5 to EVALUATED based on Phase 8.6 data.
- **Rationale:** Phase 8.5 cannot be certified retroactively by future data. Each phase must report its own immutable lifecycle trajectory.
- **Evidence:** Repository Lifecycle Governance Standard.
- **Owner / Authority:** Architecture Committee.
- **Status:** **PENDING HUMAN GOVERNANCE REVIEW**

---

### DEC-P8.6-16: Final Data Acquisition & Ingestion Authorization
- **Question:** Is authorization granted to begin downloading external documents and executing ingestion?
- **Recommended Option:** **Option A — NO. Acquisition remains strictly BLOCKED until DEC-P8.6-01 through DEC-P8.6-06 are formally signed off by human governance.**
- **Alternative Options:**
  - *Option B:* Authorize immediate downloading and ingestion.
- **Rationale:** Governance first. Downloading data before licensing and admission policies are approved introduces regulatory and architectural risk.
- **Evidence:** Phase 8.6 Safety Invariants.
- **Owner / Authority:** Human Governance Board.
- **Status:** **PENDING HUMAN GOVERNANCE REVIEW (ACQUISITION BLOCKED)**
