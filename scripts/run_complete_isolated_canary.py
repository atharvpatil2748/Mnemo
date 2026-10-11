"""Run an entirely new, non-serving, two-document multimodal rebuild canary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mnemo_server.tools.isolated_rebuild import run_complete_canary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    authority = parser.add_mutually_exclusive_group(required=True)
    authority.add_argument("--source-database", type=Path)
    authority.add_argument("--source-manifest", type=Path)
    parser.add_argument("--include", action="append", required=True)
    parser.add_argument("--paddle-detection-dir", type=Path, required=True)
    parser.add_argument("--paddle-recognition-dir", type=Path, required=True)
    parser.add_argument("--paddle-detection-sha256", required=True)
    parser.add_argument("--paddle-recognition-sha256", required=True)
    parser.add_argument("--paddle-language", required=True)
    parser.add_argument("--vision-model", required=True)
    parser.add_argument("--vision-revision", required=True)
    parser.add_argument("--clip-snapshot", type=Path, required=True)
    parser.add_argument("--visual-model", required=True)
    parser.add_argument("--visual-revision", required=True)
    parser.add_argument("--bge-cache", type=Path, required=True)
    parser.add_argument("--paddle-device", default="cpu")
    parser.add_argument("--paddle-python", type=Path)
    parser.add_argument("--visual-device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--bge-device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args()
    result = run_complete_canary(
        workspace=args.workspace,
        corpus=args.corpus,
        source_database=args.source_database,
        source_manifest=args.source_manifest,
        includes=tuple(args.include),
        paddle_detection_dir=args.paddle_detection_dir,
        paddle_recognition_dir=args.paddle_recognition_dir,
        paddle_detection_sha256=args.paddle_detection_sha256,
        paddle_recognition_sha256=args.paddle_recognition_sha256,
        paddle_language=args.paddle_language,
        vision_model=args.vision_model,
        vision_revision=args.vision_revision,
        clip_snapshot=args.clip_snapshot,
        visual_model=args.visual_model,
        visual_revision=args.visual_revision,
        bge_cache=args.bge_cache,
        paddle_device=args.paddle_device,
        paddle_python=args.paddle_python,
        visual_device=args.visual_device,
        bge_device=args.bge_device,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["activation"] != "complete_v2_retrieval_ready":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
