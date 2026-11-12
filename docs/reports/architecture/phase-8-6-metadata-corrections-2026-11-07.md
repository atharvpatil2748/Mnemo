# Phase 8.6 source metadata correction and four-notebook preparation

Date: 2026-11-07. This is an additive correction; the September 2026 acquisition, evaluation and generalization reports remain historical artifacts. The project owner attests that the substantive sources were manually ingested and audited previously. That attestation is project context, not a newly reproduced parser or retrieval run.

## Current, directly checked facts

The 24-file local source manifest `config/rebuild/codex_downloaded_24.sources.json` matches the present bytes 24/24. Twenty-one are substantive source files, three are governance/results artifacts. A retired Phase 8.6 notebook with ID `81a3bea2-8b15-5c6f-944d-24634fbf835d` and 24 source memberships is recoverable from the protected `registry_phase8_6.db` snapshot (SHA-256 `1902c3a46b2c4cba3bab7efae237af178b0830df7298fc26073c49047ad91c93`). The original local registry is empty and its retired DB contains zero notebook/source/document records. The owner approved making a **separate disposable copy** of the snapshot, leaving both protected historical objects unchanged.

The acquisition manifest correctly records `dcfa97c8-e6e7-41d3-95d1-88dacb65e492.pdf` as 12,764,759 bytes, SHA-256 `a55e99f584ea0c1a5b9dece668c57e423c223a54dbcc0836ed683a6cb59345db`, English text, Maharashtra Economic Survey 2023–24 edition, and *rejected from Marathi evaluation*. Its 346 pages are not an “official UK Government National Economic Report”; the evaluation report's “6.78 MB” is not the present file size. The retained original notebook already contains it; the new three-language partition deliberately excludes it. No missing `CAND-FD-HI-PDF-01` file is substituted.

`engineering_lab_report_heat_transfer.docx` actually discusses single-degree-of-freedom vibration transmissibility. `ml_decision_tree.pptx` contains 19 slide XML parts; `ml_linear_regression.pptx` contains 23. `ons_uk_consumer_price_inflation.xlsx` contains 41 worksheets and `ons_uk_gdp_quarterly_tables.xlsx` contains 31. These corrected observations do not retroactively alter reported benchmark metrics or establish reviewer-approved chunk judgments. The original file names are retained to preserve hash and source identity.

## Experimental boundary

`config/evaluation/phase86_four_notebooks.v1.json` explicitly allocates 5 Hindi, 6 Marathi and 9 English source files. New memberships in the disposable copy reuse the 24 already-indexed documents, their parsed IR, chunks and existing OCR/Vision/CLIP derivations where present. Reuse is **not a claim of fresh parser, OCR, Vision or CLIP inference**. The owner-run command is designed to generate a fresh four-scope BGE-M3 Full V2 projection and activate its alias only within the isolated evaluation directory. The command must fail closed if hashes, the retained notebook identity, ACL state, local model, source linkage or generation coverage disagree. Production remains `UNINDEXED`.

The post-ingestion audit and four-notebook retrieval evaluation are separate gates. A prior filename-target query is not a valid chunk-level QREL until exact notebook/source/document/version/chunk ancestry and independent target evidence are recorded. No human relevance adjudication is asserted here.
