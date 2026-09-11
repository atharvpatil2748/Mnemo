# Full Multilingual V2 — Runtime Composition and Evaluator Parity Report

**Result:** internal composition contract implemented; real ACTIVE-to-EVALUATED execution remains blocked until the central V2 security/evidence adapters are implemented and registered.

## 1. Original blocker

The active V2 alias set could be resolved from storage, but no production/internal factory consumed it to construct `FullMultilingualRetrievalApplicationV2`. The only prior construction was a unit test. An evaluator would consequently have needed direct provider/table access or evaluator-side candidate construction, all of which are forbidden.

## 2. Implemented internal-only composition boundary

Added `mnemo.phase85.v2_evaluation_runtime`:

- `FullMultilingualV2EvaluationRuntimeFactory` resolves only `resolve_active_multilingual_v2_generation_set()`; it accepts no generation ID, vector space, or alias override from the evaluator.
- `V2RuntimeIdentityV1` binds profile ID/fingerprint, V2 database identity, build-run ID, active-alias digest, canonical vector space, preprocessing, authorization, provenance, reranker protocol, and provider identities.
- `ActiveV2GenerationInspector` supplies governed generation evidence. The factory rejects a missing/partial/duplicate alias, mismatched membership/order, non-ready or incomplete generation, incorrect profile, and vector-space mismatch before it builds a dense/sparse source.
- The factory composes the existing authorization-first dense and sparse retrieval classes, the shared `RerankerCandidateBuilderProtocolV1`, public V3 reranker protocol, operation admission, query-language resolver, advanced projector, and `FullMultilingualAdvancedSourceV2`.
- `InternalFullMultilingualV2Evaluator` receives only a `ComposedFullMultilingualV2Runtime`. It owns no provider, storage, generation-selection, or candidate-construction handle. Any later retrieval delegates to the already composed `FullMultilingualRetrievalApplicationV2`.

This is internal-only. It does not alter KnowledgeEngine public composition, V2 capability discovery, HTTP, MCP, stdio, or SSE. Therefore `EXPOSED` remains false.

## 3. Dependency graph

```text
active V2 alias resolver
  -> generation inspector + governed identity validation
  -> authorized source enumerator + V2 storage adapters
  -> exact active vector/sparse generation IDs
  -> FullMultilingualRetrievalApplicationV2
  -> FullMultilingualAdvancedSourceV2
  -> InternalFullMultilingualV2Evaluator
```

The evaluator cannot skip the shared candidate builder or invoke a provider directly. Candidate construction, source enumeration, authorization, and reranking remain runtime responsibilities.

## 4. Parity and security invariants

`RuntimeParityEvidenceV1` is produced by the composition result with:

- application ID: `mnemo.full-multilingual-retrieval-application/2`;
- shared candidate-builder ID: `mnemo.reranker-candidate-builder/1`;
- governed 256-token reranker policy;
- `direct_provider_calls=false`;
- `private_runtime_access=false`;
- `caller_constructed_reranker_input=false`.

The factory does not provide a permissive evaluator authorizer and cannot make a query reach the embedder, evidence enumerator, candidate builder, or reranker while the active alias/generation/profile/vector validation fails.

## 5. Tests and static validation

| Check | Result |
| --- | --- |
| Factory resolves four active V2 generations and produces parity evidence | PASS |
| Missing active alias fails closed | PASS |
| Vector-space mismatch fails closed before provider work | PASS |
| Existing full multilingual V2 contract tests | PASS: 18 tests with no coverage gate |
| New composition tests | PASS: 3 tests with no coverage gate |
| Ruff on changed Python files | PASS |
| Strict mypy on the new composition module | PASS |
| compileall on the new composition module | PASS |
| Full pytest invocation | NOT USED: focused invocation otherwise fails only repository-wide coverage threshold, not tests |
| JSON Schema validation | NOT RUN: no schema changed |
| `git diff --check` | recorded separately in final validation |

The focused pytest invocation emitted an existing Windows pytest-cache access warning. No test assertion failed.

## 6. Remaining blocker

The repository still has no concrete production implementation/registration for these required central interfaces:

1. `AuthorizedMultilingualSourceEnumeratorV2`;
2. `LanguageEvidenceAuthorizerV3`;
3. `RerankerEvidenceResolverV1`;
4. `V2AdvancedCandidateProjector`;
5. `ActiveV2GenerationInspector` backed by the isolated V2 generation/coverage manifests.

The factory intentionally requires these dependencies instead of recreating them in evaluator code. Supplying ad-hoc SQLite queries, a permissive authorizer, or title-derived candidate text would violate the V2 parity and authorization contract. Therefore a real runtime composition smoke test against the active V2 database was not executed.

## 7. Protected state

No corpus file, canonical text, V1 database/index/alias, WP-10 database, frozen multimodal database, V2 generation, V2 alias, or model artifact was mutated. No model was loaded, no provider inference occurred, and no retrieval/evaluation query was executed.

The active alias remains governed as:

`b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0`

with the existing four ready generation IDs and canonical V2 vector-space identity:

`7dcba654e1c947145253ff65ef93e2b4ef1105cdf680b79218a446c79cc1a0d7`.

## 8. Final lifecycle

```text
DECLARED: PASS
IMPLEMENTED: PASS
CONFIGURED: PASS
BUILDABLE: PASS
READY: PASS
ACTIVE: PASS

EXPOSED: FALSE
EVALUATED: FALSE (BLOCKED: required central V2 evidence/authorization adapters are not yet concrete)
VERIFIED: FALSE
CERTIFIED: FALSE
```

No retrieval evaluation, Decision-7, WP-16, benchmark, qrel construction, metric calculation, public transport exposure, verification, or certification occurred.

