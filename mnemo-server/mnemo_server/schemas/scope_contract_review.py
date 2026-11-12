"""Accepted Module 8.9.1 design vocabulary, NOT a registered serving API.

These building blocks validate request/response shape and conservative
provenance equivalence only. They never authorize, resolve membership, choose
providers, verify a cursor, merge evidence, or execute retrieval. No adapter
imports this module. Shared-service DTO integration belongs to Module 8.9.3.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from mnemo.models import EvidenceRepresentation, RetrievalCompleteness
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from mnemo_server.schemas.automatic_query_v2 import AutomaticRepresentationStatus
from mnemo_server.typed_errors import ErrorCategory


class ReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DocumentSelection(ReviewModel):
    notebook_id: UUID
    document_id: UUID
    version_id: UUID


class SelectedNotebooks(ReviewModel):
    kind: Literal["selected"]
    notebook_ids: tuple[UUID, ...] = Field(
        min_length=1, max_length=200, json_schema_extra={"uniqueItems": True}
    )

    @field_validator("notebook_ids")
    @classmethod
    def unique(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(set(value)) != len(value):
            raise ValueError("notebook selections must be unique")
        return value


class AllAuthorizedNotebooks(ReviewModel):
    kind: Literal["all_authorized"]


class ScopeRequestReview(ReviewModel):
    contract_version: Literal["mnemo.scope-review/1"] = "mnemo.scope-review/1"
    query: str = Field(min_length=1, max_length=4096, pattern=r"\S")
    scope: Annotated[SelectedNotebooks | AllAuthorizedNotebooks, Field(discriminator="kind")]
    documents: tuple[DocumentSelection, ...] = Field(default=(), max_length=200)
    representations: tuple[EvidenceRepresentation, ...] | None = Field(
        default=None,
        min_length=1,
        max_length=len(EvidenceRepresentation),
        json_schema_extra={"uniqueItems": True},
    )
    mode: Literal["ranked", "traversal"] = "ranked"
    limit: StrictInt = Field(default=20, ge=1, le=200)
    cursor: str | None = Field(default=None, min_length=1, max_length=8192, pattern=r"\S")

    @field_validator("query")
    @classmethod
    def normalize(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("query must not be empty")
        return value

    @model_validator(mode="after")
    def consistent(self) -> ScopeRequestReview:
        if len(set(self.documents)) != len(self.documents):
            raise ValueError("document selections must be unique")
        if isinstance(self.scope, SelectedNotebooks) and any(
            document.notebook_id not in self.scope.notebook_ids for document in self.documents
        ):
            raise ValueError("document selections must belong to selected notebooks")
        if self.representations is not None and len(set(self.representations)) != len(
            self.representations
        ):
            raise ValueError("representations must be unique")
        if self.cursor is not None and (self.mode != "traversal" or not self.cursor.strip()):
            raise ValueError("continuation requires traversal and a nonblank opaque cursor")
        return self


class CanonicalIdentity(ReviewModel):
    kind: Literal["canonical"]
    chunk_id: str = Field(min_length=1)


class DerivedIdentity(ReviewModel):
    kind: Literal["derived"]
    occurrence_id: UUID
    asset_id: UUID
    derivation_id: UUID


class StructuredIdentity(ReviewModel):
    kind: Literal["structured"]
    dataset_id: UUID
    row_ids: tuple[str, ...] = Field(min_length=1)


class EvidenceAncestryReview(ReviewModel):
    """One notebook-qualified evidence membership, never a global bearer ID."""

    notebook_id: UUID
    source_id: UUID
    document_id: UUID
    version_id: UUID
    generation_id: UUID
    generation_alias: str = Field(min_length=1)
    identity: Annotated[
        CanonicalIdentity | DerivedIdentity | StructuredIdentity, Field(discriminator="kind")
    ]
    locator: str = Field(min_length=1)
    retrieval_path: tuple[str, ...] = Field(min_length=1)
    citation: str = Field(min_length=1)


def evidence_equivalence_key(evidence: EvidenceAncestryReview) -> tuple[object, ...]:
    """Conservative design key; equal keys still require payload-integrity checks.

    Distinct notebooks, source ancestry, versions, generations, locators and
    citations cannot collapse. Retrieval paths are deliberately excluded so
    identical authorized evidence may later preserve all paths in a group.
    This function does not authorize or perform a merge.
    """

    return (
        evidence.notebook_id,
        evidence.source_id,
        evidence.document_id,
        evidence.version_id,
        evidence.generation_id,
        evidence.generation_alias,
        evidence.identity,
        evidence.locator,
        evidence.citation,
    )


class SourceStatusReview(ReviewModel):
    notebook_id: UUID
    representation: EvidenceRepresentation
    status: AutomaticRepresentationStatus
    matched: StrictInt | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def searched_counts_only(self) -> SourceStatusReview:
        if (self.status is AutomaticRepresentationStatus.SEARCHED) != (self.matched is not None):
            raise ValueError("only searched sources report a match count, including zero")
        return self


class OmissionReview(ReviewModel):
    """Server-produced, bounded reason code for an applicable unsearched source."""

    notebook_id: UUID
    representation: EvidenceRepresentation
    status: Literal["unavailable", "incomplete", "failed", "omitted_by_budget"]
    reason_code: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")


class CoverageReview(ReviewModel):
    completeness: RetrievalCompleteness
    examined: StrictInt = Field(ge=0)
    returned: StrictInt = Field(ge=0)
    partial: bool
    next_cursor: str | None = Field(default=None, min_length=1)
    mode: Literal["ranked", "traversal"]

    @model_validator(mode="after")
    def no_false_completeness(self) -> CoverageReview:
        if self.returned > self.examined:
            raise ValueError("returned exceeds examined")
        if (self.completeness is RetrievalCompleteness.TRUNCATED) != (self.next_cursor is not None):
            raise ValueError("truncated completeness requires a continuation cursor and vice versa")
        if self.next_cursor is not None and self.mode != "traversal":
            raise ValueError("continuation requires traversal mode")
        if self.completeness is RetrievalCompleteness.EMPTY and self.returned:
            raise ValueError("empty completeness cannot report returned evidence")
        if self.completeness is RetrievalCompleteness.PARTIAL and not self.partial:
            raise ValueError("partial completeness must report partial coverage")
        if self.completeness is RetrievalCompleteness.COMPLETE and (
            self.mode == "ranked" or self.partial or self.next_cursor is not None
        ):
            raise ValueError("complete requires nonpartial terminal traversal")
        return self


class SafeErrorReview(ReviewModel):
    category: ErrorCategory
    correlation_id: UUID
    # No client-echoed messages, paths, actor IDs, or arbitrary details.


class ScopeResponseReview(ReviewModel):
    contract_version: Literal["mnemo.scope-review/1"] = "mnemo.scope-review/1"
    evidence: tuple[EvidenceAncestryReview, ...]
    sources: tuple[SourceStatusReview, ...]
    omissions: tuple[OmissionReview, ...] = ()
    coverage: CoverageReview
    errors: tuple[SafeErrorReview, ...] = ()

    @model_validator(mode="after")
    def no_false_source_coverage(self) -> ScopeResponseReview:
        if self.coverage.returned != len(self.evidence):
            raise ValueError("returned count must match evidence items")
        unavailable = {
            AutomaticRepresentationStatus.UNAVAILABLE,
            AutomaticRepresentationStatus.INCOMPLETE,
            AutomaticRepresentationStatus.FAILED,
            AutomaticRepresentationStatus.OMITTED_BY_BUDGET,
        }
        expected_omissions = [
            (source.notebook_id, source.representation, source.status.value)
            for source in self.sources
            if source.status in unavailable
        ]
        reported_omissions = [
            (item.notebook_id, item.representation, item.status) for item in self.omissions
        ]
        if len(set(expected_omissions)) != len(expected_omissions) or sorted(
            expected_omissions
        ) != sorted(reported_omissions):
            raise ValueError("omissions must correspond exactly to unavailable source statuses")
        if expected_omissions and (
            not self.coverage.partial
            or self.coverage.completeness
            in {RetrievalCompleteness.COMPLETE, RetrievalCompleteness.EMPTY}
        ):
            raise ValueError("unavailable or omitted sources require partial coverage")
        if self.coverage.completeness in {
            RetrievalCompleteness.COMPLETE,
            RetrievalCompleteness.EMPTY,
        } and not any(
            source.status is AutomaticRepresentationStatus.SEARCHED for source in self.sources
        ):
            raise ValueError("complete or empty outcomes require an actually searched source")
        return self
