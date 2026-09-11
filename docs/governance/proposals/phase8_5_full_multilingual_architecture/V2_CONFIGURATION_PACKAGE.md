# Full Multilingual V2 Governed Configuration Package

Date: 2026-09-01  
Status: **CONFIGURED: PASS / BUILDABLE: PASS / BUILD NOT EXECUTED**

This package freezes inputs for a later isolated V2 build. It creates no database,
generation, index, alias, runtime exposure, benchmark, or certification claim.

## 1. Executive status

| State | Verdict | Evidence |
|---|---|---|
| DECLARED / IMPLEMENTED | PASS | Additive V2 contracts and implementation exist. |
| CONFIGURED | **PASS** | Exact profile/providers, observation policies, census, coverage limitation, storage and recovery manifests are digest-bound. |
| BUILDABLE | **PASS** | Providers are offline-ready and the complete eligible population, limitations and rollback rules are frozen. |
| READY / ACTIVE / EXPOSED | **FALSE** | No V2 database, generations, aliases or runtime selection exist. |
| EVALUATED / VERIFIED / CERTIFIED | **FALSE** | No V2 benchmark or post-build evidence exists. |

`BUILDABLE` authorizes only the next controlled build phase. It is not readiness.

## 2. Provider claims

`V2_PROVIDER_CAPABILITY_CLAIMS.json` (`bf4d25e88b982ce3f9f56f49b2e85cb20f4a8b0d6db8bc91c05644cb66133840`)
retains only the locally probed EN/HI/MR deployment cohort. It is not a core allowlist or
an exhaustive model-language claim. Further BCP-47/script combinations require governed
evidence but no source-code branch. Provider claims never promote lifecycle state.

## 3. Model profile and artifact evidence

The separate V2 profile is `config/model_profiles/full_multilingual_v2_profiles.toml`
(SHA-256 `b51b8591992429cf7631b917aeb6de8431a9f21d0cf696666d93c784dbaa2de3`).
`V2_MODEL_PROFILE_BINDING.json` (`df838955d082c694968c1abf879c78169c52f59e3395bfd9c4e709dcea144983`)
binds BGE-M3 revision `5617a9f61b028005a4858fdac845db406aefb181`, 1024-dimension
cosine/L2 vectors, and reranker revision `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`,
plus exact artifacts, tokenizers, preprocessing, policy, census and namespace identities.
Existing offline provider readiness remains PASS (digest
`93afe5e74a3eb3bbda126867f4198978f602fc7052a1b0562d3bea5f3d023b90`).
The canonical semantic vector-space identity is
`7dcba654e1c947145253ff65ef93e2b4ef1105cdf680b79218a446c79cc1a0d7`.
It is derived from canonical JSON over schema, provider, model, immutable revision,
dimension, normalization, distance metric and preprocessing digest. Generation IDs,
deployment profile labels and language/script capability claims remain governed provenance
but do not change mathematical vector compatibility.

## 4. Corpus census

`V2_CORPUS_LANGUAGE_SCRIPT_REPRESENTATION_CENSUS.json` (digest
`0cf872e3822494bb0fe9c4be7f0e2adb0009d3330ef96b2461a89c5192302446`)
and its Markdown companion bind every existing evidence item:

| Evidence | Count |
|---|---:|
| Documents / versions | 44 / 44 |
| Canonical chunks | 2,658 |
| OCR regions | 402 |
| Vision derivations | 463 |
| Total observations | **3,523** |

Language is `hi=504`, `mr=10`, `und=3009`; unknown is an explicit observation, not
missing coverage. Script hypotheses are `Deva=252`, `Grek=8`, `Latn=2908`, `Mlym=1`,
`Zzzz=578`. Representations are legacy-font=502, OCR=402, Vision=463, Unicode semantic=2154,
and PDF anomaly=2. Each record binds document/version/evidence identity, lineage and source
content hash. `manuscript.pdf` remains Marathi + Devanagari + Unicode. The Ramayana remains
Hindi + legacy representation; its script remains `Zzzz` until a governed transformation.

