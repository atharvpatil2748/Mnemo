"""Freeze the independently bound MVEA cohorts without fabricating OCR targets."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPT_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_ROOT))

from scripts.bind_module_894_mvea_language import ROOT, sha256  # noqa: E402

DIR = ROOT / "evaluation/module_894_mvea"
OUTPUT = DIR / "cohort.v1.json"
INPUTS = {
    "language": ("language-identity.v1.json", 90),
    "visual": ("visual-identity.v1.json", 20),
    "security": ("security-controls.v1.json", 20),
}


def assemble() -> dict[str, Any]:
    if (
        json.loads((ROOT / "config/production/runtime-selection.json").read_text())["state"]
        != "UNINDEXED"
    ):
        raise ValueError("production selector changed")
    sections: dict[str, dict[str, object]] = {}
    case_ids: set[str] = set()
    for name, (filename, count) in INPUTS.items():
        path = DIR / filename
        value = json.loads(path.read_text(encoding="utf-8"))
        cases = value["cases"]
        if (
            len(cases) != count
            or value["judgment_method"] != "DETERMINISTIC_ENGINEERING"
            or value["semantic_relevance_adjudicated"] is not False
        ):
            raise ValueError(f"invalid {name} cohort")
        ids = {case["case_id"] for case in cases}
        if len(ids) != count or ids & case_ids:
            raise ValueError("cohort case identities overlap")
        case_ids.update(ids)
        sections[name] = {
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256(path),
            "count": count,
        }
    return {
        "schema": "mnemo.module-894-mvea-cohort/1",
        "judgment_method": "DETERMINISTIC_ENGINEERING",
        "semantic_relevance_adjudicated": False,
        "human_relevance_reviewed": False,
        "status": "PARTIAL_GROUNDED_COHORT",
        "grounded_case_count": len(case_ids),
        "planned_case_count": 140,
        "unfilled_slices": {
            "ocr_only": {
                "required": 10,
                "grounded": 0,
                "reason": (
                    "Retained OCR projection text is mainly duplicated UI chrome, isolated "
                    "glyphs, and corrupted extraction; no ten independently supportable "
                    "OCR-only target identities were established."
                ),
            }
        },
        "sections": sections,
    }


def main() -> int:
    payload = (json.dumps(assemble(), ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    digest = hashlib.sha256(payload).hexdigest()
    if not OUTPUT.exists():
        with OUTPUT.open("xb") as stream:
            stream.write(payload)
    if OUTPUT.read_bytes() != payload:
        raise ValueError("existing cohort manifest differs")
    print(json.dumps({"cases": 130, "digest": digest, "status": "PARTIAL_GROUNDED_COHORT"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
