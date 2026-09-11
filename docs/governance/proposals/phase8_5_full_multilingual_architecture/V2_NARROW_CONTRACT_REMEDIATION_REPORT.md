# Full Multilingual V2 Narrow Contract Remediation Report

Date: 2026-09-01  
Status: **CONFIGURED: PASS / BUILDABLE: PASS / READY: FALSE**

## 1. Scope and outcome

This remediation resolves only the two blockers recorded by
`V2_INDEX_BUILD_REPORT.md`: inconsistent semantic vector-space identity and the
absence of a typed build-phase authorization. No database, corpus row, embedding,
index, generation, alias, runtime exposure, evaluation, or model inference was
created or executed.

## 2. Vector-space root cause

The governance generator previously hashed provider, model, revision, dimensions,
normalization, metric, preprocessing and generation namespace. Runtime
`MultilingualEmbeddingProfile.vector_space` instead hashed provider, model,
revision, profile label, generation ID, dimension, normalization, metric,
preprocessing and language/script claim lists. Both were deterministic, but they
represented different concepts.

Generation identity, deployment labels and capability claims are provenance and
lifecycle facts; they do not change whether two vectors occupy the same mathematical
space. Including them also made identical model/preprocessing deployments appear
incompatible across generation rebuilds.

## 3. Canonical identity decision

Canonical contract: `mnemo.multilingual-vector-space/1`.

Canonical fields, serialized as UTF-8 JSON with keys sorted, no insignificant
whitespace, JSON booleans and exact field spelling:

1. `schema_version`
2. `provider`
3. `model`
4. `revision`
5. `dimension`
6. `normalized`
7. `distance_metric`
8. `preprocessing_digest`

The SHA-256 of that canonical serialization is the vector-space identity.
Generation ID, profile label, generation namespace, language claims, script claims,
hardware and operational lifecycle state are intentionally excluded. They remain
separately persisted and checked.

The single production function is
`mnemo.models.multilingual.multilingual_vector_space_identity`. Runtime provider
profiles delegate to it; deterministic governance tooling imports the same function.

Corrected canonical identity:

`7dcba654e1c947145253ff65ef93e2b4ef1105cdf680b79218a446c79cc1a0d7`

Manifest, model-profile binding, storage manifest and configured provider now
produce exactly this value.

## 4. Regenerated identities

No UUID or digest was hand-edited. `full_multilingual_v2_generation_plan` regenerated
dependent contracts from corrected canonical inputs.

| Capability | Previous generation | Regenerated generation | Result |
|---|---|---|---|
| `representation_derivation_v2` | `81f673bb-665d-591a-b12b-472ff3e39b7c` | same | Unaffected |
| `language_text_v2` | `a7220adf-202c-536e-8e7c-c09d4d4c563f` | same | Unaffected |
| `multilingual_embedding_v2` | `297fb7af-ebcd-5ab6-898c-a2b49198b8f8` | `62243160-bed5-5064-a664-815984232e31` | Regenerated |
| `multilingual_vector_v2` | `3ed4de37-677e-5bd0-8a89-feca8e57413d` | `2b26443e-bb99-5bf8-a4af-a01ba99af8ce` | Regenerated |

Regenerated artifact digests:

- Model binding: `df838955d082c694968c1abf879c78169c52f59e3395bfd9c4e709dcea144983`
- Storage manifest: `0f34a97fd64301d86ccbe8d15dad08bb7442ff484a4e5166d8ec0056b2220ed7`
- Build manifest: `fdd46786cc78aa43ca47a6aca3091374d7bd37cdf24e5791017ee0c7a1275339`
- Typed authorization: `7affc8a977bc6371dcd4bb99256394436927723cf0d8e90febde3b1b3706100f`

## 5. Typed build authorization

`V2BuildAuthorizationV1` and JSON schema
`V2_BUILD_AUTHORIZATION.schema.json` define the sole build authorization contract.
`V2_INDEX_BUILD_AUTHORIZATION.json` binds:

- deterministic authorization ID and artifact digest;
- run identity;
- bounded repository-relative disposable target;
- profile fingerprint;
- corpus and evidence-census digests;
- V2 generation namespace;
- canonical vector-space identity;
- exact storage- and build-manifest digests;
- human-governance authority and decision reference;
- READY-only build scope and affirmative state.

