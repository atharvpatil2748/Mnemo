# Mnemo Documentation

This is the entry point for Mnemo’s current architecture, governance,
certification, engineering history, and operational guidance. Current authority
is separated from point-in-time historical evidence.

Mnemo-owned documentation is proprietary: Copyright © 2026 Atharv Patil. All
rights reserved. See the [distribution policy](governance/active/proprietary_distribution_policy.md).

## Current architecture

The [ordered-text delivery follow-up](reports/operations/mnemo-ordered-text-delivery-remediation.md)
certifies mixed persisted blocks/text locally and exposes binary transfer metadata
in structured MCP content. The [owner-authorized isolated fixture](reports/operations/mnemo-isolated-external-text-fixture.md)
now passes authenticated public HTTPS reconstruction. Its separate ChatGPT
connection, client metadata refresh and [independent certification handoff](reports/operations/mnemo-ordered-text-external-handoff.md)
remain owner-controlled. Protected production parsed representations have not
been created or activated.

- [Architecture overview](architecture/README.md)
- [Mnemo architecture v2](architecture/current/mnemo_architecture_v2.md)
- [Engineering roadmap](architecture/current/mnemo_engineering_roadmap.md)
- [ADR-0079 automatic V2 retrieval decision](adr/active/ADR-0079-automatic-representation-complete-v2-retrieval.md)
- [ADR-0080 Phase 8.9 unified authorized retrieval plan](adr/active/ADR-0080-phase-8-9-unified-authorized-retrieval-plan.md)
- [ADR-0081 explicit unindexed production baseline](adr/active/ADR-0081-pre-phase-8-9-unindexed-production-baseline.md)
- [Pre-Phase-8.9 decommission execution record](reports/architecture/phase-8-9-runtime-cutover-execution.md)
- [Pre-Phase-8.9 documentation consistency audit](reports/architecture/pre-phase-8-9-documentation-consistency-audit.md)
- [Pre-Phase-8.9 final readiness report](reports/architecture/pre-phase-8-9-final-readiness-report.md)
- [Phase 8.5 architecture](architecture/historical/phase8.5_architecture.md)
- [Certified single-production-path audit](reports/architecture/mnemo-v2-single-production-path-audit.md)

Current state: Phase 8.5's certification and Phase 8.6's evaluation are
historical exact-identity evidence; their known legacy indexes have been
decommissioned. Production is offline and `UNINDEXED`. Phase 8.7 is the retrospective 14-tool MCP
capability milestone; and Phase 8.8 is in progress but not verified. Phase 9 is
planned only after an evidence-bound `Phase 8.9 GO`. Phase 8.8's active plan
ends at Module 8.8.8 without asserting phase-wide verification.
The working tree now registers an additive fifteenth tool, `query_notebook_v2`,
under ADR-0079; registration does not establish external certification. A
mandatory `search_images` tool is retired from the active plan; Phase 8.9
proposes ordinary shared hybrid search instead. ADR-0077's 8.8.14a mutable-workspace
boundary and mandatory read-only fallback are implemented, certified, and
accepted. 8.8.14b has selected and certified authenticated HTTP FinalQA V2 as
production chat; 8.8.14c has reconciled current documentation. Module 8.8.1
server-owned startup convergence is certified. [Stage 5](reports/operations/mnemo-phase-8-8-stage-5-acceptance.md)
has local implementation acceptance (8.8.2a–e/g, 8.8.3a–d, 8.8.6a–c),
not deployment or external verification of the complete Stage 5 code set.
Task 8.8.2f was subsequently implemented locally using 8.8.7 typed errors.
The first [combined Stage 6 audit](reports/operations/mnemo-stage-6-combined-forensic-audit.md)
found F-1 partitioned principal propagation and F-2 nested metadata defects;
the [dated remediation and independent reassessment](reports/operations/mnemo-stage-6-forensic-remediation-and-acceptance.md)
accepted 8.8.5, 8.8.7, 8.8.2f, 8.8.4 and 8.8.8 locally after correction.
GitHub publication does not establish deployment or external re-verification.
The [combined independent 8.8.10/8.8.11 audit](reports/operations/mnemo-stage-7-forensic-audit-remediation-and-stage-6-closure.md)
repaired a scoped structured-readiness contradiction and formally closes the
Stage 6 **local forensic** branch. The 2026-09-27 tunnel restart was historical;
the tunnel is now offline, its historical credential revoked, and production
explicitly `UNINDEXED`. Local acceptance is not current serving certification.
The [final contract audit](reports/operations/mnemo-stage-6-final-contract-and-acceptance-gate-audit.md)
records the cursor budget boundary, actor-binding correction and retest gates.
8.8.10's [local implementation](reports/operations/mnemo-module-8-8-10-local-implementation.md)
enforces the evaluation-only store boundary and specifies a future promotion
gate without activating it. Module 8.8.9 four-transport behavioral parity and the
Phase 8.8 gate remain separate.
Module 8.8.11's [local implementation](reports/operations/mnemo-module-8-8-11-local-implementation.md)
validates the authorized typed structured route and scope-qualified availability;
it does not activate structured retrieval globally. The separately named
Product Stage 7 is not this Phase 8.8 branch; no Phase 8.8 Stage 7 scope or
acceptance gate is defined in the canonical roadmap.

