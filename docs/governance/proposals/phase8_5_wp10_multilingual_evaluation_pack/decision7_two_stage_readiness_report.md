# Decision 7 Two-Stage WP-10 Readiness Report

## Executive decision

**A. TWO-STAGE IMPLEMENTATION IS ARCHITECTURALLY PERMITTED.**

This is an architectural finding, not present authorization to modify production code. WP-10 remains NO-GO until the proposed checklist is explicitly approved by the designated human governance authority.

## 1. Pre-coding numeric-threshold requirement

**NO EXPLICIT PRE-CODING NUMERIC-THRESHOLD REQUIREMENT FOUND.**

Authoritative evidence distinguishes four gates:

| Gate | Authoritative meaning | Numeric threshold needed before this gate? |
|---|---|---|
| Engineering implementation | Implement providers, builders, storage/retrieval composition, bounds, recovery, and tests | No express pre-coding requirement found |
| Verification | Exact deployment passes deterministic service/protocol/behavior/security and approved quality gates | Yes, approved verification criteria and measured evidence are required |
| Phase 8.5 exit | WP-10 DoD, blind-agent, regression, security, quality, and governance gates are satisfied | Yes, pinned per-direction thresholds must be met |
| Certification | ADR-0070 approves exact profile/generation/hardware/trust/corpus/evaluation evidence | Yes, certification floors and complete evidence are required |

The Phase 8.5 plan places per-direction pinned thresholds in WP-10's Definition of Done. It separately enumerates engineering tasks 10.1–10.8. The architecture's Stage 9 says implementation acceptance requires published thresholds, but does not state that the numbers must predate writing the implementation. ADR-0070 explicitly avoids arbitrary numbers before measurement. Therefore absence of numeric floors blocks WP-10 completion/verification/certification, not engineering work through the initial lifecycle states.

## 2. ADR-0074 lifecycle validity

The proposed two-stage process does not violate ADR-0074 if lifecycle claims remain exact:

```text
Stage 1: DECLARED → CONFIGURED → BUILDABLE
Stage 2: READY → ACTIVE → EXPOSED → VERIFIED → CERTIFIED
```

ADR-0074 expressly defines these as distinct states and states that no later state is inferred from an earlier one. `BUILDABLE` is reached when dependencies, assets, authorization, provider capability, and resource admission allow generation construction. It does not require an already-created generation or certification result.

`READY` requires actual artifacts/projections with integrity and coverage. `ACTIVE` requires an atomic alias. `EXPOSED` requires truthful adapter advertisement. `VERIFIED` requires deterministic deployment evidence and gates. `CERTIFIED` requires ADR-0070 approval.

ADR-0067's requirement to promote profiles only after benchmark acceptance applies to later generation/profile promotion. It does not prohibit engineering the provider and generation machinery required to reach `BUILDABLE`. Any activation must still satisfy ADR-0067, ADR-0074, and the approved Stage 2 runbook.

## 3. Pre-coding freeze classification

| Item | Classification | Reason |
|---|---|---|
| Source-reference contract | FROZEN | Decision 1 is frozen |
| BGE preprocessing identities | FROZEN | Decision 2 is frozen |
| Embedding protocol | FROZEN | Decision 3 is frozen |
| Conservative EN/HI/MR detector | FROZEN / recorded approval required | Decision 4 design is frozen/freeze-ready; checklist captures formal approval |
| Generation identities | FROZEN | Decision 5 is frozen |
| Reranker 256-token policy | FROZEN | Decision 6 is frozen |
| Dense backend | FROZEN | Decision 8 is frozen |
| Evaluation schema | PROPOSED | Fully specified but not human-approved |
| Qrels schema | PROPOSED | Strict schema exists; approval pending |
| Cohort structure | PROPOSED | Nine primary and secondary cohorts specified; approval pending |
| Metric definitions | PROPOSED | Exact formulas specified; not authoritative yet |
| Uncertainty methodology | PROPOSED | Wilson/bootstrap choices are not mandated |
| Zero-tolerance gates | PROPOSED | Consistent with security/correctness architecture; formal approval pending |
| No-answer policy | PROPOSED | Separate false-support/publication rates; approval pending |
| Latency reporting policy | PROPOSED | Architecture requires reporting, not the proposed exact procedure |
| Threshold derivation procedure | PROPOSED | Non-circular procedure specified; approval pending |
| Actual numeric quality thresholds | OPEN / POST-IMPLEMENTATION | NOT YET DEFENSIBLE |

## 4. Must remain open until post-implementation evidence

