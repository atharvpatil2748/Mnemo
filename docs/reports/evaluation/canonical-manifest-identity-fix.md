# Canonical manifest identity fix

Status: **CURRENT — PASS**

## Outcome

The retained Phase 8.5 and Phase 8.6 evaluation notebooks were repaired and validated without re-ingestion, re-chunking, re-embedding, OCR, Vision, or CLIP regeneration. Both stores are `READY`; the server-owned registry contains both aliases; real HTTP, MCP stdio, and MCP SSE validation passed with semantic identity parity.

## Defect and canonical contract

The reindex writer hashed JSON using Python's implicit `ensure_ascii=True`, while the registry validator used `ensure_ascii=False`. Unicode identity material in Phase 8.5 therefore produced different byte streams. The shared `mnemo.canonical-json-utf8/1` implementation now governs writer, validator, registry, and repair code:

- `ensure_ascii=False`
- `sort_keys=True`
- `separators=(",", ":")`
- UTF-8 encoding
- `allow_nan=False`
- no trailing newline in hashed bytes

Regression coverage includes ASCII, Hindi, Marathi, Unicode filenames, en/em dashes, combining characters, multilingual probes, nested objects, and reordered keys. The original `Coordinator Application 2026–27.pptx` case is reproduced explicitly.

## Governed retained-store repair

The dedicated `--repair-retained` operation cannot be combined with `--full`. Before rebinding a manifest it verifies source inventory, database SHA and prior evidence, SQLite integrity and foreign keys, document/version/source/chunk identity, FTS coverage, embedding coverage/model/revision/dimension/vector hashes/finiteness, multimodal coverage, duplicates, orphans, and provenance. It transitions through `VALIDATING` to transport-eligible `PUBLISHED`; transport validation alone transitions it to `READY`.

| Notebook | DB SHA before and after | Docs / versions / memberships | Chunks / FTS / BGE-M3 | Images / OCR / Vision / CLIP | Final manifest identity |
|---|---|---:|---:|---:|---|
| Phase 8.5 | `bc048cc15173acbd818b98786a3380a01f2263843a435708f6814c6de21a1d84` | 44 / 44 / 44 | 2,658 / 2,658 / 2,658 | 464 / 463 / 463 / 463 (one SVG policy exclusion) | `6b52d36fb5f3c60e7126a0236dfab52061e831a748b1da49b951f3228725f31a` |
| Phase 8.6 | `9a3521f8cefc74e2673592dbd207a7f5673dcfc05cebfdc18899d93be93307a2` | 24 / 24 / 24 | 5,843 / 5,843 / 5,843 | 161 / 161 / 161 / 161 | `8f4aeda7be411065f570fd798f3465b5076f78db06469c9f80d16424d325b1ed` |

Both databases report `integrity_check=ok`, zero foreign-key violations, zero identity duplicates, zero representation orphans, 1,024-dimensional finite BGE-M3 vectors, and valid stored vector hashes.

The rebuilt Phase 8.6 notebook intentionally contains 24 evaluation-source identities—not the historical 67-document union. Persisted oversized-structure metadata proves subdivision of three table-row groups, one Markdown-list group, and one Markdown-table group. Exact o200k token inspection found zero chunks above 1,024 tokens; the maximum is 1,023.

## Registry and transport validation

The registry remained empty during repair. Phase 8.5 validation-only then passed, followed by Phase 8.6 validation-only; only `READY` manifests were registered. Arbitrary client filesystem paths remain rejected.

For each notebook, actual HTTP requests returned 1, 5, and 10 results for requested `k` values 1, 5, and 10 while preserving the internal candidate pool of 50. MCP stdio and authenticated MCP SSE returned the same ordered document, version, and chunk identities as HTTP for the parity request.

- HTTP: PASS
- MCP stdio: PASS
- MCP SSE: PASS
- semantic identity parity: PASS
- authorization: `CentralAuthorizationServiceV1`
- shared application: `EvidenceRetrievalApplicationService`

## Protected state

The Phase 8.5 and Phase 8.6 database hashes are byte-identical before and after repair and transport validation. The production database remains `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`. No Ollama environment or model was changed.

Machine evidence: [`scratch/mnemo-canonical-json-digest-fix.json`](../../../scratch/mnemo-canonical-json-digest-fix.json).
