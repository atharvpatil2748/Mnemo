# ADR-0052: Citation Compliance and Final-QA Publication

- **Status:** Accepted
- **Date:** 2026-08-20
- **Extends:** ADR-0044, ADR-0045, ADR-0046, ADR-0047
- **Supersedes (only at the final-publication boundary):** ADR-0046's permissive `UNMARKED` delivery

## Context

ADR-0044 deliberately requires Module 6.8 to preserve provider text and ADR-0045
deliberately treats `[Source:N]` and `[SOURCE:N]` as ordinary prose.  Live
Ollama output demonstrated that prompt wording alone does not guarantee the
canonical `[source:N]` grammar.  The server's legacy `POST /v1/query` synthesis
path also bypasses `FinalQAOrchestrator` and `CitationEngine`, so it cannot
create the ADR-0045 persisted citation snapshots: its request has no session,
user-turn, or caller-owned assistant-turn identity.

## Decision

Citation-bearing final answers are mandatory whenever a non-empty
`ContextBuildResult` is published as a grounded answer.  `NO_CONTEXT` remains
the sole citation-free final outcome.  The canonical grammar remains exactly
ADR-0045's ASCII, case-sensitive `[source:N]`; this ADR does not normalize or
reinterpret provider output.

Add a provider-neutral **citation-compliance validation boundary** after
generation and before assistant-turn creation, final publication, or citation
persistence.  It validates the complete answer text mechanically:

- at least one canonical marker is required for a generated, evidence-backed
  final answer;
- every citation-shaped `[` + ASCII-letter token + `:` occurrence is invalid
  unless it is an exact canonical marker; this catches case variants without a
  provider- or spelling-specific exception;
- ADR-0045 continues to resolve canonical markers against retained typed
  `ContextItem.source_number` values and rejects malformed exact `[source:`
  markers or unknown source numbers.

The validator does not rewrite answer text, infer provenance, or assess the
truth of uncited prose.

## Retry and failure

One corrective regeneration is permitted.  It uses the same retained context
and an additive, provider-neutral correction instruction stating the failed
mechanical constraint and the exact canonical grammar.  The correction is a
successor final-publication contract, not a mutation of ADR-0044's first-pass
prompt or a marker normalizer.  No other retry, fallback, timeout, cache, or
partial result is introduced.

If the first answer is compliant, it is used.  If the corrective answer is
non-compliant, final publication fails with `IntegrityError` before an
assistant turn or citation write.  The failure is observable as
`citation_compliance`; it must retain no provider answer in a final response.
Cancellation propagates.  `UNMARKED` remains a valid direct
`CitationEngine` result for callers outside final publication, but is not a
successful Final-QA delivery state.

## Server boundary

`POST /v1/query` is an evidence/search API and may expose only an explicitly
labelled non-persistent preview.  It must not claim ADR-0045 citation
persistence or silently discard invalid markers.  Persisted grounded delivery
must use a server binding to `FinalQAInterfaceV1` with the exact ADR-0046
session, persisted user-turn, and caller-stable assistant-turn UUID inputs.
That binding owns no duplicate retrieval, generation, marker parsing, or
citation construction; it delegates to the composed final-QA graph.

The server contract for that binding, including endpoint versioning and
authentication, is a Phase-7 successor decision.  Until it exists, the legacy
preview route is not evidence that persisted Final QA has passed certification.

## Compatibility and consequences

No marker case is normalized.  No frozen retrieval, storage, provider, or
provenance model changes.  Existing direct Module 6.9 `UNMARKED` behavior is
preserved; only final publication becomes strict.  The additional call can add
one provider round trip only for non-compliant output.  Tests must cover
canonical, repeated, malformed, case-variant, unknown, no-marker, corrective
success, exhaustion, cancellation, and exact citation provenance cases.

## Rationale

Accepting invalid text as `UNMARKED` violates the final-QA grounding invariant.
Normalizing it would contradict ADR-0044/0045 and hide provider behavior.
Redesigning citations without markers would require a different provenance and
generation protocol.  A bounded explicit validation/retry boundary is the
smallest portable, observable correction.
