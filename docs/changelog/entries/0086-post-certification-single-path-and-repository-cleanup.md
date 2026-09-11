# 0086 — Post-certification single-path and repository cleanup

## Actual changes

- Audited HTTP, MCP stdio, and MCP SSE composition and documented their shared
  certified V2 application path.
- Declared the production manifest as the canonical configuration root and
  reconciled it with the signed active/certified state.
- Replaced the unused legacy outer cross-encoder startup provider with an inert
  V2-owned provider. Exposed V2 continues to perform exactly one governed BGE
  reranking stage.
- Retired the verified project-owned ms-marco model weights after production
  startup validation. Historical source, tests, evaluations, and metrics remain.
- Added documentation and report indexes instead of moving historical evidence
  and risking broken references.
- Preserved the production corpus, BGE-M3/BGE-reranker/CLIP artifacts, dynamic
  public `requested_k`, internal K=50, and all Ollama models/configuration.
