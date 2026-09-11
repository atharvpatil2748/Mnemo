# V2 Database Artifact Identity Contract

Status: GOVERNED ADDITIVE CONTRACT
Version: `mnemo.v2-database-artifact-identity/1`

## Canonical artifact

The governed database artifact is the immutable logical V2 build envelope, not the byte stream of the live SQLite file. Repository evidence requires this distinction because the same isolated SQLite file also contains mutable active-alias/lifecycle metadata. Hashing SQLite pages after activation would allow unrelated page order, WAL checkpointing, or lifecycle metadata to redefine the identity of an otherwise unchanged READY build.

The canonical envelope contains, in deterministic key order:

- schema version;
- persistent database UUID;
- normalized repository-relative target path;
- build-run UUID;
- corpus and census digests;
- profile and canonical vector-space fingerprints;
- build and storage manifest digests;
- exactly four capability-sorted generation envelopes.

Each generation envelope contains its capability, generation UUID, checksum, ordered source-generation UUIDs, provider identity, model identity including immutable revision when applicable, configuration digest, vector-space identity when applicable, and dimensions when applicable.

`database_identity` is lowercase hexadecimal SHA-256 over UTF-8 JSON serialized with sorted keys and compact separators. It excludes mutable aliases, timestamps, WAL/SHM state, SQLite page layout, and evaluation/runtime state. Any change to an immutable build binding produces a different identity.

## Persistence and verification

`V2_DATABASE_ARTIFACT_IDENTITY.json` is the governed persisted identity sidecar and is validated by `V2_DATABASE_ARTIFACT_IDENTITY.schema.json` under JSON Schema Draft 2020-12. Runtime verification opens the authorized database read-only/immutable and compares the sidecar to `v2_build_runs`, `index_generations`, `index_generation_sources`, and the persisted embedding vector-space value. It performs no database mutation.

The runtime identity and bounded authorization decision carry this SHA-256. A mismatched expected identity, build row, generation row, dependency, or persisted vector space fails closed.

## Vector-to-embedding generation relationship

The active vector and embedding generations remain distinct. The canonical relationship is the `index_generation_sources` entry whose `generation_id` is the vector generation, `source_kind` is `generation`, and `source_id` is the embedding generation. Resolution requires exactly that dependency and validates active-set membership, model/revision identity, vector-space identity, dimensions, checksums, configuration digests, database identity, and build run. Ordering, timestamps, UUID similarity, `latest`, and hard-coded IDs are forbidden.

## Compatibility

This contract adds V2 governance only. It does not alter V1 database identity, the built V2 database, generation contents, active aliases, corpus evidence, model artifacts, or public transport contracts.