| Evidence/threshold | Required status now | When it may be resolved |
|---|---|---|
| Recall@1/3/5/10 floors | OPEN | After approved pack/baselines support independent floors |
| MRR floors | OPEN | POST-IMPLEMENTATION governed measurement/approval |
| nDCG@10 floors | OPEN | POST-IMPLEMENTATION governed measurement/approval |
| Reranker pairwise floor | OPEN | After judged decisive pairs and retained scores exist |
| Numeric latency gates | OPEN | After hardware profile and representative measurements are frozen |
| Measured directional performance | POST-IMPLEMENTATION | Frozen pack execution |
| Nine-direction results | POST-IMPLEMENTATION | Frozen pack execution |
| Transliteration results | POST-IMPLEMENTATION | Frozen pack execution |
| Mixed-script/mixed-language results | POST-IMPLEMENTATION | Frozen pack execution |
| OCR-language results | POST-IMPLEMENTATION | Frozen pack execution using immutable derived evidence |
| Vision-language results | POST-IMPLEMENTATION | Frozen pack execution using immutable derived evidence |
| Negative/no-answer results | POST-IMPLEMENTATION | Frozen negative cohort execution |
| WP-16 external-client behavior | POST-IMPLEMENTATION | Genuine blind-client transcripts |
| Certification | POST-IMPLEMENTATION | ADR-0070/WP-17 decision |

Open thresholds must not be filled from the historical 18-query aggregates merely because the selected models performed well.

## 5. Proposed methodological values

| Value | Authoritative requirement? | Governance proposal? | Technically necessary exactly as stated? | Classification |
|---|---|---|---|---|
| 30 cases/direction | No | Yes | No; some provisional sample is necessary, exact 30 is a trade-off | Methodological choice |
| 75 cases/direction | No | Yes | No; sample depends on desired claim strength/cost | Methodological choice |
| Wilson 95% | No | Yes | Uncertainty reporting is necessary; Wilson and 95% are defensible but not uniquely required | Methodological choice |
| Bootstrap seed 8501007 | No | Yes | A fixed seed is required for exact reproducibility; this exact seed is not | Methodological choice |
| 10,000 resamples | No | Yes | Enough resamples are needed for stable estimates; exact 10,000 is not mandated | Methodological choice |

None may be promoted to an authoritative requirement without explicit approval.

## 6. Checklist amendment compatibility

Adding the following approval item is compatible with the architecture:

> APPROVE TWO-STAGE WP-10 PROCESS: Engineering implementation may begin using the frozen evaluation structure while numeric certification thresholds remain OPEN. No lifecycle state beyond BUILDABLE may be claimed until the corresponding evidence exists.

This item is safe because it:

- preserves ADR-0074's monotonic lifecycle;
- keeps later claims evidence-gated;
- preserves ADR-0070's `UNVALIDATED`, never PASS rule;
- does not waive ADR-0067 benchmark/profile-promotion constraints;
- does not mark WP-10 complete;
- does not authorize WP-16/WP-17 claims;
- explicitly protects frozen multimodal and Golden Dataset state.

The scratch checklist is not itself an authoritative amendment. A designated human governance owner must approve it. No active governance document needs architectural revision to permit the two-stage process, but the authorization decision must be recorded before engineering begins because the current project-specific gate says NO-GO.

## 7. Stage 1 permissible engineering scope

After approval, Stage 1 may implement the frozen provider adapters, observation/derivation builders, embedding/reranker protocol, deterministic generation identity/recovery, bounded isolated dense source, multilingual planner/fusion, truthful runtime gating, and tests. It may reach `BUILDABLE` only with real dependency/provider/resource evidence.

It may not activate or advertise incomplete generations; claim readiness, verification, or certification; mutate frozen evidence; mix vector spaces; or use hidden/network fallback.

## 8. Stage 2 evidence sequence

Stage 2 requires provider readiness, isolated generation build, integrity/coverage, READY status, benchmark-accepted atomic activation, truthful exposure, frozen-pack execution, retained rankings, directional metrics/uncertainty, zero-tolerance gates, live MCP/WP-16 evidence, and final ADR-0070 approval. Each transition is independently fail-closed.

## 9. Frozen-state boundary

The two-stage design is additive. It may consume canonical/OCR/Vision evidence by authorized immutable identity. It may not modify the frozen multimodal database/WAL/SHM, freeze manifest, OCR/Vision/CLIP identities or results, Golden Dataset, canonical text, V1 indexes, CursorCodecV2, or authorization architecture.

## 10. Final governance decision

**Architectural conclusion:** TWO-STAGE IMPLEMENTATION IS ARCHITECTURALLY PERMITTED.

**Present operational authorization:** NOT YET GRANTED.

**Current WP-10 status:** NO-GO until a human governance owner signs the proposed two-stage authorization checklist.

**After signature:** GO only for Stage 1 engineering through truthful `BUILDABLE`; all numeric thresholds and later lifecycle states remain OPEN/POST-IMPLEMENTATION.

