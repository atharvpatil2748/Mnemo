# Full Multilingual V2 Configuration and Buildability Preflight

Date: 2026-08-31

Status: controlled preflight complete; fail-closed blockers retained

Current lifecycle: **DECLARED / IMPLEMENTED**

This report is the repository-grounded preflight record for the first isolated Full
Multilingual V2 build. It does not authorize ingestion, embedding, index construction,
generation creation, alias activation, runtime exposure, evaluation, verification, or
certification.

## 1. Current lifecycle state

| State | Verdict | Evidence |
|---|---|---|
| DECLARED | PASS | The V2 contracts, interfaces, storage structures, retrieval application path, readiness projection, and capability projection exist. |
| IMPLEMENTED | PASS | The additive V2 implementation and focused tests exist; see `FULL_MULTILINGUAL_V2_IMPLEMENTATION_REPORT.md`. |
| CONFIGURED | **BLOCKED** | No selected V2 profile binds governed per-operation language claims, complete artifact identities, approved transformation profiles, and an isolated database target. |
| BUILDABLE | **BLOCKED** | Exact local snapshots are present, but model initialization/readiness was intentionally not run; the required legacy-representation transformation remains unconfigured. |
| READY | **FALSE** | No complete four-generation V2 set exists. |
| ACTIVE | **FALSE** | No V2 alias set exists or was promoted. |
| EXPOSED | **FALSE** | Runtime exposure is not selected and transport/security evidence is incomplete. |
| EVALUATED | **FALSE** | No V2 benchmark was run. |
| VERIFIED | **FALSE** | No post-build quality, live transport, or V2 security-verification evidence exists. |
| CERTIFIED | **FALSE** | Certification gates and numeric quality floors remain separately governed. |

Code presence, local artifact presence, and passing unit tests do not advance any later
state.

## 2. Provider inventory

| Provider | Model | Exact revision | Operation | Local artifact | Runtime readiness |
|---|---|---|---|---|---|
| `sentence-transformers` | `BAAI/bge-m3` | `5617a9f61b028005a4858fdac845db406aefb181` | document/query embedding | PASS | NOT_RUN |
| `sentence-transformers` | `BAAI/bge-reranker-v2-m3` | `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e` | candidate reranking | PASS | NOT_RUN |

Both adapters load exact snapshots with `local_files_only=True`, `trust_remote_code=False`,
and CPU execution. They fail closed on missing revisions, missing required files, malformed
dimensions/scores, or unavailable dependencies. No provider was initialized in this pass.

## 3. Provider evidence

| Field | BGE-M3 embedder | BGE reranker |
|---|---|---|
| Provider claim | Model card says multilingual and, for BGE-M3, “more than 100” languages | Model card says multilingual |
| Enumerated provider language list | **UNVERIFIED / REQUIRES_GOVERNANCE** | **UNVERIFIED / REQUIRES_GOVERNANCE** |
| Claim-source SHA-256 | `0b81ccf9134e5874d620a86e6905062ea999e779c34eb1a7e65eaeb7fe00e450` | `c887aa6dd2598f908bf0582ca7068cc816585c7a1b6a07df305b631ede0cb174` |
| Previously exercised languages | EN/HI/MR historical selection/evaluation evidence only | EN/HI/MR historical selection/evaluation evidence only |
| V2 evaluated/verified languages | none | none |
| Model architecture | XLM-RoBERTa, hidden size 1024 | XLM-RoBERTa sequence classification, hidden size 1024 |
| Tokenizer class | `XLMRobertaTokenizer` | `XLMRobertaTokenizer` |
| Tokenizer model ceiling | 8192 | 8192; governed reranker pair ceiling remains 256 |
| Provider state | artifact present; initialization NOT_RUN | artifact present; initialization NOT_RUN |

The model cards are retained evidence of `MODEL_SUPPORTED` only. They do not enumerate a
safe operation/language/script claim set and do not establish Mnemo configuration,
buildability, readiness, exposure, evaluation, verification, or certification. The legacy
`languages` and `scripts` arrays in `phase8_5_profiles.toml` remain V1/profile history and
are deliberately not projected as V2 provider claims.

## 4. Model artifact evidence

The operator-owned Hugging Face cache is present at
`D:/Mnemo/phase8.5.11-models/huggingface/hub`. No download or cache mutation occurred.

