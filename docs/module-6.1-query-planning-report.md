# Module 6.1 — Query Planning Report

## Scope and verdict

Module 6.1 is implemented, unit-tested, and locally validated. It adds the
typed query-planning boundary, intent detection, bounded query decomposition,
HyDE expansion, and HyDE paragraph embedding. It performs no retrieval and
does not start Module 6.2 or any later Phase 6 module. Milestone M6 remains
unverified.

## Architecture consulted

The implementation was checked against:

- `docs/mnemo_architecture_v2.md`, especially sections 4.2, 8.6, 11, 12,
  13, and 14;
- the Phase 6 Module 6.1 tasks and test plan in
  `docs/mnemo_engineering_roadmap.md`;
- ADR-0001 for the deferred retrieval models and frozen `MetadataFilter`;
- ADR-0002 for `LLMInterfaceV1`, `EmbeddingProviderV1`, and registry contracts;
- ADR-0003 for the configured planner LLM role; and
- ADR-0004 for `KnowledgeEngine.llm("planner")`, primary embedding resolution,
  and lifecycle boundaries.

No accepted ADR required modification. `RetrievalPlan` and `SubQuery` were
explicitly deferred to Phase 6 by ADR-0001, so defining them does not modify a
frozen Phase 1 contract.

## Existing contracts reused

- `MetadataFilter` remains the only typed retrieval-filter model.
- `LLMInterfaceV1.complete(..., structured_output=...)` is the sole planner
  LLM boundary.
- `CompletionResult` carries the structured response.
- `Message`, `Turn`, and their existing role enums carry conversation context.
- `EmbeddingProviderV1` is the HyDE embedding boundary. A configured
  `CachedEmbeddingProvider` remains usable transparently because it implements
  this interface; no provider or cache is bypassed or recreated.
- The existing planner LLM registry role and primary embedding-provider slot
  are sufficient. No planner registry slot was added.

## RetrievalPlan schema

`mnemo.models.retrieval` now defines immutable, extra-forbidding Pydantic
models and enums:

- `RetrievalIntent`: `factual`, `comparative`, `exploratory`, `synthesis`;
- `RetrievalMode`: `dense`, `sparse`, `hybrid`, `graph`, `parent`;
- `SubQuery`: `query_text`, `retrieval_mode`, `filters`, `max_results`;
- `RetrievalPlan`: `intent`, `sub_queries`, `requires_multi_hop`,
  `requires_multi_doc`.

The checked-in roadmap is authoritative for the canonical field names. It uses
`sub_queries` and `requires_multi_hop`; alternate prompt shorthand such as
`decomposition`, `requires_graph`, and planner-owned time/context budgets was
not introduced as a parallel schema.

Validation is deterministic and fail-closed:

- one to sixteen sub-queries are required;
- every query is non-empty and whitespace-normalized;
- retrieval modes and intents are enumerated;
- filters must validate as `MetadataFilter`;
- `max_results` is a strict integer from 1 through 100;
- boolean flags are strict booleans;
- extra fields are forbidden; and
- semantic duplicate sub-queries are rejected rather than silently removed.

## QueryPlanner and LLM boundary

`QueryPlanner` accepts only `LLMInterfaceV1` and `EmbeddingProviderV1`. The
planner submits the Pydantic-generated JSON Schema as immutable JSON metadata,
accepts only `CompletionResult.structured`, and validates the result as
`RetrievalPlan`. Text responses, missing fields, invalid enums, invalid nested
filters, extra fields, empty HyDE text, or plans without a dense/hybrid HyDE
query raise `IntegrityError`. Provider exceptions propagate without an
invented fallback plan.

The caller supplies the active notebook table of contents, source titles, and
recent turns explicitly. The planner performs no storage lookup. It injects at
most the last three supplied turns, preserving the architecture's working
memory boundary while leaving session retrieval to later orchestration.

## Intent and decomposition

Intent selection and decomposition occur inside the single structured planner
call. A factual plan may contain one sub-query; comparative, exploratory, and
synthesis plans may contain multiple ordered sub-queries. The planner does not
execute them, resolve retrievers, or access a backend.

## HyDE and embedding boundary

The structured planner prompt requires at least one dense or hybrid
`SubQuery.query_text` to be a hypothetical paragraph resembling relevant
source prose. It explicitly prohibits citations, quotations, page numbers,
document/source IDs, and claims of evidentiary certainty.

`embed_hyde()` embeds the first validated dense/hybrid paragraph through the
injected `EmbeddingProviderV1`. It never embeds the original question. It
validates vector presence, finiteness, and dimensions. The transient vector is
returned separately and is not added to the durable `RetrievalPlan` schema.

## Validation evidence

Executed locally on Windows with Python 3.12.10 on 2026-08-13:

- Focused: `uv run pytest mnemo-core/tests/unit/test_query_planner.py -q --no-cov`
  — 37 passed.
- Repository regression and coverage: `uv run pytest` — 799 passed, 1 skipped,
  90.26% total coverage.
- Focused production/test mypy during implementation: passed.
- Ruff checks during implementation: passed.

The final repository-wide Ruff, production mypy, and pre-commit results are
recorded in the task handoff after their final execution.

Pytest emitted a non-failing local cache cleanup warning because the existing
Windows `.pytest_cache`/temporary pytest path was not writable. Test execution
and the coverage gate completed successfully.

## Architectural decisions and limitations

- No concrete Ollama or cloud LLM adapter was added. Planner implementations
  remain plugin-provided and registry-resolved as required by ADR-0004.
- No live planner-LLM integration test was run; unit tests use deterministic
  interface-conforming stubs.
- No storage access, retrieval execution, reranking, context construction,
  synthesis, citation handling, or multi-hop orchestration was added.
- No ADR was necessary because no frozen interface or lifecycle boundary was
  changed.

Modules 6.2, 6.3, 6.4, and 6.5 were not started. M6 was not verified.