## 5. Detector policies

- `V2_LANGUAGE_OBSERVATION_POLICY.json`
  (`ef534bc678285becf3fc980d3c5abe0486a1eae9c317c0830a5244cf822f4c9d`) freezes
  metadata precedence, unpromoted provider claims, mixed language and `und` fallback.
- `V2_SCRIPT_DETECTOR_POLICY.json`
  (`98dc02ff2a38c9458e170b4c3f2cc94081dc6f177670aedd70daa52eaf541f41`) pins
  Unicode 17.0.0 Script data and ISO-15924 aliases, mixed/unknown policies, and forbids
  script-to-language inference.
- `V2_REPRESENTATION_DETECTOR_POLICY.json`
  (`2e9c43d2187101f288c14d3146ddd9f4feca72cbe0dad2dd7e44a3c947e7cb98`) freezes
  provenance/font/codepoint precedence, mixed/unknown states and forbids filename,
  language or script dispatch.

All validate under JSON Schema Draft 2020-12 using
`V2_BUILDABILITY_CONFIGURATION.schema.json`.

## 6. Legacy transformation decision

The authoritative source is established without pretending a runtime transform is ready.
SIL International's pinned `wsresources` commit
`2a39449d20420fe7259f9ce5231c347432840075` contains mapping v1.3, SHA-256
`3ff5befa3b026d6931e0f71f6ddff6d2a388a437755e7f09adff9791e873871c`, under MIT.
It is a conditional TECkit 010/011 source. Mnemo has no governed TECkit compiler/runtime,
compiled 010 artifact or adjudicated fixtures. The transform therefore remains
**UNRESOLVED** and fail-closed; no converter was invented or added.

`V2_GOVERNED_COVERAGE_LIMITATION_POLICY.json` retains all 44 documents and all census
observations, while excluding 504 non-semantic canonical chunks (502 legacy-font plus two
PDF encoding anomalies) only from `language_text_v2`, `multilingual_embedding_v2`, and
`multilingual_vector_v2` eligible sets. The exclusion identity digest is
`52eedf0e9b83ea4986dfbb48c18982a9266a2bec3a54dcc411c3dba614d85772`.
Completeness is only relative to that frozen eligible set and must disclose the limitation.

## 7. Ramayana status

V2 can build the untouched corpus while preserving the Ramayana as canonical legacy
evidence. It will create representation observations and retain all source identities and
hashes, but will create no Unicode-derived sparse/embedding/vector rows for those 502
legacy chunks. Separately authorized OCR/Vision evidence remains independently eligible.
The document is neither discarded nor silently reinterpreted. Legacy semantic retrieval
remains unverified and uncertified.

## 8. Storage and build manifests

`V2_DISPOSABLE_DATABASE_MANIFEST.json` (`0f34a97fd64301d86ccbe8d15dad08bb7442ff484a4e5166d8ec0056b2220ed7`)
binds the absent isolated target
`scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db`; its WAL/SHM are absent
and protected-path inequality is proven.

`V2_BUILD_RECOVERY_ROLLBACK_MANIFEST.json`
(`fdd46786cc78aa43ca47a6aca3091374d7bd37cdf24e5791017ee0c7a1275339`)
binds the source, profile/providers, detectors, eligibility limitation, four generation
specifications, checksums, resume/stale rules, atomic activation and rollback. Its state is
`TYPED_BUILD_AUTHORIZATION_REQUIRED`.

`V2_INDEX_BUILD_AUTHORIZATION.json`
(`7affc8a977bc6371dcd4bb99256394436927723cf0d8e90febde3b1b3706100f`)
is the sole machine-readable authorization for the next controlled build. It binds run,
target, profile, corpus, census, namespace, canonical vector space, storage manifest and
build manifest. Missing, false, stale or mismatched authorization fails closed before the
operator may enumerate source evidence or create the target.

