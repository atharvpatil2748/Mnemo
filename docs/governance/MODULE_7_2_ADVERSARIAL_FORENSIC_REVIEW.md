# Module 7.2 — Second Adversarial Forensic Review

- **Review Date:** 2026-08-16
- **Baseline Commit:** `3ec5c33dfaa054141715506c881454cad061f8b1` (v0.21.2, Module 7.1 closed)
- **Purpose:** Evidence-verify four specific claims in `MODULE_7_2_ARCHITECTURAL_AUDIT.md` before freezing the REST contract.

---

## Investigation 1 — Summary Generation: Verify the Actual Capability

### 1.1 Roadmap Requirement (Verbatim)

Roadmap line 802:
```
GET /v1/notebooks/{id}/summary   "Trigger summary generation if stale"   Medium   7.1
```

Roadmap line 955 (Module 10.2):
```
Implement `GET /v1/notebooks/{id}/summary`   "Return cached or trigger fresh"   Medium   10.2a
```

### 1.2 Trace of Frozen Implementation

Search results across the entire repository:

| Item | Result |
|---|---|
| `generate_summary()` function | **NOT FOUND** in `mnemo-core` |
| `summarize_notebook()` function | **NOT FOUND** in `mnemo-core` |
| `insight_generation` interface | **NOT FOUND** in `mnemo-core` |
| Background job API | **NOT FOUND** in `mnemo-core` |
| Summary staleness detection | **NOT FOUND** in `mnemo-core` |
| `summary` field on `Notebook` model | **NOT FOUND** — `Notebook` has: `notebook_id`, `title`, `created_at`, `updated_at`, `description`, `metadata` |
| `ChunkType.SUMMARY` | **EXISTS** — but this is a _chunk-level classification_ used during document parsing (papers, books, resumes, code READMEs), not a notebook-level summary |
| `SUMMARY_SCHEMA` in `retrieval/context.py` | **EXISTS** — used internally by `ContextBuilder` to compress individual retrieval chunks for LLM context fitting, not notebook summaries |
| Notebook-level LLM summary orchestration | **NOT FOUND** in `KnowledgeEngine` |

### 1.3 Roadmap Architecture Contradiction Evidence

The roadmap has **two conflicting placements** of `GET /v1/notebooks/{id}/summary`:

**Module 7.2 table (line 802):**
```
Trigger summary generation if stale | Medium | 7.1
```

**Module 10.2 table (line 955):**
```
Implement `GET /v1/notebooks/{id}/summary` | Return cached or trigger fresh | Medium | 10.2a
```

Module 10.2 has explicit dependency chain:
- `10.1`: Background worker + job queue
- `10.2a`: Per-source summarization via synthesizer LLM
- `10.2b`: Notebook-level multi-source synthesis
- `10.2c`: Staleness detection (re-generate when new sources added)
- `10.2d`: `GET /v1/notebooks/{id}/summary`

**Conclusion:** The Module 7.2 row in the roadmap table is a PLACEHOLDER / FORWARD REFERENCE. The full implementation capability does not exist until Module 10.2, which depends on Module 10.1 (background worker) which itself is post-Phase 9.

### 1.4 Complete Attempted Call Chain

```
HTTP GET /v1/notebooks/{id}/summary
    → mnemo-server handler
    → engine.storage.get_notebook(notebook_id)      ← EXISTS
    → engine.llm("synthesizer")                     ← EXISTS
    → ??? summarize_notebook() or equivalent         ← DOES NOT EXIST
    → ??? stale detection (check updated_at vs ?)   ← NO FRESHNESS FIELD IN Notebook MODEL
    → ??? cached summary storage                    ← NO summary FIELD IN Notebook MODEL
    → ??? background job API                        ← DOES NOT EXIST
```

Every link after `get_notebook()` does not exist.

### 1.5 What Can Actually Be Served from Frozen Core Today

