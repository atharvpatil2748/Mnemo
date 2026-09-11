# Decision 7 Two-Stage Authorization Checklist — Proposed

Status before signature: **WP-10 NO-GO**  
All approvals must identify the approver and date. Blank boxes are not approval.

| Approval | Status before review | Approver | Date | Conditions/evidence reference |
|---|---|---|---|---|
| [ ] Evaluation structure approved | PROPOSED |  |  |  |
| [ ] Qrels schema approved | PROPOSED |  |  |  |
| [ ] Cohort methodology approved | PROPOSED |  |  |  |
| [ ] Metric definitions approved | PROPOSED |  |  |  |
| [ ] Uncertainty methodology approved | PROPOSED |  |  |  |
| [ ] Zero-tolerance gates approved | PROPOSED |  |  |  |
| [ ] Detector profile approved | FREEZE-READY / requires recorded approval |  |  |  |
| [ ] BGE preprocessing approved | FROZEN design / confirm implementation authority |  |  |  |
| [ ] Reranker policy approved | FROZEN design / confirm implementation authority |  |  |  |
| [ ] Dense backend approved | FROZEN design / confirm implementation authority |  |  |  |
| [ ] Two-stage implementation policy approved | OPEN |  |  |  |
| [ ] Numeric certification thresholds explicitly REMAIN OPEN | OPEN; must remain true |  |  |  |
| [ ] WP-10 engineering authorized only through BUILDABLE initially | OPEN |  |  |  |
| [ ] READY/ACTIVE/EXPOSED/VERIFIED/CERTIFIED require later evidence | REQUIRED BY ADR-0074 |  |  |  |
| [ ] Frozen multimodal state protected | REQUIRED |  |  |  |
| [ ] Golden Dataset protected | REQUIRED |  |  |  |

## Methodological choices requiring explicit approval or amendment

| Item | Proposal | Decision |
|---|---|---|
| Provisional cases per direction | 30 | APPROVE / AMEND / DEFER |
| Certification cases per direction | 75 | APPROVE / AMEND / DEFER |
| Proportion intervals | Wilson 95% without continuity correction | APPROVE / AMEND / DEFER |
| MRR/nDCG intervals | Direction-stratified percentile bootstrap | APPROVE / AMEND / DEFER |
| Bootstrap seed | 8501007 | APPROVE / AMEND / DEFER |
| Bootstrap resamples | 10,000 | APPROVE / AMEND / DEFER |
| Latency | Report-only until hardware-specific limits are approved | APPROVE / AMEND / DEFER |

## Explicit authorization statement

[ ] **APPROVE TWO-STAGE WP-10 PROCESS:** Engineering implementation may begin using the frozen evaluation structure while numeric certification thresholds remain OPEN. No lifecycle state beyond `BUILDABLE` may be claimed under this initial authorization. `READY`, `ACTIVE`, `EXPOSED`, `VERIFIED`, and `CERTIFIED` require their later evidence and approvals.

Governance owner: ____________________  Date: __________  Signature/record: __________

Evaluation owner: ____________________  Date: __________  Signature/record: __________

Security/provenance owner: ___________  Date: __________  Signature/record: __________

Final implementation decision: **GO THROUGH BUILDABLE / NO-GO / AMEND**

Until the final decision is signed, WP-10 remains NO-GO.

