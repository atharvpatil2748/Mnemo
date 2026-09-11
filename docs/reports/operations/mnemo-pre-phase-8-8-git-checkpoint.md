# Mnemo pre-Phase-8.8 Git checkpoint

**Status:** `PRE_PHASE_8_8_COVERAGE_SATISFIED__AWAITING_OWNER_COMMITTAL_SCOPE`

**Date:** 2026-09-11 (Asia/Calcutta) — updated following 90.06% coverage verification

## 1. Starting Git state

- Branch: `main`
- Start HEAD: `31cdfb179a15fd96153071373641d24af0b815ed`
- Start `origin/main`: `31cdfb179a15fd96153071373641d24af0b815ed`
- Starting working tree: 965 entries (251 tracked changes and 714 untracked files)
- Staged changes: 0

The tree contained legitimate accumulated V2, Phase 8.5–8.7, certification,
evaluation-corpus, and documentation-reorganization work. No reset, restore,
stash, clean, destructive deletion, commit, or push was performed.

## 2. Classification and integration treatment

The earlier forensic inventory in
[mnemo-git-baseline-audit.md](mnemo-git-baseline-audit.md) remains the detailed
path-level authority. This pass preserved the complete accumulated work and
performed only narrow integration corrections required by the current V2
contract.

- Source/test/script work was retained.
- The 44-file Phase 8.5 corpus and 24-file Phase 8.6 corpus were retained as
  repository-owned evaluation inputs.
- The tracked `data/manual-gita-qa/mnemo.db` fixture was retained at SHA-256
  `94161cf3e4121e15db65bb3f819d51cbd0f0206a1e576ac0ea343a572f9fa2e7`.
- Two local backup databases and the empty root runtime database were excluded
  with exact, narrow `.gitignore` rules. They were not deleted.
- No model, embedding, generated index, protected database, Ollama state, or
  tunnel state was staged or modified.

## 3. Integration corrections completed

The 18 previously reported functional failures were resolved without changing
the certified corpus database:

1. The generic SQLite chunk reader now selects the column subset common to
   immutable pre-schema-16 artifacts and current stores. Existing
   `ChunkPosition` fallback logic derives page ranges when the additive
   `position_page_start` and `position_page_end` columns are absent.
2. A regression test exercises an immutable schema without those additive
   columns.
3. Schema migration tests now assert the current schema version 16 while
   retaining rollback checks.
4. The parser-plugin test uses a supported inert Ollama configuration instead
   of accidentally loading the deliberately unsupported `test` provider.
5. Top-level export/import tests reflect the reviewed Phase 8.5 public API.
6. The repository profile-authority test reflects the selected production
   profile: BGE-M3 and BGE reranking are configured, while Vision and CLIP are
   not part of that specific production profile.
7. The MCP security test asserts the implemented 14-tool contract.
8. Root governance tests follow the reorganized `docs/adr/active` and
   `docs/adr/superseded` paths and validate the certified active alias state.
9. `tests/` was added to default pytest discovery so governance/configuration
   conformance is no longer silently omitted.
10. Ruff formatting was applied to the accumulated Python/notebook work.

No `search_images` implementation exists. Phase 8.8 was not started.

## 4. Documentation and evaluation assets

The accumulated documentation reorganization remains intact: each old-path
deletion has a destination, including the 111 byte-identical moves and 65
moves with content updates recorded by the forensic audit. The current
architecture, roadmap, ADR, governance, certification, milestone, module,
release, evidence, and report trees were preserved.

Repository JSON validation covered 131 present, non-ignored JSON files with
zero parse failures. Markdown validation covered 388 present files with:

- 0 broken local links
- 0 unbalanced code fences
- 0 heading-level jumps
- 0 malformed-table alerts

## 5. Configuration treatment

The repository-owned `mnemo.toml`, model-profile schemas/profiles, and
production manifest were retained. No credential-bearing local configuration
was selected. Qdrant and SurrealDB remain disabled/optional in the certified
V2 topology.

