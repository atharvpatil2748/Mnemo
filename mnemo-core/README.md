# mnemo-core

Mnemo-owned code and documentation are proprietary: Copyright © 2026 Atharv
Patil. All rights reserved. See the [current-tree distribution policy](../docs/governance/active/proprietary_distribution_policy.md).

`mnemo-core` is the provider-neutral domain and pipeline library for the Mnemo
local knowledge engine. It contains the typed ingestion, document/version/chunk
identity, storage, retrieval, reranking, evidence, provenance, ContextBuilder,
FinalQA, structured, multilingual, OCR, Vision, CLIP, processing, and delivery
contracts used by the server composition.

The historically certified V2 profile used content-addressed filesystem storage, an
immutable SQLite corpus with FTS5 and governed BGE-M3 vectors, and a separate
purpose-specific mutable FinalQA operational SQLite store. That operational
store is not a general user workspace. ADR-0077 accepts a separately governed,
explicitly configured absolute mutable filesystem + SQLite workspace with
mandatory server-enforced read-only fallback; its typed storage roles and
pre-I/O boundary are implemented and certified. Qdrant remains an
optional V1/future vector-scale adapter; SurrealDB remains a partial future graph
adapter. The retired certified composition used BGE-reranker-v2-m3, not the
historical MS-Marco evaluation provider. That exact index is retired; there is no active
production reranker while production is `UNINDEXED`.

Phase 8.5 certification and Phase 8.6 validation apply to exact historical
indexes that have since been decommissioned; their source corpora and manifests
remain available for a separately governed rebuild. Production is offline and
explicitly `UNINDEXED`. Phase 8.7 is a completed retrospective MCP capability
milestone. Phase 8.8 has a scoped checkpoint through 8.8.8 but no phase-wide
verification; 8.8.14a–c remain accepted. Phase 8.9 is planned, not started,
and only its future exact-identity GO can unblock Phase 9.
The immutable-schema-compatible chunk read model and truthful optional page
locators have local [Stage 5 acceptance](../docs/reports/operations/mnemo-phase-8-8-stage-5-acceptance.md).
The complete Stage 5 code set has not been deployed or externally verified;
8.8.2f originating reader errors and the 8.8.5/8.8.7/8.8.4/8.8.8
contracts have subsequent [independent local acceptance](../docs/reports/operations/mnemo-stage-6-forensic-remediation-and-acceptance.md).
The F-1 partitioned principal and F-2 nested metadata corrections are included.
Historical 8.8.10 and 8.8.11 have separate local acceptance; unfinished
integration and external certification belong to Phase 8.9. Repository
publication does not establish deployment or external re-verification.

See the [current architecture](../docs/architecture/current/mnemo_architecture_v2.md),
[engineering roadmap](../docs/architecture/current/mnemo_engineering_roadmap.md),
and [documentation index](../docs/README.md) for authoritative status and
navigation.
