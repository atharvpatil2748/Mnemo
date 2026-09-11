# Phase 8.5 WP-03 Gate Evidence

**Date:** 2026-08-26  
**Scope:** WP-03 MCP capability surface and external-client contracts only  
**Verdict:** WP-03 COMPLETE

## Implementation

- Preserved the names, ordering, and required inputs of all ten callable MCP
  tools.
- Replaced ambiguous descriptions with machine-facing purpose, positive-use,
  negative-use, completeness, continuation, provenance, and chaining guidance.
- Made the ranked-discovery boundary explicit: `search_all_notebooks` is bounded
  top-k canonical-text discovery and is never exhaustive or exact traversal.
  Even an empty ranked page remains `bounded`; it is not promoted to a
  corpus-exhaustive `no_match` claim.
- Made exact traversal explicit: `get_document` describes opaque cursor reuse,
  the `truncated`/`next_cursor` condition, and the rule not to answer complete or
  end-of-document requests before terminal traversal.
- Distinguished asset inventory/original delivery (`get_asset`) from existing
  derived OCR/Vision delivery (`get_image_analysis`) and from semantic image
  discovery, which remains WP-09.
- Added MCP `outputSchema` definitions and authoritative `structuredContent` for
  all ten retained tools. Existing JSON text and native image/resource content
  remain as compatibility fallbacks.
- Added a structured metadata companion for native binary/image content without
  copying binary bytes into the structured result.
- Added explicit completeness, coverage, limits, omissions, and recommended
  next-action objects to retained JSON results. Recommendations name only valid
  follow-up tools and never widen authorization scope.
- Froze schemas for `search_evidence`, `query_structured`, `run_final_qa_v2`, and
  `get_capabilities`, but deliberately did not advertise or dispatch them. Their
  application services remain hard dependencies of WP-07, WP-08, WP-12, and
  WP-13 respectively. This prevents false operational capability claims.

## Compatibility and security

- The existing ten tools remain the complete advertised surface in WP-03.
- The six frozen V1 tools retain names and required input schemas. Their domain
  behavior, ranking, citations, and Final-QA semantics are unchanged; output
  enrichment is additive.
- `notebook_id` omission for document delivery still resolves only when
  unambiguous, and ambiguity remains fail-closed. WP-03 did not bypass resource
  authorization or treat an identifier as authority.
- Cursor values remain opaque and must be passed unchanged. WP-04 still owns
  common codec/TTL/key-rotation hardening.
- Binary structured companions contain opaque identity/MIME metadata, never
  image bytes, filesystem paths, credentials, or content.
- No storage migration, corpus mutation, provider call, model activation, HTTP
  route, or Phase 11 planner was introduced.

## Blind-agent contract scenarios

The deterministic contract harness validates what a client can infer solely
from `tools/list` metadata:

| Intent | Discoverable contract |
|---|---|
| Find a document | `search_all_notebooks` |
| Exact/final/complete content | search IDs → `get_document` → repeat unchanged cursor |
| One known chunk | `get_document_chunk` |
| Known document images | `get_asset` inventory |
| Original known image | `get_asset` selected occurrence |
| Existing OCR/Vision meaning | `get_asset` occurrence → `get_image_analysis` |
| All/every evidence | retained top-k tools explicitly deny completeness; `search_evidence` remains gated to WP-07 |
| Numeric filtering/aggregation | retained tools explicitly deny this; `query_structured` remains gated to WP-08 |

This is contract-level blind-agent validation, not live ChatGPT/Antigravity
behavioral certification. Repeated external-client evaluation remains WP-16.

## Focused validation

```text
.venv/Scripts/python.exe -m pytest --no-cov \
  mnemo-server/tests/test_mcp_wp03_contracts.py \
  mnemo-server/tests/test_mcp_tools.py \
  mnemo-server/tests/test_mcp_delivery.py \
  mnemo-server/tests/test_mcp_conformance.py -q

34 passed

.venv/Scripts/python.exe -m ruff check \
  mnemo-server/mnemo_server/mcp/contracts.py \
  mnemo-server/mnemo_server/mcp/tools.py \
  mnemo-server/mnemo_server/mcp/server.py \
  mnemo-server/tests/test_mcp_wp03_contracts.py \
  mnemo-server/tests/test_mcp_tools.py

All checks passed

.venv/Scripts/python.exe -m mypy --strict \
  mnemo-server/mnemo_server/mcp/contracts.py \
  mnemo-server/mnemo_server/mcp/tools.py \
  mnemo-server/mnemo_server/mcp/server.py

Success: no issues found in 3 source files
```

The first focused pytest invocation used the repository-wide coverage plugin
and therefore returned a coverage-threshold failure despite all 25 selected
tests passing. It was rerun with `--no-cov`, as intended for focused WP tests;
the final expanded set above passed all 34 tests. The persistent pytest cache
warning is a local ACL issue and does not affect test execution.

## Deliberate deferrals and discovered boundaries

- WP-04: unified cursor envelope, expiry, key rotation, and cursor security.
- WP-05: explicit page/range/from-end selectors.
- WP-06: deterministic derivation selection and enriched asset inventory.
- WP-07/WP-08/WP-12: callable evidence, structured-query, and Final-QA V2
  application services and handlers.
- WP-09/WP-10/WP-11: semantic multimodal, multilingual, and multi-document
  retrieval behavior.
- WP-13: scope-aware runtime capability registry and callable
  `get_capabilities`; the current static resource is not promoted as equivalent.
- WP-14: migrate the historical scope-resolution mechanism to
  `DocumentScopeResolverV1` and close the complete security matrix.
- WP-16: live stdio/SSE and two-client blind-agent behavioral certification.

The retained `get_source_insights` and `get_timeline` implementations are
bounded and do not currently implement continuation cursors; the machine
contract was corrected not to advertise nonexistent cursor inputs. This is
reported as a bounded legacy behavior, not false completeness.
