"""Build real BGE-M3 V2 evidence generations in a fresh isolated notebook.

This builder never changes canonical chunks or promotes any generation. Its
caller must run a separate whole-notebook coverage/compatibility gate first.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from mnemo.models.multilingual import (
    LanguageCode,
    LanguageEvidenceKindV3,
    LanguageEvidenceReferenceV3,
)
from mnemo.models.multilingual_embeddings import (
    MultilingualEmbeddingInputV3,
    MultilingualEmbeddingV3,
)
from mnemo.models.multilingual_index import (
    MultilingualEvidencePositionV1,
    MultilingualTextProjectionRowV2,
    multilingual_text_projection_row_v2_id,
)
from mnemo.models.text_representations import (
    RepresentationAuthority,
    RepresentationAuthorityClass,
    RepresentationObservationV1,
    TextRepresentationReferenceV1,
    TextRepresentationType,
    representation_observation_id,
    text_representation_reference_id,
)
from mnemo.phase85.full_multilingual_v2 import (
    CoverageRecordingGenerationBuilderV2,
    MultilingualEmbeddingGenerationBuilderV3,
    MultilingualTextGenerationBuilderV2,
    MultilingualVectorGenerationBuilderV2,
    full_multilingual_v2_generation_plan,
)
from mnemo.phase85.profiles import ModelProfileDocument
from mnemo.phase85.projections import DerivedProjectionCoordinator, ProjectionBuildResult
from mnemo.retrieval.multilingual_providers import BGEM3EmbeddingProvider
from mnemo.storage.sqlite import SQLiteStore


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class _Item:
    source: LanguageEvidenceReferenceV3
    text: str
    language: LanguageCode
    position: MultilingualEvidencePositionV1
    observation: RepresentationObservationV1
    representation: TextRepresentationReferenceV1


def _items(
    database: Path,
    notebook_id: UUID,
    language_fallbacks: list[dict[str, str]] | None = None,
) -> tuple[_Item, ...]:
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        source_by_document = {
            str(row[0]): UUID(str(row[1]))
            for row in connection.execute(
                "SELECT document_id,source_id FROM sources WHERE notebook_id=?",
                (str(notebook_id),),
            )
        }
        if not source_by_document:
            raise ValueError("isolated notebook has no authorized source memberships")
        records: list[
            tuple[
                LanguageEvidenceKindV3,
                sqlite3.Row,
                str,
                str,
                str | None,
                str | None,
                str | None,
                int | None,
                str,
            ]
        ] = []
        parsed_by_version: dict[str, dict[str, object]] = {}
        for version in connection.execute("SELECT version_id FROM document_versions"):
            version_id = str(version[0])
            path = database.parent / "files/parsed" / version_id[:8] / f"{version_id}.ir.json"
            parsed_by_version[version_id] = json.loads(path.read_text(encoding="utf-8"))
        for row in connection.execute(
            "SELECT id,document_id,version_id,text,position_page_number,"
            "source_start_ordinal,source_end_ordinal FROM chunks "
            "ORDER BY version_id,position_chunk_index"
        ):
            if str(row["document_id"]) in source_by_document and str(row["text"]).strip():
                parsed = parsed_by_version[str(row["version_id"])]
                blocks = parsed["blocks"]
                assert isinstance(blocks, list)
                languages = {
                    str(block.get("language") or parsed.get("language") or "und")
                    for block in blocks[
                        int(row["source_start_ordinal"]) : int(row["source_end_ordinal"]) + 1
                    ]
                }
                language = next(iter(languages)) if len(languages) == 1 else "und"
                records.append(
                    (
                        LanguageEvidenceKindV3.CANONICAL_CHUNK,
                        row,
                        str(row["id"]),
                        str(row["text"]),
                        None,
                        None,
                        None,
                        row["position_page_number"],
                        language,
                    )
                )
        for row in connection.execute(
            "SELECT r.region_id,r.text,r.page_number,o.document_id,o.version_id,"
            "o.occurrence_id,o.derivation_id,o.generation_id,r.language_code "
            "FROM ocr_regions r JOIN ocr_results o USING(derivation_id) "
            "WHERE o.completeness='complete' "
            "ORDER BY o.version_id,r.page_number,r.order_index"
        ):
            if str(row["document_id"]) in source_by_document and str(row["text"]).strip():
                records.append(
                    (
                        LanguageEvidenceKindV3.OCR_REGION,
                        row,
                        str(row["region_id"]),
                        str(row["text"]),
                        str(row["occurrence_id"]),
                        str(row["derivation_id"]),
                        str(row["generation_id"]),
                        int(row["page_number"]),
                        str(row["language_code"] or "und"),
                    )
                )
        for row in connection.execute(
            "SELECT v.derivation_id,v.document_id,v.version_id,v.occurrence_id,"
            "v.generation_id,v.payload,o.locator "
            "FROM vision_results v JOIN asset_occurrences o USING(occurrence_id) "
            "WHERE v.completeness='complete' ORDER BY v.version_id,v.derivation_id"
        ):
            if str(row["document_id"]) not in source_by_document:
                continue
            payload = json.loads(str(row["payload"]))
            parts = [str(item.get("text", "")).strip() for item in payload.get("captions", [])]
            parts += [
                str(item.get("value", "")).strip() for item in payload.get("observations", [])
            ]
            parts += [str(item.get("name", "")).strip() for item in payload.get("entities", [])]
            content = "\n".join(part for part in parts if part)
            if not content:
                continue
            locator = json.loads(str(row["locator"]))
            page = locator.get("page_number") or locator.get("slide_number")
            caption_languages = {
                str(item.get("language", {}).get("language_code"))
                for item in payload.get("captions", [])
                if isinstance(item.get("language"), dict) and item["language"].get("language_code")
            }
            language = next(iter(caption_languages)) if len(caption_languages) == 1 else "und"
            records.append(
                (
                    LanguageEvidenceKindV3.VISION_DERIVATION,
                    row,
                    str(row["derivation_id"]),
                    content,
                    str(row["occurrence_id"]),
                    str(row["derivation_id"]),
                    str(row["generation_id"]),
                    int(page) if page else None,
                    language,
                )
            )
        items: list[_Item] = []
        policy_digest = _hash("mnemo.isolated-multilingual-representation/2")
        for (
            kind,
            row,
            evidence_id,
            text,
            occurrence,
            derivation,
            generation,
            page,
            language,
        ) in records:
            source = LanguageEvidenceReferenceV3(
                notebook_id=notebook_id,
                source_id=source_by_document[str(row["document_id"])],
                document_id=UUID(str(row["document_id"])),
                version_id=UUID(str(row["version_id"])),
                kind=kind,
                evidence_id=evidence_id,
                source_content_hash=_hash(text),
                chunk_id=evidence_id if kind is LanguageEvidenceKindV3.CANONICAL_CHUNK else None,
                occurrence_id=UUID(occurrence) if occurrence else None,
                derivation_id=UUID(derivation) if derivation else None,
                source_generation_id=UUID(generation) if generation else None,
            )
            representation_type = {
                LanguageEvidenceKindV3.CANONICAL_CHUNK: (
                    TextRepresentationType.UNICODE_SEMANTIC_TEXT
                ),
                LanguageEvidenceKindV3.OCR_REGION: TextRepresentationType.OCR_TEXT,
                LanguageEvidenceKindV3.VISION_DERIVATION: TextRepresentationType.VISION_TEXT,
            }[kind]
            observation_id = representation_observation_id(
                source_reference_digest=source.identity_digest,
                detector_id="isolated-rebuild-source-kind",
                detector_revision="1",
                configuration_digest=policy_digest,
                input_content_hash=source.source_content_hash,
                representation_type=representation_type,
            )
            observation = RepresentationObservationV1(
                observation_id=observation_id,
                source_reference=source,
                representation_type=representation_type,
                detector_id="isolated-rebuild-source-kind",
                detector_revision="1",
                configuration_digest=policy_digest,
                input_content_hash=source.source_content_hash,
                confidence=1.0,
                calibrated=False,
                authority_class=RepresentationAuthorityClass.GOVERNED_DETECTOR,
                language_observation_references=(),
                script_observation_references=(),
                created_at=datetime.now(UTC),
            )
            authority = (
                RepresentationAuthority.ORIGINAL
                if kind is LanguageEvidenceKindV3.CANONICAL_CHUNK
                else RepresentationAuthority.EXISTING_DERIVED
            )
            generations = (UUID(generation),) if generation else ()
            representation = TextRepresentationReferenceV1(
                reference_id=text_representation_reference_id(
                    evidence_reference_digest=source.identity_digest,
                    representation_type=representation_type,
                    authority=authority,
                    content_hash=_hash(text),
                    observation_id=observation_id,
                    derivation_id=None,
                    source_generation_ids=generations,
                ),
                evidence_reference=source,
                representation_type=representation_type,
                representation_authority=authority,
                content_hash=_hash(text),
                representation_observation_id=observation_id,
                representation_derivation_id=None,
                source_generation_ids=generations,
                language_observation_references=(),
                script_observation_references=(),
            )
            try:
                admitted_language = LanguageCode(language)
            except ValueError:
                # Parser/OCR/Vision annotations are evidence, not admission authority.
                # Preserve their stored bytes and index the text with unknown language.
                admitted_language = LanguageCode("und")
                if language_fallbacks is not None:
                    language_fallbacks.append(
                        {
                            "kind": kind.value,
                            "evidence_id": evidence_id,
                            "version_id": str(row["version_id"]),
                            "supplied_tag_sha256": _hash(language),
                        }
                    )
            items.append(
                _Item(
                    source,
                    text,
                    admitted_language,
                    MultilingualEvidencePositionV1(page_number=page),
                    observation,
                    representation,
                )
            )
        return tuple(items)
    finally:
        connection.close()


class _ObservationBuilder:
    def __init__(self, store: SQLiteStore, items: tuple[_Item, ...]) -> None:
        self.store, self.items = store, items

    async def build(self, generation_id: UUID) -> ProjectionBuildResult:
        del generation_id
        for item in self.items:
            existing = await self.store.get_representation_observation_v1(
                item.observation.observation_id
            )
            if existing is None:
                await self.store.put_representation_observation_v1(item.observation)
            elif replace(item.observation, created_at=existing.created_at) != existing:
                raise ValueError("persisted representation observation has conflicting lineage")
        identities = sorted(str(item.observation.observation_id) for item in self.items)
        return ProjectionBuildResult(
            expected_count=len(identities),
            succeeded_count=len(identities),
            failed_count=0,
            skipped_count=0,
            checksum=_hash("\n".join(identities)),
        )


async def build_isolated_multilingual(
    *,
    database: Path,
    notebook_id: UUID,
    profile_file: Path,
    cache_folder: Path,
    device: str = "cpu",
    language_capability_file: Path | None = None,
) -> dict[str, object]:
    """Build complete READY-not-active BGE-M3 generations from actual new-notebook evidence."""
    language_fallbacks: list[dict[str, str]] = []
    items = _items(database, notebook_id, language_fallbacks)
    if not items:
        raise ValueError("no searchable evidence exists in the isolated notebook")
    component = (
        ModelProfileDocument.from_file(profile_file)
        .select("full_multilingual_v2_local_prebuild")
        .models["multilingual_embedding"]
    )
    from mnemo.phase85.rebuild_language_capability import load_rebuild_language_capability

    capability = (
        load_rebuild_language_capability(path=language_capability_file, component=component)
        if language_capability_file is not None
        else None
    )
    if device not in {"cpu", "cuda"}:
        raise ValueError("unsupported BGE-M3 rebuild device")
    capability_identity = capability.identity if capability is not None else "legacy-claims-only"
    policy = _hash(f"mnemo.isolated-multilingual-rebuild/3:{device}:{capability_identity}")
    profile_fingerprint = _hash(f"{component.model_dump_json()}:{device}:{capability_identity}")
    versions = tuple(sorted({item.source.version_id for item in items}, key=str))
    probe = BGEM3EmbeddingProvider(component, generation_id=UUID(int=0), cache_folder=cache_folder)
    probe_profile = await probe.profile()
    plan = full_multilingual_v2_generation_plan(
        profile_id=f"isolated-rebuild:{notebook_id}",
        profile_fingerprint=profile_fingerprint,
        source_version_ids=versions,
        representation_configuration_digest=policy,
        detector_configuration_digest=policy,
        authorization_policy_digest=policy,
        embedding_provider_identity=component.provider,
        embedding_model_identity=component.model,
        embedding_model_revision=component.revision,
        embedding_preprocessing_digest=probe_profile.preprocessing_digest,
        vector_space_identity=probe_profile.vector_space,
        dimensions=probe_profile.dimension,
    )
    provider = BGEM3EmbeddingProvider(
        component,
        generation_id=plan.multilingual_embedding.generation_id,
        cache_folder=cache_folder,
        device=device,
    )
    store = SQLiteStore(database)
    await store.open()
    try:
        coordinator = DerivedProjectionCoordinator(store)
        languages = tuple(sorted({item.language.value for item in items}))
        representation_types = tuple(
            sorted({item.representation.representation_type.value for item in items})
        )
        source_kinds = tuple(sorted({item.source.kind.value for item in items}))

        def covered(spec: object, builder: object) -> CoverageRecordingGenerationBuilderV2:
            from mnemo.phase85.full_multilingual_v2 import FullMultilingualV2Builder
            from mnemo.phase85.projections import ProjectionGenerationSpec

            if not isinstance(spec, ProjectionGenerationSpec) or not isinstance(
                builder, FullMultilingualV2Builder
            ):
                raise TypeError("invalid governed multilingual generation builder")
            return CoverageRecordingGenerationBuilderV2(
                builder=builder,
                store=store,
                generation_id=spec.generation_id,
                capability=spec.capability,
                profile_fingerprint=profile_fingerprint,
                dependency_digest=_hash("\n".join(str(v) for v in spec.source_generation_ids)),
                rollback_metadata_digest=_hash(str(notebook_id)),
                language_tags=languages,
                script_codes=(),
                representation_types=representation_types,
                source_kinds=source_kinds,
            )

        observed = await coordinator.build_and_activate(
            plan.representation_derivation,
            covered(plan.representation_derivation, _ObservationBuilder(store, items)),
            activate=False,
        )
        rows = tuple(
            MultilingualTextProjectionRowV2(
                row_id=multilingual_text_projection_row_v2_id(
                    source=item.source,
                    representation=item.representation,
                    language=item.language,
                    generation_id=plan.language_text.generation_id,
                ),
                source=item.source,
                representation=item.representation,
                language=item.language,
                text=item.text,
                text_hash=_hash(item.text),
                position=item.position,
                language_observation_references=(),
                script_observation_references=(),
                generation_id=plan.language_text.generation_id,
                source_generation_ids=item.representation.source_generation_ids,
                created_at=datetime.now(UTC),
            )
            for item in items
        )
        sparse = await coordinator.build_and_activate(
            plan.language_text,
            covered(
                plan.language_text,
                MultilingualTextGenerationBuilderV2(
                    store=store, generation_id=plan.language_text.generation_id, rows=rows
                ),
            ),
            activate=False,
        )
        await provider.initialize()
        if (await provider.profile()).vector_space != probe_profile.vector_space:
            raise RuntimeError("BGE-M3 query/document semantic-space mismatch")
        inputs = tuple(
            MultilingualEmbeddingInputV3(
                source=item.source,
                representation=item.representation,
                text=item.text,
                language=item.language,
                language_observation_references=(),
                script_observation_references=(),
            )
            for item in items
        )
        dense = await coordinator.build_and_activate(
            plan.multilingual_embedding,
            covered(
                plan.multilingual_embedding,
                MultilingualEmbeddingGenerationBuilderV3(
                    provider=provider,
                    store=store,
                    generation_id=plan.multilingual_embedding.generation_id,
                    inputs=inputs,
                ),
            ),
            activate=False,
        )
        # The storage read contract intentionally bounds one authorized vector
        # enumeration.  A full isolated rebuild can exceed that bound; partition
        # the already-verified source identities without dropping evidence.
        embedding_pages: list[MultilingualEmbeddingV3] = []
        for start in range(0, len(items), 10_000):
            embedding_pages.extend(
                await store.list_authorized_multilingual_embeddings_v3(
                    notebook_id=notebook_id,
                    generation_id=plan.multilingual_embedding.generation_id,
                    vector_space=probe_profile.vector_space,
                    authorized_sources=tuple(item.source for item in items[start : start + 10_000]),
                )
            )
        embeddings = tuple(embedding_pages)
        if len(embeddings) != len(items):
            raise RuntimeError(
                "READY embedding generation does not match current evidence identities"
            )
        vector = await coordinator.build_and_activate(
            plan.multilingual_vector,
            covered(
                plan.multilingual_vector,
                MultilingualVectorGenerationBuilderV2(
                    generation_id=plan.multilingual_vector.generation_id,
                    source_embedding_generation_id=plan.multilingual_embedding.generation_id,
                    vector_space_identity=probe_profile.vector_space,
                    embeddings=embeddings,
                ),
            ),
            activate=False,
        )
        return {
            "invalid_language_annotation_count": len(language_fallbacks),
            "invalid_language_annotation_examples": language_fallbacks[:100],
            "language_capability_identity": capability_identity,
            "language_capability_scope": capability.scope
            if capability is not None
            else "claimed_tags",
            "profile_fingerprint": profile_fingerprint,
            "items": len(items),
            "by_kind": {
                kind.value: sum(item.source.kind is kind for item in items)
                for kind in (
                    LanguageEvidenceKindV3.CANONICAL_CHUNK,
                    LanguageEvidenceKindV3.OCR_REGION,
                    LanguageEvidenceKindV3.VISION_DERIVATION,
                )
            },
            "vector_space": probe_profile.vector_space,
            "execution_device": device,
            "generations": {
                "representation_derivation_v2": str(observed.generation_id),
                "language_text_v2": str(sparse.generation_id),
                "multilingual_embedding_v2": str(dense.generation_id),
                "multilingual_vector_v2": str(vector.generation_id),
            },
            "embedding_count": len(embeddings),
            "active": False,
        }
    finally:
        await provider.close()
        await store.close()
