# ADR-0067: Multilingual Retrieval and Derived Translation

- **Status:** Accepted
- **Implementation:** Implemented/tested foundation in Phase 8.5.9; concrete
  provider/model profiles remain `UNVALIDATED` pending Phase 8.5.11 benchmarking
- **Date:** 2026-08-24
- **Extends:** ADR-0018, ADR-0039 through ADR-0042, ADR-0061, ADR-0062
- **Supersedes:** Nothing

## Context

Language support spans parsing, OCR, sparse analysis, embeddings, reranking,
query planning, generation, and evaluation. Replacing only the embedding model
does not create a reliable multilingual stack.

## Problem

Mnemo needs same-language and cross-language retrieval while keeping original
text authoritative and avoiding unbenchmarked language claims.

## Decision

Store versioned BCP-47 language and script observations as derived provenance
at document/block/region granularity with confidence and detector identity.
Never overwrite original parser/OCR text. Translation is an optional immutable
ADR-0060 derivation linked segment-by-segment to the original.

Add language-aware sparse analyzer generations, benchmark-selected multilingual
text/image embedding spaces, multilingual reranker profiles, and a planner
policy that records query language/script and chosen same-language,
transliteration, translation, or cross-language paths. Results preserve the
original evidence and label derived matches. Final QA uses an explicit answer
language policy and cites original evidence; translated display is secondary.

Initial certification targets English, Hindi, and Marathi, including each
same-language direction and requested cross-language directions. This is an
evaluation scope, not hard-coded runtime logic. Other languages remain
`UNVALIDATED` until their published benchmark gate passes.

## Alternatives

- Translate everything to English: rejected due to loss and cost.
- Trust model marketing claims: rejected without directional benchmarks.
- Change canonical language fields: rejected because observations are uncertain.

## Consequences

Multiple analyzer/model generations and per-direction evaluation are required.
Fallbacks are explicit and may return reduced capability rather than fabricate
quality.

## Compatibility

Current English/text indexes and retrieval remain valid. Language-aware paths
are selected only when enabled; canonical chunks and citations are unchanged.

## Migration

Build derived observations/translations/index generations side-by-side. Promote
profiles only after benchmark acceptance; rollback switches aliases/policy.

## Security implications

Translation/provider egress needs consent. Prompt-injection defenses apply in
every language/script; authorization precedes translation.

## Testing requirements

Measure same-language and cross-language recall/ranking, transliteration,
mixed-script queries, OCR, negative languages, grounding, citations, fallback,
cache invalidation, and adversarial instructions per direction.

## Observability

Record language/script codes, confidence bands, selected path/profile,
direction, quality cohort, latency/cost, and fallback reason without text.

## Rollback/recovery

Disable multilingual profiles and retain current English/text generation.
Derived translations remain non-authoritative and removable by policy.

## Future-phase impact

Phase 9 exposes language selection/status; Phase 11 reasons across languages
only with preserved original provenance.

## Explicit non-goals

This ADR does not claim universal language support or select models before
benchmarking.
