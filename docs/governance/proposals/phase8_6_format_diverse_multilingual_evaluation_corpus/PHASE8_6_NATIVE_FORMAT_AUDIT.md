# PHASE 8.6 — NATIVE FORMAT AUDIT
**Classification:** GOVERNANCE AUDIT — READ-ONLY SOURCE CODE INSPECTION
**Date:** 2026-09-03
**Status:** COMPLETE / VERIFIED
**Auditor:** Automated Source Code Audit

---

## 1. AUDIT METHODOLOGY

This audit was conducted by **direct, line-by-line inspection of production code** within `mnemo-core`.
No assumptions, specifications, or external documentation were accepted without code confirmation.

Inspected files:
- `mnemo-core/mnemo/parsers/__init__.py` — Canonical parser exports
- `mnemo-core/mnemo/parsers/router.py` — `ParserRouter` dispatch, MIME detection, and extension fallback
- `mnemo-core/mnemo/registry.py` — `PluginRegistry` parser registration and priority resolution
- `mnemo-core/mnemo/parsers/pdf.py` — `PDFParser` implementation
- `mnemo-core/mnemo/parsers/docx.py` — `DOCXParser` implementation
- `mnemo-core/mnemo/parsers/pptx.py` — `PPTXParser` implementation
- `mnemo-core/mnemo/parsers/xlsx.py` — `XLSXParser` implementation
- `mnemo-core/mnemo/parsers/csv_parser.py` — `CSVParser` implementation
- `mnemo-core/mnemo/parsers/plain_text.py` — `PlainTextParser` implementation
- `mnemo-core/mnemo/parsers/markdown.py` — `MarkdownParser` implementation
- `mnemo-core/mnemo/parsers/html.py` — `HTMLParser` implementation
- `mnemo-core/mnemo/parsers/json_parser.py` — `JSONParser` implementation
- `mnemo-core/mnemo/parsers/image.py` — `StandaloneImageParser` implementation
- `mnemo-core/mnemo/ocr.py` — OCR subsystem and orchestration
- `mnemo-core/mnemo/models/ocr.py` — `OCRCapability` and `OCRProfile` models

---

## 2. PARSER STACK SPECIFICATION & PRODUCTION STATUS

| Format Family | Extensions | MIME Type(s) | Parser Class | Interface Version | Production Status | Text Blocks | Table Blocks | Image Assets | OCR Support | Usability / Dependencies |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **PDF** | `.pdf` | `application/pdf` | `PDFParser` | `ParserInterfaceV2` | **NATIVE / PRODUCTION** | Yes (`RawTextBlock`, `RawHeadingBlock`, `RawListBlock`) | Yes (`RawTableBlock`) | Yes (`RawImageBlock` + `TransientAsset`) | No (`supports_ocr=False`) | **Native / Unconditional.** Backed by `fitz` (PyMuPDF). Fully usable in production. |
| **DOCX** | `.docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | `DOCXParser` | `ParserInterfaceV2` | **NATIVE / PRODUCTION** | Yes (`RawTextBlock`, `RawHeadingBlock`, `RawListBlock`) | Yes (`RawTableBlock`) | Yes (`RawImageBlock` + `TransientAsset`) | No (`supports_ocr=False`) | **Native / Unconditional.** Backed by `python-docx` and XML relationship inspection. |
| **PPTX** | `.pptx` | `application/vnd.openxmlformats-officedocument.presentationml.presentation` | `PPTXParser` | `ParserInterfaceV2` | **NATIVE / PRODUCTION** | Yes (`RawHeadingBlock` slide titles, `RawTextBlock` body text) | Yes (`RawTableBlock`) | Yes (`RawImageBlock` + `TransientAsset` slide drawings) | No (`supports_ocr=False`) | **Native / Unconditional.** Pure OOXML ZIP parsing via standard library `xml.etree` + `zipfile`. |
| **XLSX** | `.xlsx` | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` | `XLSXParser` | `ParserInterfaceV2` | **NATIVE / PRODUCTION** | Headings only (Sheet names as `RawHeadingBlock`) | Yes (`RawTableBlock`, row-partitioned) | Yes (`RawImageBlock` + `TransientAsset` drawing anchors) | No (`supports_ocr=False`) | **Native / Unconditional.** Backed by `openpyxl` (read-only mode). Partitions large sheets (>50 rows). |
| **CSV / TSV** | `.csv`, `.tsv` | `text/csv`, `text/tab-separated-values` | `CSVParser` | `ParserInterfaceV1` | **NATIVE / PRODUCTION** | No (Tables only) | Yes (`RawTableBlock`, token-budgeted ~400 tokens) | No | No (`supports_ocr=False`) | **Native / Unconditional.** Standard library `csv` with `Sniffer`. Token-bounded partitioning. |
| **Plain Text** | `.txt`, `.log` | `text/plain` | `PlainTextParser` | `ParserInterfaceV1` | **NATIVE / PRODUCTION** | Yes (`RawTextBlock` split by double newline) | No | No | No (`supports_ocr=False`) | **Native / Unconditional.** Direct UTF-8 decoding. |
| **Code** | `.py`, `.js`, `.ts`, `.tsx`, `.jsx`, `.java`, `.go`, `.rs`, `.c`, `.h`, `.cpp`, `.cc`, `.cxx`, `.hpp` | `text/plain` (via extension fallback) | `PlainTextParser` | `ParserInterfaceV1` | **NATIVE / PRODUCTION** | Yes (`RawCodeBlock` with language tags) | No | No | No (`supports_ocr=False`) | **Native / Unconditional.** Direct text parsing with extension-to-language mapping. |
| **Markdown** | `.md`, `.markdown` | `text/markdown` | `MarkdownParser` | `ParserInterfaceV2` | **NATIVE / PRODUCTION** | Yes (`RawTextBlock`, `RawHeadingBlock`, `RawListBlock`, `RawCodeBlock`) | Yes (`RawTableBlock`) | Yes (`RawImageBlock` data-URI assets) | No (`supports_ocr=False`) | **Native / Unconditional.** Backed by `markdown-it-py`. |
| **HTML** | `.html`, `.htm` | `text/html` | `HTMLParser` | `ParserInterfaceV2` | **NATIVE / PRODUCTION** | Yes (`RawTextBlock`, `RawHeadingBlock`, `RawListBlock`, `RawCodeBlock`) | Yes (`RawTableBlock`) | Yes (`RawImageBlock` data-URI assets) | No (`supports_ocr=False`) | **Native / Unconditional.** Backed by `BeautifulSoup` + `readability-lxml`. |
| **JSON** | `.json` | `application/json` | `JSONParser` | `ParserInterfaceV1` | **NATIVE / PRODUCTION** | Yes (`RawTextBlock` with key-path context) | No | No | No (`supports_ocr=False`) | **Native / Unconditional.** Flattens nested keys into contextual prose blocks. |
| **Standalone Image** | `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.tif`, `.tiff`, `.bmp`, `.svg` | `image/png`, `image/jpeg`, `image/gif`, `image/webp`, `image/tiff`, `image/bmp`, `image/svg+xml` | `StandaloneImageParser` | `ParserInterfaceV2` | **NATIVE / PRODUCTION** | **NO TEXT EXTRACTED** | No | Yes (Wraps payload as authoritative `TransientAsset`) | No (`supports_ocr=False`) | **Native / Unconditional.** Ingests image bytes for asset foundation. Text extraction requires separate OCR provider. |

