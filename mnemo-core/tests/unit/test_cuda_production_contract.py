"""CI-safe guard for the Windows production CUDA dependency selection."""

from __future__ import annotations

import tomllib
from pathlib import Path

from mnemo.retrieval.multilingual_providers import BGE_RERANKER_PRODUCTION_EXECUTION_V1

ROOT = Path(__file__).resolve().parents[3]


def test_windows_cuda_wheel_is_locked_without_changing_linux_ci() -> None:
    workspace = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    server = tomllib.loads((ROOT / "mnemo-server/pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))

    assert workspace["tool"]["uv"]["sources"]["torch"] == [
        {"index": "pytorch-cu130", "marker": "sys_platform == 'win32'"}
    ]
    assert any(
        index["name"] == "pytorch-cu130"
        and index["url"] == "https://download.pytorch.org/whl/cu130"
        and index["explicit"] is True
        for index in workspace["tool"]["uv"]["index"]
    )
    evaluation = server["project"]["optional-dependencies"]["evaluation"]
    assert "torch==2.13.0+cu130; sys_platform == 'win32'" in evaluation
    assert "torch>=2.2,<3; sys_platform != 'win32'" in evaluation
    packages = lock["package"]
    assert any(
        package["name"] == "torch"
        and package["version"] == "2.13.0+cu130"
        and any("cp312-cp312-win_amd64" in wheel["url"] for wheel in package["wheels"])
        for package in packages
    )
    assert any(
        package["name"] == "torch"
        and package["version"] == "2.13.0"
        and any("linux" in wheel["url"] for wheel in package["wheels"])
        for package in packages
    )
    assert BGE_RERANKER_PRODUCTION_EXECUTION_V1.device == "cuda"
    assert BGE_RERANKER_PRODUCTION_EXECUTION_V1.allow_device_fallback is False
