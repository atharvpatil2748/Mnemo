"""Owner-authorized temporary, read-only certification endpoint; NOT production.

Persists explicit supported IR through the existing SQLite/filesystem APIs.
Serves only three canonical MCP tools, with the existing owner authentication.
No model, production activation, registry federation or mutation route exists.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import jsonschema
import mcp.types as types
import uvicorn
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.server.stdio import stdio_server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mnemo.interfaces import ContractValidationError, NotFoundError
from mnemo.models import (
    CodeBlock,
    DeliveryRequest,
    DeliveryView,
    DocType,
    Document,
    DocumentMetadata,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    EquationBlock,
    HeadingBlock,
    ImageBlock,
    Notebook,
    ParsedDocument,
    Source,
    TableBlock,
    TextBlock,
)
from mnemo.storage.filesystem import FilesystemBlobStore
from mnemo.storage.sqlite import SQLiteStore
from mnemo.storage.v2_runtime import SQLiteV2ReadOnlyRuntimeStore
from mnemo_server.auth import AuthMiddleware
from mnemo_server.config import ServerConfig
from mnemo_server.mcp.principal import (
    bind_session_principal,
    session_principal,
    sse_principal_from_scope,
    stdio_principal,
)
from mnemo_server.mcp.tools import get_mcp_tools
from mnemo_server.schemas.delivery import DeliveryResponseBody, DocumentExpansionRequestBody
from mnemo_server.services.authorization import principal_from_claims
from mnemo_server.services.delivery import build_delivery_service_for_storage
from mnemo_server.typed_errors import classify_public_error
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route

REPO = Path(__file__).resolve().parents[1]
BASE = REPO / "scratch" / "ordered_text_external"
SPEC = REPO / "docs/reports/operations/mnemo-ordered-text-fixture-manifest.json"


def approved_root(root: Path) -> Path:
    candidate = root.resolve()
    base = BASE.resolve()
    if candidate == base or not candidate.is_relative_to(base):
        raise ValueError("fixture must use a dedicated approved test directory")
    protected = (
        REPO / "scratch/phase8_5_full_multilingual_v2",
        REPO / "scratch/phase8_5_wp16",
        REPO / "scratch/evaluation_notebooks",
        REPO / "config/production",
    )
    for path in protected:
        resolved = path.resolve()
        if candidate.is_relative_to(resolved) or resolved.is_relative_to(candidate):
            raise ValueError("fixture root overlaps protected state")
    return candidate


async def provision(root: Path) -> dict[str, Any]:
    root = approved_root(root)
    if root.exists():
        raise ValueError("refusing to overwrite an existing fixture")
    truth = json.loads(SPEC.read_text(encoding="utf-8"))
    if hashlib.sha256(truth["expected_text"].encode()).hexdigest() != truth["text_sha256_utf8"]:
        raise ValueError("independent text truth digest mismatch")
    records = truth["expected_blocks"]
    digest = hashlib.sha256(
        json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if digest != truth["block_fields_sha256"]:
        raise ValueError("independent block truth digest mismatch")
    ids = {key: uuid4() for key in ("notebook_id", "source_id", "document_id", "version_id")}
    classes = {
        c.__name__: c
        for c in (HeadingBlock, TextBlock, TableBlock, CodeBlock, EquationBlock, ImageBlock)
    }
    blocks = []
    for index, record in enumerate(records):
        fields = {k: v for k, v in record.items() if k != "kind"}
        if "rows" in fields:
            fields["rows"] = tuple(tuple(row) for row in fields["rows"])
        if "asset_id" in fields:
            fields["asset_id"] = UUID(fields["asset_id"])
        blocks.append(classes[record["kind"]](ordinal=index, page_number=index + 1, **fields))
    now = datetime.now(UTC)
    source_bytes = json.dumps(
        records, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    metadata = DocumentMetadata(
        content_hash=hashlib.sha256(source_bytes).hexdigest(),
        title="Ordered text external certification",
        page_count=12,
    )
    version = DocumentVersion(
        version_id=ids["version_id"],
        document_id=ids["document_id"],
        content_hash=metadata.content_hash,
        metadata=metadata,
        status=DocumentVersionStatus.CURRENT,
        created_at=now,
    )
    document = Document(
        document_id=ids["document_id"],
        versions=(version,),
        current_version_id=ids["version_id"],
        current_hash=metadata.content_hash,
        status=DocumentStatus.INDEXED,
        created_at=now,
        updated_at=now,
    )
    root.mkdir(parents=True)
    writer = SQLiteStore(root / "fixture.db")
    blobs = FilesystemBlobStore(root / "blobs")
    await writer.open()
    await blobs.open()
    try:
        await writer.upsert_notebook(
            Notebook(
                notebook_id=ids["notebook_id"],
                title=metadata.title,
                description="Disposable read-only ordered-text certification",
                created_at=now,
                updated_at=now,
            )
        )
        await writer.upsert_document(document)
        await writer.upsert_source(
            Source(
                source_id=ids["source_id"],
                notebook_id=ids["notebook_id"],
                document_id=ids["document_id"],
                created_at=now,
            )
        )
        await blobs.put_parsed_document(
            ids["version_id"],
            ParsedDocument(
                blocks=tuple(blocks), metadata=metadata, language="en", doc_type=DocType.GENERIC
            ),
        )
    finally:
        await blobs.close()
        await writer.close()
    manifest = {
        **truth,
        **{k: str(v) for k, v in ids.items()},
        "schema_version": "mnemo.isolated-text-fixture/1",
        "serving_role": "isolated_certification",
        "source_specification_sha256": metadata.content_hash,
        "created_utc": now.isoformat(),
        "expires_utc": (now + timedelta(days=2)).isoformat(),
        "retention": (
            "Serving automatically stops after 48 hours; owner removes test data within 7 days."
        ),
        "database_sha256": hashlib.sha256((root / "fixture.db").read_bytes()).hexdigest(),
        "representations": ["parsed_blocks/v1", "parsed_text/v1"],
        "exposure": "isolated endpoint; never federated into production",
    }
    (root / "fixture-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=True))
    return manifest


class FixtureReader(SQLiteV2ReadOnlyRuntimeStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root / "fixture.db")
        self.blobs = FilesystemBlobStore(root / "blobs")

    async def get_parsed_document(self, version_id: UUID) -> ParsedDocument | None:
        return await self.blobs.get_parsed_document(version_id)


def fixture_app(root: Path, config: ServerConfig) -> Starlette:
    root = approved_root(root)
    manifest = json.loads((root / "fixture-manifest.json").read_text(encoding="utf-8"))
    if config.auth_mode != "api-key" or not config.api_key:
        raise ValueError("fixture requires the existing owner API-key authentication")
    if (
        hashlib.sha256((root / "fixture.db").read_bytes()).hexdigest()
        != manifest["database_sha256"]
    ):
        raise ValueError("fixture database identity mismatch")
    reader = FixtureReader(root)
    service = build_delivery_service_for_storage(reader, reader, config)
    server = Server("mnemo-isolated-ordered-text-certification", version="1.0.0")
    declarations = {
        t.name: t
        for t in get_mcp_tools()
        if t.name in {"get_capabilities", "list_notebooks", "get_document"}
    }
    # Reuse canonical argument schemas, but never impersonate the certified
    # production capability document on this model-free fixture endpoint.
    declarations["get_capabilities"] = declarations["get_capabilities"].model_copy(
        update={
            "description": "Read-only isolated fixture readiness; NOT production certification.",
            "outputSchema": {
                "type": "object",
                "required": ["schema_version", "runtime", "capabilities"],
                "properties": {
                    "schema_version": {"const": "mnemo.isolated-text-capabilities/1"},
                    "runtime": {"type": "object"},
                    "capabilities": {"type": "array"},
                },
            },
        }
    )
    expiry = datetime.fromisoformat(manifest["expires_utc"])
    if datetime.now(UTC) >= expiry:
        raise ValueError("fixture lease expired")
    authorized_actors = {principal_from_claims({"sub": "api-key"}).actor_id}
    if config.mcp_stdio_principal_subject:
        authorized_actors.add(stdio_principal(config).actor_id)

    def authorize() -> Any:
        principal = session_principal()
        if principal.actor_id not in authorized_actors or datetime.now(UTC) >= expiry:
            raise PermissionError("fixture authorization or lease unavailable")
        return principal

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        authorize()
        return list(declarations.values())

    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> types.CallToolResult:
        request_id = uuid4()
        try:
            principal = authorize()
            args = arguments or {}
            if name not in declarations:
                raise ContractValidationError("operation is unavailable on this isolated endpoint")
            jsonschema.validate(args, declarations[name].inputSchema)
            allowed = {
                "get_capabilities": {"notebook_id", "capability_ids"},
                "list_notebooks": {"limit", "cursor"},
                "get_document": {
                    "notebook_id",
                    "document_id",
                    "version_id",
                    "mode",
                    "selector",
                    "cursor",
                    "max_items",
                    "max_bytes",
                },
            }[name]
            if set(args) - allowed:
                raise ContractValidationError("unsupported fixture arguments")
            if args.get("notebook_id", manifest["notebook_id"]) != manifest["notebook_id"]:
                raise NotFoundError("authorized resource was not found")
            if name == "get_document":
                if any(args.get(k) != manifest[k] for k in ("document_id", "version_id")):
                    raise NotFoundError("authorized resource was not found")
                request = DeliveryRequest(
                    notebook_id=UUID(manifest["notebook_id"]),
                    document_id=UUID(manifest["document_id"]),
                    version_id=UUID(manifest["version_id"]),
                    view=DeliveryView(args.get("mode", "blocks")),
                    cursor=args.get("cursor"),
                    max_items=args.get("max_items"),
                    max_bytes=args.get("max_bytes"),
                )
                scoped = service.for_actor(principal.actor_id)
                selector = args.get("selector")
                if request.view is DeliveryView.TEXT and selector not in (None, {"kind": "full"}):
                    raise ContractValidationError("text view supports only full traversal")
                if request.view is DeliveryView.ORIGINAL:
                    from mnemo.delivery import DeliveryRepresentationUnavailableError

                    raise DeliveryRepresentationUnavailableError(
                        "fixture original representation unavailable"
                    )
                if request.view is DeliveryView.BLOCKS and selector is not None:
                    body = DocumentExpansionRequestBody.model_validate(
                        {
                            "selector": selector,
                            "cursor": request.cursor,
                            "max_items": request.max_items,
                            "max_bytes": request.max_bytes,
                        }
                    )
                    result = await scoped.expand_document_v2(
                        body.to_core(
                            notebook_id=request.notebook_id,
                            document_id=request.document_id,
                            version_id=request.version_id,
                        )
                    )
                else:
                    result = await scoped.expand_document(request)
                data = DeliveryResponseBody.model_validate(asdict(result)).model_dump(mode="json")
                data.update(
                    schema_version="phase8.5-mcp-v1",
                    operation=name,
                    request_id=str(request_id),
                    coverage={"serving_role": "isolated_certification"},
                    limits={"max_items": request.max_items, "max_bytes": request.max_bytes},
                    recommended_next_actions=[],
                )
            elif name == "list_notebooks":
                if args.get("cursor"):
                    raise ContractValidationError("fixture inventory has no continuation")
                data = {
                    "schema_version": "phase8.5-mcp-v1",
                    "operation": name,
                    "request_id": str(request_id),
                    "completeness": "complete",
                    "next_cursor": None,
                    "total": 1,
                    "notebooks": [
                        {
                            "notebook_id": manifest["notebook_id"],
                            "name": "Ordered text external certification",
                            "source_count": 1,
                            "source_id": manifest["source_id"],
                            "document_id": manifest["document_id"],
                            "version_id": manifest["version_id"],
                        }
                    ],
                    "coverage": {},
                    "limits": {},
                    "recommended_next_actions": [],
                }
            else:
                data = {
                    "schema_version": "mnemo.isolated-text-capabilities/1",
                    "request_id": str(request_id),
                    "scope_notebook_id": args.get("notebook_id"),
                    "scope_qualified": "notebook_id" in args,
                    "runtime": {
                        "serving_role": "isolated_certification",
                        "mutation_enabled": False,
                        "database_sha256": manifest["database_sha256"],
                        "expires_utc": manifest["expires_utc"],
                    },
                    "capabilities": [
                        {
                            "id": "document_delivery",
                            "available": True,
                            "representations": manifest["representations"],
                            "certified": False,
                        }
                    ],
                    "limitations": ["Temporary fixture only; no production/model certification."],
                }
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=json.dumps(data))],
                structuredContent=data,
            )
        except Exception as error:
            if isinstance(error, (jsonschema.ValidationError, ValueError)):
                error = ContractValidationError("fixture request is invalid")
            data = {"error": classify_public_error(error, request_id).body()}
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=json.dumps(data))],
                structuredContent=data,
                isError=True,
            )

    transport = SseServerTransport("/messages")
    http_transport = StreamableHTTPSessionManager(server, json_response=True, stateless=True)

    async def sse(request: Request) -> Response:
        with bind_session_principal(sse_principal_from_scope(request.scope)):
            async with transport.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                await server.run(*streams, server.create_initialization_options())
        return Response()

    async def streamable(scope, receive, send):
        with bind_session_principal(sse_principal_from_scope(scope)):
            await http_transport.handle_request(scope, receive, send)

    @asynccontextmanager
    async def lifespan(app: Starlette):
        await reader.open()
        await reader.blobs.open()
        try:
            async with http_transport.run():
                yield
        finally:
            await reader.blobs.close()
            await reader.close()

    application = Starlette(
        routes=[
            Route("/sse", sse),
            Mount("/messages", app=transport.handle_post_message),
            Mount("/mcp", app=streamable),
        ],
        lifespan=lifespan,
        middleware=[Middleware(AuthMiddleware, config=config)],
    )
    application.state.fixture_mcp_server = server
    return application


async def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("command", choices=("provision", "serve", "stdio"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8057)
    args = parser.parse_args()
    if args.command == "provision":
        await provision(args.root)
        return
    config = ServerConfig.from_env(certified_production=True)
    app = fixture_app(args.root, config)
    manifest = json.loads((args.root / "fixture-manifest.json").read_text(encoding="utf-8"))
    ttl = (datetime.fromisoformat(manifest["expires_utc"]) - datetime.now(UTC)).total_seconds()
    if ttl <= 0:
        raise ValueError("fixture lease expired")
    if args.command == "stdio":
        with bind_session_principal(stdio_principal(config)):
            async with app.router.lifespan_context(app), stdio_server() as streams:
                server = app.state.fixture_mcp_server
                await asyncio.wait_for(
                    server.run(*streams, server.create_initialization_options()), timeout=ttl
                )
        return
    listener = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning")
    )

    async def expire() -> None:
        await asyncio.sleep(ttl)
        listener.should_exit = True

    expiry_task = asyncio.create_task(expire())
    try:
        await listener.serve()
    finally:
        expiry_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
