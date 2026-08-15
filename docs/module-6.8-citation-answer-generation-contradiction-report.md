# Module 6.8 Citation / Answer-Generation Contradiction Report

- **Status:** BLOCKED â€” architectural decision required
- **Date:** 2026-08-13
- **Scope:** Phase 6 Module 6.8 only
- **Implementation:** Not started

## Requirement

Module 6.8 must consume the complete ADR-0043 `ContextBuildResult` through an
explicit immutable contract, preserve provenance, perform only its assigned
Phase 6 responsibility, and provide an unambiguous typed handoff to Module 6.9.
No frozen Phase 1 or Phase 6 contract may be changed or bypassed.

## Repository evidence inspected

- `docs/mnemo_engineering_roadmap.md`, Modules 6.7â€“6.10 and Phase 6 tests
- `docs/mnemo_architecture_v2.md`, retrieval pipeline, `ContextBuilder`,
  `CitationEngine`, registry, and pipeline diagram
- ADR-0001 conversation and citation model semantics
- ADR-0002 storage and error contracts
- ADR-0041 through ADR-0043 stage boundaries
- `ContextBuildResult`, `ContextItem`, and `DocumentContextLabel`
- `Citation`, `Turn`, and `Session`
- `LLMInterfaceV1`, `PluginRegistry`, and the existing `llm/synthesizer` role
- `StorageInterfaceV1` citation operations and their Composite/SQLite/Qdrant/
  SurrealDB implementations
- current `KnowledgeEngine` provider composition

## Contradiction 1 â€” Module identity and ordering conflict

The authoritative repository roadmap labels Module 6.8 **Citation Engine** and
Module 6.9 **Synthesizer**. It requires Module 6.8 to parse `[source:N]` markers
from *synthesized text*, while Module 6.9 is the first stage that produces that
text. The roadmap simultaneously declares Module 6.9 dependent on Module 6.8.

The architecture diagram shows the executable order as:

```text
Context Builder -> Synthesizer -> Citation Engine
```

That order contradicts the detailed numbering/dependency table:

```text
6.7 Context Builder -> 6.8 Citation Engine -> 6.9 Synthesizer
```

The current task also describes Module 6.8 in answer-generation terms. The
repository therefore has two materially different definitions of Module 6.8.
This is not a naming-only discrepancy: each choice has a different input,
provider dependency, output, and failure contract.

## Contradiction 2 â€” ADR-0043 handoff is insufficient for Citation Engine

ADR-0043 states that Module 6.8 receives `ContextBuildResult`. That object
contains attributed source items and complete retrieval provenance, but it does
not contain:

- synthesized assistant text containing `[source:N]` markers;
- an assistant `turn_id`;
- a citation timestamp or citation-record identity;
- a persistence transaction/request; or
- an answer-generation result.

Consequently, the documented Citation Engine cannot execute from its only
accepted input. Parsing `ContextBuildResult.rendered_context` is both
architecturally forbidden and ineffective: its markers are context headers
(`=== Source [N] ... ===`), not assistant-answer citations (`[source:N]`).

## Contradiction 3 â€” canonical output and next-stage handoff are undefined

No repository contract defines what Module 6.8 returns. It is unspecified
whether output is:

- synthesized answer text;
- `tuple[Citation, ...]`;
- a typed answer plus unresolved markers;
- a typed citation-resolution result retaining `ContextBuildResult`;
- a persistence receipt; or
- a combined answer/citation result.

There is likewise no defined Module 6.8 -> 6.9 signature. A string-only output
would lose the ADR-0043 provenance chain, while `tuple[Citation, ...]` cannot be
created before synthesized text and assistant-turn identity exist.

## Contradiction 4 â€” citation resolution semantics are incomplete

ADR-0001 fixes the persisted `Citation` fields and requires the quote to be
verbatim evidence from the referenced canonical chunk. The remaining creation
semantics are undefined:

