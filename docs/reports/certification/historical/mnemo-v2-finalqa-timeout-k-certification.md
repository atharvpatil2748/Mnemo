# Mnemo V2 FinalQA operational storage, timeout, dynamic-k, and certification gate

Date: 2026-09-06  
Status: **PRODUCTION_CERTIFICATION_BLOCKED**  
Highest truthful lifecycle: **EXPOSED**

## Executive result

The three immediate serving defects are remediated and validated:

1. FinalQA writes now go to a dedicated mutable operational SQLite store. Retrieval, authorization, and evidence resolution remain bound to the immutable 44-document production corpus database.
2. The five-second retrieval timeout was replaced by a server-owned 30-second retrieval deadline based on measured serving latency. Provider generation retains its separate timeout.
3. Client `requested_k` remains dynamic. The governed value 50 means the internal top-50 fused candidate pool entering reranking; it does not replace the client result limit.

Real authenticated FinalQA completed through HTTP, MCP stdio, and MCP SSE. Gemma ran explicitly on the RTX 4060 through Ollama at 100% GPU residency. Transport parity passed for the retrieval and semantic context layers.

Certification stops at the next gate. The repository has no governed production-parity evaluator that can load BGE for an 18-query evaluation without activating the production reranker. The only similarly named script is an incompatible standalone Phase 8.6 CPU script against a different database with synthetic identities. It cannot truthfully authorize activation.

## FinalQA storage separation

The authoritative corpus remains:

- path: `scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db`
- governed identity: `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d`
- physical SHA-256 after all real transport tests: `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`
- 44 documents, 44 versions, 44 source memberships, 2,658 chunks
- `PRAGMA integrity_check`: `ok`
- foreign-key violations: 0
- WAL: 0 bytes

Mutable FinalQA execution state is stored separately at:

`scratch/phase8_5_full_multilingual_v2/operational/final_qa_v2.db`

`SQLiteFinalQAOperationalStore` exposes only the typed FinalQA execution-store contract. It owns execution, snapshot, transition, and citation persistence and does not implement the corpus storage interface. Production startup rejects configuration in which the operational and corpus paths resolve to the same file. Corpus reads used by evidence authorization still use the production corpus store.

## Retrieval timeout governance

The prior 5,000 ms advanced-retrieval deadline was lower than observed V2 retrieval latency. The production server configuration now owns a 30,000 ms retrieval deadline. This is based on the observed approximately nine-second normal retrieval and the prior 15.430-second controlled maximum, rather than an arbitrary model timeout.

The deadline wraps the retrieval portion of both FinalQA retrieval entry paths. Timeout produces the existing typed `OperationTimeoutError`; it does not silently fall back to V1. Ollama generation remains governed by its independent provider timeout.

## Dynamic user-k contract

The corrected contract is:

```text
requested_k / evidence_budget -> dynamic public result limit
internal candidate pool       -> exactly top 50 fused candidates entering reranking
```

Production planning therefore sets recall, fusion, and rerank limits to the governed internal pool of 50 while retaining the authenticated request's evidence budget as the result limit. Response diagnostics expose both values. Tests cover requested values 1, 5, 10, and 50 and prove that the internal reranker pool remains 50.

## Explicit Gemma GPU remediation

The initial Ollama CUDA OOM was not evidence that `gemma4:e4b` needed CPU execution. Mnemo requested a 16,384-token context, which caused excessive per-model KV-cache reservation when the shared Ollama service retained its four parallel slots.

The CPU override was removed. Mnemo does not override the shared Ollama parallelism. Its project-local synthesizer request is now bounded through the existing Ollama `num_ctx` request option:

```text
OLLAMA_NUM_PARALLEL=4        # unchanged shared user setting
Mnemo synthesizer num_ctx=8192
```

Observed evidence:

- test server inherited the persistent `OLLAMA_NUM_PARALLEL=4` value
- representative request contained 6,327 prompt tokens and completed successfully
- `ollama ps`: `gemma4:e4b`, **100% GPU**, context 8,192
- `nvidia-smi`: 4,887 MiB used
- direct exact-model GPU request: 16.133 seconds
- no `num_gpu=0`, `OLLAMA_NUM_PARALLEL`, or `OLLAMA_MAX_LOADED_MODELS` override in Mnemo production configuration
- no CPU fallback

