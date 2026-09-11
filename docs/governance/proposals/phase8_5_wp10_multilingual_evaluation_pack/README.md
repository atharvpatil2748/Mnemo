# Mnemo Phase 8.5 WP-10 Decision 7 Approval Package

This directory contains a **scratch-only proposed governance package**. Nothing here is authoritative until reviewed and approved by the designated Mnemo governance owners.

## Package contents

1. `multilingual_evaluation_contract.proposed.md` — human-readable proposed evaluation contract: corpus, cohorts, counts, judgments, metrics, uncertainty, thresholds, latency, and failures.
2. `multilingual_evaluation_contract.proposed.schema.json` — strict machine-readable schema for the eventual evaluation manifest/contract.
3. `multilingual_qrels.schema.json` — strict evidence-level relevance/provenance judgment schema.
4. `multilingual_threshold_contract.proposed.json` — proposed sample/uncertainty/derivation structure with all unsupported numeric floors left `NOT YET DEFENSIBLE`.
5. `multilingual_evaluation_manifest.template.json` — schema-valid template for the future approved immutable evaluation pack; query/qrel/digest fields are intentionally empty.
6. `governance_approval_checklist.md` — explicit approval fields and signatures.
7. `decision7_final_readiness_report.md` — final Decision 7 readiness and GO/NO-GO analysis.
8. `README.md` — this guide.

Earlier analytical inputs retained in this directory:

- `multilingual_evaluation_manifest.proposed.json`
- `multilingual_evaluation_manifest.proposed.schema.json`
- `decision7_threshold_report.proposed.md`

The earlier artifacts remain forensic/proposal inputs and are not silently promoted by this package.

## What is proposed

- 30 cases/direction as a provisional measurement floor.
- 75 cases/direction as a certification evaluation target.
- Exact secondary-cohort targets listed in the contract.
- Three-grade qrels, two independent reviewers, adjudication, strict provenance.
- Macro Recall@1/3/5/10, MRR, graded nDCG@10, decisive-pair reranker accuracy.
- Wilson 95% intervals and a 10,000-resample direction-stratified bootstrap with proposed seed `8501007`.
- Reporting-only latency until hardware and limits are approved.
- A non-circular threshold derivation procedure.

Every item above is **PROPOSED — REQUIRES HUMAN/GOVERNANCE APPROVAL** unless an authoritative document already freezes it.

## What is authoritative

The authoritative sources remain the Phase 8.5 plan, architecture, ADR-0067, ADR-0070, ADR-0074, existing WP gate evidence, the frozen Golden Dataset, and frozen multimodal evidence. This scratch package does not modify or supersede them.

## What cannot yet be claimed

- Decision 7 fully frozen.
- Any directional numeric certification floor.
- Approved reranker MRR/nDCG.
- Approved pairwise/no-answer/latency floor.
- WP-10 implementation permission.
- Multilingual retrieval readiness, verification, or certification.
- WP-16 behavioral verification or Phase 8.5 certification.

## Required human approval

Use `governance_approval_checklist.md`. Approval must cover the corpus and candidate universe, sample sizes, query/qrel creation, reviewer qualifications, adjudication, metrics, uncertainty/bootstrap settings, latency, threshold procedure, zero-tolerance gates, reranker contradiction handling, and explicit permission to begin implementation.

## Safety state

This package was created without loading models, running retrieval, generating embeddings, ingesting data, opening SQLite for mutation, activating generations, modifying MCP, changing environment configuration, downloading artifacts, or changing authoritative governance. Only files in this scratch directory were created or updated.

