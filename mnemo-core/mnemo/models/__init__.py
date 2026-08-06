"""Public Module 1.1 domain model exports."""

from ._shared import BoundingBox, FrozenMetadata, JSONPrimitive, JSONValue
from .assets import Asset
from .blocks import (
    Block,
    CaptionBlock,
    CodeBlock,
    EquationBlock,
    HeadingBlock,
    ImageBlock,
    TableBlock,
    TextBlock,
)
from .chunks import Chunk, ChunkPosition, ChunkType
from .documents import (
    DocType,
    Document,
    DocumentMetadata,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    ParsedDocument,
)
from .graph import Entity, GraphEdge
from .notebook import (
    Citation,
    Insight,
    InsightType,
    Note,
    Notebook,
    NoteOrigin,
    Session,
    Source,
    Turn,
    TurnRole,
)
from .retrieval import MetadataFilter, ScoredChunk

__all__ = [
    "Asset",
    "Block",
    "BoundingBox",
    "CaptionBlock",
    "Chunk",
    "ChunkPosition",
    "ChunkType",
    "Citation",
    "CodeBlock",
    "DocType",
    "Document",
    "DocumentMetadata",
    "DocumentStatus",
    "DocumentVersion",
    "DocumentVersionStatus",
    "Entity",
    "EquationBlock",
    "FrozenMetadata",
    "GraphEdge",
    "HeadingBlock",
    "ImageBlock",
    "Insight",
    "InsightType",
    "JSONPrimitive",
    "JSONValue",
    "MetadataFilter",
    "Note",
    "NoteOrigin",
    "Notebook",
    "ParsedDocument",
    "ScoredChunk",
    "Session",
    "Source",
    "TableBlock",
    "TextBlock",
    "Turn",
    "TurnRole",
]
