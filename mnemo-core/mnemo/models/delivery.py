"""Bounded, provenance-preserving Phase 8.5 resource delivery models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from ._shared import require_non_empty, require_non_negative, require_positive, require_sha256


class DeliveryCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    BOUNDED = "bounded"
    TRUNCATED = "truncated"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    EMPTY = "empty"


class DeliveryResourceKind(StrEnum):
    DOCUMENT = "document"
    CHUNK = "chunk"
    ASSET_INVENTORY = "asset_inventory"
    ASSET = "asset"
    ANALYSIS = "analysis"
    MULTIMODAL_EVIDENCE = "multimodal_evidence"


class DeliveryView(StrEnum):
    BLOCKS = "blocks"
    ORIGINAL = "original"


class DocumentSelectorKind(StrEnum):
    FULL = "full"
    PAGE_RANGE = "page_range"
    SLIDE_RANGE = "slide_range"
    SHEET_RANGE = "sheet_range"
    BLOCK_RANGE = "block_range"
    CHUNK_RANGE = "chunk_range"
    SECTION = "section"
    FROM_END = "from_end"
    ADJACENT = "adjacent"


class FromEndUnit(StrEnum):
    PAGE = "page"
    SLIDE = "slide"
    SHEET = "sheet"
    BLOCK = "block"
    CHUNK = "chunk"
    SECTION = "section"
    PARAGRAPH = "paragraph"


class AdjacentAnchorKind(StrEnum):
    BLOCK = "block"
    CHUNK = "chunk"


class AssetAnalysisModality(StrEnum):
    OCR = "ocr"
    VISION = "vision"
    VISUAL_EMBEDDING = "visual_embedding"
    OTHER = "other"


class AssetAnalysisSelection(StrEnum):
    EXPLICIT = "explicit"
    LATEST_READY = "latest_ready"
    ALL = "all"


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetDerivationDescriptor:
    derivation_id: UUID
    occurrence_id: UUID
    modality: AssetAnalysisModality
    operation: str
    provider_identity: str
    model_identity: str
    configuration_digest: str
    status: str
    generation_id: UUID | None
    generation_profile: str | None
    generation_state: str | None
    result_available: bool
    confidence: float | None
    language: str | None
    created_at: datetime
    updated_at: datetime

    @property
    def ready(self) -> bool:
        return (
            self.status == "succeeded"
            and self.result_available
            and self.generation_state in {None, "ready"}
        )

    @property
    def availability(self) -> str:
        if self.ready:
            return "ready"
        if self.status == "failed" or self.generation_state == "failed":
            return "failed"
        if self.generation_state in {"superseded", "retired"}:
            return "stale"
        if self.status in {"pending", "running"} or self.generation_state == "building":
            return "pending"
        return "unavailable"


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetAnalysisSelector:
    selection: AssetAnalysisSelection
    modalities: tuple[AssetAnalysisModality, ...] = (
        AssetAnalysisModality.OCR,
        AssetAnalysisModality.VISION,
    )
    derivation_ids: tuple[UUID, ...] = ()
    profile: str | None = None

    def __post_init__(self) -> None:
        if not self.modalities or len(set(self.modalities)) != len(self.modalities):
            raise ValueError("modalities must be non-empty and unique")
        if any(
            item in {AssetAnalysisModality.VISUAL_EMBEDDING, AssetAnalysisModality.OTHER}
            for item in self.modalities
        ):
            raise ValueError("non-analysis derivations cannot be requested as analysis payloads")
        if self.selection is AssetAnalysisSelection.EXPLICIT and not self.derivation_ids:
            raise ValueError("explicit analysis selection requires derivation_ids")
        if self.selection is not AssetAnalysisSelection.EXPLICIT and self.derivation_ids:
            raise ValueError("derivation_ids are valid only for explicit selection")
        if self.profile is not None:
            require_non_empty(self.profile, "profile")


@dataclass(frozen=True, slots=True, kw_only=True)
class FullDocumentSelector:
    kind: DocumentSelectorKind = field(default=DocumentSelectorKind.FULL, init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class PageRangeSelector:
    start: int
    end: int
    kind: DocumentSelectorKind = field(default=DocumentSelectorKind.PAGE_RANGE, init=False)

    def __post_init__(self) -> None:
        _validate_one_based_range(self.start, self.end)


@dataclass(frozen=True, slots=True, kw_only=True)
class SlideRangeSelector:
    start: int
    end: int
    kind: DocumentSelectorKind = field(default=DocumentSelectorKind.SLIDE_RANGE, init=False)

    def __post_init__(self) -> None:
        _validate_one_based_range(self.start, self.end)


@dataclass(frozen=True, slots=True, kw_only=True)
class SheetRangeSelector:
    start: int
    end: int
    kind: DocumentSelectorKind = field(default=DocumentSelectorKind.SHEET_RANGE, init=False)

    def __post_init__(self) -> None:
        _validate_one_based_range(self.start, self.end)


@dataclass(frozen=True, slots=True, kw_only=True)
class BlockRangeSelector:
    start: int
    end: int
    kind: DocumentSelectorKind = field(default=DocumentSelectorKind.BLOCK_RANGE, init=False)

    def __post_init__(self) -> None:
        _validate_zero_based_range(self.start, self.end)


@dataclass(frozen=True, slots=True, kw_only=True)
class ChunkRangeSelector:
    start: int
    end: int
    kind: DocumentSelectorKind = field(default=DocumentSelectorKind.CHUNK_RANGE, init=False)

    def __post_init__(self) -> None:
        _validate_zero_based_range(self.start, self.end)


@dataclass(frozen=True, slots=True, kw_only=True)
class SectionSelector:
    heading_path: tuple[str, ...]
    kind: DocumentSelectorKind = field(default=DocumentSelectorKind.SECTION, init=False)

    def __post_init__(self) -> None:
        if not self.heading_path or any(not item.strip() for item in self.heading_path):
            raise ValueError("heading_path must contain non-empty exact headings")


@dataclass(frozen=True, slots=True, kw_only=True)
class FromEndSelector:
    unit: FromEndUnit
    count: int = 1
    kind: DocumentSelectorKind = field(default=DocumentSelectorKind.FROM_END, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.unit, FromEndUnit):
            raise TypeError("unit must be FromEndUnit")
        require_positive(self.count, "count")


@dataclass(frozen=True, slots=True, kw_only=True)
class AdjacentSelector:
    anchor_kind: AdjacentAnchorKind
    block_ordinal: int | None = None
    chunk_id: str | None = None
    before: int = 0
    after: int = 0
    include_anchor: bool = True
    kind: DocumentSelectorKind = field(default=DocumentSelectorKind.ADJACENT, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.anchor_kind, AdjacentAnchorKind):
            raise TypeError("anchor_kind must be AdjacentAnchorKind")
        require_non_negative(self.before, "before")
        require_non_negative(self.after, "after")
        if self.before == 0 and self.after == 0 and not self.include_anchor:
            raise ValueError("adjacent selector must request at least one item")
        if self.anchor_kind is AdjacentAnchorKind.BLOCK:
            if self.block_ordinal is None or self.chunk_id is not None:
                raise ValueError("block adjacency requires only block_ordinal")
            require_non_negative(self.block_ordinal, "block_ordinal")
        elif self.chunk_id is None or self.block_ordinal is not None:
            raise ValueError("chunk adjacency requires only chunk_id")
        else:
            require_sha256(self.chunk_id, "chunk_id")


DocumentSelectorV2 = (
    FullDocumentSelector
    | PageRangeSelector
    | SlideRangeSelector
    | SheetRangeSelector
    | BlockRangeSelector
    | ChunkRangeSelector
    | SectionSelector
    | FromEndSelector
    | AdjacentSelector
)


class DeliveryCapabilityState(StrEnum):
    SUPPORTED = "supported"
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"
    POLICY_DENIED = "policy_denied"
    BUDGET_DENIED = "budget_denied"
    UNVALIDATED = "unvalidated"


@dataclass(frozen=True, slots=True, kw_only=True)
class DeliveryLimits:
    """Deployment ceilings; request limits may only reduce these values."""

    max_document_bytes: int = 4 * 1024 * 1024
    max_asset_bytes: int = 8 * 1024 * 1024
    max_assets: int = 32
    max_aggregate_asset_bytes: int = 16 * 1024 * 1024
    max_items: int = 256
    max_ocr_regions: int = 256
    max_vision_observations: int = 256
    max_response_bytes: int = 8 * 1024 * 1024
    max_stream_seconds: int = 60

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            require_positive(getattr(self, name), name)


@dataclass(frozen=True, slots=True, kw_only=True)
class DeliveryRequest:
    notebook_id: UUID
    document_id: UUID
    version_id: UUID
    view: DeliveryView = DeliveryView.BLOCKS
    cursor: str | None = None
    max_bytes: int | None = None
    max_items: int | None = None

    def __post_init__(self) -> None:
        if self.max_bytes is not None:
            require_positive(self.max_bytes, "max_bytes")
        if self.max_items is not None:
            require_positive(self.max_items, "max_items")
        if self.cursor is not None:
            require_non_empty(self.cursor, "cursor")


@dataclass(frozen=True, slots=True, kw_only=True)
class DocumentExpansionRequestV2:
    notebook_id: UUID
    document_id: UUID
    version_id: UUID
    selector: DocumentSelectorV2
    cursor: str | None = None
    max_bytes: int | None = None
    max_items: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(
            self.selector,
            (
                FullDocumentSelector,
                PageRangeSelector,
                SlideRangeSelector,
                SheetRangeSelector,
                BlockRangeSelector,
                ChunkRangeSelector,
                SectionSelector,
                FromEndSelector,
                AdjacentSelector,
            ),
        ):
            raise TypeError("selector must be exactly one DocumentSelectorV2")
        if self.cursor is not None:
            require_non_empty(self.cursor, "cursor")
        if self.max_bytes is not None:
            require_positive(self.max_bytes, "max_bytes")
        if self.max_items is not None:
            require_positive(self.max_items, "max_items")


@dataclass(frozen=True, slots=True, kw_only=True)
class DeliveryAttribution:
    notebook_id: UUID
    source_id: UUID
    document_id: UUID
    version_id: UUID
    asset_id: UUID | None = None
    occurrence_id: UUID | None = None
    derivation_id: UUID | None = None
    modality: str = "document"
    language: str | None = None
    script: str | None = None
    generation_id: UUID | None = None
    authority: str = "original"

    def __post_init__(self) -> None:
        require_non_empty(self.modality, "modality")
        require_non_empty(self.authority, "authority")


@dataclass(frozen=True, slots=True, kw_only=True)
class DeliveryItem:
    index: int
    kind: str
    attribution: DeliveryAttribution
    payload: dict[str, object]
    byte_size: int

    def __post_init__(self) -> None:
        require_non_negative(self.index, "index")
        require_non_empty(self.kind, "kind")
        require_non_negative(self.byte_size, "byte_size")


@dataclass(frozen=True, slots=True, kw_only=True)
class DeliveryUsage:
    items: int
    bytes: int
    assets: int = 0

    def __post_init__(self) -> None:
        require_non_negative(self.items, "items")
        require_non_negative(self.bytes, "bytes")
        require_non_negative(self.assets, "assets")


@dataclass(frozen=True, slots=True, kw_only=True)
class DeliveryResponse:
    resource_kind: DeliveryResourceKind
    snapshot_identity: str
    completeness: DeliveryCompleteness
    items: tuple[DeliveryItem, ...]
    usage: DeliveryUsage
    omissions: tuple[str, ...] = ()
    next_cursor: str | None = None

    def __post_init__(self) -> None:
        require_sha256(self.snapshot_identity, "snapshot_identity")
        if self.completeness is DeliveryCompleteness.TRUNCATED and self.next_cursor is None:
            raise ValueError("truncated delivery requires a continuation cursor")
        if self.completeness is DeliveryCompleteness.COMPLETE and self.next_cursor is not None:
            raise ValueError("complete delivery cannot contain a continuation cursor")


@dataclass(frozen=True, slots=True, kw_only=True)
class BinaryDelivery:
    resource_kind: DeliveryResourceKind
    attribution: DeliveryAttribution
    snapshot_identity: str
    content: bytes
    media_type: str
    content_hash: str
    total_byte_size: int
    range_start: int
    completeness: DeliveryCompleteness
    next_cursor: str | None = None

    def __post_init__(self) -> None:
        require_sha256(self.snapshot_identity, "snapshot_identity")
        require_non_empty(self.media_type, "media_type")
        require_sha256(self.content_hash, "content_hash")
        require_positive(self.total_byte_size, "total_byte_size")
        require_non_negative(self.range_start, "range_start")
        if self.range_start + len(self.content) > self.total_byte_size:
            raise ValueError("binary range exceeds total byte size")
        if self.completeness is DeliveryCompleteness.TRUNCATED and self.next_cursor is None:
            raise ValueError("truncated binary delivery requires a continuation cursor")
        if self.completeness is DeliveryCompleteness.COMPLETE and self.next_cursor is not None:
            raise ValueError("complete binary delivery cannot contain a continuation cursor")


@dataclass(frozen=True, slots=True, kw_only=True)
class DeliveryCapability:
    name: str
    state: DeliveryCapabilityState
    reason: str | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.name, "name")


def _validate_one_based_range(start: int, end: int) -> None:
    require_positive(start, "start")
    require_positive(end, "end")
    if start > end:
        raise ValueError("start must not exceed end")


def _validate_zero_based_range(start: int, end: int) -> None:
    require_non_negative(start, "start")
    require_non_negative(end, "end")
    if start > end:
        raise ValueError("start must not exceed end")
