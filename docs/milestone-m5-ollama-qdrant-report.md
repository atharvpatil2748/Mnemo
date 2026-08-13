# M5 Ollama and Qdrant Verification

**Verdict:** PASS
**Executed:** 2026-08-13 06:08:38 UTC
**Input:** first 1,000 M4 chunks in deterministic source order

## Runtime preconditions

- Ollama endpoint: `http://127.0.0.1:11434`
- Configured and installed model: `nomic-embed-text`
- ADR-0018 startup hook: executed before provider resolution and dimension reads
- Discovered/configured dimensions: 768 / 768
- Qdrant: repository-pinned `qdrant/qdrant:v1.19.0`
- Isolated collection: `mnemo_m5_gita_20260813t060713393050z`
- Collection points before acceptance write: 0
- Collection vector size: 768, cosine distance

The executed production path was:

```text
Chunk
  → EmbedderModule
  → CachedEmbeddingProvider
  → OllamaEmbedder
  → local Ollama
  → CompositeStorage
  → QdrantStore
  → Qdrant
  → independent Qdrant read-back
```

No provider, cache, or vector-store mock was used.

## Embedding result

| Measurement | Result |
|---|---:|
| Requested chunks | 1,000 |
| Returned embedded chunks | 1,000 |
| Model | `nomic-embed-text` |
| Dimensions | 768 |
| Batch size | 50 |
| `EmbedderModule` concurrency | 4 |
| Logical Ollama embedding requests | 1,000 |
| Startup probe requests | 1 |
| First-run cache hits / misses | 0 / 1,000 |
| Cache rows after run | 1,000 |
| Embedding time | 27.280 s |
| Average wall latency per chunk | 27.280 ms |
| Throughput | 36.66 chunks/s |

Every vector was present, non-empty, finite, exactly 768 elements long, and
returned in the same order as the input chunks. All original chunk IDs,
document/version IDs, source spans, heading paths, text, and metadata were
preserved.

## Persistence and independent read-back

| Measurement | Result |
|---|---:|
| Qdrant upsert path | `CompositeStorage → QdrantStore` |
| Qdrant write time | 2.479 s |
| Requested points | 1,000 |
| Exact collection count | 1,000 |
| Points independently retrieved with vectors/payloads | 1,000 |
| Deterministic payload samples checked | 10 |
| Payload validation | PASS |

The read-back queried Qdrant independently rather than trusting the upsert
return. Sampled points matched `chunk_id`, `document_id`, `version_id`,
`source_span`, `heading_path`, payload presence, vector presence, and vector
dimension.

## Cache repeat acceptance

A deterministic 100-chunk subset was requested again using the original
unembedded Chunk values so `EmbedderModule` could exercise the cache path.

- Cache hits: 100
- Cache misses: 0
- Underlying Ollama requests: 0
- Repeat time: 0.618 s
- Returned vectors: equivalent to first-run vectors within `1e-6`
- Cache cardinality before/after repeat: unchanged at 1,000
- Keys: SHA-256 text digest plus model name, preserving model specificity

## Performance scope

The mandatory 1,000-chunk milestone passed. The roadmap's separate
10,000-chunk/5-minute benchmark was **not executed** because this corpus
produced 1,275 real chunks and the run did not duplicate or fabricate text.
That performance criterion remains unverified.

## Failures observed during verification

1. An initial harness cold-cache check used an async generator incorrectly and
   stopped before embeddings or writes. It was corrected and rerun.
2. A later run embedded all 1,000 chunks but `CompositeStorage` failed closed
   at SQLite's document foreign key because the harness had not registered the
   real Document/DocumentVersion record. No Qdrant points were written. The
   production registry step was added and the full pipeline rerun with a fresh
   cache and collection.

## Reproduction

```powershell
ollama list
docker compose -f docker/docker-compose.yml up -d --wait qdrant surrealdb
.venv\Scripts\python.exe scripts/verify_phase_4_5_milestones.py all
```

The opt-in pytest entrypoint is:

```powershell
$env:MNEMO_RUN_LIVE_MILESTONES='1'
.venv\Scripts\python.exe -m pytest mnemo-core/tests/integration/test_golden_phase_4_5_acceptance.py --no-cov
```

Machine-readable evidence is in
`docs/milestone-evidence/m5-ollama-qdrant.json`.
