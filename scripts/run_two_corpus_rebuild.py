"""Fail-closed 44+24 rebuild; each run replaces verified prior derived outputs."""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

from mnemo_server.tools.two_corpus_rebuild import (
    preview_cleanup,
    run_two_corpus_rebuild,
    validate_inputs,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--manifest-a", type=Path, required=True)
    parser.add_argument("--manifest-b", type=Path, required=True)
    parser.add_argument("--profile-a", type=Path, required=True)
    parser.add_argument("--profile-b", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    if args.preflight_only:
        checked = validate_inputs(
            manifest_a=args.manifest_a,
            manifest_b=args.manifest_b,
            profile_a=args.profile_a,
            profile_b=args.profile_b,
        )
        print(
            json.dumps(
                {
                    "manifest_verified": True,
                    "counts": [len(item[0]["sources"]) for item in checked],
                    "would_delete_on_rebuild": preview_cleanup(
                        workspace=args.workspace, validated=checked
                    ),
                    "note": (
                        "No notebook deleted or created; model inference not proved "
                        "by this preflight."
                    ),
                },
                indent=2,
            )
        )
        return
    try:
        result = run_two_corpus_rebuild(
            workspace=args.workspace,
            manifest_a=args.manifest_a,
            manifest_b=args.manifest_b,
            profile_a=args.profile_a,
            profile_b=args.profile_b,
        )
    except Exception:
        traceback.print_exc()
        print("TWO-CORPUS REBUILD: FAILED", flush=True)
        raise SystemExit(1) from None
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["complete"]:
        print(
            f"TWO-CORPUS REBUILD: FAILED (state={result['state']}; see {result['report_path']})",
            flush=True,
        )
        raise SystemExit(1)
    for label, notebook, count in zip(("A", "B"), result["notebooks"], (44, 24), strict=True):
        print(
            f"Notebook {label}: {notebook['notebook_id']} — {count}/{count} COMPLETE; "
            "all required representations COMPLETE; Full V2 ACTIVE",
            flush=True,
        )
    print("TWO-CORPUS REBUILD: COMPLETE", flush=True)
    print("Build integrity: PASS", flush=True)
    print("READY FOR EXTERNAL VALIDATION", flush=True)


if __name__ == "__main__":
    main()
