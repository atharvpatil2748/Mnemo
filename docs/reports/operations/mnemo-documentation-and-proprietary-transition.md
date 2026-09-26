# Mnemo documentation reconciliation and proprietary current-tree transition

**Date:** 2026-09-26. **Scope:** documentation, repository community files and
project-owned package metadata only. This record does not amend accepted ADRs,
certification artifacts, historical license grants or GitHub visibility.

## Baseline, authority and implementation state

Initial Git: `main...origin/main`, HEAD
`069ec468a675c37544a5a2591eac1204c3cb6888`, 41 modified tracked and
18 untracked files, zero staged. Existing dirty Stage 6 source, tests and
reports were preserved. Current architecture §§21.3–21.8, the canonical
roadmap, ADR-0076/0077/0078 and the
[dated Stage 6 remediation acceptance](mnemo-stage-6-forensic-remediation-and-acceptance.md)
govern technical status. The [initial combined audit](mnemo-stage-6-combined-forensic-audit.md)
remains blocked historical evidence, not the current verdict. This pass did
not independently rerun the historical 2,694-pass, 18-skip, 90.31%-coverage
result until the validation checkpoint below; it is labeled by its source.

Modules 8.8.5, 8.8.7, 8.8.2f, 8.8.4 and 8.8.8 were independently accepted
locally after F-1 authenticated-principal propagation into partitioned V2
retrieval and F-2 top-level/nested source-metadata parity. Stage 5 remains
locally accepted. The five-module batch is uncommitted and unpublished; it is
not loaded into the production tunnel or newly externally verified. Stage 6
closure still requires 8.8.10a–c and 8.8.11a–c. Module 8.8.9 behavioral
four-transport parity, `search_images`, final Phase 8.8 certification and
Phase 9 readiness are separate gates. Production Phase 8.5 certification and
8.8.1 startup convergence remain scoped to their signed identities.

## Documentation and rights inventory

Reviewed root, `docs/`, component and plugin READMEs; current architecture,
roadmap, ADR index and accepted ADR-0076/0077/0078; Stage 5 and five-module
Stage 6 reports; governance, runbook, release, changelog and report indexes;
MCP/HTTP status descriptions; `.github` workflow/templates; Python/Node
manifests; root legal/community files; tracked source headers; and dependency,
model and evaluation license records. The complete local filename inventory
contained one root project-owned `LICENSE`, one `CONTRIBUTING.md`, one
`CODE_OF_CONDUCT.md`, one third-party source notice, three project-owned Python
license declarations, one already-private frontend package, and three
GitHub issue-template files plus a PR template. No separate root `NOTICE` or
`COPYING` was found.

| Class | Finding and disposition |
|---|---|
| Project-owned open-source grant/invitation | Root Apache-2.0 `LICENSE`, Apache badge, three Python `license` fields, public contribution guide and templates: removed from current tree. Root license SHA-256 before removal: `0f4f09dec1de81f9d8ebe6517d44e8f44e0644898939fb7dada4fcbface174a8f`. |
| Third-party notice | `mnemo-core/mnemo/THIRD_PARTY_NOTICES.md` and tiktoken-derived `o200k_base.py` retain MIT/OpenAI/Shantanu Jain attribution and upstream terms; no project-rights substitution. |
| Historical legal/governance evidence | Earlier license-bearing Git commits/tags, architecture task rows, release reports and evaluation proposals are retained as point-in-time records. Current status text now disambiguates them. |
| Dependency/model metadata | `uv.lock`, `pnpm-lock.yaml`, model-profile `license` values, reranker Apache-2.0 model metadata and package dependency notices are untouched. They do not license Mnemo-owned source. |
| Generated/vendor | No bundled generated binary or vendored license was deleted. Local build products and dependency caches remain outside the edit scope. |
| External reference checkouts | The local `references/` tree contains third-party sample repositories and many of their notices; `git ls-files references` returned zero tracked files. They were not relicensed or packaged by this edit. Inclusion in any future distribution requires a separate inventory. |
| Ownership/permission ambiguity | Local Git shortlog has only Atharv Patil as commit author through HEAD, but one commit has a Cursor AI-tool co-author trailer. Authorship records are not copyright assignments. Third-party code/asset/model rights and any non-Git contribution require distribution review. |

## Current-tree changes

- Root `README.md` now leads with the owner-specified copyright and
  all-rights-reserved notice, removes the Apache badge and public invitation,
  and separates local acceptance from deployment and certification.
