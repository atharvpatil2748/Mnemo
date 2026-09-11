# Full Multilingual V2 Index Build Report

Status: **V2 INDEX BUILD INCOMPLETE — READY NOT GRANTED**

Remediation status (2026-09-01): the blockers recorded by this historical build
attempt are resolved by `V2_NARROW_CONTRACT_REMEDIATION_REPORT.md`. The old hashes
and generation IDs below remain preserved as evidence of the failed preflight and
must not be used for a future build. Current governed identities live in
`V2_CONFIGURATION_PACKAGE.md` and the machine-readable manifests.

This report records the controlled `BUILDABLE -> READY` attempt authorized on
2026-09-01. The attempt stopped during mandatory pre-write validation. No V2
database, generation, vector, projection, alias, benchmark, or runtime exposure
was created.

## 1. Build identity

- Requested run: `build-20260831-01`
- Manifest run ID: `0b04f05c-a3d5-5879-b878-cd5f8e84ff2f`
- Build manifest digest: `ab2bf10b33125e276e1e7b66a7bd593474b9eba72264225f21eda08d1aa90316`
- Storage manifest digest: `88347f021e49ae60dd1a7a271127593a9c8d626aaf6bf168c7ac65b2379b3ade`
- Stop phase: mandatory manifest/provider identity reconciliation, before target creation

## 2. Database target

- Authorized target path:
  `scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db`
- Preflight target absent: **PASS**
- Preflight WAL absent: **PASS**
- Preflight SHM absent: **PASS**
- Target created: **NO**
- Isolation validation: **PASS**

The storage manifest still says `database_creation_authorized=false`, while the
build manifest says `BUILD_AUTHORIZED_FOR_NEXT_PHASE_ONLY` and the current human
instruction authorizes this phase. A manifest-consuming operator needs a typed,
machine-readable phase authorization or a governed storage-manifest amendment;
it must not infer this override.

## 3. Source corpus identity and hash

- Governed source corpus digest:
  `e086e48dda72b9bc38f6cb4d4f68a60bc5af7dfa38b47b49659fc3312a2efd9b`
- Governed source database SHA-256:
  `18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d`
- Golden Dataset pre/post tree comparison: **IDENTICAL**
- Corpus files read for validation only; no corpus file was written.

## 4. Configuration fingerprint

- Profile fingerprint:
  `51eb57f1f252d4e3e771668be8a70316303ede40c97cf0d3d25f7d20ed728034`
- V2 model-profile binding digest:
  `de9e17be7b517d50fd89a29c758de6630c51c204d14b23af69961e5d7a4b0156`
- Configuration acceptance: **BLOCKED** by the vector-space mismatch in section 6.

## 5. Provider, model, and tokenizer identities

The configured identities were parsed without loading either model:

- Embedder: `BAAI/bge-m3`
- Embedder revision: `5617a9f61b028005a4858fdac845db406aefb181`
- Embedder dimensions: `1024`
- Embedder metric/normalization: `cosine` / `l2`
- Embedder preprocessing digest:
  `41a8b2efb281c506065b05e5abe0ebf88df3847c017184733b2de180968a073e`
- Reranker: `BAAI/bge-reranker-v2-m3`
- Reranker revision: `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`
- Models initialized in this attempt: **NO**
- Network access/downloads: **NO**

## 6. Blocking vector-space identity defect

The approved build manifest binds:

`d13ddb899ec69f9534b271462a647ddd4b0e7428194ef62e3f44d475c70c8168`

The actual `MultilingualEmbeddingProfile.vector_space` constructed by the
configured BGE-M3 adapter for governed embedding generation
`297fb7af-ebcd-5ab6-898c-a2b49198b8f8` is:

`f28e49180f6ffa32240b43a7dabd96b2b23f90e98beff256bde8fb2b92919f9e`

These values are unequal. The mismatch is deterministic and was reproduced
without model initialization. The provider vector-space identity includes its
actual profile fields, including the embedding generation identity, whereas the
governed manifest carries a different profile-level digest.

Production enforcement is explicit:

- `MultilingualEmbeddingProfile.vector_space` derives the persisted vector-space identity.
- `MultilingualVectorGenerationBuilderV2.build` rejects every embedding whose
  persisted profile vector space differs from its configured
  `vector_space_identity`.

Continuing would therefore either fail the vector generation after expensive
embedding work or require weakening vector-space isolation. Both are forbidden.

Required resolution:

1. Freeze one canonical semantic meaning for `vector_space_identity`.
2. Make `V2_MODEL_PROFILE_BINDING.json`, the build manifest, generation
   fingerprints, provider-created `MultilingualEmbeddingProfile`, storage rows,
   retrieval filters, and vector-generation validation derive the exact same
   value.
3. Regenerate the four deterministic generation specifications after that
   correction; do not hand-edit generation IDs.
4. Add a pre-inference test asserting manifest identity equals provider profile
   identity for the exact governed generation.
5. Revalidate all proposal JSON digests and cross-references.

## 7. Corpus counts

The governed census remains available and unchanged:

- Documents: `44`
- Versions: `44`
- Canonical chunks: `2,658`
- OCR regions: `402`
- Vision derivations: `463`
- Total evidence records: `3,523`

No ingestion was run, so these are pre-build governed counts, not newly persisted
V2 build results.

## 8. Vision source/representation hash validation

A suspected issue was investigated and resolved as non-blocking:

