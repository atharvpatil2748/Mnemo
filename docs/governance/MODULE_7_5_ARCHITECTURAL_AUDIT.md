# Module 7.5 — Architectural Audit & Contract Forensic Analysis

- **Module:** Phase 7, Module 7.5 (Sessions, Notes & Insights REST Endpoints)
- **Status:** AUDITED & APPROVED
- **Date:** 2026-08-16
- **Authoritative References:**
  - `docs/mnemo_architecture_v2.md` §4.3, §5.1
  - `docs/mnemo_engineering_roadmap.md` Phase 7, Module 7.5 & Phase 10
  - `docs/adr/ADR-0049-phase-7-server-application-architecture.md`
  - `docs/adr/ADR-0050-notebook-and-knowledge-graph-rest-api.md`
  - `docs/adr/ADR-0051-sources-and-document-ingestion-rest-api.md`
  - Frozen `mnemo-core` models (`mnemo/models/notebook.py`) and interfaces (`mnemo/interfaces/storage.py`)

---

## 1. Executive Summary

This forensic architectural audit reviews the contracts, domain models, storage interfaces, security/ownership invariants, and runtime composition required for Phase 7, Module 7.5.

Module 7.5 exposes 11 REST endpoints under the `/v1/notebooks/{notebook_id}/` scope:
- **Sessions (5 endpoints):** List sessions, Create session, Get session with turns & citations, Append turn, Delete session.
- **Notes (4 endpoints):** List notes, Create note, Update note (PATCH), Delete note.
- **Insights (2 endpoints):** List extracted insights, Trigger insight generation (formally deferred to Phase 10 with 501 status).

All domain entities (`Session`, `Turn`, `Citation`, `Note`, `Insight`), enums (`TurnRole`, `NoteOrigin`, `InsightType`), and storage methods already exist in the frozen `mnemo-core` package. No modifications to `mnemo-core`, `plugins/`, or ADRs 0001–0051 are required.

---

## 2. Frozen Core Contract Inspection

### 2.1 Domain Models (`mnemo/models/notebook.py`)
- **`TurnRole`**: `USER = "user"`, `ASSISTANT = "assistant"`.
- **`NoteOrigin`**: `USER = "user"`, `GENERATED = "generated"`.
- **`InsightType`**: `KEY_FACT = "key_fact"`, `CLAIM = "claim"`, `ENTITY = "entity"`, `SUMMARY = "summary"`.
- **`Turn`**: `turn_id: UUID`, `session_id: UUID`, `sequence: int`, `role: TurnRole`, `content: str`, `created_at: datetime`, `metadata: FrozenMetadata`.
- **`Session`**: `session_id: UUID`, `notebook_id: UUID`, `created_at: datetime`, `updated_at: datetime`, `title: str | None`, `turns: tuple[Turn, ...]`, `metadata: FrozenMetadata`.
- **`Citation`**: `citation_id: UUID`, `turn_id: UUID`, `source_number: int`, `chunk_id: str`, `document_id: UUID`, `version_id: UUID`, `document_title: str`, `verbatim_quote: str`, `created_at: datetime`, `page_number: int | None`, `heading_path: tuple[str, ...]`.
- **`Note`**: `note_id: UUID`, `notebook_id: UUID`, `title: str | None`, `content: str`, `origin: NoteOrigin`, `created_at: datetime`, `updated_at: datetime`, `metadata: FrozenMetadata`.
- **`Insight`**: `insight_id: UUID`, `notebook_id: UUID`, `source_id: UUID`, `type: InsightType`, `content: str`, `created_at: datetime`, `confidence: float | None`, `metadata: FrozenMetadata`.

### 2.2 Storage Facade (`StorageInterfaceV1`)
The frozen storage facade already exposes complete async methods for all required operations:
- `upsert_session(session: Session) -> None`
- `get_session(session_id: UUID) -> Session | None`
- `list_sessions(notebook_id: UUID, limit: int, cursor: str | None) -> Page[Session]`
- `append_turn(session_id: UUID, turn: Turn) -> None`
- `list_turns(session_id: UUID, after_turn_id: UUID | None, limit: int) -> Page[Turn]`
- `get_citations_for_turn(turn_id: UUID) -> tuple[Citation, ...]`
- `delete_session(session_id: UUID) -> bool`
- `upsert_note(note: Note) -> None`
- `get_note(note_id: UUID) -> Note | None`
- `delete_note(note_id: UUID) -> bool`
- `list_notes(notebook_id: UUID, limit: int, cursor: str | None) -> Page[Note]`
- `upsert_insight(insight: Insight) -> None`
- `get_insight(insight_id: UUID) -> Insight | None`
- `delete_insight(insight_id: UUID) -> bool`
- `list_insights(notebook_id: UUID, limit: int, cursor: str | None) -> Page[Insight]`

