"""Rebuild query languages follow the governed provider capability, not corpus tags."""

from pathlib import Path

import pytest
from mnemo.phase85.profiles import ModelProfileDocument
from mnemo.phase85.rebuild_language_capability import load_rebuild_language_capability


def test_bge_rebuild_capability_is_bound_to_selected_model() -> None:
    root = Path(__file__).resolve().parents[3]
    component = (
        ModelProfileDocument.from_file(
            root / "config/model_profiles/full_multilingual_v2_profiles.toml"
        )
        .select("full_multilingual_v2_local_prebuild")
        .models["multilingual_embedding"]
    )
    capability = load_rebuild_language_capability(
        path=root / "config/rebuild/multilingual_embedding_capability.json",
        component=component,
    )
    assert capability.scope == "multilingual_unenumerated"
    assert capability.permits("query_embedding")
    assert not capability.permits("reranking")
    assert len(capability.identity) == 64
    with pytest.raises(ValueError, match="does not match"):
        load_rebuild_language_capability(
            path=root / "config/rebuild/multilingual_embedding_capability.json",
            component=component.model_copy(update={"revision": "different"}),
        )