- Vision rows checked: `463`
- Blank rendered semantic texts: `0`
- Complete structured-result hash equal to rendered semantic-text hash: `0/463`

This difference is intentional. `LanguageEvidenceReferenceV3.source_content_hash`
binds the complete immutable Vision result, while
`TextRepresentationReferenceV1.content_hash` binds its rendered semantic text.
Embedding and sparse contracts validate these independently. No census change is
required.

## 9. Language, script, representation, and transformations

No observations or transformations were persisted in this attempt. Governed
pre-build evidence remains:

- Language distribution: `hi=504`, `mr=10`, `und=3009`
- Explicit unresolved representation exclusions: `504`
- Legacy-font canonical exclusions: `502`
- PDF-encoding-anomaly exclusions: `2`
- Transformation output generated: `0`

## 10. Generation identities and coverage

The four manifest identities were validated syntactically but not built:

| Capability | Generation ID | Result |
|---|---|---|
| `representation_derivation_v2` | `81f673bb-665d-591a-b12b-472ff3e39b7c` | NOT_RUN |
| `language_text_v2` | `a7220adf-202c-536e-8e7c-c09d4d4c563f` | NOT_RUN |
| `multilingual_embedding_v2` | `297fb7af-ebcd-5ab6-898c-a2b49198b8f8` | NOT_RUN |
| `multilingual_vector_v2` | `3ed4de37-677e-5bd0-8a89-feca8e57413d` | NOT_RUN |

Generation checksums and coverage are **NOT AVAILABLE** because execution was
correctly stopped before generation creation.

## 11. Vector, provenance, and authorization integrity

- Embeddings created: `0`
- Vector rows created: `0`
- Sparse rows created: `0`
- Orphan audit: `NOT_RUN` (no V2 rows exist)
- Authorization enumeration audit: `NOT_RUN`
- Alias rows created/promoted: `0`

The build operator is still absent. A later remediation must implement an
operator that consumes governed manifests, validates authorization before source
enumeration, supports checkpoint/resume, and publishes generations to READY
without calling any alias-promotion method.

## 12. Recovery and idempotency

- Controlled interruption test: `NOT_RUN`
- Resume test: `NOT_RUN`
- Idempotent rerun test: `NOT_RUN`
- Clean-build checksum equivalence: `NOT_RUN`

These require the vector-space contract and machine-readable build authorization
to be corrected first.

## 13. Protected-state hash comparison

Snapshots:

- Before: `scratch/phase8_5_full_multilingual_v2/configuration_package/protected_state.index_build.before.json`
- After: `scratch/phase8_5_full_multilingual_v2/configuration_package/protected_state.index_build.after.json`

Comparison results:

- Golden Dataset tree: **IDENTICAL**
- `manuscript.pdf`: **IDENTICAL**
- Ramayana PDF: **IDENTICAL**
- Frozen DB and freeze manifest: **IDENTICAL**
- WP-10 DB: **IDENTICAL**
- V1 DB and captured sidecars: **IDENTICAL**
- BGE-M3 snapshot tree: **IDENTICAL**
- BGE reranker snapshot tree: **IDENTICAL**
- V2 target/WAL/SHM absent after attempt: **YES**

## 14. Tests and commands

Executed read-only checks:

1. Manifest/storage target identity and sidecar absence.
2. Exact four-generation manifest parsing.
3. Provider-profile construction without model loading.
4. Governed-vs-runtime vector-space digest comparison.
5. Read-only 463-row Vision source/semantic-hash census.
6. Before/after protected-state snapshots and equality comparison.

No model probe, corpus ingestion, embedding, index build, benchmark, activation,
or transport execution was run after the blocker was found.

## 15. READY gate result

- A. Corpus ingestion complete: **FAIL / NOT_RUN**
- B. Governed observations persisted: **FAIL / NOT_RUN**
- C. Exclusions persisted: **FAIL / NOT_RUN**
- D. Four generations complete: **FAIL / NOT_RUN**
- E. Dependency compatibility: **BLOCKED**
- F. Checksums valid: **NOT_RUN**
- G. Provenance complete: **NOT_RUN**
- H. Authorization valid: **NOT_RUN**
- I. Vector integrity valid: **BLOCKED**
- J. Vector-space isolation valid: **FAIL (identity mismatch)**
- K. Recovery/idempotency: **NOT_RUN**
- L. Configuration/build fingerprint match: **BLOCKED**
- M. Provider identities match: **PARTIAL; model/revision match, vector space does not**
- N. Protected artifacts unchanged: **PASS**
- O. Unauthorized writes absent: **PASS**
- P. Approved target only: **PASS; target remained absent**

**READY: BLOCKED**

## 16. Lifecycle and exact next action

The recorded pre-task lifecycle claimed `BUILDABLE: PASS`. Mandatory pre-write
validation disproved that claim for the current manifest/provider combination.
The evidence-derived state is therefore:

- DECLARED: PASS
- IMPLEMENTED: PASS
- CONFIGURED: PASS
- BUILDABLE: **BLOCKED**
- READY: **FALSE**
- ACTIVE: **FALSE**
- EXPOSED: **FALSE**
- EVALUATED: **FALSE**
- VERIFIED: **FALSE**
- CERTIFIED: **FALSE**

Exact next controlled action: perform a narrow configuration/implementation
contract remediation for canonical vector-space identity plus a typed build-phase
authorization artifact, regenerate dependent deterministic manifest identities,
and rerun pre-write validation. Index construction remains unauthorized until
that remediation restores `BUILDABLE: PASS`.