The server CAN return:
- The `Notebook` record itself (title, description, metadata, timestamps)
- `list_insights(notebook_id)` — stored `Insight` objects (from SQLite) which include `type` (KEY_FACT, CLAIM, ENTITY, SUMMARY), `content`, and `confidence`

**However**, these insights are only present if they were previously ingested via an LLM extraction pipeline that does not yet exist in any frozen module. In a freshly created notebook with no ingestion pipeline run, `list_insights()` will return an empty page.

### 1.6 Verdict

**SUMMARY_GENERATION: BLOCKED**

`GET /v1/notebooks/{id}/summary` with "trigger if stale" semantics **is NOT implementable in Module 7.2** using only the frozen core. The required capabilities (LLM summarization orchestration, staleness detection, background job system) are deferred to Module 10.2, which depends on Module 10.1 (background worker).

**Recommendation for Module 7.2:** Scope the endpoint to `GET /v1/notebooks/{id}/summary` as a **read-only** endpoint returning stored `Insight` objects of type `SUMMARY`. If no insights exist, return `{ "summaries": [], "generated_at": null }`. Do NOT attempt to trigger generation. The "trigger if stale" behavior is Module 10.2 work and must not be promised in 7.2.

This is a **scope correction**, not a frozen-core blocker. The endpoint can be implemented in 7.2 with read-only semantics.

---

## Investigation 2 — Graph Edges: Prove the Actual Edge Source

### 2.1 Graph Edge Storage Forensics

**Where edges are stored:** SurrealDB's `graph_edge` record type via `upsert_edge()`.

**SurrealQL schema (from `surrealdb.py:149-165`):**
```surql
UPSERT type::thing('graph_edge', $edge_id) CONTENT {
    in: type::thing('entity', $source_id),
    out: type::thing('entity', $target_id),
    relation: $relation,
    weight: $weight
};
```

Edge ID format: `{source_id}_{relation}_{target_id}` (string composite, not UUID).

### 2.2 What `StorageInterfaceV1` Exposes for Edges

| Method | Signature | Present? |
|---|---|---|
| `upsert_edge(edge: GraphEdge) -> None` | Write-only | ✅ Exists |
| `get_entity(entity_id: UUID) -> Entity \| None` | Returns one entity | ✅ Exists |
| `find_entities(canonical_name, entity_type, document_ids, limit)` | Returns `tuple[Entity, ...]` | ✅ Exists |
| `get_related_entities(entity_id, hops, relations, limit)` | Returns `tuple[Entity, ...]` only | ✅ Exists |
| `list_edges_for_document(document_id)` | **NOT PRESENT** | ❌ Missing |
| `list_edges_for_notebook(notebook_id)` | **NOT PRESENT** | ❌ Missing |
| `get_edge(source_id, target_id, relation)` | **NOT PRESENT** | ❌ Missing |
| `list_all_entities_for_document(document_id)` | **NOT PRESENT** | ❌ Missing |

### 2.3 What `get_related_entities()` Actually Returns

From `surrealdb.py:234-299`, the SurrealQL traversal query is:
```surql
SELECT VALUE ->graph_edge->entity FROM type::thing('entity', $id);
```

This traverses edges and returns **destination entities only** — not the edges themselves. The query uses `SELECT VALUE path FROM` which extracts the endpoint nodes via SurrealDB graph relations. The `relation`, `weight`, or intermediate `graph_edge` record fields are **NOT returned**.

### 2.4 Complete Graph Construction Algorithm for Module 7.2

**Proposed algorithm:**
```
GET /v1/notebooks/{id}/graph
    → storage.get_notebook(notebook_id)        → Notebook | None (404 if None)
    → storage.list_sources(notebook_id, ...)   → Page[Source]
    → for each source: document_ids = {source.document_id, ...}
    → for each document_id:
        → storage.find_entities("", None, (document_id,), limit=100)
            ← Returns tuple[Entity, ...] — NODES available
    → for each entity:
        → storage.get_related_entities(entity.entity_id, hops=1, relations=(), limit=50)
            ← Returns tuple[Entity, ...] — NEIGHBOR NODES, NOT the edges connecting them
```

