# Decision 7 Two-Stage WP-10 Implementation Authorization — Proposed

Status: **PROPOSED — REQUIRES EXPLICIT HUMAN/GOVERNANCE APPROVAL**  
Effect before approval: none. WP-10 remains NO-GO.  
Scope: Phase 8.5 WP-10 multilingual engineering and subsequent evaluation only.

## 1. Authoritative basis

No authoritative repository document states that numeric multilingual certification floors must exist before production engineering code may be written.

**NO EXPLICIT PRE-CODING NUMERIC-THRESHOLD REQUIREMENT FOUND.**

The authoritative documents instead separate implementation, activation, verification, and certification:

- ADR-0074 defines `DECLARED → CONFIGURED → BUILDABLE → READY → ACTIVE → EXPOSED → VERIFIED → CERTIFIED` and forbids inferring a later state from an earlier one.
- ADR-0070 says unmeasured capability is `UNVALIDATED`, never PASS, and explicitly refuses arbitrary quality numbers before baselines are measured.
- The Phase 8.5 plan defines WP-10 engineering tasks 10.1–10.8 and places pinned per-direction thresholds in the WP-10 Definition of Done, not as an express prerequisite to writing tasks 10.1–10.4.
- The Phase 8.5 architecture sequences contracts/evaluation design, implementation, live evaluation, and certification, and requires published thresholds for acceptance.
- ADR-0067 requires directional benchmark acceptance before profile promotion and validated claims; it does not prohibit implementing the provider, generation, and retrieval mechanisms needed to produce the evidence.

This proposal therefore authorizes engineering only under strict lifecycle truthfulness. It does not waive any WP-10 exit, WP-16, or WP-17 gate.

## 2. Already frozen

The following architecture decisions remain frozen and may be implemented without redesign:

1. `LanguageEvidenceReferenceV2` source-reference contract.
2. BGE-M3 query/document preprocessing identities.
3. `MultilingualEmbeddingProviderV2` query and batch protocol.
4. `unicode-en-hi-mr-conservative-v1` detector policy.
5. Language-text and multilingual-vector generation identities.
6. BGE reranker 256-token pair policy.
7. Bounded SQLite exact-cosine BGE-M3 dense backend, isolated from V1 and CLIP spaces.
8. Frozen model identities and revisions already governed elsewhere.

The Decision 7 evaluation structure is fully specified as a proposal: contract/schema, qrels schema, cohort layout, metrics, uncertainty choices, zero-tolerance gates, no-answer handling, latency reporting, and non-circular threshold procedure.

## 3. Remains open

The following are not approved performance claims and remain open:

- Human approval of the proposed evaluation structure and methodological choices.
- Actual governed query and qrels content and their immutable digests.
- Candidate-universe digest and exact evaluation environment identity.
- Recall@1/3/5/10 floors for each of nine directions.
- MRR and nDCG@10 floors for each direction.
- Reranker pairwise-accuracy floor.
- No-answer false-support and false-publication numeric limits.
- Numeric latency gates and the approved hardware profile.
- Measured directional, transliteration, mixed-script, mixed-language, OCR-language, Vision-language, negative, MCP, and WP-16 results.
- Resolution of the historical reranker MRR/nDCG summary conflict.
- `VERIFIED`, `CERTIFIED`, WP-16 completion, WP-17 completion, and Phase 8.5 certification.

Every open quality value remains `NOT YET DEFENSIBLE` until governed evidence exists.

## 4. Two-stage authorization

### Stage 1 — engineering toward BUILDABLE

After this proposal is explicitly approved, engineering may implement the frozen WP-10 design:

- production language transformation/observation composition required by the frozen contract;
- exact-revision offline BGE-M3 embedding adapter;
- exact-revision BGE reranker adapter;
- provider registration, capability declaration, bounded batching, readiness-probe implementation, and safe failure behavior;
- language observation/derivation and multilingual embedding builders;
- deterministic generation identity, checksum, recovery, and stale-generation rejection;
- bounded exact-cosine multilingual dense source isolated from V1 and CLIP spaces;
- multilingual planner/fusion/reranker integration;
- additive runtime and `search_evidence` composition behind truthful lifecycle gating;
- deterministic unit/integration tests using isolated fixtures and no frozen-state mutation.

Stage 1 may establish `DECLARED`, `CONFIGURED`, and—only when ADR-0074 dependencies, provider capability, authorization, assets, and resource admission are actually satisfied—`BUILDABLE`.

Stage 1 does not authorize active generation promotion, truthful public advertisement, verification, certification, corpus mutation, or modification of frozen multimodal artifacts.