## Architecture decisions

The [complete-resource delivery follow-up](reports/operations/mnemo-complete-resource-delivery-remediation.md)
adds actor-bound delivery cursors, explicit binary ranges and ordered persisted-block
text delivery. Actual local MCP multipart PDF/JPEG reconstruction passes; complete
parsed text for the specified production versions remains unavailable and external
ChatGPT attachment reconstruction is still an independent verification gate.

- [ADR index](adr/README.md)
- [Active ADRs](adr/active/)
- [Superseded ADRs](adr/superseded/)
- [ADR-0076 certification standard](adr/active/ADR-0076-project-owner-engineering-certification-standard.md)
- [ADR-0077 governed mutable workspace boundary](adr/active/ADR-0077-governed-mutable-workspace-boundary.md)
- [ADR-0078 generation-aware production credentials](adr/active/ADR-0078-generation-aware-production-credential-lifecycle.md)

ADR-0079 governs a separate V2 normal-query path: retained V1 notebook query
and cross-notebook search remain canonical-text-only. The shared application
service is intended for MCP, HTTP and future native UI. It selects authorized,
ready canonical/OCR/Vision evidence itself and preserves actual image-occurrence
and derivation provenance. Stored OCR/Vision records alone do not make search
active. Certified production remains immutable; evaluation rebuilding requires
new governed identities, not edits to the protected corpus. Implementation and
certification status of this V2 path are separate from ADR acceptance. The current
implementation returns governed typed evidence and a representation decision
report, with `answer_status=not_generated`; it does not yet synthesize an answer.

## Governance

- [Governance index](governance/README.md)
- [Active governance](governance/active/)
- [Machine-readable contracts](governance/contracts/)
- [Proprietary distribution policy](governance/active/proprietary_distribution_policy.md)
- [Proposals](governance/proposals/)
- [Historical governance](governance/historical/)

## Certification and evaluation

- [Report index](reports/README.md)
- [Current final certification](reports/certification/current/mnemo-v2-final-certification.md)
- [Module 8.8.1 certification](reports/operations/mnemo-module-8-8-1-certification.md)
- [Module 8.8.1 forensic audit](reports/operations/mnemo-module-8-8-1-forensic-audit.md)
- [Phase 8.8 Stage 5 local acceptance](reports/operations/mnemo-phase-8-8-stage-5-acceptance.md)
- [Evaluation reports](reports/evaluation/)
- [Audit reports](reports/audits/)
- [Performance reports](reports/performance/)

## Engineering history

- [Milestones](milestones/README.md)
- [Module documentation](modules/README.md)
- [Releases](releases/README.md)
- [Changelog](changelog/README.md)
- [Evidence records](evidence/README.md)

## Operations

- [Runbooks](runbooks/README.md)

## Status rules

- ADRs are immutable decisions; a later ADR may narrowly supersede one.
- Files under `historical/` are point-in-time evidence, not current runtime
  declarations.
- Current production selection is explicitly `UNINDEXED` in
  [`config/production/runtime-selection.json`](../config/production/runtime-selection.json).
  The retained [Full V2 manifest](../config/production/full_multilingual_v2.production.json)
  and final signed certification describe a retired exact identity, not a
  selectable current production index.
