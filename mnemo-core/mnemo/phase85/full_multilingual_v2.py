"""Buildable-only generation contracts for isolated Full Multilingual V2 indexing."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from mnemo.interfaces.multilingual import MultilingualEmbeddingProviderV3, MultilingualStoreV2
from mnemo.interfaces.text_representations import TextRepresentationStoreV1
from mnemo.models.multilingual import LanguageEvidenceReferenceV3
from mnemo.models.multilingual_embeddings import (
    MultilingualEmbeddingInputV3,
    MultilingualEmbeddingV3,
)
from mnemo.models.multilingual_generation import MultilingualCoverageManifestV2
from mnemo.models.multilingual_index import MultilingualTextProjectionRowV2
from mnemo.models.text_representations import TextRepresentationReferenceV1
from mnemo.phase85.projections import ProjectionBuildResult, ProjectionGenerationSpec
from mnemo.retrieval.text_representations import RepresentationPipelineV1


@dataclass(frozen=True, slots=True, kw_only=True)
class FullMultilingualV2GenerationPlan:
    representation_derivation: ProjectionGenerationSpec
    language_text: ProjectionGenerationSpec
    multilingual_embedding: ProjectionGenerationSpec
    multilingual_vector: ProjectionGenerationSpec


def full_multilingual_v2_generation_plan(
    *,
    profile_id: str,
    profile_fingerprint: str,
    source_version_ids: tuple[UUID, ...],
    representation_configuration_digest: str,
    detector_configuration_digest: str,
    authorization_policy_digest: str,
    embedding_provider_identity: str,
    embedding_model_identity: str,
    embedding_model_revision: str,
    embedding_preprocessing_digest: str,
    vector_space_identity: str,
    dimensions: int,
) -> FullMultilingualV2GenerationPlan:
    """Create four deterministic V2 specs without encoding a language allowlist."""
    shared = _digest(
        profile_fingerprint,
        representation_configuration_digest,
        detector_configuration_digest,
        authorization_policy_digest,
    )
    representation = ProjectionGenerationSpec(
        capability="representation_derivation_v2",
        profile_id=profile_id,
        schema_version=1,
        input_scope="authorized-evidence-representations-v3",
        provider_identity="configured-transformation-registry",
        model_identity=None,
        model_revision=None,
        configuration_fingerprint=shared,
        source_version_ids=source_version_ids,
    )
    language_text = ProjectionGenerationSpec(
        capability="language_text_v2",
        profile_id=profile_id,
        schema_version=1,
        input_scope="authorized-text-representations-v1",
        provider_identity="sqlite-fts5-unicode61",
        model_identity=None,
        model_revision=None,
        configuration_fingerprint=_digest(shared, "language-text-v2"),
        source_version_ids=source_version_ids,
        source_generation_ids=(representation.generation_id,),
    )
    embedding = ProjectionGenerationSpec(
        capability="multilingual_embedding_v2",
        profile_id=profile_id,
        schema_version=1,
        input_scope="authorized-text-representations-v1",
        provider_identity=embedding_provider_identity,
        model_identity=embedding_model_identity,
        model_revision=embedding_model_revision,
        configuration_fingerprint=_digest(
            shared, embedding_preprocessing_digest, vector_space_identity
        ),
        source_version_ids=source_version_ids,
        source_generation_ids=(representation.generation_id,),
        dimensions=dimensions,
    )
    vector = ProjectionGenerationSpec(
        capability="multilingual_vector_v2",
        profile_id=profile_id,
        schema_version=1,
        input_scope="multilingual-embeddings-v2-exact-cosine",
        provider_identity="sqlite-exact-cosine-v2",
        model_identity=embedding_model_identity,
        model_revision=embedding_model_revision,
        configuration_fingerprint=_digest(
            shared, embedding_preprocessing_digest, vector_space_identity, "exact-cosine-v2"
        ),
        source_version_ids=source_version_ids,
        source_generation_ids=(embedding.generation_id,),
        dimensions=dimensions,
    )
    return FullMultilingualV2GenerationPlan(
        representation_derivation=representation,
        language_text=language_text,
        multilingual_embedding=embedding,
        multilingual_vector=vector,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class RepresentationGenerationInputV2:
    actor_id: UUID
    source: LanguageEvidenceReferenceV3
    text: str
    source_representation: TextRepresentationReferenceV1
    target_profile_id: str | None = None

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("representation generation text must not be blank")
        if self.source_representation.evidence_reference != self.source:
            raise ValueError("representation generation source mismatch")
        if hashlib.sha256(self.text.encode("utf-8")).hexdigest() != (
            self.source.source_content_hash
        ):
            raise ValueError("representation generation source hash mismatch")


class RepresentationGenerationBuilderV2:
    def __init__(
        self,
        *,
        pipeline: RepresentationPipelineV1,
        store: TextRepresentationStoreV1,
        generation_id: UUID,
        inputs: tuple[RepresentationGenerationInputV2, ...],
    ) -> None:
        self._pipeline = pipeline
        self._store = store
        self._generation_id = generation_id
        self._inputs = inputs

    async def build(self, generation_id: UUID) -> ProjectionBuildResult:
        if generation_id != self._generation_id:
            raise ValueError("representation generation identity mismatch")
        identities: list[str] = []
        for item in self._inputs:
            _, observation = await self._pipeline.observe(
                actor_id=item.actor_id, source=item.source, text=item.text
            )
            await self._store.put_representation_observation(observation)
            identities.append(f"observation:{observation.observation_id}")
            if item.target_profile_id is not None:
                output_text, transformation = await self._pipeline.transform(
                    actor_id=item.actor_id,
                    source=item.source,
                    source_text=item.text,
                    source_representation=item.source_representation,
                    observation=observation,
                    generation_id=generation_id,
                    target_profile_id=item.target_profile_id,
                )
                await self._store.put_representation_transformation(
                    transformation, output_text=output_text
                )
                identities.append(f"transformation:{transformation.transformation_id}")
        return _complete_result(len(self._inputs), identities)


class MultilingualEmbeddingGenerationBuilderV3:
    def __init__(
        self,
        *,
        provider: MultilingualEmbeddingProviderV3,
        store: MultilingualStoreV2,
        generation_id: UUID,
        inputs: tuple[MultilingualEmbeddingInputV3, ...],
        max_batch: int = 32,
    ) -> None:
        if not 1 <= max_batch <= 32:
            raise ValueError("V2 embedding batch exceeds governed bound")
        self._provider = provider
        self._store = store
        self._generation_id = generation_id
        self._inputs = inputs
        self._max_batch = max_batch

    async def build(self, generation_id: UUID) -> ProjectionBuildResult:
        if generation_id != self._generation_id:
            raise ValueError("embedding generation identity mismatch")
        identities: list[str] = []
        for start in range(0, len(self._inputs), self._max_batch):
            batch = self._inputs[start : start + self._max_batch]
            values = await self._provider.embed_documents_v3(batch)
            if len(values) != len(batch):
                raise RuntimeError("embedding provider changed ordered batch cardinality")
            for item, value in zip(batch, values, strict=True):
                if value.source != item.source or value.profile.generation_id != generation_id:
                    raise RuntimeError("embedding provider returned incompatible provenance")
                await self._store.put_multilingual_embedding_v3(value)
                identities.append(str(value.embedding_id))
        return _complete_result(len(self._inputs), identities)


@runtime_checkable
class MultilingualTextProjectionWriterV2(Protocol):  # pragma: no cover
    async def put_multilingual_text_projection_row_v2(
        self, row: MultilingualTextProjectionRowV2
    ) -> bool: ...


@runtime_checkable
class FullMultilingualV2Builder(Protocol):  # pragma: no cover
    async def build(self, generation_id: UUID) -> ProjectionBuildResult: ...


@runtime_checkable
class MultilingualCoverageManifestWriterV2(Protocol):  # pragma: no cover
    async def put_multilingual_coverage_manifest_v2(
        self, manifest: MultilingualCoverageManifestV2
    ) -> bool: ...


class CoverageRecordingGenerationBuilderV2:
    """Attach exact operation/language/script/representation coverage to any V2 build."""

    def __init__(
        self,
        *,
        builder: FullMultilingualV2Builder,
        store: MultilingualCoverageManifestWriterV2,
        generation_id: UUID,
        capability: str,
        profile_fingerprint: str,
        dependency_digest: str,
        rollback_metadata_digest: str,
        language_tags: tuple[str, ...],
        script_codes: tuple[str, ...],
        representation_types: tuple[str, ...],
        source_kinds: tuple[str, ...],
    ) -> None:
        self._builder = builder
        self._store = store
        self._generation_id = generation_id
        self._capability = capability
        self._profile_fingerprint = profile_fingerprint
        self._dependency_digest = dependency_digest
        self._rollback_metadata_digest = rollback_metadata_digest
        self._language_tags = tuple(sorted(set(language_tags)))
        self._script_codes = tuple(sorted(set(script_codes)))
        self._representation_types = tuple(sorted(set(representation_types)))
        self._source_kinds = tuple(sorted(set(source_kinds)))

    async def build(self, generation_id: UUID) -> ProjectionBuildResult:
        if generation_id != self._generation_id:
            raise ValueError("coverage wrapper generation identity mismatch")
        result = await self._builder.build(generation_id)
        manifest = MultilingualCoverageManifestV2(
            generation_id=generation_id,
            capability=self._capability,
            profile_fingerprint=self._profile_fingerprint,
            dependency_digest=self._dependency_digest,
            expected_count=result.expected_count,
            succeeded_count=result.succeeded_count,
            failed_count=result.failed_count,
            skipped_count=result.skipped_count,
            language_tags=self._language_tags,
            script_codes=self._script_codes,
            representation_types=self._representation_types,
            source_kinds=self._source_kinds,
            provenance_complete=result.failed_count == 0,
            authorization_compatible=result.failed_count == 0,
            rollback_metadata_digest=self._rollback_metadata_digest,
            item_identity_digest=result.checksum,
            created_at=datetime.now(UTC),
        )
        if not manifest.complete:
            raise RuntimeError("incomplete V2 build cannot publish complete coverage")
        await self._store.put_multilingual_coverage_manifest_v2(manifest)
        return result


class MultilingualTextGenerationBuilderV2:
    def __init__(
        self,
        *,
        store: MultilingualTextProjectionWriterV2,
        generation_id: UUID,
        rows: tuple[MultilingualTextProjectionRowV2, ...],
    ) -> None:
        self._store = store
        self._generation_id = generation_id
        self._rows = rows

    async def build(self, generation_id: UUID) -> ProjectionBuildResult:
        if generation_id != self._generation_id:
            raise ValueError("language text generation identity mismatch")
        for row in self._rows:
            if row.generation_id != generation_id:
                raise ValueError("language text row belongs to another generation")
            await self._store.put_multilingual_text_projection_row_v2(row)
        return _complete_result(len(self._rows), [str(row.row_id) for row in self._rows])


class MultilingualVectorGenerationBuilderV2:
    """Validate the V2 embedding space; vectors remain in the embedding rows by design."""

    def __init__(
        self,
        *,
        generation_id: UUID,
        source_embedding_generation_id: UUID,
        vector_space_identity: str,
        embeddings: tuple[MultilingualEmbeddingV3, ...],
    ) -> None:
        self._generation_id = generation_id
        self._source_embedding_generation_id = source_embedding_generation_id
        self._vector_space_identity = vector_space_identity
        self._embeddings = embeddings

    async def build(self, generation_id: UUID) -> ProjectionBuildResult:
        if generation_id != self._generation_id:
            raise ValueError("multilingual vector generation identity mismatch")
        for embedding in self._embeddings:
            if embedding.profile.generation_id != self._source_embedding_generation_id:
                raise ValueError("vector input belongs to another embedding generation")
            if embedding.profile.vector_space != self._vector_space_identity:
                raise ValueError("vector input belongs to another vector space")
        return _complete_result(
            len(self._embeddings), [str(item.embedding_id) for item in self._embeddings]
        )


def _complete_result(expected: int, identities: list[str]) -> ProjectionBuildResult:
    return ProjectionBuildResult(
        expected_count=expected,
        succeeded_count=expected,
        failed_count=0,
        skipped_count=0,
        checksum=hashlib.sha256("\n".join(sorted(identities)).encode("utf-8")).hexdigest(),
    )


def _digest(*values: str) -> str:
    if any(not value for value in values):
        raise ValueError("generation identity components must not be blank")
    return hashlib.sha256("\x1f".join(values).encode("utf-8")).hexdigest()
