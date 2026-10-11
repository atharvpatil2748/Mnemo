# Module 8.8.10 — local implementation and verification

Date: 2026-09-27. Scope: Phase 8.8 Stage 6, Phase 8.6 exposure boundary.
This is implementation evidence, **not** independent forensic acceptance,
production deployment, live-tunnel certification, Phase 8.6 promotion or
Stage 6 closure.

## Authority and baseline

The checked-out `main` and `origin/main` both started at
`5d2612fef6d26cc1e1b0547bb5bd3da6abf21187`, with a clean working tree.
The source-of-truth hierarchy is indexed in `docs/README.md`. Requirements
come from architecture §21.10 and the roadmap's Module 8.8.10 and canonical
execution order. ADR-0076 governs certified identity; ADR-0077 governs the
disjoint mutable workspace; ADR-0078 governs server-owned credentials and
generation. The earlier five-module Stage 6 batch is independently locally
accepted, but not thereby deployed. The Phase 8.5 production composition is
certified; the Phase 8.6 registry is validated for evaluation only.

Before implementation the certified production DB and WP16 DB matched their
accepted SHA-256 hashes, byte sizes and UTC mtimes and had no SQLite sidecars.
The two READY evaluation notebook DBs also matched their recorded hashes:
Phase 8.5 `bc048cc15173acbd818b98786a3380a01f2263843a435708f6814c6de21a1d84`
(45,592,576 bytes) and Phase 8.6
`9a3521f8cefc74e2673592dbd207a7f5673dcfc05cebfdc18899d93be93307a2`
(52,600,832 bytes). Unlike production/WP16, **both evaluation stores had
pre-existing zero-byte WAL and 32,768-byte SHM sidecars**. They were not
deleted or treated as evidence of this module's writes.

## Selection-path inventory and threat model

| Path | Serving authority | Isolation observation |
|---|---|---|
| Certified HTTP, MCP stdio, SSE and tunnel startup | Server-owned manifest, credential generation and exact store/model binding | `resolve_certified_production_binding` rejects mismatched identity before startup; public clients cannot select it. |
| Production storage preflight | Configured certified DB/blob roots plus ADR-0077 inventory | Previously omitted the `scratch/evaluation_notebooks` root and could accept it as mutable workspace or as a production-mode selected store. Fixed below. |
| Public 14-tool dispatcher and HTTP routes | Bound engine and authenticated central authorization | No public registry-lookup or serving-role parameter. Retained V1 and V2 routes remain distinct. |
| Internal Phase 8.6 validation transport | Server-owned READY alias and digest-bound registry | Separate nonproduction child may select `phase8_5` or `phase8_6`; arbitrary client paths and other aliases are rejected. Candidate validation is not serving promotion. |
| Governed mutable workspace | Explicit disjoint server-owned path | Overlap with certified, operational and evaluation roots must fall back to read-only. |

The lower-level `create_mcp_server` factory intentionally accepts an injected
engine for synthetic tests and separately governed internal evaluation. It is
not, by itself, a certified production launcher. The certified transport
startup paths enforce the manifest binding and production storage preflight
before public exposure.

Threats checked were a direct DB/blob selection into the evaluation namespace,
workspace overlap, symbolic-link alias, client-supplied path or registry alias,
unknown/evaluation-only notebook and cross-notebook subordinate identity, and
accidental evaluation federation in global search or capability output. The
existing certified startup binding separately rejects wrong model, generation,
store and historical fallback; this module does not replace it.

## 8.8.10a — enforced evaluation-only selection

`production_storage_composition.py` now includes the entire server-owned
evaluation notebook namespace in its protected inventory. Before production
storage is opened, it rejects a configured SQLite database or blob root inside
that namespace with a path-free `EVALUATION_ONLY_STORE_NOT_SERVABLE` error.
The check uses resolved paths, so a disposable symlink alias cannot bypass it.
For real `MnemoConfig` values the storage paths are `Path` objects; existing
mock-only startup tests remain compatible. The evaluation transport's existing
digest-checked alias resolver remains separate and unchanged. No public
evaluation-mode toggle, registry federation or production allowlist was added.

