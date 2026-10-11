"""Static safety policy for governed database usage in tests."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_ROOTS = (ROOT / "tests", ROOT / "mnemo-core/tests", ROOT / "mnemo-server/tests")
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
        "tests must use read-only readers or tmp_path copies for governed databases: "
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


def test_governed_reset_inspection_is_wal_aware_not_immutable() -> None:
    """Immutable reads can silently omit uncheckpointed WAL transactions."""
    executor = (ROOT / "mnemo-server/mnemo_server/tools/legacy_decommission.py").read_text(
        encoding="utf-8"
    )
    assert "mode=ro" in executor
    assert "immutable=1" not in executor
    assert "expected_wal_sha256" in executor
    assert "processes_using_files" in executor
