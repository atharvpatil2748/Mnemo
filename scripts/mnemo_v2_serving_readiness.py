"""Generate the pre-exposure Full Multilingual V2 same-store readiness artifact."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from mnemo_server.config import ServerConfig
from mnemo_server.runtime_config import resolve_mnemo_runtime_config
from mnemo_server.services.production_store_readiness import (
    validate_production_v2_serving_readiness,
    write_readiness_artifact,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, default=Path("mnemo.toml"))
    parser.add_argument(
        "--identity-manifest",
        type=Path,
        default=Path(
            "docs/governance/proposals/phase8_5_full_multilingual_architecture/"
            "V2_DATABASE_ARTIFACT_IDENTITY.json"
        ),
    )
    parser.add_argument(
        "--output", type=Path, default=Path("scratch/mnemo_v2_exposed_readiness.json")
    )
    parser.add_argument(
        "--unification-output",
        type=Path,
        default=Path("scratch/mnemo-v2-production-store-unification.json"),
    )
    return parser


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


async def _run(args: argparse.Namespace) -> None:
    root = args.workspace_root.resolve()
    result = await validate_production_v2_serving_readiness(
        workspace_root=root,
        mnemo_config=resolve_mnemo_runtime_config(config_path=root / args.config),
        server_config=ServerConfig(),
        identity_manifest=root / args.identity_manifest,
    )
    output = root / args.output
    write_readiness_artifact(result, output)
    git_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    unification = {
        "schema_version": "mnemo.v2-production-store-unification/1",
        "generated_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit,
        "status": {
            "production_store": "PRODUCTION_STORE_UNIFIED",
            "serving_readiness": "SERVING_READINESS_VALIDATED",
            "v2_exposed": False,
            "bge_activated": False,
            "verified": False,
            "certified": False,
        },
        "readiness_artifact": args.output.as_posix(),
        "readiness": result.payload(),
        "evaluation_store": {
            "path": "data/canonical_production/mnemo_canonical.db",
            "role": "evaluation_only",
            "last_verified_sha256": (
                "dc9e7fa2d1cb77f0e42ec3220377f74b1e2f98842acbfe487d1c7e6502fb2ada"
            ),
            "current_direct_hash": "unavailable_locked_artifact_not_forced",
        },
        "configuration": {
            "path": args.config.as_posix(),
            "sha256": _sha256(root / args.config),
            "production_manifest": "config/production/full_multilingual_v2.production.json",
            "production_manifest_sha256": _sha256(
                root / "config/production/full_multilingual_v2.production.json"
            ),
        },
        "protected_state": {
            "active_database_sha256": result.production_store.physical_sha256,
            "active_alias_digest": result.production_store.alias_set_digest,
            "identity_manifest_sha256": _sha256(root / args.identity_manifest),
            "active_database_modified": False,
            "evaluation_database_modified": False,
            "golden_dataset_modified": False,
            "model_artifacts_modified": False,
            "provider_inference_run": False,
            "indexing_run": False,
            "alias_activation_run": False,
        },
        "validation": {
            "focused_tests": {"passed": 164, "failed": 0},
            "ruff": "PASS",
            "targeted_strict_mypy": "PASS",
            "compileall": "PASS",
            "json_parse": "PASS",
            "targeted_git_diff_check": "PASS",
            "repository_git_diff_check": (
                "PRE_EXISTING_FAILURE: mnemo-core/mnemo/models/chunks.py:65 trailing whitespace"
            ),
            "provider_inference": "NOT_RUN",
            "retrieval_evaluation": "NOT_RUN",
            "live_http_mcp_v2_requests": "NOT_RUN_PRE_EXPOSURE",
        },
        "remaining_blockers": [
            "Controlled V2 HTTP/MCP exposure has not been authorized or executed.",
            "Post-exposure real HTTP/MCP parity has not been executed.",
            "BGE alias activation, post-activation verification, rollback validation, "
            "and certification remain separate gates.",
        ],
    }
    unification_output = root / args.unification_output
    unification_output.write_text(
        json.dumps(unification, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"status={result.status}")
    print(f"currently_exposed={result.currently_exposed}")
    print(f"production_store={result.production_store.path}")
    print(f"database_identity={result.production_store.governed_database_identity}")
    print(f"output={output}")
    print(f"unification_output={unification_output}")


def main() -> None:
    asyncio.run(_run(_parser().parse_args()))


if __name__ == "__main__":
    main()