**The edge problem:**
`get_related_entities()` returns neighboring `Entity` objects but does NOT return the `GraphEdge` records (i.e., `source_id`, `target_id`, `relation`, `weight`). To reconstruct a graph edge between entity A and entity B, the server would know:
- A and B are connected (because B appears in A's neighbors)
- But NOT which `relation` label connects them
- NOT the `weight` of the edge

**This means:**
A Module 7.2 graph endpoint cannot return complete, faithful `GraphEdge` objects using only the existing public `StorageInterfaceV1`. It would need to either:
1. Return nodes only (no edges) — which is technically implementable but misleading
2. Reconstruct placeholder edges (A→B, relation="related_to") — which **invents** relationship data not in the core
3. Use a Server-Side Adapter calling a direct SurrealQL query via `engine.storage` — however, `StorageInterfaceV1` does not expose arbitrary query execution, and the server must not call `engine.storage._sur` directly (layer violation)

### 2.5 SurrealDB Disabled Fallback

When `engine.storage.capabilities().supports_graph is False` (SurrealDB disabled, SQLite-only mode), **all** graph calls on `CompositeStorage` delegate to `SurrealDBStore` which raises `NotImplementedError`. The `CompositeStorage.upsert_entity`, `CompositeStorage.find_entities`, and `CompositeStorage.get_related_entities` all delegate directly to `self._sur` with no fallback guard:

```python
# composite.py:335-360
async def upsert_entity(self, entity: Entity) -> None:
    return await self._sur.upsert_entity(entity)   # raises NotImplementedError if disabled
async def find_entities(self, ...) -> tuple[Entity, ...]:
    return await self._sur.find_entities(...)       # raises NotImplementedError if disabled
async def get_related_entities(self, ...) -> tuple[Entity, ...]:
    return await self._sur.get_related_entities(...) # raises NotImplementedError if disabled
```

There is **no guard on `supports_graph`** inside `CompositeStorage`. The server must check `engine.storage.capabilities().supports_graph` before calling graph methods.

### 2.6 Verdict

**GRAPH_EDGES: SUPPORTED_WITH_SERVER_ADAPTER**

A complete node+edge graph is not retrievable through the existing `StorageInterfaceV1` because:
- No `list_edges_for_document` or equivalent method exists
- `get_related_entities` returns neighbor nodes, not edge records with `relation` and `weight`

**Two valid options for Module 7.2:**

**Option A (Recommended for 7.2):** Return nodes only, no edges. The graph response `{ "nodes": [...], "edges": [] }` is technically correct with the current API surface. Edge support deferred to a later module that adds `list_edges_for_document()` to `StorageInterfaceV1`.

**Option B (Server adapter):** The server calls `get_related_entities(hops=1)` for each entity node and then re-derives edge records by intersecting the neighborhood. This reconstructs `(source_id, target_id)` pairs but still cannot recover `relation` or `weight` without a frozen-core change.

**Critical constraint:** Neither option requires modifying frozen `mnemo-core`. Option A is the architecturally clean and honest choice for Module 7.2.

ADR-0050 must explicitly document this graph edge limitation as a known constraint for Module 7.2 and define which future module adds `list_edges_for_document()`.

---

## Investigation 3 — Concurrency: PATCH /v1/notebooks/{id}

### 3.1 `upsert_notebook()` Transaction Analysis

From `sqlite.py:667-691`:
```python
async def upsert_notebook(self, notebook: Notebook) -> None:
    async with db.execute(
        """
        INSERT INTO notebooks (notebook_id, title, description, created_at, updated_at, metadata)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(notebook_id) DO UPDATE SET
            title=excluded.title,
            description=excluded.description,
            created_at=excluded.created_at,
            updated_at=excluded.updated_at,
            metadata=excluded.metadata
        """,
        (...),
    ):
        await db.commit()
```

Key observations:
1. Uses `INSERT … ON CONFLICT … DO UPDATE` (SQLite UPSERT) — **unconditional overwrite**
2. Does NOT use `_transaction()` (BEGIN IMMEDIATE) context manager
3. Does NOT check any version condition (`WHERE updated_at = expected_updated_at` or `WHERE version = expected_version`)
4. `Notebook` model has `updated_at` field but it is NOT used as an optimistic concurrency guard in the SQL

### 3.2 Constructed Race Condition

```
Timeline (simultaneous requests, single SQLite connection, WAL mode):

Client A:                               Client B:
GET /v1/notebooks/{id}                  GET /v1/notebooks/{id}
← Notebook(title="Original",           ← Notebook(title="Original",
   updated_at=T0)                          updated_at=T0)

PATCH body: {title: "Client A Title"}  PATCH body: {title: "Client B Title"}

Server A constructs:                    Server B constructs:
Notebook(title="Client A Title",        Notebook(title="Client B Title",
  created_at=T0, updated_at=T1)          created_at=T0, updated_at=T2)

storage.upsert_notebook(A) ─────────────────────────────────────────┐
                                                                      │ SQLite serializes
storage.upsert_notebook(B) ──────────────────────────────────────────┤ both writes
                                                                      │
                                                                      ↓
Result:
One of Client A or Client B wins — whichever commit arrives last.
The loser's update is silently discarded with a 200 OK response.
BOTH clients receive a 200 OK with their updated title.
The actual notebook contains only one title.
```

### 3.3 ETag / If-Match Check

**No ETag mechanism exists anywhere in the frozen core or Module 7.1.**

There is no:
- `version` field on `Notebook` model
- `etag` field on `Notebook` model
- `expected_updated_at` parameter on `upsert_notebook()`
- `If-Match` header handling in `mnemo-server`
- Version precondition SQL (`WHERE updated_at = ?`)

Compare with `delete_document()` in `sqlite.py:633-661`, which DOES have `expected_version_id: UUID | None` as an optional optimistic concurrency guard. **Notebooks do not have this**.

### 3.4 SQLite WAL Behavior

WAL mode serializes concurrent writes on the SQLite level — but this only guarantees **database integrity**, not **application-level lost-update prevention**. Two writes to the same row will both succeed atomically; the last one wins. This is classic **Last Write Wins (LWW)** behavior.

`PRAGMA busy_timeout` is set in `cache.py:18` and `cache.py:45` but is **NOT set** in `SQLiteStore.open()` (lines 302-315). Only `foreign_keys = ON` and `journal_mode = WAL` are set. This means a concurrent writer that cannot acquire the write lock will receive `SQLITE_BUSY` immediately (no wait), not after a timeout.

### 3.5 Verdict

**CONCURRENCY: LAST_WRITE_WINS (explicit)**

Module 7.2's `PATCH /v1/notebooks/{id}` will operate with Last Write Wins semantics. This is **not a bug** — it is a valid, well-understood concurrency model for single-user local-first deployments (Mnemo's primary use case per ADR-0003 and architecture spec). However, it must be **explicitly declared** rather than implied, and not be confused with a claimed optimistic concurrency guarantee.

