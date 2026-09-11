# 0082 — Phase 8.5 WP-13 Capability Discovery

Activated deterministic, machine-readable capability negotiation over the
single `Phase85RuntimeV1` state.

- Expanded `GET /v2/capabilities` from delivery-only metadata to the complete
  redacted runtime capability document.
- Activated MCP `get_capabilities` and reused the same document for structured
  content, JSON fallback, and the capability resource.
- Added lifecycle, dependency, provider/profile, generation, transport,
  representation, modality, language, bounds, unavailable-reason, next-action,
  and blind-client routing fields.
- Added focused runtime-truth, HTTP/MCP parity, redaction, schema, advertisement,
  and blind-client guidance tests.

No capability is marked verified or certified by WP-13. WP-14, WP-16, WP-17,
and Phase 11 remain pending.

