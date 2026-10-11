"""Provider normalization tests; no model download or corpus mutation."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import io
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from mnemo.models.ocr import OCRRequest
from mnemo.ocr_paddle import (
    PaddleOCRConfiguration,
    PaddleOCRProvider,
    _model_tree_hash,
    paddle_ocr_profile,
)
from PIL import Image


def _config() -> PaddleOCRConfiguration:
    return PaddleOCRConfiguration(
        package_version="3.4.1",
        model_identity="devanagari_PP-OCRv3_mobile_rec",
        model_revision="approved-test-revision",
        detection_model_dir=Path("not-provisioned/detection"),
        recognition_model_dir=Path("not-provisioned/recognition"),
        detection_model_sha256="a" * 64,
        recognition_model_sha256="b" * 64,
        language="hi",
    )


def _request(config: PaddleOCRConfiguration) -> OCRRequest:
    content = b"not-a-real-image-in-injected-runner"
    return OCRRequest(
        actor_id="authorized-test-actor",
        notebook_id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        occurrence_id=uuid4(),
        asset_id=uuid4(),
        asset_content_hash=hashlib.sha256(content).hexdigest(),
        media_type="image/png",
        profile=paddle_ocr_profile(
            config,
            profile_id="paddle-hi-test",
            scope_identity="isolated-notebook-test",
            max_output_characters=1000,
        ),
    )


async def _not_cancelled() -> bool:
    return False


def test_paddle_ocr_normalizes_order_geometry_confidence_and_script() -> None:
    config = _config()
    request = _request(config)
    provider = PaddleOCRProvider(
        config,
        runner=lambda _: [
            {
                "res": {
                    "rec_texts": [" L = Iω ", " कोणीय संवेग "],
                    "rec_scores": [0.95, 0.65],
                    "rec_boxes": [[1, 2, 30, 40], [2, 42, 39, 65]],
                }
            }
        ],
    )
    result = asyncio.run(provider.recognize(request, b"fixture", _not_cancelled))
    assert result.derivation_id == request.derivation_id
    assert result.regions[0].text == "L = Iω"
    assert result.regions[1].text == "कोणीय संवेग"
    assert result.regions[0].bounding_box == (1.0, 2.0, 30.0, 40.0)
    assert [region.order_index for region in result.regions] == [0, 1]
    assert result.regions[1].language is not None
    assert result.regions[1].language.script == "Deva"
    assert result.content_hash


def test_paddle_ocr_identity_changes_with_configuration() -> None:
    config = _config()
    first = _request(config)
    changed = replace(config, recognition_model_sha256="c" * 64)
    second = replace(
        first,
        profile=paddle_ocr_profile(
            changed,
            profile_id=first.profile.profile_id,
            scope_identity="isolated-notebook-test",
            max_output_characters=first.profile.max_output_characters,
        ),
    )
    assert first.cache_key != second.cache_key
    assert first.derivation_id != second.derivation_id
    assert first.profile.generation_id != second.profile.generation_id
    threshold_change = replace(config, high_confidence_threshold=0.9)
    assert (
        paddle_ocr_profile(
            threshold_change,
            profile_id=first.profile.profile_id,
            scope_identity="isolated-notebook-test",
            max_output_characters=first.profile.max_output_characters,
        ).generation_id
        != first.profile.generation_id
    )
    raster_change = replace(config, external_rasterizer_identity="windows_wmp_first_frame_png_v1")
    assert (
        paddle_ocr_profile(
            raster_change,
            profile_id="hi",
            scope_identity="isolated-notebook-test",
            max_output_characters=1000,
        ).generation_id
        != first.profile.generation_id
    )


def test_paddle_ocr_admits_gif_and_governed_wmp_conversion() -> None:
    config = replace(_config(), external_rasterizer_identity="windows_wmp_first_frame_png_v1")
    observed: list[bytes] = []

    def predict(data: bytes) -> list[dict[str, object]]:
        observed.append(data)
        return [{"rec_texts": [], "rec_scores": [], "rec_boxes": []}]

    provider = PaddleOCRProvider(
        config, runner=predict, external_rasterizer=lambda _: b"rasterized-png"
    )
    capability = asyncio.run(provider.capabilities())
    assert "image/gif" in capability.supported_media_types
    assert "image/vnd.ms-photo" in capability.supported_media_types
    request = replace(_request(config), media_type="image/vnd.ms-photo")
    result = asyncio.run(provider.recognize(request, b"original-wmp", _not_cancelled))
    assert observed == [b"rasterized-png"]
    assert result.provider.capability == capability
    assert config.identity_metadata["animated_image_frame_policy"] == "first_frame"
    with pytest.raises(ValueError, match="rasterizer and its governed identity"):
        PaddleOCRProvider(config, runner=predict)
    plain = PaddleOCRProvider(_config(), runner=predict)
    assert "image/vnd.ms-photo" not in asyncio.run(plain.capabilities()).supported_media_types


def test_paddle_ocr_rejects_unprovisioned_model() -> None:
    with pytest.raises(RuntimeError, match="not provisioned"):
        PaddleOCRProvider(_config())


def test_paddle_ocr_rejects_unsupported_language_series() -> None:
    assert replace(_config(), ocr_version="PP-OCRv5").ocr_version == "PP-OCRv5"
    with pytest.raises(ValueError, match="combination"):
        replace(_config(), ocr_version="PP-OCRv2")
    with pytest.raises(ValueError, match="checked dependency"):
        replace(_config(), package_version="3.5.0")
    with pytest.raises(ValueError, match="thresholds"):
        replace(_config(), medium_confidence_threshold=0.9)


def test_paddle_ocr_checks_local_model_tree_hashes(tmp_path: Path) -> None:
    detection = tmp_path / "detection"
    recognition = tmp_path / "recognition"
    detection.mkdir()
    recognition.mkdir()
    (detection / "model.pdiparams").write_bytes(b"approved detection fixture")
    (recognition / "model.pdiparams").write_bytes(b"approved recognition fixture")
    config = replace(
        _config(),
        detection_model_dir=detection,
        recognition_model_dir=recognition,
        detection_model_sha256=_model_tree_hash(detection),
        recognition_model_sha256=_model_tree_hash(recognition),
    )
    PaddleOCRProvider(config)
    (recognition / "model.pdiparams").write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="digest"):
        PaddleOCRProvider(config)


def test_paddle_ocr_rejects_profile_mismatch_and_bad_output() -> None:
    config = _config()
    request = _request(config)
    provider = PaddleOCRProvider(
        config,
        runner=lambda _: [{"rec_texts": ["text"], "rec_scores": [], "rec_boxes": []}],
    )
    with pytest.raises(ValueError, match="inconsistent lengths"):
        asyncio.run(provider.recognize(request, b"fixture", _not_cancelled))
    changed = replace(request.profile, model_revision="unapproved")
    with pytest.raises(ValueError, match="model mismatch"):
        asyncio.run(
            provider.recognize(replace(request, profile=changed), b"fixture", _not_cancelled)
        )


def test_paddle_ocr_cancellation() -> None:
    provider = PaddleOCRProvider(_config(), runner=lambda _: ())

    async def cancelled() -> bool:
        return True

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(provider.recognize(_request(_config()), b"fixture", cancelled))


def test_paddle_ocr_dependency_unavailable_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_name: str) -> str:
        raise importlib.metadata.PackageNotFoundError("paddleocr")

    monkeypatch.setattr(importlib.metadata, "version", missing)
    provider = PaddleOCRProvider(_config(), runner=lambda _: ())
    with pytest.raises(RuntimeError, match="not installed"):
        provider._predict(b"fixture")


def test_paddle_ocr_binds_explicit_model_names_in_runtime_and_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = replace(
        _config(),
        language="en",
        ocr_version="PP-OCRv5",
        detection_model_name="PP-OCRv5_server_det",
        recognition_model_name="en_PP-OCRv5_mobile_rec",
    )
    observed: dict[str, object] = {}

    class FakePaddle:
        def __init__(self, **kwargs: object) -> None:
            observed.update(kwargs)

        def predict(self, _image: object) -> list[SimpleNamespace]:
            return [SimpleNamespace(json={"rec_texts": [], "rec_scores": [], "rec_boxes": []})]

    actual_import = __import__("importlib").import_module

    def fake_import(name: str) -> object:
        if name == "paddleocr":
            return SimpleNamespace(PaddleOCR=FakePaddle)
        return actual_import(name)

    monkeypatch.setattr("mnemo.ocr_paddle.importlib.import_module", fake_import)
    monkeypatch.setattr("mnemo.ocr_paddle.importlib.metadata.version", lambda _: "3.4.1")
    image = Image.new("RGB", (4, 4), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    PaddleOCRProvider(config, runner=lambda _: ())._predict(buffer.getvalue())
    assert observed["text_detection_model_name"] == "PP-OCRv5_server_det"
    assert observed["text_recognition_model_name"] == "en_PP-OCRv5_mobile_rec"
    changed = replace(config, recognition_model_name="en_PP-OCRv5_server_rec")
    assert (
        paddle_ocr_profile(
            config, profile_id="en", scope_identity="notebook", max_output_characters=100
        ).generation_id
        != paddle_ocr_profile(
            changed, profile_id="en", scope_identity="notebook", max_output_characters=100
        ).generation_id
    )
