# Changelog 0008: SQLite FTS5 Store

**Date**: 2026-08-07
**Component**: Storage
**Status**: Implemented

## Overview

This module completes **Module 2.2: SQLite FTS5 Store** as defined in the Phase 2 roadmap. It provides a robust, relational metadata store implementing `StorageInterfaceV1` with integrated BM25 sparse search capabilities.

## Changes

- Created `mnemo/storage/sqlite.py` implementing `StorageInterfaceV1`.
- Configured schema migrations with explicit normalization (3NF) and cascading foreign keys.
- Implemented `DocumentRepository`, `NotebookRepository`, `SessionRepository`, `CitationRepository`, and `ChunkRepository`.
- Built BM25 sparse search using SQLite FTS5 `content='chunks'` table with trigger-based sync.
- Integrated filtering constraints (Notebook, Document Type, Source) directly into the FTS5 query.
- Re-inverted FTS5's negative BM25 score to positive relevance.
- Used `aiosqlite` with `BEGIN IMMEDIATE` manual transaction patterns (`@asynccontextmanager _transaction`) for absolute write consistency.
- Maintained a strict `foreign_keys = ON` policy per connection setup.

## Validation

- Passed `mypy --strict`.
- Passed `ruff format` and `ruff check`.
- Written comprehensive `test_sqlite_store.py` covering all implemented behaviors and cascading deletes.
- Achieved >93% overall codebase test coverage, satisfying the >90% coverage requirement.
- Successfully performed integration checks via Pytest without transaction deadlocks.

## Architectural Consistency

- No deviations from `StorageInterfaceV1`.
- Identifiers are exactly `UUID` as requested.
- Preserved immutability paradigms as outlined in ADR-0001.

## Next Steps

- This concludes Module 2.2.
- The project is ready to proceed to Module 2.3 (Graph Store).
