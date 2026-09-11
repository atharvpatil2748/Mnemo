"""Behavioral branch coverage for the immutable V2 runtime validation boundary."""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from uuid import uuid4

import pytest
from mnemo.interfaces.errors import StorageError
from mnemo.models.advanced_retrieval import PositionalScopeV2, RetrievalScopeV2
from mnemo.retrieval.final_qa_snapshot import _encode
from mnemo.storage.v2_runtime import (
    SQLiteV2ReadOnlyRuntimeStore,
    _checked_payload,
    _permitted_or_single,
    _position_clauses,
    _scope_clauses,
    _validate_decision_generation,
    _validate_source_scope,
)


def test_scope_and_position_clauses_bind_every_authorized_dimension() -> None:
    notebook, source, document, version = (uuid4() for _ in range(4))
    scope = RetrievalScopeV2(
        notebook_id=notebook,
        source_ids=(source,),
        document_ids=(document,),
        version_ids=(version,),
    )
    clauses, params = _scope_clauses(scope)
    assert clauses == [
        "notebook_id=?",
        "source_id IN (?)",
        "document_id IN (?)",
        "version_id IN (?)",
    ]
    assert params == [str(notebook), str(source), str(document), str(version)]

    decision = SimpleNamespace(
        positional_scope=PositionalScopeV2(
            page_start=2,
            page_end=8,
            section_indexes=(0, 3),
            heading_prefix=("Rate%", "A_B"),
        )
    )
    positional_params: list[object] = []
    positional = _position_clauses(decision, positional_params)  # type: ignore[arg-type]
    assert len(positional) == 4
    assert positional_params == [2, 8, 0, 3, "Rate%\x1fA_B", "Rate\\%\x1fA\\_B\x1f%"]

    empty = SimpleNamespace(positional_scope=PositionalScopeV2())
    empty_params: list[object] = []
    assert _position_clauses(empty, empty_params) == []  # type: ignore[arg-type]
    assert empty_params == []


def test_decision_generation_and_source_scope_fail_closed() -> None:
    generation = uuid4()
    decision = SimpleNamespace(
        operation="retrieve",
        runtime_binding=SimpleNamespace(generation_ids=(generation,)),
    )
    _validate_decision_generation(decision, generation)  # type: ignore[arg-type]
    with pytest.raises(PermissionError, match="AUTHORIZATION_DENIED"):
        _validate_decision_generation(
            SimpleNamespace(
                operation="mutate",
                runtime_binding=SimpleNamespace(generation_ids=(generation,)),
            ),
            generation,
        )  # type: ignore[arg-type]
    with pytest.raises(PermissionError, match="GENERATION_MISMATCH"):
        _validate_decision_generation(decision, uuid4())  # type: ignore[arg-type]

    notebook, source_id, document, version = (uuid4() for _ in range(4))
    source = SimpleNamespace(
        notebook_id=notebook,
        source_id=source_id,
        document_id=document,
        version_id=version,
    )
    scope = RetrievalScopeV2(
        notebook_id=notebook,
        source_ids=(source_id,),
        document_ids=(document,),
        version_ids=(version,),
    )
    _validate_source_scope(source, scope)
    for field in ("notebook_id", "source_id", "document_id", "version_id"):
        wrong = SimpleNamespace(**vars(source))
        setattr(wrong, field, uuid4())
        with pytest.raises(PermissionError, match="EVIDENCE_SCOPE_MISMATCH"):
            _validate_source_scope(wrong, scope)
    unrestricted = RetrievalScopeV2(notebook_id=notebook)
    _validate_source_scope(source, unrestricted)
    assert _permitted_or_single((), document) == (document,)
    assert _permitted_or_single((version,), document) == (version,)


def test_checked_payload_rejects_shape_hash_and_type_mismatch() -> None:
    scope = RetrievalScopeV2(notebook_id=uuid4())
    payload = _encode(scope)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    assert _checked_payload((payload, digest), RetrievalScopeV2, "scope") == scope
    for malformed in (None, (payload,), (payload, digest, "extra")):
        with pytest.raises(StorageError, match="invalid persisted scope"):
            _checked_payload(malformed, RetrievalScopeV2, "scope")
    with pytest.raises(StorageError, match="integrity mismatch"):
        _checked_payload((payload, "0" * 64), RetrievalScopeV2, "scope")
    with pytest.raises(StorageError, match="invalid persisted scope"):
        wrong_payload = _encode(("wrong",))
        _checked_payload(
            (wrong_payload, hashlib.sha256(wrong_payload.encode()).hexdigest()),
            RetrievalScopeV2,
            "scope",
        )


@pytest.mark.anyio
async def test_read_only_runtime_open_is_absent_safe_and_idempotent(tmp_path) -> None:  # type: ignore[no-untyped-def]
    missing = SQLiteV2ReadOnlyRuntimeStore(tmp_path / "missing.db")
    with pytest.raises(FileNotFoundError, match="approved V2 runtime database"):
        await missing.open()

    database = tmp_path / "runtime.db"
    import sqlite3

    sqlite3.connect(database).close()
    store = SQLiteV2ReadOnlyRuntimeStore(database)
    await store.open()
    connection = store._db
    await store.open()
    assert store._db is connection
    with pytest.raises(Exception, match=r"readonly|read-only"):
        await store._db.execute("CREATE TABLE forbidden(value TEXT)")  # type: ignore[union-attr]
    await store.close()