- Component READMEs, `docs/README.md`, architecture and governance indexes
  point to the current-tree distribution policy and corrected Stage 6 status.
- Architecture §21.6 records F-1 principal/partition ancestry and no V1
  fallback; §21.7 records F-2 same-envelope nested parity. Its former
  open-source project type, license target and diagram label are corrected.
  The roadmap records local batch acceptance without changing canonical
  dependency order. No accepted ADR was rewritten or new retrieval ADR needed.
- The report index links this record; changelog 0090 is an unreleased entry.
  Prior reports and their counts/verdicts remain unchanged.
- `CODE_OF_CONDUCT.md` is retained as an internal behavioral standard with
  Contributor Covenant attribution, not a public participation invitation.
  Security, ADR, release and operational governance remains in force.
- The root project-owned `LICENSE`, public-only `CONTRIBUTING.md`, GitHub PR
  template and three issue-template files were removed. The three Python
  project packages no longer assert Apache-2.0 or advertise public issue
  submission; no fabricated proprietary SPDX identifier was added.
  `mnemo-ui/package.json` was already `private: true` and is unchanged.
  No automatic Python publication-prevention flag is asserted. CI remains
  read/test/build only; it contains no package-publish job.

Exact files edited in this pass: `README.md`, `CODE_OF_CONDUCT.md`,
`docs/README.md`, `docs/architecture/README.md`,
`docs/architecture/current/mnemo_architecture_v2.md`,
`docs/architecture/current/mnemo_engineering_roadmap.md`,
`docs/changelog/README.md`, `docs/governance/README.md`,
`docs/reports/README.md`, `mnemo-core/README.md`,
`mnemo-server/README.md`, `plugins/email-ingestion/README.md`,
`mnemo-core/pyproject.toml`, `mnemo-server/pyproject.toml`, and
`plugins/email-ingestion/pyproject.toml`. Newly added:
`docs/governance/active/proprietary_distribution_policy.md`,
`docs/changelog/entries/0090-stage-6-local-acceptance-proprietary-transition.md`,
and this report. Deleted: `LICENSE`, `CONTRIBUTING.md`,
`.github/pull_request_template.md`, `.github/ISSUE_TEMPLATE/bug_report.yml`,
`.github/ISSUE_TEMPLATE/architecture_proposal.yml`, and
`.github/ISSUE_TEMPLATE/config.yml`. All earlier Stage 6 implementation and
test edits are inherited and are not changes made by this transition.

## Historical rights and public exposure

