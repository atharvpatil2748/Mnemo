"""Offline, read-only query-provider probe; never touches notebook stores."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
from pathlib import Path
from uuid import uuid4

from mnemo.phase85.profiles import ModelProfileDocument
from mnemo.retrieval.multilingual_providers import BGEM3EmbeddingProvider

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path("D:/Mnemo/phase8.5.11-models/huggingface/hub")


async def probe_bge() -> dict[str, object]:
    component = (
        ModelProfileDocument.from_file(ROOT / "config/model_profiles/phase8_5_profiles.toml")
        .select("phase8_5_local_v1")
        .models["multilingual_embedding"]
    )
    provider = BGEM3EmbeddingProvider(component, generation_id=uuid4(), cache_folder=CACHE)
    try:
        await provider.initialize()
        ready = await provider.readiness()
        query = await provider.embed_query(
            query="A deliberately disposable test phrase.", language="en"
        )
        profile = await provider.profile()
        return {
            "provider": component.provider,
            "model": component.model,
            "revision": component.revision,
            "initialized": ready.initialized,
            "available_locally": ready.available_locally,
            "loadable": ready.loadable,
            "reason_code": ready.reason_code,
            "query_dimensions": len(query.vector),
            "query_l2_norm": math.sqrt(sum(value * value for value in query.vector)),
            "languages_declared": [value.value for value in profile.languages],
            "metric": profile.distance_metric,
            "normalized": profile.normalized,
            "vector_space": profile.vector_space,
            "notebook_bound_admission": "NOT_VERIFIED",
        }
    finally:
        await provider.close()


def probe_clip() -> dict[str, object]:
    from transformers import CLIPModel, CLIPProcessor

    snapshot = (
        CACHE
        / "models--openai--clip-vit-large-patch14"
        / "snapshots"
        / "32bd64288804d66eefd0ccbe215aa642df71cc41"
    )
    processor = CLIPProcessor.from_pretrained(snapshot, local_files_only=True)
    model = CLIPModel.from_pretrained(snapshot, local_files_only=True)
    model.eval()  # type: ignore[no-untyped-call]
    import torch

    inputs = processor(text=["A deliberately disposable test phrase."], return_tensors="pt")
    with torch.no_grad():
        output = model.text_model(
            input_ids=inputs["input_ids"], attention_mask=inputs["attention_mask"]
        )
        vector = model.text_projection(output.pooler_output)[0]
        vector = vector / vector.norm()
    return {
        "provider": "transformers-local",
        "model": "openai/clip-vit-large-patch14",
        "revision": snapshot.name,
        "query_dimensions": len(vector),
        "query_l2_norm": float(vector.norm()),
        "query_side_loaded": True,
        "asset_side_loaded": False,
        "asset_shared_space_match": "NOT_VERIFIED",
        "notebook_bound_admission": "NOT_VERIFIED",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=("bge", "clip"))
    args = parser.parse_args()
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"):
        os.environ[key] = "1"
    value = asyncio.run(probe_bge()) if args.provider == "bge" else probe_clip()
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
