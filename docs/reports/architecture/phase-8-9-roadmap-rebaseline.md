# Phase 8.9 documentation re-baseline review

Date: 2026-10-09. Scope: documentation and design only; no runtime or data
certification is claimed.

## Baseline and audit input

- Authority: [Engineering Roadmap v1.0](../../architecture/current/mnemo_engineering_roadmap.md)
  and [Architecture Specification v2.0](../../architecture/current/mnemo_architecture_v2.md).
- The prior unified-retrieval audit was provided as a conversation attachment,
  not a repository file. Its proposed `scratch/validation/unified_retrieval_architecture_2026_10_09/architecture_decision.md`
  path was not created. The audit found one-notebook automatic V2 scope,
  missing actor-to-notebook membership, separate typed structured retrieval,
  incomplete cross-notebook provenance/pagination and no external-client
  certification. These are mapped to roadmap 8.9.1–8.9.9.
- [ADR-0079](../../adr/active/ADR-0079-automatic-representation-complete-v2-retrieval.md)
  governs the accepted single-notebook V2 direction; [ADR-0077](../../adr/active/ADR-0077-governed-mutable-workspace-boundary.md)
  and [ADR-0078](../../adr/active/ADR-0078-generation-aware-production-credential-lifecycle.md)
  retain their narrower accepted storage/runtime decisions.
- [8.8.1 certification](../operations/mnemo-module-8-8-1-certification.md)
  supports exact runtime convergence; [Stage 5](../operations/mnemo-phase-8-8-stage-5-acceptance.md)
  and [Stage 6 remediation](../operations/mnemo-stage-6-forensic-remediation-and-acceptance.md)
  support local acceptance of subsequent modules, not full transport certification.
  [8.8.10/11 local closure](../operations/mnemo-stage-7-forensic-audit-remediation-and-stage-6-closure.md)
  remains historical, not a new active 8.8 task.

## Disposition

| Former allocation | Current treatment |
|---|---|
| 8.8.14a–c, 8.8.1 | Preserve accepted/certified historical evidence |
| 8.8.2–8.8.8 | Last active 8.8 scope; preserve actual local acceptance, no phase-wide verified claim |
| 8.8.10–11 | Preserve separately accepted local evidence as historical follow-on |
| 8.8.9 | Unfinished parity/FinalQA diagnosis → 8.9.8 |
| 8.8.12 | Retire mandatory dedicated `search_images`; useful modality requirements → 8.9.4/7 |
| 8.8.13 | Unfinished provenance → 8.9.7/8.9.8 |
| 8.8.14d | Readiness decision → 8.9.9 |

## Validation scope

The current registered MCP count and one-notebook guard were checked against
`mnemo-server/mnemo_server/mcp/tools.py`, `services/automatic_query_v2.py`
and `services/authorization.py`; the code still lacks ownership authority.
The current architecture and roadmap distinguish proposed public names from
registered routes. On 2026-10-09 a read-only PowerShell relative-link check
covered the eight edited/created documents listed in the re-baseline scope and
found **0 broken relative links**. The ADR index contains one ADR-0080 entry
and names ADR-0081 as the next available number; `git diff --check` completed
with exit code 0. These are documentation checks only, not implementation,
production promotion, external certification, or `PHASE_8_9_GO`.
