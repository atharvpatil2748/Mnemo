"""Local CLIP text encoder for an explicitly matching active visual space."""

from __future__ import annotations

import asyncio
from pathlib import Path

from mnemo.interfaces.advanced_retrieval import (
    VisualQueryVector,
    VisualVectorMetric,
)


class LocalCLIPTextQueryProvider:
    """Use the text tower from the exact snapshot used for image embeddings."""

    def __init__(
        self,
        *,
        snapshot: Path,
        profile_id: str,
        shared_space_id: str,
        dimensions: int,
    ) -> None:
        if not snapshot.is_dir() or not profile_id or not shared_space_id:
            raise ValueError("compatible local CLIP snapshot and identities are required")
        if dimensions != 768:
            raise ValueError("CLIP text query dimension differs from the governed profile")
        from transformers import CLIPModel, CLIPProcessor

        self._processor = CLIPProcessor.from_pretrained(snapshot, local_files_only=True)
        self._model = CLIPModel.from_pretrained(snapshot, local_files_only=True)
        self._model.eval()  # type: ignore[no-untyped-call]
        if self._model.config.projection_dim != dimensions:
            raise ValueError("CLIP snapshot projection dimension is incompatible")
        self.profile_id = profile_id
        self._shared_space_id = shared_space_id
        self._dimensions = dimensions

    async def ready(self) -> bool:
        return True

    async def embed_text(self, query: str) -> VisualQueryVector:
        if not query.strip():
            raise ValueError("visual text query must not be blank")
        return await asyncio.to_thread(self._encode, query)

    def _encode(self, query: str) -> VisualQueryVector:
        import torch

        inputs = self._processor(text=[query], return_tensors="pt", padding=True, truncation=True)
        with torch.no_grad():
            output = self._model.text_model(
                input_ids=inputs["input_ids"], attention_mask=inputs["attention_mask"]
            )
            projected = self._model.text_projection(output.pooler_output)[0]
            normalized = projected / projected.norm()
        values = tuple(float(value) for value in normalized.detach().cpu().tolist())
        return VisualQueryVector(
            profile_id=self.profile_id,
            shared_space_id=self._shared_space_id,
            dimensions=self._dimensions,
            metric=VisualVectorMetric.COSINE,
            values=values,
        )
