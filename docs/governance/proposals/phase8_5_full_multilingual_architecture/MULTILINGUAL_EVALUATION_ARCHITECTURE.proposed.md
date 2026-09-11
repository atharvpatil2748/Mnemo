# PROPOSED — REQUIRES HUMAN/GOVERNANCE APPROVAL
# Full Multilingual V2 Evaluation Architecture

## 1. Purpose

This design prevents a failure at one layer from being reported as a failure of another. It replaces neither ADR-0070 nor the approved Decision-7 metric structure; it adds the diagnostic and scalable cohort rules required by the EN/HI/MR investigation.

## 2. Mandatory per-case contract

Every governed semantic retrieval case records:

- case/manifest/corpus/qrels digests;
- natural-language query and query language/script/representation observations;
- target evidence language, topic or entity, and answerability;
- expected notebook/document/version and evidence/occurrence/derivation identity where applicable;
- relevant grades and provenance expectations;
- exact provider/profile/generation/vector-space identities;
- every dense/sparse candidate and score, fused rank, typed reranker candidate/input audit, reranker score and final rank;
- authorization/provenance/completeness outcome;
- latency/resource state and failure taxonomy code.

No filesystem path, secret, signing key, raw protected evidence outside the authorized transcript policy, or private evaluator hint is retained in public output.

## 3. Layered gates

| Layer | Proof | Failure examples |
|---|---|---|
| Corpus | Immutable source and authorized evidence census | `CORPUS_ABSENT` only with census proof |
| Language | Observation exists, detector/metadata identity and confidence retained | `CORPUS_PRESENT_UNDETECTED`, `CORPUS_PRESENT_WRONG_LANGUAGE` |
| Script | Independent ISO-15924 observation | `SCRIPT_UNRESOLVED` |
| Representation | Unicode/legacy/OCR/Vision/transform state identified | `REPRESENTATION_UNRESOLVED` |
| Transformation | Exact authorized transform output and lineage | `TRANSFORMATION_UNAVAILABLE`, `TRANSFORMATION_FAILED` |
| Embedding/index | Exact vector space, generation coverage and active alias | `EMBEDDING_*`, `INDEX_MISSING` |
| Retrieval | Raw dense/sparse candidates and scores retained | `DENSE_RETRIEVAL_FAILED` |
| Candidate build | Shared builder, actual semantic text, input hashes/truncation | `RERANKER_INPUT_INVALID` |
| Reranking | Same candidate identities, scores and stable ordering | `RERANKER_FAILED` |
| Authorization/provenance | Scope before enumeration and final lineage revalidation | `AUTHORIZATION_FILTERED`, `PROVENANCE_INVALID` |
| Transport | Shared application result through HTTP/MCP/stdin/SSE as applicable | `EVALUATION_HARNESS_ERROR` |
| Qrels/metrics | Valid topic-grounded qrels and deterministic calculation | `QUERY_UNGROUNDED`, `QREL_INVALID`, `METRIC_COMPUTATION_ERROR` |

Later layers are not interpreted when an earlier prerequisite failed. A case may expose multiple diagnostics, but the primary root cause is the earliest invalid gate.

## 4. Query classes

1. **Language capability/routing:** proves a declared language/script/representation can be represented and routed. Generic prompts are allowed but excluded from Recall/MRR/nDCG.
2. **Semantic retrieval quality:** requires a topic/entity and adjudicated evidence. This is the only class used for retrieval quality metrics.
3. **Provenance/security:** tests exact lineage and denials; quality ranking may be irrelevant.
4. **Representation/transformation:** validates source and derived text equivalence/lineage, including generic legacy-font fixtures.
5. **Behavioral blind-client:** the client sees only public metadata/prompts; scored separately under WP-16.

`QUERY_UNGROUNDED` is not a language failure. A filename-only query may be a selector/discovery test, not semantic multilingual quality evidence.

## 5. Cohort scaling

Avoid exhaustive L×L evaluation:

- same-language admission cohort for every candidate exposed language;
- provider-declared but unconfigured languages appear in capability tests only;
- cross-language edges sampled by script-family pairs, same-script confusion, deployment demand, corpus evidence and anchor languages;
- one stable anchor set for longitudinal comparison plus rotating edges for breadth;
- mandatory high-risk representations (legacy font, transliteration, OCR, Vision, mixed script/language);
- no-answer, authorization and provenance controls in every certification pack;
- per-edge state remains `UNVALIDATED` when no governed qrels exist.

This supports many languages without generalizing an anchor edge's score to unmeasured directions.

## 6. Mandatory regressions from the investigation

- Corpus census proves the Marathi `manuscript.pdf` evidence exists before evaluating target retrieval.
- A failed query against that evidence cannot produce `CORPUS_ABSENT`.
- Title-only/empty candidate input fails before the provider call.
- Positive test proves actual candidate chunk text reaches the reranker and the exact rendered hash is retained.
- Generic English/Hindi/Marathi “find related evidence” prompts are classified as routing/ungrounded, not semantic quality.
- A topic-grounded Marathi query has an exact qrel and trace through dense, fusion, rerank and final output.
- A generic legacy-font fixture exercises representation detection/transformation without a Ramayana/document-name branch.
- Canonical text/hash remains identical after every transform test.

## 7. Metrics and lifecycle

Metric definitions, uncertainty and thresholds remain governed by the Decision-7 evaluation contract. This architecture does not invent floors. `EVALUATED` requires retained raw artifacts for the exact language/operation/direction; `VERIFIED` requires approved results and security evidence; `CERTIFIED` requires ADR-0070 governance for exact corpus, profile, generation and environment.

## 8. Harness integrity

Evaluation scripts consume the production application service, evidence resolver and shared reranker candidate builder. Direct provider calls are permitted only in explicitly labeled provider conformance tests, never as transport/runtime evidence. The harness validates its own candidate/query/qrel digests before scoring and emits `EVALUATION_HARNESS_ERROR` rather than attributing malformed input to Mnemo retrieval.
## 9. Normative V2 records and path-parity invariant

`MULTILINGUAL_EVALUATION_CONTRACT.proposed.json` freezes `QueryRecordV2`, `EvidenceQrelV2`, `CorpusPresenceEvidenceV2`, `EvaluationStageRecordV2`, `EvaluationFailureRecordV2`, `RuntimeParityEvidenceV2`, and `EvaluationCaseRecordV2`.

A semantic-quality query is eligible for ranking metrics only when `grounding_state=QUERY_GROUNDED`, its topic and evidence-level qrels are present, and every qrel resolves to authorized, provenance-valid evidence. A generic prompt may remain a routing/behavioral case only with `QUERY_UNGROUNDED`; it is excluded from semantic metrics. Document-title-only qrels are invalid for semantic quality.

The V2 evaluator invokes the same public application service as production. It cannot access private provider runtimes, construct reranker input, select permissive authorization, or synthesize lineage. Production and evaluation evidence must show identical candidate-builder, preprocessing, tokenizer, reranker-adapter, authorization, provenance-validator, retrieval and fusion identities/digests.

`CORPUS_ABSENT` requires both an immutable source-census predicate and an authorized evidence-census predicate proving absence. An empty dense/sparse/fused ranking never proves corpus absence or unsupported language.

## 10. Representation and transport parity

Every V2 evaluation transport consumes the vocabulary in `EVIDENCE_REPRESENTATION_VOCABULARY.proposed.json`. Equal requests over HTTP, MCP stdio and MCP SSE must produce equal normalized arguments, representation semantics, completeness, lineage, authorization behavior, structured content and canonical JSON fallback. Contract-digest parity and semantic fixture parity are pre-exposure tests.