---

## 3. OCR SUBSYSTEM AUDIT (NOT NATIVE / UNCONDITIONAL)

Inspection of `mnemo-core/mnemo/ocr.py` and `mnemo-core/mnemo/models/ocr.py` confirms:

1. **Parsers Do Not Execute OCR:** Every parser explicitly reports `supports_ocr=False` in its `ParserCapabilities`.
2. **Provider-Backed Architecture:** OCR is an asynchronous, decoupled pipeline requiring an external `OCRProviderV1` implementation.
3. **Budget and Consent Gating:** OCR jobs require `ProcessingBudget` verification and user `ProcessingConsent`. Jobs will fail-closed if unconfigured or unbudgeted.
4. **Conclusion for Evaluation:** Scanned documents, image-only PDFs, or raster image files **CANNOT** be assumed to produce searchable text in standard evaluation runs. Phase 8.6 format-diversity candidates must contain **native selectable Unicode text**, not scanned bitmap images.

---

## 4. FORMATS NOT SUPPORTED (HARD NEGATIVES)

The following formats have **zero parser implementation** in the repository and must be rejected:
- Legacy Microsoft Word (`.doc`) — Binary Compound Document format
- Legacy Microsoft Excel (`.xls`) — Binary BIFF format
- Legacy Microsoft PowerPoint (`.ppt`) — Binary presentation format
- OpenDocument formats (`.odt`, `.ods`, `.odp`)
- Electronic Publication (`.epub`)
- Rich Text Format (`.rtf`)
- Audio / Video media (`.mp3`, `.wav`, `.mp4`, etc.)

---

## 5. EXISTING FORMAT REPRESENTATION IN PHASE 8.5 GOLDEN CORPUS

The frozen Phase 8.5 Golden Corpus (`goldenDataset/Phase 8.5 Evaluation Corpus/`, 44 files) currently exercises:
- `PDFParser`: 12 files (11 English, 1 Hindi/Bilingual Ramayana)
- `XLSXParser`: 5 files (All English)
- `StandaloneImageParser`: 8 files (JPG/JPEG personal photos, no text)
- `PlainTextParser` (Code): 12 files (11 JS, 1 Python)
- `PPTXParser`: 2 files (Both English)
- `DOCXParser`: 1 file (English)
- `HTMLParser`: 1 file (English)
- `MarkdownParser`: 1 file (English)
- `CSVParser`: 1 file (English)
- `PlainTextParser` (Text): 1 file (English)

### Multilingual Deficit in Frozen Corpus:
- **English:** Represented across 10 format families.
- **Hindi:** Represented in exactly 2 PDF files (`Valmiki Ramayana` and `Act 2. panch-parmeshwar-by-munshi-premchand.pdf`). Zero DOCX, zero PPTX, zero XLSX.
- **Marathi:** Represented in exactly 1 PDF (`manuscript.pdf`, 10 chunks). **Zero representation in DOCX, PPTX, XLSX, CSV, Markdown, or HTML.**

---

## 6. PHASE 8.6 FORMAT-DIVERSITY OBJECTIVE

To establish true parser-path evaluation parity, Phase 8.6 must prioritize:
1. **PDF Expansion:** Authoritative native Hindi and Marathi PDFs containing rich continuous prose and tables.
2. **DOCX Introduction:** Native Hindi and/or Marathi `.docx` documents containing Devanagari Unicode paragraphs and headings.
3. **PPTX Introduction:** Native Hindi and/or Marathi `.pptx` presentations containing slide headings and bullet points.
4. **Avoid TXT-Only Fallacy:** Plain text (`.txt`) files exercise only `PlainTextParser` and provide zero verification of PyMuPDF table extraction, Word heading hierarchies, or PowerPoint slide segmentation.

---

*Audit Complete — 2026-09-03*
*Repository state: Phase 8.5 FROZEN / UNCHANGED*
