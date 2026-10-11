# Mnemo Architecture

- [Current architecture](current/) contains the broad architecture
  specifications used to understand the certified system.
- [Historical architecture](historical/) contains superseded plans and scoped
  roadmaps retained as engineering history.
- Architecture audits and production-path reconciliation reports live under
  [reports/architecture](../reports/architecture/).

Current starting points:

- [Mnemo architecture v2](current/mnemo_architecture_v2.md)
- [Engineering roadmap](current/mnemo_engineering_roadmap.md)
- [ADR-0079 automatic representation-complete V2 retrieval](../adr/active/ADR-0079-automatic-representation-complete-v2-retrieval.md)
- [ADR-0080 Phase 8.9 unified authorized retrieval plan](../adr/active/ADR-0080-phase-8-9-unified-authorized-retrieval-plan.md)
- [ADR-0081 pre-Phase-8.9 unindexed baseline](../adr/active/ADR-0081-pre-phase-8-9-unindexed-production-baseline.md)
- [Decoupling and reset execution record](../reports/architecture/phase-8-9-runtime-cutover-execution.md)
- [Pre-Phase-8.9 documentation consistency audit](../reports/architecture/pre-phase-8-9-documentation-consistency-audit.md)
- [Pre-Phase-8.9 final readiness report](../reports/architecture/pre-phase-8-9-final-readiness-report.md)
- [Phase 8.9 documentation re-baseline review](../reports/architecture/phase-8-9-roadmap-rebaseline.md)
- [Phase 8.5 architecture](historical/phase8.5_architecture.md)
- [Single production path audit](../reports/architecture/mnemo-v2-single-production-path-audit.md)

Production is currently offline and explicitly `UNINDEXED`; the historical
certified SQLite topology is retained as design and certification history,
not live serving authority. ADR-0077 accepts an explicit absolute, separately governed mutable
filesystem + SQLite user workspace with mandatory server-enforced read-only
fallback; its implementation and certification are accepted. Authenticated HTTP
FinalQA V2 is the accepted production chat path; legacy V1 WebSocket is not.
Qdrant is an optional derived vector-scale path; SurrealDB is a partial future
graph path. Phase 8.8's active plan ends at Module 8.8.8 without a phase-wide
verification claim. Planned Phase 8.9 owns shared authorized hybrid search,
unfinished parity/provenance and the explicit Phase 9 GO/NO-GO gate.
The additive working-tree `query_notebook_v2` shares one server-owned evidence
application service between MCP and HTTP. It is evidence-first, not a certified
answer generator, and V1 query/search remain canonical-only. OCR/Vision enter
only through ready active V2 projections; the protected corpus is unchanged.
The corrected five-module Stage 6 batch is [independently accepted locally](../reports/operations/mnemo-stage-6-forensic-remediation-and-acceptance.md);
8.8.10 and 8.8.11 have separate historical local acceptance. Current project-owned material
follows the [proprietary distribution policy](../governance/active/proprietary_distribution_policy.md).
