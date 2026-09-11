# Phase 8.5 WP-13 Gate Evidence

Status: **COMPLETE**

## Scope implemented

WP-13 exposes one deterministic capability document through `GET
/v2/capabilities`, MCP `get_capabilities`, and the existing
`mnemo://capabilities` resource. All three are projections of
`Phase85RuntimeV1`; no second capability registry or lifecycle state machine was
introduced.

The document preserves the frozen DECLARED → CONFIGURED → BUILDABLE → READY →
ACTIVE → EXPOSED → VERIFIED → CERTIFIED lifecycle as distinct booleans plus the
highest reached stage. Behavioral verification, security verification, and
certification are never inferred from code presence, configuration, exposure,
or this implementation gate.

## Runtime truth and negotiation

Each capability reports redacted dependencies, profile readiness, generation
presence and activation, transport declarations and runtime callability,
representations, modalities, languages, retrieval modes, continuation support,
client-visible bounds, unavailable reasons, recommended tools, and deterministic
next actions. Provider/model filesystem locations, cursor secrets, API keys,
credentials, environment variables, and storage paths are excluded.

Configured-but-provider-unavailable, generation-missing, ready-but-inactive,
exposed-but-unverified, and verified-but-uncertified fixtures are covered. OCR,
Vision, visual-vector, multilingual, structured, and multimodal claims remain
generation/provider gated. Supported representations/modalities/languages are
empty while the relevant runtime capability is inactive.

## Blind-client guidance

The common task guidance identifies ranked and exhaustive `search_evidence`,
exact `get_document`, structured `query_structured`, original `get_asset`,
derived `get_image_analysis`, multilingual/multimodal search, persisted
`run_final_qa_v2`, and `get_capabilities`. Availability is computed from runtime
exposure rather than the existence of a tool definition.

## Transports and compatibility

MCP now advertises 14 tools, adding the previously reserved
`get_capabilities`. Its TextContent JSON fallback and structuredContent are the
same capability document. HTTP and MCP parity is asserted against the exact
serialized document and snapshot identity. The partial delivery-only
`/v2/capabilities` adapter was replaced by the WP-13 runtime document; delivery
operations themselves are unchanged.

V1 retrieval, V1 Final-QA, citations, canonical identities, Chunk.text, and all
WP-06 through WP-12 application semantics are unchanged. Processing jobs and
other unavailable adapters are reported non-callable rather than falsely
advertised active.

## Validation

- Focused WP-13 capability suite: **5 passed**.
- Affected runtime/HTTP/MCP/retrieval/structured/Final-QA regression matrix:
  **102 passed**.
- Strict Pydantic/MCP output-schema validation: **passed**.
- Capability matrix schema and MCP contract JSON validation: **passed**.
- Ruff check and format check: **passed**.
- Strict mypy for affected production modules: **passed**.
- `git diff --check`: **passed**.

The only test warning was the existing local pytest cache/temp-directory
permission warning; no assertion failed.

No database migration, corpus mutation, ingestion, projection rebuild, model
download/inference, or benchmark was performed. WP-14 security certification,
WP-16 external-agent behavioral certification, WP-17 final Phase 8.5
certification, and Phase 11 remain pending.

