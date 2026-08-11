# 0035: Module 4.8 - Resume Chunker

**Date:** 2026-08-11
**Version:** 0.18.1

## Overview
This release implements Module 4.8 (Resume Chunker) of Phase 4 (Deterministic Chunking). 

## Changes
- Implemented `ResumeChunker` implementing `ChunkerInterfaceV2`.
- Registered chunker for `DocType.RESUME`.
- Added support for canonical boundary grouping `(parser.resume.section, parser.resume.role_local_id)`.
- Implemented fail-closed behavior for unclassified Resume blocks, grouping them deterministically into an `unknown` section chunk.
- Updated ADR-0017 to remove semantic guessing and confirm the fail-closed `unknown` section fallback behavior.
- Included 100% acceptance testing for Resume structure constraints, missing metadata handling, and oversized fallback limits.

## Validation
- The implementation strictly adheres to ADR-0015, operating without storage, LLMs, network, or reparsing.
- Provenance spans are contiguous, maintaining strict mapping to `ParsedDocument` ordinals.
- `ruff` linting and `mypy` typing passed.
- Pytest suite successfully executed and covers all boundary conditions.
