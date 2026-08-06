"""Immutable knowledge-graph domain models."""

from dataclasses import dataclass
from uuid import UUID

from ._shared import (
    require_non_empty,
    require_tuple,
    require_unique,
    require_unit_interval,
    require_uuid,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class Entity:
    """A normalized entity occurrence derived from one document."""

    name: str
    type: str
    confidence: float
    document_id: UUID
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate entity fields and deterministic aliases."""
        require_non_empty(self.name, "name")
        require_non_empty(self.type, "type")
        require_unit_interval(self.confidence, "confidence")
        require_uuid(self.document_id, "document_id")
        require_tuple(self.aliases, "aliases")
        for alias in self.aliases:
            require_non_empty(alias, "alias")
            if alias == self.name:
                raise ValueError("aliases cannot contain the canonical name")
        require_unique(self.aliases, "aliases")


@dataclass(frozen=True, slots=True, kw_only=True)
class GraphEdge:
    """A weighted directed relationship between normalized entity names."""

    source: str
    target: str
    relation: str
    weight: float

    def __post_init__(self) -> None:
        """Validate graph-edge fields."""
        require_non_empty(self.source, "source")
        require_non_empty(self.target, "target")
        require_non_empty(self.relation, "relation")
        require_unit_interval(self.weight, "weight")
