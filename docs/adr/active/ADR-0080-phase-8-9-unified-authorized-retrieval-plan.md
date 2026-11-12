# ADR-0080: Phase 8.9 unified authorized retrieval plan

- **Status:** Accepted for design (owner authorization 2026-10-21); implementation and certification remain separate gates
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
Those approved future public names are **not** registered by this ADR. No old route is
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
readiness policy and dedup identity were resolved for design in the
2026-10-21 approval addendum below. Registration and shared-service code
remain gated by their roadmap modules and their own validation evidence.
The exact validation pair is evaluation-only; the certified Phase 8.5 corpus,
Phase 8.6 sources, mutable-workspace boundary and signed operational state
remain protected. No Phase 8.6 promotion, Qdrant/SurrealDB activation, rebuild,
or production indexing is authorized here.

Phase 9 may start only after an exact-identity, machine-verifiable Phase 8.9
GO based on integrated scope, representation, structured, provenance, V1
compatibility, external MCP/deployed HTTP transport, FinalQA and protected-state
evidence. Local tests, route registration or rebuild completion are not GO.

## Owner-approved contract decisions (2026-10-21)

The project owner explicitly authorized resolution of the four design gates
for Module 8.9.1. This acceptance is not external-client sign-off,
production admission, provider certification, an indexed runtime, or permission
to implement later modules out of sequence. The versioned review schema and
field-by-field mapping are in the
[Module 8.9.1 contract record](../../reports/architecture/module-8-9-1-contract-authority.md).

1. **Public operation names.** Approve additive MCP search and HTTP
   POST /v2/search as the intended unified-search pair for roadmap 8.9.6a.
   Exact typed query_structured, query_notebook_v2, search_evidence,
   delivery and FinalQA remain available. search_structured and
   describe_datasets remain optional names requiring separate exact-operation
   parity and consumer review under 8.9.6b; search_images remains optional
   only by a separate use-case decision. No new name is registered in 8.9.1.
   Rationale: additive names permit a distinct multi-notebook contract without
   changing frozen V1 or retained V2 semantics. Rejected: in-place rename,
   silently expanding V1, and registration before shared authorization,
   schema and adapter parity. Client-supplied names or IDs confer no authority.

2. **Structured intent grammar.** The approved initial grammar is the existing
   strict, typed StructuredRetrievalRequest AST: operations describe,
   query (one explicit dataset), union (two or more explicit datasets),
   and join (explicit, distinct left/right datasets). Existing typed
   filters, selections, grouping, aggregates and sort fields are validated
   against their operation and authorized exact-version scope. Field and
   dataset identifiers retain exact identity; query text normalization does
   not rewrite them. Unknown fields, duplicate/ambiguous selections,
   incompatible operation combinations, malformed predicates and unauthorized
   actor/store/generation/provider override fields fail with safe typed
   invalid-input or authorization outcomes. Natural-language translation
   into structured predicates is not in this approved grammar. A later
   grammar requires its own design review under 8.9.5b and must refuse
   ambiguity rather than guess. Rejected: free-form SQL, inferred joins and
   approximate arithmetic on semantic chunks. Existing exact typed callers
   remain compatible.

3. **Provider readiness.** Authenticate and authorize before capability or
   source disclosure. A source is searched only after an applicable,
   compatible, active and ready provider actually searched its authorized
   scope; matched=0 then means searched-zero, not corpus-wide absence.
   Not-applicable is distinct and does not alone imply a partial result.
   Applicable unavailable, incomplete, failed or omitted-by-budget sources
   must be reported with reason/omission and partial coverage; they cannot
   be relabeled complete or empty. Automatic ranked search may return other
   authorized evidence with honest PARTIAL coverage, consistent with
   ADR-0079, but never claim exhaustive recall. With no applicable searched
   source, return a typed capability-unavailable or retrieval-failure outcome,
   not an empty successful search. Exact structured/exhaustive requests whose
   required projection is unavailable fail closed rather than fabricate exact
   results. Unknown generation, missing authority, incompatible identity or
   revoked serving state fail closed before planning. This is a policy, not
   evidence any production provider is ready; profile-specific mandatory/
   optional matrices and certification remain later-module gates. Rejected:
   installed code or stored derivations as readiness, searched-zero
   substitution, and false completeness.

4. **Cross-notebook deduplication identity.** There is no global text/content
   key. A conservative type-specific equivalence key includes notebook
   membership, source, document, version, generation and alias, typed chunk
   or occurrence/asset/derivation or dataset/row identity, locator and
   citation. Retrieval path is excluded from identity so identical evidence
   within one authorized membership can retain every path. Different notebook
   memberships never collapse to one bearer item; same-text/different-source,
   version, derivation or row remain distinct. Before any later runtime merge,
   payload and ancestry equality must be checked; a collision fails integrity
   validation. This preserves authorization, citation and deterministic cursor
   partitions without inventing a universal ID. Rejected: candidate UUID
   alone across notebooks, text similarity and source-agnostic fusion. The
   review-only equivalence key and fixtures freeze design, not a live
   cross-notebook deduplicator.

Design approval unblocks contract freeze review, not Module 8.9.2a membership
writes, 8.9.3 shared-service integration, 8.9.5b NL grammar, 8.9.6 adapter
registration or Phase 8.9 certification. No historical certification or
unknown external consumer is deemed to have accepted these decisions.
