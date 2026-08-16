"""Knowledge graph response schemas for mnemo-server."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GraphNodeResponse(BaseModel):
    """An entity node in the knowledge graph."""

    model_config = ConfigDict(frozen=True)

    entity_id: UUID
    canonical_name: str
    type: str
    confidence: float
    document_id: UUID
    aliases: list[str] = Field(default_factory=list)


class GraphEdgeResponse(BaseModel):
    """A directed edge in the knowledge graph."""

    model_config = ConfigDict(frozen=True)

    source_id: UUID
    target_id: UUID
    relation: str
    weight: float


class EntityGraphResponse(BaseModel):
    """Response model for GET /v1/notebooks/{notebook_id}/graph."""

    model_config = ConfigDict(frozen=True)

    notebook_id: UUID
    nodes: list[GraphNodeResponse] = Field(default_factory=list)
    edges: list[GraphEdgeResponse] = Field(default_factory=list)
    status: Literal["active", "disabled", "empty"]
