"""Losslessly adapt frozen MVEA language identities to the Phase 8.6 evaluator schema."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPT_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_ROOT))

from scripts.bind_module_894_mvea_language import OUTPUT, ROOT  # noqa: E402

EXPECTED_INPUT = "9498ec0f4f873f92aa99ebed3ac3afa78854e3ce3966f82071b7db6bec5185c0"
ADAPTER = ROOT / "evaluation/module_894_mvea/language-phase86-adapter.v1.json"


def adapt() -> dict[str, Any]:
    raw = OUTPUT.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED_INPUT:
        raise ValueError("frozen language QREL changed")
    manifest: dict[str, Any] = json.loads(raw)
    if len(manifest["cases"]) != 90 or manifest["human_relevance_reviewed"] is not False:
        raise ValueError("frozen language QREL incomplete")
    return {
        **manifest,
        "schema": "mnemo.phase86-four-notebook-dere/1",
        "human_adjudication_claimed": False,
        "source_qrel_sha256": EXPECTED_INPUT,
    }


def main() -> int:
    payload = (json.dumps(adapt(), ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    digest = hashlib.sha256(payload).hexdigest()
    if not ADAPTER.is_file():
        with ADAPTER.open("xb") as stream:
            stream.write(payload)
    if ADAPTER.read_bytes() != payload:
        raise ValueError("existing evaluator adapter differs from frozen QREL")
    print(json.dumps({"cases": 90, "digest": digest, "path": str(ADAPTER)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