Artifact manifests were calculated read-only using
`mnemo-hf-snapshot-manifest-v1`: SHA-256 every resolved regular snapshot file, record its
relative filename and byte size, then SHA-256 canonical sorted compact JSON containing
algorithm, cache model directory, revision, and file records.

| Model | Files | Weight evidence | Artifact-manifest SHA-256 |
|---|---:|---|---|
| BGE-M3 | 10 | `pytorch_model.bin`, 2,271,145,830 bytes, SHA-256 `b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38` | `b6f5839f34a02b1160b77594ae7779055c91d143d567a65876069136d67a6aa0` |
| BGE reranker | 7 | `model.safetensors`, 2,271,071,852 bytes, SHA-256 `d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286` | `373ec5de24f82eba3f35a4bcf2e101dfcad6b398588449d6bae777224b7e99cc` |

Relevant metadata evidence:

- BGE-M3 `config.json`: `26159e7ad065073448460117eb24b7a4572f6f4e78eadff65dc0a11c052449fa`.
- BGE-M3 `tokenizer_config.json`: `a62b2b6784f990259fddef5f16388693a8043be4f69179e6a5257eeb3f9abac4`.
- Reranker `config.json`: `13dcd6c31d9fec9d1d8e158702072f62d7fa7d312a64b9fe057bec9a08cfe41a`.
- Reranker `tokenizer_config.json`: `7e4c1cc848840aeccdd763458c18dd525eb0f795c992e00ebe9c28554e7db2d4`.

These are observed artifact identities, not runtime loadability evidence. Before BUILDABLE,
an approved V2 profile must bind the exact artifact-manifest, tokenizer, preprocessing,
model revision, operation, and vector-space identities; then an authorized offline provider
probe must confirm loadability and output contracts.

## 5. Language capability model status

PASS for structure; BLOCKED for configured claims.

- `LanguageCode` remains BCP-47-compatible and is not restricted to EN/HI/MR.
- Provider claims are operation scoped and carry immutable claim-source digests.
- Legacy profile arrays do not grant V2 admission.
- Effective capability is projected from provider claim, implementation, configuration,
  runtime/generation state, exposure, evaluation, verification, and certification evidence.
- Provider claim alone never permits retrieval.

No defensible enumerated provider claim artifact is currently present. Governance must
approve either an exact enumerated claim source or a smaller deployment claim set supported
by explicit evidence. A broad `multilingual` marketing statement must not be expanded into
invented BCP-47 records.

## 6. Script capability status

PASS for structure; UNVERIFIED for deployment coverage.

Language and script are independent types and observations. The V2 modules contain no
`Devanagari => Hindi`, `Latin => English`, or filename/title language inference. Arbitrary
ISO-15924-compatible script identities, unknown script, and multiple hypotheses are
representable. Actual corpus script coverage has not been materialized into a governed V2
census in this pass.

The EN/HI/MR and Latin/Devanagari branches in the existing V1 detector/transliteration code
are retained historical/V1 behavior, not V2 admission logic.

## 7. Representation capability status

PASS for the generic contract; BLOCKED for complete corpus configuration.

The V2 representation vocabulary independently supports Unicode semantic text,
legacy-font encoded text, PDF encoding anomalies, OCR text, Vision-derived text,
transliteration, normalization, unknown representation, and future typed representations.
Canonical evidence is immutable; transforms create separately identified derived evidence
with input/output hashes, exact lineage, source generations, and authorization scope.

Read-only PDF inspection established:

- `manuscript.pdf` exposes genuine Unicode Devanagari text and embedded Unicode-capable
  fonts. It does not require a legacy-font substitution.
- `Valmiki Ramayana aur Ramakien Ek Tulnamatmak Adhyayan.pdf` embeds `Kruti Dev 010`
  variants and extracted legacy-encoded sequences such as `okYehfd jkek;.k`. This is a
  representation condition, not corpus absence and not a language inference.

No filename, title, or document-specific dispatch exists in the new V2 production modules.

## 8. Transformation readiness

**BLOCKED / REQUIRES_GOVERNANCE.**

The generic detector, registry, deterministic longest-match transformer, and authorized
pipeline exist. Registry selection uses only a typed representation observation and an
exact governed profile. Unknown, disabled, unready, unmatched, unchanged, blank, or failed
transformations fail closed. Canonical text is never rewritten.

No approved Kruti Dev or other legacy mapping, detector profile, mapping source identity,
mapping checksum, confidence policy, or validation fixture is present. None was invented.
For a complete full-corpus V2 build, governance must supply and approve:

