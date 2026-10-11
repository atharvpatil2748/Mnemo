"""Restart Manager observes a live disposable file handle without closing it."""

import os
from pathlib import Path

import pytest
from mnemo_server.tools.windows_open_handles import processes_using_files


@pytest.mark.skipif(os.name != "nt", reason="Windows Restart Manager only")
def test_live_file_user_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "fixture.db"
    path.write_bytes(b"fixture")
    with path.open("rb"):
        users = processes_using_files((path.resolve(),))
        assert os.getpid() in users


def test_empty_probe_is_rejected() -> None:
    with pytest.raises(ValueError):
        processes_using_files(())
