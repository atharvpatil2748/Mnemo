"""Frozen negative controls bind authorization and absence without semantic labels."""

from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path

import pytest

from scripts import bind_module_894_mvea_security as binder
from scripts.evaluate_module_894_mvea_security import append_progress, backup_acl, digest


def test_security_controls_are_distinct_and_not_human_judged() -> None:
    manifest = binder.bind()
    cases = manifest["cases"]
    assert len(cases) == 20
    assert manifest["semantic_relevance_adjudicated"] is False
    assert len({case["case_id"] for case in cases}) == 20
    assert Counter(case["control"] for case in cases) == {
        "exact_identifier_absence": 5,
        "wrong_notebook": 5,
        "ungranted_principal": 5,
        "revoked_membership": 5,
    }
    assert all(case["human_relevance_reviewed"] is False for case in cases)
    assert all(
        case["semantic_no_answer_adjudicated"] is False
        for case in cases
        if case["control"] == "exact_identifier_absence"
    )


def test_security_binding_rejects_changed_language_qrel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(binder, "EXPECTED_LANGUAGE", "0" * 64)
    with pytest.raises(ValueError, match="frozen language QREL differs"):
        binder.bind()


def test_security_acl_backup_is_isolated_and_nonoverwriting(tmp_path: Path) -> None:
    original = tmp_path / "acl.db"
    copy = tmp_path / "negative-control-acl.db"
    with sqlite3.connect(original) as db:
        db.execute("CREATE TABLE grants(actor TEXT PRIMARY KEY)")
        db.execute("INSERT INTO grants VALUES('owner')")
    before = digest(original)
    backup_acl(original, copy)
    with sqlite3.connect(copy) as db:
        db.execute("DELETE FROM grants")
    assert digest(original) == before
    with sqlite3.connect(original) as db:
        assert db.execute("SELECT count(*) FROM grants").fetchone() == (1,)
    with pytest.raises(FileExistsError):
        backup_acl(original, copy)


def test_security_progress_is_append_only_and_text_free(tmp_path: Path) -> None:
    path = tmp_path / "progress.jsonl"
    append_progress(path, "Q01", "started")
    append_progress(path, "Q01", "completed")
    assert path.read_text(encoding="utf-8").splitlines() == [
        '{"case_id": "Q01", "event": "started"}',
        '{"case_id": "Q01", "event": "completed"}',
    ]