1. representation detector identity/revision/configuration digest;
2. an authoritative mapping source and license/provenance;
3. the exact mapping artifact digest and deterministic unmapped-character policy;
4. source/target representation types and compatibility predicates;
5. positive, negative, ambiguous, and round-trip/semantic review fixtures;
6. approval criteria for multiple possible mappings and fail-closed selection;
7. a versioned `TransformationProfileV1` and ready registry entry.

If no mapping can be approved, governance must explicitly define the evidence as unresolved
and accept that complete representation coverage and READY cannot be claimed.

## 9. V2 model-profile status

**BLOCKED.** The existing selected profile is `phase8_5_local_v1`; it is not an approved
Full Multilingual V2 profile. A V2 profile structure is implementable with the current
component and provider-claim contracts, but the following governed values remain missing:

- a distinct V2 profile ID/version and operator selection;
- exact embedding/reranking artifact-manifest digests above;
- tokenizer identity/revision/configuration digests;
- query/document preprocessing identities;
- exact 1024-dimension, cosine, L2-normalized BGE-M3 vector-space identity;
- operation-scoped, language/script-specific provider claims with approved claim sources;
- transformation registry/profile bindings and required representation coverage;
- an isolated storage/environment binding.

The exact model and preprocessing values already frozen in code remain:

- BGE-M3 query `bge-m3-query-v1`, document `bge-m3-document-v1`, NFKC plus whitespace
  normalization, no invented instruction prefix, 1024 dimensions, cosine/L2, batch <=32,
  context <=8192.
- BGE reranker `bge-reranker-v2-m3-v1`, batch <=16, at most 200 candidates, deterministic
  audited pair length 256.

No new EN/HI/MR allowlist was added. No proposed profile was selected or written into
production configuration because its language claims and transformation bindings are not
yet defensible.

## 10. Disposable database readiness

**BLOCKED; target not created.**

`mnemo.toml` currently points at the existing `scratch/phase8_5_11/eval-20260825-02/mnemo.db`.
That existing database is not a permissible V2 build target. The frozen multimodal and
WP-10 databases are also explicitly prohibited.

Before build authorization, an operator must approve a new run-scoped target such as
`scratch/phase8_5_full_multilingual_v2/<run-id>/mnemo.db` and freeze a preflight manifest
that binds:

- resolved target path and a target/database UUID;
- `disposable=true` and explicit protected-path inequality checks;
- source corpus and frozen-evidence digests;
- selected V2 profile fingerprint and provider artifact identities;
- V2 vector-space identity;
- separate V2 generation and alias namespaces;
- rollback namespace and previous-valid-alias-set identity;
- initial assertion that the target and its WAL/SHM do not preexist;
- environment/host identity without credentials or secret paths in public evidence.

No directory or database was created, opened, migrated, ingested, or indexed in this pass.

## 11. Reranker invariant status

**PASS for code and focused tests; provider execution NOT_RUN.**

The V2 application uses `RerankerCandidateBuilderV1` and
`MultilingualRerankCandidateV3`. The builder resolves authorized evidence, validates exact
notebook/source/document/version/occurrence/derivation scope before and after resolution,
uses actual semantic evidence, rejects blank/title-only and scope-mismatched candidates,
and binds tokenizer/model/preprocessing/token/truncation/hash audit fields. Title metadata
is explicitly excluded. Stable output ordering uses score, input ordinal, then candidate
identity.

The V2 evaluator calls the same `EvidenceRetrievalApplicationService`; it cannot access a
private provider runtime or construct reranker inputs. The older V1 reranker protocol and
historical benchmark scripts remain untouched for compatibility/evidence preservation and
are not V2 paths. Repository call-site inspection found no V2 path that bypasses the shared
candidate builder. The historical `title: manuscript.pdf` defect is therefore structurally
excluded from V2.

## 12. Authorization status

**PASS for implemented preflight invariants; live V2 security verification pending.**

- Dense and sparse V2 candidate universes require exact pre-authorized V3 evidence
  references before enumeration/scoring.
- Source/document/version/occurrence/derivation identity is revalidated on returned rows.
- Candidate construction repeats scope/provenance checks.
- Unknown positional or unsupported scope fails closed.
- Derived representations inherit source scope; transformations cannot expand access.
- Existing central authorization and CursorCodecV2 semantics are unchanged.

Focused negative tests cover scope mismatch and WP-14 authorization behavior. Full live V2
cross-scope security verification is required before EXPOSED and was not run here.