The failing-before regression showed three workspace-overlap cases and two
direct selected-store cases accepted before correction. All five became
ordinary passing tests after the change. The HTTP production lifespan test
proves rejection before any evaluation directory or database is opened.

## 8.8.10b — future promotion gate, not activation

The [governance gate](../../governance/active/phase_8_6_serving_promotion_gate.md)
specifies the explicit serving-role decision, exact notebook allowlist,
membership proof, immutable schema read compatibility, store/model identity,
lifecycle/capability state, fresh four-transport parity, provenance,
protected-state check and separate activation authorization. An incomplete
proposal grants no serving role. Neither this specification nor a READY
registry state activates Phase 8.6. No production allowlist, credential,
manifest, generation or corpus was modified; no data is copied into the
certified database.

## 8.8.10c — disposable adversarial isolation evidence

`test_phase86_exposure_boundary.py` uses an older and a newer disposable
production schema plus a separate evaluation-marker SQLite file. Direct MCP
returns production notebook/search evidence; exact delivery through HTTP
returns the production chunk; evaluation-only notebook requests fail without
the marker or unauthorized identity appearing in responses. The test installs
a registry-lookup tripwire: if the production public path attempts registry
resolution, it fails. Capability output does not list the evaluation store.
Client-supplied serving role, registry alias and DB path produce typed
`invalid_input`, not a role switch. The existing same-fixture direct/real
stdio/loopback-SSE matrix now repeats the forbidden serving-role request
through those transports. Existing route-registry, reader, authorization,
typed-error and evaluation-registry suites provide additional regressions;
none is presented as live-tunnel certification.
For a mixed document filter, ranked evidence returns an authorized production
item only. The response may echo the caller's submitted filter UUID; that is
not server-side discovery or evidence from the evaluation store.

| Boundary | Older schema | Newer schema | Result |
|---|---|---|---|
| Production preflight evaluation DB/blob or workspace | Path-based; schema independent | Path-based; schema independent | Rejected before I/O |
| Direct MCP inventory/search/capabilities and unauthorized exact scope | Exercised | Exercised | Production-only result or sanitized denial |
| HTTP exact chunk, evaluation-only notebook | Exercised | Exercised | Authorized production result; denied evaluation ID |
| Real local stdio and loopback SSE client role override | Exercised in shared transport matrix | Exercised in shared transport matrix | Typed `invalid_input`; no role selection |
| Internal evaluation READY registry | Existing digest-bound registry tests | Schema-independent selection | Separate evaluation path remains functional |

## Validation and disposition

The focused production composition/exposure tests passed (17 tests). The
larger focused route, registry, transport and forensic selection passed (41
tests before the final two relative-path cases), and the real local
same-fixture transport matrix passed (6 tests).
Ruff lint/format, strict mypy (291 source files), compileall, `uv lock
--check`, three Python package builds, frontend format/lint/typecheck/test/
build, three Docker Compose config checks and `git diff --check` passed.
All three Docker core, server and UI images built locally, including a final
server rebuild after the boundary correction.

One diagnostic non-CI invocation of the complete suite exposed three
mock-path compatibility failures, corrected with an actual-`Path` guard, and
one existing local-database certification assertion that expects manifest
lifecycle booleans to be true even though the protected manifest records
false. The manifest was **not** changed. The repository's `conftest.py`
intentionally skips `local_database` tests in CI; the final CI-safe suite
uses that existing policy. Neither this historical assertion nor local
fixture evidence is presented as a fresh production certification.

An intermediate CI-safe full run passed 2,704 tests, skipped 18, emitted eight
warnings and reached 90.31% repository-wide coverage. The **final run on the
complete source and test state** passed **2,706**, skipped **18**, emitted
**eight warnings**, and reached **90.31% repository-wide coverage**. It used
the repository's existing `MNEMO_CI=1` marker policy, without reducing the
coverage threshold. The final focused selection, registry, route, transport
and forensic subset passed **43**. No xfails or XPASS were introduced.

## Protected state and residual boundaries

The final before/after comparison found no protected identity change:

| Store | SHA-256 | Bytes | UTC mtime | Sidecars |
|---|---|---:|---|---|
| Certified production | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` | 189,804,544 | `2026-09-01T11:09:20.1047581Z` | None |
| WP16 | `18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d` | 37,195,776 | `2026-08-29T13:37:31.2308106Z` | None |
| Evaluation Phase 8.5 | `bc048cc15173acbd818b98786a3380a01f2263843a435708f6814c6de21a1d84` | 45,592,576 | `2026-09-08T06:41:25.6366051Z` | Pre-existing zero-byte WAL and 32,768-byte SHM |
| Evaluation Phase 8.6 | `9a3521f8cefc74e2673592dbd207a7f5673dcfc05cebfdc18899d93be93307a2` | 52,600,832 | `2026-09-08T08:14:51.7220651Z` | Pre-existing zero-byte WAL and 32,768-byte SHM |

Both evaluation SHM files retained SHA-256
`fd4c9fda9cd3f9ae7c962b0ddf37232294d55580e1aa165aa06129b8549389eb`;
both WAL files remained empty. READY manifest identities still matched their
registry records: Phase 8.5
`6b52d36fb5f3c60e7126a0236dfab52061e831a748b1da49b951f3228725f31a`
and Phase 8.6
`8f4aeda7be411065f570fd798f3465b5076f78db06469c9f80d16424d325b1ed`.
The protected manifest, certified launcher, signed activation, certificate,
final evidence and signed startup convergence matched their accepted SHA-256
hashes, respectively:

- Manifest `e579727c8867c92d4ca7fe05256a35d74942077f86b86a6fad9938ff3b4fc566`.
- Launcher `007ee235783cb8f673a2f9c135bc38269ba2a355057c5cd119c0125e471fde22`.
- Activation `c17a7f5531cc75795fb63c6f53682d30eb6ed831127db95038d3d1741cd25525`.
- Certificate `1a69e95796b98abcc1f4f6484692481058bff776b454a14e3a0b35d86f16312a`.
- Final evidence `0255160992fc1ed2fdc5b5c6bfb55bb442b55018655f511274d698569a06230c`.
- Signed convergence `b5ccccb9787773ef10f5a6364bbc80ed98324640ea5438da604ebfaf2b7c2b23`.

Credential-registry metadata
still names exactly one ACTIVE generation,
`fc85192e-f672-4cc0-9539-b4b063bb8f41`; no credential values were read
or copied into this report. No test opens a protected DB writable. All test
databases are disposable.

Module 8.8.11, independent forensic acceptance, Module 8.8.9 live four-
transport certification, GitHub closure for this change, production
deployment and external ChatGPT verification remain separate. A future
Phase 8.6 promotion requires its own authorized decision and fresh evidence.

## Acceptance and handoff

- **MODULE_8_8_10A_LOCALLY_VERIFIED:** production composition rejects evaluation
  DB/blob selection, including relative and symlink aliases; the registry root
  cannot become a mutable workspace. Internal evaluation alias resolution is
  unchanged.
- **MODULE_8_8_10B_LOCALLY_VERIFIED:** the ten-part future gate is reviewable,
  explicitly inactive and linked from architecture and governance. No
  promotion workflow or public serving-role selector was introduced.
- **MODULE_8_8_10C_LOCALLY_VERIFIED:** older/newer disposable schemas, direct
  MCP/HTTP, local stdio/SSE, mixed scope, capability nondisclosure, protected
  state and existing routing/authorization suites pass.

**MODULE_8_8_10_LOCALLY_VERIFIED.** This is local implementation verification
only. Independent adversarial review should challenge path normalization,
cross-store lookup, transport-specific startup and capability scope against
the same disposable stores. Module 8.8.11 still prevents Stage 6 closure;
Module 8.8.9 live four-transport/tunnel certification and any Phase 8.6
promotion require separate authority and evidence.

Final Git state: `main` remains at
`5d2612fef6d26cc1e1b0547bb5bd3da6abf21187`, tracking the same
`origin/main` commit. Eight tracked files are modified and three new files
are untracked (this report, the promotion gate and the exposure test). No
files are staged. No commit, push, deployment, production restart or tunnel
restart occurred.
