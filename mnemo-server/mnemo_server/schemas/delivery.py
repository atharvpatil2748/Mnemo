"""Pydantic transport DTOs for bounded Phase 8.5 delivery."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from mnemo.models import (
    AdjacentAnchorKind,
    AdjacentSelector,
    BlockRangeSelector,
    ChunkRangeSelector,
    DocumentExpansionRequestV2,
    DocumentSelectorV2,
    FromEndSelector,
    FromEndUnit,
    FullDocumentSelector,
    PageRangeSelector,
    SectionSelector,
    SheetRangeSelector,
    SlideRangeSelector,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator


class FullSelectorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["full"]


class _RangeSelectorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    start: int
    end: int

    @model_validator(mode="after")
    def validate_order(self) -> _RangeSelectorRequest:
        if self.start > self.end:
            raise ValueError("selector start must not exceed end")
        return self


class PageRangeSelectorRequest(_RangeSelectorRequest):
    kind: Literal["page_range"]
    start: int = Field(ge=1)
    end: int = Field(ge=1)


class SlideRangeSelectorRequest(_RangeSelectorRequest):
    kind: Literal["slide_range"]
    start: int = Field(ge=1)
    end: int = Field(ge=1)


class SheetRangeSelectorRequest(_RangeSelectorRequest):
    kind: Literal["sheet_range"]
    start: int = Field(ge=1)
    end: int = Field(ge=1)


class BlockRangeSelectorRequest(_RangeSelectorRequest):
    kind: Literal["block_range"]
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class ChunkRangeSelectorRequest(_RangeSelectorRequest):
    kind: Literal["chunk_range"]
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class SectionSelectorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["section"]
    heading_path: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_headings(self) -> SectionSelectorRequest:
        if any(not heading.strip() for heading in self.heading_path):
            raise ValueError("heading_path entries must not be blank")
        return self


class FromEndSelectorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["from_end"]
    unit: FromEndUnit
    count: int = Field(default=1, ge=1)


class AdjacentSelectorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["adjacent"]
    anchor_kind: AdjacentAnchorKind
    block_ordinal: int | None = Field(default=None, ge=0)
    chunk_id: str | None = Field(default=None, min_length=64, max_length=64)
    before: int = Field(default=0, ge=0)
    after: int = Field(default=0, ge=0)
    include_anchor: bool = True

    @model_validator(mode="after")
    def validate_anchor(self) -> AdjacentSelectorRequest:
        if self.anchor_kind is AdjacentAnchorKind.BLOCK:
            if self.block_ordinal is None or self.chunk_id is not None:
                raise ValueError("block adjacency requires only block_ordinal")
        elif self.chunk_id is None or self.block_ordinal is not None:
            raise ValueError("chunk adjacency requires only chunk_id")
        if self.before == 0 and self.after == 0 and not self.include_anchor:
            raise ValueError("adjacent selector must request at least one item")
        return self


DocumentSelectorRequest = Annotated[
    FullSelectorRequest
    | PageRangeSelectorRequest
    | SlideRangeSelectorRequest
    | SheetRangeSelectorRequest
    | BlockRangeSelectorRequest
    | ChunkRangeSelectorRequest
    | SectionSelectorRequest
    | FromEndSelectorRequest
    | AdjacentSelectorRequest,
    Field(discriminator="kind"),
]


class DocumentExpansionRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    selector: DocumentSelectorRequest
    cursor: str | None = None
    max_bytes: int | None = Field(default=None, ge=1)
    max_items: int | None = Field(default=None, ge=1)

    def to_core(
        self, *, notebook_id: UUID, document_id: UUID, version_id: UUID
    ) -> DocumentExpansionRequestV2:
        selector = self.selector
        core: DocumentSelectorV2
        if isinstance(selector, FullSelectorRequest):
            core = FullDocumentSelector()
        elif isinstance(selector, PageRangeSelectorRequest):
            core = PageRangeSelector(start=selector.start, end=selector.end)
        elif isinstance(selector, SlideRangeSelectorRequest):
            core = SlideRangeSelector(start=selector.start, end=selector.end)
        elif isinstance(selector, SheetRangeSelectorRequest):
            core = SheetRangeSelector(start=selector.start, end=selector.end)
        elif isinstance(selector, BlockRangeSelectorRequest):
            core = BlockRangeSelector(start=selector.start, end=selector.end)
        elif isinstance(selector, ChunkRangeSelectorRequest):
            core = ChunkRangeSelector(start=selector.start, end=selector.end)
        elif isinstance(selector, SectionSelectorRequest):
            core = SectionSelector(heading_path=selector.heading_path)
        elif isinstance(selector, FromEndSelectorRequest):
            core = FromEndSelector(unit=selector.unit, count=selector.count)
        else:
            core = AdjacentSelector(
                anchor_kind=selector.anchor_kind,
                block_ordinal=selector.block_ordinal,
                chunk_id=selector.chunk_id,
                before=selector.before,
                after=selector.after,
                include_anchor=selector.include_anchor,
            )
        return DocumentExpansionRequestV2(
            notebook_id=notebook_id,
            document_id=document_id,
            version_id=version_id,
            selector=core,
            cursor=self.cursor,
            max_bytes=self.max_bytes,
            max_items=self.max_items,
        )


class DeliveryAttributionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    notebook_id: UUID
    source_id: UUID
    document_id: UUID
    version_id: UUID
    asset_id: UUID | None = None
    occurrence_id: UUID | None = None
    derivation_id: UUID | None = None
    modality: str
    language: str | None = None
    script: str | None = None
    generation_id: UUID | None = None
    authority: str


class DeliveryItemResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    index: int = Field(ge=0)
    kind: str
    attribution: DeliveryAttributionResponse
    payload: dict[str, Any]
    byte_size: int = Field(ge=0)


class DeliveryUsageResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: int = Field(ge=0)
    bytes: int = Field(ge=0)
    assets: int = Field(ge=0)


class DeliveryResponseBody(BaseModel):
    model_config = ConfigDict(frozen=True)
    resource_kind: str
    snapshot_identity: str
    completeness: str
    items: list[DeliveryItemResponse]
    usage: DeliveryUsageResponse
    omissions: list[str]
    next_cursor: str | None = None


class DeliveryCapabilityResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    state: str
    reason: str | None = None


class DeliveryCapabilitiesResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    capabilities: list[DeliveryCapabilityResponse]