**ADR-0050 must explicitly state:**
- PATCH uses Last Write Wins semantics
- No ETag / `If-Match` / `version` field exists or is required for Module 7.2
- Concurrent PATCH to the same notebook from multiple clients will silently overwrite (last commit wins)
- If future modules require optimistic concurrency, a new ADR will introduce version fields to `Notebook` — this requires a schema migration, not a frozen-core modification

**Additional finding:** `SQLiteStore.open()` does not set `busy_timeout`. Under concurrent writes, a waiting writer may fail immediately with `SQLITE_BUSY` rather than waiting 30 seconds as documented in the M6 governance artifacts. This should be documented as an existing limitation (not a new blocker), and not fixed during Module 7.2 (frozen core).

---

## Investigation 4 — Cursor Pagination: Forensic Verification

### 4.1 `list_notebooks()` Implementation (sqlite.py:724-756)

```python
async def list_notebooks(self, limit: int, cursor: str | None) -> Page[Notebook]:
    query = "SELECT notebook_id, ... FROM notebooks"
    params: list[Any] = []

    if cursor is not None:
        query += " WHERE notebook_id > ?"
        params.append(cursor)

    query += " ORDER BY notebook_id ASC LIMIT ?"
    params.append(limit + 1)

    ...
    has_next = len(rows) > limit
    page_rows = rows[:limit]
    ...
    next_cursor = str(page_rows[-1][0]) if has_next and page_rows else None
    return Page(items=tuple(items), next_cursor=next_cursor)
```

