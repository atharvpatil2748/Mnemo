"""Deterministic synthetic V2 database fixture for clean CI and isolated testing."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path


def create_synthetic_v2_db(target: Path, manifest_path: Path) -> None:
    """Create a minimal deterministic V2 database.

    Satisfies manifest identity and runtime contracts. Used ONLY when the governed
    production database is not present in the environment (e.g. clean CI).
    If the target file already exists and is non-empty, this function is a strict no-op.
    """
    if target.exists() and target.stat().st_size > 0:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    conn = sqlite3.connect(target)
    try:
        cur = conn.cursor()

        # 1. v2_build_runs  (schema matches production V2 DB)
        cur.execute(
            """CREATE TABLE v2_build_runs (
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
            )"""
        )
        cur.execute(
            """INSERT INTO v2_build_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                manifest["build_run_id"],
                "0d7a1648-b585-54e8-b80a-129e6409b6d6",  # authorization_id
                manifest["target_path"],
                manifest["corpus_digest"],
                manifest["census_digest"],
                manifest["profile_fingerprint"],
                manifest["vector_space_identity"],
                manifest["build_manifest_digest"],
                manifest["storage_manifest_digest"],
                "2026-09-01T05:07:22.126096+00:00",
                "2026-09-01T09:45:54.280131+00:00",
                "ready",
            ),
        )

        # 2. index_generations
        cur.execute(
            """CREATE TABLE index_generations (
                generation_id TEXT PRIMARY KEY, capability TEXT, checksum TEXT,
                provider_identity TEXT, model_identity TEXT,
                configuration_digest TEXT, dimensions INTEGER, state TEXT,
                profile TEXT DEFAULT 'full_multilingual_v2_local_prebuild',
                item_count INTEGER DEFAULT 3019
            )"""
        )
        for g in manifest["generations"]:
            cur.execute(
                """INSERT INTO index_generations (
                    generation_id, capability, checksum, provider_identity,
                    model_identity, configuration_digest, dimensions, state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    g["generation_id"],
                    g["capability"],
                    g["checksum"],
                    g["provider_identity"],
                    g["model_identity"],
                    g["configuration_digest"],
                    g["dimensions"],
                    "ready",
                ),
            )

        # 3. index_generation_sources
        cur.execute(
            """CREATE TABLE index_generation_sources (
                generation_id TEXT, source_id TEXT, source_kind TEXT
            )"""
        )
        for g in manifest["generations"]:
            for src in g.get("source_generation_ids", []):
                cur.execute(
                    "INSERT INTO index_generation_sources VALUES (?, ?, 'generation')",
                    (g["generation_id"], src),
                )

        # 4. multilingual_embeddings_v2
        cur.execute(
            """CREATE TABLE multilingual_embeddings_v2 (
                generation_id TEXT, vector_space TEXT
            )"""
        )
        emb = next(
            g for g in manifest["generations"] if g["capability"] == "multilingual_embedding_v2"
        )
        cur.execute(
            "INSERT INTO multilingual_embeddings_v2 VALUES (?, ?)",
            (emb["generation_id"], manifest["vector_space_identity"]),
        )

        # 5. index_generation_coverage  (schema matches production V2 DB)
        cur.execute(
            """CREATE TABLE index_generation_coverage (
                generation_id TEXT PRIMARY KEY
                    REFERENCES index_generations(generation_id) ON DELETE CASCADE,
                expected_count INTEGER NOT NULL CHECK(expected_count >= 0),
                succeeded_count INTEGER NOT NULL CHECK(succeeded_count >= 0),
                failed_count INTEGER NOT NULL CHECK(failed_count >= 0),
                skipped_count INTEGER NOT NULL CHECK(skipped_count >= 0),
                completeness TEXT NOT NULL CHECK(completeness IN ('complete','partial')),
                checksum TEXT NOT NULL,
                failure_digest TEXT,
                updated_at TEXT NOT NULL,
                CHECK(expected_count = succeeded_count + failed_count + skipped_count)
            )"""
        )
        _ts = "2026-09-01T05:07:22+00:00"
        for g in manifest["generations"]:
            cur.execute(
                "INSERT INTO index_generation_coverage VALUES"
                " (?, 3019, 3019, 0, 0, 'complete', ?, NULL, ?)",
                (g["generation_id"], g["checksum"], _ts),
            )

        # 6. multilingual_coverage_manifests_v2
        cur.execute(
            """CREATE TABLE multilingual_coverage_manifests_v2 (
                generation_id TEXT PRIMARY KEY,
                capability TEXT,
                profile_fingerprint TEXT,
                dependency_digest TEXT,
                coverage_digest TEXT,
                item_identity_digest TEXT,
                expected_count INTEGER,
                succeeded_count INTEGER,
                failed_count INTEGER,
                skipped_count INTEGER,
                provenance_complete INTEGER,
                authorization_compatible INTEGER,
                rollback_metadata_digest TEXT,
                payload TEXT,
                payload_hash TEXT,
                created_at TEXT
            )"""
        )
        for g in manifest["generations"]:
            payload = json.dumps(
                {
                    "schema_version": 1,
                    "payload": {"$ref": "1"},
                    "objects": {
                        "1": {
                            "kind": "dataclass",
                            "type": (
                                "mnemo.models.multilingual_generation"
                                ":MultilingualCoverageManifestV2"
                            ),
                            "fields": {
                                "generation_id": {"$uuid": g["generation_id"]},
                                "capability": g["capability"],
                                "profile_fingerprint": manifest["profile_fingerprint"],
                                "dependency_digest": (
                                    "4f53cda18c2baa0c0354bb5f9a3ecbe5e"
                                    "d12ab4d8e11ba873c2f11161202b945"
                                ),
                                "coverage_digest": (
                                    "471142981927966d6875608039adbc385"
                                    "108ab50dfb6fa1dcb38ff0f39071e02"
                                ),
                                "item_identity_digest": g["checksum"],
                                "expected_count": 3019,
                                "succeeded_count": 3019,
                                "failed_count": 0,
                                "skipped_count": 0,
                                "provenance_complete": True,
                                "authorization_compatible": True,
                                "language_tags": {"$tuple": ["hi", "mr", "und"]},
                                "script_codes": {
                                    "$tuple": ["Deva", "Grek", "Latn", "Mlym", "Zzzz"]
                                },
                                "representation_types": {
                                    "$tuple": ["ocr_text", "unicode_semantic_text", "vision_text"]
                                },
                                "source_kinds": {
                                    "$tuple": [
                                        "canonical_chunk",
                                        "ocr_region",
                                        "vision_derivation",
                                    ]
                                },
                                "rollback_metadata_digest": (
                                    "068d362eb7a36fcef56e401a748dbad1b"
                                    "56377f5ca3227c85a48229a10aab17a"
                                ),
                                "created_at": {"$datetime": "2026-09-01T05:07:22.126096+00:00"},
                            },
                        }
                    },
                },
                separators=(",", ":"),
            )
            _mcm_ts = "2026-09-01T05:07:22+00:00"
            payload_hash = hashlib.sha256(payload.encode()).hexdigest()
            cur.execute(
                """INSERT INTO multilingual_coverage_manifests_v2 VALUES (
                    ?, ?, ?, 'dep', 'cov', ?,
                    3019, 3019, 0, 0, 1, 1, 'roll', ?, ?, ?
                )""",
                (
                    g["generation_id"],
                    g["capability"],
                    manifest["profile_fingerprint"],
                    g["checksum"],
                    payload,
                    payload_hash,
                    _mcm_ts,
                ),
            )

        # 7. active_multilingual_v2_alias_set & multilingual_v2_alias_sets
        alias_digest = "b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0"
        cur.execute(
            """CREATE TABLE active_multilingual_v2_alias_set (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                alias_set_digest TEXT NOT NULL,
                promoted_at TEXT NOT NULL
            )"""
        )
        cur.execute(
            "INSERT INTO active_multilingual_v2_alias_set VALUES"
            " (1, ?, '2026-09-01T11:09:20+00:00')",
            (alias_digest,),
        )

        cur.execute(
            """CREATE TABLE multilingual_v2_alias_sets (
                alias_set_digest TEXT PRIMARY KEY,
                profile_fingerprint TEXT NOT NULL,
                generation_ids TEXT NOT NULL,
                rollback_alias_set_digest TEXT,
                rollback_generation_ids TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        gen_ids_json = json.dumps(
            sorted([g["generation_id"] for g in manifest["generations"]]),
            separators=(",", ":"),
        )
        cur.execute(
            "INSERT INTO multilingual_v2_alias_sets VALUES"
            " (?, ?, ?, 'rollback', '[]', '2026-09-01T11:07:21+00:00')",
            (alias_digest, manifest["profile_fingerprint"], gen_ids_json),
        )

        # 7b. multilingual_v2_activation_records  (matches production schema)
        cur.execute(
            """CREATE TABLE multilingual_v2_activation_records (
                alias_set_digest TEXT PRIMARY KEY
                    REFERENCES multilingual_v2_alias_sets(alias_set_digest),
                activation_mode TEXT NOT NULL CHECK(
                    activation_mode IN ('first_v2_activation','v2_upgrade')
                ),
                recovery_mode TEXT NOT NULL CHECK(
                    recovery_mode IN ('deactivate_v2_alias_set','prior_v2_alias_set')
                ),
                authorization_id TEXT NOT NULL,
                authorization_digest TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        cur.execute(
            "INSERT INTO multilingual_v2_activation_records VALUES"
            " (?, 'first_v2_activation', 'deactivate_v2_alias_set',"
            " '3d8e50f6-1dda-5abf-89b9-c04f2ffd6a43',"
            " '52ae49cbf5958e6d3760a60846ab98cfaf90174ef4558f1f2441288fd83b8521',"
            " '2026-09-01T11:07:21.244709+00:00')",
            (alias_digest,),
        )

        # 8. notebooks, documents, document_versions, chunks
        nb_id = "df9c20cf-85fe-529c-902e-2e9e68193fbe"
        doc_id = "3ae9cb8b-6798-5dcf-a340-5b2d31f4248f"
        ver_id = "32a665e7-fb65-5fd5-aebe-0b0d4ddc84b8"
        chunk_id = "6ca72226f39552c65fa3f09fe06c59d792f7d16d06143b228e4863f805cd9545"

        cur.execute(
            """CREATE TABLE notebooks (
                notebook_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata TEXT NOT NULL
            )"""
        )
        _nb_ts = "2026-09-01T00:00:00Z"
        cur.execute(
            "INSERT INTO notebooks VALUES (?, 'Test NB', 'Desc', ?, ?, '{}')",
            (nb_id, _nb_ts, _nb_ts),
        )

        cur.execute(
            """CREATE TABLE documents (
                document_id TEXT PRIMARY KEY,
                current_version_id TEXT NOT NULL,
                current_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        cur.execute(
            "INSERT INTO documents VALUES (?, ?, 'hash', 'indexed', ?, ?)",
            (doc_id, ver_id, _nb_ts, _nb_ts),
        )

        cur.execute(
            """CREATE TABLE document_versions (
                version_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                metadata TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        cur.execute(
            "INSERT INTO document_versions VALUES (?, ?, 'hash', '{}', 'current', ?)",
            (ver_id, doc_id, _nb_ts),
        )

        cur.execute(
            """CREATE TABLE chunks (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                version_id TEXT NOT NULL,
                text TEXT NOT NULL,
                chunk_type TEXT NOT NULL,
                position_section_index INTEGER NOT NULL,
                position_chunk_index INTEGER NOT NULL,
                position_page_number INTEGER,
                position_start_offset INTEGER,
                position_end_offset INTEGER,
                source_start_ordinal INTEGER NOT NULL,
                source_end_ordinal INTEGER NOT NULL,
                heading_path TEXT NOT NULL,
                parent_chunk_id TEXT,
                sibling_ids TEXT NOT NULL,
                metadata TEXT NOT NULL
            )"""
        )
        cur.execute(
            """INSERT INTO chunks VALUES (
                ?, ?, ?, 'Sample semantic text for unit test verification', 'passage',
                0, 0, 1, 0, 48, 0, 1, '["Heading"]', NULL, '[]', '{}'
            )""",
            (chunk_id, doc_id, ver_id),
        )

        # 9. language_text_projection_rows_v2
        lang_gen = next(g for g in manifest["generations"] if g["capability"] == "language_text_v2")
        cur.execute(
            """CREATE TABLE language_text_projection_rows_v2 (
                row_id TEXT PRIMARY KEY,
                notebook_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                version_id TEXT NOT NULL,
                occurrence_id TEXT,
                derivation_id TEXT,
                evidence_reference_digest TEXT NOT NULL,
                representation_reference_id TEXT NOT NULL,
                representation_type TEXT NOT NULL,
                language TEXT NOT NULL,
                page_number INTEGER,
                section_index INTEGER,
                heading_path TEXT NOT NULL,
                heading_path_key TEXT NOT NULL,
                generation_id TEXT NOT NULL,
                text_hash TEXT NOT NULL,
                payload TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        cur.execute(
            """INSERT INTO language_text_projection_rows_v2 VALUES (
                'row-1', ?, ?, ?, ?, NULL, NULL,
                'ev-digest', 'rep-id', 'unicode_semantic_text', 'hi',
                1, 0, '["Heading"]', 'heading',
                ?, 'text-hash', '{}', 'payload-hash', '2026-09-01T00:00:00Z'
            )""",
            (nb_id, chunk_id, doc_id, ver_id, lang_gen["generation_id"]),
        )

        conn.commit()
    finally:
        conn.close()
