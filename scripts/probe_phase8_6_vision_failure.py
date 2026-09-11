"""Probe one retained Phase 8.6 Vision occurrence without mutating its database."""

from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import sqlite3
from pathlib import Path
from typing import Any
from uuid import UUID

from mnemo.models import FrozenMetadata, VisionProfile, VisionRequest
from phase8_5_11_derived_pipeline import (
    VISION_PROMPT_TEMPLATE_ID,
    OllamaVisionProvider,
    vision_prompt_hash,
)
from PIL import Image, ImageStat


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--occurrence", type=UUID, required=True)
    return parser.parse_args()


def _blob_path(root: Path, content_hash: str, mime_type: str) -> Path:
    extension = mimetypes.guess_extension(mime_type) or ".bin"
    return root / "files" / content_hash[:2] / content_hash[2:] / f"raw{extension}"


def _request(runtime: Path, occurrence: UUID) -> tuple[VisionRequest, Path]:
    database = (runtime / "mnemo.db").resolve(strict=True)
    uri = database.as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        row = connection.execute(
            "SELECT j.manifest,a.content_hash,a.mime_type "
            "FROM processing_jobs j "
            "JOIN asset_occurrences o ON o.occurrence_id=j.occurrence_id "
            "JOIN asset_catalog a ON a.asset_id=o.asset_id "
            "WHERE j.occurrence_id=? AND j.operation='vision_analysis'",
            (str(occurrence),),
        ).fetchone()
    if row is None:
        raise RuntimeError("retained Vision occurrence is absent")
    manifest = json.loads(row[0])
    values = manifest["configuration"]["vision"]
    model, separator, revision = manifest["model_identity"].rpartition("@")
    if not separator:
        raise RuntimeError("retained Vision model identity has no revision")
    profile = VisionProfile(
        profile_id=str(values["profile_id"]),
        provider_identity=str(manifest["provider_identity"]),
        model_identity=model,
        model_revision=revision,
        preprocessing=FrozenMetadata(values["preprocessing"]),
        analysis_schema_version=int(values["analysis_schema_version"]),
        prompt_template_id=str(values["prompt_template_id"]),
        prompt_hash=str(values["prompt_hash"]),
        language_hints=tuple(values["language_hints"]),
        max_pixels=int(values["max_pixels"]),
        max_output_characters=int(values["max_output_characters"]),
        max_observations=int(values["max_observations"]),
        generation_id=UUID(str(manifest["generation_id"])),
    )
    request = VisionRequest(
        actor_id=str(manifest["actor_id"]),
        notebook_id=UUID(str(manifest["notebook_id"])),
        document_id=UUID(str(manifest["document_id"])),
        version_id=UUID(str(manifest["version_id"])),
        occurrence_id=occurrence,
        asset_id=UUID(str(values["asset_id"])),
        asset_content_hash=str(values["asset_content_hash"]),
        media_type=str(values["media_type"]),
        profile=profile,
    )
    return request, _blob_path(runtime, str(row[1]), str(row[2]))


def _image_evidence(path: Path) -> dict[str, Any]:
    with Image.open(path) as source:
        image = source.convert("RGB")
        statistics = ImageStat.Stat(image)
        result = {
            "path": str(path),
            "size": list(image.size),
            "entropy": image.entropy(),
            "mean_rgb": statistics.mean,
            "stddev_rgb": statistics.stddev,
            "extrema_rgb": image.getextrema(),
        }
        image.close()
        return result


async def _run(args: argparse.Namespace) -> int:
    runtime = args.runtime.resolve(strict=True)
    request, blob = _request(runtime, args.occurrence)
    raw = blob.read_bytes()
    provider = OllamaVisionProvider(request.profile.model_identity)

    async def not_cancelled() -> bool:
        return False

    evidence: dict[str, Any] = {
        "schema": "mnemo.phase8.6-vision-failure-probe/1",
        "read_only": True,
        "runtime": str(runtime),
        "occurrence_id": str(args.occurrence),
        "asset_id": str(request.asset_id),
        "asset_content_hash": request.asset_content_hash,
        "model": request.profile.model_identity,
        "model_revision": request.profile.model_revision,
        "retained_request_prompt_template_id": request.profile.prompt_template_id,
        "probe_prompt_template_id": VISION_PROMPT_TEMPLATE_ID,
        "probe_prompt_hash": vision_prompt_hash(),
        "image": _image_evidence(blob),
    }
    try:
        result = await provider.analyze(request, raw, not_cancelled)
        evidence["status"] = "PASS"
        evidence["captions"] = [caption.text for caption in result.captions]
        evidence["observations"] = [item.value for item in result.observations]
    except BaseException as error:
        chain = []
        current: BaseException | None = error
        while current is not None:
            chain.append({"type": type(current).__name__, "message": str(current)})
            current = current.__cause__
        evidence["status"] = "FAIL"
        evidence["error_chain"] = chain
    finally:
        await provider._client.aclose()
    print(json.dumps(evidence, indent=2, sort_keys=True))
    print(f"RESULT: VISION_PROBE_{evidence['status']}")
    return 0 if evidence["status"] == "PASS" else 1


def main() -> int:
    return asyncio.run(_run(_arguments()))


if __name__ == "__main__":
    raise SystemExit(main())