### 4.2 Cursor Forensics

| Property | Value | Verified? |
|---|---|---|
| **Cursor content** | Raw `notebook_id` UUID string (e.g., `"550e8400-e29b-41d4-a716-446655440000"`) | ✅ Line 755: `str(page_rows[-1][0])` |
| **Cursor encoding** | Plain UTF-8 string, no base64, no JSON wrapper, no HMAC signature | ✅ Confirmed |
| **Ordering field** | `notebook_id` UUID string, ascending (`ORDER BY notebook_id ASC`) | ✅ Line 735 |
| **Tie-breaking** | UUID primary key — globally unique, no ties possible | ✅ |
| **Opaque to clients** | ❌ **NOT opaque** — cursor is the raw UUID of the last item on the page. Clients can inspect and construct valid cursors manually. |
| **Cursor validation** | None — any non-empty string passed as `cursor` is passed directly to `WHERE notebook_id > ?`. An invalid string produces an empty result, not a 422 error. | ⚠️ |
| **Malformed cursor behavior** | Passes through to SQLite comparison. UUID strings sort lexicographically. A malformed cursor like `"zzz-invalid"` returns an empty result (no notebook_id sorts > "zzz..."). No error raised. | ⚠️ |
| **Expired/stale cursor** | No expiry — cursors are valid as long as the sorted order is stable (since ordering is by UUID, not insertion time, stale cursors remain valid). | ✅ Safe |
| **Mutation between pages** | Concurrent inserts may appear or be skipped; concurrent deletes may cause the cursor to point to a deleted record (produces empty next page, not an error). | ⚠️ Medium risk, acceptable for single-user use |
| **Maximum limit** | No maximum is enforced at the storage layer. A caller can request `limit=9999999` and the query runs. | ❌ Must be bounded at the server layer |
| **Minimum limit** | No minimum. `limit=0` returns empty `items`, `next_cursor` is `None`. | ⚠️ |
| **Keyset-based** | ✅ Yes — `WHERE notebook_id > ?` is a genuine keyset/seek pagination pattern, not OFFSET-based. |
| **Frozen in core** | ✅ Yes — `Page[T]` with `items: tuple[T, ...]` and `next_cursor: str | None` is frozen in `mnemo.interfaces.types`. |

### 4.3 REST Representation Safety

The proposed REST representation is:
```json
{
  "items": [...],
  "next_cursor": "550e8400-e29b-41d4-a716-446655440000",
  "limit": 50
}
```

**Issues requiring ADR-0050 decisions:**

1. **Cursor is NOT opaque:** The raw UUID cursor is guessable. ADR-0050 must decide whether to:
   - Keep the cursor transparent (acceptable for local-first) — simpler but exposes internal identity
   - Wrap it in a base64 envelope with type tag (e.g., `eyJ0eXBlIjoibm90ZWJvb2siLCAiY3Vyc29yIjoiVVVJRCJ9`) — more robust but adds complexity
   
2. **No cursor validation:** If a client sends a malformed cursor, the server should return `422 Unprocessable Entity`, not silently return an empty result.

3. **No max limit enforcement:** The server must clamp `limit` to a maximum (e.g., 100) via `Query(ge=1, le=100)` in FastAPI.

4. **Multiple list methods use the same pattern:** `list_notebooks`, `list_sources`, `list_notes`, `list_sessions`, `list_insights` all use the same cursor-keyset implementation. ADR-0050 must standardize the REST contract once for all of them.