## 13. Evaluation architecture status

**PASS for contracts; NOT_RUN for evaluation.**

The V2 evaluator distinguishes corpus, language, script, representation, transformation,
provider, embedding, generation/index, sparse, dense, fusion, candidate build, reranking,
authorization, provenance, transport, qrels, and metrics stages. Semantic-quality cases
must be grounded, use evidence-level qrels, and retain raw-ranking identity. Ungrounded
generic prompts are excluded from ranking metrics.

`CORPUS_ABSENT` is valid only with `presence_state=absent_proven` plus retained corpus,
source-census, and authorized-evidence-census digests. Empty retrieval, detector failure,
authorization filtering, or representation failure cannot be relabeled as corpus absence.
No statement equivalent to “No Marathi document exists” can be emitted by the V2 contract
without census proof.

No corpus-wide census, qrel pack, raw ranking, quality metric, threshold comparison, or
benchmark was produced in this pass.

## 14. MCP/HTTP parity status

**PASS for static contract tests; live transport evidence NOT_RUN.**

- Existing public MCP tool names are unchanged.
- `multilingual_text` is aligned across internal, HTTP, MCP JSON Schema,
  `structuredContent`, canonical JSON fallback, and capability vocabulary.
- HTTP/MCP and V2 evaluation terminate at the shared retrieval application service.
- Capability discovery projects the same runtime/readiness evidence and reports no V2
  languages unless records are actually active and available.
- Compiling contracts does not expose V2; `v2_exposed` remains false.

No live HTTP, stdio, or SSE V2 call was executed. Transport parity therefore remains
UNVERIFIED and cannot support EXPOSED.

## 15. Test results

Focused command (coverage add-ons disabled so a focused run is not misclassified by the
repository-wide 90% threshold):

```text
pytest -q -o addopts= \
  mnemo-core/tests/unit/test_full_multilingual_v2.py \
  mnemo-core/tests/unit/test_multilingual_stage1.py \
  mnemo-core/tests/unit/test_model_profiles.py \
  mnemo-core/tests/unit/test_phase85_runtime.py \
  mnemo-core/tests/unit/test_scope_authorization.py \
  mnemo-server/tests/test_capabilities_v2.py \
  mnemo-server/tests/test_mcp_tools.py \
  mnemo-server/tests/test_retrieval_v2.py \
  mnemo-server/tests/test_wp14_security.py
```

Result: **76 passed** in 12.83 seconds. One pre-existing pytest cache/temp cleanup permission
warning occurred after the recorded result and did not alter it.

An earlier focused invocation ran 45 passing tests but exited nonzero solely because the
repository-wide coverage fail-under was applied to a partial suite. It disclosed no test
failure. The corrected focused invocation above is the authoritative result.

Covered preflight contracts include provider identity and fake readiness, exact revision,
dimensions/normalization/batch ordering, independent language/script observations, generic
transformation/provenance/fail-closed behavior, V3 semantic candidate construction,
title-only and scope mismatch rejection, authorization-before-enumeration, corpus absence
census rule, evaluator/runtime parity, readiness/generation dependency validation, atomic
rollback binding, vector-space isolation, dynamic capability projection, MCP vocabulary,
retrieval application behavior, and WP-14 security regression.

Proposal JSON validation: **PASS**. All 8 proposal JSON documents validate as JSON Schema
Draft 2020-12 meta-schemas.

## 16. Remaining blockers

| Blocker | Status | Owner/evidence needed | Blocks |
|---|---|---|---|
| Governed enumerated provider claim artifact | REQUIRES_GOVERNANCE | Approved claim source and digest per operation/language/script | CONFIGURED |
| Approved V2 model profile | REQUIRES_GOVERNANCE | Bind exact revisions, artifact/tokenizer/preprocessing/vector identities and claims | CONFIGURED |
| Corpus representation census | BLOCKED | Authorized immutable census with language/script/representation kept independent | CONFIGURED / coverage planning |
| Legacy-font detector/mapping/profile | REQUIRES_GOVERNANCE | Verified generic mapping source, digest, fixtures, policy, registry entry | CONFIGURED / BUILDABLE |
| Isolated V2 storage binding | REQUIRES_GOVERNANCE | New disposable target manifest and protected-path proof | CONFIGURED |
| Real offline provider probe | NOT_RUN | Explicit later authorization to load exact local models and verify contracts | BUILDABLE |
| Four V2 generations and aliases | NOT_RUN | Later isolated build only | READY / ACTIVE |
| Live HTTP/stdio/SSE parity and V2 security gate | NOT_RUN | Later pre-exposure validation | EXPOSED |
| Governed qrels/metrics/threshold evidence | NOT_RUN / OPEN | Later evaluation and separate governance approval | EVALUATED / VERIFIED / CERTIFIED |