The regenerated embedding generation is
`62243160-bed5-5064-a664-815984232e31`; the regenerated vector generation is
`2b26443e-bb99-5bf8-a4af-a01ba99af8ce`. Representation and sparse generation identities
remain unchanged because their identity inputs did not change. Nothing was executed here.

## 9. Tests

Focused remediation/V2 pytest: **57 passed** (only the pre-existing inaccessible pytest cache/temp cleanup
warning). Coverage includes schema/self-digests, Unicode mixed-script detection,
language/script/representation independence, census completeness, governed exclusion,
provider/profile identity, genericity, fail-closed transformation, reranker semantic-text
invariants, isolated storage, generation manifests and WP-14 authorization regressions.
Ruff: **PASS**. Strict mypy on the affected production modules: **PASS**. Compileall:
**PASS**. Draft-2020-12 JSON schema validation: **PASS**. `git diff --check`: **PASS**.
The repository-wide pytest run completed with **1,817 passed, 1 skipped, 8 failed**. The
eight failures are pre-existing baseline expectation drift (schema-v14 assertions against
the implemented schema v15, frozen Phase-1 export/import assumptions, and an old 10-tool
MCP assertion against the governed 14-tool surface); none is in the V2 closure or security
suite, and no unrelated test/code was altered to hide them.

## 10. Protected-state status

Before/after snapshots cover the Golden tree, named PDFs, frozen/WP-10/V1 databases,
freeze manifest, exact model trees, absent V2 target/sidecars and database row censuses.
The final before/after comparison is **IDENTICAL**:

- Golden tree: 44 files, digest
  `32c10db5bbdeddf4fd07aa37eeb04c234173e25293dcba3f9ac70b22e758330f`;
- `manuscript.pdf`: `31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085`;
- Ramayana PDF: `759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75`;
- frozen DB: `18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d`;
- WP-10 DB: `8ffbb367b35a313c8866e89e21f499aeef92153d5ef6e57d362208f0c05bca0d`;
- V1 DB: `861c0f1bc50894fadf2eba6088bcadf68083f3a7043e44d20a3583419c84b00f`;
- BGE-M3/reranker snapshot tree digests unchanged;
- V2 target, WAL and SHM absent; V2 generations in the frozen source DB: zero.

## 11. Gate determination

**CONFIGURED: PASS.** Provider, tokenizer/preprocessing, observation, coverage, census,
storage, typed build authorization and recovery inputs are explicit and digest-bound.

**BUILDABLE: PASS.** The unresolved legacy transform is not a dependency of the explicitly
limited first build. Its affected items are individually accounted for and fail-closed;
providers, eligible input population, isolated storage, typed authorization, recovery and
rollback are frozen. Manifest and provider vector-space identities are exactly equal.

Remaining non-blocking risks: legacy semantic transformation is unavailable; most
language observations truthfully remain `und`; actual generation coverage may still fail;
Decision-7 numeric gates and certification remain open.

## 12. Explicit non-executed operations

- Corpus ingestion/indexing/embedding: **NOT_RUN**
- V2 database/generation/alias creation: **NOT_RUN**
- Runtime/MCP/HTTP exposure: **NOT_RUN**
- Decision-7/quality benchmark: **NOT_RUN**
- Model inference in this closure phase: **NOT_RUN**
- READY/ACTIVE/EXPOSED/EVALUATED/VERIFIED/CERTIFIED promotion: **NOT_RUN**

## 13. Next phase authorization

**V2 BUILD AUTHORIZED FOR THE NEXT PHASE ONLY THROUGH THE TYPED AUTHORIZATION ARTIFACT.**

The next phase may create only the manifest-bound disposable database, ingest the unchanged
Golden Dataset into it, persist the governed observations, execute the four builders
against the frozen eligible set, and stop before alias promotion. It must verify protected
hashes first, reject a target mismatch, retain all 504 exclusion records, and produce
row-level coverage/checksum evidence. Indexing remains unexecuted in this package.
