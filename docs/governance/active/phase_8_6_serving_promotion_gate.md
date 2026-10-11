# Phase 8.6 future serving-role promotion gate

Status: **specified, not approved or activated**. This contract records the
review required by architecture §21.10 and roadmap Module 8.8.10b. It grants
no production-serving authority to the Phase 8.6 evaluation registry.

The current Phase 8.5 identity remains the sole certified production selection.
Phase 8.6's READY registry state means validation for the separately governed
evaluation workflow only. The registry is not a notebook federation source for
production MCP, HTTP, stdio or SSE requests. Clients cannot request a serving
role or supply a registry entry or filesystem path.

Before any future activation, the project owner and certification authority
must review one versioned, server-owned promotion proposal containing:

1. An explicit decision naming the proposed serving role, target generation and
   responsible approver; absence of a decision means evaluation-only.
2. A governed allowlist of exact notebook identities, not titles, aliases or
   filenames. Unknown or duplicate identities are not implicitly eligible.
3. Verified authenticated-principal memberships for each allowlisted notebook
   and subordinate-resource authorization, with unknown/unauthorized
   nondisclosure preserved.
4. Evidence that the selected immutable store supports the compatible older
   and newer schema read contracts, exact provenance and truthful locators.
5. Exact store/database, blob, index, embedding-model and reranker identities
   bound to one server-owned effective composition; no historical or evaluation
   fallback and no client overrides.
6. Scope-qualified capability lifecycle evidence separating readiness,
   activation, exposure, availability and certification. READY alone is not
   production availability.
7. Fresh HTTP, stdio, SSE and existing-tunnel parity evidence for the proposed
   identity, authenticated scope, errors and relevant tools.
8. Fresh source/document/version/chunk/asset provenance and citation
   certification for that identity.
9. Before/after protected-state hashes, sizes, UTC mtimes and SQLite sidecar
   observations, including production and evaluation stores and signed runtime
   evidence.
10. A separately authorized activation decision and post-activation
    verification. No proposal, test fixture or registry edit itself activates
    production serving.

An incomplete or unapproved proposal remains **evaluation-only**. A future
implementation must validate this complete gate before altering production
selection, and must follow the accepted ADR-0076/0077/0078 certification,
storage-role and credential authorities. Promotion does **not** copy or merge
the evaluation corpus into the certified production database. Module 8.8.10
does not implement a promotion API, change an allowlist or activate a new
generation.