## 17. Exact evidence required to advance to BUILDABLE

The first isolated V2 build must not start until all of the following are retained and
approved:

1. A distinct selected V2 model profile containing the exact BGE-M3 and reranker revisions,
   observed artifact-manifest digests, tokenizer identities/digests, preprocessing
   identities, vector contract, and operation limits.
2. A governed provider-claim artifact with explicit BCP-47 language, optional independent
   ISO-15924 script, operation, source identity, and claim-source digest. Marketing wording
   alone is insufficient.
3. An authorized corpus/evidence census that independently records language, script, and
   representation and retains exact source/provenance hashes.
4. Approved generic representation detector and transformation profiles for every
   representation required for complete build coverage, especially the observed legacy
   Kruti Dev evidence; or an explicit governed unresolved/exclusion decision that prevents
   false completeness.
5. A new disposable V2 database/storage manifest proving path, database, profile,
   vector-space, generation namespace, alias namespace, rollback namespace, and protected
   artifact isolation.
6. An explicitly authorized offline-only provider initialization probe that proves both
   exact snapshots are loadable, BGE-M3 emits ordered finite L2-normalized 1024-dimensional
   vectors, and the reranker honors the audited 256-token pair contract without a V1
   fallback.
7. A deterministic build plan whose source-generation, configuration, coverage,
   provenance, authorization, checksum, interruption/recovery, and rollback identities are
   frozen before any write.

Once items 1-7 pass, CONFIGURED and BUILDABLE can be reassessed. They do not by themselves
authorize READY, ACTIVE, or EXPOSED.

## 18. Explicitly not executed and protected-state audit

Not executed:

- model import/initialization/inference: **NO**;
- network/model download or Ollama pull: **NO**;
- corpus ingestion: **NO**;
- V2 embedding/index build: **NO**;
- V2 generation creation: **NO**;
- V2 alias activation: **NO**;
- benchmark/evaluation: **NO**;
- live HTTP/stdio/SSE V2 execution: **NO**;
- production runtime V2 exposure: **NO**.

Protected post-preflight identities:

| Artifact | SHA-256 |
|---|---|
| Frozen multimodal DB | `18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d` |
| Frozen multimodal manifest | `17977efc87d3d95bb1e2e6e6c8025e78b63a4c3a0a301f98869b44724fef5a8f` |
| Current WP-10 DB | `8ffbb367b35a313c8866e89e21f499aeef92153d5ef6e57d362208f0c05bca0d` |
| Current configured V1 SQLite DB | `861c0f1bc50894fadf2eba6088bcadf68083f3a7043e44d20a3583419c84b00f` |
| Golden `manuscript.pdf` | `31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085` |
| Golden Ramayana comparison PDF | `759f2adbfd2fc1191ff8576401d1cbc34bbfefa79a573e8747c53d4c858af75` |

The 44-file Golden corpus produced
`bd7ed059cf63a16f1214bbb6e2f732408c29fc2c01c3c9ed4b91a0baa082a896`
under the explicitly recorded legacy composite algorithm: sort top-level files by name,
SHA-256 each file, then SHA-256 the concatenation of each UTF-8 filename and lowercase file
digest. This value is used only as this pass's before/after integrity comparator; it is not
silently substituted for a differently defined authoritative corpus-manifest digest.

The protected database WAL/SHM identities and timestamps were also recorded and rechecked;
none was opened or changed by this preflight. Golden Dataset, canonical text, frozen
multimodal evidence, current WP-10 evidence, V1 index/vector spaces, model artifacts,
CursorCodecV2, MCP tool names, and authorization semantics remain unchanged.

## Strict gate verdict

```text
CONFIGURED: BLOCKED
BUILDABLE: BLOCKED
READY: FALSE
ACTIVE: FALSE
EXPOSED: FALSE
EVALUATED: FALSE
VERIFIED: FALSE
CERTIFIED: FALSE
```

The exact governed inputs still required before Mnemo can safely build its first isolated
Full Multilingual V2 index are the seven evidence packages in section 17. Until they exist,
the correct repository state is fail-closed DECLARED / IMPLEMENTED.