- accepted marker grammar, case sensitivity, whitespace, and malformed marker
  behavior;
- repeated marker behavior and output ordering;
- unknown or omitted source numbers;
- whether one source may produce one or several citation records per turn;
- deterministic `citation_id` generation and `created_at` ownership;
- exact quote selection and boundaries within canonical `Chunk.text`;
- how a citation derived from a compressed `ContextItem` selects a verbatim
  canonical quote;
- whether an answer may contain no markers or cite an omitted item; and
- whether invalid markers reject the whole answer or produce a typed partial
  outcome.

Implementing any of these choices would invent public behavior.

## Contradiction 5 â€” required title versus optional label

ADR-0043 deliberately makes exact-version `DocumentContextLabel` values
partial and permits a context item with no title. ADR-0001 requires every
persisted `Citation.document_title` to be non-empty. Module 6.8 has no lawful
rule for resolving a missing title and must not invent a metadata key or query
storage behind the context boundary.

The architecture must choose whether citation creation requires a complete
label set, accepts a separately supplied immutable title mapping, defers
persistence, or changes another non-frozen boundary. Silent placeholder titles
are not compliant.

## Contradiction 6 â€” persistence ownership and backend claims conflict

The roadmap says Citation Engine persists every citation in SurrealDB. Actual
storage evidence differs:

- frozen `StorageInterfaceV1` exposes `upsert_citation()`;
- `CompositeStorage` delegates citation persistence to its SQL store;
- `SQLiteStore` implements citation persistence;
- `SurrealDBStore.upsert_citation()` is currently `NotImplementedError`; and
- Qdrant correctly does not implement citation persistence.

No accepted decision selects the canonical backend for Module 6.8. Nor does it
define atomicity between assistant-turn persistence and citation persistence,
rollback/partial failure, idempotency, or whether a pure resolver or a later QA
orchestrator owns writes. Calling SurrealDB directly would violate the storage
boundary; calling `StorageInterfaceV1` would contradict the current prose
without resolving transaction semantics.

## Contradiction 7 â€” answer-generation contract is also incomplete

If Module 6.8 is intended to be answer generation instead, the existing
`llm/synthesizer` registry role and `LLMInterfaceV1` are available, but the
executable contract is still undefined. The repository does not fix:

- the immutable answer-generation input/output models;
- the exact grounded system/user prompts and treatment of context as untrusted
  evidence;
- session-history inclusion and ordering;
- marker-generation grammar;
- streaming versus completed output ownership;
- maximum output tokens and provider-context validation;
- empty-context behavior for each ADR-0043 `ContextEmptyReason`;
- provider absence, malformed output, cancellation, retry, and timeout rules;
- whether citations are validated during generation or only in the following
  stage; or
- the provenance-preserving Module 6.9 handoff.

Using `LLMInterfaceV1.complete()` or `stream()` without these decisions would
silently invent the answer protocol.

## Affected contracts and files

The contradiction affects, but does not authorize changes to:

- `ContextBuildResult` and `ContextItem`;
- `Citation`, `Turn`, and `Session`;
- `LLMInterfaceV1` and registry slot `llm/synthesizer`;
- `StorageInterfaceV1` citation operations;
- `KnowledgeEngine` composition;
- the roadmap Modules 6.8 and 6.9;
- the architecture `Synthesizer -> CitationEngine` pipeline; and
- the future final QA integration boundary.

No frozen contract was modified during this investigation.

## Considered compliant resolutions

### Option A â€” correct detailed numbering to executable pipeline order

Define Module 6.8 as grounded answer generation consuming
`ContextBuildResult`, and Module 6.9 as citation resolution/persistence
consuming the typed answer result plus the exact `ContextBuildResult` and
assistant-turn identity. This matches the architecture pipeline and removes
the impossible forward dependency. It requires an additive answer result and
an accepted generation contract, followed by a separate citation ADR/contract.

### Option B â€” retain numbering but split citation preparation from resolution

