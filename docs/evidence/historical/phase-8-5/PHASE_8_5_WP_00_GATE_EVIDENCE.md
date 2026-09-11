# Phase 8.5 WP-00 Gate Evidence

**Work package:** WP-00 — Baseline, Authority, and Successor ADR Freeze  
**Date:** 2026-08-26  
**Verdict:** **WP-00 COMPLETE**  
**Scope:** Architecture/contracts only; no WP-01+ runtime implementation

## Authority and repository facts reviewed

- `docs/governance/historical/PHASE_8_5_COMPLETE_IMPLEMENTATION_PLAN.md`
- `docs/architecture/current/phase8.5_architecture.md`
- `docs/architecture/historical/mnemo_phase8_5_engineering_roadmap.md`
- `docs/architecture/current/mnemo_engineering_roadmap.md`
- `docs/architecture/current/mnemo_architecture_v2.md`
- ADR-0058, ADR-0059, ADR-0061–ADR-0072, the ADR index, and relevant Phase 0–8 interface/composition/retrieval ADRs
- `docs/reports/evaluation/PHASE_8_5_11_EVALUATION_REPORT.md`
- `docs/reports/audits/MCP_SEARCH_TO_DOCUMENT_RETRIEVAL_PROPAGATION_AUDIT.md`
- `docs/reports/architecture/POST_PHASE_8_5_MCP_ARCHITECTURAL_AUDIT.md`
- Phase 8.5 gate evidence and changelog status records
- Current MCP definitions/dispatcher, search schemas/services, bounded delivery,
  storage protocol, engine/configuration, cursor/completeness models, and focused tests

The ADR inventory contained no 0073–0075 conflict. ADR-0073 was the next free
number. Existing worktree changes were treated as runtime fact and preserved.

## Frozen decisions

1. ADR-0073 retains the ten current MCP tools and freezes four additive semantic
   tools: `search_evidence`, `query_structured`, `run_final_qa_v2`, and
   `get_capabilities`. It defines positive/negative guidance, typed envelopes,
   JSON fallback, binary companions, cursors, completeness, provenance,
   next-actions, compatibility, and blind-agent validation.
2. ADR-0074 freezes `Phase85RuntimeV1`, one composition root/profile registry,
   and the declared → configured → buildable → ready → active → exposed →
   verified → certified lifecycle. No state is inferred from an earlier state.
3. ADR-0075 preserves ADR-0072 notebook propagation, unambiguous resolution,
   and fail-closed ambiguity, while superseding its storage-protocol widening
   with additive `DocumentScopeResolverV1`.
4. The pre-ADR-0072 `StorageInterfaceV1` method set is the frozen baseline. The
   current extra `list_sources_for_document` member is explicitly recorded as
   known transitional drift; consumer/protocol migration belongs to WP-01 and
   WP-14, not WP-00.
5. The dependency graph and Phase 11 non-goals are machine-readable and frozen.

## Machine-readable artifacts

- `docs/governance/contracts/phase8_5_capability_matrix.schema.json`
- `docs/governance/contracts/phase8_5_capability_matrix.json`
- `docs/governance/contracts/phase8_5_mcp_contracts.json`

The capability matrix contains every required family and separately records
`code_present`, `configured`, `provider_ready`, `generation_present`,
`generation_active`, `exposed_http`, `exposed_mcp`, `discoverable`,
`behaviorally_verified`, `security_verified`, and `certified`. Unwired Phase
8.5 capabilities are not labeled supported or certified.

## Frozen boundaries

Unchanged: canonical IDs, document/version/source identities, `Chunk.text`, V1
FTS/embeddings/retrieval/reranking, V1 citations/Final-QA, V1 HTTP/streaming,
the original six MCP semantics, and Qdrant optionality.

Reserved for Phase 11: autonomous planning, decomposition, evidence-gap
replanning, adaptive/learned routing, recursive multi-hop, generalized graph
traversal, and open-ended joins. Phase 8.5 supplies deterministic typed
primitives only.

## Focused validation

Initial diagnostic command:

```text
uv run pytest -q tests/governance/test_phase8_5_wp00_contracts.py
```

This found one assertion typo and also invoked the repository-wide production
coverage gate, which is inapplicable to static governance tests. The typo was
corrected; no production code changed.

Final command:

```text
uv run pytest -q --no-cov -p no:cacheprovider tests/governance/test_phase8_5_wp00_contracts.py
```

Result: `8 passed in 0.02s` on the final run.

The tests validate ADR numbering/links/successor relationships, matrix shape
and state implications, the frozen storage signature plus documented drift,
the resolver contract, MCP retained/additive sets and semantic distinctions,
and the dependency/non-goal graph.

Focused static-quality commands:

```text
uv run ruff format --check tests/governance/test_phase8_5_wp00_contracts.py
uv run ruff check tests/governance/test_phase8_5_wp00_contracts.py
git diff --check -- <WP-00 files>
```

Results: Ruff format/check PASS; WP-00 diff check PASS.

The JSON Schema itself and the capability instance were also validated with
`jsonschema.Draft202012Validator`; result: schema valid, instance valid.

## Remaining implementation work

There is no unresolved WP-00 architectural contradiction. The documented
runtime, projection, exposure, discoverability, and certification gaps remain
open by design for WP-01–WP-17. Phase 8.5 is not certified complete.
