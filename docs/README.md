# Mnemo Documentation

This is the entry point for Mnemo’s current architecture, governance,
certification, engineering history, and operational guidance. Current authority
is separated from point-in-time historical evidence.

## Current architecture

- [Architecture overview](architecture/README.md)
- [Mnemo architecture v2](architecture/current/mnemo_architecture_v2.md)
- [Engineering roadmap](architecture/current/mnemo_engineering_roadmap.md)
- [Phase 8.5 architecture](architecture/historical/phase8.5_architecture.md)
- [Certified single-production-path audit](reports/architecture/mnemo-v2-single-production-path-audit.md)

Current state: Phase 8.5 is completed/certified; Phase 8.6 is a validated,
isolated evaluation notebook; Phase 8.7 is the retrospective 14-tool MCP
capability milestone; and Phase 8.8 is designed but not implemented. Phase 9 is
the next implementation phase only after `Phase 8.8 VERIFIED → Phase 9 GO`.
The planned `search_images` tool becomes the fifteenth MCP tool only after its
Phase 8.8 implementation and verification.

## Architecture decisions

- [ADR index](adr/README.md)
- [Active ADRs](adr/active/)
- [Superseded ADRs](adr/superseded/)
- [ADR-0076 certification standard](adr/active/ADR-0076-project-owner-engineering-certification-standard.md)

## Governance

- [Governance index](governance/README.md)
- [Active governance](governance/active/)
- [Machine-readable contracts](governance/contracts/)
- [Proposals](governance/proposals/)
- [Historical governance](governance/historical/)

## Certification and evaluation

- [Report index](reports/README.md)
- [Current final certification](reports/certification/current/mnemo-v2-final-certification.md)
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
