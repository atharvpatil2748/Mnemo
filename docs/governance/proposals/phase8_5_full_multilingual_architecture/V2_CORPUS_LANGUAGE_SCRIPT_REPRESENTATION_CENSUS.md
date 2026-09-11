# V2 Corpus Language / Script / Representation Census

Status: **GOVERNED PRE-BUILD EVIDENCE**

This census reads the immutable Golden Dataset binding and frozen evaluation database; it creates no database rows.

## Totals

- Documents: 44
- Evidence items: 3523
- Canonical chunks: 2658
- OCR regions: 402
- Vision derivations: 463
- Governed legacy exclusions: 504

## Distributions

- Language: `{"hi": 504, "mr": 10, "und": 3009}`
- Script hypotheses: `{"Deva": 252, "Grek": 8, "Latn": 2908, "Mlym": 1, "Zzzz": 578}`
- Representation: `{"legacy_font_encoded_text": 502, "ocr_text": 402, "pdf_encoding_anomaly": 2, "unicode_semantic_text": 2154, "vision_text": 463}`

## Required named-document findings

- `manuscript.pdf`: adjudicated Marathi (`mr`), Unicode Devanagari (`Deva`), Unicode semantic text.
- `Valmiki Ramayana aur Ramakien Ek Tulnamatmak Adhyayan.pdf`: adjudicated Hindi (`hi`), legacy Kruti Dev 010 representation; script remains `Zzzz` until governed transformation.

The Ramayana remains in the corpus and census. Its legacy canonical chunks are explicitly excluded only from transformation-dependent semantic rows; no source content is rewritten or discarded.

Machine artifact digest: `0cf872e3822494bb0fe9c4be7f0e2adb0009d3330ef96b2461a89c5192302446`
