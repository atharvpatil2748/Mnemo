# Mnemo pre-Phase-8.8 Git baseline audit

Status: **PRE_PHASE_8_8_GIT_BASELINE_AUDIT_COMPLETE**  
Scope: Git forensics and baseline planning only  
Audit timestamp: 2026-09-08T18:54:28.3825080Z

## 1. Git state

The repository is on `main` at
`31cdfb179a15fd96153071373641d24af0b815ed`. `origin/main` resolves to the
same commit. The remote is `https://github.com/atharvpatil2748/Mnemo.git`.

Before creating this report and its JSON companion, the working tree contained
965 entries: 75 tracked modifications, 176 tracked deletions, no Git-recognized
renames, and 714 untracked files. The tracked diff contains 8,526 insertions and
27,006 deletions across 251 paths. `git diff --check` fails on pre-existing
trailing whitespace at `mnemo-core/mnemo/models/chunks.py:65`.

The unstaged documentation moves are currently represented as old-path
deletions plus new untracked paths. All 176 deleted documentation filenames
exist at new same-filename destinations. Of those, 111 are byte-identical; 65
also contain content edits. The absence of Git rename records is therefore an
index-state effect, not evidence that the destination documents are unrelated.

## 2. Dirty-tree inventory

Counts below classify every one of the 965 pre-audit entries. Sizes are the
working file size, or the `HEAD` blob size for deleted paths.

| Category | Count | Approx. size | Tracked | Untracked | Recommended treatment |
|---|---:|---:|---:|---:|---|
| SOURCE_CODE | 191 | 2.65 MB | 48 | 143 | Review and commit only in coherent implementation units |
| TEST_CODE | 79 | 1.17 MB | 20 | 59 | Bind to the implementation increment being tested |
| SCRIPT | 13 | 146 KB | 1 | 12 | Separate governed reusable tooling from diagnostics |
| CONFIGURATION | 5 | 14 KB | 1 | 4 | Do not commit before configuration ownership review |
| DOCUMENTATION | 320 | 2.32 MB | 100 | 220 | Potentially safe only as the complete move/edit set |
| README | 15 | 45 KB | 3 | 12 | Review mixed attribution and implementation claims |
| DATABASE | 4 | 17.84 MB | 1 | 3 | Do not commit without an explicit fixture decision |
| EMBEDDING/INDEX | 0 | 0 | 0 | 0 | No dirty entries; current artifacts remain protected |
| MODEL_ARTIFACT | 0 | 0 | 0 | 0 | No dirty entries |
| SCRATCH | 0 | 0 | 0 | 0 | Ignored; do not commit wholesale |
| GENERATED_OUTPUT | 0 | 0 | 0 | 0 | Ignored or governed separately |
| CACHE | 0 | 0 | 0 | 0 | Ignored; never commit |
| TEMPORARY | 0 | 0 | 0 | 0 | Ignored or absent; never commit |
| BUILD_OUTPUT | 0 | 0 | 0 | 0 | Ignored; never commit |
| EVALUATION_ARTIFACT | 60 | 222.52 MB | 0 | 60 | Requires a deliberate corpus/evaluation policy |
| CERTIFICATION_ARTIFACT | 19 | 101 KB | 3 | 16 | Protected; review moves and evidence bindings |
| GOVERNANCE_ARTIFACT | 259 | 6.53 MB | 74 | 185 | Protected; commit only as a complete history-preserving set |
| UNKNOWN_REVIEW_REQUIRED | 0 | 0 | 0 | 0 | No entry remained unclassified |

The exact semantic source/test/script count is 283 (191 + 79 + 13). The earlier
271 figure was a filename/path-regex approximation that omitted source-like
files under less conventional paths, including corpus tooling.

## 3. Pre-existing versus recent changes

Source and test timestamps span June through September 8, with the dominant
implementation period from August 24 through September 7. They therefore
predate the immediately preceding documentation synchronization task.

The prior task touched these twelve files:

