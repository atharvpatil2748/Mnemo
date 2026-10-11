# Isolated external ordered-text fixture — 2026-09-28

SERVER-SIDE FIXTURE PROVISIONED AND AUTHENTICATED PUBLIC RECONSTRUCTION PASSED.
Independent ChatGPT certification and its connector configuration remain pending.

## Authority, isolation and baseline

The owner explicitly authorized a disposable isolated certification fixture and
separate endpoint, not production backfill or evaluation federation. Main and
origin/main remain 5d2612fef6d26cc1e1b0547bb5bd3da6abf21187. Initial tree:
58 modified tracked files, 40 untracked, nothing staged. All pre-existing changes
were preserved. The 291-product-file content digest remains
cdf4bc9b3140d5b0b8063766e7b0bdd7f4154df9190b42aa17fec77b63d2313d.
No core/server product implementation was changed during this assignment.

[Fixture server](../../../scripts/serve_ordered_text_fixture.py) uses actual
SQLite persistence, FilesystemBlobStore parsed IR, immutable SQLite reader,
existing delivery service, canonical argument schemas, transport-owned principal
binding and the existing authentication middleware. Only get_capabilities,
list_notebooks and get_document are exposed here. This is not a second certified
production composition and does not claim model or product certification.
Its capability schema is explicitly mnemo.isolated-text-capabilities/1 rather
than impersonating the production capability document. Production keeps all14.

The authenticated API-key actor and the configured trusted stdio owner actor
are the only accepted actors. Clients cannot choose principals, stores or roles.
No mutation tool, evaluation lookup, model fallback or production database is
part of the fixture. Canonically resolved fixture roots must remain inside the
dedicated test directory and outside protected roots. Database identity is
checked at startup. Unknown/cross-resource document/version requests fail safely.

## Actual fixture and independent truth

Endpoint: https://rotary-tobago-michelle-filter.trycloudflare.com/mcp/

| Identity | Actual value |
| --- | --- |
| Notebook | 434043e6-7149-4232-86af-e72e0f8434ef |
| Source | 215543fc-70aa-4ae7-8cda-870e925d1177 |
| Document | cf43cabc-08f8-4ca6-ad4d-f35cbf25bf69 |
| Version | b8183755-55d4-4771-8d84-2ffd0e741cee |
| Database SHA-256 | acb5635fd0b0056205f16d739966613d3df46ac6ae89057ef560645d05eacc35 |
| Typed representation | parsed_blocks/v1 |
| Rendered representation | parsed_text/v1 |
| Items/pages in source | 12 blocks, page references 1–12, ordinals 0–11 |
| Text UTF-8 SHA-256 | 70f933e57255937afc39612ac54a311f7653ab9c1c7d91c20106a4db12a83493 |
| Typed-field SHA-256 | b2da14fd657a73dc60acf1839d96f4a9303783dbed8afd71b1346bd440c51d88 |
| Blocks snapshot | 4e5d9f73a2a38754865a2057587591317590a3dd28d59883a11abcb6e69d735f |
| Text snapshot | 7405a9cd9e6139be0ce596e761e9a59075edbcfb332ceecffcc204d0ed4f8e97 |

The [truth manifest](mnemo-ordered-text-fixture-manifest.json) originates from
the existing explicit mixed-content specification, not delivery output. This
assignment persisted that same supported content under fresh random identities;
the former fixed local-test IDs are not the public fixture IDs. Headings,
paragraphs, two tables, Python code, two LaTeX expressions, image alt text and
Unicode/blank lines are persisted via supported IR types. This is explicit IR
test infrastructure, not a claim that an untested parser ingested a source PDF.
The image block references test alt text, not an available binary image asset.

Text rendering preserves textual values and intentional whitespace, but does
not preserve heading level, table header count, code language, equation display
flag or image bytes. Those typed fields remain available in blocks mode. Tables
use tabs/newlines; equations use LaTeX text; each item's separator_after is
authoritative. Do not trim, normalize Unicode, or add a trailing newline.

## Retention and deployment

Created 2026-09-28T12:31:23.150652Z; lease expires
2026-09-30T12:31:23.150652Z. Every operation and discovery checks the lease;
HTTP and stdio runtimes stop automatically at expiry. Owner removes the isolated
test data and stops its HTTPS companion within seven days. No permanent
availability is promised. The accountless temporary HTTPS address has no uptime
guarantee and may change if that companion restarts; never substitute production.

The fixture binds loopback only and the installed cloudflared companion routes
that isolated port to HTTPS. Authentication remains mandatory on both MCP
message paths. Missing/wrong credentials returned401 at the actual public URL.
No credential value was logged, written to a report or rotated.
Public SSE stalled during initial investigation; streamable HTTP with JSON
responses succeeded. SSE is retained and tested locally, not advertised as a
passing public-HTTPS transport. The [inactive tunnel template](../../../config/testing/ordered-text-tunnel.example.yaml)
and [stdio launcher](../../../scripts/start_isolated_text_fixture.bat) provide
an alternative separate Secure MCP Tunnel setup; no administrative tunnel CRUD
or new management credential was performed.

