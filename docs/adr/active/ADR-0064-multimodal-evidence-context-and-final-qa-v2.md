# ADR-0064: Multimodal Evidence, Context, and Final QA V2

- **Status:** Accepted
- **Implementation:** Implemented/Tested (Phase 8.5.8)
- **Date:** 2026-08-24
- **Extends:** ADR-0043 through ADR-0047, ADR-0052, ADR-0054 through ADR-0056
- **Supersedes:** Nothing

## Context

V1 context and citations are deliberately chunk/text specific. Images, OCR
regions, VLM observations, table rows, and document ranges cannot be honestly
flattened into V1 `Citation` snapshots.

## Problem

Multimodal answers need typed evidence, original-versus-derived provenance,
bounded binary context, citation compliance, safe publication, and exact
idempotent replay without changing `[source:N]` behavior for V1.

## Decision

Add, alongside V1, `EvidenceCandidateV2`, `MultimodalContextBuildResultV1`,
`EvidenceCitationV2`, `FinalQARequestV2`, `FinalQAResultV2`, and versioned V2
execution snapshots. Candidate kinds include canonical chunk, document range,
table row/cell/result, original asset occurrence, OCR region, VLM observation,
and visual-vector match. Every derived candidate links to its original
occurrence/asset and derivation provenance.

Context has separate token, byte, page/slide, asset, and decoded-pixel budgets.
It retains source numbering, deterministic ordering, completeness, omission
reasons, MIME descriptors, and authorized resource handles. Binary bytes are
not embedded in prompts unless the selected provider contract explicitly
supports them.

Canonical answer markers remain exact case-sensitive `[source:N]`. V2 source
numbers resolve to typed evidence snapshots. The ADR-0054 one-corrective-retry
rule, validation-before-publication, ADR-0056 execution claim/replay/resume,
and zero-provider-call replay all apply to V2. Fingerprints additionally bind
evidence-contract version, resource manifests, completeness, provider modality
capability, and all budgets.

## Alternatives

- Reuse V1 `Citation`: rejected because it requires a chunk.
- Convert every visual to text: rejected because the original evidence vanishes.
- Change V1 markers: rejected because the grammar is frozen and sufficient.

## Consequences

Two explicit generations coexist. Adapters can render common fields but cannot
silently convert V2 evidence into V1 persisted citations.

## Compatibility

All V1 Final QA routes, schemas, persistence, marker grammar, retry, and replay
remain unchanged. V2 uses a new endpoint/interface and snapshot schema.

## Migration

Add V2 execution/evidence tables. V1 executions remain replayable only as V1;
no provenance is reconstructed or upgraded.

## Security implications

Context construction reauthorizes every occurrence/resource and treats all
OCR/VLM/document instructions as untrusted evidence. Snapshots exclude secrets
and raw provider reasoning.

## Testing requirements

Test every evidence kind, mixed-modality budgets, completeness, authorization,
marker validation/retry/exhaustion, publication order, immutable snapshots,
crash/concurrency/resume, and exact zero-call replay.

## Observability

Record evidence kinds/counts, budget use, completeness, retry class, execution
state, and provider modality without content.

## Rollback/recovery

Disable V2 capability advertisement/routes and retain immutable snapshots. V1
continues unchanged.

## Future-phase impact

Phase 9 renders typed evidence; Phase 11 can reason across evidence kinds while
preserving individual provenance.

## Explicit non-goals

This ADR does not loosen grounding, expose chain of thought, or make derived
analysis authoritative.
