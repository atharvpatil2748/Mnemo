# Mnemo Governance

Governance is separated into current authority, machine-readable contracts,
proposals, and immutable historical records.

## Current authority

- [Active governance](active/)
- [ADR-0076 project-owner engineering certification standard](../adr/active/ADR-0076-project-owner-engineering-certification-standard.md)
- [ADR-0079 automatic representation-complete V2 retrieval](../adr/active/ADR-0079-automatic-representation-complete-v2-retrieval.md)
- [Final Mnemo V2 certification](../reports/certification/current/mnemo-v2-final-certification.md)
- [Governed evaluation-harness policy](active/evaluation_harness_governance.md)
- [Phase 8.6 future serving-role promotion gate](active/phase_8_6_serving_promotion_gate.md)
- [Proprietary distribution policy for the current tree](active/proprietary_distribution_policy.md)
- [Machine-readable contracts](contracts/)

The canonical runtime declaration remains
`config/production/full_multilingual_v2.production.json`. ADR-0076 applies to
the exact certified production identity and narrowly amends ADR-0070 for that
scope.
The earlier five-module Stage 6 batch has [independent local acceptance](../reports/operations/mnemo-stage-6-forensic-remediation-and-acceptance.md).
Modules 8.8.10 and 8.8.11 now have a [combined local forensic acceptance and
Stage 6 closure](../reports/operations/mnemo-stage-7-forensic-audit-remediation-and-stage-6-closure.md)
after correction of a structured capability-readiness mismatch. This does
not publish or deploy the new working-tree changes or activate new production
data. The
owner's proprietary-distribution decision concerns the current project-owned
tree and does not amend accepted runtime ADRs or historical rights.

## Proposals

The [proposals](proposals/) tree preserves proposed and ratified design packs in
their original workstream groupings. Proposal status is stated by each record.

## Historical governance

[Historical governance](historical/) contains completed plans, closure reports,
and reconciliation records. Phase gate evidence is organized separately under
[evidence](../evidence/README.md), and governance-related audits are indexed
under [reports](../reports/README.md).