## Executed evidence

[Verifier](../../../scripts/verify_isolated_text_fixture.py) independently compares
every typed field and exact reconstructed UTF-8 bytes with the truth manifest.
Raw page receipts and request IDs are preserved in ignored test infrastructure.

| Transport | Blocks size1 / size3 | Text size1 / size3 | Security |
| --- | --- | --- | --- |
| Authenticated loopback SSE | 12 / 4 pages, matching typed truth | 12 / 4 pages, exact digest | 28 negative calls rejected; deterministic replay |
| Real isolated stdio | 12 / 4 pages, matching typed truth | 12 / 4 pages, exact digest | 28 negative calls rejected; deterministic replay |
| Authenticated public HTTPS streamable MCP | 12 / 4 pages, matching typed truth | 12 / 4 pages, exact digest | 28 negative calls rejected; unauthenticated/wrong-key401 |
| Owner's ChatGPT connection | Not yet performed | Not yet performed | Connector connection/refresh pending |

Final public traversal UTC window: 2026-09-28T14:45:22.458752Z–14:45:41.291534Z.
Scoped capability request796066c1-3eab-4145-b9ed-d9176ba53ba1.
First block page eb960db1-f015-4d50-b576-244b314ab79f; first text page
248a9536-3187-43bd-9096-e91d3dc57bcd. Public tools/list advertised
blocks|text|original. All traversals retained stable per-mode snapshots, canonical
ancestry, sequential ordinals, total12, truncated intermediate pages and complete
terminal pages without a cursor. Final code was reloaded before this public run.

Negative network tests changed limits, mode, selector, document/version and
tampered cursors. Core delivery tests additionally cover actor binding, expiry,
exact limits before clamping, empty/single/oversized Unicode and snapshot changes.
No secondary real credential was created; adversarial actors are disposable.

## Failed attempts and corrections

Initial provisioning completed its database/IR/manifest writes but stdout failed
under Windows cp1252. ASCII-safe output fixed that, without overwriting the fixture.
Startup subsequently exposed an implicit-encoding read; UTF-8 is now explicit.
First discovery failed because the new endpoint referred to a nonexistent
principal.subject; it now uses the existing authenticated actor identity.
Strict MCP client output validation rejected the initially simplified capability
payload under production's schema. The fixture now declares its own truthful
capability output schema. Streamable HTTP initially used an outdated SDK header
argument; the client now uses a managed authenticated httpx client. None of these
test-endpoint setup failures required a production or protected-data change.

Five permanent fixture regressions cover directory confinement, persisted Unicode,
immutable DB reads/no sidecars, overwrite refusal, authenticated tools/list schema,
missing/wrong credentials, bad DB identity, no-auth refusal and expired startup.
The first test attempts had two configuration failures because disposable signing
configuration omitted/misnamed the required existing secret field; corrected
fixtures supply a strong disposable delivery_cursor_secret, without weakening
the production validator. Final five tests pass.

## System validation and protected state

Focused persisted delivery/security/schema/transport group: 66 passed, one
pytest-cache warning. All14 tools invoked in real certified stdio and authenticated
loopback SSE: each25 calls, 23 successes and two expected safe negative responses;
FinalQA returned citation_resolved, complete stop termination and exact replay.
53 HTTP operations remain in the manifest; the existing real-TCP fixture matrix
passed256 tests/four warnings, including disposable mutation/negative fixtures.
This is neither53 production mutation successes nor public REST certification.

Completed full CI-safe run: 2,795 passed,18 existing local_database skips,
nine warnings,90.31% coverage. A preceding concurrent diagnostic run had one
ordered-stdio failure,2,794 passes,18 skips,ten warnings; isolated four transport
tests passed, followed by the successful sequential full run. Resource contention
is a bounded explanation, not a proved root cause from unavailable diagnostic
details. Final release rerun evidence is recorded below.
No new skip/xfail, lowered threshold or weakened assertion. Historical unrestricted
protected-manifest lifecycle failure remains separately disclosed; no unrestricted
suite pass is claimed.

Ruff lint/format, strict mypy291 files, compileall, uv lock check, all three Python
sdist/wheel builds, frontend format/lint/typecheck/test/build, three Compose configs
and all three Docker image builds passed. Frontend: one test,100% reported coverage.
An initially wrong email package name failed before its correct package build.
Docker artifacts are build evidence, not the deployed fixture runtime.

The [accepted file checkpoint](mnemo-ordered-text-protected-checkpoint.json)
was independently rehashed before work and after deployment/testing: all22 file
records match SHA-256, byte size, exact UTC mtime or required absence. Production
and WP16 remain sidecar-free; both evaluation DBs retain their prior zero-byte WAL
and32,768-byte SHM identities. Manifest, certified launcher, signed activation,
certificate, final evidence and convergence artifact are unchanged. Exactly one
ACTIVE generation remains fc85192e-f672-4cc0-9539-b4b063bb8f41. No secret values
were read into logs. Operational FinalQA test publications are not protected corpus
mutations. Production's original process/configuration was not restarted or changed.

