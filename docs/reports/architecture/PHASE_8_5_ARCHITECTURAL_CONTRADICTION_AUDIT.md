# Phase 8.5 Architectural Contradiction Audit

**Date:** 2026-08-24
**Baseline:** v0.25.0, ADR-0001 through ADR-0057
**Reviewed package:** ADR-0058 through ADR-0071
**Status:** ARCHITECTURE ACCEPTED — IMPLEMENTATION PENDING

## Method

The review compared every Phase 8.5 decision with the frozen domain, parser,
storage, embedding, retrieval, context, citation, Final QA, server, MCP,
configuration, migration, security, roadmap, and release contracts. Historical
ADRs were not edited. A conflict is resolved only by an additive interface,
versioned contract, or explicit narrow supersession in a successor ADR.

## Contradiction matrix

| Existing decision/claim | Potential conflict | Resolution in Phase 8.5 | Result |
|---|---|---|---|
| ADR-0001 canonical identities and `Asset` | new visual identity might replace canonical models | ADR-0059 reuses `Asset` and adds references/occurrences/derivations | CONSISTENT |
| ADR-0002 frozen core interfaces | multimodal/jobs might widen V1 | independent V1/V2 facilities; StorageInterfaceV1 and text embedding V1 unchanged | CONSISTENT |
| ADR-0003 configuration authority | provider/UI defaults could bypass config | profiles/capabilities/budgets resolve through existing configuration authority | CONSISTENT |
| ADR-0004 composition root | routes/workers could construct pipelines | providers/services compose in core engine; HTTP/MCP remain adapters | CONSISTENT |
| ADR-0008 parser images | old image fields are incomplete | ADR-0059 extends occurrence provenance; parser V1 adapter remains | CONSISTENT |
| ADR-0011 raw parse boundary | retaining originals/derived text could mutate IR | originals and derivations are additive; canonical parser output remains authoritative | CONSISTENT |
| ADR-0014 canonicalization | occurrence IDs might alter document/chunk identity | occurrences link after version identity and never enter UUID computation | CONSISTENT |
| ADR-0018 text embedding lifecycle | visual vectors might share incompatible cache/index | ADR-0062 adds named modality spaces and separate generations | CONSISTENT |
| ADR-0038/0039 filters and sparse provenance | V2 plans might alter V1 ranking | ADR-0058 wraps/extends; completeness cannot be inferred from V1 | CONSISTENT |
| ADR-0040 parent promotion | multimodal candidates lack text parents | V1 remains; V2 candidate kinds define their own provenance, no fake parent | CONSISTENT |
| ADR-0041/0042/0057 fusion/reranking | cross-space scores could overwrite evidence | ADR-0062/0064 use typed candidates and rank fusion; V1 order untouched | CONSISTENT |
| ADR-0043 text context | binary/structured evidence cannot fit V1 | ADR-0064 adds a budgeted multimodal context contract alongside V1 | CONSISTENT |
| ADR-0044/0045 citations | image evidence lacks canonical chunk | V1 stays frozen; `EvidenceCitationV2` is explicit and retains original link | CONSISTENT |
| ADR-0046/0047 Final QA integration/composition | second pipeline could duplicate orchestration | V2 follows the same composed-interface ownership and thin adapters | CONSISTENT |
| ADR-0048 diversity/routing | new planner might erase policy | ADR-0058 defines typed V2 planning; V1 routing and diversity remain | CONSISTENT |
| ADR-0049 server architecture | binary/jobs could put business logic in HTTP | ADR-0065/0069 require shared core services and thin transport adapters | CONSISTENT |
| ADR-0050/0051 REST contracts | new document delivery might replace current APIs | versioned additive endpoints, existing management/ingestion routes unchanged | CONSISTENT |
| ADR-0052/0054 publication/retry | V2 might normalize or add retries | ADR-0064 retains exact `[source:N]`, one correction, and validation ordering | CONSISTENT |
| ADR-0055 preview versus persisted QA | `/v1/query` might become multimodal persisted QA | preview routes remain transient; V2 persisted binding is separate | CONSISTENT |
| ADR-0056 immutable replay | V2 might reconstruct from mutable assets | V2 snapshot stores exact typed evidence/resource manifest and reuses state semantics | CONSISTENT |
| Qdrant/SurrealDB optionality | vectors/jobs might require optional services | ADR-0060 baseline SQLite jobs; ADR-0062 does not enable Qdrant | CONSISTENT |
| six-tool MCP Phase 8 contract | tool replacement/schema drift | ADR-0066 keeps six tools and adds four capability-gated tools/resources | CONSISTENT |
| Phase 9 Web UI responsibility | Phase 8.5 could consume UI phase | ADR-0069 defines contracts/mock validation only; implementation remains Phase 9 | CONSISTENT |
| Phase 10 background worker roadmap | first worker described as SurrealDB-specific | ADR-0060 narrowly supersedes roadmap assumption; Phase 10 extends common jobs | RESOLVED PROSPECTIVELY |
| architecture “no external calls” shorthand | optional consented cloud providers | local-first default remains; cloud is explicit configured/consented trust profile | CLARIFIED |

## Ownership audit

| Responsibility | Sole owner |
|---|---|
| immutable bytes and occurrence catalog | asset catalog/storage services |
| expensive-operation lifecycle | processing job service/worker |
| OCR/VLM/embedding execution | registered providers invoked by job handlers |
| completeness/result-set lifecycle | retrieval V2 services |
| structured execution | typed compiler/executor, never LLM or HTTP |
| multimodal context/citation/publication | Final QA V2 graph |
| authorization and consent | shared application policy services |
| HTTP/MCP translation | thin server adapters |
| UI controls/display | Phase 9 frontend consuming certified APIs |

No duplicated runtime ownership is accepted.

## Migration and rollback audit

ADR-0071 provides the common additive schema and side-by-side generation
lifecycle. No accepted decision requires destructive migration, corpus
re-ingestion, canonical identity mutation, enabling an optional backend, or
upgrading a V1 immutable snapshot. Every capability has an advertisement/
profile/alias rollback that leaves Phase 0–8 operational.

## Security audit outcome

ADR-0068 resolves the novel trust boundary: all logical access traverses an
authorized occurrence despite physical hash deduplication. ADR-0060 controls
provider egress/cost, ADR-0065 bounds delivery, ADR-0063 forbids user SQL, and
ADR-0070 requires malicious-media and multilingual prompt-injection cohorts.
No new bare asset-ID, filesystem-path, or silent cloud trust boundary remains.

## Open profile decisions

Provider/model selections, measured transport/resource ceilings, cloud policy,
per-direction quality thresholds, and retention periods remain profile-level
decisions recorded in the roadmap. They do not create current contradictions
and may not be silently chosen during implementation.

## Verdict

**PASS — no unresolved contradiction prevents Phase 8.5 implementation.**

This verdict certifies planning consistency only. It does not certify or claim
any Phase 8.5 runtime implementation.
