# ADR-0073: MCP-Native Retrieval and Delivery Contracts

- **Status:** Accepted
- **Implementation:** WP-03 contract/discoverability, WP-04 cursor/completeness, WP-05 exact selectors, WP-06 derivation-aware asset delivery, and WP-07 `search_evidence` are implemented; structured/Final-QA/capability handlers remain gated by WP-08/WP-12/WP-13 and behavioral certification remains WP-16
- **Date:** 2026-08-26
- **Extends:** ADR-0058, ADR-0064, ADR-0065, ADR-0066, ADR-0067, ADR-0068, ADR-0069, ADR-0070
- **Supersedes:** Nothing

## Context

Mnemo exposes ten MCP tools. Direct calls work when a caller already knows the
correct identifiers, but an unfamiliar agent sees ambiguous input-only schemas.
In particular, bounded ranked discovery appears suitable for exact traversal or
exhaustive questions, asset delivery appears suitable for semantic image search,
and analysis delivery requires identifiers that cannot be naturally discovered.

Phase 8.5 already defines exact, exhaustive, structured, multilingual,
multimodal, and bounded delivery domain contracts. The MCP adapter must expose
those distinctions without changing the six frozen Phase 8 tools or turning MCP
into an autonomous Phase 11 planner.

## Decision

### Retained tools

The following names and existing required inputs remain compatible:

1. `list_notebooks`
2. `get_notebook_summary`
3. `search_all_notebooks`
4. `query_notebook`
5. `get_source_insights`
6. `get_timeline`
7. `get_document`
8. `get_document_chunk`
9. `get_asset`
10. `get_image_analysis`

The first six retain their Phase 8 semantics. The four delivery tools retain
the ADR-0066 behaviors. Descriptions and optional fields may be enriched, but a
retained tool may not silently acquire a different semantic meaning.

### Additive tools

Four semantic tools are added only when their backing capability is ready:

- `search_evidence`: ranked or bounded exhaustive retrieval over explicitly
  requested representations and scope. It discovers canonical, OCR, Vision,
  visual-vector, title, positional, and other typed evidence; it does not
  deliver arbitrary binary bytes or perform structured arithmetic.
- `query_structured`: typed filters, comparisons, sorting, grouping, and
  aggregates over an explicit ready structured projection. It does not infer
  numeric completeness from semantic chunks.
- `run_final_qa_v2`: persisted Final-QA V2 over typed authorized evidence,
  reusing ADR-0054 citation compliance and ADR-0056 publication/replay.
- `get_capabilities`: scope-aware capability, readiness, generation, bounds,
  and limitation discovery. It never advertises class existence as support.

### Mandatory intent guidance

Every tool definition contains `when to use`, `when not to use`, bounds,
continuation behavior, and recommended next actions. At minimum:

- `search_all_notebooks` is **bounded ranked canonical-text discovery**. It is
  not exhaustive enumeration, exact page/range/end traversal, structured
  arithmetic, or semantic image search.
- `get_document` is **exact-version bounded traversal/delivery**. Exact
  page/range/end/full requests use explicit selectors when available and must
  continue an unchanged cursor until the requested scope is complete or a
  typed terminal limitation is returned.
- `get_asset` lists known authorized occurrences or delivers one known
  original asset. It is not natural-language or visual-semantic discovery.
- `get_image_analysis` delivers authorized derived OCR/Vision evidence. It is
  neither the original image nor an image-search operation.
- `query_notebook` remains bounded V1 retrieval/optional synthesis and does not
  promise exhaustive, structured, or multimodal completeness.

Tool-chain examples are documentation and selection guidance, not an embedded
planner. Search/discovery results propagate every opaque identifier required by
the next authorized operation. Responses may recommend semantic next actions,
but the server does not autonomously execute them.

### Input and output contract

Input schemas define formats, maxima, defaults, selectors, modes, scope, and
mutual exclusions. UUID fields use UUID format; chunk identities use their
canonical digest format. Unknown fields are rejected for new V2 tools.

Every result has a transport envelope containing:

- `schema_version`, `operation`, and opaque `request_id`;
- `items` or a typed singular `resource`;
- `scope` with authorized notebook and applicable source/document/version IDs;
- `provenance` on every evidence/resource item;
- `completeness`, `coverage`, `omissions`, and `limits`;
- `next_cursor` when and only when continuation is valid;
- `recommended_next_actions` using tool names and already-authorized opaque
  identifiers, never filesystem paths;
- a stable typed error envelope on failure.

Structured MCP content is authoritative. For clients limited to text content,
the same envelope is serialized as canonical JSON without losing IDs,
completeness, provenance, or continuation fields. Binary data uses native MCP
image/resource content; a small structured companion envelope carries its
identity, MIME, hash, size, occurrence, completeness, and provenance.

### Continuation and completeness

Cursors are opaque, signed, expiring, and bound to actor/notebook, exact
version or generation, selector/query fingerprint, immutable snapshot, and
effective server budgets. A client supplies `next_cursor` unchanged to the same
operation. Reauthorization occurs for every page. A cursor cannot widen scope
or limits.

`COMPLETE` means the declared scope and requested representations were
exhausted under the contract. `TRUNCATED`, `PARTIAL`, `BOUNDED`, `UNKNOWN`,
`UNAVAILABLE`, `FAILED`, and `NO_MATCH`/`EMPTY` remain distinct as defined by
the owning domain result. Ranked top-k is never relabeled complete. An
unavailable required projection is not a no-match.

### Compatibility policy

- The ten retained tools keep their names and existing required inputs.
- Optional inputs and additive output fields receive schema snapshot tests.
- The four new tools are advertised only when their handlers and dependencies
  meet the readiness contract in ADR-0074.
- Stdio and SSE use the same definitions, services, authorization, bounds, and
  error mapper.
- Existing JSON-only clients receive the compatibility fallback above.

### Behavioral validation

Contract conformance is necessary but insufficient. A blind-agent evaluation
provides only natural-language requests and discovered MCP metadata. It scores
first-tool selection, identifier propagation, continuation, answer accuracy,
provenance, completeness honesty, bounds, and security. The oracle tool chain
is withheld. Direct calls with preselected IDs do not prove discoverability.

## Alternatives

- Only improve prose on the ten tools: rejected because exhaustive,
  structured, multimodal, capability, and Final-QA V2 operations are missing.
- Overload `search_all_notebooks`: rejected because it would break frozen V1
  ranked semantics and blur completeness.
- Add one tool per modality/action: rejected because excessive overlapping
  tools reduce selection reliability.
- Add a server-side autonomous planner: rejected as Phase 11 scope.

## Consequences

The public surface becomes more explicit and composable while remaining
bounded. Tool count grows only when backing services are operational. Clients
must handle typed completeness and continuation instead of assuming one call is
complete.

## Security

Tool possession and opaque IDs are not authorization capabilities. Every
candidate, page, occurrence, derivation, binary, snapshot, and replay is
reauthorized. Responses and errors expose neither paths nor inaccessible
resource existence. Content, OCR/Vision text, vectors, prompts, and secrets are
excluded from logs.

## Rollback

Stop advertising additive tools and optional enrichments. Retained tools fall
back to their prior compatible schemas and V1 behavior. Persisted data is not
deleted.

## Required tests

- Exact schema snapshots for retained and additive tools.
- Semantic lint assertions distinguishing ranked/exhaustive, search/traversal,
  discovery/delivery/analysis, and semantic/structured retrieval.
- Structured-content/JSON equivalence and native-binary envelope tests.
- Cursor, completeness, errors, authorization, stdio/SSE parity, and old-client
  compatibility tests.
- Blind-agent matrix from the authoritative Phase 8.5 implementation plan.

## References

- `docs/governance/historical/PHASE_8_5_COMPLETE_IMPLEMENTATION_PLAN.md`
- `docs/governance/contracts/phase8_5_mcp_contracts.json`
- ADR-0058, ADR-0064–ADR-0070