## Reproduction and owner-only step

From the repository with the approved environment, run the isolated verifier with
--url pointing to the public /mcp/ URL, --manifest pointing to the isolated fixture's
persisted manifest and --receipts pointing to a NEW ignored receipt directory.
For loopback use http://127.0.0.1:8057/sse; for real stdio use stdio://fixture.
Supply authentication via existing server-owned configuration, never command-line
secret arguments. Reprovisioning refuses existing directories.

Owner must refresh the production connection and configure the separate fixture
connection. If ChatGPT cannot securely configure a Bearer header, use a separately
admin-created scoped Secure MCP Tunnel and the inactive template. The existing
runtime control-plane key cannot perform admin CRUD. Do not publish it or replace
the production tunnel. See [handoff](mnemo-ordered-text-external-handoff.md).

## Final release checkpoint

Final-source MNEMO_CI=1 release rerun: **2,795 passed,18 skipped,nine warnings,
90.31% coverage**,275.31 seconds. Zero xfails/xpasses. Warnings are the existing
Starlette/httpx and422/413 deprecations, deliberately malformed XLSX relationship
warnings, local Qdrant payload-index warning, MCP read_resource deprecation and
pytest-cache permissions warning. No warning or exclusion was suppressed.
Documentation file-target validation checked470 relative links across425 Markdown
documents with zero missing targets, excluding code fences and external URLs;
heading anchors were not automatically validated. The initial naive regex mistook
two fenced Python BaseModel expressions for links; respecting code fences resolved
those false positives without editing historical ADRs. Git diff check passes.

Production tunnel readyz returned200 at2026-09-28T14:53:02.235114Z. Its existing
tree33680→22920→79880→54892 is unchanged. Pre-existing tunnel process20956 was
left untouched. Final isolated Python tree95504→67560 and dedicated HTTPS
companion96480 serve the fixture; production does not load it.
Fixture server script SHA-256:
44c49c656e690de6945d6b89cb33e3200bd28dc65e3f8ed74527ddac598717ee.
Verifier SHA-256:
55e119cf554945ef7eda0992237f2efcb1171f2bb3dece40216346320fb5fe3c.
These are operator file/process attestations, not public source-revision proof.
Production's291-file content digest remains unchanged.

| Protected database | SHA-256 | Bytes | Exact UTC mtime |
| --- | --- | --- | --- |
| Certified production | 3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c | 189804544 | 2026-09-01T11:09:20.1047581Z |
| WP16 | 18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d | 37195776 | 2026-08-29T13:37:31.2308106Z |
| Phase8.5 evaluation | bc048cc15173acbd818b98786a3380a01f2263843a435708f6814c6de21a1d84 | 45592576 | 2026-09-08T06:41:25.6366051Z |
| Phase8.6 evaluation | 9a3521f8cefc74e2673592dbd207a7f5673dcfc05cebfdc18899d93be93307a2 | 52600832 | 2026-09-08T08:14:51.7220651Z |

Final22-entry rehash at2026-09-28T14:52:05.1622926Z had zero differences.
The new fixture database also retains its independently recorded digest.
It is978,944 bytes with UTC mtime2026-09-28T12:31:23.2319211Z.
Fresh production stdio adjacent checks received PDF[0,524288),[524288,1048576)
and JPEG[0,65536),[65536,131072). Actual decoded bytes matched public structured
and native metadata. rangeStart/rangeEnd are integers; rangeEndExclusive is
BOOLEAN true. Changed max_bytes conflicted safely. Both production versions
returned delivery.representation_unavailable in blocks and text with fresh
correlation IDs. Full multipart reconstruction was not needlessly repeated
because the product/binary implementation did not change.

Final tree: main/originmain at5d2612fef6d26cc1e1b0547bb5bd3da6abf21187;
58 modified tracked files,48 untracked entries,nothing staged. New files here:
fixture server, verifier, stdio launcher, inactive test-tunnel template,
five-test regression file and three reports. Updated existing files:
truth manifest, representative binary probe and current docs/reports indexes.
Other dirty files belong to prior work and were preserved. No Git staging,
commit,push,PR,merge,credential rotation,signed-artifact rewrite,protected corpus
write,production activation or serving-role promotion occurred.

Final post-change fixture rechecks: authenticated loopback SSE at
2026-09-28T14:55:33.165795Z–14:55:35.704041Z and real isolated stdio at
14:55:39.185640Z–14:55:43.882303Z both completed all four traversals and28
negative checks. All snapshots and content digests match the public run.
Final real-TCP rerun:256 passed,four warnings,125.22 seconds. Comparing actual
observed method/path pairs with the53-operation manifest found exactly53 expected
operations exercised,zero missing andzero extra pairs. Backends for disposable
HTTP tests include test doubles; this proves network/contract serialization, not
53 live production positive/mutation executions or public REST availability.
The final post-TCP protected comparison at2026-09-28T14:57:48.6155035Z again
matched all22 records and exactly one unchanged ACTIVE generation.
