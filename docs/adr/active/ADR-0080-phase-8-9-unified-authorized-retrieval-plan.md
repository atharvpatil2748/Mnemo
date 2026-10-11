# ADR-0080: Phase 8.9 unified authorized retrieval plan

- **Status:** Proposed for design approval; no Phase 8.9 implementation or certification implied
- **Date:** 2026-10-09
- **Phase:** 8.9
- **Extends:** ADR-0058, ADR-0061–0064, ADR-0067–0069, ADR-0073–0079
- **Supersedes:** Only the *unimplemented planning assumption* that Phase 8.8.12 must add a public `search_images` tool and that Phase 8.8.14d directly gates Phase 9; no accepted implementation or certification evidence

## Context and problem

The former Phase 8.8 plan scheduled dedicated image search, transport parity,
provenance and a direct Phase 9 gate after compatibility work. The attached
2026-10-09 unified-retrieval architecture audit (conversation attachment; no
repository report was written) found that actual automatic V2 search serves
only one unambiguous notebook, has no selected-document or multi-notebook
request, and does not automatically plan typed structured operations. Retained
V1 cross-notebook search is canonical-only. Persistence has no actor-to-notebook
ownership relation, so removing the one-notebook guard would be unsafe.
In-process MCP dispatch/ASGI evidence is not external-client certification.
The audit also identified partial provenance normalization, source starvation
risk, and no grounded answer in `query_notebook_v2` itself.

## Decision

Re-baseline the active Phase 8.8 execution scope at Module 8.8.8 without
relabelling the phase `PHASE_8_8_VERIFIED`. Preserve Module 8.8.1's signed
runtime certification, 8.8.14a–c accepted work, and actual local acceptance
of 8.8.2–8.8.8, 8.8.10 and 8.8.11. The unfinished 8.8.9 transport matrix,
8.8.13 provenance and 8.8.14d readiness move to Phase 8.9. The former 8.8.12
requirements for OCR, Vision, compatible visual retrieval, asset resolution,
partial results and authorization move into ordinary automatic hybrid search.
`search_images` is not mandatory. A future separate public image-discovery
operation requires its own consumer/use-case justification and decision.

Phase 8.9 designs one shared, server-owned search application boundary beneath
MCP, HTTP and future UI. A versioned request can specify all authorized or
selected notebooks plus notebook-qualified document/version filters; omission
of representation hints means automatic applicable-source planning. The
server derives principal, authorized scope, generation aliases, compatible
models and budgets. Authorization and membership authority precede scope or
capability disclosure. Until a real actor-to-notebook authority exists, private
multi-user fan-out fails closed. Client IDs are not grants.

Canonical, OCR, Vision, provider-compatible multilingual and compatible visual
sources remain typed. OCR/Vision never become fake V1 blocks or chunks.
Structured natural-language planning may invoke existing typed dataset
operations only with unambiguous exact semantics; exact filters, joins and
aggregations remain separately callable. BGE-M3 text and CLIP visual spaces
cannot be compared as raw similarity scores. Fusion uses bounded source ranks,
diversity and explicit coverage rather than arbitrary modality weights.

Evidence retains notebook/source/document/version and chunk **or** occurrence/
asset/derivation **or** dataset/row, with locator, generation, retrieval path
and resolvable citation. Membership survives deduplication. Signed cursors
bind principal, scope, policy, representations, aliases, query and limits.
Source status distinguishes searched-zero, not-applicable, unavailable,
incomplete, failed and omitted-by-budget. Ranked top-k is not exhaustive
semantic recall; terminal-cursor traversal and exact structured predicates
have separate completeness meanings. Typed errors remain safe across adapters.

Existing V1 query/search contracts and the persisted V1 IR are frozen.
`query_notebook_v2`, `search_evidence`, `query_structured`, exact delivery and
FinalQA remain available while Phase 8.9 inventories consumers and proposes
canonical `search`/HTTP search plus optional structured discovery operations.
Those proposed public names are **not** registered by this ADR. No old route is
removed before versioned parity, migration guidance and client evidence.
FinalQA may later consume the shared authorized evidence snapshot, retaining
deadline, replay/idempotency and citation-publication controls.

## Alternatives

- Expand V1 search in place: rejected because chunk-only contracts and callers
  would silently change meaning.
- Add mandatory `search_images`: rejected as ordinary image questions must not
  require modality knowledge; `get_asset`/`get_image_analysis` still serve exact
  recovery and inspection.
- Run independent MCP/HTTP/UI retrieval planners: rejected for authorization,
  cursor and error drift.
- Remove one-notebook guard without membership authority: rejected as a
  potential cross-user disclosure.
- Treat vector top-k as exhaustive or convert derived text to V1 chunks:
  rejected as false coverage/provenance.

## Consequences, gates and open questions

Follow the [Phase 8.9 roadmap](../../architecture/current/mnemo_engineering_roadmap.md)
tasks 8.9.1–8.9.9. Membership-state design/migration requires separate approval.
The canonical public operation names, structured intent grammar, provider
readiness policy and dedup identity require contract review before code changes.
The exact validation pair is evaluation-only; the certified Phase 8.5 corpus,
Phase 8.6 sources, mutable-workspace boundary and signed operational state
remain protected. No Phase 8.6 promotion, Qdrant/SurrealDB activation, rebuild,
or production indexing is authorized here.

Phase 9 may start only after an exact-identity, machine-verifiable Phase 8.9
GO based on integrated scope, representation, structured, provenance, V1
compatibility, external MCP/deployed HTTP transport, FinalQA and protected-state
evidence. Local tests, route registration or rebuild completion are not GO.
