# PROPOSED — REQUIRES HUMAN/GOVERNANCE APPROVAL
# Full Multilingual V2 Migration and Index Lifecycle

## 1. Protected baseline

The following are immutable inputs/evidence and are never purge targets:

- `goldenDataset/Phase 8.5 Evaluation Corpus/**`, including `manuscript.pdf`, the Ramayana PDF and filenames;
- frozen multimodal database, WAL/SHM, freeze manifest and active OCR/Vision/CLIP identities/outputs;
- current WP-10 evaluation database, generation records, qrels, raw rankings, reports and behavioral evidence;
- V1 text vectors/collection, canonical chunks, original assets and source hashes;
- model artifacts and immutable provider/model/revision records;
- historical governance reports, including contradictory or defective results.

No purge, copy, rebuild or activation is authorized by this proposal.

## 2. Side-by-side lifecycle

| Phase | Future action | Hard safety boundary | Exit evidence |
|---|---|---|---|
| A — finish V1 | Allow current EN/HI/MR evaluation to finish without interference | No restart, write, query substitution or capability change | Operator-declared completion |
| B — freeze V1 | Hash DB/files and retain corpus census, observations, representation census, generations, raw dense/fused/reranker/final ranks, exact reranker inputs, qrels, reports and capability snapshot | Preserve known Marathi/title-input/query-design defects as historical evidence | Immutable V1 manifest and evidence digests |
| C — approve V2 | Approve capability, representation, candidate and evaluation contracts | No data work | ADR/governance approval and exact profile identifiers |
| D — create isolation target | Create a new disposable V2 DB from an approved immutable source snapshot | Explicit path allowlist; target cannot resolve to protected DB or its WAL/SHM | Source/corpus digest, empty V2 generation census, DB identity |
| E — build observations | Create language, script and representation observations | Inputs read-only; provider/config identities fixed | Complete count/checksum/coverage manifests |
| F — build transforms | Create only approved normalized/transcoded/transliterated derived text | Authorization before source access; canonical text unchanged | Source→target lineage and deterministic transform checksum |
| G — build projections | Create multilingual embeddings, language-text sparse rows and multilingual-vector rows in the isolated DB | Exact vector space and source-generation binding | Complete generation checksums and coverage dimensions |
| H — activate isolated aliases | Atomically select compatible READY generations only in V2 runtime | No V1/frozen alias mutation | Alias audit and runtime/capability parity |
| I — evaluate | Run layered V2 evaluation and blind transport checks | Retain raw ranks, typed reranker input audits and failures; never rewrite corpus/qrels from results | Metrics, intervals, failure taxonomy and protected transcripts |
| J — promote or rollback | Governance decides exact capabilities | No automatic certification/promotion | ADR-0070/0074 evidence or withdrawal record |

## 3. V2 generation dependency graph

```text
immutable authorized evidence
  ├─ language_observation_v2
  ├─ script_observation_v1
  └─ representation_observation_v1
       └─ representation_transformation_v1 (optional, profile-specific)
            ├─ language_text_v2 sparse projection
            └─ multilingual_embedding_v2
                 └─ multilingual_vector_v2

all branches → capability_coverage_manifest_v1
```

Canonical Unicode evidence may bypass transformation. OCR and Vision text enter as derived representations with their existing occurrence/derivation lineage. Legacy-font encoded canonical evidence can feed an authorized transform, but its canonical value is neither replaced nor reclassified as transformed output.

## 4. Generation identity and activation

Identity/checksum input includes source snapshot/generation IDs; detector/script/representation/transform identities and configuration digests; exact provider/model/revision; query/document preprocessing; vector-space identity/dimension/metric/normalization; analyzer schema; admitted language/script/representation/operation set; and authorization/trust policy version.

Filesystem location is not model identity. A path-only change does not invalidate compatible data; an identity/revision/preprocessing/vector-space change does.

Activation requires `BUILDING → READY` only after complete expected counts, valid hashes, declared exclusions, source binding and dependency compatibility. One atomic alias selects the READY generation. BUILDING, FAILED, PARTIAL, STALE, SUPERSEDED and RETIRED generations are never served.

## 5. What may later be purged

Only explicitly named disposable **V2 derived/index state** may be removed after its manifest, hashes, run logs and raw evaluation outputs are retained and the resolved absolute target is verified inside the disposable V2 root:

- failed/superseded V2 observations;
- failed/superseded V2 representation derivations;
- failed/superseded V2 embeddings;
- failed/superseded V2 sparse/vector projection rows and aliases;
- transient V2 evaluation caches that are not governed evidence.

Current V1/WP-10 derived state is not “disposable V2” and is not purged. Source/canonical/multimodal data, qrels, raw rankings, candidate input audits, transcripts, manifests and governance evidence are never purged.

## 6. What V2 rebuilds

V2 rebuilds language/script/representation observations, approved transformations, multilingual embeddings, language-text sparse projections, multilingual-vector projections, coverage manifests and isolated aliases from immutable authorized inputs. It reuses OCR/Vision text as immutable evidence and does not regenerate or modify OCR/Vision/CLIP.

## 7. Rollback and recovery

- Before exposure: abandon the isolated V2 DB/generation; baseline unaffected.
- After isolated activation: disable V2 exposure and atomically select the prior READY V2 alias.
- After promoted exposure: stop advertising affected language-operation facts; retain canonical/V1 paths and prior generation.
- Crash/interruption: resume idempotently by deterministic IDs/hashes; never mark partial generations READY.
- Provider/transform failure: emit typed unavailable/failure state; no hidden fallback or fabricated language claim.
- Evaluation defect: withdraw affected evaluation-pack version to `UNVALIDATED`; do not alter runtime data or historical evidence.
## 8. Combined V2 readiness and atomic activation

`V2_ACTIVATION_READINESS_CONTRACT.proposed.json` is the normative evidence snapshot. The required alias set contains exactly one compatible READY generation for `representation_derivation_v2`, `language_text_v2`, `multilingual_embedding_v2`, and `multilingual_vector_v2`. A governed no-op representation generation is explicit when no transformation is required; absence is not silently treated as readiness.

Activation is one transaction over the complete alias-set record. The transaction compares the expected previous alias-set digest, promotes all four target identities, records the rollback target, and commits once. A mismatch or interruption commits nothing. Rollback similarly restores one retained, complete, checksum-valid, profile-compatible alias set in one transaction.

The following keep V2 non-READY: missing/incomplete/stale generation, provider revision mismatch, vector-space mismatch, incomplete language/script/representation coverage, invalid checksums or lineage, missing sparse projection, authorization incompatibility, or invalid rollback metadata. Missing transport parity or failed pre-exposure security evidence keeps V2 non-EXPOSED even when ACTIVE.

No V1 or frozen multimodal alias, generation, database, WAL/SHM, source evidence, OCR/Vision/CLIP output or evaluation evidence is purged by this migration.
