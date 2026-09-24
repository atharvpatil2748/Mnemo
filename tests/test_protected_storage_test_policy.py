"""Static safety policy for governed database usage in tests."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_ROOTS = (ROOT / "tests", ROOT / "mnemo-core/tests", ROOT / "mnemo-server/tests")
PYTHON_ROOTS = (
    *TEST_ROOTS,
    ROOT / "mnemo-core/mnemo",
    ROOT / "mnemo-server/mnemo_server",
    ROOT / "scripts",
)
GOVERNED_DATABASE_TOKENS = (
    "scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db",
    "scratch/phase8_5_wp16/eval-20260828-01/mnemo.db",
)


def test_no_test_opens_a_governed_database_through_writable_sqlite_store() -> None:
    violations: list[str] = []
    for test_root in TEST_ROOTS:
        for path in test_root.rglob("*.py"):
            if path == Path(__file__):
                continue
            text = path.read_text(encoding="utf-8")
            if "SQLiteStore(" not in text:
                continue
            normalized = text.replace("\\", "/")
            if any(token in normalized for token in GOVERNED_DATABASE_TOKENS):
                violations.append(str(path.relative_to(ROOT)))

    assert violations == [], (
        "tests must use immutable readers or tmp_path copies for governed databases: "
        + ", ".join(sorted(violations))
    )


def test_deprecated_manual_gita_fixture_has_no_active_test_reference() -> None:
    references = [
        str(path.relative_to(ROOT))
        for test_root in TEST_ROOTS
        for path in test_root.rglob("*.py")
        if path != Path(__file__)
        if "manual-" + "gita-qa" in path.read_text(encoding="utf-8")
    ]

    assert references == []


def test_read_only_sqlite_uris_are_immutable_safe() -> None:
    unsafe: list[str] = []
    pattern = re.compile(r"mode=ro(?!&immutable=1)")
    for source_root in PYTHON_ROOTS:
        for path in source_root.rglob("*.py"):
            if path == Path(__file__):
                continue
            if pattern.search(path.read_text(encoding="utf-8")):
                unsafe.append(str(path.relative_to(ROOT)))

    assert unsafe == [], "bare mode=ro may create governed WAL/SHM sidecars: " + ", ".join(
        sorted(unsafe)
    )
