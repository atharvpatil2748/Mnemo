# ADR-0078: Generation-aware production credential lifecycle and re-keying

- **Status:** Accepted; implemented and certified for Module 8.8.1 on 2026-09-24
- **Date:** 2026-09-23
- **Authority:** Project-owner instruction for Module 8.8.1 recovery
- **Extends:** ADR-0076 and ADR-0077
- **Supersedes:** No historical activation, certificate, final evidence, or model identity

## Context

The original production delivery-cursor signing credential is unavailable. The
current signed reranker activation cannot be verified with a replacement key.
The production manifest also binds an activation, a WP-17 certificate, and
final evidence whose signature references must agree. Substituting a new secret
while reusing these artifacts would misrepresent cryptographic continuity.

## Decision

Mnemo assigns a non-secret ID to every server credential generation. A
canonical UTF-8 JSON registry records type, domain, owner principal, scope,
creation and transition times, lifecycle state, secret-store reference,
fingerprint, activation path/digest, certificate path/digest, and final-evidence
path/digest. A human-readable registry view contains the same non-secret facts.
Neither format contains secret material. The registry is governed operational
metadata, never a user workspace or certified corpus store.

Secrets are generated with a cryptographic random source and kept in the
operating system's user-bound secure credential store. The Windows deployment
uses Windows Credential Manager through its WinVault keyring backend. Production
must fail closed if that backend is unavailable; plaintext fallback, environment
dumping, and source-controlled credentials are forbidden. The server resolves
only the registry-selected `ACTIVE` generation and verifies the retrieved
secret's fingerprint before binding runtime identity. A client and the tunnel
cannot choose a generation or secret-store reference.

The supported lifecycle is `PROVISIONED` → `VALIDATED` → `ACTIVE` →
`SUPERSEDED` or `REVOKED`; malformed records are `INVALID` and cannot serve.
Provisioning does not activate production. Revocation disables use and does not
delete historical metadata. Rollback is possible only if the previous secret
is still accessible and its evidence remains valid; the lost original secret
cannot support cryptographic rollback.

Activation, WP-17 certificate, and final evidence for a new generation are
written to **new paths** and each binds its generation ID and predecessor
digest. The old artifacts remain byte-identical. The re-key operation stages a
new credential and evidence set, independently verifies the complete identity
chain and ADR-0076 gates, and promotes one active generation only after every
gate passes. Any staging failure leaves the new generation non-active and the
previous records intact. Promotion is fail-closed if the registry, manifest, or
artifact references disagree. A new generation never claims to validate the
old signature.

Tunnel control-plane credentials, external provider credentials, and Mnemo
server credentials are separate domains. This decision governs Mnemo server
credentials only; it neither copies nor rotates tunnel/provider credentials.
Authenticated principals and operator/service identities may be represented as
non-secret owners/scopes, without adding actor-to-notebook ACL semantics.

## Recovery execution status (2026-09-24)

The original signing secret remains unavailable. Its activation, certificate,
and final evidence are retained as historical. A distinct generation,
`fc85192e-f672-4cc0-9539-b4b063bb8f41`, has fresh signed activation,
five executed and signed WP-17 rehearsal records, a signed `/3` pre-activation
certificate, and generation-bound final evidence. These were independently
verified before atomic promotion. The registry now marks this generation
`ACTIVE`; the old cryptographic generation is not represented as verifiable
with the new key. The certified corpus and model revisions remain unchanged.

The OS-backed secret-store adapter, non-secret registry, generation-bound
verification, and fail-closed runtime selection remain in force. Signed
pre-certification convergence and separate signed post-promotion startup
convergence both passed. The scoped result and external-request evidence limit
are documented in the [certification report](../../reports/operations/mnemo-module-8-8-1-certification.md)
and [forensic audit](../../reports/operations/mnemo-module-8-8-1-forensic-audit.md).

## Pre-certification observation boundary

Fresh WP-17 transport evidence cannot be produced if final evidence is required
before every runtime call. A single staged `PROVISIONED` generation may therefore
enter `PRE_CERTIFICATION_OBSERVATION` after its new signed activation is verified
and recorded in the server-owned registry. This state is not certified or active.
The normal certified startup gate remains unchanged. A separate operator-started
observation-only HTTP/MCP composition uses the same canonical manifest, immutable
corpus reader, exact model profile/revisions, signed activation, and server-owned
authentication, but exposes only a read-only `observe_runtime` operation. It
registers no chat, mutation, or ordinary MCP knowledge tools.

