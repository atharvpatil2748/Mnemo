# ADR-0077: Governed mutable workspace boundary

- **Status:** Accepted; implemented and certified
- **Date:** 2026-09-22
- **Authority:** `PROJECT_OWNER_GOVERNANCE_APPROVAL`
- **Phase:** 8.8.14a
- **Extends:** ADR-0069, ADR-0070, ADR-0074, and ADR-0076
- **Supersedes:** The forward-planning alternative that left the Phase 9 mutable-workspace topology undecided; no historical evidence or completed implementation

## Context

The certified Phase 8.5 corpus is immutable and bound to database, configuration,
model, activation, and certification identities. Mnemo nevertheless has existing
notebook, source, note, session, ingestion, blob, parsed-document, cache, and
generated-artifact write paths. They currently share the generic storage facade.

The generic engine is not a read-only certified-corpus composition. Its
configuration resolves writable filesystem and SQLite paths, prepares their
parents, opens SQLite normally, enables WAL, applies migrations, and initializes
the blob and embedding-cache stores. Server startup initializes that engine
before it installs the read-only Full Multilingual V2 adapter. Consequently, the
read-only adapter does not establish a safe product-level boundary for future UI
or tool writes.

The existing FinalQA operational database and activation/certification records
are purpose-specific governed operational state. They are not a general user
workspace. Tokenizer/model caches are also separate from user data. No current
abstraction gives future Phase 9 writes a governed root that is disjoint from
all certified, evaluation, and operational artifacts.

## Decision

Mnemo accepts **Option A**: a separately governed mutable filesystem + SQLite
workspace. Production configuration must name its root explicitly as an
absolute, operator-controlled path. There is no implicit production default.

If the workspace configuration is absent, invalid, ambiguous, aliases or
overlaps protected storage, or fails any validation, production must apply
**Option B as its mandatory fail-closed fallback**: server-enforced read-only
workspace behavior. Mutation routes and tools must not be exposed. This fallback
does not make a malformed workspace acceptable and does not redirect writes to
another location.

This decision is implemented and machine-certified for Phase 8.8.14a. Phase
8.8 as a whole remains in progress and unverified; Phase 9 remains blocked.

## Storage roles

Every configured storage location must have exactly one server-owned role:

- `CERTIFIED_CORPUS`: immutable production database and canonical corpus blobs;
- `EVALUATION_ARTIFACT`: immutable or run-governed evaluation databases,
  datasets, manifests, and evidence;
- `GOVERNED_OPERATIONAL`: purpose-specific FinalQA execution,
  activation/lifecycle, and certification state;
- `MUTABLE_WORKSPACE`: user/application notebooks, sources, notes, sessions,
  uploads, parsed representations, and generated workspace artifacts; and
- `USER_CACHE`: disposable tokenizer, model, embedding, and other caches whose
  identity and lifecycle are not user-workspace persistence.

These roles remain distinct. A path cannot acquire a second role because a
caller, transport, environment, or working directory selects it. In particular,
the mutable workspace is not FinalQA operational storage, activation state,
certification state, an evaluation database, or a user cache.

## Workspace topology and configuration

After the configured root passes validation, the mutable workspace owns this
conceptual topology:

```text
<configured absolute mutable workspace root>/
    workspace.db
    blobs/
    parsed/
    caches/
    generated/
```

The child names are server-owned roles, not independently client-configurable
paths. The implementation may version this internal layout without weakening
the single-root boundary.

The root must not be derived from:

- the certified corpus database or its parent directory;
- the process current working directory;
- a client request, tool argument, upload field, or notebook record;
- an evaluation database, dataset, or run directory;
- FinalQA operational storage; or
- activation, lifecycle, certification, or evidence storage.

Relative and current-working-directory-dependent production workspace paths are
invalid. No fake fallback path may be supplied merely to make startup or tests
pass.

## Validation and startup ordering

The server-owned composition root must validate the complete role map before
any potentially mutating side effect, including:

1. directory creation;
2. SQLite connection;
3. WAL activation;
4. migrations;
5. embedding-cache initialization;
6. blob-store initialization; and
7. mutation-route or mutation-tool exposure.

Validation must use canonical, platform-aware identities and reject:

- equality between mutable and protected paths;
- ancestor or descendant overlap in either direction;
- symlink or Windows junction aliases;
- Windows case-normalization aliases;
- `..` traversal or any other lexical alias that resolves into a protected
  location;
