# Phase 8.5 WP-12 Gate Evidence

Status: **COMPLETE**

## Verified existing implementation

`FinalQAV2Orchestrator` already implements the ADR-0054/ADR-0056 lifecycle:
request fingerprinting, execution claiming, context budget enforcement,
provider generation, one corrective citation retry, citation-compliance
rejection, immutable validated/published snapshots, publication conflict
handling, authorization at evidence/context boundaries, and replay without a
provider call.

## Implemented in this continuation

`KnowledgeEngine` now has an additive, explicit `final_qa_v2` composition seam
and property. A caller may inject a governed implementation of
`FinalQAInterfaceV2`; it is exposed only while the engine is READY. When
provided, Phase85Runtime registers `final_qa_v2` as ready/active/exposed. No
provider fallback or hidden model selection was introduced.

Added `LLMFinalQAV2Provider`, a governed adapter from the configured
`LLMInterfaceV1` to `MultimodalProviderV1`. It reports stable provider/model
identity and truthful vision support and performs no direct storage access.
Added `StorageEvidenceAuthorizerV2`, which verifies notebook membership and
exact document/version provenance through the canonical storage facade and
fails closed when derived-generation activation cannot be established.
When the explicit V2 components and execution-store contract are available,
`KnowledgeEngine` composes these adapters into the existing
`FinalQAV2Orchestrator`; no second orchestrator or provider registry exists.

Added the strict `FinalQAV2RequestBody` / `FinalQAV2Response` DTOs and a shared
`FinalQAV2ApplicationService`. The service validates the notebook-bound typed
evidence request, negotiates the configured provider profile, enforces the
complete-evidence publication policy, builds the canonical multimodal result,
delegates execution/replay to the existing orchestrator, and serializes only
safe provenance fields.

Activated the additive HTTP route
`POST /v2/notebooks/{notebook_id}/final-qa` and the reserved MCP
`run_final_qa_v2` tool. Both call the same application service. MCP now lists
13 tools (the prior 12 plus `run_final_qa_v2`).

Added focused transport-contract coverage for canonical HTTP/MCP request
equivalence and MCP advertisement. Updated affected MCP conformance tests for
the callable 13-tool surface.

## Closure evidence

Transport tests exercise the real HTTP/MCP DTO, shared application service,
orchestrator, provider, and execution-store path. They prove:

- HTTP first execution invokes the provider once; identical replay retains a
  provider count of one and reuses the execution identity.
- MCP first execution invokes the provider once; identical replay retains a
  provider count of one and reuses the immutable answer/execution.
- changed request fingerprints conflict; changed server-owned principals,
  forged client principal fields, unauthorized evidence, and corrupt snapshots
  fail closed without generation.
- one invalid citation triggers exactly one corrective retry; replay after a
  compliant retry adds zero calls. Two invalid attempts reject publication and
  subsequent replay adds zero calls.
- image occurrence and OCR-derived evidence retain asset/occurrence/
  derivation/document/version provenance. Hindi, Marathi, and mixed-language
  evidence reaches the provider context unchanged.
- partial and truncated evidence are rejected by `require_complete` and remain
  explicitly partial/truncated under `allow_partial`.
- unsupported and explicitly unavailable modalities, plus ungoverned
  provider-profile requests, fail before provider invocation.

HTTP derives actor identity from server authentication claims. MCP accepts no
client actor field and uses the server-owned MCP principal seam. Centralized
authorization certification remains WP-14; this does not weaken WP-12 replay
or evidence authorization.

## Validation performed

- `.venv\\Scripts\\python.exe -m pytest mnemo-core/tests/unit/test_engine.py mnemo-core/tests/unit/test_multimodal.py --no-cov -q`: **40 passed**.
- `.venv\\Scripts\\python.exe -m pytest mnemo-server/tests/test_mcp_server.py --no-cov -q`: **7 passed**.
- `.venv\\Scripts\\python.exe -m pytest mnemo-server/tests/test_server_app.py --no-cov -q`: **9 passed**.
- `.venv\\Scripts\\python.exe -m pytest mnemo-server/tests/test_final_qa_v2.py mnemo-server/tests/test_mcp_server.py mnemo-server/tests/test_mcp_conformance.py mnemo-server/tests/test_mcp_tools.py mnemo-server/tests/test_server_app.py --no-cov -q`: **33 passed**.
- `.venv\\Scripts\\python.exe -m pytest mnemo-server/tests/test_final_qa_v2_transport.py --no-cov -q`: **7 passed**.
- Focused WP-12/V1 affected regression matrix: **104 passed**.
- Strict mypy for the seven affected production modules (`engine.py`, the
  Final-QA provider/authorizer/orchestrator, DTO, application service, and HTTP
  router): **passed**.
- Ruff check and format check for the eleven affected production/test modules:
  **passed**.
- Capability and MCP governance contract JSON parsing: **passed**.
- `git diff --check`: **passed**.
- The default coverage-enforced invocation is not a useful gate for this
  focused subset because repository-wide coverage is 23% (configured fail-under
  90%); no test assertion failed.

No database migration, corpus mutation, external model invocation, ingestion,
or benchmark was performed. WP-13+ and Phase 11 remain untouched. This gate is
implementation verification, not WP-16 behavioral certification or WP-17
Phase 8.5 certification.