The removed root file granted Apache License 2.0 rights for earlier licensed
versions. Removing it from the current tree does **not** rewrite Git history,
retroactively revoke prior grants, privatize past releases, or eliminate
third-party obligations. The [Apache-2.0 text](https://www.apache.org/licenses/LICENSE-2.0.html)
describes a perpetual, irrevocable copyright grant subject to its terms.
GitHub currently reports `atharvpatil2748/Mnemo` **public**, zero reported
forks, and a published `v0.25.0` release. These are point-in-time GitHub API
observations, not proof that no clones, mirrors, packages or cached copies
exist. [GitHub's visibility guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility)
states that public forks are not made private by making the source private.
The owner must separately decide and authorize any visibility, release,
package, mirror or access-control action. No such change was made here.
Python metadata has no ecosystem-wide `private` switch analogous to the
already-private UI package. Keep package registry credentials and publication
permissions restricted; confirm any release automation and registry visibility
with the owner before a future publication. This pass did not publish packages.

Before proprietary distribution, review inherited open-source components,
model weights, frontend/Electron build contents, bundled assets, generated
materials and any external contributions for attribution, copyleft and
distribution obligations. The local inventory did not establish a complete
third-party legal clearance or verify absence of off-Git rights. No private
contact detail is published; permission requests need an owner-authorized
channel. The new current-tree policy does not purport to supersede applicable
law or pre-existing rights.

## Residual-match classification and validation

Remaining Apache/MIT/open-source/license terms are expected in historical
roadmap tasks, prior reports, governance proposals, current legal explanation,
the third-party notice/source header, dependency/model license metadata,
lockfiles and evaluation-source constraints. Those are not current-project
open-source grants. No contradictory current project-owned package license or
public-contribution invitation should remain after the final search.

Final documentation links, metadata/lockfile checks, Python/frontend/build
checks, test results, Compose configuration and protected identities are
recorded in the completion checkpoint below.

## Completion checkpoint

The 15 edited/new current-status Markdown files had **153 relative links
checked, zero broken** after excluding inline code from link detection.
`markdown-it-py` parsed the root README, documentation
index, architecture, roadmap, policy and report. A broad first-pass checker
over local and ignored third-party reference Markdown flagged 36 apparent
links: 35 in external reference trees and one `class PageResponse[T](BaseModel):`
code-fence line in historical ADR-0050. The latter is not a Markdown link.
No accepted ADR or third-party reference checkout was edited to silence this
simple regex check. Current-document status searches found no active claim
that 8.8.2f awaits implementation, Stage 6 is closed, or Mnemo-owned current
code remains under Apache-2.0. Historical Stage 5 deferral wording remains
explicitly point-in-time.

`uv lock --check` resolved 171 packages. Ruff lint and format checks passed
(521 Python files formatted), strict mypy passed on 291 source files, and
compileall passed. All three Python source/wheel package builds passed; the
new 0.25.0 wheel metadata has no Mnemo-owned `License` field and the core wheel
retains `THIRD_PARTY_NOTICES.md`. Frontend format, lint, typecheck, one test
(100% reported frontend coverage), and build passed. All three Docker Compose
`config --quiet` checks passed. Docker image builds were **not run** and are
not claimed as passed. `git diff --check` passed. The local dangling temporary
`~nemo_server` dist-info warning was not cleaned up.

Because Python packaging metadata changed, the exact-tree full CI-safe
`CI=true MNEMO_CI=1 uv run pytest -q -p no:cacheprovider --tb=short
--cov-report=term:skip-covered` was run: **2,694 passed, 18 skipped, eight
warnings, 90.31% repository-wide coverage**, meeting the unchanged 90% gate.
Warnings were pre-existing Starlette/httpx, openpyxl fixture, local Qdrant,
MCP and FastAPI deprecations/advice. This run confirms local regression only,
not production deployment or external ChatGPT verification.

At the final checkpoint, production DB SHA-256
`3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`,
189,804,544 bytes, UTC mtime `2026-09-01T11:09:20.1047581Z`; WP16 DB SHA-256
`18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d`,
37,195,776 bytes, UTC mtime `2026-08-29T13:37:31.2308106Z` matched the
pre-edit and certified baselines. Neither had WAL, SHM or journal sidecars.
Production manifest `e579727c8867c92d4ca7fe05256a35d74942077f86b86a6fad9938ff3b4fc566`,
certified launcher `007ee235783cb8f673a2f9c135bc38269ba2a355057c5cd119c0125e471fde22`,
signed activation `c17a7f5531cc75795fb63c6f53682d30eb6ed831127db95038d3d1741cd25525`,
certificate `1a69e95796b98abcc1f4f6484692481058bff776b454a14e3a0b35d86f16312a`,
final evidence `0255160992fc1ed2fdc5b5c6bfb55bb442b55018655f511274d698569a06230c`,
and registry-referenced **signed** convergence
`b5ccccb9787773ef10f5a6364bbc80ed98324640ea5438da604ebfaf2b7c2b23`
matched accepted records. The distinct *derived*, unsigned comparison file
`scratch/phase8_8_1_runtime_convergence/convergence.json` remains
`57f6aa5ec5a92916d38a09600793068924a6967de53dbfb3490145cd47dd53a8`;
it must not be confused with the signed artifact. Credential-registry metadata
reports exactly one ACTIVE generation,
`fc85192e-f672-4cc0-9539-b4b063bb8f41`; no credential value was reported.

Final Git: `main...origin/main`, HEAD unchanged at
`069ec468a675c37544a5a2591eac1204c3cb6888`, zero staged, 52 modified
tracked, six deleted tracked, 21 untracked. The initial 41 modified/18
untracked Stage 6 work remains. The additional changes are the precisely
listed documentation, community and project-package metadata files above.
No product source/test code was edited in this pass. No commit, push, PR,
visibility change, package publication, deployment, production/tunnel restart,
credential change or protected-store mutation occurred.

**Documentation verdict:** `DOCUMENTATION_RECONCILED` for the current local
tree; historical evidence and mandatory Stage 6/Phase 8.8 gates remain open.
**Rights-posture verdict:** `PROPRIETARY_TRANSITION_LOCALLY_COMPLETED` for
Mnemo-owned material in the current tree only. Public GitHub exposure,
previously granted rights and third-party obligations require separate owner
and legal review before any proprietary distribution.
