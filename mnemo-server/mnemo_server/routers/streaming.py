"""FastAPI WebSocket and SSE streaming routers for query processing."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import StreamingResponse
from mnemo.engine import EngineState
from mnemo.interfaces import (
    ContractValidationError,
    NotFoundError,
    TokenCounterInterfaceV1,
)
from pydantic import ValidationError

from mnemo_server.dependencies import get_streaming_query_service, get_token_counter
from mnemo_server.schemas.query import QueryRequest
from mnemo_server.schemas.streaming import (
    StreamErrorData,
    StreamEvent,
    StreamEventType,
)
from mnemo_server.services.streaming import StreamingQueryService

_LOGGER = logging.getLogger(__name__)

router = APIRouter(tags=["streaming"])


async def _handle_websocket_connection(websocket: WebSocket) -> None:
    """Process incoming queries and heartbeat messages on an active WebSocket connection."""
    await websocket.accept()

    # Validate KnowledgeEngine readiness
    engine = getattr(websocket.app.state, "engine", None)
    if engine is None or engine.state is not EngineState.READY:
        await websocket.send_text(
            StreamEvent(
                event=StreamEventType.ERROR,
                data=StreamErrorData(
                    code="dependency_unavailable",
                    message="KnowledgeEngine is not ready",
                ),
            ).model_dump_json()
        )
        await websocket.close(code=1011)
        return

    # Obtain or provision token counter
    token_counter: TokenCounterInterfaceV1 | None = getattr(
        websocket.app.state, "token_counter", None
    )
    if token_counter is None:
        token_counter = get_token_counter(Request(scope=websocket.scope))

    service = StreamingQueryService(engine=engine, token_counter=token_counter)

    while True:
        try:
            raw_text = await websocket.receive_text()
        except WebSocketDisconnect:
            _LOGGER.debug("WebSocket client disconnected")
            break

        stripped = raw_text.strip()
        if stripped in ('"ping"', '{"type": "ping"}', '{"event": "ping"}', "ping"):
            await websocket.send_text(StreamEvent(event=StreamEventType.PONG).model_dump_json())
            continue

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as err:
            await websocket.send_text(
                StreamEvent(
                    event=StreamEventType.ERROR,
                    data=StreamErrorData(code="bad_request", message=f"Invalid JSON: {err}"),
                ).model_dump_json()
            )
            continue

        if isinstance(payload, dict) and (
            payload.get("type") == "ping" or payload.get("event") == "ping"
        ):
            await websocket.send_text(StreamEvent(event=StreamEventType.PONG).model_dump_json())
            continue

        try:
            query_request = QueryRequest.model_validate(payload)
        except ValidationError as err:
            await websocket.send_text(
                StreamEvent(
                    event=StreamEventType.ERROR,
                    data=StreamErrorData(code="validation_error", message=str(err)),
                ).model_dump_json()
            )
            continue

        try:
            async for event in service.stream_query(query_request):
                await websocket.send_text(event.model_dump_json())
        except NotFoundError as err:
            await websocket.send_text(
                StreamEvent(
                    event=StreamEventType.ERROR,
                    data=StreamErrorData(code="not_found", message=str(err)),
                ).model_dump_json()
            )
        except ContractValidationError as err:
            await websocket.send_text(
                StreamEvent(
                    event=StreamEventType.ERROR,
                    data=StreamErrorData(code="contract_validation_error", message=str(err)),
                ).model_dump_json()
            )
        except Exception as err:
            _LOGGER.exception("Streaming query execution failed: %s", err)
            await websocket.send_text(
                StreamEvent(
                    event=StreamEventType.ERROR,
                    data=StreamErrorData(code="internal_error", message=str(err)),
                ).model_dump_json()
            )


@router.websocket("/ws/query")
async def websocket_query_root(websocket: WebSocket) -> None:
    """WebSocket streaming query endpoint conforming to Architecture §5.3."""
    await _handle_websocket_connection(websocket)


@router.websocket("/v1/ws/query")
async def websocket_query_v1(websocket: WebSocket) -> None:
    """WebSocket streaming query endpoint mounted at /v1/ws/query."""
    await _handle_websocket_connection(websocket)


@router.post(
    "/v1/query/stream",
    summary="Server-Sent Events (SSE) streaming query endpoint",
)
async def query_stream_sse(
    request: QueryRequest,
    service: Annotated[StreamingQueryService, Depends(get_streaming_query_service)],
) -> StreamingResponse:
    """Stream query results using Server-Sent Events (text/event-stream)."""

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for event in service.stream_query(request):
                yield f"event: {event.event.value}\ndata: {event.model_dump_json()}\n\n"
        except NotFoundError as err:
            err_event = StreamEvent(
                event=StreamEventType.ERROR,
                data=StreamErrorData(code="not_found", message=str(err)),
            )
            yield f"event: {StreamEventType.ERROR.value}\ndata: {err_event.model_dump_json()}\n\n"
        except Exception as err:
            err_event = StreamEvent(
                event=StreamEventType.ERROR,
                data=StreamErrorData(code="internal_error", message=str(err)),
            )
            yield f"event: {StreamEventType.ERROR.value}\ndata: {err_event.model_dump_json()}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
