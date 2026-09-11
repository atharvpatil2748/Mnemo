# Full Multilingual V2 Production Adapter Implementation Report

Status: **BLOCKED — FAIL-CLOSED HARD STOP**  
Date: 2026-09-02

## 1. Executive result

The five adapters were not registered or wired. Repository forensics found three
contract/storage conflicts covered by the task's hard-stop rule. Implementing around
them would either invent a database identity, downgrade the bounded V2 authorization
decision to `AuthorizationScopeV1`, or silently reinterpret the vector generation.

The partial adapter experiment was removed. No production runtime path was activated.

## 2. Repository evidence and blockers

### B1 — authorized resolution interfaces still discard the bounded V2 decision

Current production contracts are:

- `RerankerEvidenceResolverV1.resolve_reranker_evidence(actor_id, source,
  authorization_scope)`;
- `RerankerCandidateBuilderProtocolV1.build(actor_id, query, source,
  authorization_scope, input_ordinal)`;
- `V2AdvancedCandidateProjector.project_advanced_candidate(actor_id, value)`.

They carry neither `V2RetrievalAuthorizationDecisionV1` nor its active alias,
four-generation, profile, vector-space, database, build-run, freshness, and positional
scope bindings. The approved evidence-resolution contract requires all of those
bindings. An adapter cannot recover them from `actor_id` or `AuthorizationScopeV1`
without inventing or weakening security semantics.

Required remediation: version these three downstream V2-only interfaces so the
bounded decision (or an immutable non-expandable context derived from it) is mandatory
through resolution and projection. Candidate provenance must bind the decision
fingerprint, active generation set, retrieval paths, and fusion rank.

### B2 — canonical database identity is not persisted in the built database

`V2ActiveRuntimeBindingV1.database_identity` and the authorization/evidence JSON
schemas require a SHA-256 identity. The disposable database manifest contains a UUID
`database_id`, while `v2_build_runs` persists the target path, run, corpus, census,
profile, vector space, and manifest digests but no canonical SHA-256 database identity.

No governed rule defines a SHA-256 derivation from the UUID/path/run tuple. Hashing
one of those combinations inside an adapter would manufacture a security identity.

Required remediation: govern one canonical database-identity definition and persist
or immutably bind it in a runtime-readable manifest/record. Then provide a storage API
that verifies the opened database path and build-run row against that identity before
authorization is issued.

### B3 — vector generation is a manifest-only projection over embedding rows

The active vector generation is
`2b26443e-bb99-5bf8-a4af-a01ba99af8ce`, but
`multilingual_embeddings_v2` contains zero rows under that ID. Its 3,019 vectors are
stored under embedding generation
`62243160-bed5-5064-a664-815984232e31`.
`index_generation_sources` correctly records the vector-to-embedding dependency.

The current runtime factory passes the vector-generation ID into
`list_authorized_multilingual_embeddings_v3`, which filters the embedding table by
that ID and therefore produces an empty dense set. An adapter must not simply swap IDs
without a governed source-generation resolution contract.

Required remediation: define the vector projection read contract explicitly as
`active vector generation -> exactly one active embedding source generation -> rows`,
validate the dependency from `index_generation_sources`, and carry both identities in
retrieval/provenance. Alternatively materialize separately keyed vector projection
rows in a later governed build; no rebuild was authorized here.

## 3. Five-adapter status

| Adapter | Status | Reason |
|---|---|---|
| ActiveV2GenerationInspector | BLOCKED | Cannot prove canonical database identity; current protocol also accepts only generation IDs. |
| LanguageEvidenceAuthorizerV3 | BLOCKED | A bounded decision exists, but downstream resolution contracts still downgrade it. |
| Authorized evidence resolver | BLOCKED | Required decision/profile/vector/database/build bindings are absent from its interface. |
| Candidate projector/builder | BLOCKED | Projector receives actor plus candidate, not the bounded decision; full security provenance cannot be proven. |
| Active generation/source storage adapter | BLOCKED | Vector-generation row semantics are not defined for the existing embedding-backed projection. |

## 4. Security decision

No evaluator-only authorization, actor-to-notebook ownership, arbitrary SQL resolver,
generation override, vector-space override, V1 fallback, title-derived evidence, or
hard-coded language behavior was introduced. Authorization remains before existing
dense/sparse enumeration. The active runtime continues to fail closed because concrete
production adapters remain absent.

## 5. Validation performed

- Read-only SQLite connection used `mode=ro&immutable=1`.
- SQLite integrity: `ok`.
- Focused existing V2 authorization/runtime/candidate tests: **24 passed**.
- Ruff on affected V2 files: **PASS**.
- Strict mypy on the existing V2 application/factory/candidate modules: **PASS**.
- Compileall: **PASS**.
- `git diff --check`: **PASS**.
- Pytest emitted only a Windows cache cleanup warning; no test failed.

No adapter smoke test was run because a truthful production composition cannot yet be
constructed.

## 6. Protected-state verification

Read-only post-audit evidence:

- Golden corpus: 44 files; composite digest
  `92f806fe1a06a1dfa4443ffebe04c2f9aadca1bcf72811ac3110da1c113dba45`.
- `manuscript.pdf`:
  `31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085`.
- Ramayana PDF:
  `759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75`.
- V2 database:
  `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`.
- Active alias remains
  `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0`.
- Active four-generation membership remains unchanged.

No corpus, database, index, generation, alias, model, or V1 state was written. No
provider inference, retrieval, benchmark, Decision-7, WP-16, or evaluation ran.

## 7. Exact next phase

Authorize a narrow contract/storage remediation that:

1. propagates `V2RetrievalAuthorizationDecisionV1` through evidence resolution,
   candidate building, and advanced projection;
2. freezes and persists the canonical SHA-256 database identity;
3. defines and tests the active vector-generation to embedding-source-generation read
   binding without rebuilding or changing the existing index;
4. updates the active inspector contract to verify alias, profile, database, build run,
   dependency graph, checksums, and vector space together.

Only after those three conflicts are resolved can the five adapters be implemented
without inventing semantics.

## 8. Lifecycle

DECLARED: PASS  
IMPLEMENTED: PASS  
CONFIGURED: PASS  
BUILDABLE: PASS  
READY: PASS  
ACTIVE: PASS  
EXPOSED: FALSE  
EVALUATED: FALSE  
VERIFIED: FALSE  
CERTIFIED: FALSE
