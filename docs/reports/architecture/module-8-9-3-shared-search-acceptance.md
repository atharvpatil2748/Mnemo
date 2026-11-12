# Module 8.9.3 — shared search application boundary (2026-11-04)

## Decision and limits

**COMPLETE for the approved internal development/test exit criteria.** The
project-owner review kept application orchestration in `mnemo-server`, retained
all existing HTTP V2 routes and MCP tool names/defaults, and reserved public
`search` registration, multi-notebook fan-out, structured natural-language
planning, deployed transport parity, and production activation for later
roadmap gates. This record is not an external-client or production certificate.

The working tree was already substantially modified before this task (58
tracked modified paths plus existing untracked 8.9.1/8.9.2 artifacts). No
existing work was reset, staged, committed, or pushed. The production selector
was read as `UNINDEXED` before and after the implementation.

## Acceptance matrix

| Criterion | Implementation and authority | Executed evidence | Status |
|---|---|---|---|
| 8.9.3a: internal shared request/response and server-owned authority plan | `services/shared_search.py`: discriminated internal request, server-derived actor/notebook/revision plan, versioned typed ancestry envelope, provider status/coverage and safe-error shape. Existing V2 request budgets and mode defaults remain authoritative; inner V2 services build their retrieval plans under server configuration. `schemas/scope_contract_review.py` remains an unregistered review vocabulary. | `test_module_893_shared_search.py` validates request mismatch, JSON Schema, serialization, canonical and dataset-row identity, safe error fields, searched-zero versus unavailable, owner/reader ACL revalidation and in-flight revocation. Existing `test_module_891_contracts.py` validates the accepted review schema. | PASS for internal DTO; not a new public wire freeze |
| 8.9.3b: one composition seam, no parallel retrieval stack | Existing HTTP `/v2/retrieval/automatic`, `/evidence`, `/structured` and MCP `query_notebook_v2`, `search_evidence`, `query_structured` now call `SharedSearchApplicationService.execute`. It delegates to `AutomaticQueryV2ApplicationService`, `EvidenceRetrievalApplicationService`/`AdvancedRetrievalService`, or `StructuredRetrievalApplicationService`; existing services retain provider/generation admission, plan limits, cursor validation, document ancestry and post-work revalidation. Structured service returns its already-authorized catalog through an internal method so dataset/row references are mapped from authoritative candidate identities without changing its public response. | `test_retrieval_v2.py`, `test_structured_v2.py`, `test_module_892_retrieval_routes.py`, `test_module_892_real_engine.py`, `test_module_893_shared_search.py`, and the Module 8.9.1 public-surface snapshots passed. Call-graph review found no second retriever, signer, provider-readiness policy or transport-specific planner introduced here. | PASS for retained internal V2 operations |
| 8.9.3c: governed answer boundary | `FinalQAV2ApplicationService` obtains evidence through the shared boundary's existing advanced-retrieval composition, then binds a transient `AuthorizedEvidenceSnapshot` to the server principal, notebook, current ACL revision and evidence result. Document/version/source ancestry and revision are rechecked before generation; the existing FinalQA owner-only write check remains independent of reader evidence access. The existing timeout, replay/idempotency, citation and publication-policy orchestration is retained; authorization is rechecked before return. | `test_final_qa_v2_transport.py`, `test_module_892_real_engine.py`, `test_final_qa_and_search_ci_safe.py` and full-suite results below. A first full run exposed a changed unauthenticated error string; the original fail-closed error ordering/text was restored, focused test passed, and the subsequent full run passed. | PASS for the existing FinalQA V2 path; later 8.9.7c still owns full persisted-snapshot correctness |
| No public compatibility change | No route/tool registration or public DTO/default modification. V1 MCP/HTTP defaults remain intentionally distinct. Internal envelope is never serialized as an existing public response. | Module 8.9.1 contract and immutable MCP schema tests: 124 passed with the new shared-service test file. Full suite includes the existing transport and V1/V2 regression tests. | PASS for registered local contracts; deployed parity is later 8.9.8 |

