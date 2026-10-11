# Stage 6 external-audit remediation — 2026-09-27

## Scope and baseline

This is a forward-only local remediation of external findings E1–E4, not an
independent external acceptance verdict. `main` and `origin/main` were
`5d2612fef6d26cc1e1b0547bb5bd3da6abf21187`; the 8.8.10/8.8.11 and
forensic working-tree changes were preserved without staging. The serving
tunnel before this pass was PID 75376, with `cmd.exe` 74072, editable-venv
Python 88032 and interpreter child 52796, started 2026-09-27 13:24:59 UTC.
The signed launcher and existing direct stdio route were used for diagnostics.
The actual public endpoint and credentials were not changed or printed.

The authoritative contracts are architecture §§21.3–21.10, the canonical
engineering roadmap, ADR-0076/0077/0078, the local Stage 6 forensic closure
and prior [preparation record](mnemo-stage-6-external-verification-preparation.md).
The external verifier's first report is client evidence, not proof of its
suggested root causes.

## Findings and applied dispositions

| Finding | Independent reproduction and root cause | Disposition |
|---|---|---|
| E1 exhaustive continuation | Certified stdio with the exact authorized notebook/document, query, representations and budgets returned a truncated first page (one item, opaque cursor length 987, cursor SHA-256 `a4facb6717e6744897a164f127140b44899476c1bd3a7e08bf4d32818b7b20a0`), then `ContractValidationError` on unchanged-cursor page 2. A fresh 2,000-character traversal returned one item on page 1 and one on terminal page 2 (cursor length 990 on page 1). The later evidence item cannot fit the caller's 80-character content ceiling: `_apply_output_bounds` rejects an item when no candidate fits. This is a truthful per-item budget rejection, not evidence of broken cursor authentication. | No cursor-security code change. Added old/new public MCP budget-shape traversal and a focused regression for late-item budget rejection, signed budget conflict and successful restart with a larger budget. The second external client must restart, not reuse the old cursor after changing limits. Raw opaque tokens were not put in this report. |
| E2 OCR ambiguity | Phase85 `ocr` is the generation profile (`profile_not_configured`); `ocr_text` is an independently configured read of already persisted derived text. An accessible source with zero matches truthfully reports `searched`, examined 0, completeness `empty`. | No OCR activation or product change. Added a focused coexistence regression. A real external client must test the persisted representation independently of the generation lifecycle. |
| E3 document/exact/asset | Architecture §21.8 explicitly allows broader `document_delivery` and `exact_retrieval` families to remain `service_not_registered` while exact persisted chunk reads may work. Asset delivery is similarly not registered as a complete production family; the certified corpus is not made multimodal by 14-tool registration. | No fabricated registration, persisted blocks, assets or production capability. Keep per-operation typed unavailability and report the actual lifecycle. |
| E3 FinalQA V2 | `KnowledgeEngine.initialize()` composed `final_qa_v2` locally, but `_compose_phase85_runtime()` inspected the old `self._final_qa_v2` field before assignment. The new failing-first unit regression showed `service_not_registered` despite a composed service. | Pass the newly composed service into same-startup capability registration. Post-fix regression passes. Dependency gating still decides whether the live capability can become ready/exposed; no model/store/activation was changed. |
| E3 structured | Notebook-scoped readiness can be true while an exact authorized version has no projection. | Existing typed `capability_unavailable` is correct for that version; no production projection was created. |
| E4 production identity | External response matched certified DB SHA-256 `3157ff…`, governed identity `0c6c73…`, and runtime binding `56b64e…`. The 44-source notebook `df9c20cf-85fe-529c-902e-2e9e68193fbe` has a historical “Evaluation Corpus” display name but is the authorized notebook in the certified production store. The separate evaluation DB hashes differ. | No new public build identifier or certified-field modification. Source-content identity remains an operator-side attestation, not an MCP assertion. |

The F-1/F-2 partition principal and metadata corrections, 14-tool route map,
typed errors, V1/V2 isolation, evaluation-store pre-open guard and structured
readiness boundaries were not changed by this pass.

### Certified service-availability matrix

| Family | Authoritative expectation | Post-restart observation | Disposition |
|---|---|---|---|
| Document delivery | §21.8 permits a registered public tool with truthful unavailability when the certified corpus lacks required persisted representation. | `declared`, `service_not_registered` for the broad family. | No blocks/original bytes fabricated. |
| Exact retrieval | Exact authorized operations depend on actual persisted representation; tool registration does not certify the full family. | Broad family remains unavailable; exact chunk behavior is separately scoped. | No blanket readiness claim. |
| Asset delivery | Requires authorized persisted asset and service composition. | `declared`, `service_not_registered`. | No synthetic production asset or registration. |
| FinalQA V2 | Certified composition and all dependencies required; registration alone is insufficient. | Corrected from erroneous `declared/service_not_registered` to `buildable`; still not exposed/callable. | Registration timing repaired, dependency gate retained. |
| Structured retrieval | Scoped projection/generation readiness is narrower than notebook-level availability. | Notebook scope can be available while the requested exact version returns `capability_unavailable`. | No production projection created. |

## Verification and deployment checkpoint

The added regression failed first for the FinalQA capability timing defect,
then passed after the one-argument composition correction. The synthetic
older/newer public MCP exhaustive traversal passed in four variants, including
the external budget shape. The deliberate low-budget late-item test passed;
existing cursor tamper, expiry, snapshot, principal/scope and budget-binding
regressions remained in the full suite. The external verifier's exact cursor
bytes were not supplied, so no claim is made about their serialization.

