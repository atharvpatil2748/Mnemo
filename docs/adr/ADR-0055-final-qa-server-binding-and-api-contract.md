# ADR-0055: Final-QA Server Binding and API Contract

- **Status:** Accepted
- **Date:** 2026-08-20
- **Scope:** Phase 7 transport adapter for ADR-0046 final QA
- **Extends:** ADR-0046, ADR-0047, ADR-0049, ADR-0050, ADR-0052, ADR-0054

## Decision

Add the non-streaming persisted Final-QA endpoint:

```text
POST /v1/notebooks/{notebook_id}/final-qa
```

It is a thin transport adapter over the ready engine's
`FinalQAInterfaceV1.execute()`.  It performs no retrieval, generation, marker
parsing, citation construction, or persistence logic itself.

## Request and canonical inputs

The path `notebook_id` and JSON body are:

```text
session_id: UUID                         required
user_turn_id: UUID                       required
assistant_turn_id: UUID                  required, caller-owned and stable
global_limit: int = 20                   1..100
context_budget: int = 8000               1..1_000_000
max_output_tokens: int = 1000            1..4096
filters: QueryFilters | null = null
table_of_contents: tuple[str, ...] = ()
```

The binding loads the session and verifies it belongs to the path notebook.
It derives `query` exclusively from the persisted identified user turn; the
client cannot supply a second query.  It derives exact-version
`DocumentContextLabel` and source-title tuples from canonical documents linked
to that notebook, and supplies the default ADR-0044 system prompt.  It creates
the immutable ADR-0046 `FinalQARequest`, adding the path notebook as the hard
`MetadataFilter.notebook_id` and intersecting optional filters under ADR-0046.

The caller first creates a session and appends the USER turn through the
existing sessions API.  The user turn must be that session's final turn and
its normalized content is the final-QA query.  The supplied assistant UUID is
the only idempotency key: identical repeat calls converge through ADR-0046;
different output or incompatible history is `ConflictError`.

## Response and errors

On `200`, return a transport DTO containing `status` (`citation_resolved` or
`no_context`), `answer`, and ADR-0045 `CitationItemResponse` snapshots.  The
strict publication contract means `unmarked` is not a successful response.
The adapter does not flatten or expose a replacement provenance model.

ADR-0049 middleware remains the sole authentication mechanism (none, API key,
or JWT according to deployment configuration).  Current local-first server
configuration has no per-notebook principal model; therefore authorization is
limited to successful middleware authentication and notebook/session
association checks.  Multi-tenant ownership enforcement requires a successor
authorization ADR.

Malformed UUID/schema input maps to `422`; missing notebook/session/user turn
to `404`; notebook/session mismatch or assistant retry conflict to `409`;
unsupported multi-hop to `400`; dependency/storage lifecycle errors retain
ADR-0049 mappings.  `IntegrityError`, including exhausted
`citation_compliance`, maps to ADR-0049 `500 contract.integrity`; a structured
event records the classification without answer/context text.  Cancellation
propagates using the existing cancellation mapping.  No timeout or streaming
operation is added.

## Existing query and streaming endpoints

`POST /v1/query` remains an explicitly non-persistent search/evidence preview.
Its response must identify preview semantics and must not claim ADR-0045
persisted citations.  During compatibility support, synthesis preview uses the
shared ADR-0054 validator and may return transient context evidence, but no
assistant turn or `Citation` record.  `POST /v1/query/stream` is likewise a
non-persistent preview; persisted Final QA is complete-only until a future
streaming ADR.

## Lifecycle, security, and tests

The adapter accesses `engine.final_qa` only after normal engine readiness;
`KnowledgeEngine` retains provider lifecycle ownership.  All canonical storage
access is through the composed orchestrator and existing session/document
services; no direct SQLite/Qdrant/SurrealDB access is introduced.

Tests must cover auth modes, UUID/schema validation, notebook/session
association, user-turn preconditions, canonical label/title derivation,
idempotent assistant reuse/conflict, no-context, compliant citation response,
retry exhaustion, cancellation, and proof that fake final-QA receives the
exact immutable request while the adapter performs no duplicate stages.
