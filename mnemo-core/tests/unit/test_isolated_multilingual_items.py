"""Real persisted IR, OCR and Vision are distinct V2 evidence sources."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from mnemo.models.multilingual import LanguageCode, LanguageEvidenceKindV3
from mnemo.models.multilingual_index import MultilingualEvidencePositionV1
from mnemo.models.text_representations import RepresentationAuthority
from mnemo.phase85 import isolated_multilingual
from mnemo.phase85.isolated_multilingual import _items, _ObservationBuilder


def test_isolated_builder_reads_real_canonical_ocr_and_vision_lineage(tmp_path: Path) -> None:
    database = tmp_path / "mnemo.db"
    notebook, source, document, version, occurrence, ocr, vision, generation = (
        uuid4() for _ in range(8)
    )
    foreign_notebook, foreign_source, foreign_document, foreign_version = (
        uuid4() for _ in range(4)
    )
    parsed = tmp_path / "files" / "parsed" / str(version)[:8]
    parsed.mkdir(parents=True)
    (parsed / f"{version}.ir.json").write_text(
        json.dumps({"language": "en", "blocks": [{"language": "en"}, {"language": "hi"}]}),
        encoding="utf-8",
    )
    foreign_parsed = tmp_path / "files" / "parsed" / str(foreign_version)[:8]
    foreign_parsed.mkdir(parents=True)
    (foreign_parsed / f"{foreign_version}.ir.json").write_text(
        json.dumps({"language": "en", "blocks": [{"language": "en"}]}),
        encoding="utf-8",
    )
    with sqlite3.connect(database) as connection:
        connection.executescript(
            "CREATE TABLE sources(notebook_id TEXT,document_id TEXT,source_id TEXT);"
            "CREATE TABLE document_versions(version_id TEXT);"
            "CREATE TABLE chunks(id TEXT,document_id TEXT,version_id TEXT,text TEXT,"
            "position_page_number INTEGER,source_start_ordinal INTEGER,"
            "source_end_ordinal INTEGER,position_chunk_index INTEGER);"
            "CREATE TABLE ocr_results(derivation_id TEXT,document_id TEXT,version_id TEXT,"
            "occurrence_id TEXT,generation_id TEXT,completeness TEXT);"
            "CREATE TABLE ocr_regions(region_id TEXT,derivation_id TEXT,text TEXT,"
            "page_number INTEGER,language_code TEXT,order_index INTEGER);"
            "CREATE TABLE vision_results(derivation_id TEXT,document_id TEXT,"
            "version_id TEXT,occurrence_id TEXT,generation_id TEXT,payload TEXT,"
            "completeness TEXT);"
            "CREATE TABLE asset_occurrences(occurrence_id TEXT,locator TEXT);"
        )
        connection.execute(
            "INSERT INTO sources VALUES(?,?,?)", (str(notebook), str(document), str(source))
        )
        connection.execute(
            "INSERT INTO sources VALUES(?,?,?)",
            (str(foreign_notebook), str(foreign_document), str(foreign_source)),
        )
        connection.execute("INSERT INTO document_versions VALUES(?)", (str(version),))
        connection.execute("INSERT INTO document_versions VALUES(?)", (str(foreign_version),))
        connection.execute(
            "INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?)",
            ("canonical-chunk", str(document), str(version), "Angular momentum", 1, 0, 0, 0),
        )
        connection.execute(
            "INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?)",
            (
                "mixed-chunk",
                str(document),
                str(version),
                "Angular momentum कोणीय संवेग",
                1,
                0,
                1,
                1,
            ),
        )
        connection.execute(
            "INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?)",
            ("foreign-chunk", str(foreign_document), str(foreign_version), "Private", 1, 0, 0, 0),
        )
        connection.execute(
            "INSERT INTO ocr_results VALUES(?,?,?,?,?,?)",
            (str(ocr), str(document), str(version), str(occurrence), str(generation), "complete"),
        )
        connection.execute(
            "INSERT INTO ocr_regions VALUES(?,?,?,?,?,?)",
            ("region-1", str(ocr), "कोणीय संवेग", 1, "hi", 0),
        )
        connection.execute(
            "INSERT INTO asset_occurrences VALUES(?,?)",
            (str(occurrence), json.dumps({"page_number": 2})),
        )
        connection.execute(
            "INSERT INTO vision_results VALUES(?,?,?,?,?,?,?)",
            (
                str(vision),
                str(document),
                str(version),
                str(occurrence),
                str(generation),
                json.dumps(
                    {
                        "captions": [
                            {"text": "Rotating wheel", "language": {"language_code": "en"}}
                        ],
                        "observations": [{"value": "Angular velocity arrow"}],
                        "entities": [{"name": "wheel"}],
                    }
                ),
                "complete",
            ),
        )
        connection.execute(
            "INSERT INTO vision_results VALUES(?,?,?,?,?,?,?)",
            (
                str(uuid4()),
                str(document),
                str(version),
                str(occurrence),
                str(generation),
                json.dumps({"captions": [], "observations": [], "entities": []}),
                "complete",
            ),
        )
    items = _items(database, notebook)
    assert [item.source.kind for item in items] == [
        LanguageEvidenceKindV3.CANONICAL_CHUNK,
        LanguageEvidenceKindV3.CANONICAL_CHUNK,
        LanguageEvidenceKindV3.OCR_REGION,
        LanguageEvidenceKindV3.VISION_DERIVATION,
    ]
    assert [item.language.value for item in items] == ["en", "und", "hi", "en"]
    assert items[0].source.chunk_id == "canonical-chunk"
    assert items[0].representation.representation_authority is RepresentationAuthority.ORIGINAL
    assert items[1].source.chunk_id == "mixed-chunk"
    assert items[2].source.occurrence_id == occurrence
    assert items[2].source.derivation_id == ocr
    assert items[2].source.chunk_id is None
    assert items[2].text == "कोणीय संवेग"
    assert items[3].source.derivation_id == vision
    assert items[3].position.page_number == 2
    assert items[3].text == "Rotating wheel\nAngular velocity arrow\nwheel"
    assert all(
        item.observation.input_content_hash == item.source.source_content_hash for item in items
    )
    malformed_languages = (
        "hi-IN/en-US",
        "unknown_script_or_symbol_representation_of_a_character_like_the_Arabic_letter_q_or_a_stylized_symbol.",
    )
    invalid_vision_ids = (uuid4(), uuid4())
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO ocr_regions VALUES(?,?,?,?,?,?)",
            ("region-invalid", str(ocr), "mixed annotation", 1, "en_US/hi_IN", 1),
        )
        connection.execute(
            "INSERT INTO ocr_regions VALUES(?,?,?,?,?,?)",
            ("region-japanese", str(ocr), "角運動量", 1, "ja-JP", 2),
        )
        for identifier, malformed in zip(invalid_vision_ids, malformed_languages, strict=True):
            connection.execute(
                "INSERT INTO vision_results VALUES(?,?,?,?,?,?,?)",
                (
                    str(identifier),
                    str(document),
                    str(version),
                    str(occurrence),
                    str(generation),
                    json.dumps(
                        {
                            "captions": [
                                {"text": "source caption", "language": {"language_code": malformed}}
                            ]
                        }
                    ),
                    "complete",
                ),
            )
    fallbacks: list[dict[str, str]] = []
    expanded = _items(database, notebook, fallbacks)
    by_evidence = {str(item.source.evidence_id): item for item in expanded}
    assert by_evidence["region-invalid"].language == LanguageCode("und")
    assert by_evidence["region-japanese"].language == LanguageCode("ja-JP")
    assert all(
        by_evidence[str(identifier)].language == LanguageCode("und")
        for identifier in invalid_vision_ids
    )
    assert {item["evidence_id"] for item in fallbacks} == {
        "region-invalid",
        *(str(identifier) for identifier in invalid_vision_ids),
    }
    assert all(item["version_id"] == str(version) for item in fallbacks)
    with sqlite3.connect(database) as connection:
        retained = json.loads(
            connection.execute(
                "SELECT payload FROM vision_results WHERE derivation_id=?",
                (str(invalid_vision_ids[0]),),
            ).fetchone()[0]
        )
    assert retained["captions"][0]["language"]["language_code"] == malformed_languages[0]
    with pytest.raises(ValueError, match="no authorized source memberships"):
        _items(database, uuid4())


def test_observation_builder_persists_exact_derived_identities() -> None:
    identities = (uuid4(), uuid4())
    persisted: list[object] = []

    class Store:
        async def get_representation_observation_v1(self, identifier: object) -> None:
            assert identifier in identities
            return None

        async def put_representation_observation_v1(self, value: object) -> bool:
            persisted.append(value)
            return True

    items = tuple(
        SimpleNamespace(observation=SimpleNamespace(observation_id=identifier))
        for identifier in identities
    )
    result = asyncio.run(_ObservationBuilder(Store(), items).build(uuid4()))  # type: ignore[arg-type]
    assert result.expected_count == result.succeeded_count == 2
    assert result.failed_count == 0
    assert {value.observation_id for value in persisted} == set(identities)


def test_observation_builder_reuses_matching_immutable_record_and_rejects_conflict() -> None:
    @dataclass(frozen=True)
    class Observation:
        observation_id: object
        created_at: datetime
        lineage: str

    identifier = uuid4()
    earlier = datetime.now(UTC) - timedelta(days=1)
    current = Observation(identifier, datetime.now(UTC), "same-source")
    persisted = Observation(identifier, earlier, "same-source")
    writes: list[object] = []

    class Store:
        async def get_representation_observation_v1(self, value: object) -> Observation:
            assert value == identifier
            return persisted

        async def put_representation_observation_v1(self, value: object) -> bool:
            writes.append(value)
            return True

    item = SimpleNamespace(observation=current)
    result = asyncio.run(_ObservationBuilder(Store(), (item,)).build(uuid4()))  # type: ignore[arg-type]
    assert result.succeeded_count == 1
    assert writes == []
    conflicting = SimpleNamespace(
        observation=Observation(identifier, datetime.now(UTC), "different-source")
    )
    with pytest.raises(ValueError, match="conflicting lineage"):
        asyncio.run(_ObservationBuilder(Store(), (conflicting,)).build(uuid4()))  # type: ignore[arg-type]


def test_builder_keeps_new_notebook_generations_ready_not_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    notebook = uuid4()
    source = SimpleNamespace(
        version_id=uuid4(),
        identity_digest="a" * 64,
        kind=LanguageEvidenceKindV3.CANONICAL_CHUNK,
    )
    text = "Canonical multilingual text"
    representation = SimpleNamespace(
        evidence_reference=source,
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
        source_generation_ids=(),
        reference_id=uuid4(),
        representation_type=SimpleNamespace(value="unicode_semantic_text"),
    )
    item = SimpleNamespace(
        source=source,
        text=text,
        language=LanguageCode("en"),
        position=MultilingualEvidencePositionV1(page_number=1),
        observation=SimpleNamespace(observation_id=uuid4()),
        representation=representation,
    )
    monkeypatch.setattr(isolated_multilingual, "_items", lambda *_: (item,))
    stages: list[str] = []

    class Provider:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def profile(self) -> object:
            return SimpleNamespace(
                vector_space="b" * 64,
                preprocessing_digest="c" * 64,
                dimension=1024,
            )

        async def initialize(self) -> None:
            stages.append("initialize")

        async def close(self) -> None:
            stages.append("close")

    class Store:
        def __init__(self, database: Path) -> None:
            assert database == tmp_path / "new.db"

        async def open(self) -> None:
            stages.append("open")

        async def close(self) -> None:
            stages.append("store_close")

        async def list_authorized_multilingual_embeddings_v3(
            self, **kwargs: object
        ) -> tuple[object, ...]:
            assert kwargs["notebook_id"] == notebook
            assert kwargs["authorized_sources"] == (source,)
            return (SimpleNamespace(embedding_id=uuid4(), source=source),)

    class Coordinator:
        def __init__(self, store: Store) -> None:
            assert isinstance(store, Store)

        async def build_and_activate(
            self, spec: object, builder: object, *, activate: bool
        ) -> object:
            assert not activate
            stages.append(type(builder).__name__)
            return SimpleNamespace(generation_id=spec.generation_id)

    monkeypatch.setattr(isolated_multilingual, "BGEM3EmbeddingProvider", Provider)
    monkeypatch.setattr(isolated_multilingual, "SQLiteStore", Store)
    monkeypatch.setattr(isolated_multilingual, "DerivedProjectionCoordinator", Coordinator)
    report = asyncio.run(
        isolated_multilingual.build_isolated_multilingual(
            database=tmp_path / "new.db",
            notebook_id=notebook,
            profile_file=(
                Path(__file__).resolve().parents[3]
                / "config/model_profiles/full_multilingual_v2_profiles.toml"
            ),
            cache_folder=tmp_path,
        )
    )
    assert report["items"] == 1
    assert report["embedding_count"] == 1
    assert report["invalid_language_annotation_count"] == 0
    assert report["invalid_language_annotation_examples"] == []
    assert report["active"] is False
    assert set(report["generations"]) == {
        "representation_derivation_v2",
        "language_text_v2",
        "multilingual_embedding_v2",
        "multilingual_vector_v2",
    }
    assert stages[0] == "open"
    assert stages[-2:] == ["close", "store_close"]
