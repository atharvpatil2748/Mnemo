# mnemo-core

Mnemo-owned code and documentation are proprietary: Copyright © 2026 Atharv
Patil. All rights reserved. See the [current-tree distribution policy](../docs/governance/active/proprietary_distribution_policy.md).

`mnemo-core` is the provider-neutral domain and pipeline library for the Mnemo
local knowledge engine. It contains the typed ingestion, document/version/chunk
identity, storage, retrieval, reranking, evidence, provenance, ContextBuilder,
FinalQA, structured, multilingual, OCR, Vision, CLIP, processing, and delivery
contracts used by the server composition.

The current certified V2 profile uses content-addressed filesystem storage, an
immutable SQLite corpus with FTS5 and governed BGE-M3 vectors, and a separate
purpose-specific mutable FinalQA operational SQLite store. That operational
store is not a general user workspace. ADR-0077 accepts a separately governed,
explicitly configured absolute mutable filesystem + SQLite workspace with
mandatory server-enforced read-only fallback; its typed storage roles and
pre-I/O boundary are implemented and certified. Qdrant remains an
optional V1/future vector-scale adapter; SurrealDB remains a partial future graph
adapter. Current production reranking is BGE-reranker-v2-m3, not the historical
MS-Marco evaluation provider.

Phase 8.5 is completed/certified, Phase 8.6 is a validated evaluation-only
notebook, and Phase 8.7 is a completed MCP capability milestone. Phase 8.8 is
in progress but not verified. 8.8.14a and authenticated HTTP FinalQA V2 chat
(8.8.14b) are accepted, and 8.8.14c documentation is reconciled; Phase 9
remains gated on complete Phase 8.8 verification.
The immutable-schema-compatible chunk read model and truthful optional page
locators have local [Stage 5 acceptance](../docs/reports/operations/mnemo-phase-8-8-stage-5-acceptance.md).
The complete Stage 5 code set has not been deployed or externally verified;
8.8.2f originating reader errors and the 8.8.5/8.8.7/8.8.4/8.8.8
contracts have subsequent [independent local acceptance](../docs/reports/operations/mnemo-stage-6-forensic-remediation-and-acceptance.md).
The F-1 partitioned principal and F-2 nested metadata corrections are included.
Stage 6 still requires 8.8.10 and 8.8.11. Repository publication does not
establish deployment or external re-verification of this batch.

See the [current architecture](../docs/architecture/current/mnemo_architecture_v2.md),
[engineering roadmap](../docs/architecture/current/mnemo_engineering_roadmap.md),
and [documentation index](../docs/README.md) for authoritative status and
navigation.