| Path | Git state | Pre-existing before task? | Last task changed it? | Proposed action |
|---|---|---|---|---|
| `README.md` | tracked modified | Indeterminate/mixed | Yes | Review full diff |
| `mnemo-core/README.md` | tracked modified | Indeterminate/mixed | Yes | Review with core baseline |
| `mnemo-server/README.md` | tracked modified | Indeterminate/mixed | Yes | Review with server/MCP baseline |
| `docs/README.md` | untracked | Yes, reorganization output | Yes | Commit with complete docs move |
| `docs/architecture/README.md` | untracked | Yes | Yes | Commit with complete docs move |
| `docs/reports/README.md` | untracked | Yes | Yes | Commit with complete docs move |
| `docs/adr/README.md` | untracked | Yes | Yes | Commit with complete ADR move |
| `docs/architecture/historical/mnemo_phase8_5_engineering_roadmap.md` | untracked | Yes | Yes | Pair with source deletion |
| `docs/architecture/historical/phase8.5_architecture.md` | untracked | Yes | Yes | Commit with historical architecture set |
| `docs/reports/architecture/mnemo-documentation-reorganization.md` | untracked | Yes | Yes | Commit as move evidence |
| `docs/modules/module-7/MODULE_7_2_ADVERSARIAL_FORENSIC_REVIEW.md` | untracked | Yes | Yes | Pair with source deletion |
| `docs/reports/audits/audit_report_phase0-8.md` | untracked | Yes | Yes | Pair with source deletion |

All twelve have September 8 task-time modification stamps. The nine untracked
files were already present in the reorganized documentation tree and were
further edited. The tracked modified count moved from 74 to 75 even though all
three tracked READMEs were touched; therefore at least two were already dirty.
There is no saved per-path pre-task snapshot capable of identifying which one
newly transitioned from clean to modified. Treat all three as mixed-attribution
files requiring whole-diff review.

## 4. Documentation changes

The documentation state is principally a real tree reorganization plus later
architecture synchronization. It must not be committed by selecting only the
new directories: doing that would omit the matching tracked deletions. The safe
documentation set is the complete old-path deletion/new-path addition pairing,
followed by review of the 65 moved documents whose bytes changed.

The living architecture and roadmap, Phase 8.5/8.6/8.7 history, MCP audits,
certification reports, ADRs, and governance records are all present in the new
tree. They are potentially committable as documentation, but only as one
reviewed move/edit unit. A documentation-only commit would leave the V2 source
implementation it describes uncommitted, so it is not by itself a trustworthy
pre-8.8 implementation baseline.

## 5. Source and test changes

The 283 source/test/script entries are coherent accumulated Phase 8.5, Phase
8.6, Phase 8.7, V2 production, and certification work rather than generated
code. Evidence includes implementation and tests for:

- multilingual and multimodal models, OCR, Vision, CLIP, structured retrieval,
  projection generations, and asset foundations;
- V2 retrieval authorization, evidence resolution, production adapters,
  production readiness, FinalQA operational-store separation, and durable BGE
  activation;
- HTTP/MCP contracts, authenticated principal handling, transport validation,
  evaluation notebook registry/canonical JSON, and certification authorities.

No implementation reference to `search_images` exists. The dedicated Phase 8.8
MCP tool has therefore not begun. A schema-compatible immutable V2 chunk reader
does exist in `mnemo-core/mnemo/storage/v2_runtime.py`, but the generic
`SQLiteStore.get_chunk()` path still selects `position_page_start/end`. This
explains why legacy sparse retrieval against the older certified schema still
fails as `sq-2:sparse`.

The failing validation results correlate directly with this accumulated work:

- `SQLiteStore` advances the schema from 6 to 16, while eight older migration
  tests retain intermediate schema expectations.
- expanded top-level exports cause the two frozen Phase 1 export/import tests
  to fail;
- `mnemo.toml` changes to the production corpus, BGE-M3, and no outer reranker,
  while one profile-authority test retains the old expectation;
- five golden MCP retrieval tests encounter the old-schema sparse reader;
- most MCP tests expect 14 tools, while one golden-corpus test still expects 10;
- one plugin-registration test, one mypy assignment, and 52 Ruff findings remain.

This is legitimate but incompletely integrated work. It is not safe to squash
into a checkpoint until reviewed and brought to an explicitly accepted test
state in a separately authorized source task.

## 6. Database, index, and embedding state