`MNEMO_CI=1` full repository pytest on the corrected tree: **2,727 passed,
18 skipped, 9 warnings, 90.31% repository-wide coverage**. The nine warnings
include a local pytest-cache permission warning; the established 18 CI-policy
skips remain. The historical unrestricted protected-manifest assertion was
not repaired or represented as green.
The focused engine/retrieval/schema-matrix rerun passed **102 tests**, with
one local pytest-cache permission warning. Its first focused-only invocation
also passed all 102 tests but exited on the repository-wide 90% coverage gate
(37.92% when only three files were selected); the rerun disabled only the
inherited focused-run coverage options. The complete suite above retained
and passed the enforced 90% gate.

Ruff lint/format, strict mypy (291 source files), compileall, `uv lock --check`
(171 packages), all three Python source/wheel builds, frontend format/lint/
typecheck/test/build and three Compose configuration checks passed. Three
Docker image builds and changed-document link validation are recorded at the
final checkpoint below; no image was deployed. `git diff --check` passed.

## Protected-state checkpoint

The read-only preflight matched all accepted identities:

| Protected database | SHA-256 | Bytes | UTC mtime | Sidecars |
|---|---|---:|---|---|
| Production | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` | 189804544 | 2026-09-01T11:09:20.1047581Z | none |
| WP16 | `18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d` | 37195776 | 2026-08-29T13:37:31.2308106Z | none |
| Evaluation 8.5 | `bc048cc15173acbd818b98786a3380a01f2263843a435708f6814c6de21a1d84` | 45592576 | 2026-09-08T06:41:25.6366051Z | existing 0-byte WAL, 32768-byte SHM, accepted hashes |
| Evaluation 8.6 | `9a3521f8cefc74e2673592dbd207a7f5673dcfc05cebfdc18899d93be93307a2` | 52600832 | 2026-09-08T08:14:51.7220651Z | same |

Production manifest `e579727c…`, signed launcher `007ee235…`, activation
`c17a7f55…`, certificate `1a69e957…`, final evidence `02551609…` and
convergence `b5ccccb9…` matched accepted full hashes. The credential
registry contained exactly one ACTIVE generation,
`fc85192e-f672-4cc0-9539-b4b063bb8f41`; no secret value was printed.

## Final live and report checkpoint

The existing `Mnemo Tunnel` scheduled task was restarted forward-only at
2026-09-27 15:43:06 UTC. The former tunnel PID 75376 was stopped; its orphaned
old Python/cmd descendants (52796, 88032, 74072) were then identified by
ancestry and stopped. The new tree is tunnel PID 65196, cmd PID 69648, venv
Python PID 86348 and interpreter child PID 55896 (child start 15:43:08 UTC).
The existing listener remained on port 8080. The existing tunnel client's
`health --port 8080` returned `/healthz` and `/readyz` HTTP 200; its main
channel was enabled, `external`/`stdio`, with `probe_status=ok`. No endpoint,
credential or signed launcher was changed. The source resolves from the
workspace via the authorized editable venv; the child started after the
corrected `mnemo-core/mnemo/engine.py` mtime. The eight-file modified product
Python content manifest digest is
`6ecb1158ddcef2e0d2380676840bfd2df42e1270ab0f4b86fff002441b70c55d`.
This is operator-side file/process attestation, **not** an MCP-exposed source
revision or independent in-memory checksum.

Post-restart certified local stdio listed exactly 14 tools and retained
database binding `56b64e879eb64a251a45ab9beabaa5d9dfd8afee760bd5b8f18383a6df510a1d`.
FinalQA V2 now reports `buildable`, not the erroneous
`declared/service_not_registered`; it is still not advertised as exposed or
callable because its required dependencies remain gated. A fresh exhaustive
2,000-character local-stdio traversal returned a truncated first page
(request ID `ff16f374-616a-4d5b-8797-3fbc9180120d`, item content length
37) and a complete second page (request ID
`d9d01509-ac99-407d-9371-ac752ca62667`, item content length 1148).
The tunnel control-plane health probe succeeded, but this task's tools did
not expose an authenticated external Mnemo MCP client; **no post-restart
external tool call is claimed**. That is the purpose of the second independent
ChatGPT verification.

All three local Docker image builds succeeded; none was deployed. Changed
document relative-link validation checked four documents and 39 links with
zero broken links. `git diff --check` passed. The post-restart read-only
protected-state check reproduced every database hash, byte count, UTC mtime
and sidecar state in the table above; the six signed/protected artifact
hashes and sole ACTIVE generation also remained identical. No database or
signed-artifact write was made.

The worktree remains intentionally unstaged and uncommitted. All newly added
tests and reports remain local; no GitHub publication, production corpus
change, serving-role promotion or independent external acceptance occurred.
The remaining acceptance gate is the second authenticated external MCP run,
including the 80-character budget outcome and the fresh successful
2,000-character continuation. Full four-transport certification and direct
public proof of the loaded source digest remain separate evidence limits.

The [second independent-client prompt](mnemo-stage-6-stage-7-external-chatgpt-verification-prompt.md)
keeps Product Stage 7 distinct and requires fresh connected-tool evidence.
No commit, push, PR, credential rotation, protected-store write, serving-role
promotion or external acceptance verdict occurred in this pass.
