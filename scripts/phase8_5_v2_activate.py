"""Perform only the governed first Full Multilingual V2 READY-to-ACTIVE transition."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mnemo-core"))

from mnemo.phase85.v2_activation import execute_v2_activation  # noqa: E402


def main() -> None:
    proposal_root = ROOT / "docs/governance/proposals/phase8_5_full_multilingual_architecture"
    print(
        json.dumps(
            execute_v2_activation(workspace_root=ROOT, proposal_root=proposal_root),
            sort_keys=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