Each actual ready-runtime observation is HMAC-bound to the staged generation,
campaign, transport, correlation ID, semantic composition, and safe principal
identity. Signed observations from HTTP, MCP stdio, MCP SSE, and the external
tunnel must match exactly. Their signed convergence record is a distinct
`PRE_CERTIFICATION_TRANSPORT_CONVERGENCE` artifact, never final certification.
WP-17 generation certification and final-evidence verification reject unsigned
or divergent transport parity. The registry records `OBSERVATION_CONVERGED`, then
`FINAL_EVIDENCE_GENERATED`, `CERTIFIED`, and `ACTIVE` only through the separately
verified lifecycle steps. Successful observation does not promote a generation.
The external tunnel remains transport-only; this decision does not authorize a
live cutover before local gates and operator provisioning pass.

## Historical-to-registry authority transition

Gate 0 locates the exact frozen reranker in the existing operator-owned offline
cache. The operator-only manifest transition has a read-only prepare step that
requires one staged, signed generation, verifies its credential references and
activation against the canonical corpus/profile, and records the hashes of the
historical activation, certificate, and final evidence. Commit revalidates the
same inputs under an exclusive lock and atomically replaces only the manifest.
The candidate removes all three historical authority fields, points to the
server-derived operational registry, and marks certified/active lifecycle
claims false. A missing, ambiguous, incomplete, or changed registry leaves the
old manifest untouched. The historical signed files are never overwritten.
The real production manifest now selects the credential registry as its sole
authority. That transition alone did not activate or certify the then-staged
generation; subsequent independently verified evidence and atomic promotion did.

## WP-17 pre-activation authorization and rehearsal

The historical WP-17 certificate records an already exposed BGE production
runtime. Its signed `/1` semantics and artifacts remain unchanged. A new
credential generation cannot use that historical final-active-state claim as a
precondition for its own certificate: ordinary certified startup requires the
certificate, final evidence, and an active registry pointer first.

For generation-bound WP-17, `final_active_state` refers only to the **final BGE
state of an isolated rehearsal**, after real rollback, reactivation, and
restart checks. It must state `scope=ISOLATED_WP17_REHEARSAL`,
`global_generation_active=false`, and `public_production_exposed=false`.
This is not production promotion or post-activation attestation. A
generation-bound pre-activation certificate uses schema `/3`, declares
`PRE_ACTIVATION_CERTIFIED`, and leaves lifecycle `ACTIVE` and `EXPOSED` false.
Historical `/1` certificates retain their original meaning.

The five fresh generation rehearsal records (evaluation, activation, security,
rollback, and rehearsal final BGE state) use the existing WP-17 evidence inputs
but must be signed under the generation's certification credential. Verification
binds each record's type, generation, activation digest, complete signed
four-transport semantic identity, isolation scope, executed-check declarations,
and content signature. A historical PASS file with a new generation ID cannot
meet this contract. The producer must supply real measured results; signing a
synthetic check declaration is not a valid operational rehearsal.
The WP-17 authority provides a read-only generation rehearsal verifier; its
PASS result alone does not write a certificate or promote a generation.

The order is: signed activation and four-transport observation convergence;
fresh, independently verified generation-bound WP-17 rehearsal evidence;
pre-activation certificate; generation-bound final evidence; atomic registry
promotion; certified startup; separate post-activation verification. Neither
the rehearsal nor the certificate authorizes serving while the registry
generation is non-active. The producer must run the evaluation and security
checks and isolate rollback effects; relabeling historical PASS files is not
valid rehearsal evidence.

## Non-goals

- No full multi-user ACL or product account system.
- No plaintext secrets in JSON, Markdown, TOML, YAML, logs, tests, Git, or
  certification artifacts.
- No silent credential replacement, old-evidence overwrite, or bypass of
  signature, transport, authorization, or WP-17 verification.
- No automatic deletion of historical evidence or inaccessible old credentials.
- No Module 8.8.2 or Phase 9 implementation.