`validate_v2_build_authorization` runs before target use. It rejects absent/false
authorization, malformed/self-inconsistent artifacts, wrong run, target, profile,
corpus, census, namespace, vector space or manifest bindings, paths outside the V2
scratch namespace, protected database paths, and non-disposable targets. It grants
no V1 authority and contains no activation or exposure permission.

The storage manifest now declares
`typed_build_authorization_v1_required` rather than embedding a contradictory
boolean. The build manifest declares `TYPED_BUILD_AUTHORIZATION_REQUIRED`; the
separate typed artifact supplies the affirmative decision without a digest cycle.

## 6. Production files changed

- `mnemo-core/mnemo/models/multilingual.py`
- `mnemo-core/mnemo/models/__init__.py`
- `mnemo-core/mnemo/phase85/v2_build_authorization.py` (new)
- `mnemo-core/mnemo/phase85/__init__.py`

No V1 vector implementation, authorization semantics, CursorCodecV2, MCP contract,
database schema, ingestion pipeline or runtime exposure was changed.

## 7. Governance/configuration files changed or added

- `V2_MODEL_PROFILE_BINDING.json`
- `V2_DISPOSABLE_DATABASE_MANIFEST.json`
- `V2_BUILD_RECOVERY_ROLLBACK_MANIFEST.json`
- `V2_INDEX_BUILD_AUTHORIZATION.json` (new)
- `V2_BUILD_AUTHORIZATION.schema.json` (new)
- `V2_CONFIGURATION_PACKAGE.md`
- this report

The deterministic artifact generators under the configuration-package scratch
workspace were updated so the artifacts are reproducible; they are tooling, not
authoritative output.

## 8. Tests added or updated

- Canonical identity determinism and field sensitivity.
- Equivalent profile identity across generation IDs.
- Manifest/provider identity equality without model loading.
- Deterministic generation-fingerprint and UUID regeneration.
- Vector-generation rejection of incompatible vector spaces.
- Dense retrieval rejection of incompatible query vector spaces.
- Authorization-first retrieval call ordering.
- Missing/false/malformed/stale authorization rejection.
- Wrong target/run/profile/vector-space rejection.
- Protected/unbounded database-path rejection.
- V2-only READY-scoped authorization.
- Draft 2020-12 authorization schema and cross-artifact bindings.
- Existing multilingual profile regression updated to require generation-independent
  semantic vector compatibility and preprocessing-sensitive identity.

Focused V2/governance suite: **57 passed**. The first pytest invocation also had all
57 tests pass but returned nonzero solely because repository-wide coverage settings
cannot be satisfied by a focused subset; the governed rerun used `--no-cov` and passed.

## 9. Validation

- Ruff on affected production, tests and deterministic tooling: **PASS**
- Strict mypy on affected production modules: **PASS**
- Focused pytest: **PASS (57/57)**
- JSON Schema Draft 2020-12: **PASS**
- Artifact self-digests and cross-document bindings: **PASS**
- Canonical provider/manifest vector equality: **PASS**
- Compileall: **PASS**
- `git diff --check`: **PASS**

## 10. Protected-state verification

Before/after SHA-256 snapshots are retained under the V2 configuration-package
scratch directory. Golden Dataset, named PDFs, frozen database/manifest, WP-10 DB,
V1 DB/sidecars and exact BGE model snapshot trees compare identically. The V2 target,
WAL and SHM remain absent. Models were not loaded, downloaded or modified.

## 11. Lifecycle determination

- DECLARED: **PASS**
- IMPLEMENTED: **PASS**
- CONFIGURED: **PASS**
- BUILDABLE: **PASS**
- READY: **FALSE**
- ACTIVE: **FALSE**
- EXPOSED: **FALSE**
- EVALUATED: **FALSE**
- VERIFIED: **FALSE**
- CERTIFIED: **FALSE**

The next controlled build must validate the typed authorization before any source
enumeration or target creation and stop at READY. This report does not execute or
authorize activation, exposure, evaluation, verification or certification.