This isolates memory control to Mnemo's own request context and leaves the shared four-slot Ollama service untouched for other projects.

## Real transport execution

| Gate | Result | Elapsed | Evidence |
|---|---:|---:|---|
| Authenticated HTTP FinalQA | PASS (HTTP 200) | 25.831 s | `scratch/http-finalqa-e2e-result.json` |
| Authenticated MCP stdio FinalQA | PASS | 40.308 s including startup | `scratch/mcp-stdio-finalqa-e2e-result.json` |
| Authenticated MCP SSE FinalQA | PASS | 19.922 s | `scratch/mcp-sse-finalqa-e2e-result.json` |
| HTTP/MCP retrieval-context parity | PASS | n/a | `scratch/finalqa-http-mcp-parity.json` |

All three requests traversed real transport servers and produced published, citation-resolved FinalQA results. Each used the same five ordered retrieval candidates and the same four ContextBuilder items. Candidate semantic text, content hashes, source/document/version/chunk provenance, production database identity, vector space, and generation identities matched.

Raw rendered context hashes differ solely because the bounded authorization-decision fingerprint is transport/principal-specific. After masking only that security-context field, ContextBuilder input is byte-identical. This is expected authentication behavior, not retrieval divergence.

## Implementation changes

Production implementation:

- added `SQLiteFinalQAOperationalStore` and production operational-store resolver;
- wired the operational store into HTTP, MCP stdio, and MCP SSE startup/shutdown;
- retained the corpus store for evidence authorization;
- governed the 30-second retrieval deadline;
- separated dynamic requested-k from the internal K=50 reranker pool;
- completed missing multilingual storage facade delegates;
- projected governed multilingual text evidence into canonical-chunk FinalQA evidence;
- corrected the FinalQA citation prompt to use governed `[source:N]` markers;
- adapted MCP structured output metadata without weakening the typed FinalQA response.

Evaluation-only evidence:

- real HTTP/MCP probe scripts and their result artifacts;
- durable transport-parity verifier and parity artifact;
- Ollama GPU runtime logs.

No BGE alias, production generation, corpus content, embedding, Golden Dataset, Phase 8.6 data, or 67-document evaluation database was changed.

## Validation

- focused tests: **76 passed**
- Ruff on touched implementation/tests/probes: **PASS**
- strict mypy on 12 touched source files: **PASS**
- compileall: **PASS**
- generated JSON parsing: **PASS**
- repository-wide `git diff --check`: retains the previously documented unrelated whitespace at `mnemo-core/mnemo/models/chunks.py:65`

## Blocking production-parity gate

`scratch/evaluate_v2_production_contract.py` is not usable for this gate. It is a standalone 70-query Phase 8.6 script that:

- points to `data/phase8_6_eval/phase8_6_eval.db`, not the 44-document production store;
- initializes the embedding and reranker on CPU;
- constructs synthetic UUID identities;
- does not execute the server-owned exposed V2 application composition.

Meanwhile, the governed `RerankerActivationAuthorityV1` correctly requires `production_evaluation_passed=true` before installing BGE into the active router. There is no separate server-owned evaluation lease/runner between these two contracts. Activating the router to perform the missing evaluation would invert the gate and violate governance.

Therefore the unexecuted stages are:

- 18-query production-parity Golden BGE evaluation;
- controlled BGE activation;
- post-activation HTTP/MCP verification;
- governed rollback execution;
- final certification.

BGE remains inactive. No rollback was required.

The smallest safe next action is to govern and implement a server-owned, non-activating production-parity evaluator. It must reuse the actual 44-document V2 composition and governed 256-token candidate builder, load exact-revision BGE on CUDA with batch 2 under an evaluation-only lease, write identity-bound 18-query evidence, and be structurally unable to mutate the active reranker router.

## Lifecycle

```text
DECLARED:    PASS
IMPLEMENTED: PASS
CONFIGURED:  PASS
BUILDABLE:   PASS
READY:       PASS
ACTIVE:      PASS
EXPOSED:     PASS
EVALUATED:   FALSE
VERIFIED:    FALSE
CERTIFIED:   FALSE
```

Final status: **PRODUCTION_CERTIFICATION_BLOCKED**  
Failed gate: **PRODUCTION_PARITY_EVALUATION_BLOCKED**
