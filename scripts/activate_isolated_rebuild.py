"""Activate one exact complete generation set in a disposable rebuild runtime."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from uuid import UUID

from mnemo.phase85.rebuild_runtime import resolve_governed_rebuild_runtime
from mnemo_server.tools.isolated_activation import (
    REQUIRED,
    activate_isolated_generation_set,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--notebook-id", type=UUID, required=True)
    parser.add_argument("--generation", action="append", required=True)
    parser.add_argument("--vector-space", required=True)
    parser.add_argument("--embedding-model-identity", required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve(strict=True)
    runtime = args.runtime.resolve(strict=True)
    resolve_governed_rebuild_runtime(
        workspace=workspace, runtime=runtime, notebook_id=args.notebook_id
    )
    generations: dict[str, UUID] = {}
    for item in args.generation:
        capability, separator, identifier = item.partition("=")
        if not separator or capability not in REQUIRED or capability in generations:
            raise ValueError("generation selection is invalid or duplicated")
        generations[capability] = UUID(identifier)
    result = asyncio.run(
        activate_isolated_generation_set(
            database=runtime / "mnemo.db",
            notebook_id=args.notebook_id,
            generation_ids=generations,
            vector_space=args.vector_space,
            embedding_model_identity=args.embedding_model_identity,
            report_path=runtime / "activation-decision.json",
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result.get("active", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
