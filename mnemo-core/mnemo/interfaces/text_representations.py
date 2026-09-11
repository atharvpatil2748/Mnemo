"""Provider-neutral Full Multilingual V2 representation protocols."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from mnemo.models.multilingual import LanguageEvidenceReferenceV3
from mnemo.models.text_representations import (
    AuthorizationScopeV1,
    RepresentationObservationV1,
    RepresentationTransformationV1,
    TextRepresentationReferenceV1,
    TransformationProfileV1,
    TransformationRegistryEntryV1,
)


@runtime_checkable
class RepresentationDetectorV1(Protocol):  # pragma: no cover
    async def observe(
        self,
        *,
        actor_id: UUID,
        source: LanguageEvidenceReferenceV3,
        text: str,
        authorization_scope: AuthorizationScopeV1,
    ) -> RepresentationObservationV1: ...


@runtime_checkable
class RepresentationTransformerV1(Protocol):  # pragma: no cover
    async def initialize(self) -> None: ...

    async def close(self) -> None: ...

    async def ready(self) -> bool: ...

    async def transform(
        self,
        *,
        actor_id: UUID,
        source: TextRepresentationReferenceV1,
        source_text: str,
        observation: RepresentationObservationV1,
        profile: TransformationProfileV1,
        authorization_scope: AuthorizationScopeV1,
    ) -> str: ...


@runtime_checkable
class TransformationRegistryV1(Protocol):  # pragma: no cover
    def entries(self) -> tuple[TransformationRegistryEntryV1, ...]: ...

    def select(
        self,
        *,
        observation: RepresentationObservationV1,
        target_profile_id: str | None = None,
    ) -> TransformationRegistryEntryV1 | None: ...

    def resolve(self, entry: TransformationRegistryEntryV1) -> RepresentationTransformerV1: ...


@runtime_checkable
class TextRepresentationStoreV1(Protocol):  # pragma: no cover
    async def put_representation_observation(
        self, observation: RepresentationObservationV1
    ) -> bool: ...

    async def put_representation_transformation(
        self, transformation: RepresentationTransformationV1, *, output_text: str
    ) -> bool: ...
