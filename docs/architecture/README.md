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
- [Phase 8.5 architecture](historical/phase8.5_architecture.md)
- [Single production path audit](../reports/architecture/mnemo-v2-single-production-path-audit.md)

The current certified topology is content-addressed filesystem storage plus an
immutable SQLite corpus and a separate mutable operational SQLite store.
Qdrant is an optional derived vector-scale path; SurrealDB is a partial future
graph path. Phase 8.8 is designed but unimplemented and gates Phase 9.
