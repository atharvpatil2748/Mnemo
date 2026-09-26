# Mnemo Reports

Reports are organized by purpose. Their conclusions remain point-in-time
evidence unless explicitly identified as current authority.

## Current certification

- [Final Mnemo V2 certification](certification/current/mnemo-v2-final-certification.md)
- [Single production path audit](architecture/mnemo-v2-single-production-path-audit.md)
- [Module 8.8.1 certified runtime convergence](operations/mnemo-module-8-8-1-certification.md)
- [Module 8.8.1 independent forensic audit](operations/mnemo-module-8-8-1-forensic-audit.md)

Earlier certification stages are retained under
[certification/historical](certification/historical/).

## Evaluation

- [Production-parity BGE evaluation](evaluation/mnemo-v2-production-parity-bge-evaluation.md)
- [Phase 8.5 Golden A/B](evaluation/retrieval-evaluation-phase8_5-golden-ab.md)
- [Phase 8.6 GPU A/B](evaluation/retrieval-evaluation-gpu-ab.md)
- [Identity-bound harness validation](evaluation/identity-bound-evaluation-harness-validation.md)

All evaluation reports are in [evaluation](evaluation/).

## Other report categories

- [Architecture and production-path reports](architecture/)
- [Audits](audits/)
- [Performance and model benchmarking](performance/)
- [Operational audits and cleanup evidence](operations/)

Current Phase 8.8 inputs include the
[post-Phase-8 architecture audit](operations/mnemo-post-phase8-architecture-next-step-audit.md),
[MCP failure and contract audit](operations/mnemo-mcp-failure-and-contract-audit.md),
and [post-Phase-8.5 MCP architecture audit](architecture/POST_PHASE_8_5_MCP_ARCHITECTURAL_AUDIT.md).
The [Phase 8.8 Stage 5 implementation acceptance](operations/mnemo-phase-8-8-stage-5-acceptance.md)
records local prerequisite-branch evidence, not Phase 8.8 certification or a
production deployment.
The [Module 8.8.5 forensic acceptance](operations/mnemo-module-8-8-5-forensic-acceptance.md)
records independent local metadata-contract verification, not deployment or
external ChatGPT verification of that working tree.
The [Module 8.8.7 local typed-error implementation](operations/mnemo-module-8-8-7-local-implementation.md)
records local validation of the shared error boundary, not deployment or
completion of deferred reader-specific task 8.8.2f.
The [Module 8.8.7 independent forensic acceptance](operations/mnemo-module-8-8-7-forensic-acceptance.md)
records adversarial local transport and nondisclosure verification, not
production deployment or Stage 6 closure.
The [Module 8.8.2f local reader-error implementation](operations/mnemo-module-8-8-2f-local-implementation.md)
records safe originating-reader error propagation through the shared typed
contract; the combined audit below independently assesses it. Stage 6 closure
remains separate.
The [Module 8.8.4 local 14-tool contract implementation](operations/mnemo-module-8-8-4-local-implementation.md)
and [Module 8.8.8 local V1/V2 routing implementation](operations/mnemo-module-8-8-8-local-implementation.md)
record fixture-backed local acceptance only; neither establishes live tunnel
behavior, deployment, independent forensic acceptance or Stage 6 closure.
The [Stage 6 combined independent forensic audit](operations/mnemo-stage-6-combined-forensic-audit.md)
records reproduced partitioned-evidence contract defects and blocked the batch
at that checkpoint; it does not amend historical implementation reports or ADRs.
The [Stage 6 forensic remediation and acceptance](operations/mnemo-stage-6-forensic-remediation-and-acceptance.md)
records the subsequent F-1/F-2 corrections, fresh local evidence, and current
module and batch verdicts. It is not production or external verification.
The [documentation and proprietary transition report](operations/mnemo-documentation-and-proprietary-transition.md)
records current-status reconciliation and the local current-tree rights change,
without changing GitHub visibility or historical grants.

Historical claims are not rewritten when current architecture changes. Use the
current certification and architecture audit above for production truth.
