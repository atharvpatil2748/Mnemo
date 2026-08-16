from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

import pytest
from mnemo.config import SurrealDBStorageConfig
from mnemo.models import Entity, GraphEdge
from mnemo.storage.surrealdb import SurrealDBStore
from pydantic import HttpUrl


class MockSurreal:
    last_url: str | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        type(self).last_url = str(args[0]) if args else None
        self.connected = False
        self.signed_in = False
        self.namespace = ""
        self.database = ""
        # store for mock data
        self.entities: dict[str, dict[str, Any]] = {}
        self.edges: dict[str, dict[str, Any]] = {}

    async def connect(self) -> None:
        self.connected = True

    async def signin(self, credentials: dict[str, Any]) -> None:
        self.signed_in = True

    async def use(self, namespace: str, database: str) -> None:
        self.namespace = namespace
        self.database = database

    async def close(self) -> None:
        self.connected = False

    async def query(
        self, statement: str, vars: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        if not self.connected:
            raise RuntimeError("Not connected")

        vars = vars or {}
        stmt = statement.strip()

        if stmt.startswith("RETURN true"):
            return [{"status": "OK", "time": "0ms", "result": True}]

        if stmt.startswith("UPSERT type::thing('entity'"):
            # UPSERT entity
            ent_id = vars.get("id")
            content = vars.get("content", {})
            record = {"id": f"entity:{ent_id}", **content}
            self.entities[str(ent_id)] = record
            return [{"status": "OK", "time": "0ms", "result": [record]}]

        if stmt.startswith("UPSERT type::thing('graph_edge'"):
            # UPSERT edge
            edge_id = vars.get("edge_id")
            source_id = vars.get("source_id")
            target_id = vars.get("target_id")
            relation = vars.get("relation")
            weight = vars.get("weight")
            record = {
                "id": f"graph_edge:{edge_id}",
                "in": f"entity:{source_id}",
                "out": f"entity:{target_id}",
                "relation": relation,
                "weight": weight,
            }
            self.edges[str(edge_id)] = record
            return [{"status": "OK", "time": "0ms", "result": [record]}]

        if stmt.startswith("SELECT * FROM type::thing('entity'"):
            # GET entity
            ent_id = vars.get("id")
            ent_record: dict[str, Any] | None = self.entities.get(str(ent_id))
            if ent_record:
                return [{"status": "OK", "time": "0ms", "result": [ent_record]}]
            return [{"status": "OK", "time": "0ms", "result": []}]

        if stmt.startswith("SELECT * FROM entity WHERE"):
            # FIND entities
            limit = vars.get("limit", 10)
            matches = []
            for e in self.entities.values():
                name_match = ("name" not in vars) or e.get("canonical_name") == vars["name"]
                type_match = ("type" not in vars) or e.get("type") == vars["type"]
                doc_match = ("docs" not in vars) or e.get("document_id") in vars["docs"]
                if name_match and type_match and doc_match:
                    matches.append(e)
            return [{"status": "OK", "time": "0ms", "result": matches[:limit]}]

        if stmt.startswith("SELECT VALUE"):
            # GET related
            # Simple mock for hops = 1 or 2
            source_id = vars.get("id")
            limit = vars.get("limit", 10)
            rels = vars.get("rels")

            # Find edges where in == source_id
            related_ids = set()
            for edge in self.edges.values():
                if edge["in"] == f"entity:{source_id}" and (not rels or edge["relation"] in rels):
                    target = edge["out"].split(":")[1]
                    related_ids.add(target)

            # This handles 1 hop. For 2 hops we'd repeat...
            # For simplicity of test, we just return the 1 hop ones
            res = []
            for tgt in list(related_ids)[:limit]:
                if tgt in self.entities:
                    res.append(self.entities[tgt])

            return [{"status": "OK", "time": "0ms", "result": res}]

        if stmt.startswith("DELETE entity WHERE"):
            # DELETE graph for doc
            doc_id = vars.get("doc_id")
            to_delete = []
            for k, v in self.entities.items():
                if v.get("document_id") == doc_id:
                    to_delete.append(k)
            for k in to_delete:
                del self.entities[k]
            return [{"status": "OK", "time": "0ms", "result": []}]

        return []


@pytest.fixture
def mock_surreal_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("mnemo.storage.surrealdb.Surreal", MockSurreal)


@pytest.fixture
def surreal_config() -> SurrealDBStorageConfig:
    return SurrealDBStorageConfig(
        enabled=True,
        url=HttpUrl("http://localhost:8000/rpc"),
        namespace="mnemo",
        database="knowledge",
        username="root",
        password="root",
    )


@pytest.fixture
async def surreal_store(
    surreal_config: SurrealDBStorageConfig, mock_surreal_client: None
) -> AsyncGenerator[SurrealDBStore, None]:
    store = SurrealDBStore(config=surreal_config)
    await store.open()
    yield store
    await store.close()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_surreal_lifecycle(
    surreal_config: SurrealDBStorageConfig, mock_surreal_client: None
) -> None:
    store = SurrealDBStore(config=surreal_config)

    # Should not be healthy before open
    health = await store.health_check()
    assert len(health) == 1
    assert not health[0].healthy

    await store.open()

    assert MockSurreal.last_url == "ws://localhost:8000"

    # Should be healthy after open
    health = await store.health_check()
    assert health[0].healthy

    await store.close()


@pytest.mark.anyio
async def test_surreal_upsert_and_get_entity(surreal_store: SurrealDBStore) -> None:
    doc_id = uuid4()
    ent_id = uuid4()

    entity = Entity(
        entity_id=ent_id,
        canonical_name="test_entity",
        type="PERSON",
        confidence=0.9,
        document_id=doc_id,
        aliases=("tester",),
    )

    await surreal_store.upsert_entity(entity)

    # Retrieve it
    retrieved = await surreal_store.get_entity(ent_id)
    assert retrieved is not None
    assert retrieved.entity_id == ent_id
    assert retrieved.canonical_name == "test_entity"
    assert retrieved.type == "PERSON"
    assert retrieved.confidence == 0.9
    assert retrieved.document_id == doc_id
    assert retrieved.aliases == ("tester",)

    # Missing entity
    assert await surreal_store.get_entity(uuid4()) is None


@pytest.mark.anyio
async def test_surreal_find_entities(surreal_store: SurrealDBStore) -> None:
    doc_id = uuid4()
    ent_id1 = uuid4()
    ent_id2 = uuid4()

    await surreal_store.upsert_entity(
        Entity(
            entity_id=ent_id1,
            canonical_name="John Doe",
            type="PERSON",
            confidence=0.9,
            document_id=doc_id,
            aliases=(),
        )
    )
    await surreal_store.upsert_entity(
        Entity(
            entity_id=ent_id2,
            canonical_name="Jane Doe",
            type="PERSON",
            confidence=0.9,
            document_id=doc_id,
            aliases=(),
        )
    )

    results = await surreal_store.find_entities("John Doe", "PERSON", (doc_id,), 10)
    assert len(results) == 1
    assert results[0].entity_id == ent_id1


@pytest.mark.anyio
async def test_surreal_graph_traversal(surreal_store: SurrealDBStore) -> None:
    doc_id = uuid4()
    ent_id1 = uuid4()
    ent_id2 = uuid4()

    await surreal_store.upsert_entity(
        Entity(
            entity_id=ent_id1,
            canonical_name="A",
            type="THING",
            confidence=1.0,
            document_id=doc_id,
        )
    )
    await surreal_store.upsert_entity(
        Entity(
            entity_id=ent_id2,
            canonical_name="B",
            type="THING",
            confidence=1.0,
            document_id=doc_id,
        )
    )

    edge = GraphEdge(
        source_id=ent_id1,
        target_id=ent_id2,
        relation="connects",
        weight=0.8,
    )
    await surreal_store.upsert_edge(edge)

    related = await surreal_store.get_related_entities(
        ent_id1, hops=1, relations=("connects",), limit=10
    )
    assert len(related) == 1
    assert related[0].entity_id == ent_id2


@pytest.mark.anyio
async def test_surreal_delete_graph(surreal_store: SurrealDBStore) -> None:
    doc_id = uuid4()
    ent_id = uuid4()

    await surreal_store.upsert_entity(
        Entity(
            entity_id=ent_id,
            canonical_name="A",
            type="THING",
            confidence=1.0,
            document_id=doc_id,
        )
    )

    assert await surreal_store.get_entity(ent_id) is not None

    await surreal_store.delete_graph_for_document(doc_id)

    assert await surreal_store.get_entity(ent_id) is None


@pytest.mark.anyio
async def test_surreal_unsupported_methods(surreal_store: SurrealDBStore) -> None:
    uid = uuid4()
    with pytest.raises(NotImplementedError):
        await surreal_store.put_asset(b"", "text/plain", None)  # type: ignore
    with pytest.raises(NotImplementedError):
        await surreal_store.get_asset(uid)
    with pytest.raises(NotImplementedError):
        await surreal_store.delete_asset(uid)
    with pytest.raises(NotImplementedError):
        await surreal_store.upsert_document(None)  # type: ignore
    with pytest.raises(NotImplementedError):
        await surreal_store.search_dense(None, None, 10)  # type: ignore


@pytest.mark.anyio
async def test_surreal_disabled_behavior() -> None:
    """Verify disabled SurrealDBStore operations are safe no-ops and return empty results."""
    disabled_config = SurrealDBStorageConfig(
        enabled=False,
        url=HttpUrl("http://localhost:8001"),
        username="root",
        password="root",
        namespace="test",
        database="test",
    )
    store = SurrealDBStore(config=disabled_config)

    # open() should perform no network I/O and remain unconnected
    await store.open()
    assert not store._connected

    # health_check() should return empty tuple for disabled component
    health = await store.health_check()
    assert health == ()

    # graph methods should return empty/none without error
    ent_id = uuid4()
    assert await store.get_entity(ent_id) is None
    assert await store.find_entities("name", None, (), 10) == ()
    assert await store.get_related_entities(ent_id, 1, (), 10) == ()

    # write methods should be safe no-ops
    entity = Entity(
        entity_id=ent_id,
        canonical_name="Test",
        type="TEST",
        confidence=1.0,
        document_id=uuid4(),
    )
    await store.upsert_entity(entity)
    await store.delete_graph_for_document(entity.document_id)
    await store.close()


@pytest.mark.anyio
async def test_surreal_enabled_unopened_raises() -> None:
    """Verify enabled but unopened SurrealDBStore raises RuntimeError."""
    enabled_config = SurrealDBStorageConfig(
        enabled=True,
        url=HttpUrl("http://localhost:8001"),
        username="root",
        password="root",
        namespace="test",
        database="test",
    )
    store = SurrealDBStore(config=enabled_config)

    ent_id = uuid4()
    with pytest.raises(RuntimeError, match="SurrealDBStore is not open"):
        await store.get_entity(ent_id)
