"""Registry-driven language and script observation without script→language inference."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from mnemo.interfaces.multilingual import LanguageDetectorProviderV2, ScriptDetectorV1
from mnemo.models.multilingual import (
    LanguageCode,
    LanguageConfidence,
    LanguageEvidenceKindV3,
    LanguageEvidenceReferenceV3,
    LanguageHypothesisV2,
    LanguageObservationScope,
    LanguageObservationV2,
    ObservationAuthorityClass,
    ScriptCode,
    ScriptHypothesisV1,
    ScriptObservationV1,
    language_observation_v2_id,
    script_observation_v1_id,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class DetectorRegistrationV1:
    provider: object
    priority: int
    configured: bool
    ready: bool
    enabled: bool
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if self.priority < 0:
            raise ValueError("detector priority must be non-negative")
        if self.enabled and (not self.configured or not self.ready):
            raise ValueError("enabled detector must be configured and ready")


class LanguageDetectorRegistryV2:
    def __init__(self, registrations: tuple[DetectorRegistrationV1, ...]) -> None:
        usable: list[tuple[DetectorRegistrationV1, LanguageDetectorProviderV2]] = []
        identities: set[str] = set()
        for registration in registrations:
            if not isinstance(registration.provider, LanguageDetectorProviderV2):
                raise TypeError("language detector registration has invalid provider")
            provider = registration.provider
            identity = provider.detector_id
            if identity in identities:
                raise ValueError("duplicate language detector identity")
            identities.add(identity)
            usable.append((registration, provider))
        self._registrations = tuple(
            sorted(usable, key=lambda item: (item[0].priority, item[1].detector_id))
        )

    async def detect(
        self,
        *,
        actor_id: UUID,
        notebook_id: UUID,
        target_id: str,
        text: str,
        source: LanguageEvidenceReferenceV3 | None = None,
    ) -> LanguageObservationV2:
        for item, provider in self._registrations:
            if item.configured and item.ready and item.enabled:
                return await provider.detect_languages(
                    actor_id=actor_id,
                    notebook_id=notebook_id,
                    target_id=target_id,
                    text=text,
                    source=source,
                )
        raise LookupError("no configured ready language detector")


class ScriptDetectorRegistryV1:
    def __init__(self, registrations: tuple[DetectorRegistrationV1, ...]) -> None:
        usable: list[tuple[DetectorRegistrationV1, ScriptDetectorV1]] = []
        identities: set[str] = set()
        for registration in registrations:
            if not isinstance(registration.provider, ScriptDetectorV1):
                raise TypeError("script detector registration has invalid provider")
            provider = registration.provider
            identity = provider.detector_id
            if identity in identities:
                raise ValueError("duplicate script detector identity")
            identities.add(identity)
            usable.append((registration, provider))
        self._registrations = tuple(
            sorted(usable, key=lambda item: (item[0].priority, item[1].detector_id))
        )

    async def detect(
        self,
        *,
        actor_id: UUID,
        notebook_id: UUID,
        target_id: str,
        text: str,
        source: LanguageEvidenceReferenceV3 | None = None,
    ) -> ScriptObservationV1:
        for item, provider in self._registrations:
            if item.configured and item.ready and item.enabled:
                return await provider.detect_scripts(
                    actor_id=actor_id,
                    notebook_id=notebook_id,
                    target_id=target_id,
                    text=text,
                    source=source,
                )
        raise LookupError("no configured ready script detector")


class UnknownLanguageDetectorV2:
    """Fail-closed fallback: never infers language from text or script."""

    detector_id = "unknown-language-fallback-v2"
    detector_revision = "1"
    configuration_digest = hashlib.sha256(b"unknown-language-fallback-v2:1").hexdigest()

    async def detect_languages(
        self,
        *,
        actor_id: UUID,
        notebook_id: UUID,
        target_id: str,
        text: str,
        source: LanguageEvidenceReferenceV3 | None = None,
    ) -> LanguageObservationV2:
        input_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if source is not None and source.source_content_hash != input_hash:
            raise ValueError("language detector input conflicts with source evidence")
        hypothesis = LanguageHypothesisV2(
            language=LanguageCode("und"),
            confidence=LanguageConfidence(value=0.0, calibrated=False),
            authority_class=ObservationAuthorityClass.UNKNOWN,
            evidence_digest=_digest({"detector": self.detector_id, "input_hash": input_hash}),
        )
        observation_id = language_observation_v2_id(
            notebook_id=notebook_id,
            target_scope=_source_scope(source),
            target_id=target_id,
            detector=self.detector_id,
            detector_revision=self.detector_revision,
            configuration_digest=self.configuration_digest,
            input_hash=input_hash,
            source_reference_digest=None if source is None else source.identity_digest,
        )
        return LanguageObservationV2(
            observation_id=observation_id,
            actor_id=actor_id,
            notebook_id=notebook_id,
            target_scope=_source_scope(source),
            target_id=target_id,
            hypotheses=(hypothesis,),
            detector=self.detector_id,
            detector_revision=self.detector_revision,
            configuration_digest=self.configuration_digest,
            input_hash=input_hash,
            mixed_language=False,
            source_reference=source,
            created_at=datetime.now(UTC),
        )


class ConfiguredUnicodeScriptDetectorV1:
    """Configured codepoint-range detector that emits scripts, never languages."""

    detector_id = "configured-unicode-script-detector-v1"
    detector_revision = "1"

    def __init__(self, ranges: dict[str, tuple[tuple[int, int], ...]]) -> None:
        normalized: dict[ScriptCode, tuple[tuple[int, int], ...]] = {}
        for raw_script, raw_ranges in ranges.items():
            script = ScriptCode(raw_script)
            if any(start < 0 or end < start or end > 0x10FFFF for start, end in raw_ranges):
                raise ValueError("invalid configured Unicode script range")
            normalized[script] = tuple(raw_ranges)
        self._ranges = normalized
        self.configuration_digest = _digest(
            {
                script.value: [list(item) for item in values]
                for script, values in sorted(normalized.items(), key=lambda item: item[0].value)
            }
        )

    async def detect_scripts(
        self,
        *,
        actor_id: UUID,
        notebook_id: UUID,
        target_id: str,
        text: str,
        source: LanguageEvidenceReferenceV3 | None = None,
    ) -> ScriptObservationV1:
        input_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if source is not None and source.source_content_hash != input_hash:
            raise ValueError("script detector input conflicts with source evidence")
        counts: dict[ScriptCode, int] = {}
        for char in text:
            codepoint = ord(char)
            for script, ranges in self._ranges.items():
                if any(start <= codepoint <= end for start, end in ranges):
                    # Common and Inherited code points (punctuation, digits,
                    # combining marks) are not independent script evidence and
                    # must not turn an otherwise single-script item into mixed.
                    if script.value not in {"Zyyy", "Zinh"}:
                        counts[script] = counts.get(script, 0) + 1
                    break
        total = sum(counts.values())
        hypotheses = tuple(
            ScriptHypothesisV1(
                script=script,
                confidence=LanguageConfidence(
                    value=count / total if total else 0.0, calibrated=False
                ),
                authority_class=ObservationAuthorityClass.GOVERNED_DETECTOR,
                evidence_digest=_digest(
                    {"script": script.value, "count": count, "input_hash": input_hash}
                ),
            )
            for script, count in sorted(counts.items(), key=lambda item: item[0].value)
        )
        if not hypotheses:
            hypotheses = (
                ScriptHypothesisV1(
                    script=ScriptCode("Zzzz"),
                    confidence=LanguageConfidence(value=0.0, calibrated=False),
                    authority_class=ObservationAuthorityClass.UNKNOWN,
                    evidence_digest=_digest({"script": "Zzzz", "input_hash": input_hash}),
                ),
            )
        scope = _source_scope(source)
        observation_id = script_observation_v1_id(
            notebook_id=notebook_id,
            target_scope=scope,
            target_id=target_id,
            detector=self.detector_id,
            detector_revision=self.detector_revision,
            configuration_digest=self.configuration_digest,
            input_hash=input_hash,
            source_reference_digest=None if source is None else source.identity_digest,
        )
        return ScriptObservationV1(
            observation_id=observation_id,
            actor_id=actor_id,
            notebook_id=notebook_id,
            target_scope=scope,
            target_id=target_id,
            hypotheses=hypotheses,
            detector=self.detector_id,
            detector_revision=self.detector_revision,
            configuration_digest=self.configuration_digest,
            input_hash=input_hash,
            mixed_script=len(hypotheses) > 1,
            source_reference=source,
            created_at=datetime.now(UTC),
        )


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _source_scope(
    source: LanguageEvidenceReferenceV3 | None,
) -> LanguageObservationScope:
    if source is None:
        return LanguageObservationScope.QUERY
    if source.kind is LanguageEvidenceKindV3.CANONICAL_CHUNK:
        return LanguageObservationScope.CHUNK
    if source.kind is LanguageEvidenceKindV3.OCR_REGION:
        return LanguageObservationScope.OCR_REGION
    if source.kind in {
        LanguageEvidenceKindV3.OCR_OCCURRENCE,
        LanguageEvidenceKindV3.VISION_DERIVATION,
    }:
        return LanguageObservationScope.ASSET
    # Derived text inherits an evidence identity rather than pretending to be
    # a canonical chunk.  The existing scope enum has no generic derivation
    # member, so document is the narrowest non-fabricated V1-compatible scope.
    return LanguageObservationScope.DOCUMENT