Four database-like dirty entries exist:

| Path | State | Size | SHA-256 | Finding | Treatment |
|---|---|---:|---|---|---|
| `data/manual-gita-qa/mnemo.db` | tracked modified | 8,867,840 | `94161cf3e4121e15db65bb3f819d51cbd0f0206a1e576ac0ea343a572f9fa2e7` | 15 docs, 1,514 chunks, schema expanded, integrity OK | Explicit fixture decision required |
| `data/manual-gita-qa/mnemo.db.7-source` | untracked | 4,485,120 | `4d2cb30940336c91fde59ed3900466eafa4185cd06d05daa51648533a8962d49` | 7-doc backup | Do not commit |
| `data/manual-gita-qa/mnemo.db.before-15doc-switch` | untracked | 4,485,120 | same as above | byte-identical backup | Do not commit |
| `mnemo.db` | untracked | 0 | empty-file digest | empty local artifact | Do not commit |

The tracked DB is a legacy/golden test fixture or local runtime database, not
the certified production store. It was already dirty before the documentation
task; its September 8 modification time also shows it was touched during later
test execution. Its eventual inclusion must be a conscious fixture migration,
never an incidental part of a broad commit.

No embedding/index or model artifact occurs in the non-ignored 965-entry set.
Current indexes, embeddings, and model/runtime caches reside in protected or
ignored storage and must remain outside a general Git commit.

## 7. Generated, cache, and temporary state

The repository already ignores `.venv`, Python caches, `.pytest_cache`,
`.mypy_cache`, `.ruff_cache`, coverage, `dist`, `node_modules`, `.pnpm-store`,
`scratch`, local data, Qdrant/SurrealDB data, and `references`.

Material ignored storage includes approximately 6.60 GB under `scratch`, 1.12
GB under `.venv`, 181 MB under `mnemo-ui/node_modules`, 164 MB under the local
pnpm store, 484 MB under `data/canonical_production`, and 301 MB under
`references`. These are intentionally absent from the 965-entry classification
and must not be committed. `.pytest_cache` is ignored but currently has a
Windows permission issue. The two database backup suffixes and empty root
`mnemo.db` are not ignored and need a later owner policy decision; this audit
does not change `.gitignore`.

## 8. Certification and governance

There are 320 dirty governance/certification/evidence-related path entries when
the reorganized ADR, governance, evidence, changelog, release, and named
certification paths are considered together: 77 old-path deletions and 243 new
untracked paths. This includes current ADR-0070, ADR-0076, the current final
certification report, historical certification reports, and the moved release
and changelog records.

These paths are protected audit history. Their dirty state is primarily the
documentation reorganization plus newly generated governance/certification
records. They should be committed only after verifying every old/new move pair
and every artifact digest/reference; they must not be discarded or committed
piecemeal.

## 9. Protected artifact verification

Read-only SHA-256 checks passed:

- production: `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`;
- Phase 8.5 notebook: `bc048cc15173acbd818b98786a3380a01f2263843a435708f6814c6de21a1d84`;
- Phase 8.6 notebook: `9a3521f8cefc74e2673592dbd207a7f5673dcfc05cebfdc18899d93be93307a2`.

All three reside under ignored scratch paths and are absent from the dirty Git
set. No model, embedding, MCP tunnel, Qdrant, SurrealDB, or activation state was
changed by this audit.

## 10. Candidate commit sets

### SAFE_TO_COMMIT after review

- the complete documentation reorganization, including both sides of every
  move and the synchronized README/living-document edits;
- coherent V2 implementation units with their own tests, but only after their
  quality gates are accepted or corrected in a separately authorized task.

### DO_NOT_COMMIT

- ignored caches, environments, node modules, builds, coverage, scratch,
  runtime logs, local indexes, embeddings, and model artifacts;
- any of the four dirty database-like files without an explicit fixture/data
  decision;
- protected certified stores;
- the entire working tree as one undifferentiated commit.

### REVIEW_REQUIRED

- all 283 source/test/script entries;
- all five configuration entries;
- all 60 untracked evaluation/corpus entries;
- the 65 moved documentation files with content changes;
- governance/certification evidence bindings.

