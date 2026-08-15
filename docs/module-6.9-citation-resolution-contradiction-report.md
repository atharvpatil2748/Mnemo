# Module 6.9 Citation Resolution and Persistence Contradiction Report

## Status

**CONFIRMED AND RESOLVED ARCHITECTURALLY BY ADR-0045.** Module 6.9 production
implementation has not started.

## Requirement

Module 6.9 must consume the exact ADR-0044 `GroundedAnswerResult`, resolve its
canonical `[source:N]` markers against retained typed `ContextItem` records,
construct frozen ADR-0001 `Citation` snapshots, and persist them without
changing any frozen Phase 1 or prior Phase 6 contract.

## Existing architecture and contracts

- ADR-0044 deliberately defers assistant-turn identity, marker validation,
  repeated/unknown/missing marker behavior, title and quote selection,
  compressed-item behavior, citation identity/time ownership, backend choice,
  transactions, rollback, and persistence failures to Module 6.9.
- `GroundedAnswerResult` retains the exact `ContextBuildResult`; each selected
  `ContextItem` retains the exact canonical `Chunk` provenance.
- ADR-0001 `Citation` requires a UUID identity, assistant `turn_id`, positive
  source number, exact chunk/document/version identity, non-empty title,
  non-empty verbatim quote, optional page, heading path, and UTC timestamp.
- `ContextBuildResult` does not retain `DocumentContextLabel` separately, and
  labels were intentionally optional in Module 6.7. A required citation title
  therefore cannot be recovered from typed provenance alone.
- `StorageInterfaceV1` exposes `append_turn`, individual `upsert_citation`, and
  `get_citations_for_turn`; it exposes no batch citation write, delete citation,
  public transaction, or atomic turn-plus-citation operation.

## Actual persistence implementation

- `CompositeStorage` delegates session, turn, and citation operations only to
  its SQLite component.
- `SQLiteStore.upsert_citation()` commits each citation independently and uses
  `ON CONFLICT(citation_id) DO UPDATE`.
- SQLite foreign keys require the target turn, document, and document version,
  but the schema does not enforce that the target turn role is assistant.
- `SurrealDBStore` session, turn, and citation methods raise
  `NotImplementedError`. Architecture prose describing SurrealDB as the active
  citation source of truth is stale relative to the executable facade.
- There is no existing citation resolver, marker parser, quote selector,
  citation ID policy, clock policy, batch rollback, or compensation utility.

## Genuine contradictions and ambiguities

1. The required non-empty `Citation.document_title` is unavailable when an
   exact-version `DocumentContextLabel` was omitted, and storage lookup would
   violate the typed provenance boundary.
2. No contract assigns or supplies the assistant `Turn` identity required by
   every citation, nor states whether Module 6.9 creates the turn.
3. The frozen storage facade cannot atomically create an assistant turn plus an
   arbitrary citation set or roll back earlier per-citation commits.
4. Active architecture prose names SurrealDB for citation persistence, while
   the implemented `CompositeStorage` routes citations to SQLite and SurrealDB
   has no implementation.
5. Marker grammar beyond the example, repeated/malformed/unknown/missing
   markers, and references to omitted candidates have no executable rule.
6. Citation quote semantics are undefined for both verbatim and compressed
   context items.
7. Citation UUID generation, duplicate/retry behavior, timestamp ownership,
   ordering, cancellation, and partial persistence behavior are undefined.
8. No immutable Module 6.9 output exists for the Module 6.10 handoff.

Implementation would therefore require inventing public behavior. The roadmap
itself records that these decisions require Module 6.9 architecture.

## Considered compliant resolutions

1. Extend `StorageInterfaceV1` with a transactional batch operation. Rejected:
   it breaks a frozen contract and forces a storage migration before the V1
   citation semantics are otherwise known.
2. Query storage for titles and chunks. Rejected: provenance already exists in
   typed records, title lookup is absent from the frozen contract, and direct
   backend access would couple the citation engine to storage layout.
3. Store compressed summaries as verbatim quotes. Rejected: compressed content
   is query-transient and is not verbatim canonical evidence.
4. Make Module 6.9 create the assistant turn and citations. Rejected: the frozen
   facade cannot make that combined operation atomic, and conversation
   sequencing belongs to the caller/final integration boundary.
5. Use an additive request/result boundary, require an already-persisted exact
   assistant turn and complete cited-version labels, derive citations from
   retained chunks, and use deterministic per-record upserts. Selected by
   ADR-0045 as the smallest executable contract.

## Compatibility and migration impact

ADR-0045 is additive and changes no frozen model or interface. It makes the
implemented SQLite path behind `CompositeStorage` authoritative for Phase 6
conversation/citation persistence and corrects stale active documentation.
No schema migration is required. The deliberate V1 consequence is that a
multi-citation invocation is convergent and idempotent but not all-or-nothing;
an interrupted or failed invocation can leave a persisted prefix and must be
retried with the same deterministic inputs.

## Resolution

Accepted ADR-0045 defines the complete marker, identity, title, quote,
assistant-turn, persistence, failure, and Module 6.10 handoff semantics. Module
6.9 is now **ARCHITECTURE RESOLVED / IMPLEMENTATION NOT STARTED**. Modules 6.10
and milestone M6 remain not started/not verified.

## Implementation addendum (2026-08-13)

ADR-0045 has now been implemented by the additive immutable
`CitationResolutionResult` contract and backend-neutral `CitationEngine`.
Focused, cumulative, full repository, isolated SQLite/CompositeStorage, and
real Bhagavad Gita pipeline validation passed. The contradiction analysis above
remains historical evidence; Module 6.9 is now **COMPLETE**, Module 6.10 remains
not started, and M6 remains not verified.
