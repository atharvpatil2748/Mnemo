# ADR-0054: Final-QA Citation Compliance Retry Contract

- **Status:** Accepted
- **Date:** 2026-08-20
- **Extends:** ADR-0044, ADR-0045, ADR-0052
- **Supersedes:** ADR-0044/0046 no-retry semantics only for one failed final-publication citation-compliance attempt; ADR-0048 prompt routing only for strict persisted Final QA

## Context

ADR-0052 correctly requires strict final-publication citation compliance but
does not define the second provider invocation.  ADR-0044 freezes first-pass
prompt and output preservation, so retry behavior cannot be inferred or
implemented as marker normalization.

## Decision

The first generation remains the exact ADR-0044 operation: its system
instruction and sole user message are unchanged. ADR-0048's adaptive prompt
templates are therefore not used by strict persisted Final QA; they remain a
legacy preview concern until separately reconciled. A failed mechanical
compliance check permits exactly one second `LLMInterfaceV1.complete()` call on
the same resolved `llm/synthesizer`, model, registry, token counter,
`max_output_tokens`, and exact retained `ContextBuildResult`.

The second call uses the identical first-pass system instruction and immutable
original user message byte-for-byte, followed by one additional USER message
whose exact content is:

```text
CITATION_COMPLIANCE_CORRECTION
Generate a replacement answer only. Reuse the QUESTION and CONTEXT already supplied. Do not discuss, quote, or preserve the prior answer. Every evidence-backed claim must use only exact ASCII citations in the form [source:N], where N is an available Source number. Include at least one such citation. Do not use case variants, malformed markers, unavailable source numbers, or a references section.
```

The prior generated answer is deliberately not supplied: it is untrusted model
output, is not provenance, and is unnecessary to state the mechanical
constraint.  No provider-specific parameter, model change, temperature change,
or hidden configuration is introduced.

## Validation and token accounting

The same provider-neutral validator runs after each response.  It scans the
whole answer in ASCII mode, accepts only ADR-0045 `[source:N]`, requires at
least one marker for generated final publication, and validates each number
against the retained `ContextItem.source_number` set.  Any ASCII case-insensitive
`[source:`-shaped construct that is not canonical, a malformed canonical
prefix, an unknown number, or no marker is non-compliant.  It never rewrites
text, infers provenance, or creates a citation.

For the retry, compute:

```text
counter.count(first_pass_system_instruction)
+ counter.count(original_user_message)
+ counter.count(CITATION_COMPLIANCE_CORRECTION)
+ max_output_tokens
<= synthesizer.max_context_tokens
```

Failure of this preflight is `ContractValidationError` and invokes no retry.
The retry response is validated, stripped, model-identity checked, surrogate
checked, and output-count checked exactly as ADR-0044 requires.  Its generation
evidence describes the actual retry call; structured operational logging emits
`citation_compliance_retry` with attempt `1`, never answer or context text.

## Failure and lifecycle

There is no timeout, cache, fallback, or loop.  Caller cancellation propagates
unchanged.  A second non-compliant response raises `IntegrityError` with the
observable classification `citation_compliance` before assistant-turn creation,
publication, or citation persistence.  First-pass non-compliance is not
published.  `NO_CONTEXT` invokes neither generation nor validation retry.

ADR-0045 continues to own final marker resolution, deterministic citation
construction, and persistence after the retry output is compliant.  Direct
Module 6.9 callers retain ADR-0045 `UNMARKED`; this contract applies only to
strict final publication.

## Compatibility and tests

No frozen model/interface changes.  The retry adds at most one provider call
and its prompt-token cost.  Tests must prove exact first-pass preservation,
exact correction content/order, same context identity/model/configuration,
one-call bound, all marker variants, valid maximum source number, no-context,
preflight failure, cancellation, retry exhaustion, and no turn/citation write
before compliance.
