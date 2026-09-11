# Decision 7 Governance Approval Checklist

Package status: **PROPOSED — REQUIRES HUMAN/GOVERNANCE APPROVAL**

Status vocabulary: `FROZEN`, `PROPOSED`, `OPEN`, `REQUIRES HUMAN APPROVAL`, `POST-IMPLEMENTATION`.

| Approval item | Current status | Proposed value/action | Approver | Decision/date |
|---|---|---|---|---|
| [ ] Corpus definition | PROPOSED | 44-document Phase 8.5 source corpus plus authorized immutable canonical/OCR/Vision evidence in a separate isolated evaluation snapshot |  |  |
| [ ] Directional cohort size | REQUIRES HUMAN APPROVAL | Provisional 30/direction; certification 75/direction |  |  |
| [ ] Secondary cohort size | REQUIRES HUMAN APPROVAL | 20 transliteration each; 30 mixed-script; 30 mixed-language; 20 OCR each; 20 Vision; 30 negative; 30 provenance/security |  |  |
| [ ] Query construction method | PROPOSED | Natural tasks; candidate rankings hidden; no expected tools/oracles |  |  |
| [ ] Qrels schema | PROPOSED | `multilingual_qrels.schema.json` |  |  |
| [ ] Reviewer qualification | REQUIRES HUMAN APPROVAL | Two independent reviewers jointly covering query/evidence languages |  |  |
| [ ] Adjudication policy | REQUIRES HUMAN APPROVAL | Qualified third-party adjudication; retain independent records |  |  |
| [ ] Candidate universe | OPEN | Freeze all authorized eligible evidence identities before measurement |  |  |
| [ ] Recall definitions | PROPOSED | Macro query Recall@1/3/5/10 over valid grade-2 qrels |  |  |
| [ ] MRR definition | PROPOSED | First valid grade-2 evidence; macro per direction |  |  |
| [ ] nDCG@10 definition | PROPOSED | Gain `2^grade-1`, log2 discount, cutoff 10, macro per direction |  |  |
| [ ] Pairwise accuracy | PROPOSED | Strict decisive judged pairs only; ties/unjudged excluded |  |  |
| [ ] No-answer policy | PROPOSED | Separate false-support and false-publication rates |  |  |
| [ ] Uncertainty method | REQUIRES HUMAN APPROVAL | Wilson 95% plus stratified query bootstrap |  |  |
| [ ] Bootstrap seed | REQUIRES HUMAN APPROVAL | `8501007` |  |  |
| [ ] Bootstrap resamples | REQUIRES HUMAN APPROVAL | `10000` |  |  |
| [ ] Latency policy | REQUIRES HUMAN APPROVAL | Report-only until frozen hardware profile and limits |  |  |
| [ ] Threshold derivation procedure | PROPOSED | Freeze/judge first, independent floors, then candidate run |  |  |
| [ ] Numeric certification floors | OPEN / POST-IMPLEMENTATION | NOT YET DEFENSIBLE |  |  |
| [ ] WP-16 pass criteria | OPEN / POST-IMPLEMENTATION | Apply governed behavioral thresholds without revealing oracle |  |  |
| [ ] Zero-tolerance gates | PROPOSED | Every listed correctness/security violation allowed count = 0 |  |  |
| [ ] Reranker contradiction resolution | OPEN | Locate raw output or rerun frozen legacy cohort and retain rankings |  |  |
| [ ] Permission to begin WP-10 implementation | OPEN | Explicit governance decision required; current state remains NO-GO |  |  |

## Required signatures

- Governance owner: ____________________  Date: __________  Decision: __________
- Evaluation owner: ____________________  Date: __________  Decision: __________
- Security/provenance owner: ___________  Date: __________  Decision: __________
- WP-10 implementation authorization: ___ Date: __________  GO / NO-GO

Approval of structure does not imply approval of numeric floors, behavioral verification, or certification.

