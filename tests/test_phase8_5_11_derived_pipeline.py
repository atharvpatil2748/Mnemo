"""Focused contracts for the evaluation-notebook derived pipeline."""

import asyncio
import hashlib
import io
import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from mnemo.models import FrozenMetadata, VisionProfile, VisionRequest
from mnemo.storage.sqlite import SQLiteStore
from PIL import Image

from scripts.phase8_5_11_derived_pipeline import (
    VISION_PROMPT_TEMPLATE_ID,
    VISION_RESPONSE_SCHEMA,
    VISION_SYSTEM_PROMPT,
    VISION_USER_PROMPT,
    OllamaVisionProvider,
    _live_rows,
    vision_prompt_hash,
)


def test_vision_v2_contract_governs_low_information_images() -> None:
    assert VISION_PROMPT_TEMPLATE_ID == "mnemo-vision-safe/v3"
    assert "No discernible visual content." in VISION_SYSTEM_PROMPT
    assert "non-empty string" in VISION_USER_PROMPT
    properties = VISION_RESPONSE_SCHEMA["properties"]
    assert isinstance(properties, dict)
    assert properties["caption"] == {"type": "string", "minLength": 1, "maxLength": 1200}
    assert properties["observations"] == {
        "type": "array",
        "items": {"type": "string", "maxLength": 300},
        "maxItems": 6,
    }


def test_vision_v2_prompt_contract_has_stable_digest() -> None:
    first = vision_prompt_hash()
    second = vision_prompt_hash()

    assert first == second
    assert len(first) == 64
    int(first, 16)


def test_worker_observation_sees_live_wal_rows(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = SQLiteStore(tmp_path / "worker.db")
        await store.open()
        try:
            writer = store._require_open()
            await writer.execute("CREATE TABLE evidence(value TEXT)")
            await writer.execute("INSERT INTO evidence VALUES('persisted vision')")
            await writer.commit()
            assert await _live_rows(store, "SELECT value FROM evidence") == [("persisted vision",)]
        finally:
            await store.close()

    asyncio.run(scenario())


def _vision_fixture() -> tuple[VisionRequest, bytes]:
    encoded = io.BytesIO()
    Image.new("RGB", (24, 24), color="white").save(encoded, format="PNG")
    original = encoded.getvalue()
    profile = VisionProfile(
        profile_id="test-vision",
        provider_identity="ollama",
        model_identity="model",
        model_revision="revision",
        preprocessing=FrozenMetadata({"test": "bounded_json"}),
        analysis_schema_version=1,
        prompt_template_id=VISION_PROMPT_TEMPLATE_ID,
        prompt_hash=vision_prompt_hash(),
        language_hints=("en",),
        max_pixels=100_000,
        max_output_characters=8_000,
        max_observations=6,
        generation_id=uuid4(),
    )
    return (
        VisionRequest(
            actor_id="test",
            notebook_id=uuid4(),
            document_id=uuid4(),
            version_id=uuid4(),
            occurrence_id=uuid4(),
            asset_id=uuid4(),
            asset_content_hash=hashlib.sha256(original).hexdigest(),
            media_type="image/png",
            profile=profile,
        ),
        original,
    )


def test_vision_length_truncation_escalates_bounded_budget_without_fabricating() -> None:
    request, original = _vision_fixture()
    budgets: list[int] = []

    def respond(incoming: httpx.Request) -> httpx.Response:
        payload = json.loads(incoming.content)
        budgets.append(payload["options"]["num_predict"])
        assert payload["format"]["properties"]["caption"]["maxLength"] == 1200
        if len(budgets) == 1:
            return httpx.Response(
                200,
                json={"done_reason": "length", "message": {"content": '{"caption":"unfinished'}},
            )
        return httpx.Response(
            200,
            json={
                "done_reason": "stop",
                "message": {
                    "content": json.dumps(
                        {
                            "caption": "Visible printed formula",
                            "observations": ["A formula is present"],
                            "language_code": "en",
                            "script": "Latn",
                        }
                    )
                },
            },
        )

    async def scenario() -> None:
        provider = OllamaVisionProvider("model")
        await provider.close()
        provider._client = httpx.AsyncClient(
            base_url="http://test", transport=httpx.MockTransport(respond)
        )
        try:
            result = await provider.analyze(
                request, original, lambda: asyncio.sleep(0, result=False)
            )
            assert result.captions[0].text == "Visible printed formula"
            assert result.occurrence_id == request.occurrence_id
        finally:
            await provider.close()

    asyncio.run(scenario())
    assert budgets == [2048, 4096]


def test_vision_fails_closed_when_maximum_decoder_budget_is_exhausted() -> None:
    request, original = _vision_fixture()
    budgets: list[int] = []

    def respond(incoming: httpx.Request) -> httpx.Response:
        budgets.append(json.loads(incoming.content)["options"]["num_predict"])
        return httpx.Response(
            200,
            json={"done_reason": "length", "message": {"content": '{"caption":"unfinished'}},
        )

    async def scenario() -> None:
        provider = OllamaVisionProvider("model")
        await provider.close()
        provider._client = httpx.AsyncClient(
            base_url="http://test", transport=httpx.MockTransport(respond)
        )
        try:
            with pytest.raises(RuntimeError, match="exhausted the governed decoder budget"):
                await provider.analyze(request, original, lambda: asyncio.sleep(0, result=False))
        finally:
            await provider.close()

    asyncio.run(scenario())
    assert budgets == [2048, 4096]
