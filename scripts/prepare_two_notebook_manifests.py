"""Record the two immutable source corpora for a future isolated rebuild."""

from __future__ import annotations

import json
from pathlib import Path

from mnemo_server.tools.source_manifest import build_source_manifest


def main() -> None:
    workspace = Path(__file__).resolve().parent.parent
    target = workspace / "config" / "rebuild"
    target.mkdir(parents=True, exist_ok=True)
    corpora = (
        ("personal_44", workspace / "goldenDataset" / "Phase 8.5 Evaluation Corpus", 44),
        (
            "codex_downloaded_24",
            workspace
            / "evaluationDataset"
            / "Phase 8.6 Format-Diverse Multilingual Evaluation Corpus",
            24,
        ),
    )
    for label, root, count in corpora:
        manifest = build_source_manifest(corpus=root, label=label, expected_count=count)
        output = target / f"{label}.sources.json"
        output.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"{label}: {count} sources, input {manifest['notebook_input_identity']}")


if __name__ == "__main__":
    main()