- relative/CWD-dependent production paths; and
- client-selected database, blob, parsed, cache, generated, or storage-role
  paths.

Where a path or a not-yet-created descendant cannot be resolved safely, startup
must choose read-only behavior rather than assume separation. Validation covers
the certified corpus, canonical blobs, Phase 8.5 and Phase 8.6 evaluation
artifacts, certification manifests/evidence, activation state, FinalQA
operational state, and other explicitly governed roots.

## Composition and authorization boundary

Certified read storage and mutable workspace storage must be separate typed
dependencies. No generic writable storage object may be capable of addressing
both domains. Certified readers open only the certified corpus through the
governed read-only boundary. Workspace mutation services receive only the
`MUTABLE_WORKSPACE` dependency.

The server decides the effective storage role before authorization and route
dispatch. Authorization can decide whether an authenticated principal may
perform a mutation within the selected workspace; it cannot select a storage
root or convert protected storage into a mutable role. Transport clients never
supply physical paths.

Read-only fallback permits only routes/tools whose complete call graph is
non-mutating with respect to workspace and certified artifacts. Purpose-specific
governed operational writes remain independently controlled by their own
contracts; they do not authorize workspace mutation.

## Preserved boundaries

- The certified corpus and canonical corpus blobs remain immutable.
- Phase 8.5 remains certified for its exact governed identity.
- Phase 8.6 remains evaluation-only.
- FinalQA operational persistence remains separate and purpose-specific.
- Reranker activation, lifecycle, certification, and evidence state remain
  separate and server-owned.
- Tokenizer and model caches remain `USER_CACHE`, not user data.
- Qdrant and SurrealDB remain disabled and are not prerequisites.
- This decision does not choose the authenticated V2 chat contract owned by
  Phase 8.8.14b and does not begin Module 8.8.1 or Phase 9.

## Consequences

Phase 9 notebook creation, uploads, notes, sessions, and generated application
artifacts can be enabled only after the mutable workspace is configured,
validated, composed, authorized, and certified. Until then, a production profile
must not expose those mutations against the certified corpus.

The existing generic storage facade cannot simply be pointed at the certified
database and then overlaid with a read-only V2 adapter. Implementation requires
typed storage-role configuration, pre-I/O path validation, separate certified
read and workspace-write compositions, capability/route gating, and evidence
that protected hashes are unchanged.

## Certification requirements

Phase 8.8.14a is complete only when machine tests and retained evidence prove:

- accepted absolute workspace roots initialize only after full validation;
- missing or invalid configuration produces server-enforced read-only behavior;
- every equality, ancestor/descendant, traversal, symlink/junction, and Windows
  case-alias overlap is rejected before side effects;
- clients cannot select or override storage paths or roles;
- mutation routes/tools are absent or fail closed in read-only mode;
- workspace writes land only beneath the validated workspace root;
- certified readers cannot acquire writable workspace capabilities, and
  workspace writers cannot address certified/evaluation/operational roots;
- FinalQA, activation, certification, and user-cache roles remain separate;
- startup failure leaves no created directories, SQLite/WAL files, migrations,
  cache files, blob directories, or exposed mutation routes; and
- all protected database and artifact hashes remain unchanged across positive
  and negative tests.

## Implementation and certification record

The accepted boundary is implemented through explicit storage-role
configuration, a server-owned pre-I/O mutable-workspace validator, separate
immutable certified-read and mutable-workspace compositions, read-only fallback,
mutation-route gating, and truthful workspace/mutation capabilities.

Certification on 2026-09-22 established:

- focused boundary and composition coverage: 226 passed, 6 intentionally
  skipped;
- governance coverage: 21 passed;
- the corrected real governed-reader regression: 1 passed using
  `mode=ro&immutable=1` with unchanged hash, size, timestamp, and no SQLite
  sidecars;
- full CI-mode coverage: 2,341 passed, 18 intentionally skipped, 90.05%;
- Ruff formatting and linting, strict mypy across 282 source files, and
  compileall all passed; and
- both current governed databases retained their exact hashes, sizes, and
  timestamps with no WAL, SHM, or journal sidecars before or after the full
  suite.

The deprecated Manual Gita fixture and its writable Golden Corpus integration
test are removed from the active governed/test surface. This completion applies
only to 8.8.14a and does not complete any later Phase 8.8 task.
