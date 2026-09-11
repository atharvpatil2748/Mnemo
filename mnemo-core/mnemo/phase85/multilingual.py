"""Governed WP-10 observation, derivation, and embedding generation builders."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from mnemo.interfaces.errors import IntegrityError
from mnemo.interfaces.multilingual import (
    LanguageDetectorV1,
    LanguageEvidenceAuthorizerV2,
    LanguageTransformationProviderV2,
    MultilingualEmbeddingProviderV2,
    MultilingualStoreV1,
)
from mnemo.models.multilingual import (
    LanguageCode,
    LanguageConfidence,
    LanguageDerivation,
    LanguageDerivationKind,
    LanguageDetectionSource,
    LanguageEvidenceKindV2,
    LanguageEvidenceReferenceV2,
    LanguageObservation,
    LanguageObservationScope,
    LanguageProviderProfile,
    LanguageTransformationRequestV2,
    MultilingualEmbeddingInputV2,
    MultilingualProviderReadinessV2,
    ScriptCode,
    language_observation_id,
)
from mnemo.models.processing import ProcessingConsent
from mnemo.phase85.projections import ProjectionBuildResult, ProjectionGenerationSpec
from mnemo.retrieval.multilingual import transliterate_devanagari


@dataclass(frozen=True, slots=True, kw_only=True)
class LanguageEvidenceInputV2:
    actor_id: UUID
    source: LanguageEvidenceReferenceV2
    text: str
    declared_language: LanguageCode | None = None
    declared_script: ScriptCode | None = None
    metadata_source: LanguageDetectionSource | None = None

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("language evidence text must not be empty")
        if hashlib.sha256(self.text.encode("utf-8")).hexdigest() != (
            self.source.source_content_hash
        ):
            raise ValueError("language evidence text does not match source hash")
        supplied = (
            self.declared_language is not None,
            self.declared_script is not None,
            self.metadata_source is not None,
        )
        if any(supplied) and not all(supplied):
            raise ValueError("language metadata must provide language, script, and source together")
        if self.metadata_source is LanguageDetectionSource.LIGHTWEIGHT_DETECTOR:
            raise ValueError("detector output cannot be supplied as authoritative metadata")


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualGenerationPlanV1:
    language_derivation: ProjectionGenerationSpec
    multilingual_embedding: ProjectionGenerationSpec
    language_text: ProjectionGenerationSpec
    multilingual_vector: ProjectionGenerationSpec


def multilingual_generation_plan(
    *,
    profile_fingerprint: str,
    source_version_ids: tuple[UUID, ...],
    detector_digest: str,
    language_preprocessing_digest: str,
) -> MultilingualGenerationPlanV1:
    """Create the deterministic four-generation dependency chain for WP-10."""
    derivation = ProjectionGenerationSpec(
        capability="language_derivation",
        profile_id="unicode-en-hi-mr-conservative-v1",
        schema_version=2,
        input_scope="authorized-canonical-ocr-vision-evidence-v2",
        provider_identity="mnemo-local",
        model_identity="deterministic-devanagari-transliteration",
        model_revision="1",
        configuration_fingerprint=_combined_digest(
            profile_fingerprint, detector_digest, language_preprocessing_digest
        ),
        source_version_ids=source_version_ids,
    )
    embedding = ProjectionGenerationSpec(
        capability="multilingual_embedding",
        profile_id="bge-m3-query-v1",
        schema_version=2,
        input_scope="authorized-language-evidence-v2",
        provider_identity="sentence-transformers",
        model_identity="BAAI/bge-m3",
        model_revision="5617a9f61b028005a4858fdac845db406aefb181",
        configuration_fingerprint=profile_fingerprint,
        source_version_ids=source_version_ids,
        source_generation_ids=(derivation.generation_id,),
        dimensions=1024,
    )
    language_text = ProjectionGenerationSpec(
        capability="language_text",
        profile_id="unicode-en-hi-mr-conservative-v1",
        schema_version=1,
        input_scope="active-language-derivations",
        provider_identity="mnemo-local",
        model_identity=None,
        model_revision=None,
        configuration_fingerprint=profile_fingerprint,
        source_version_ids=source_version_ids,
        source_generation_ids=(derivation.generation_id,),
    )
    multilingual_vector = ProjectionGenerationSpec(
        capability="multilingual_vector",
        profile_id="bge-m3-query-v1",
        schema_version=1,
        input_scope="active-multilingual-embeddings",
        provider_identity="sentence-transformers",
        model_identity="BAAI/bge-m3",
        model_revision="5617a9f61b028005a4858fdac845db406aefb181",
        configuration_fingerprint=profile_fingerprint,
        source_version_ids=source_version_ids,
        source_generation_ids=(embedding.generation_id,),
        dimensions=1024,
    )
    return MultilingualGenerationPlanV1(
        language_derivation=derivation,
        multilingual_embedding=embedding,
        language_text=language_text,
        multilingual_vector=multilingual_vector,
    )


class DeterministicTransliterationProvider:
    """Local, restart-safe Devanagari transliteration; translation remains optional."""

    def __init__(self, profile: LanguageProviderProfile) -> None:
        self._profile = profile
        self._initialized = False

    async def initialize(self) -> None:
        self._initialized = True

    async def close(self) -> None:
        self._initialized = False

    async def readiness(self) -> MultilingualProviderReadinessV2:
        return MultilingualProviderReadinessV2(
            available_locally=True,
            loadable=True,
            initialized=self._initialized,
            exact_identity=True,
            reason_code="provider_ready" if self._initialized else "provider_not_initialized",
        )

    async def capabilities(self) -> LanguageProviderProfile:
        return self._profile

    async def transform(self, request: LanguageTransformationRequestV2) -> LanguageDerivation:
        if not self._initialized:
            raise IntegrityError("transliteration provider is not initialized")
        if request.kind is not LanguageDerivationKind.TRANSLITERATION:
            raise IntegrityError("deterministic provider supports transliteration only")
        output = transliterate_devanagari(request.source_text)
        if not output.strip() or output == request.source_text:
            raise IntegrityError("transliteration produced no governed derived representation")
        cache_key = request.cache_key()
        return LanguageDerivation(
            derivation_id=request.derivation_id(),
            cache_key=cache_key,
            actor_id=request.actor_id,
            notebook_id=request.source.notebook_id,
            document_id=request.source.document_id,
            version_id=request.source.version_id,
            source_evidence_id=request.source.evidence_id,
            source_hash=request.source.source_content_hash,
            source_language=request.source_language,
            target_language=request.target_language,
            kind=request.kind,
            output_text=output,
            output_hash=hashlib.sha256(output.encode("utf-8")).hexdigest(),
            provider_profile=request.provider_profile,
            preprocessing_digest=request.preprocessing_digest,
            generation_id=request.generation_id,
            created_at=datetime.now(UTC),
            source_reference=request.source,
        )


class LanguageObservationDerivationBuilder:
    """Consumes explicitly authorized immutable sources; never enumerates evidence."""

    def __init__(
        self,
        *,
        store: MultilingualStoreV1,
        detector: LanguageDetectorV1,
        authorizer: LanguageEvidenceAuthorizerV2,
        transformer: LanguageTransformationProviderV2,
        generation_id: UUID,
        preprocessing_digest: str,
        consent: ProcessingConsent,
        inputs: tuple[LanguageEvidenceInputV2, ...],
    ) -> None:
        self._store = store
        self._detector = detector
        self._authorizer = authorizer
        self._transformer = transformer
        self._generation_id = generation_id
        self._preprocessing_digest = preprocessing_digest
        self._consent = consent
        self._inputs = inputs

    async def build(self, generation_id: UUID) -> ProjectionBuildResult:
        if generation_id != self._generation_id:
            raise IntegrityError("language derivation generation identity mismatch")
        succeeded: list[str] = []
        failed = 0
        profile = await self._transformer.capabilities()
        for item in self._inputs:
            try:
                if not await self._authorizer.authorize_language_evidence(
                    item.actor_id, item.source
                ):
                    raise IntegrityError("language evidence authorization denied")
                observation = await self._observe(item)
                existing_observation = await self._store.get_authorized_language_observation(
                    actor_id=item.actor_id,
                    notebook_id=item.source.notebook_id,
                    observation_id=observation.observation_id,
                )
                if existing_observation is None:
                    await self._store.put_language_observation(observation)
                succeeded.append(f"observation:{observation.observation_id}")
                if observation.script.value == "Deva" and observation.language.value in {
                    "hi",
                    "mr",
                }:
                    request = LanguageTransformationRequestV2(
                        actor_id=item.actor_id,
                        source=item.source,
                        source_text=item.text,
                        source_language=observation.language,
                        target_language=observation.language,
                        kind=LanguageDerivationKind.TRANSLITERATION,
                        provider_profile=profile,
                        preprocessing_digest=self._preprocessing_digest,
                        generation_id=generation_id,
                        consent=self._consent,
                    )
                    existing = await self._store.get_authorized_language_derivation_by_cache_key(
                        actor_id=item.actor_id,
                        notebook_id=item.source.notebook_id,
                        cache_key=request.cache_key(),
                    )
                    derivation = existing or await self._transformer.transform(request)
                    if existing is None:
                        await self._store.put_language_derivation(derivation)
                    succeeded.append(f"derivation:{derivation.derivation_id}")
            except IntegrityError:
                raise
            except Exception:
                failed += 1
        return _build_result(len(self._inputs), succeeded, failed)

    async def _observe(self, item: LanguageEvidenceInputV2) -> LanguageObservation:
        if item.declared_language is None:
            return await self._detector.detect(
                actor_id=item.actor_id,
                notebook_id=item.source.notebook_id,
                target_id=item.source.identity_digest,
                text=item.text,
                document_id=item.source.document_id,
                version_id=item.source.version_id,
            )
        assert item.declared_script is not None and item.metadata_source is not None
        configuration_digest = hashlib.sha256(
            f"metadata-precedence-v1:{item.metadata_source.value}".encode()
        ).hexdigest()
        input_hash = item.source.source_content_hash
        scope = _scope(item.source.kind)
        return LanguageObservation(
            observation_id=language_observation_id(
                notebook_id=item.source.notebook_id,
                target_scope=scope,
                target_id=item.source.identity_digest,
                detector="authoritative-language-metadata",
                detector_revision="1",
                configuration_digest=configuration_digest,
                input_hash=input_hash,
            ),
            actor_id=item.actor_id,
            notebook_id=item.source.notebook_id,
            document_id=item.source.document_id,
            version_id=item.source.version_id,
            target_scope=scope,
            target_id=item.source.identity_digest,
            language=item.declared_language,
            script=item.declared_script,
            confidence=LanguageConfidence(value=1.0, calibrated=True),
            detection_source=item.metadata_source,
            detector="authoritative-language-metadata",
            detector_revision="1",
            configuration_digest=configuration_digest,
            input_hash=input_hash,
            mixed_language=False,
            mixed_script=False,
            region=None,
            created_at=datetime.now(UTC),
        )


class MultilingualEmbeddingGenerationBuilder:
    """Ordered, idempotent embedding build over caller-authorized sources."""

    def __init__(
        self,
        *,
        store: MultilingualStoreV1,
        provider: MultilingualEmbeddingProviderV2,
        authorizer: LanguageEvidenceAuthorizerV2,
        generation_id: UUID,
        inputs: tuple[LanguageEvidenceInputV2, ...],
    ) -> None:
        self._store = store
        self._provider = provider
        self._authorizer = authorizer
        self._generation_id = generation_id
        self._inputs = inputs

    async def build(self, generation_id: UUID) -> ProjectionBuildResult:
        if generation_id != self._generation_id:
            raise IntegrityError("multilingual embedding generation identity mismatch")
        profile = await self._provider.profile()
        if profile.generation_id != generation_id:
            raise IntegrityError("provider profile belongs to another generation")
        authorized: list[MultilingualEmbeddingInputV2] = []
        for item in self._inputs:
            if not await self._authorizer.authorize_language_evidence(item.actor_id, item.source):
                raise IntegrityError("language evidence authorization denied")
            observation = await self._detector_observation(item)
            authorized.append(
                MultilingualEmbeddingInputV2(
                    source=item.source,
                    text=item.text,
                    language=observation,
                )
            )
        succeeded: list[str] = []
        failed = 0
        for start in range(0, len(authorized), 32):
            batch = tuple(authorized[start : start + 32])
            try:
                embeddings = await self._provider.embed_documents(batch)
                if len(embeddings) != len(batch):
                    raise IntegrityError("embedding provider changed ordered batch cardinality")
                for embedding in embeddings:
                    await self._store.put_multilingual_embedding(embedding)
                    succeeded.append(str(embedding.embedding_id))
            except IntegrityError:
                raise
            except Exception:
                failed += len(batch)
        return _build_result(len(authorized), succeeded, failed)

    async def _detector_observation(self, item: LanguageEvidenceInputV2) -> LanguageCode:
        if item.declared_language is not None:
            return item.declared_language
        raise IntegrityError(
            "embedding generation requires a persisted/governed language observation"
        )


def _scope(kind: LanguageEvidenceKindV2) -> LanguageObservationScope:
    if kind is LanguageEvidenceKindV2.CANONICAL_CHUNK:
        return LanguageObservationScope.CHUNK
    if kind is LanguageEvidenceKindV2.OCR_REGION:
        return LanguageObservationScope.OCR_REGION
    return LanguageObservationScope.ASSET


def _build_result(expected: int, succeeded: list[str], failed: int) -> ProjectionBuildResult:
    checksum = hashlib.sha256("\n".join(sorted(succeeded)).encode()).hexdigest()
    return ProjectionBuildResult(
        expected_count=expected,
        succeeded_count=expected - failed,
        failed_count=failed,
        skipped_count=0,
        checksum=checksum,
    )


def _combined_digest(*values: str) -> str:
    return hashlib.sha256("\x1f".join(values).encode()).hexdigest()
