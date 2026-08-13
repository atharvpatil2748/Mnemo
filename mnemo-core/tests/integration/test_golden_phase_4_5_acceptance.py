"""Opt-in live acceptance test for the real Phase 4 -> Phase 5 milestones."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
RUN_LIVE = os.environ.get("MNEMO_RUN_LIVE_MILESTONES") == "1"


@pytest.mark.skipif(
    not RUN_LIVE,
    reason="set MNEMO_RUN_LIVE_MILESTONES=1 with Ollama and Qdrant running",
)
def test_real_bhagavad_gita_to_ollama_and_qdrant() -> None:
    """Execute both milestones without mocks and require persisted read-back."""
    command = [sys.executable, "scripts/verify_phase_4_5_milestones.py", "all"]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr

    m4 = json.loads(
        (ROOT / "docs/milestone-evidence/m4-bhagavad-gita.json").read_text(encoding="utf-8")
    )
    m5 = json.loads(
        (ROOT / "docs/milestone-evidence/m5-ollama-qdrant.json").read_text(encoding="utf-8")
    )
    assert m4["verdict"] == "PASS"
    assert m4["dataset"] == "goldenDataset/Bhagavad-gita-As-It-Is.pdf"
    assert m4["dataset_sha256"] == (
        "ff112b0b056d303b792f6f2e68cbd73a89adf612fa9113f932446cdea7741583"
    )
    assert m4["physical_pages"] == 952
    assert m4["authored_chapter_count"] == 18
    assert m4["chapter_boundary_violations"] == 0
    assert m4["deterministic_repeat"] is True
    assert m5["verdict"] == "PASS"
    assert m5["input_chunks"] == 1000
    assert m5["qdrant_points_written"] == 1000
    assert m5["qdrant_points_read_back"] == 1000
    assert m5["repeat_cache_hits"] == 100
