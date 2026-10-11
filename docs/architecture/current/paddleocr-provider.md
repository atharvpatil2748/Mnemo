# PaddleOCR V1 provider: opt-in production-path contract

`mnemo.ocr_paddle.PaddleOCRProvider` implements `OCRProviderV1` and is injected
into the existing `OCRProcessingOperation`. It does not change canonical V1 IR,
authorization, the V2 planner, or projection activation.

Install the `mnemo-core[ocr-paddle]` optional dependency from the checked lock.
Provision detection and recognition model directories separately; construction
fails if either tree is absent or its deterministic SHA-256 tree digest differs
from the approved configuration. No model is downloaded by provider construction.
The profile binds PaddleOCR package version, model identity/revision, tree
digests, language (`en`, `hi`, `mr`), device, orientation/unwarping options and
pixel limit. `paddle_ocr_generation_id` derives a new generation identity when
any of those values or the governed notebook/run scope changes. Requests and
derivations also bind the exact profile and immutable source-asset hash.
For the pinned PaddleOCR 3.4.1 API, `hi` and `mr` use the documented PP-OCRv3
language path; `en` may use PP-OCRv5. A PP-OCRv5 `lang=hi` or `lang=mr` profile
is rejected before any job is admitted. A later, explicitly verified package
and model revision may change this governed compatibility rule.

The adapter calls the PaddleOCR 3 `predict` API over decoded RGB image bytes,
normalizing `rec_texts`, `rec_scores` and `rec_boxes` to ordered `OCRRegion`
records. It preserves recognized text, page, box, confidence and observable
script. It does **not** label Devanagari as Hindi or Marathi without a language
detector; PaddleOCR's region result does not supply that distinction. The
worker enforces asset authorization and hash checks, page/pixel/output bounds,
wall-time and durable publication. Timeout/cancellation prevents publication,
but Python cannot forcibly terminate a blocked native inference thread; an
isolated worker process is required for a hard native-process kill guarantee.

The existing `scripts/phase8_5_11_derived_pipeline.py` accepts
`--ocr-provider paddleocr` plus exact package/model revision, both model paths
and digests, and language/device options. Its default remains Tesseract for
historical replay. Do **not** run it on protected Phase 8.5 or existing Phase
8.6 databases. The next phase must create new isolated notebook/index identities,
execute derivations there, build OCR/Vision/Multilingual projections, validate
complete coverage, and only then perform separately governed activation and
retrieval/citation certification. This adapter has unit tests but has not yet
performed real PaddleOCR inference on the approved model artifacts.

Official API and model references: [PaddleOCR 3 OCR pipeline](https://www.paddleocr.ai/v3.4.1/en/version3.x/pipeline_usage/OCR.html),
[PP-OCRv5 multilingual model list](https://www.paddleocr.ai/latest/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html).