All storage methods are implemented and tested in `SQLiteStore` and `CompositeStorage`.

---

## 3. Explicit Endpoint Call Chains

### 3.1 Sessions Call Chains
1. **`GET /v1/notebooks/{notebook_id}/sessions`**
   ```
   HTTP GET ?limit=50&cursor=...
     ↓
   Validate notebook_id exists (404 if missing)
   Validate cursor UUID format (422 if invalid)
     ↓
   SessionService.list_sessions(notebook_id, limit, cursor)
     ↓
   engine.storage.list_sessions(notebook_id, limit, cursor)
     ↓
   PageResponse[SessionSummaryResponse] (200 OK)
   ```

2. **`POST /v1/notebooks/{notebook_id}/sessions`**
   ```
   HTTP POST CreateSessionRequest
     ↓
   Validate notebook_id exists (404 if missing)
     ↓
   SessionService.create_session(notebook_id, request)
     ↓
   Construct Session(session_id=uuid4(), notebook_id=notebook_id, created_at=now, updated_at=now, ...)
   engine.storage.upsert_session(session)
     ↓
   SessionSummaryResponse (201 Created)
   ```

3. **`GET /v1/notebooks/{notebook_id}/sessions/{session_id}`**
   ```
   HTTP GET /v1/notebooks/{notebook_id}/sessions/{session_id}
     ↓
   Validate notebook_id exists (404 if missing)
     ↓
   SessionService.get_session(notebook_id, session_id)
     ↓
   session = engine.storage.get_session(session_id)
   Verify session is not None and session.notebook_id == notebook_id (404 if mismatch/missing)
     ↓
   For each turn in session.turns:
     citations = engine.storage.get_citations_for_turn(turn.turn_id)
     ↓
   SessionDetailResponse with turns and citations (200 OK)
   ```

4. **`POST /v1/notebooks/{notebook_id}/sessions/{session_id}/turns`**
   ```
   HTTP POST CreateTurnRequest
     ↓
   Validate notebook_id exists (404 if missing)
     ↓
   SessionService.append_turn(notebook_id, session_id, request)
     ↓
   session = engine.storage.get_session(session_id)
   Verify session is not None and session.notebook_id == notebook_id (404 if mismatch/missing)
     ↓
   next_sequence = len(session.turns)
   Construct Turn(turn_id=uuid4(), session_id=session_id, sequence=next_sequence, ...)
   engine.storage.append_turn(session_id, turn)
   engine.storage.upsert_session(replace(session, updated_at=now, turns=(*session.turns, turn)))
     ↓
   TurnResponse (201 Created)
   ```

5. **`DELETE /v1/notebooks/{notebook_id}/sessions/{session_id}`**
   ```
   HTTP DELETE /v1/notebooks/{notebook_id}/sessions/{session_id}
     ↓
   Validate notebook_id exists (404 if missing)
     ↓
   SessionService.delete_session(notebook_id, session_id)
     ↓
   session = engine.storage.get_session(session_id)
   Verify session is not None and session.notebook_id == notebook_id (404 if mismatch/missing)
     ↓
   engine.storage.delete_session(session_id)
     ↓
   204 No Content
   ```

### 3.2 Notes Call Chains
1. **`GET /v1/notebooks/{notebook_id}/notes`**
   ```
   HTTP GET ?limit=50&cursor=...
     ↓
   Validate notebook_id exists (404 if missing)
   Validate cursor UUID format (422 if invalid)
     ↓
   NoteService.list_notes(notebook_id, limit, cursor)
     ↓
   engine.storage.list_notes(notebook_id, limit, cursor)
     ↓
   PageResponse[NoteResponse] (200 OK)
   ```

2. **`POST /v1/notebooks/{notebook_id}/notes`**
   ```
   HTTP POST CreateNoteRequest
     ↓
   Validate notebook_id exists (404 if missing)
     ↓
   NoteService.create_note(notebook_id, request)
     ↓
   Construct Note(note_id=uuid4(), notebook_id=notebook_id, created_at=now, updated_at=now, ...)
   engine.storage.upsert_note(note)
     ↓
   NoteResponse (201 Created)
   ```

