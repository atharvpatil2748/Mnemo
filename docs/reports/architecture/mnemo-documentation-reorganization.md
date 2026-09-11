# Mnemo Documentation Reorganization

## Executive summary

The documentation tree was reorganized by moving files, not by layering indexes
over the former flat layout. The `docs/` root now contains only `README.md` and
the major category directories. Historical content was preserved, current
authority was separated from point-in-time evidence, and repository references
were rewritten to the new canonical paths.

## Before tree

Before this work, `docs/` contained 417 files across six existing subtrees and
33 root-level files. Of those root files, 32 were loose Markdown documents in
addition to `README.md`.

```text
docs/
├── README.md
├── 32 loose architecture, audit, milestone, module, and phase reports
├── adr/                  57 files
├── changelog/            88 files
├── governance/          206 files
├── milestone-evidence/    8 files
├── releases/              2 files
└── reports/               23 files
```

The complete pre-move classification, hashes, inbound references, proposed
destinations, and safety decisions are recorded in
[`scratch/mnemo-documentation-reorganization-inventory.json`](../../../scratch/mnemo-documentation-reorganization-inventory.json).

## After tree

```text
docs/
├── README.md
├── adr/
│   ├── README.md
│   ├── active/
│   └── superseded/
├── architecture/
│   ├── README.md
│   ├── current/
│   └── historical/
├── governance/
│   ├── README.md
│   ├── active/
│   ├── contracts/
│   ├── historical/
│   └── proposals/
├── reports/
│   ├── README.md
│   ├── architecture/
│   ├── audits/
│   ├── certification/current/
│   ├── certification/historical/
│   ├── evaluation/
│   └── performance/
├── milestones/
│   ├── README.md
│   ├── phase-4/
│   ├── phase-4-5/
│   ├── phase-5/
│   └── phase-6/
├── modules/
│   ├── README.md
│   ├── module-6/
│   ├── module-7/
│   └── module-8/
├── releases/
│   ├── README.md
│   └── historical/
├── changelog/
│   ├── README.md
│   └── entries/
├── runbooks/
│   ├── README.md
│   ├── development/
│   └── production/
└── evidence/
    ├── README.md
    └── historical/
        ├── milestones/
        └── phase-8-5/
```

## Move summary

| Measure | Result |
|---|---:|
| Files moved | 285 |
| Files renamed | 0 |
| Files deleted | 0 |
| Root-level files before | 33 |
| Root-level files after | 1 |
| Loose root Markdown files before, excluding README | 32 |
| Loose root Markdown files after, excluding README | 0 |

Important moves include:

- Broad architecture documents moved to `architecture/current/`; the Phase 8.5
  roadmap moved to `architecture/historical/`.
- ADR-0008 and ADR-0072 moved to `adr/superseded/`; all other accepted ADRs
  moved to `adr/active/` without renumbering or renaming.
- Module 6, 7, and 8 reports moved into dedicated module directories.
- Milestone reports moved under their corresponding phase; their JSON evidence
  moved to `evidence/historical/milestones/`.
- Phase 8.5 gate evidence moved to `evidence/historical/phase-8-5/`.
- Retrieval reports moved to `reports/evaluation/`, model benchmarks to
  `reports/performance/`, audits to `reports/audits/` or
  `reports/architecture/`, and certification reports to current/historical
  certification directories.
- Operational instructions moved to `runbooks/production/` and
  `runbooks/development/`.
- Changelog entries and release notes moved into their historical collections.

## Current authority

The principal current documents are:

- [`docs/README.md`](../../README.md) — documentation home.
- [Mnemo architecture v2](../../architecture/current/mnemo_architecture_v2.md).
- [Phase 8.5 architecture](../../architecture/historical/phase8.5_architecture.md).
- [ADR-0076](../../adr/active/ADR-0076-project-owner-engineering-certification-standard.md).
- [Final Mnemo V2 certification](../certification/current/mnemo-v2-final-certification.md).
- [Single production path audit](mnemo-v2-single-production-path-audit.md).
- [Active evaluation-harness governance](../../governance/active/evaluation_harness_governance.md).

## Historical preservation

No historical report, governance record, ADR, certification evidence, or
milestone record was deleted. Historical documents retain their original
claims and filenames. Directory placement and navigation metadata now prevent
those point-in-time claims from being mistaken for current production state.

## Link validation

All local Markdown link targets in the active repository documentation/source
surface were resolved after the moves. Legacy machine-specific
`file:///C:/...` links found there were replaced with portable relative
repository links. The final broken-link result is zero across 379 Markdown
files, and no stale moved-path reference remains in that surface. Ignored
point-in-time scratch audit archives were not rewritten; they are evidence
snapshots rather than canonical documentation and may quote paths that were
correct when captured.

## Git validation

The worktree was already dirty before the reorganization, with unrelated user
and prior certification changes. Those changes were preserved. Move integrity
checks prove that all 285 old paths are absent, all 285 destinations exist, and
all destinations are unique. The documentation-only targeted `git diff
--check` passes. The repository-wide check continues to report the unrelated
pre-existing trailing whitespace at `mnemo-core/mnemo/models/chunks.py:65`; it
was intentionally not modified.

## Production and certification safety

No production source, runtime configuration, corpus, embedding, FTS index,
model artifact, Ollama setting, or certification state was changed. The
production database remained byte-identical at SHA-256
`3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`,
with 44 documents, 44 versions, 44 memberships, 2,658 chunks, SQLite integrity
`ok`, zero foreign-key violations, and a zero-byte WAL.

The signed certification evidence continues to report:

- `V2_EXPOSED = true`
- `BGE_ACTIVE = true`
- `RERANKER_MODE = BGE_V2_M3`
- `EVALUATED = true`
- `VERIFIED = true`
- `CERTIFIED = true`

## Result

`DOCUMENTATION_REORGANIZATION_PASS`
