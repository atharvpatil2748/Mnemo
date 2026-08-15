# Phase 6 Comprehensive Audit Contradiction Report

## Status

**BLOCKED — architectural approval required before M6 verification or release.**

Date: 2026-08-13

## Requirement

The accepted Phase 6 runtime must compose `KnowledgeEngine` through
`MultiSourceRetriever` with one source-local `ParentRetriever`, then complete
the real Phase 0–6 Bhagavad Gita path before milestone M6 or release.

## Authoritative contracts

- ADR-0040 defines the additive parent-promotion slot as
  `parent_promotion/default`.
- ADR-0041 requires `MultiSourceRetriever` to resolve and invoke
  `parent_promotion/default` exactly once per source-local stream.
- ADR-0047, accepted later for final-QA runtime composition, explicitly requires
  `KnowledgeEngine` to register and validate `parent_promotion/primary`.

These names identify different registry slots; registry resolution does not
alias them.

## Actual implementation

- `MultiSourceRetriever._preflight()` correctly follows ADR-0041 and resolves
  `parent_promotion/default`.
- `KnowledgeEngine` follows ADR-0047 and registers/validates
  `parent_promotion/primary`.
- Module 6.5 tests register `default`; Module 6.10 engine tests register/check
  `primary`. Consequently, both isolated suites pass while the composed graph
  is non-executable.

## Real rebuild evidence

A fresh timestamped Phase 0–6 run parsed and chunked the canonical PDF, created
a cold embedding cache, embedded and independently indexed 1,000 chunks in a
new empty Qdrant collection, initialized real Ollama `gemma4:e4b`, loaded the
pinned cross-encoder, persisted the user session, and produced a real structured
retrieval plan. The first retrieval/fusion preflight then failed with:

```text
DependencyUnavailableError: parent_promotion/default capability is unavailable
```

The failed run's Qdrant collection was deleted. The source PDF remains present
with SHA-256
`ff112b0b056d303b792f6f2e68cbd73a89adf612fa9113f932446cdea7741583`.

## Why this is a genuine contradiction

Changing either slot silently would violate an accepted ADR. Registering both
names would create two public capability identities for one V1 contract and
would conceal rather than resolve the ownership conflict. No frozen interface
change is needed, but one accepted decision must explicitly choose the
canonical slot.

## Smallest compatible resolution

Amend or supersede only ADR-0047's composition wording so that
`KnowledgeEngine` registers and validates `parent_promotion/default`, preserving
ADR-0040 and ADR-0041 and requiring no migration. Then update the engine
composition tests, rerun the clean rebuild from the PDF, complete the remaining
audit, run the full validation suite, and only then execute M6.

The larger alternative is to supersede the slot semantics in ADR-0040 and
ADR-0041, change Module 6.5 plus all registry/tests/documentation references to
`primary`, and record the compatibility impact. This has no demonstrated
benefit and is not recommended.

## Additional audit findings fixed before the blocker

- Added the architecture-promised local Ollama `LLMInterfaceV1` adapter through
  the existing `llm/<role>` registry family; no frozen contract or new registry
  family was introduced.
- Added missing engine-owned `CompositeStorage` startup/shutdown hooks, guarded
  so inactive lower-priority built-ins are not started.
- Added recursive immutable-schema conversion at the Ollama wire boundary.
- Added an official clean M6 runner, which remains failing by design until this
  architectural contradiction is resolved.

Focused Ollama/engine tests, Ruff, and strict production mypy passed after
these corrections. Comprehensive validation, M6, version bump, commit, tag,
push, and release were not performed.

## Compatibility and migration

- Frozen contracts modified: **NO**.
- Storage/schema migration required by the recommended resolution: **NO**.
- Historical v0.20.1 tag modified: **NO**.
- M6 status: **NOT VERIFIED**.
- Release status: **NOT CREATED**.

---

## Resolution Addendum

**Date:** 2026-08-14
**Resolution status:** APPLIED — blocker resolved

The recommended resolution (amend ADR-0047 to use `parent_promotion/default`)
was applied in full. All historical evidence above is preserved unchanged.

### ADR-0047 amendment

`docs/adr/ADR-0047-final-qa-runtime-composition.md`

- Status updated to `ACCEPTED — AMENDED 2026-08-14`.
- Composition ownership section: `parent_promotion/primary` corrected to
  `parent_promotion/default` with inline amendment note recording the original
  (erroneous) text, the authoritative ADR references, and the rationale.
- Provider validation section: `parent_promotion/primary` corrected to
  `parent_promotion/default` with inline amendment note.
- No frozen Phase 1 contracts or other accepted ADRs were changed.

### KnowledgeEngine implementation correction

`mnemo-core/mnemo/engine.py`

- `CoreRetrievalPlugin.register()`: `register_parent_promoter("primary", ...)` →
  `register_parent_promoter("default", ...)`.
- `_compose_final_qa()`: `resolve_parent_promoter("primary")` →
  `resolve_parent_promoter("default")`.

### Engine unit test correction

`mnemo-core/tests/unit/test_engine.py`

- `_phase6_plugin()`: `register_parent_promoter("primary", ...)` →
  `register_parent_promoter("default", ...)`.

### Preserved without change

- ADR-0040: unchanged.
- ADR-0041: unchanged.
- `ParentPromotionInterfaceV1`: unchanged.
- `RetrieverInterfaceV1`: unchanged.
- `StorageInterfaceV1`: unchanged.
- `MultiSourceRetriever._preflight()`: unchanged (already used `"default"`).
- Module 6.4 and 6.5 tests: unchanged (already used `"default"`).
- All historical contradiction evidence above: unchanged.

### Post-resolution compatibility

- Frozen contracts modified: **NO**.
- Storage/schema migration required: **NO**.
- Historical v0.20.1 tag modified: **NO**.
- M6 blocker resolved: **YES** — composed pipeline no longer raises
  `DependencyUnavailableError: parent_promotion/default capability is unavailable`.
- M6 status: **PENDING** — comprehensive architecture audit and real Ollama
  rebuild must still complete before M6 can be executed.
- Release status: **NOT CREATED**.