### 4.4 Verdict

**PAGINATION: NEEDS_CONTRACT**

The underlying keyset pagination is technically sound and genuine (not offset-based). However:
- The cursor is not opaque (raw UUID)
- No server-layer cursor validation exists yet
- No max limit capping exists yet
- ADR-0050 must formalize the pagination contract for all notebook-scoped list endpoints

---

## 5. ADR-0050 Scope Review — Precise Decision Analysis

### 5.1 Decision 1: REST DTO Schema Standard

**Existing source of truth:** ADR-0049 establishes the error envelope schema but does NOT define response schemas for domain resources.

**Why existing ADRs are insufficient:** No ADR defines how `Notebook`, `Source`, `Page[Notebook]`, or `Entity` should be serialized to JSON at the HTTP boundary.

**Decision needed:** Yes — Pydantic DTO schemas for request/response objects, separated from frozen core dataclasses.

**Verdict: REQUIRED in ADR-0050.**

---

### 5.2 Decision 2: Pagination Contract

**Existing source of truth:** `Page[T]` with `items: tuple[T, ...]` and `next_cursor: str | None` is frozen in `mnemo.interfaces.types`. But its HTTP JSON representation, cursor opacity semantics, and max-limit policy are undefined.

**Why existing ADRs are insufficient:** ADR-0049 covers error envelopes; no ADR covers pagination.

**Decision needed:** Yes — `PageResponse[T]` envelope format, whether cursor is opaque, cursor validation behavior, and `limit` bounds.

**Verdict: REQUIRED in ADR-0050.**

---

### 5.3 Decision 3: Timeline Event Contract

**Existing source of truth:** None. The `GET /v1/notebooks/{id}/timeline` endpoint is listed in the roadmap but the timeline event data model is **entirely undefined** in frozen core. No `TimelineEvent` model exists. The roadmap explicitly places the full timeline implementation (backed by SurrealDB, generated by `timeline-gen` plugin) in Module 12.4.

**Why existing ADRs are insufficient:** No ADR defines timeline events at all.

**Decision needed:**
- For Module 7.2: Is the timeline endpoint in scope at all without `TimelineEvent` data?
- If yes: What is the minimal read-only timeline that can be assembled from frozen `Source.created_at` and `Note.created_at` and `Session.created_at` timestamps?
- If no: Should the endpoint be deferred to a later module?

**Verdict: REQUIRED in ADR-0050** — but only to define whether Module 7.2 implements a *synthetic* timestamp timeline (assembling sources/notes/sessions by `created_at`) or defers the endpoint entirely. This is a genuine architectural decision with no existing source of truth.

---

### 5.4 Decision 4: Graph DTO Representation

**Existing source of truth:** `Entity` and `GraphEdge` frozen dataclasses exist. But their HTTP JSON representation and the node/edge graph response structure are undefined.

**Why existing ADRs are insufficient:** No ADR defines the graph HTTP response schema.

**Decision needed:** Yes — `EntityGraphResponse` with `nodes: list[GraphNodeResponse]` and `edges: list[GraphEdgeResponse]`, and the explicit decision that Module 7.2 returns **nodes only** (edges deferred due to missing `list_edges_for_document()` in frozen core).

**Verdict: REQUIRED in ADR-0050.**

---

### 5.5 Decision 5: Summary Freshness / Generation Semantics

**Existing source of truth:** None. Module 7.2's "trigger if stale" summary behavior is architecturally blocked (no LLM summarization pipeline exists in frozen core).

**Why existing ADRs are insufficient:** No ADR defines summary staleness semantics.

**Decision needed:** Yes — ADR-0050 must formally declare that Module 7.2 implements `GET /v1/notebooks/{id}/summary` as **read-only** (returning stored `Insight` objects of type `SUMMARY`), and explicitly defer the "trigger if stale" generation behavior to Module 10.2.

**Verdict: REQUIRED in ADR-0050** — scope correction must be formally recorded.

---

