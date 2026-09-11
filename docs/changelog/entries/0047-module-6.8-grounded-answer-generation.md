# Changelog 0047: Module 6.8 Grounded Answer Generation

## Status

Module 6.8 is implemented and locally validated under ADR-0044. This remains
unreleased Phase 6 work; version 0.20.1 and all existing tags are unchanged.

## Changes

- Added immutable `GroundedAnswerStatus`, `GenerationEvidence`, and
  `GroundedAnswerResult` records retaining the exact ADR-0043 context result.
- Added backend-neutral `GroundedAnswerGenerator` using the existing frozen
  registry, `llm/synthesizer`, `LLMInterfaceV1.complete()`, and canonical token
  counter.
- Implemented the exact grounded prompt, exact question/context envelope,
  provider-window preflight, output bound, text completion validation, and
  generation token evidence required by ADR-0044.
- Added typed no-context handling that avoids provider resolution for all four
  ADR-0043 empty outcomes.
- Preserved marker-bearing answer text and the full provenance chain without
  citation parsing, citation creation, persistence, or storage access.
- Added 29 focused tests and a real Bhagavad Gita Module 6.7 handoff acceptance
  runner with durable evidence.

Real acceptance retained four context items and six omissions, used exactly
1,596 context tokens, produced a 19-token answer containing `[source:1]`, and
preserved the exact query, context result, canonical chunks, and prior-stage
evidence.

Module 6.9 and Module 6.10 remain not started, and milestone M6 is not verified.
