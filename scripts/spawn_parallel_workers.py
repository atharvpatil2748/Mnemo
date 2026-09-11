import asyncio
from pathlib import Path
from uuid import UUID

from mnemo.ocr import OCRProcessingOperation
from mnemo.processing import ProcessingAdmissionProfile, ProcessingWorker
from mnemo.storage.filesystem import FilesystemBlobStore
from mnemo.storage.sqlite import SQLiteStore
from mnemo.vision import VisionProcessingOperation, VisualEmbeddingProcessingOperation
from phase8_5_11_derived_pipeline import (
    CLIPVisualProvider,
    OllamaVisionProvider,
    TesseractProvider,
)


async def _worker_loop(store, blobs, tess, vision, clip, notebook_id, worker_id):
    operations = {
        "ocr": OCRProcessingOperation(
            catalog=store,
            ocr_store=store,
            job_store=store,
            asset_reader=blobs,
            providers={tess.provider_identity: tess},
        ),
        "vision_analysis": VisionProcessingOperation(
            catalog=store,
            vision_store=store,
            job_store=store,
            asset_reader=blobs,
            providers={vision.provider_identity: vision},
        ),
        "visual_embedding": VisualEmbeddingProcessingOperation(
            catalog=store,
            vision_store=store,
            job_store=store,
            asset_reader=blobs,
            providers={clip.provider_identity: clip},
        ),
    }
    worker = ProcessingWorker(
        store=store,
        actor_id="phase8.5.11-evaluator",
        notebook_id=notebook_id,
        worker_id=worker_id,
        operations=operations,
        admission_profile=ProcessingAdmissionProfile(
            max_active_workers=1,
            max_pages=1,
            max_pixels=100_000_000,
            max_images=1,
            max_bytes=25_000_000,
            max_cloud_requests=0,
        ),
    )
    processed = 0
    while await worker.run_once():
        processed += 1
    print(f"[{worker_id}] finished, processed {processed} jobs.")


async def main():
    db_path = Path("scratch/phase8_5_wp16/eval-20260828-01/mnemo.db")
    blobs_path = Path("scratch/phase8_5_wp16/eval-20260828-01/files")
    tessdata = Path("D:/Mnemo/phase8.5.11-models/tessdata")
    clip_path = Path(
        "D:/Mnemo/phase8.5.11-models/huggingface/hub/models--openai--clip-vit-large-patch14/snapshots/32bd64288804d66eefd0ccbe215aa642df71cc41"
    )
    notebook_id = UUID("df9c20cf-85fe-529c-902e-2e9e68193fbe")

    store = SQLiteStore(db_path.resolve())
    blobs = FilesystemBlobStore(blobs_path.resolve())
    await store.open()
    await blobs.open()

    tess = TesseractProvider(tessdata.resolve())
    vision = OllamaVisionProvider("qwen2.5vl:latest")
    clip = CLIPVisualProvider(
        clip_path.resolve(),
        model_identity="openai/clip-vit-large-patch14",
        model_revision="32bd64288804d66eefd0ccbe215aa642df71cc41",
    )

    # Run 4 parallel worker tasks
    tasks = [
        asyncio.create_task(
            _worker_loop(store, blobs, tess, vision, clip, notebook_id, f"parallel-worker-{i}")
        )
        for i in range(1, 5)
    ]
    await asyncio.gather(*tasks)
    await store.close()
    await blobs.close()


if __name__ == "__main__":
    asyncio.run(main())