3. **`PATCH /v1/notebooks/{notebook_id}/notes/{note_id}`**
   ```
   HTTP PATCH UpdateNoteRequest
     ↓
   Validate at least one field is provided (422 if empty)
   Validate notebook_id exists (404 if missing)
     ↓
   NoteService.update_note(notebook_id, note_id, request)
     ↓
   note = engine.storage.get_note(note_id)
   Verify note is not None and note.notebook_id == notebook_id (404 if mismatch/missing)
     ↓
   Construct updated Note with updated_at=now
   engine.storage.upsert_note(updated_note)
     ↓
   NoteResponse (200 OK)
   ```

4. **`DELETE /v1/notebooks/{notebook_id}/notes/{note_id}`**
   ```
   HTTP DELETE /v1/notebooks/{notebook_id}/notes/{note_id}
     ↓
   Validate notebook_id exists (404 if missing)
     ↓
   NoteService.delete_note(notebook_id, note_id)
     ↓
   note = engine.storage.get_note(note_id)
   Verify note is not None and note.notebook_id == notebook_id (404 if mismatch/missing)
     ↓
   engine.storage.delete_note(note_id)
     ↓
   204 No Content
   ```

### 3.3 Insights Call Chains
1. **`GET /v1/notebooks/{notebook_id}/insights`**
   ```
   HTTP GET ?limit=50&cursor=...&type=...
     ↓
   Validate notebook_id exists (404 if missing)
   Validate cursor UUID format (422 if invalid)
     ↓
   InsightService.list_insights(notebook_id, limit, cursor, type_filter)
     ↓
   engine.storage.list_insights(notebook_id, limit, cursor)
   (Apply in-memory type filtering if type_filter is supplied)
     ↓
   PageResponse[InsightResponse] (200 OK)
   ```

2. **`POST /v1/notebooks/{notebook_id}/insights/generate`**
   ```
   HTTP POST /v1/notebooks/{notebook_id}/insights/generate
     ↓
   Validate notebook_id exists (404 if missing)
     ↓
   InsightService.generate_insights(notebook_id)
     ↓
   Raises HTTPException(status_code=501, detail="Insight generation pipeline is scheduled for Phase 10")
   or returns 501 Not Implemented envelope.
   ```

---

## 4. Contradiction & Scope Analysis

### Contradiction 1: Insight Generation Pipeline
- **Roadmap Text:** "Insights endpoints: List + generate"
- **Architecture §4.3 & Roadmap Phase 10:** Background workers, job queue polling, and multi-stage insight extraction (Stages 9A–9D) are scheduled for Phase 10 (Module 10.1+). `mnemo-core` in Phases 0–6 contains no insight extraction pipeline.
- **Resolution:** As established by ADR-0050 Decision 4 for notebook summaries, `mnemo-server` must not build speculative background job runners or hallucinate LLM extraction pipelines. `POST /v1/notebooks/{id}/insights/generate` explicitly returns `501 Not Implemented` (`http.501`) explaining that automated insight extraction is a Phase 10 feature.

### Contradiction 2: Turn CRUD vs Append-Only Invariant
- **Architecture §5.1:** Defines `POST /v1/notebooks/{id}/sessions/{sid}/turns`.
- **Domain Invariant:** Conversational turns are contiguous, non-decreasing in timestamps, and immutable once stored.
- **Resolution:** The server implements `POST /turns` (append-only) and returns turns within `GET /sessions/{sid}`. No arbitrary turn deletion or modification endpoints are exposed, preserving conversational sequence integrity.

---

## 5. Security & Ownership Validation Rules

1. **Strict Scoping (`/v1/notebooks/{notebook_id}/...`):**
   - Every operation first verifies that `notebook_id` exists in storage (`404 Not Found` if missing).
   - For single-resource access (`sessions/{sid}`, `notes/{nid}`), the service verifies that the resource's `notebook_id` matches the path `notebook_id`.
   - If the resource exists but belongs to a different notebook, the endpoint returns `404 Not Found` (`contract.not_found`), completely preventing IDOR and resource enumeration attacks.
2. **Payload Protection:**
   - All Pydantic request models enforce `extra="forbid"`.
   - Title and content fields are whitespace-stripped and validated for non-emptiness where required.
   - Cursors are validated as UUIDs before hitting the storage layer (`422 Unprocessable Entity` if malformed).
