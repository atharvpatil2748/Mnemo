# MCP stdio validation diagnostic and retention fix

Status: **MCP_VALIDATION_DIAGNOSTIC_FIX_PASS**  
Full reindex readiness: **PRODUCTION_PIPELINE_REINDEX_READY**  
Expensive ingestion executed during this fix: **No**

## Original failure

Run `run-20260907T145440Z` completed Phase 8.6 ingestion, multimodal processing,
5,843 BGE-M3 projections, atomic publication, and HTTP validation. The subsequent
real MCP stdio `search_evidence` call returned an MCP error. The old validator
discarded its content, emitted only `MCP_STDIO_SEARCH_FAILED`, then deleted the
successfully built notebook and registry.

The original deleted notebook cannot be recovered from the remaining run artifacts.
Its checkpoint and event log remain unchanged as historical evidence.

## Root cause

A real MCP stdio reproduction against an existing indexed fixture preserved the
underlying server message:

```text
advanced retrieval is not configured
```

The isolated HTTP runtime used `create_app`, which constructed `KnowledgeEngine`
with the server retrieval cursor codec. The isolated stdio runtime constructed
`KnowledgeEngine(core)` without that codec. Core therefore did not compose advanced
retrieval, and `EvidenceRetrievalApplicationService` failed at the genuine MCP tool
boundary. The SSE runtime had the same latent construction mismatch.

The fix supplies `build_retrieval_cursor_codec(server_config)` when the isolated
stdio and SSE runtimes construct their engines. Authentication, authorization,
candidate construction, reranking, and evidence semantics were not bypassed or
changed.

## Diagnostic evidence

An MCP `isError=true` result now retains the high-level classification and records:

- MCP content, structured content, metadata, error code/message when present;
- tool name and redacted arguments;
- exception type, message, and traceback for client/runtime exceptions;
- server stderr artifact path;
- authenticated principal type/subject;
- notebook alias, notebook ID, store identity, database digest, query, and requested k;
- a non-secret runtime-configuration digest and timestamp.

Known secrets and values under token, secret, password, credential, authorization,
API-key, and HMAC keys are redacted recursively. The structured failure is written
to the run event log, a dedicated MCP failure JSON artifact, and the run checkpoint.

## Notebook retention and registry behavior

The build and serving states are now separate:

1. An indexed and store-validated notebook is atomically published as `PUBLISHED`.
2. Real HTTP, MCP stdio, and MCP SSE validation runs against the server-owned,
   allowlisted validation candidate.
3. On success, its manifest becomes `READY` and it enters the serving registry.
4. On transport failure, it becomes `TRANSPORT_VALIDATION_FAILED`, remains on disk,
   and is excluded from the serving registry.

The normal registry resolver still accepts only digest-bound `READY` manifests.
The validation resolver accepts only allowlisted managed candidates and validates
manifest identity plus the physical database digest. Arbitrary client paths remain
forbidden. A registry can therefore neither serve a quarantined notebook nor point
to a deleted database.

## Transport-only retry

For a retained Phase 8.6 notebook, run:

```powershell
& .\scratch\.venv-gpu-preflight\Scripts\python.exe -m mnemo_server.tools.reindex_evaluation_notebooks --phase86 --validate-only --verbose
```

This path does not ingest sources, run multimodal jobs, or create embeddings. It
checks the retained database digest, executes real HTTP at requested k 1/5/10,
executes real MCP stdio and SSE at k 5, verifies semantic identity parity, and only
then promotes the manifest to `READY` and registers it.

## Cheap real validation

Run `run-20260907T183626Z` used an existing four-document, 2,837-chunk validation
store. It performed no ingestion. Results:

- HTTP requested k 1, 5, and 10: PASS;
- real MCP stdio: PASS;
- real MCP SSE: PASS;
- HTTP/MCP document, version, and chunk identity parity: PASS;
- fixture database SHA before/after: identical.

After validation, the disposable copies were removed through the orchestrator's
managed-path safety check. Their original fixture sources remain intact. The serving
registry is empty and exposes no diagnostic notebook.

## Tests and static validation

- Focused pytest: 32 passed (one pre-existing Windows pytest cache permission warning).
- Ruff: PASS.
- Strict mypy for the three changed runtime modules: PASS.
- Compileall for the changed runtime modules: PASS.
- JSON validation: PASS.

Regression coverage verifies structured MCP errors, secret redaction, quarantine
retention, serving-registry exclusion, validation resolution, retry failure
checkpointing, and retry promotion to READY.

## Production safety

The certified production database remained byte-identical:

```text
before 3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c
after  3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c
```

No production corpus, Ollama configuration/model, BGE model/revision, production
reranker state, or certification state was changed.

## Next full run

The next full Phase 8.5 + Phase 8.6 run is technically ready, but was deliberately
not executed by this task. The user/operator runs it manually:

```powershell
& .\scratch\.venv-gpu-preflight\Scripts\python.exe -m mnemo_server.tools.reindex_evaluation_notebooks --full --verbose
```

If a post-publication transport check fails, the expensive notebook is now retained
in a non-serving state with diagnostics and can be retried using `--validate-only`.