Module 6.8 could prepare a source-number-to-context-item index without parsing
synthesized text or creating `Citation` records; Module 6.9 could synthesize,
then a later final-integration stage could resolve and persist citations. This
would require changing the roadmap's Module 6.8 responsibility and leaves the
meaning of "Citation Engine" incomplete until a later stage.

### Option C â€” combine synthesis and citation resolution in Module 6.8

Rejected as the default because it collapses the documented 6.8/6.9 boundary,
duplicates a separately scheduled Synthesizer, and prematurely decides final
QA/persistence orchestration.

### Option D â€” fabricate synthesized text or placeholder citations

Rejected. It would violate canonical provenance, title, quote, and persistence
invariants and disguise architectural incompleteness as implementation.

## Recommended minimum architectural decision

Create the next unique ADR (currently expected to be ADR-0044 after a fresh
number check) that first reconciles the phase sequence. The smallest coherent
direction is **Option A**:

1. Module 6.8 becomes grounded answer generation because it can lawfully
   consume the exact ADR-0043 `ContextBuildResult`.
2. It returns a new additive immutable answer-generation result retaining the
   exact `ContextBuildResult` and generated marker-bearing answer text.
3. The ADR defines exact prompt/messages, output-token bounds, empty-context,
   provider absence/failure, malformed output, cancellation, streaming, and
   deterministic orchestration semantics using existing `llm/synthesizer`.
4. Module 6.9 becomes citation resolution/persistence and receives the exact
   answer result plus the assistant-turn/persistence inputs selected by its own
   accepted contract.
5. The citation decision separately fixes marker grammar, title completeness,
   verbatim quote selection (including compressed items), deterministic record
   identity/time ownership, repeated/invalid markers, storage ownership, and
   transaction/failure behavior.

This recommendation is not implemented or accepted by this report. Maintainer
approval and a complete ADR are required.

## Compatibility and migration impact

An additive result-contract approach can preserve all frozen interfaces and
models. No data migration is required merely to resolve numbering. Citation
persistence may require a later reconciliation of the stale SurrealDB claim
with the implemented Composite/SQLite boundary, but no storage mutation or
migration is authorized here.

Historical M4/M5 evidence, existing Phase 6 evidence, version 0.20.1, and the
v0.20.1 tag remain untouched.

## Stop decision

Module 6.8 remains **BLOCKED / NOT IMPLEMENTED**. No production code, tests,
implementation report, changelog, roadmap completion mark, provider call,
storage call, or golden acceptance was created. Modules 6.9 and 6.10 remain
**NOT STARTED**, and M6 remains **NOT VERIFIED**.

## Resolution addendum — ADR-0044

The execution-order contradiction above is confirmed and resolved by accepted
ADR-0044, `Grounded Answer Generation and Citation Pipeline`. Option A was
selected: Module 6.8 is now Grounded Answer Generation, Module 6.9 is Citation
Resolution and Persistence, and Module 6.10 is Final QA Integration. The active
roadmap and architecture now follow `ContextBuilder -> Grounded Answer
Generation -> Citation Engine -> Final QA Integration`.

This addendum changes architectural status only. Module 6.8 production
implementation has **NOT STARTED**. Module 6.9 and Module 6.10 remain **NOT
STARTED**, and M6 remains **NOT VERIFIED**. The historical findings above are
preserved as the evidence that required ADR-0044.

## Implementation addendum — Module 6.8

ADR-0044 was subsequently implemented and validated by the focused Module 6.8
test suite, full repository validation, and the real Bhagavad Gita Module 6.7
handoff recorded in `docs/milestone-evidence/module-6.8-grounded-answer.json`.
Module 6.8 is now **COMPLETE**. Module 6.9 and Module 6.10 remain **NOT
STARTED**, and M6 remains **NOT VERIFIED**. This addendum does not alter the
historical contradiction or its architectural-resolution record.
