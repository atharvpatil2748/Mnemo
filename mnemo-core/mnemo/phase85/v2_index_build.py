"""Manifest-bound Full Multilingual V2 build operator.

The operator materializes the immutable, already-ingested governed source database into
one authorized disposable target and adds only V2 observations/projections.  It never
promotes aliases or changes runtime exposure.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from mnemo.interfaces.errors import ContractValidationError, IntegrityError
from mnemo.models import IndexGenerationState
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
from mnemo.models.multilingual_embeddings import MultilingualEmbeddingInputV3
from mnemo.models.multilingual_generation import MultilingualCoverageManifestV2
from mnemo.models.multilingual_index import (
    MultilingualEvidencePositionV1,
    MultilingualTextProjectionRowV2,
    multilingual_text_projection_row_v2_id,
)
from mnemo.models.text_representations import (
    ObservationKind,
    ObservationReferenceV1,
    RepresentationAuthority,
    RepresentationAuthorityClass,
    RepresentationObservationV1,
    TextRepresentationReferenceV1,
    TextRepresentationType,
    representation_observation_id,
    text_representation_reference_id,
)
from mnemo.phase85.profiles import ModelProfileDocument
from mnemo.phase85.projections import (
    ProjectionBuildResult,
    ProjectionCoverage,
    ProjectionGenerationSpec,
)
from mnemo.phase85.v2_build_authorization import (
    V2BuildAuthorizationV1,
    validate_v2_build_authorization,
)
from mnemo.retrieval.multilingual_providers import BGEM3EmbeddingProvider
from mnemo.storage.sqlite import SQLiteStore

_ACTOR_NAMESPACE = UUID("bdad8221-4686-5b9c-944c-49c067986a4f")
_EXCLUSION_NAMESPACE = UUID("cafda68b-b9aa-5de0-8906-b229576f236e")
_BUILD_TABLES = """
CREATE TABLE IF NOT EXISTS v2_build_runs (
    run_id TEXT PRIMARY KEY,
    authorization_id TEXT NOT NULL,
    target_database_path TEXT NOT NULL,
    corpus_digest TEXT NOT NULL,
    census_digest TEXT NOT NULL,
    profile_fingerprint TEXT NOT NULL,
    vector_space_identity TEXT NOT NULL,
    build_manifest_digest TEXT NOT NULL,
    storage_manifest_digest TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    state TEXT NOT NULL CHECK(state IN ('building','ready','failed'))
);
CREATE TABLE IF NOT EXISTS v2_build_checkpoints (
    run_id TEXT NOT NULL REFERENCES v2_build_runs(run_id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    completed_count INTEGER NOT NULL CHECK(completed_count >= 0),
    checkpoint_digest TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(run_id,stage)
);
CREATE TABLE IF NOT EXISTS v2_build_exclusions (
    exclusion_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES v2_build_runs(run_id) ON DELETE CASCADE,
    evidence_reference_digest TEXT NOT NULL,
    evidence_kind TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    representation_type TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    transformation_requirement TEXT NOT NULL,
    source_content_hash TEXT NOT NULL,
    generation_id TEXT NOT NULL,
    payload_digest TEXT NOT NULL,
    UNIQUE(run_id,evidence_reference_digest,generation_id)
);
"""


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _artifact(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ContractValidationError(f"{path.name} must contain an object")
    claimed = value.get("artifact_digest")
    unsigned = {key: item for key, item in value.items() if key != "artifact_digest"}
    if claimed != _digest(unsigned):
        raise ContractValidationError(f"{path.name} artifact digest mismatch")
    return value


@dataclass(frozen=True, slots=True)
class V2BuildArtifacts:
    authorization: V2BuildAuthorizationV1
    authorization_raw: Mapping[str, object]
    storage: Mapping[str, object]
    build: Mapping[str, object]
    binding: Mapping[str, object]
    census: Mapping[str, object]
    corpus_census: Mapping[str, object]
    language_policy: Mapping[str, object]
    script_policy: Mapping[str, object]
    representation_policy: Mapping[str, object]
    coverage_policy: Mapping[str, object]

    @classmethod
    def load(cls, proposal_root: Path) -> V2BuildArtifacts:
        authorization_raw = _artifact(proposal_root / "V2_INDEX_BUILD_AUTHORIZATION.json")
        return cls(
            authorization=V2BuildAuthorizationV1.from_mapping(authorization_raw),
            authorization_raw=authorization_raw,
            storage=_artifact(proposal_root / "V2_DISPOSABLE_DATABASE_MANIFEST.json"),
            build=_artifact(proposal_root / "V2_BUILD_RECOVERY_ROLLBACK_MANIFEST.json"),
            binding=_artifact(proposal_root / "V2_MODEL_PROFILE_BINDING.json"),
            census=_artifact(
                proposal_root / "V2_CORPUS_LANGUAGE_SCRIPT_REPRESENTATION_CENSUS.json"
            ),
            corpus_census=_artifact(proposal_root / "V2_CORPUS_REPRESENTATION_CENSUS.json"),
            language_policy=_artifact(proposal_root / "V2_LANGUAGE_OBSERVATION_POLICY.json"),
            script_policy=_artifact(proposal_root / "V2_SCRIPT_DETECTOR_POLICY.json"),
            representation_policy=_artifact(
                proposal_root / "V2_REPRESENTATION_DETECTOR_POLICY.json"
            ),
            coverage_policy=_artifact(
                proposal_root / "V2_GOVERNED_COVERAGE_LIMITATION_POLICY.json"
            ),
        )


@dataclass(frozen=True, slots=True)
class V2BuildPreflight:
    target: Path
    source_database: Path
    corpus_root: Path
    generation_specs: tuple[ProjectionGenerationSpec, ...]


@dataclass(frozen=True, slots=True)
class _Evidence:
    source: LanguageEvidenceReferenceV3
    text: str
    language: LanguageCode
    language_observation: LanguageObservationV2
    script_observation: ScriptObservationV1
    representation_observation: RepresentationObservationV1
    representation: TextRepresentationReferenceV1
    position: MultilingualEvidencePositionV1
    excluded: bool
    transformation_requirement: str


class FullMultilingualV2IndexBuildOperator:
    """One bounded build-to-READY operator with no activation/exposure surface."""

    def __init__(self, *, workspace_root: Path, proposal_root: Path) -> None:
        self._root = workspace_root.resolve()
        self._proposal_root = proposal_root.resolve()
        self._artifacts = V2BuildArtifacts.load(self._proposal_root)

    def preflight(self) -> V2BuildPreflight:
        protected = (
            self._root / "scratch/phase8_5_wp16/eval-20260828-01/mnemo.db",
            self._root / "scratch/phase8_5_wp10_stage2/eval-20260829-01/mnemo.db",
            self._root / "scratch/phase8_5_11/eval-20260825-02/mnemo.db",
        )
        target = validate_v2_build_authorization(
            self._artifacts.authorization,
            storage_manifest=self._artifacts.storage,
            build_manifest=self._artifacts.build,
            workspace_root=self._root,
            protected_database_paths=protected,
        )
        if target.exists():
            self._validate_existing_target(target)
        elif Path(f"{target}-wal").exists() or Path(f"{target}-shm").exists():
            raise ContractValidationError("V2 sidecar exists without its authorized database")
        source_database = protected[0].resolve()
        corpus_root = (self._root / "goldenDataset/Phase 8.5 Evaluation Corpus").resolve()
        if _file_digest(source_database) != self._artifacts.build["source_database_sha256"]:
            raise IntegrityError("governed source database digest mismatch")
        self._validate_corpus(corpus_root)
        self._validate_bindings()
        specifications = _mapping_sequence(
            self._artifacts.build.get("generation_specifications"),
            "generation_specifications",
        )
        specs = tuple(
            ProjectionGenerationSpec.from_manifest_payload(item) for item in specifications
        )
        expected = (
            "representation_derivation_v2",
            "language_text_v2",
            "multilingual_embedding_v2",
            "multilingual_vector_v2",
        )
        if tuple(item.capability for item in specs) != expected:
            raise ContractValidationError("V2 build generation order is not canonical")
        return V2BuildPreflight(
            target=target,
            source_database=source_database,
            corpus_root=corpus_root,
            generation_specs=specs,
        )

    async def execute(self) -> dict[str, object]:
        # This call is deliberately the first source-enumerating boundary.
        preflight = self.preflight()
        if not preflight.target.exists():
            preflight.target.parent.mkdir(parents=True, exist_ok=True)
            self._clone_source(preflight.source_database, preflight.target)
        self._initialize_build_audit(preflight.target)
        store = SQLiteStore(preflight.target)
        provider: BGEM3EmbeddingProvider | None = None
        await store.open()
        try:
            evidence = self._load_evidence(preflight.target)
            expected_counts = self._artifacts.build["expected_coverage"]
            if len(evidence) != int(expected_counts["evidence_items"]):  # type: ignore[index]
                raise IntegrityError("V2 evidence count differs from governed census")
            provider = self._embedding_provider(preflight.generation_specs[2])
            await provider.initialize()
            profile = await provider.profile()
            if profile.vector_space != self._artifacts.build["vector_space_profile_identity"]:
                raise IntegrityError("initialized provider vector space differs from manifest")
            await self._build_representation(store, preflight.generation_specs[0], evidence)
            eligible = tuple(item for item in evidence if not item.excluded)
            await self._build_sparse(store, preflight.generation_specs[1], eligible)
            await self._build_embeddings(
                store, preflight.target, preflight.generation_specs[2], eligible, provider
            )
            await self._build_vector(store, preflight.target, preflight.generation_specs[3])
            result = self._audit(preflight.target, preflight.generation_specs)
            self._finish_run(preflight.target, "ready")
            return result
        except BaseException:
            self._finish_run(preflight.target, "failed")
            raise
        finally:
            if provider is not None:
                await provider.close()
            await store.close()

    def _validate_corpus(self, corpus_root: Path) -> None:
        files = _mapping_sequence(self._artifacts.corpus_census.get("corpus_files"), "corpus_files")
        actual = []
        for item in files:
            path = corpus_root / str(item["name"])
            if not path.is_file():
                raise IntegrityError(f"governed corpus file is absent: {item['name']}")
            actual.append(
                {"name": item["name"], "sha256": _file_digest(path), "size": path.stat().st_size}
            )
        if tuple(actual) != files:
            raise IntegrityError("Golden Dataset differs from the governed corpus manifest")
        if _digest(actual) != self._artifacts.authorization.corpus_digest:
            raise IntegrityError("Golden Dataset composite identity mismatch")

    def _validate_bindings(self) -> None:
        a = self._artifacts.authorization
        b = self._artifacts.binding
        build = self._artifacts.build
        if b["profile_fingerprint"] != a.profile_fingerprint:
            raise ContractValidationError("profile fingerprint binding mismatch")
        vector_spaces = {
            a.vector_space_identity,
            str(b["embedding"]["vector_space_profile_identity"]),  # type: ignore[index]
            str(build["vector_space_profile_identity"]),
            str(self._artifacts.storage["vector_space_profile_identity"]),
        }
        if len(vector_spaces) != 1:
            raise ContractValidationError("V2 vector-space bindings disagree")
        if self._artifacts.census["artifact_digest"] != a.census_digest:
            raise ContractValidationError("census authorization binding mismatch")
        if (
            self._artifacts.coverage_policy["excluded_from_transformation_dependent_generations"]
            != 504
        ):
            raise ContractValidationError("governed exclusion population changed")

    @staticmethod
    def _clone_source(source: Path, target: Path) -> None:
        source_connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
        target_connection = sqlite3.connect(target)
        try:
            source_connection.backup(target_connection)
            target_connection.execute("PRAGMA foreign_keys=ON")
            if target_connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise IntegrityError("isolated SQLite backup failed integrity_check")
        finally:
            target_connection.close()
            source_connection.close()

    def _validate_existing_target(self, target: Path) -> None:
        """Admit only a checkpoint owned by the same typed authorization."""
        connection = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)
        try:
            if (
                connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='v2_build_runs'"
                ).fetchone()
                is None
            ):
                raise ContractValidationError("existing V2 target has no governed build identity")
            row = connection.execute(
                """SELECT authorization_id,target_database_path,corpus_digest,census_digest,
                          profile_fingerprint,vector_space_identity,build_manifest_digest,
                          storage_manifest_digest
                   FROM v2_build_runs WHERE run_id=?""",
                (str(self._artifacts.authorization.run_id),),
            ).fetchone()
            expected = (
                str(self._artifacts.authorization.authorization_id),
                self._artifacts.authorization.target_database_path,
                self._artifacts.authorization.corpus_digest,
                self._artifacts.authorization.census_digest,
                self._artifacts.authorization.profile_fingerprint,
                self._artifacts.authorization.vector_space_identity,
                self._artifacts.authorization.build_manifest_digest,
                self._artifacts.authorization.storage_manifest_digest,
            )
            if row is None or tuple(row) != expected:
                raise ContractValidationError("existing V2 checkpoint authorization mismatch")
        finally:
            connection.close()

    def _initialize_build_audit(self, target: Path) -> None:
        authorization = self._artifacts.authorization
        connection = sqlite3.connect(target)
        try:
            connection.executescript(_BUILD_TABLES)
            existing = connection.execute(
                "SELECT started_at,state FROM v2_build_runs WHERE run_id=?",
                (str(authorization.run_id),),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """INSERT INTO v2_build_runs(
                       run_id,authorization_id,target_database_path,corpus_digest,census_digest,
                       profile_fingerprint,vector_space_identity,build_manifest_digest,
                       storage_manifest_digest,started_at,state)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        str(authorization.run_id),
                        str(authorization.authorization_id),
                        authorization.target_database_path,
                        authorization.corpus_digest,
                        authorization.census_digest,
                        authorization.profile_fingerprint,
                        authorization.vector_space_identity,
                        authorization.build_manifest_digest,
                        authorization.storage_manifest_digest,
                        datetime.now(UTC).isoformat(),
                        "building",
                    ),
                )
            else:
                connection.execute(
                    """UPDATE v2_build_runs SET state='building',completed_at=NULL
                       WHERE run_id=?""",
                    (str(authorization.run_id),),
                )
            connection.commit()
        finally:
            connection.close()

    def _load_evidence(self, target: Path) -> tuple[_Evidence, ...]:
        connection = sqlite3.connect(target)
        connection.row_factory = sqlite3.Row
        records = _mapping_sequence(self._artifacts.census.get("records"), "records")
        source_by_document = {
            str(row[0]): (UUID(str(row[1])), UUID(str(row[2])))
            for row in connection.execute("SELECT document_id,source_id,notebook_id FROM sources")
        }
        chunk_rows = {
            str(row["id"]): row
            for row in connection.execute(
                "SELECT c.*,v.created_at FROM chunks c JOIN document_versions v USING(version_id)"
            )
        }
        ocr_rows = {
            str(row["region_id"]): row
            for row in connection.execute(
                """SELECT r.*,o.document_id,o.version_id,o.occurrence_id,o.generation_id,
                          o.created_at FROM ocr_regions r JOIN ocr_results o USING(derivation_id)"""
            )
        }
        vision_rows = {
            str(row["derivation_id"]): row
            for row in connection.execute("SELECT * FROM vision_results")
        }
        occurrence_pages = {}
        for row in connection.execute("SELECT occurrence_id,locator FROM asset_occurrences"):
            locator = json.loads(str(row[1]))
            occurrence_pages[str(row[0])] = locator.get("page_number") or locator.get(
                "slide_number"
            )
        actor = uuid5(_ACTOR_NAMESPACE, str(self._artifacts.authorization.run_id))
        values: list[_Evidence] = []
        for raw in records:
            document_id = str(raw["document_id"])
            source_id, notebook_id = source_by_document[document_id]
            kind = LanguageEvidenceKindV3(str(raw["evidence_kind"]))
            if kind is LanguageEvidenceKindV3.CANONICAL_CHUNK:
                evidence_row = chunk_rows[str(raw["evidence_id"])]
                text = str(evidence_row["text"])
                created_at = datetime.fromisoformat(str(evidence_row["created_at"]))
                position = MultilingualEvidencePositionV1(
                    page_number=evidence_row["position_page_number"],
                    section_index=int(evidence_row["position_section_index"]),
                    heading_path=tuple(json.loads(str(evidence_row["heading_path"]))),
                )
            elif kind is LanguageEvidenceKindV3.OCR_REGION:
                evidence_row = ocr_rows[str(raw["evidence_id"])]
                text = str(evidence_row["text"])
                created_at = datetime.fromisoformat(str(evidence_row["created_at"]))
                position = MultilingualEvidencePositionV1(
                    page_number=int(evidence_row["page_number"])
                )
            else:
                evidence_row = vision_rows[str(raw["evidence_id"])]
                text = _vision_text(str(evidence_row["payload"]))
                created_at = datetime.fromisoformat(str(evidence_row["created_at"]))
                position = MultilingualEvidencePositionV1(
                    page_number=occurrence_pages.get(str(raw["occurrence_id"]))
                )
            if not text.strip():
                raise IntegrityError(
                    f"governed evidence has blank semantic text: {raw['evidence_id']}"
                )
            source = LanguageEvidenceReferenceV3(
                notebook_id=notebook_id,
                source_id=source_id,
                document_id=UUID(document_id),
                version_id=UUID(str(raw["version_id"])),
                kind=kind,
                evidence_id=str(raw["evidence_id"]),
                source_content_hash=str(raw["source_content_hash"]),
                chunk_id=(
                    str(raw["evidence_id"])
                    if kind is LanguageEvidenceKindV3.CANONICAL_CHUNK
                    else None
                ),
                occurrence_id=(
                    None if raw["occurrence_id"] is None else UUID(str(raw["occurrence_id"]))
                ),
                derivation_id=(
                    None if raw["derivation_id"] is None else UUID(str(raw["derivation_id"]))
                ),
                source_generation_id=(
                    None
                    if raw["source_generation_id"] is None
                    else UUID(str(raw["source_generation_id"]))
                ),
            )
            language = LanguageCode(str(raw["language"]["language"]))
            language_observation = self._language_observation(
                actor, source, raw, language, created_at
            )
            script_observation = self._script_observation(actor, source, raw, created_at)
            language_ref = ObservationReferenceV1(
                observation_id=language_observation.observation_id,
                observation_kind=ObservationKind.LANGUAGE,
                observation_digest=_observation_reference_digest(language_observation),
            )
            script_ref = ObservationReferenceV1(
                observation_id=script_observation.observation_id,
                observation_kind=ObservationKind.SCRIPT,
                observation_digest=_observation_reference_digest(script_observation),
            )
            representation_type = TextRepresentationType(str(raw["representation"]))
            representation_observation = RepresentationObservationV1(
                observation_id=representation_observation_id(
                    source_reference_digest=source.identity_digest,
                    detector_id=str(self._artifacts.representation_policy["detector_id"]),
                    detector_revision=str(self._artifacts.representation_policy["version"]),
                    configuration_digest=str(
                        self._artifacts.representation_policy["artifact_digest"]
                    ),
                    input_content_hash=source.source_content_hash,
                    representation_type=representation_type,
                ),
                source_reference=source,
                representation_type=representation_type,
                detector_id=str(self._artifacts.representation_policy["detector_id"]),
                detector_revision=str(self._artifacts.representation_policy["version"]),
                configuration_digest=str(self._artifacts.representation_policy["artifact_digest"]),
                input_content_hash=source.source_content_hash,
                confidence=1.0,
                calibrated=False,
                authority_class=RepresentationAuthorityClass.GOVERNED_DETECTOR,
                language_observation_references=(language_ref,),
                script_observation_references=(script_ref,),
                created_at=created_at,
            )
            text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            authority = (
                RepresentationAuthority.ORIGINAL
                if kind is LanguageEvidenceKindV3.CANONICAL_CHUNK
                else RepresentationAuthority.EXISTING_DERIVED
            )
            source_generations = (
                () if source.source_generation_id is None else (source.source_generation_id,)
            )
            representation = TextRepresentationReferenceV1(
                reference_id=text_representation_reference_id(
                    evidence_reference_digest=source.identity_digest,
                    representation_type=representation_type,
                    authority=authority,
                    content_hash=text_hash,
                    observation_id=representation_observation.observation_id,
                    derivation_id=None,
                    source_generation_ids=source_generations,
                ),
                evidence_reference=source,
                representation_type=representation_type,
                representation_authority=authority,
                content_hash=text_hash,
                representation_observation_id=representation_observation.observation_id,
                representation_derivation_id=None,
                source_generation_ids=source_generations,
                language_observation_references=(language_ref,),
                script_observation_references=(script_ref,),
            )
            values.append(
                _Evidence(
                    source=source,
                    text=text,
                    language=language,
                    language_observation=language_observation,
                    script_observation=script_observation,
                    representation_observation=representation_observation,
                    representation=representation,
                    position=position,
                    excluded=str(raw["transformation_requirement"])
                    == "required_unavailable_excluded",
                    transformation_requirement=str(raw["transformation_requirement"]),
                )
            )
        connection.close()
        return tuple(values)

    def _language_observation(
        self,
        actor: UUID,
        source: LanguageEvidenceReferenceV3,
        raw: Mapping[str, Any],
        language: LanguageCode,
        created_at: datetime,
    ) -> LanguageObservationV2:
        policy = self._artifacts.language_policy
        authority = (
            ObservationAuthorityClass.ADJUDICATED
            if str(raw["language"]["authority"]).startswith("adjudicated")
            else ObservationAuthorityClass.UNKNOWN
        )
        hypothesis = LanguageHypothesisV2(
            language=language,
            confidence=LanguageConfidence(
                value=float(raw["language"]["confidence"]),
                calibrated=bool(raw["language"]["calibrated"]),
            ),
            authority_class=authority,
            evidence_digest=_digest(raw["language"]),
        )
        target_scope = _scope(source.kind)
        detector = str(policy["policy_id"])
        revision = str(policy["version"])
        configuration = str(policy["artifact_digest"])
        identity = language_observation_v2_id(
            notebook_id=source.notebook_id,
            target_scope=target_scope,
            target_id=source.evidence_id,
            detector=detector,
            detector_revision=revision,
            configuration_digest=configuration,
            input_hash=source.source_content_hash,
            source_reference_digest=source.identity_digest,
        )
        return LanguageObservationV2(
            observation_id=identity,
            actor_id=actor,
            notebook_id=source.notebook_id,
            target_scope=target_scope,
            target_id=source.evidence_id,
            hypotheses=(hypothesis,),
            detector=detector,
            detector_revision=revision,
            configuration_digest=configuration,
            input_hash=source.source_content_hash,
            mixed_language=False,
            source_reference=source,
            created_at=created_at,
        )

    def _script_observation(
        self,
        actor: UUID,
        source: LanguageEvidenceReferenceV3,
        raw: Mapping[str, Any],
        created_at: datetime,
    ) -> ScriptObservationV1:
        policy = self._artifacts.script_policy
        hypotheses = tuple(
            ScriptHypothesisV1(
                script=ScriptCode(str(item["script"])),
                confidence=LanguageConfidence(value=float(item["confidence"]), calibrated=False),
                authority_class=ObservationAuthorityClass.GOVERNED_DETECTOR,
                evidence_digest=_digest(item),
            )
            for item in raw["script"]["hypotheses"]
        )
        target_scope = _scope(source.kind)
        detector = str(policy["detector_id"])
        revision = str(policy["version"])
        configuration = str(policy["artifact_digest"])
        identity = script_observation_v1_id(
            notebook_id=source.notebook_id,
            target_scope=target_scope,
            target_id=source.evidence_id,
            detector=detector,
            detector_revision=revision,
            configuration_digest=configuration,
            input_hash=source.source_content_hash,
            source_reference_digest=source.identity_digest,
        )
        return ScriptObservationV1(
            observation_id=identity,
            actor_id=actor,
            notebook_id=source.notebook_id,
            target_scope=target_scope,
            target_id=source.evidence_id,
            hypotheses=hypotheses,
            detector=detector,
            detector_revision=revision,
            configuration_digest=configuration,
            input_hash=source.source_content_hash,
            mixed_script=bool(raw["script"]["mixed"]),
            source_reference=source,
            created_at=created_at,
        )

    def _embedding_provider(self, spec: ProjectionGenerationSpec) -> BGEM3EmbeddingProvider:
        profile_file = self._root / str(self._artifacts.binding["profile_file"])
        document = ModelProfileDocument.from_file(profile_file)
        component = document.select(str(self._artifacts.binding["profile_id"])).models[
            "multilingual_embedding"
        ]
        return BGEM3EmbeddingProvider(
            component,
            generation_id=spec.generation_id,
            cache_folder=Path(r"D:\Mnemo\phase8.5.11-models\huggingface\hub"),
        )

    async def _begin_generation(self, store: SQLiteStore, spec: ProjectionGenerationSpec) -> bool:
        existing = await store.get_index_generation(spec.generation_id)
        if existing is not None:
            if not spec.compatible_with(existing):
                raise IntegrityError(f"stale {spec.capability} generation is incompatible")
            if existing.state is IndexGenerationState.READY:
                return False
            if existing.state is not IndexGenerationState.BUILDING:
                raise IntegrityError(f"{spec.capability} generation cannot be resumed")
            return True
        if not await store.create_index_generation(spec.new_generation(datetime.now(UTC))):
            raise IntegrityError(f"could not create {spec.capability} generation")
        await store.put_index_generation_sources(
            generation_id=spec.generation_id,
            source_generation_ids=spec.source_generation_ids,
            source_version_ids=spec.source_version_ids,
        )
        return True

    async def _complete_generation(
        self,
        store: SQLiteStore,
        spec: ProjectionGenerationSpec,
        result: ProjectionBuildResult,
        evidence: Sequence[_Evidence],
    ) -> None:
        coverage = ProjectionCoverage.from_result(
            spec.generation_id, result, updated_at=datetime.now(UTC)
        )
        if coverage.completeness.value != "complete":
            raise IntegrityError(f"{spec.capability} generation coverage is partial")
        await store.put_index_generation_coverage(coverage)
        dependency_digest = _digest(sorted(str(item) for item in spec.source_generation_ids))
        rollback_digest = _digest(
            {
                "namespace": self._artifacts.storage["rollback_namespace"],
                "run_id": str(self._artifacts.authorization.run_id),
            }
        )
        manifest = MultilingualCoverageManifestV2(
            generation_id=spec.generation_id,
            capability=spec.capability,
            profile_fingerprint=self._artifacts.authorization.profile_fingerprint,
            dependency_digest=dependency_digest,
            expected_count=result.expected_count,
            succeeded_count=result.succeeded_count,
            failed_count=result.failed_count,
            skipped_count=result.skipped_count,
            language_tags=tuple(sorted({item.language.value for item in evidence})),
            script_codes=tuple(
                sorted(
                    {
                        hypothesis.script.value
                        for item in evidence
                        for hypothesis in item.script_observation.hypotheses
                    }
                )
            ),
            representation_types=tuple(
                sorted({item.representation.representation_type.value for item in evidence})
            ),
            source_kinds=tuple(sorted({item.source.kind.value for item in evidence})),
            provenance_complete=True,
            authorization_compatible=True,
            rollback_metadata_digest=rollback_digest,
            item_identity_digest=result.checksum,
            created_at=self._run_started_at(),
        )
        await store.put_multilingual_coverage_manifest_v2(manifest)
        if not await store.transition_index_generation(
            spec.generation_id,
            IndexGenerationState.BUILDING,
            IndexGenerationState.READY,
            item_count=result.succeeded_count,
            checksum=result.checksum,
        ):
            current = await store.get_index_generation(spec.generation_id)
            if current is None or current.state is not IndexGenerationState.READY:
                raise IntegrityError(f"{spec.capability} READY transition failed")

    async def _build_representation(
        self, store: SQLiteStore, spec: ProjectionGenerationSpec, evidence: tuple[_Evidence, ...]
    ) -> None:
        if not await self._begin_generation(store, spec):
            return
        identities = []
        for index, item in enumerate(evidence, 1):
            await store.put_language_observation_v2(item.language_observation)
            await store.put_script_observation_v1(item.script_observation)
            await store.put_representation_observation_v1(item.representation_observation)
            identities.append(f"observation:{item.representation_observation.observation_id}")
            if item.excluded:
                self._put_exclusion(spec, item)
            if index % 100 == 0:
                self._checkpoint("representation_derivation_v2", index, identities)
        result = _complete_result(identities)
        await self._complete_generation(store, spec, result, evidence)
        self._checkpoint(spec.capability, len(evidence), identities)

    async def _build_sparse(
        self, store: SQLiteStore, spec: ProjectionGenerationSpec, evidence: tuple[_Evidence, ...]
    ) -> None:
        if not await self._begin_generation(store, spec):
            return
        identities = []
        for index, item in enumerate(evidence, 1):
            row = MultilingualTextProjectionRowV2(
                row_id=multilingual_text_projection_row_v2_id(
                    source=item.source,
                    representation=item.representation,
                    language=item.language,
                    generation_id=spec.generation_id,
                ),
                source=item.source,
                representation=item.representation,
                language=item.language,
                text=item.text,
                text_hash=item.representation.content_hash,
                position=item.position,
                language_observation_references=item.representation.language_observation_references,
                script_observation_references=item.representation.script_observation_references,
                generation_id=spec.generation_id,
                source_generation_ids=spec.source_generation_ids,
                created_at=self._run_started_at(),
            )
            await store.put_multilingual_text_projection_row_v2(row)
            identities.append(str(row.row_id))
            if index % 100 == 0:
                self._checkpoint(spec.capability, index, identities)
        result = _complete_result(identities)
        await self._complete_generation(store, spec, result, evidence)
        self._checkpoint(spec.capability, len(evidence), identities)

    async def _build_embeddings(
        self,
        store: SQLiteStore,
        target: Path,
        spec: ProjectionGenerationSpec,
        evidence: tuple[_Evidence, ...],
        provider: BGEM3EmbeddingProvider,
    ) -> None:
        if not await self._begin_generation(store, spec):
            return
        existing = self._existing_embedding_source_digests(target, spec.generation_id)
        for start in range(0, len(evidence), 32):
            batch_evidence = tuple(
                item
                for item in evidence[start : start + 32]
                if item.source.identity_digest not in existing
            )
            if batch_evidence:
                batch = tuple(
                    MultilingualEmbeddingInputV3(
                        source=item.source,
                        representation=item.representation,
                        text=item.text,
                        language=item.language,
                        language_observation_references=(
                            item.representation.language_observation_references
                        ),
                        script_observation_references=(
                            item.representation.script_observation_references
                        ),
                    )
                    for item in batch_evidence
                )
                embedded = await provider.embed_documents_v3(batch)
                for value in embedded:
                    if value.profile.vector_space != (
                        self._artifacts.authorization.vector_space_identity
                    ):
                        raise IntegrityError("provider emitted an unauthorized vector space")
                    await store.put_multilingual_embedding_v3(value)
            completed = min(start + 32, len(evidence))
            if completed % 128 == 0 or completed == len(evidence):
                ids = self._embedding_ids(target, spec.generation_id)
                self._checkpoint(spec.capability, len(ids), ids)
        identities = self._embedding_ids(target, spec.generation_id)
        if len(identities) != len(evidence):
            raise IntegrityError("embedding generation did not cover the eligible population")
        result = _complete_result(identities)
        await self._complete_generation(store, spec, result, evidence)

    async def _build_vector(
        self, store: SQLiteStore, target: Path, spec: ProjectionGenerationSpec
    ) -> None:
        if not await self._begin_generation(store, spec):
            return
        source_generation = spec.source_generation_ids[0]
        connection = sqlite3.connect(target)
        rows = connection.execute(
            """SELECT embedding_id,vector_space,payload FROM multilingual_embeddings_v2
               WHERE generation_id=? ORDER BY embedding_id""",
            (str(source_generation),),
        ).fetchall()
        connection.close()
        identities = []
        for embedding_id, vector_space, payload in rows:
            if vector_space != self._artifacts.authorization.vector_space_identity:
                raise IntegrityError("vector projection encountered another vector space")
            decoded = json.loads(str(payload))
            vector = _encoded_dataclass_vector(decoded)
            if len(vector) != 1024 or any(not math.isfinite(value) for value in vector):
                raise IntegrityError("stored embedding vector is invalid")
            norm = math.sqrt(sum(value * value for value in vector))
            if not math.isclose(norm, 1.0, rel_tol=1e-5, abs_tol=1e-5):
                raise IntegrityError("stored embedding vector is not L2 normalized")
            identities.append(str(embedding_id))
        result = _complete_result(identities)
        eligible = self._eligible_evidence_stub(target, source_generation)
        await self._complete_generation(store, spec, result, eligible)
        self._checkpoint(spec.capability, len(identities), identities)

    def _eligible_evidence_stub(self, target: Path, generation_id: UUID) -> tuple[_Evidence, ...]:
        # Coverage vocabulary for vector generation is copied from the embedding rows.
        all_evidence = self._load_evidence(target)
        existing = self._existing_embedding_source_digests(target, generation_id)
        return tuple(item for item in all_evidence if item.source.identity_digest in existing)

    def _put_exclusion(self, spec: ProjectionGenerationSpec, item: _Evidence) -> None:
        payload = {
            "run_id": str(self._artifacts.authorization.run_id),
            "evidence_reference_digest": item.source.identity_digest,
            "evidence_kind": item.source.kind.value,
            "evidence_id": item.source.evidence_id,
            "representation_type": item.representation.representation_type.value,
            "reason_code": "representation_transform_unavailable_governed_exclusion",
            "transformation_requirement": item.transformation_requirement,
            "source_content_hash": item.source.source_content_hash,
            "generation_id": str(spec.generation_id),
        }
        exclusion_id = uuid5(_EXCLUSION_NAMESPACE, _digest(payload))
        target = self._authorized_target()
        connection = sqlite3.connect(target)
        try:
            connection.execute(
                """INSERT OR IGNORE INTO v2_build_exclusions(
                   exclusion_id,run_id,evidence_reference_digest,evidence_kind,evidence_id,
                   representation_type,reason_code,transformation_requirement,
                   source_content_hash,generation_id,payload_digest)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    str(exclusion_id),
                    *payload.values(),
                    _digest(payload),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def _checkpoint(self, stage: str, count: int, identities: Sequence[str]) -> None:
        target = self._authorized_target()
        checksum = hashlib.sha256("\n".join(sorted(identities)).encode()).hexdigest()
        connection = sqlite3.connect(target)
        try:
            connection.execute(
                """INSERT INTO v2_build_checkpoints(run_id,stage,completed_count,
                   checkpoint_digest,updated_at) VALUES(?,?,?,?,?)
                   ON CONFLICT(run_id,stage) DO UPDATE SET completed_count=excluded.completed_count,
                   checkpoint_digest=excluded.checkpoint_digest,updated_at=excluded.updated_at""",
                (
                    str(self._artifacts.authorization.run_id),
                    stage,
                    count,
                    checksum,
                    datetime.now(UTC).isoformat(),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def _run_started_at(self) -> datetime:
        connection = sqlite3.connect(self._authorized_target())
        row = connection.execute(
            "SELECT started_at FROM v2_build_runs WHERE run_id=?",
            (str(self._artifacts.authorization.run_id),),
        ).fetchone()
        connection.close()
        if row is None:
            raise IntegrityError("V2 build run identity is absent")
        return datetime.fromisoformat(str(row[0]))

    def _authorized_target(self) -> Path:
        return (self._root / self._artifacts.authorization.target_database_path).resolve()

    @staticmethod
    def _existing_embedding_source_digests(target: Path, generation_id: UUID) -> set[str]:
        connection = sqlite3.connect(target)
        rows = connection.execute(
            """SELECT evidence_reference_digest FROM multilingual_embeddings_v2
               WHERE generation_id=?""",
            (str(generation_id),),
        ).fetchall()
        connection.close()
        return {str(row[0]) for row in rows}

    @staticmethod
    def _embedding_ids(target: Path, generation_id: UUID) -> list[str]:
        connection = sqlite3.connect(target)
        rows = connection.execute(
            """SELECT embedding_id FROM multilingual_embeddings_v2
               WHERE generation_id=? ORDER BY embedding_id""",
            (str(generation_id),),
        ).fetchall()
        connection.close()
        return [str(row[0]) for row in rows]

    def _finish_run(self, target: Path, state: str) -> None:
        if not target.exists():
            return
        connection = sqlite3.connect(target)
        try:
            if (
                connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='v2_build_runs'"
                ).fetchone()
                is not None
            ):
                connection.execute(
                    "UPDATE v2_build_runs SET state=?,completed_at=? WHERE run_id=?",
                    (
                        state,
                        datetime.now(UTC).isoformat(),
                        str(self._artifacts.authorization.run_id),
                    ),
                )
                connection.commit()
        finally:
            connection.close()

    def _audit(
        self, target: Path, specs: tuple[ProjectionGenerationSpec, ...]
    ) -> dict[str, object]:
        connection = sqlite3.connect(target)
        connection.row_factory = sqlite3.Row
        counts = {
            name: int(connection.execute(f"SELECT count(*) FROM {name}").fetchone()[0])
            for name in (
                "documents",
                "document_versions",
                "chunks",
                "ocr_regions",
                "vision_results",
                "language_observations_v2",
                "script_observations_v1",
                "representation_observations_v1",
                "v2_build_exclusions",
                "language_text_projection_rows_v2",
                "multilingual_embeddings_v2",
                "multilingual_coverage_manifests_v2",
                "multilingual_v2_alias_sets",
                "active_multilingual_v2_alias_set",
            )
        }
        generations = [
            dict(row)
            for row in connection.execute(
                """SELECT g.generation_id,g.capability,g.state,g.item_count,g.checksum,
                          c.expected_count,c.succeeded_count,c.failed_count,c.skipped_count,
                          c.completeness
                   FROM index_generations g JOIN index_generation_coverage c USING(generation_id)
                   WHERE g.generation_id IN (?,?,?,?) ORDER BY g.capability""",
                tuple(str(item.generation_id) for item in specs),
            )
        ]
        foreign_key_errors = [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")]
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        active_v2 = int(
            connection.execute(
                "SELECT count(*) FROM active_index_generations WHERE capability LIKE '%_v2'"
            ).fetchone()[0]
        )
        connection.close()
        expected = {
            "documents": 44,
            "document_versions": 44,
            "chunks": 2658,
            "ocr_regions": 402,
            "vision_results": 463,
            "language_observations_v2": 3523,
            "script_observations_v1": 3523,
            "representation_observations_v1": 3523,
            "v2_build_exclusions": 504,
            "language_text_projection_rows_v2": 3019,
            "multilingual_embeddings_v2": 3019,
            "multilingual_coverage_manifests_v2": 4,
            "multilingual_v2_alias_sets": 0,
            "active_multilingual_v2_alias_set": 0,
        }
        if counts != expected:
            raise IntegrityError(f"V2 READY row counts do not reconcile: {counts}")
        if len(generations) != 4 or any(row["state"] != "ready" for row in generations):
            raise IntegrityError("all four V2 generations are not READY")
        if any(row["completeness"] != "complete" for row in generations):
            raise IntegrityError("V2 generation coverage is incomplete")
        if integrity != "ok" or foreign_key_errors:
            raise IntegrityError("V2 database integrity audit failed")
        if active_v2 != 0:
            raise IntegrityError("V2 generation alias was promoted during build")
        return {
            "counts": counts,
            "generations": generations,
            "integrity_check": integrity,
            "foreign_key_errors": foreign_key_errors,
            "active_v2_aliases": active_v2,
            "target_sha256": _file_digest(target),
        }


def _scope(kind: LanguageEvidenceKindV3) -> LanguageObservationScope:
    if kind is LanguageEvidenceKindV3.CANONICAL_CHUNK:
        return LanguageObservationScope.CHUNK
    if kind is LanguageEvidenceKindV3.OCR_REGION:
        return LanguageObservationScope.OCR_REGION
    return LanguageObservationScope.ASSET


def _mapping_sequence(value: object, name: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ContractValidationError(f"{name} must be an array of objects")
    return tuple(value)


def _vision_text(payload: str) -> str:
    value = json.loads(payload)
    parts = [str(item.get("text", "")).strip() for item in value.get("captions", [])]
    parts += [str(item.get("value", "")).strip() for item in value.get("observations", [])]
    parts += [str(item.get("name", "")).strip() for item in value.get("entities", [])]
    return "\n".join(item for item in parts if item)


def _observation_reference_digest(value: LanguageObservationV2 | ScriptObservationV1) -> str:
    return _digest(
        {
            "observation_id": str(value.observation_id),
            "configuration_digest": value.configuration_digest,
            "input_hash": value.input_hash,
            "source_reference_digest": (
                None if value.source_reference is None else value.source_reference.identity_digest
            ),
        }
    )


def _complete_result(identities: Sequence[str]) -> ProjectionBuildResult:
    return ProjectionBuildResult(
        expected_count=len(identities),
        succeeded_count=len(identities),
        failed_count=0,
        skipped_count=0,
        checksum=hashlib.sha256("\n".join(sorted(identities)).encode()).hexdigest(),
    )


def _encoded_dataclass_vector(payload: Mapping[str, Any]) -> tuple[float, ...]:
    objects = payload.get("objects")
    root = payload.get("payload")
    if not isinstance(objects, dict) or not isinstance(root, dict):
        raise IntegrityError("stored embedding payload is malformed")
    reference = root.get("$ref")
    fields = objects[str(reference)]["fields"]
    encoded = fields["vector"]
    return tuple(float(item) for item in encoded["$tuple"])
