"""Authorized generic observation and transformation pipeline for text representations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from uuid import UUID

from mnemo.interfaces.multilingual import RepresentationEvidenceAuthorizerV3
from mnemo.interfaces.text_representations import (
    RepresentationDetectorV1,
    RepresentationTransformerV1,
)
from mnemo.models.multilingual import (
    EvidenceLineageOriginV3,
    LanguageEvidenceKindV3,
    LanguageEvidenceReferenceV3,
)
from mnemo.models.text_representations import (
    AuthorizationScopeV1,
    RepresentationAuthority,
    RepresentationAuthorityClass,
    RepresentationObservationV1,
    RepresentationTransformationV1,
    TextRepresentationReferenceV1,
    TextRepresentationType,
    TransformationProfileV1,
    TransformationProvenanceV1,
    TransformationRegistryEntryV1,
    content_hash,
    representation_observation_id,
    representation_transformation_id,
    text_representation_reference_id,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class RepresentationDetectionResultV1:
    representation_type: TextRepresentationType
    confidence: float
    calibrated: bool
    authority_class: RepresentationAuthorityClass


class ConfiguredRepresentationDetectorV1(RepresentationDetectorV1):
    """Generic detector whose classification policy is injected as governed configuration."""

    def __init__(
        self,
        *,
        detector_id: str,
        detector_revision: str,
        configuration_digest: str,
        classify: object,
    ) -> None:
        if not callable(classify):
            raise TypeError("representation classifier must be callable")
        self._detector_id = detector_id
        self._detector_revision = detector_revision
        self._configuration_digest = configuration_digest
        self._classify = classify

    async def observe(
        self,
        *,
        actor_id: UUID,
        source: LanguageEvidenceReferenceV3,
        text: str,
        authorization_scope: AuthorizationScopeV1,
    ) -> RepresentationObservationV1:
        del actor_id
        _validate_authorized_scope(authorization_scope, source)
        if content_hash(text) != source.source_content_hash:
            raise ValueError("representation detector text conflicts with source hash")
        result = self._classify(text)
        if not isinstance(result, RepresentationDetectionResultV1):
            raise TypeError("representation classifier returned an invalid result")
        now = datetime.now(UTC)
        identity = representation_observation_id(
            source_reference_digest=source.identity_digest,
            detector_id=self._detector_id,
            detector_revision=self._detector_revision,
            configuration_digest=self._configuration_digest,
            input_content_hash=source.source_content_hash,
            representation_type=result.representation_type,
        )
        return RepresentationObservationV1(
            observation_id=identity,
            source_reference=source,
            representation_type=result.representation_type,
            detector_id=self._detector_id,
            detector_revision=self._detector_revision,
            configuration_digest=self._configuration_digest,
            input_content_hash=source.source_content_hash,
            confidence=result.confidence,
            calibrated=result.calibrated,
            authority_class=result.authority_class,
            language_observation_references=(),
            script_observation_references=(),
            created_at=now,
        )


class DeterministicTransformationRegistryV1:
    """Exact representation/profile registry; never routes by language, script, or filename."""

    def __init__(
        self,
        registrations: tuple[
            tuple[TransformationRegistryEntryV1, RepresentationTransformerV1], ...
        ],
    ) -> None:
        by_profile: dict[
            str, tuple[TransformationRegistryEntryV1, RepresentationTransformerV1]
        ] = {}
        for entry, transformer in registrations:
            if entry.profile.profile_id in by_profile:
                raise ValueError("duplicate transformation profile registration")
            if not isinstance(transformer, RepresentationTransformerV1):
                raise TypeError("transformer does not implement RepresentationTransformerV1")
            by_profile[entry.profile.profile_id] = (entry, transformer)
        self._registrations: Mapping[
            str, tuple[TransformationRegistryEntryV1, RepresentationTransformerV1]
        ] = MappingProxyType(by_profile)

    def entries(self) -> tuple[TransformationRegistryEntryV1, ...]:
        return tuple(
            item[0] for _, item in sorted(self._registrations.items(), key=lambda row: row[0])
        )

    def select(
        self,
        *,
        observation: RepresentationObservationV1,
        target_profile_id: str | None = None,
    ) -> TransformationRegistryEntryV1 | None:
        candidates: tuple[
            tuple[TransformationRegistryEntryV1, RepresentationTransformerV1], ...
        ] = tuple(self._registrations.values())
        if target_profile_id is not None:
            selected = self._registrations.get(target_profile_id)
            candidates = () if selected is None else (selected,)
        for entry, _ in sorted(candidates, key=lambda item: item[0].profile.profile_id):
            if (
                entry.configured
                and entry.provider_ready
                and entry.enabled
                and observation.representation_type in entry.profile.allowed_source_representations
            ):
                return entry
        return None

    def resolve(self, entry: TransformationRegistryEntryV1) -> RepresentationTransformerV1:
        registered = self._registrations.get(entry.profile.profile_id)
        if registered is None or registered[0] != entry:
            raise ValueError("transformation registry entry is not registered")
        return registered[1]


class GovernedMappingRepresentationTransformerV1:
    """Generic offline longest-match text transducer driven only by a frozen profile."""

    def __init__(
        self,
        *,
        mapping: Mapping[str, str],
        unmapped_policy: str,
    ) -> None:
        if not mapping or any(not key or not value for key, value in mapping.items()):
            raise ValueError("transformation mapping requires non-empty keys and values")
        if unmapped_policy not in {"preserve_unmapped", "reject_unmapped"}:
            raise ValueError("unsupported transformation unmapped policy")
        self._mapping = MappingProxyType(dict(mapping))
        self._keys = tuple(sorted(mapping, key=lambda value: (-len(value), value)))
        self._unmapped_policy = unmapped_policy
        self.configuration_digest = hashlib.sha256(
            json.dumps(
                {
                    "mapping": dict(sorted(mapping.items())),
                    "unmapped_policy": unmapped_policy,
                    "algorithm": "deterministic-longest-match-v1",
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        self._initialized = False

    async def initialize(self) -> None:
        self._initialized = True

    async def close(self) -> None:
        self._initialized = False

    async def ready(self) -> bool:
        return self._initialized

    async def transform(
        self,
        *,
        actor_id: UUID,
        source: TextRepresentationReferenceV1,
        source_text: str,
        observation: RepresentationObservationV1,
        profile: TransformationProfileV1,
        authorization_scope: AuthorizationScopeV1,
    ) -> str:
        del actor_id
        if not self._initialized:
            raise RuntimeError("representation transformer is not initialized")
        _validate_authorized_scope(authorization_scope, source.evidence_reference)
        if profile.configuration_digest != self.configuration_digest:
            raise ValueError("mapping transformer configuration differs from governed profile")
        if source.representation_type not in profile.allowed_source_representations:
            raise ValueError("source representation is not admitted by transformation profile")
        if content_hash(source_text) != source.content_hash:
            raise ValueError("mapping transformer source content hash mismatch")
        output: list[str] = []
        offset = 0
        while offset < len(source_text):
            matched = next((key for key in self._keys if source_text.startswith(key, offset)), None)
            if matched is not None:
                output.append(self._mapping[matched])
                offset += len(matched)
                continue
            if self._unmapped_policy == "reject_unmapped":
                raise ValueError("source contains an unmapped representation sequence")
            output.append(source_text[offset])
            offset += 1
        transformed = "".join(output)
        if not transformed.strip() or transformed == source_text:
            raise ValueError("mapping transformation produced no distinct semantic output")
        return transformed


class RepresentationPipelineV1:
    """Authorize, observe, transform, and construct immutable derived lineage."""

    def __init__(
        self,
        *,
        authorizer: RepresentationEvidenceAuthorizerV3,
        detector: RepresentationDetectorV1,
        registry: DeterministicTransformationRegistryV1,
    ) -> None:
        self._authorizer = authorizer
        self._detector = detector
        self._registry = registry

    async def observe(
        self,
        *,
        actor_id: UUID,
        source: LanguageEvidenceReferenceV3,
        text: str,
    ) -> tuple[AuthorizationScopeV1, RepresentationObservationV1]:
        scope = await self._authorizer.authorize_language_evidence_v3(actor_id, source)
        if scope is None:
            raise PermissionError("representation source is not authorized")
        _validate_authorized_scope(scope, source)
        observation = await self._detector.observe(
            actor_id=actor_id,
            source=source,
            text=text,
            authorization_scope=scope,
        )
        return scope, observation

    async def transform(
        self,
        *,
        actor_id: UUID,
        source: LanguageEvidenceReferenceV3,
        source_text: str,
        source_representation: TextRepresentationReferenceV1,
        observation: RepresentationObservationV1,
        generation_id: UUID,
        target_profile_id: str | None = None,
    ) -> tuple[str, RepresentationTransformationV1]:
        scope = await self._authorizer.authorize_language_evidence_v3(actor_id, source)
        if scope is None:
            raise PermissionError("representation source is not authorized")
        _validate_authorized_scope(scope, source)
        if source_representation.evidence_reference != source:
            raise ValueError("representation source reference mismatch")
        if content_hash(source_text) != source.source_content_hash:
            raise ValueError("representation source text hash mismatch")
        if observation.source_reference != source:
            raise ValueError("representation observation source mismatch")
        entry = self._registry.select(observation=observation, target_profile_id=target_profile_id)
        if entry is None:
            raise LookupError("no ready governed transformation is available")
        transformer = self._registry.resolve(entry)
        output_text = await transformer.transform(
            actor_id=actor_id,
            source=source_representation,
            source_text=source_text,
            observation=observation,
            profile=entry.profile,
            authorization_scope=scope,
        )
        if not isinstance(output_text, str) or not output_text.strip():
            raise ValueError("transformation produced no usable derived representation")
        output_hash = content_hash(output_text)
        transformation_id = representation_transformation_id(
            source_reference_digest=source.identity_digest,
            source_representation_reference_id=source_representation.reference_id,
            profile=entry.profile,
            input_content_hash=source.source_content_hash,
            target_representation=entry.profile.target_representation,
            generation_id=generation_id,
        )
        derived_evidence = LanguageEvidenceReferenceV3(
            notebook_id=source.notebook_id,
            source_id=source.source_id,
            document_id=source.document_id,
            version_id=source.version_id,
            kind=LanguageEvidenceKindV3.REPRESENTATION_DERIVATION,
            evidence_id=str(transformation_id),
            source_content_hash=output_hash,
            lineage_origin=EvidenceLineageOriginV3.NATIVE_V3,
            occurrence_id=source.occurrence_id,
            derivation_id=transformation_id,
            source_generation_id=generation_id,
            parent_evidence_reference_digest=source.identity_digest,
        )
        source_generations = tuple(
            dict.fromkeys(
                (
                    *((source.source_generation_id,) if source.source_generation_id else ()),
                    generation_id,
                )
            )
        )
        output_reference_id = text_representation_reference_id(
            evidence_reference_digest=derived_evidence.identity_digest,
            representation_type=entry.profile.target_representation,
            authority=RepresentationAuthority.REPRESENTATION_DERIVED,
            content_hash=output_hash,
            observation_id=observation.observation_id,
            derivation_id=transformation_id,
            source_generation_ids=source_generations,
        )
        output_reference = TextRepresentationReferenceV1(
            reference_id=output_reference_id,
            evidence_reference=derived_evidence,
            representation_type=entry.profile.target_representation,
            representation_authority=RepresentationAuthority.REPRESENTATION_DERIVED,
            content_hash=output_hash,
            representation_observation_id=observation.observation_id,
            representation_derivation_id=transformation_id,
            source_generation_ids=source_generations,
            language_observation_references=source_representation.language_observation_references,
            script_observation_references=source_representation.script_observation_references,
        )
        provenance = TransformationProvenanceV1(
            source_reference_digest=source.identity_digest,
            source_representation_reference_id=source_representation.reference_id,
            source_representation_observation_id=observation.observation_id,
            profile_id=entry.profile.profile_id,
            profile_configuration_digest=entry.profile.configuration_digest,
            input_content_hash=source.source_content_hash,
            output_content_hash=output_hash,
            generation_id=generation_id,
            authorization_scope_digest=scope.actor_scope_digest,
        )
        transformation = RepresentationTransformationV1(
            transformation_id=transformation_id,
            source_representation=source_representation,
            source_observation=observation,
            transformation_profile=entry.profile,
            target_representation_type=entry.profile.target_representation,
            input_content_hash=source.source_content_hash,
            output_content_hash=output_hash,
            output_reference=output_reference,
            generation_id=generation_id,
            source_generation_ids=source_generations,
            authorization_scope=scope,
            language_observation_references=source_representation.language_observation_references,
            script_observation_references=source_representation.script_observation_references,
            provenance=provenance,
            created_at=datetime.now(UTC),
        )
        return output_text, transformation


def _validate_authorized_scope(
    scope: AuthorizationScopeV1, source: LanguageEvidenceReferenceV3
) -> None:
    if (
        scope.notebook_id != source.notebook_id
        or scope.source_id != source.source_id
        or scope.document_id != source.document_id
        or scope.version_id != source.version_id
        or scope.occurrence_id != source.occurrence_id
        or scope.derivation_id != source.derivation_id
    ):
        raise PermissionError("authorization scope conflicts with source evidence")


def deterministic_configuration_digest(value: Mapping[str, object]) -> str:
    return hashlib.sha256(
        repr(tuple(sorted(value.items(), key=lambda item: item[0]))).encode("utf-8")
    ).hexdigest()
