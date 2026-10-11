"""The visual text encoder must use the matched local CLIP space."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from mnemo.retrieval.clip_text_query import LocalCLIPTextQueryProvider


@pytest.mark.anyio
async def test_clip_query_uses_matching_snapshot_and_normalized_cosine_vector(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import torch
    from transformers import CLIPModel, CLIPProcessor

    class Processor:
        def __call__(self, **kwargs: object) -> dict[str, object]:
            assert kwargs["text"] == ["cutting tool"]
            return {
                "input_ids": torch.ones((1, 2), dtype=torch.long),
                "attention_mask": torch.ones((1, 2), dtype=torch.long),
            }

    class Model:
        config = SimpleNamespace(projection_dim=768)

        def eval(self) -> None:
            pass

        def text_model(self, **kwargs: object) -> object:
            assert "input_ids" in kwargs
            return SimpleNamespace(pooler_output=torch.ones((1, 768)))

        def text_projection(self, values: object) -> object:
            return values

    def load_processor(snapshot: Path, *, local_files_only: bool) -> object:
        assert snapshot == tmp_path and local_files_only
        return Processor()

    def load_model(snapshot: Path, *, local_files_only: bool) -> object:
        assert snapshot == tmp_path and local_files_only
        return Model()

    monkeypatch.setattr(CLIPProcessor, "from_pretrained", load_processor)
    monkeypatch.setattr(CLIPModel, "from_pretrained", load_model)
    with pytest.raises(ValueError, match="dimension"):
        LocalCLIPTextQueryProvider(
            snapshot=tmp_path, profile_id="clip", shared_space_id="clip-space", dimensions=512
        )
    provider = LocalCLIPTextQueryProvider(
        snapshot=tmp_path, profile_id="clip", shared_space_id="clip-space", dimensions=768
    )
    assert await provider.ready()
    with pytest.raises(ValueError, match="blank"):
        await provider.embed_text(" ")
    vector = await provider.embed_text("cutting tool")
    assert vector.profile_id == "clip"
    assert vector.shared_space_id == "clip-space"
    assert len(vector.values) == 768
    assert sum(value * value for value in vector.values) == pytest.approx(1.0)
    with pytest.raises(ValueError, match="snapshot"):
        LocalCLIPTextQueryProvider(
            snapshot=tmp_path / "missing",
            profile_id="clip",
            shared_space_id="clip-space",
            dimensions=768,
        )
    Model.config = SimpleNamespace(projection_dim=512)
    with pytest.raises(ValueError, match="projection dimension"):
        LocalCLIPTextQueryProvider(
            snapshot=tmp_path,
            profile_id="clip",
            shared_space_id="clip-space",
            dimensions=768,
        )