### 5.6 Decision 6: Concurrency Semantics for PATCH

**Existing source of truth:** `upsert_notebook()` is an unconditional overwrite. No ETag, no version field, no version precondition SQL exists.

**Why existing ADRs are insufficient:** No ADR defines the concurrency model for notebook mutations.

**Decision needed:** Yes — ADR-0050 must explicitly declare Last Write Wins semantics for `PATCH /v1/notebooks/{id}` and define the future compatibility path for optimistic concurrency (which would require a schema migration via a new ADR, not a modification of the frozen `Notebook` model).

**Verdict: REQUIRED in ADR-0050.**

---

## 6. Final Verdicts

```
SUMMARY_GENERATION:
BLOCKED (for "trigger if stale" semantics)
PARTIAL (for read-only "return stored SUMMARY-type insights" semantics)
→ Endpoint is implementable in 7.2 with REDUCED SCOPE only.
  Full summary generation deferred to Module 10.2 (dependency: 10.1 background worker).

GRAPH_EDGES:
SUPPORTED_WITH_SERVER_ADAPTER
→ Nodes are retrievable from frozen core.
  Edges (relation, weight) are NOT retrievable without a new StorageInterfaceV1 method.
  Module 7.2 must return nodes-only graph.
  Edge support deferred to a future module that adds list_edges_for_document() to StorageInterfaceV1.
  This requires a NEW ADR (not 7.2 scope) when edges are to be added.

CONCURRENCY:
LAST_WRITE_WINS
→ upsert_notebook() is an unconditional overwrite with no version precondition.
  This is acceptable for single-user local-first deployment.
  ADR-0050 must explicitly state LWW semantics to prevent false assumptions.
  busy_timeout is NOT set in SQLiteStore.open() — SQLITE_BUSY under contention returns immediately.
  This is a pre-existing limitation (not introduced in Module 7.2). Not a blocker.

PAGINATION:
NEEDS_CONTRACT
→ Keyset pagination is technically sound and genuine.
  Cursor is raw UUID — not opaque.
  No cursor validation or max-limit cap exists at the storage layer.
  ADR-0050 must define: cursor opacity policy, malformed cursor response (422), max limit (<=100).

ADR_0050_REQUIRED:
YES

ADR_0050_SCOPE:
1. REST DTO schema standard (Pydantic DTOs separate from frozen core dataclasses)
2. Pagination contract (PageResponse[T] envelope, cursor opacity, cursor validation, limit bounds)
3. Timeline event contract (decide: synthetic timestamp timeline vs. deferral to Module 12.4)
4. Graph DTO contract (nodes-only for 7.2, edges explicitly deferred, list_edges_for_document() gap documented)
5. Summary freshness/generation semantics (read-only in 7.2, "trigger if stale" deferred to Module 10.2)
6. Concurrency semantics (PATCH = Last Write Wins, no ETag, no version precondition)

MODULE_7_2_STATUS:
GREEN WITH CONDITIONS (revised)
→ All conditions are now formally identified, evidence-backed, and resolvable via ADR-0050.
   No frozen-core modifications required.
   Implementation-blocking issues: 0.
   Scope corrections required: 2 (summary generation, graph edges).

FROZEN_PHASE_MODIFICATIONS_REQUIRED:
NO

IMPLEMENTATION_READY:
NO — pending ADR-0050 acceptance.

BLOCKING_ISSUES:
0

HIGH_RISKS:
0 (the original audit's HIGH/MEDIUM risk assessment is now confirmed accurate
   after tracing the actual code)

MEDIUM_RISKS:
3
  1. Summary endpoint scope must be explicitly narrowed before implementation
     to avoid building a non-functional "trigger if stale" stub.
  2. Graph endpoint must explicitly return nodes-only to avoid inventing edge data.
  3. SQLITE_BUSY under concurrent PATCH has no retry — if this becomes an issue
     in testing, busy_timeout must be set (but this requires frozen-core fix, 
     which should be documented as a known limitation, not worked around in the server).
```
