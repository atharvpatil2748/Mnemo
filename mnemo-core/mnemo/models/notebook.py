"""Immutable notebook, conversation, citation, note, and insight models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from ._shared import (
    FrozenMetadata,
    identity_equal,
    require_enum,
    require_non_empty,
    require_non_negative,
    require_optional_non_empty,
    require_positive,
    require_sha256,
    require_tuple,
    require_unit_interval,
    require_utc,
    require_uuid,
)


class TurnRole(StrEnum):
    """Producer of a persisted conversational turn."""

    USER = "user"
    ASSISTANT = "assistant"


class NoteOrigin(StrEnum):
    """Origin of first-class notebook note content."""

    USER = "user"
    GENERATED = "generated"


class InsightType(StrEnum):
    """Supported categories of extracted source insight."""

    KEY_FACT = "key_fact"
    CLAIM = "claim"
    ENTITY = "entity"
    SUMMARY = "summary"


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class Turn:
    """One persisted user or assistant message in a session."""

    turn_id: UUID
    session_id: UUID
    sequence: int
    role: TurnRole
    content: str
    created_at: datetime
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        """Validate the turn snapshot."""
        require_uuid(self.turn_id, "turn_id")
        require_uuid(self.session_id, "session_id")
        require_non_negative(self.sequence, "sequence")
        require_enum(self.role, TurnRole, "role")
        require_non_empty(self.content, "content")
        require_utc(self.created_at, "created_at")
        if not isinstance(self.metadata, FrozenMetadata):
            raise TypeError("metadata must be FrozenMetadata")

    def __eq__(self, other: object) -> bool:
        """Compare turns by stable identity."""
        return identity_equal(self, other, Turn, self.turn_id, getattr(other, "turn_id", None))

    def __hash__(self) -> int:
        """Hash the stable turn identity."""
        return hash(self.turn_id)


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class Session:
    """A conversation thread attached to one notebook."""

    session_id: UUID
    notebook_id: UUID
    created_at: datetime
    updated_at: datetime
    title: str | None = None
    turns: tuple[Turn, ...] = ()
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        """Validate session identity, timestamps, and turn ordering."""
        require_uuid(self.session_id, "session_id")
        require_uuid(self.notebook_id, "notebook_id")
        require_optional_non_empty(self.title, "title")
        require_tuple(self.turns, "turns")
        if any(not isinstance(turn, Turn) for turn in self.turns):
            raise TypeError("turns must contain Turn instances")
        if any(turn.session_id != self.session_id for turn in self.turns):
            raise ValueError("all turns must belong to session_id")
        expected_sequences = tuple(range(len(self.turns)))
        if tuple(turn.sequence for turn in self.turns) != expected_sequences:
            raise ValueError("turn sequences must be contiguous and match order")
        if any(
            earlier.created_at > later.created_at
            for earlier, later in zip(self.turns, self.turns[1:], strict=False)
        ):
            raise ValueError("turn timestamps must be non-decreasing")
        require_utc(self.created_at, "created_at")
        require_utc(self.updated_at, "updated_at")
        if self.created_at > self.updated_at:
            raise ValueError("created_at cannot be later than updated_at")
        if not isinstance(self.metadata, FrozenMetadata):
            raise TypeError("metadata must be FrozenMetadata")

    def __eq__(self, other: object) -> bool:
        """Compare sessions by stable identity."""
        return identity_equal(
            self,
            other,
            Session,
            self.session_id,
            getattr(other, "session_id", None),
        )

    def __hash__(self) -> int:
        """Hash the stable session identity."""
        return hash(self.session_id)


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class Citation:
    """Versioned evidence resolved from one canonical source marker."""

    citation_id: UUID
    turn_id: UUID
    source_number: int
    chunk_id: str
    document_id: UUID
    version_id: UUID
    document_title: str
    verbatim_quote: str
    created_at: datetime
    page_number: int | None = None
    heading_path: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate the versioned citation snapshot."""
        require_uuid(self.citation_id, "citation_id")
        require_uuid(self.turn_id, "turn_id")
        require_positive(self.source_number, "source_number")
        require_sha256(self.chunk_id, "chunk_id")
        require_uuid(self.document_id, "document_id")
        require_uuid(self.version_id, "version_id")
        require_non_empty(self.document_title, "document_title")
        require_non_empty(self.verbatim_quote, "verbatim_quote")
        require_utc(self.created_at, "created_at")
        if self.page_number is not None:
            require_positive(self.page_number, "page_number")
        require_tuple(self.heading_path, "heading_path")
        for heading in self.heading_path:
            require_non_empty(heading, "heading_path entry")

    def __eq__(self, other: object) -> bool:
        """Compare citations by stable record identity."""
        return identity_equal(
            self,
            other,
            Citation,
            self.citation_id,
            getattr(other, "citation_id", None),
        )

    def __hash__(self) -> int:
        """Hash the stable citation identity."""
        return hash(self.citation_id)


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class Notebook:
    """A named organizational collection whose membership lives in Source."""

    notebook_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    description: str | None = None
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        """Validate notebook identity and descriptive fields."""
        require_uuid(self.notebook_id, "notebook_id")
        require_non_empty(self.title, "title")
        require_optional_non_empty(self.description, "description")
        _validate_time_range(self.created_at, self.updated_at)
        if not isinstance(self.metadata, FrozenMetadata):
            raise TypeError("metadata must be FrozenMetadata")

    def __eq__(self, other: object) -> bool:
        """Compare notebooks by stable identity."""
        return identity_equal(
            self,
            other,
            Notebook,
            self.notebook_id,
            getattr(other, "notebook_id", None),
        )

    def __hash__(self) -> int:
        """Hash the stable notebook identity."""
        return hash(self.notebook_id)


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class Source:
    """The sole association between one notebook and one logical document."""

    source_id: UUID
    notebook_id: UUID
    document_id: UUID
    created_at: datetime

    def __post_init__(self) -> None:
        """Validate source association identifiers and timestamp."""
        require_uuid(self.source_id, "source_id")
        require_uuid(self.notebook_id, "notebook_id")
        require_uuid(self.document_id, "document_id")
        require_utc(self.created_at, "created_at")

    def __eq__(self, other: object) -> bool:
        """Compare source associations by stable identity."""
        return identity_equal(
            self,
            other,
            Source,
            self.source_id,
            getattr(other, "source_id", None),
        )

    def __hash__(self) -> int:
        """Hash the stable source identity."""
        return hash(self.source_id)


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class Note:
    """First-class user-created or generated notebook content."""

    note_id: UUID
    notebook_id: UUID
    content: str
    origin: NoteOrigin
    created_at: datetime
    updated_at: datetime
    title: str | None = None
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        """Validate note identity, content, origin, and timestamps."""
        require_uuid(self.note_id, "note_id")
        require_uuid(self.notebook_id, "notebook_id")
        require_optional_non_empty(self.title, "title")
        require_non_empty(self.content, "content")
        require_enum(self.origin, NoteOrigin, "origin")
        _validate_time_range(self.created_at, self.updated_at)
        if not isinstance(self.metadata, FrozenMetadata):
            raise TypeError("metadata must be FrozenMetadata")

    def __eq__(self, other: object) -> bool:
        """Compare notes by stable identity."""
        return identity_equal(self, other, Note, self.note_id, getattr(other, "note_id", None))

    def __hash__(self) -> int:
        """Hash the stable note identity."""
        return hash(self.note_id)


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class Insight:
    """One extracted source insight within a notebook context."""

    insight_id: UUID
    notebook_id: UUID
    source_id: UUID
    type: InsightType
    content: str
    created_at: datetime
    confidence: float | None = None
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        """Validate insight identity, classification, and raw confidence."""
        require_uuid(self.insight_id, "insight_id")
        require_uuid(self.notebook_id, "notebook_id")
        require_uuid(self.source_id, "source_id")
        require_enum(self.type, InsightType, "type")
        require_non_empty(self.content, "content")
        if self.confidence is not None:
            require_unit_interval(self.confidence, "confidence")
        require_utc(self.created_at, "created_at")
        if not isinstance(self.metadata, FrozenMetadata):
            raise TypeError("metadata must be FrozenMetadata")

    def __eq__(self, other: object) -> bool:
        """Compare insights by stable identity."""
        return identity_equal(
            self,
            other,
            Insight,
            self.insight_id,
            getattr(other, "insight_id", None),
        )

    def __hash__(self) -> int:
        """Hash the stable insight identity."""
        return hash(self.insight_id)


def _validate_time_range(created_at: datetime, updated_at: datetime) -> None:
    require_utc(created_at, "created_at")
    require_utc(updated_at, "updated_at")
    if created_at > updated_at:
        raise ValueError("created_at cannot be later than updated_at")