### Stage 2 — readiness, activation, exposure, evaluation, and certification gates

Stage 2 may begin only under a separately approved isolated evaluation runbook. It must:

1. Prove exact provider/model/revision/preprocessing/dimension readiness.
2. Build new multilingual generations in an isolated evaluation database.
3. Verify complete coverage, checksums, source binding, recovery, and stale/partial rejection.
4. Advance a generation to `READY` only after all integrity/coverage checks pass.
5. Advance to `ACTIVE` only through an atomic alias selecting that exact READY generation and after applicable ADR-0067 benchmark-acceptance/profile-promotion policy is satisfied.
6. Advance to `EXPOSED` only when HTTP/MCP capability reporting truthfully advertises the exact active state; an unverified exposed capability remains explicitly unverified/unvalidated.
7. Execute the frozen evaluation pack, retain raw rankings, compute per-direction metrics and uncertainty, and run security/provenance gates.
8. Advance to `VERIFIED` only when deterministic service, protocol, behavior, security, and approved quality gates pass for the exact deployment snapshot.
9. Advance to `CERTIFIED` only when ADR-0070 governance approves the exact profile, generation, hardware/trust scope, and corpus/evaluation version.

Stage 2 does not automatically follow from Stage 1 completion. Each lifecycle transition requires its own evidence.

## 5. Lifecycle evidence table

| State | Evidence required | Permitted initial claim |
|---|---|---|
| DECLARED | Frozen contract, owner, interfaces, identifiers | Yes, when present |
| CONFIGURED | Enabled syntactically valid profile with exact provider/model/revision/policy/bounds and no hidden fallback | Yes, after configuration validation |
| BUILDABLE | Dependencies, authorized source assets, real provider capability, resource admission, and builders can create the governed generation | Only after those facts are proven |
| READY | Complete immutable generation; exact profile/source binding; counts/checksums/coverage/integrity pass; no stale/partial state | Not authorized by Stage 1 |
| ACTIVE | Atomic alias selects exactly one compatible READY generation | Not authorized by Stage 1 |
| EXPOSED | HTTP/MCP adapter advertises the exact active capability and truthful unverified status | Not authorized by Stage 1 |
| VERIFIED | Deterministic service/protocol/behavior, security, provenance, completeness, and approved quality gates pass for the deployment snapshot | POST-IMPLEMENTATION |
| CERTIFIED | ADR-0070 approval for exact profile, generation, hardware/trust scope, corpus/evaluation version, and retained evidence | POST-IMPLEMENTATION |

No model file, class, unit test, configured profile, or generation row may be used as evidence for a later state by itself.

## 6. Independent threshold rule

The historical 18-query BGE-M3 and reranker results remain model-selection evidence. They are not certification floors. Numeric thresholds must be approved through the frozen, non-circular procedure and must not be chosen merely to make the implemented candidate pass.

The proposed `30` provisional cases/direction, `75` certification cases/direction, Wilson 95% intervals, bootstrap seed `8501007`, and 10,000 resamples are governance proposals and methodological choices. Their exact values are not authoritative or technically mandatory until approved.

## 7. Prohibited claims and actions

Engineering may not claim `READY`, `ACTIVE`, `EXPOSED`, `VERIFIED`, `CERTIFIED`, behaviorally verified, WP-16 complete, WP-17 complete, or Phase 8.5 certified without the corresponding evidence.

Engineering may not silently expose an incomplete capability, activate partial/stale generations, use network fallback, mix BGE/V1/CLIP vector spaces, mutate canonical text, or represent OCR/Vision/transliteration/translation as original source content.

## 8. Frozen multimodal and corpus protection

No WP-10 activity may modify:

- the frozen multimodal database, WAL, or SHM;
- the multimodal freeze manifest;
- existing OCR, Vision, or CLIP records/generation identities;
- the Golden Dataset;
- canonical `Chunk.text`;
- V1 retrieval/reranker/index semantics;
- CursorCodecV2 or authorization boundaries.

WP-10 may consume authorized immutable source/derived evidence by identity and must create only additive multilingual records/generations in a separately authorized isolated environment.

## 9. Proposed approval

Approval of this proposal means:

> Engineering implementation may begin using the frozen architecture and approved evaluation structure while numeric certification thresholds remain OPEN. Initial authorization extends only through truthful `BUILDABLE`. No later lifecycle state may be claimed without its required evidence.

Approval does not itself make WP-10 READY, ACTIVE, EXPOSED, VERIFIED, CERTIFIED, or complete.

Governance approver: ____________________  
Decision: APPROVE / REJECT / AMEND  
Date: ____________________  
Conditions: ________________________________________________________________

