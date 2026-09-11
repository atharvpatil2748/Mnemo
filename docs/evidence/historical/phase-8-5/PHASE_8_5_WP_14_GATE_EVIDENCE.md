# Phase 8.5 WP-14 Gate Evidence

**Status:** COMPLETE (2026-08-28)

## Objective and boundary

WP-14 preserves isolation across every new search, delivery, structured,
multimodal, capability, and Final-QA V2 path while repairing the ADR-0072
storage-protocol drift. This gate establishes security verification only. It
does not establish WP-16 external-agent verification or WP-17 final Phase 8.5
certification.

## Implemented controls

- Added the additive `DocumentScopeResolverV1`, `SourceAssociationReaderV1`,
  `PrincipalContextV1`, and typed resolved-scope contract.
- Added the concrete fail-closed storage-backed resolver with explicit,
  unique-association, missing, ambiguous, and exact-version outcomes.
- Removed `list_sources_for_document` from frozen `StorageInterfaceV1` while
  retaining concrete SQLite/Composite compatibility methods.
- Added one server authorization service and server-owned principal mapping;
  API-key and JWT authentication now produce server-owned request context and
  client actor/principal fields are ignored.
- Routed V2 evidence retrieval, structured retrieval, Final-QA execution and
  replay, and MCP delivery through the shared principal/scope boundary.
- Bound advanced and structured continuation fingerprints to the server-owned
  actor scope. Existing CursorCodecV2 domain, scope, query, snapshot, budget,
  expiry, future-time, key-rotation, and signature validation remains intact.
- Strengthened `StorageEvidenceAuthorizerV2` to validate the exact
  notebook/source/document/version chain and, when present, occurrence and
  derivation parentage before context/provider use.
- Preserved occurrence-scoped original/analysis delivery, generation-active
  checks, structured allow-listed IR/parameterization, Final-QA immutable
  replay and zero-generation replay, and capability redaction.

The current schema intentionally has no actor-to-notebook ownership relation.
WP-14 carries actor context and enforces canonical notebook membership without
inventing a future multi-user policy, exactly as required by the frozen plan.

## Security invariant matrix

| Invariant | Evidence/result |
|---|---|
| Client identity cannot override server identity | Principal claim tests; strict DTO extra-field tests; PASS |
| Cross-notebook/document/version isolation | Resolver explicit/unique/ambiguous/missing/version tests and delivery suites; PASS |
| Source/occurrence/derivation chain | Evidence authorizer and asset/delivery suites; PASS |
| Generation lifecycle | Multimodal/multilingual/structured readiness and inactive-generation tests; PASS |
| Cursor privilege escalation | CursorCodecV2 plus delivery/advanced/structured cursor suites, including actor-bound fingerprints; PASS |
| Snapshot/replay bypass | Final-QA execution/transport replay, conflict, revocation, and zero-provider-call tests; PASS |
| Ranked/exhaustive scope | Advanced retrieval and V2 transport suites; PASS |
| Structured injection/scope escape | Typed compiler, SQL-shaped input, join, limits, cursor tests; PASS |
| Multimodal/multilingual leakage | Multimodal and multilingual authorization/provenance suites; PASS |
| Capability discovery grants no access or leaks secrets | Runtime consistency and redaction tests; PASS |
| Error/log leakage | Server stable-error and delivery sanitization tests; PASS |
| Unbounded enumeration | Delivery/retrieval/structured budget and pagination tests; PASS |

## Executed validation

Focused WP-14 tests:

```text
python -m pytest mnemo-core/tests/unit/test_scope_authorization.py
  mnemo-server/tests/test_wp14_security.py -q --no-cov
6 passed
```

Final HTTP delivery authorization integration check:

```text
python -m pytest mnemo-server/tests/test_server_delivery.py
  mnemo-server/tests/test_wp14_security.py -q --no-cov
8 passed
```

The final focused closure command combined both groups without duplication:

```text
python -m pytest mnemo-core/tests/unit/test_scope_authorization.py
  mnemo-server/tests/test_wp14_security.py
  mnemo-server/tests/test_server_delivery.py -q --no-cov
11 passed
```

Affected Phase 8.5 security and transport matrix:

```text
python -m pytest [cursor, delivery, advanced, structured, multimodal,
multilingual, Final-QA execution, server auth, MCP delivery, V2 retrieval,
V2 structured, Final-QA transport, capabilities, errors, config] -q --no-cov
215 passed
```

V1/engine/MCP/governance compatibility matrix:

```text
python -m pytest [engine, V1 Final-QA, V1 search/query, MCP tools,
WP-00 governance contracts] -q --no-cov
81 passed
```

The only warning was the pre-existing Windows pytest cache/temp-directory ACL
warning after successful test completion; it did not change test outcomes.

Static and governance results are recorded after the final commands below:

- Ruff check/format: PASS.
- Strict mypy on affected production modules: PASS.
- Capability/MCP JSON and JSON-schema validation: PASS.
- `git diff --check`: PASS.

## Compatibility and state safety

- V1 retrieval, Final-QA, citations, HTTP/MCP semantics, canonical identities,
  `Chunk.text`, FTS, embeddings/reranking, and Qdrant optionality are unchanged.
- Concrete source-association lookup remains available for direct legacy
  callers; legacy V1 structural doubles no longer need the accidental method.
- No migration was added. No corpus, database, ingestion, projection,
  provider, model, or benchmark state was changed.
- No WP-15, WP-16, WP-17, or Phase 11 functionality was implemented.

## Verdict

No P0/P1 WP-14 security defect remains in the tested Phase 8.5 snapshot.
Applicable capabilities may be marked **SECURITY VERIFIED**, never finally
**CERTIFIED** by this gate.
