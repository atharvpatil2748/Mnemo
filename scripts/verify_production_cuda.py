"""Local-only CUDA readiness check for the frozen production reranker.

Run with the project's existing .venv interpreter. No database or credential is read.
"""

from __future__ import annotations

import asyncio
import math
import os
from pathlib import Path

import torch
from mnemo.phase85.profiles import ModelProfileDocument, profile_snapshot
from mnemo.retrieval.multilingual_providers import (
    BGE_RERANKER_PRODUCTION_EXECUTION_V1,
    BGE_RERANKER_REVISION,
    BGEMultilingualReranker,
)
from mnemo_server.services.full_multilingual_v2_startup import PROFILE_NAME


async def main() -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("PRODUCTION_CUDA_UNAVAILABLE")
    tensor = torch.tensor([2.0, 3.0], device="cuda")
    if float((tensor * tensor).sum().item()) != 13.0:
        raise RuntimeError("PRODUCTION_CUDA_TENSOR_FAILED")

    root = Path(__file__).resolve().parents[1]
    cache = Path(os.environ["MNEMO_SERVER_FULL_MULTILINGUAL_V2_MODEL_CACHE"])
    if not cache.is_absolute():
        raise RuntimeError("PRODUCTION_MODEL_CACHE_NOT_ABSOLUTE")
    profile = profile_snapshot(
        ModelProfileDocument.from_file(
            root / "config/model_profiles/full_multilingual_v2_profiles.toml"
        ).select(PROFILE_NAME)
    )
    component = profile.components["multilingual_reranker"]
    if component.revision != BGE_RERANKER_REVISION:
        raise RuntimeError("PRODUCTION_RERANKER_REVISION_MISMATCH")
    execution = BGE_RERANKER_PRODUCTION_EXECUTION_V1
    if execution.device != "cuda" or execution.allow_device_fallback:
        raise RuntimeError("PRODUCTION_CPU_FALLBACK_REJECTED")
    reranker = BGEMultilingualReranker(component, cache_folder=cache, execution=execution)
    try:
        await reranker.initialize()
        runtime = reranker._runtime
        if runtime is None or runtime._model.device.type != "cuda":
            raise RuntimeError("PRODUCTION_RERANKER_NOT_ON_CUDA")
        scores = runtime.predict("What is the capital of India?", ("New Delhi is the capital.",))
        if len(scores) != 1 or not math.isfinite(scores[0]):
            raise RuntimeError("PRODUCTION_RERANKER_INFERENCE_FAILED")
    finally:
        await reranker.close()
    print("PRODUCTION_CUDA_READINESS=PASS")
    print(f"TORCH_BUILD={torch.__version__}")
    print(f"RERANKER_REVISION={component.revision}")


if __name__ == "__main__":
    asyncio.run(main())