## 11. Strategy assessment and risks

**Option A — documentation-only checkpoint:** technically possible with very
careful path selection, but it leaves the implementation described by the docs
uncommitted and risks incomplete move pairs. It is suitable only as a docs
reorganization commit inside a larger ordered baseline, not as the baseline by
itself.

**Option B — commit all accumulated work:** unsafe now. Tests/lint/type checking
fail, and configuration, database fixtures, evaluation corpora, and generated
evidence have different governance requirements.

**Option C — new branch or worktree from current HEAD:** preserves this working
tree but starts from v0.25.0 without the accumulated V2 implementation. A branch
pointer cannot capture uncommitted files and therefore does not create the
desired baseline.

**Option D — reviewed layered baseline:** recommended. Preserve this inventory,
make explicit owner decisions on data/config/evaluation scope, review and
integrate the accumulated implementation in coherent commits, then commit the
documentation move/synchronization as a complete pair-preserving change. Record
the resulting green commit as the pre-Phase-8.8 baseline.

The main risks are accidental inclusion of mutable databases, orphaning one
side of documentation moves, committing certification records without their
bound implementation/evidence, and losing traceability by squashing months of
work into one commit.

## 12. Recommended baseline strategy

Use **Strategy D**:

1. Project owner decides whether `data/manual-gita-qa/mnemo.db` is an intended
   updated tracked fixture.
2. Project owner decides whether the 60 evaluation/corpus files belong in Git.
3. Project owner confirms the four untracked production/profile configuration
   files are intended repository configuration rather than local state.
4. In a separately authorized task, review accumulated V2 work by coherent
   Phase 8.5/8.6/8.7/certification units and resolve the existing integration
   failures without implementing Phase 8.8.
5. Create ordered implementation/config/test commits, excluding unapproved
   databases and generated/runtime files.
6. Commit the full documentation reorganization and synchronization as its own
   reviewed move/edit commit.
7. Record the resulting passing commit as the exact Phase 8.8 starting point.

A perfectly clean tree is less important than preserving work, but Phase 8.8
should begin from a known commit that contains the implementation it is meant
to harden. If intentionally retained local artifacts remain dirty, bind their
path/digest inventory to the baseline and explicitly exclude them from Phase
8.8 commits.

## 13. Exact next action required from the project owner

Approve or revise Strategy D and provide three scope decisions: whether the
15-document `data/manual-gita-qa/mnemo.db` is an intentional fixture update,
whether the 60 evaluation/corpus files are intended Git content, and whether
the four untracked production/profile configuration files should be committed.
Then authorize a separate pre-8.8 source-integration task to review/fix the
existing quality failures and prepare the ordered commit series.

## Final decision

CURRENT BRANCH:  
main

CURRENT HEAD:  
31cdfb179a15fd96153071373641d24af0b815ed

UPSTREAM:  
origin/main at 31cdfb179a15fd96153071373641d24af0b815ed

WORKING TREE:  
DIRTY

TRACKED CHANGES:  
251 (75 modified, 176 deleted)

UNTRACKED:  
714 before these two requested audit outputs

DOCUMENTATION CHANGES FROM LAST TASK:  
12

SOURCE/TEST/SCRIPT CHANGES:  
283 exact semantic classification; 271 was the prior path-regex approximation

DATABASE/INDEX CHANGES:  
4 database-like entries; 0 embedding/index entries

PROTECTED ARTIFACTS:  
PASS

PRE-EXISTING WORK IDENTIFIED:  
YES

DOCUMENTATION-ONLY CHECKPOINT POSSIBLE:  
REQUIRES CAREFUL PATH SELECTION

SAFE BASELINE STRATEGY:  
D

REASON:  
The tree contains coherent but uncommitted V2 implementation, tests,
configuration, evaluation material, certification/governance evidence, and a
documentation reorganization. A reviewed layered baseline preserves that work
without mixing mutable databases, generated artifacts, and unrelated concerns.

COMMIT:  
NOT PERFORMED

PUSH:  
NOT PERFORMED

PHASE 8.8:  
NOT STARTED

FINAL STATUS:  
PRE_PHASE_8_8_GIT_BASELINE_AUDIT_COMPLETE
