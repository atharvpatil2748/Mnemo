"""Build BGE-M3 evidence projections only in a new isolated rebuild runtime."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from uuid import UUID

from mnemo.phase85.isolated_multilingual import build_isolated_multilingual
from mnemo.phase85.rebuild_runtime import resolve_governed_rebuild_runtime


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--notebook-id", type=UUID, required=True)
    parser.add_argument("--cache-folder", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve(strict=True)
    runtime = args.runtime.resolve(strict=True)
    resolve_governed_rebuild_runtime(
        workspace=workspace, runtime=runtime, notebook_id=args.notebook_id
    )
    result = asyncio.run(
        build_isolated_multilingual(
            database=runtime / "mnemo.db",
            notebook_id=args.notebook_id,
            profile_file=workspace / "config/model_profiles/full_multilingual_v2_profiles.toml",
            cache_folder=args.cache_folder.resolve(strict=True),
            device=args.device,
            language_capability_file=(
                workspace / "config/rebuild/multilingual_embedding_capability.json"
            ),
        )
    )
    encoded = json.dumps(result, indent=2, sort_keys=True)
    if args.output is not None:
        target = args.output.resolve(strict=False)
        if target.parent != runtime:
            raise ValueError("multilingual report must remain inside isolated runtime")
        target.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