The typed internal reference includes notebook/source/document/version and
chunk, occurrence/derivation or dataset/row identity. The unchanged public
responses retain richer locator/path/content fields. A generation ID is not
fabricated for advanced candidates that do not expose one; per-scope active
generation resolution and full ancestry certification remain 8.9.4a and
8.9.7a. Structured row-to-dataset binding is derived from the authorized
catalog's candidate identity, not from a client claim. The internal safe-error
shape does not replace the existing transport error mappers.

## Verification performed

- First full run: `.venv\Scripts\python.exe -m pytest -q --junitxml=scratch/phase893_20261104_junit.xml -o 'addopts=--strict-config --strict-markers --cov=mnemo --cov=mnemo_server --cov=email_ingestion --cov-config=pyproject.toml --cov-branch --cov-report=term-missing --cov-report=xml:scratch/phase893_20261104_coverage.xml --cov-fail-under=90'` — **exit 1**, 3,301 passed, 1 failed, 6 skipped; the failure was `test_final_qa_v2_authorized_retrieval_branches`, asserting the established unauthenticated error text. Coverage reached 90.00%. This run is failure evidence, not an acceptance pass.
- After restoring the error ordering/text, focused failing-test plus new-boundary tests: **8 passed, exit 0**.
- Completed full rerun with the same configured options and fresh `scratch/phase893_20261104_rerun_junit.xml` and `scratch/phase893_20261104_rerun_coverage.xml`: **exit 0, 3,302 passed, 6 skipped, 0 failed, 9 warnings**. Combined line/branch coverage from XML counts is **90.010184%** (the CLI rounds to 90.01%), meeting the unchanged 90% minimum. The JUnit and coverage XML are separate artifacts.
- Final complete run after the last test-only JSON round-trip assertion: `.venv\Scripts\python.exe -m pytest -q --junitxml=scratch/phase893_20261104_final_junit.xml -o 'addopts=--strict-config --strict-markers --cov=mnemo --cov=mnemo_server --cov=email_ingestion --cov-config=pyproject.toml --cov-branch --cov-report=term-missing --cov-report=xml:scratch/phase893_20261104_final_coverage.xml --cov-fail-under=90'` — **exit 0, 3,302 passed, 6 skipped, 0 failures/errors, 9 warnings**. JUnit has 3,308 cases; combined covered/valid line-and-branch counts in the final coverage XML give **90.012003%**, above 90%. This is the final full-suite acceptance run.
- `pytest -q -o addopts='' mnemo-server/tests/test_module_893_shared_search.py mnemo-server/tests/test_module_891_contracts.py mnemo-server/tests/test_mcp_immutable_schema_matrix.py`: **exit 0, 124 passed**, one local pytest-cache permission warning. This focused run includes the final internal DTO JSON round-trip assertions, added after the full rerun; it does not replace the full coverage gate.
- `.venv\Scripts\python.exe -m ruff check .`: **exit 0**; `.venv\Scripts\python.exe -m ruff format --check .`: **exit 0**, 609 files already formatted. Formatting was run only on the explicit 8.9.3 implementation/test paths, not on the whole working tree.
- `.venv\Scripts\python.exe -m mypy --strict mnemo-core/mnemo mnemo-server/mnemo_server plugins/email-ingestion/email_ingestion`: **exit 0**, 320 source files. This is the established source scope, not a claim that all legacy tests type-check.
- `.venv\Scripts\python.exe -m compileall -q mnemo-core/mnemo mnemo-server/mnemo_server plugins/email-ingestion/email_ingestion`: **exit 0**. `git diff --check`: **exit 0**.

The 9 full-suite warnings include a local pytest-cache permission warning,
Starlette deprecations, parser malformed-input warnings, and a local Qdrant
payload-index warning; no failure was suppressed. No source feature was
disabled and no timeout, coverage threshold, or security assertion was
relaxed. Tests used disposable fixtures; no production migration, index,
credential, or tunnel operation was performed.

## Scope retained for later gates

8.9.4 owns authorized multi-notebook/document fan-out, per-scope generation
selection and fusion/traversal. 8.9.5 owns structured intent and presentation.
8.9.6 owns new public adapter registration and migration. 8.9.7 owns full
provenance and persisted evidence-snapshot certification. 8.9.8 owns deployed
transport parity and actual consumer evidence. The shared boundary is
UI-*ready* as an application interface; no UI build or deployed UI test was
available or claimed.
