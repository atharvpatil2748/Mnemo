"""Execute the single governed Full Multilingual V2 build-to-READY operation."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mnemo-core"))

from mnemo.phase85.v2_index_build import FullMultilingualV2IndexBuildOperator  # noqa: E402

PROPOSALS = ROOT / "docs" / "governance" / "proposals" / "phase8_5_full_multilingual_architecture"


async def main() -> None:
    operator = FullMultilingualV2IndexBuildOperator(
        workspace_root=ROOT,
        proposal_root=PROPOSALS,
    )
    result = await operator.execute()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
