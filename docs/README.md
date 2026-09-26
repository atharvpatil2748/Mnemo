# Mnemo Documentation

This is the entry point for Mnemo’s current architecture, governance,
certification, engineering history, and operational guidance. Current authority
is separated from point-in-time historical evidence.

Mnemo-owned documentation is proprietary: Copyright © 2026 Atharv Patil. All
rights reserved. See the [distribution policy](governance/active/proprietary_distribution_policy.md).

## Current architecture

- [Architecture overview](architecture/README.md)
- [Mnemo architecture v2](architecture/current/mnemo_architecture_v2.md)
- [Engineering roadmap](architecture/current/mnemo_engineering_roadmap.md)
- [Phase 8.5 architecture](architecture/historical/phase8.5_architecture.md)
- [Certified single-production-path audit](reports/architecture/mnemo-v2-single-production-path-audit.md)

Current state: Phase 8.5 is completed/certified; Phase 8.6 is a validated,
isolated evaluation notebook; Phase 8.7 is the retrospective 14-tool MCP
capability milestone; and Phase 8.8 is in progress but not verified. Phase 9 is
the next implementation phase only after `Phase 8.8 VERIFIED → Phase 9 GO`.
The planned `search_images` tool becomes the fifteenth MCP tool only after its
Phase 8.8 implementation and verification. ADR-0077's 8.8.14a mutable-workspace
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
GitHub publication does not establish deployment or external re-verification. Stage 6
still requires 8.8.10/8.8.11; 8.8.9 four-transport behavioral parity and the
Phase 8.8 gate remain separate.

## Architecture decisions

- [ADR index](adr/README.md)
- [Active ADRs](adr/active/)
- [Superseded ADRs](adr/superseded/)
- [ADR-0076 certification standard](adr/active/ADR-0076-project-owner-engineering-certification-standard.md)
- [ADR-0077 governed mutable workspace boundary](adr/active/ADR-0077-governed-mutable-workspace-boundary.md)
- [ADR-0078 generation-aware production credentials](adr/active/ADR-0078-generation-aware-production-credential-lifecycle.md)

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
- The current production configuration is
  [`config/production/full_multilingual_v2.production.json`](../config/production/full_multilingual_v2.production.json).
- The current certified lifecycle is documented by the final certification
  report and its signed machine-readable evidence.