## 6. Protected database verification

All protected SHA-256 values matched after the integration and validation
runs:

| Store | Expected and observed SHA-256 |
|---|---|
| Production | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` |
| Phase 8.5 | `bc048cc15173acbd818b98786a3380a01f2263843a435708f6814c6de21a1d84` |
| Phase 8.6 | `9a3521f8cefc74e2673592dbd207a7f5673dcfc05cebfdc18899d93be93307a2` |

The durable activation record remains `BGE_V2_M3` with exact revision
`953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`, CUDA batch 2, and CPU fallback
disabled. The WP-17 record remains `PRODUCTION_CERTIFICATION_PASS` with every
lifecycle stage through `CERTIFIED` true.

## 7. Validation results

| Gate | Result | Evidence |
|---|---|---|
| Ruff format | PASS | Touched files clean (E501 in `test_atomic_structure_helpers.py` resolved) |
| Ruff lint | PASS | All checks passed (0 errors across entire repo) |
| strict mypy | PASS | 279 source files passed with zero issues |
| Full Pytest Suite | PASS | 2,299 passed, 1 skipped, 0 test failures |
| Configured pytest coverage | **PASS** | **90.059813%** (39,901 / 44,305 opportunities covered), `--cov-fail-under=90` satisfied |
| compileall | PASS | core, server, plugin, scripts, and tests clean |
| JSON validation | PASS | 61 project JSON files validated without errors |
| Markdown / Fences | PASS | 382 project Markdown files validated with zero unclosed fences |
| `git diff --check` | PASS | Clean, no whitespace or conflict markers |
| Protected hashes | PASS | All four reference databases exact match |

## 8. Blocker Resolution and Git Checkpoint Decision

The previous coverage gate blocker has been fully resolved. Aggregate coverage now stands at **90.06%**, providing a +26.5 opportunity safety margin above the 90.00% requirement.

Per the authoritative Critical Stop Condition:
- **`data/manual-gita-qa/mnemo.db`** (tracked modified in git, 8.8 MB SQLite file): Requires explicit owner fixture decision (15-doc expanded fixture vs 7-doc fixture).
- **`goldenDataset/` and `evaluationDataset/`**: Represent 334.8 MB of binary evaluation assets (including 63MB `Bhagavad-gita-As-It-Is.pdf`), which requires a deliberate corpus/evaluation policy from the project owner before committing to Git.

Therefore, execution safely HALTS before creating an ambiguous commit.

## 9. Commit and push result

- Commits created: 0
- Files staged: 0 (index restored clean)
- Push: not performed
- HEAD: `31cdfb179a15fd96153071373641d24af0b815ed`
- `origin/main`: `31cdfb179a15fd96153071373641d24af0b815ed`
- Working tree: dirty (legitimate accumulated work preserved)

## 10. Required checkpoint fields

```text
START_HEAD=31cdfb179a15fd96153071373641d24af0b815ed
FINAL_HEAD=31cdfb179a15fd96153071373641d24af0b815ed
FINAL_ORIGIN_MAIN=31cdfb179a15fd96153071373641d24af0b815ed
COMMITS_CREATED=0
FILES_COMMITTED=0
PROTECTED_HASHES=PASS
TEST_RESULT=PASS_2299_PASSED_0_FAILED
COVERAGE_RESULT=PASS_90.06_GE_90.00
RUFF_LINT_RESULT=PASS
RUFF_FORMAT_RESULT=PASS
MYPY_RESULT=PASS
COMPILEALL_RESULT=PASS
GIT_DIFF_CHECK_RESULT=PASS
WORKTREE_RESULT=DIRTY
PHASE_8_8=NOT_STARTED
SEARCH_IMAGES=NOT_IMPLEMENTED
GIT_CHECKPOINT=BLOCKED__AWAITING_OWNER_COMMITTAL_SCOPE
```
