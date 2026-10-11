# ADR-0079 — Automatic representation-complete V2 retrieval

Status: Accepted for implementation; deployment and certification are separate gates.

## Context and problem

Canonical V1 chunks do not contain later OCR/Vision derivations. An image-only PDF can have complete derived records but zero canonical chunks. A normal question must not stop at canonical zero matches or require the user to identify an image or modality. Existing `search_evidence` requires explicit representations; retained V1 query/search responses contain canonical chunk citations.

## Decision

Keep `query_notebook`, `search_all_notebooks`, persisted V1 IR and canonical chunks unchanged. Add a versioned V2 normal-query capability, `query_notebook_v2`, implemented by one shared application service below MCP and HTTP. Its server-owned planner authenticates and authorizes first, resolves an authorized notebook scope, inspects active complete compatible generations and constructs an existing `RetrievalPlanV2`. The client supplies a question and bounded public limits, never actor, path, store, model, generation, source or representation set. Ambiguous or ungoverned multi-notebook scope fails closed. A separate approved membership authority is needed before private multi-principal fan-out can be certified.

For every ordinary ranked question, search canonical text and each applicable ready OCR and Vision text projection, without query-keyword gating. Canonical zero is not terminal. Multilingual derived text participates only with a compatible certified text space. Visual similarity participates only with a compatible ready text-query provider, active complete shared-space generation, authorized scope and evaluated bounded policy. No raw cross-space score comparison. Exhaustive search may not silently omit a required source or describe bounded semantic top-k as exhaustive.

OCR/Vision remain distinct typed V2 candidates with `chunk=None`, real occurrence/derivation/generation/locator and retrieval-path ancestry. Preserve notebook, source, document, version, page, asset, projection and embedding identities. Reuse V2 reciprocal-rank fusion and signed plan/snapshot cursors; bound context diversity by occurrence/page without replacing provenance or inventing uncalibrated modality weights.

The representation decision report distinguishes `searched`, `not_applicable`, `unavailable`, `incomplete`, `failed` and `omitted_by_budget`. A searched zero is only a scoped match result; ranked top-k never proves document-level absence. Missing modalities degrade to available evidence with honest partial coverage. Complete-evidence FinalQA retains its stricter publication gate. Capability discovery distinguishes provider configuration, persisted derivations, complete/ready/active projection, callability, compatibility and certification; storage alone is not activation.

An opt-in PaddleOCR adapter implements `OCRProviderV1` with an exact package version, local model-tree digests, model revision, language, device and preprocessing identity. It is not automatically active: the worker must be configured with this provider and complete governed derivation/projection generations must be built and activated in a new isolated index. Installing the package or persisting OCR records alone does not establish runtime readiness or certification. Provider changes do not change planner, authorization, MCP or provenance. Preserve original bytes and hashes; do not mutate certified Phase 8.5 production, existing Phase 8.6 evaluation or signed certification artifacts. Future production promotion remains separately governed.

## Alternatives rejected

- Expanding frozen V1 query/search semantics: breaks chunk-only citations and compatibility.
- Copying derived text into V1 blocks/chunks: fabricates authored provenance.
- Parallel OCR/Vision search stack: duplicates V2 lifecycle, authorization, fusion and cursor machinery.
- Selecting modalities from words such as “image”: misses ordinary questions.
- Treating READY evaluation projection or stored derivations as production activation: violates lifecycle and isolation.

## Consequences and implementation order

Contract and authorization decision; governed projection path over existing derivations; shared planner and V2 query service; provenance/diversity validation; multilingual derived dense path; bounded OCR-provider adapter; fresh isolated evaluation rebuild; validation and independent certification. No re-index or production activation is authorized by this ADR alone.
