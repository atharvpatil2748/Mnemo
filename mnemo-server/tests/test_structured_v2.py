"""Focused WP-08 structured runtime, HTTP, MCP, cursor, and security tests."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from mnemo.engine import EngineState
from mnemo.interfaces import (
    ConflictError,
    ContractValidationError,
    IntegrityError,
    OperationTimeoutError,
)
from mnemo.models import (
    AdvancedRetrievalCandidate,
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    EvidenceRepresentation,
    ExtractedStructuredRecord,
    FrozenMetadata,
    RetrievalPathEvidenceV2,
    RetrievalScopeV2,
    StructuredDatasetCatalog,
    StructuredDatasetDescriptor,
    StructuredDatasetField,
    StructuredDatasetReadiness,
    StructuredField,
    StructuredFieldType,
    StructuredSchemaConfidence,
    advanced_candidate_id,
    structured_schema_generation,
)
from mnemo.retrieval import StructuredDatasetRuntimeService
from mnemo_server.app import create_app
from mnemo_server.config import ServerConfig
from mnemo_server.mcp.tools import execute_mcp_tool, get_mcp_tools, structured_content_for
from mnemo_server.schemas.structured_v2 import StructuredRetrievalRequest
from mnemo_server.services.structured_v2 import StructuredRetrievalApplicationService

NOTEBOOK = UUID(int=800)
VERSION = UUID(int=801)


class _Store:
    def __init__(self, catalog: StructuredDatasetCatalog, rows: dict[UUID, tuple[dict, ...]]):
        self.catalog = catalog
        self.rows = rows

    async def structured_projection_ready(self) -> bool:
        return True

    async def active_structured_generation_identity(self) -> str | None:
        return "1" * 64

    async def list_structured_datasets(self, *, scope, schema_scan_limit):  # type: ignore[no-untyped-def]
        del schema_scan_limit
        if scope != self.catalog.scope:
            return StructuredDatasetCatalog(
                scope=scope,
                snapshot_identity="f" * 64,
                datasets=(),
                requested_version_ids=scope.version_ids,
                ready_version_ids=(),
                unavailable_version_ids=scope.version_ids,
            )
        return self.catalog

    async def extract_structured_dataset_records(
        self, *, notebook_id, dataset_id, candidate_id, fields, limit
    ):  # type: ignore[no-untyped-def]
        if notebook_id != NOTEBOOK or dataset_id not in self.rows:
            return ()
        return tuple(
            ExtractedStructuredRecord(
                candidate_id=candidate_id,
                row_ordinal=index,
                values=FrozenMetadata(row),
                cell_locators=FrozenMetadata(
                    {
                        field.name: {
                            "dataset_id": str(dataset_id),
                            "row": index,
                            "column": field.name,
                        }
                        for field in fields
                    }
                ),
                extraction_method="wp08-test",
            )
            for index, row in enumerate(self.rows[dataset_id], 1)
        )[:limit]


def _dataset(index: int, *, version_id: UUID = VERSION) -> StructuredDatasetDescriptor:
    document_id, source_id, dataset_id, generation_id = (
        UUID(int=810 + index),
        UUID(int=820 + index),
        UUID(int=830 + index),
        UUID(int=840 + index),
    )
    fields = (
        StructuredField(name="Name", field_type=StructuredFieldType.STRING, source_name="Name"),
        StructuredField(name="CPI", field_type=StructuredFieldType.DECIMAL, source_name="CPI"),
        StructuredField(name="Branch", field_type=StructuredFieldType.STRING, source_name="Branch"),
    )
    chunk = Chunk(
        id=f"{index:064x}",
        document_id=document_id,
        version_id=version_id,
        text="Name\tCPI\tBranch",
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=index, page_number=1),
        source_span=BlockSpan(start_ordinal=index, end_ordinal=index),
        heading_path=("Students",),
        metadata=FrozenMetadata(),
    )
    candidate = AdvancedRetrievalCandidate(
        candidate_id=advanced_candidate_id(
            representation=EvidenceRepresentation.CANONICAL_TEXT,
            document_id=document_id,
            version_id=version_id,
            chunk_id=chunk.id,
            occurrence_id=None,
            derivation_id=None,
        ),
        notebook_id=NOTEBOOK,
        source_id=source_id,
        document_id=document_id,
        version_id=version_id,
        representation=EvidenceRepresentation.CANONICAL_TEXT,
        chunk=chunk,
        occurrence_id=None,
        derivation_id=None,
        locator=FrozenMetadata({"block_ordinal": index}),
        document_title=f"Students {index}",
        content=None,
        paths=(
            RetrievalPathEvidenceV2(
                path="structured-dataset-catalog", source_rank=index, source_score=None
            ),
        ),
    )
    return StructuredDatasetDescriptor(
        dataset_id=dataset_id,
        generation_id=generation_id,
        schema_identity=structured_schema_generation(fields),
        checksum=f"{index + 10:064x}",
        notebook_id=NOTEBOOK,
        source_id=source_id,
        document_id=document_id,
        version_id=version_id,
        block_ordinal=index,
        page_number=1,
        row_count=4,
        fields=tuple(
            StructuredDatasetField(
                field=field,
                confidence=StructuredSchemaConfidence.EXACT,
                non_missing_count=4,
            )
            for field in fields
        ),
        readiness=StructuredDatasetReadiness.READY,
        candidate=candidate,
    )


def _engine():  # type: ignore[no-untyped-def]
    first, second = _dataset(1), _dataset(2)
    scope = RetrievalScopeV2(
        notebook_id=NOTEBOOK,
        document_ids=(first.document_id, second.document_id),
        version_ids=(VERSION,),
    )
    catalog = StructuredDatasetCatalog(
        scope=scope,
        snapshot_identity="a" * 64,
        datasets=(first, second),
        requested_version_ids=(VERSION,),
        ready_version_ids=(VERSION,),
        unavailable_version_ids=(),
    )
    rows = {
        first.dataset_id: (
            {"Name": "Atharv", "CPI": "9.20", "Branch": "CSE"},
            {"Name": "Asha", "CPI": "8.95", "Branch": "CSE"},
            {"Name": "Bela", "CPI": "8.50", "Branch": "ME"},
            {"Name": "Cara", "CPI": "7.90", "Branch": "EE"},
        ),
        second.dataset_id: (
            {"Name": "Atharv", "CPI": "9.20", "Branch": "CSE"},
            {"Name": "Dev", "CPI": "8.75", "Branch": "ME"},
            {"Name": "Esha", "CPI": "9.10", "Branch": "EE"},
            {"Name": "Null", "CPI": "", "Branch": "CSE"},
        ),
    }
    return (
        SimpleNamespace(
            state=EngineState.READY,
            structured_retrieval=StructuredDatasetRuntimeService(_Store(catalog, rows)),
        ),
        catalog,
    )


def _request(catalog: StructuredDatasetCatalog, **changes: object) -> StructuredRetrievalRequest:
    first = catalog.datasets[0]
    value: dict[str, object] = {
        "operation": "query",
        "scope": catalog.scope.model_dump(mode="json"),
        "dataset_ids": [str(first.dataset_id)],
        "page_size": 100,
    }
    value.update(changes)
    return StructuredRetrievalRequest.model_validate(value)


def test_http_and_mcp_contracts_are_strict_and_discoverable() -> None:
    app = create_app(server_config=ServerConfig(), provision_tokenizer_on_startup=False)
    assert "/v2/retrieval/structured" in app.openapi()["paths"]
    tools = {item.name: item for item in get_mcp_tools()}
    assert len(tools) == 14 and "query_structured" in tools
    description = (tools["query_structured"].description or "").lower()
    assert "cpi > 8.9" in description and "arbitrary sql" in description
    assert "next_cursor" in description and tools["query_structured"].outputSchema is not None


@pytest.mark.anyio
async def test_http_route_invokes_the_shared_structured_service() -> None:
    engine, catalog = _engine()
    app = create_app(server_config=ServerConfig(), provision_tokenizer_on_startup=False)
    app.state.engine = engine
    app.state.server_config = ServerConfig()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v2/retrieval/structured",
            json=_request(
                catalog,
                filters=[{"field": "CPI", "operator": "gt", "value": 8.9}],
            ).model_dump(mode="json", exclude_none=True),
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["completeness"] == "complete"
    assert payload["structured"]["matched_count"] == 2


@pytest.mark.anyio
async def test_describe_is_authorized_exact_version_schema_discovery() -> None:
    engine, catalog = _engine()
    service = StructuredRetrievalApplicationService(engine, ServerConfig())  # type: ignore[arg-type]
    result = await service.execute(_request(catalog, operation="describe", dataset_ids=[]))
    assert result.completeness == "complete"
    assert result.items[0]["fields"][1]["field_type"] == "decimal"
    assert "table_id" not in json.dumps(result.model_dump(mode="json"))


@pytest.mark.anyio
async def test_behavior_7_gt_is_numeric_complete_and_provenanced() -> None:
    engine, catalog = _engine()
    result = await StructuredRetrievalApplicationService(  # type: ignore[arg-type]
        engine, ServerConfig()
    ).execute(
        _request(
            catalog,
            filters=[{"field": "CPI", "operator": "gt", "value": "8.9"}],
        )
    )
    assert result.completeness == "complete"
    assert [item["values"]["Name"]["value"] for item in result.items] == ["Atharv", "Asha"]
    assert result.items[0]["values"]["CPI"]["provenance"][0]["version_id"] == str(VERSION)


@pytest.mark.anyio
async def test_behavior_8_paginates_every_match_with_bound_cursor() -> None:
    engine, catalog = _engine()
    service = StructuredRetrievalApplicationService(engine, ServerConfig())  # type: ignore[arg-type]
    request = _request(
        catalog,
        filters=[{"field": "CPI", "operator": "gt", "value": "8"}],
        page_size=1,
    )
    first = await service.execute(request)
    assert first.completeness == "truncated" and first.next_cursor
    second = await service.execute(request.model_copy(update={"cursor": first.next_cursor}))
    assert second.next_cursor is not None
    with pytest.raises(ConflictError):
        await service.execute(
            request.model_copy(update={"cursor": first.next_cursor, "page_size": 2})
        )


@pytest.mark.anyio
async def test_behaviors_9_13_count_and_average_use_complete_universe() -> None:
    engine, catalog = _engine()
    service = StructuredRetrievalApplicationService(engine, ServerConfig())  # type: ignore[arg-type]
    result = await service.execute(
        _request(
            catalog,
            filters=[{"field": "CPI", "operator": "gt", "value": "8"}],
            aggregations=[
                {"name": "count", "operation": "count"},
                {"name": "average", "operation": "avg", "field": "CPI"},
            ],
        )
    )
    assert result.completeness == "complete"
    aggregates = result.items[0]["aggregates"]
    assert aggregates["count"]["value"] == 3
    assert aggregates["average"]["value"] == "8.883333333333333333333333333"


@pytest.mark.anyio
async def test_behaviors_10_11_12_15_filter_range_sort_group() -> None:
    engine, catalog = _engine()
    service = StructuredRetrievalApplicationService(engine, ServerConfig())  # type: ignore[arg-type]
    ranged = await service.execute(
        _request(
            catalog,
            filters=[{"field": "CPI", "operator": "between", "value": [8, 9]}],
            order_by=[{"field": "CPI", "direction": "desc", "null_order": "last"}],
        )
    )
    assert [item["values"]["Name"]["value"] for item in ranged.items] == ["Asha", "Bela"]
    grouped = await service.execute(
        _request(
            catalog,
            filters=[{"field": "Branch", "operator": "in", "value": ["CSE", "ME"]}],
            group_by=["Branch"],
            aggregations=[{"name": "count", "operation": "count"}],
        )
    )
    counts = {
        item["keys"]["Branch"]["value"]: item["aggregates"]["count"]["value"]
        for item in grouped.items
    }
    assert counts == {"CSE": 2, "ME": 1}


@pytest.mark.anyio
async def test_behavior_14_exact_named_rows_and_union() -> None:
    engine, catalog = _engine()
    service = StructuredRetrievalApplicationService(engine, ServerConfig())  # type: ignore[arg-type]
    exact = await service.execute(
        _request(
            catalog,
            filters=[{"field": "Name", "operator": "in", "value": ["Atharv", "Asha"]}],
        )
    )
    assert {item["values"]["Name"]["value"] for item in exact.items} == {"Atharv", "Asha"}
    union = await service.execute(
        _request(
            catalog,
            operation="union",
            dataset_ids=[str(item.dataset_id) for item in catalog.datasets],
            filters=[{"field": "CPI", "operator": "gte", "value": 9}],
        )
    )
    assert union.structured["matched_count"] == 3


@pytest.mark.anyio
async def test_equality_join_duplicate_and_null_keys_are_deterministic() -> None:
    engine, catalog = _engine()
    left, right = catalog.datasets
    result = await StructuredRetrievalApplicationService(  # type: ignore[arg-type]
        engine, ServerConfig()
    ).execute(
        _request(
            catalog,
            operation="join",
            dataset_ids=[],
            join={
                "left_dataset_id": str(left.dataset_id),
                "right_dataset_id": str(right.dataset_id),
                "left_field": "Name",
                "right_field": "Name",
            },
        )
    )
    assert result.completeness == "complete"
    assert [item["join_key"] for item in result.items] == ["Atharv"]


@pytest.mark.anyio
async def test_sql_injection_unknown_fields_and_cursor_tampering_fail_closed() -> None:
    engine, catalog = _engine()
    service = StructuredRetrievalApplicationService(engine, ServerConfig())  # type: ignore[arg-type]
    with pytest.raises(ContractValidationError, match="unknown field"):
        await service.execute(
            _request(
                catalog,
                filters=[{"field": "CPI); DROP TABLE chunks;--", "operator": "gt", "value": 8}],
            )
        )
    with pytest.raises(ValueError):
        StructuredRetrievalRequest.model_validate(
            {**_request(catalog).model_dump(mode="json"), "sql": "SELECT * FROM secrets"}
        )
    first = await service.execute(_request(catalog, page_size=1))
    assert first.next_cursor
    with pytest.raises(IntegrityError):
        await service.execute(_request(catalog, page_size=1, cursor=first.next_cursor[:-1] + "x"))

    filtered = _request(
        catalog,
        filters=[{"field": "CPI", "operator": "gt", "value": 8}],
        page_size=1,
    )
    filtered_page = await service.execute(filtered)
    assert filtered_page.next_cursor
    with pytest.raises(ConflictError):
        await service.execute(
            _request(
                catalog,
                filters=[{"field": "CPI", "operator": "gte", "value": 8}],
                page_size=1,
                cursor=filtered_page.next_cursor,
            )
        )


@pytest.mark.anyio
async def test_malicious_transport_shapes_scope_and_timeout_fail_closed() -> None:
    engine, catalog = _engine()
    with pytest.raises(ValueError):
        StructuredRetrievalRequest.model_validate(
            {
                **_request(catalog).model_dump(mode="json"),
                "filters": [{"field": "CPI", "operator": "gt; DROP", "value": 8}],
            }
        )
    with pytest.raises(ValueError):
        StructuredRetrievalRequest.model_validate(
            {**_request(catalog).model_dump(mode="json"), "page_size": 1001}
        )
    with pytest.raises(ContractValidationError, match="authorized scope"):
        await StructuredRetrievalApplicationService(  # type: ignore[arg-type]
            engine, ServerConfig()
        ).execute(
            _request(
                catalog,
                scope={
                    **catalog.scope.model_dump(mode="json"),
                    "notebook_id": str(UUID(int=999)),
                },
            )
        )

    class _SlowRuntime:
        async def discover(self, *, scope, schema_scan_limit):  # type: ignore[no-untyped-def]
            del scope, schema_scan_limit
            await asyncio.sleep(0.1)

    slow_engine = SimpleNamespace(
        state=EngineState.READY,
        structured_retrieval=_SlowRuntime(),
    )
    with pytest.raises(OperationTimeoutError):
        await StructuredRetrievalApplicationService(  # type: ignore[arg-type]
            slow_engine,
            ServerConfig(max_structured_elapsed_milliseconds=1),
        ).execute(_request(catalog, operation="describe", dataset_ids=[]))


@pytest.mark.anyio
async def test_mcp_uses_same_application_contract_and_structured_fallback() -> None:
    engine, catalog = _engine()
    content = await execute_mcp_tool(  # type: ignore[arg-type]
        engine,
        "query_structured",
        _request(
            catalog,
            filters=[{"field": "CPI", "operator": "gte", "value": 9}],
        ).model_dump(mode="json", exclude_none=True),
        ServerConfig(),
    )
    payload = json.loads(content[0].text)  # type: ignore[union-attr]
    assert payload["operation"] == "query" and payload["completeness"] == "complete"
    assert payload["schema_version"] == payload["contract_version"]
    assert structured_content_for("query_structured", {}, content) == payload
