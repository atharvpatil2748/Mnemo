"""Deterministic synthetic V2 database fixture for clean CI and isolated testing."""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import zlib
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
        row_payload = zlib.decompress(
            base64.b64decode(
                b"eJy1V8mO3DYQ/ZWG4FvCMXdKfcti5BAnNhxjLrHR4FLsVqyWGlraHhgG/A/JMed8mL8kRamntxk"
                b"PvIyBgWdEsha+qveKfps17i/wfZfN32Ys/RNLqML46VuwPYSF7dPXg4AffbmGbJ5xyjWhBaHsOV"
                b"VzauacXzCuaaG/o3ROafbu+2wJNbS2L5t6UYbRwTCkPzJrOKc2RIJePFFCA8nBeOJpEWSQXmkRk"
                b"4PK1svBLmG0bSGiqT5eXzSug3Y7hcB9aKH2MGb+oB82FRr+ubeU2buXaLtpujKdP/Jpks8WNi10"
                b"UPf2bFeMu83rsztQBUIWmpOi8IYokI5YpSOxEIwJIBmI0W/n23LTf1amasq0a4bWH9+dZ/vVxQm"
                b"2N/zscsxZ1EY4R7RWgaiCWeIYd0QaHqMAUTjjp1g9vMESZ4/ebKDFAtc94S/qF/Vl6aYgs761db"
                b"cuu650ZVX2V7MmzuysK+tlBSTAsgUgTSQRf4dmPeuuuh7WycUvbTNsZr83FzMy+1HPfsYWmn14/"
                b"/eM6oc0f8gp1enUH6sy9uM6S91DGJsL+uH9f/ufi4vZuEYYbu9W//1nv51NV1isbLfCe0AelJBO"
                b"eO+wxYIrtHIFCCW4kopypriyQQQeQeXcSB1kQXVhracxL7SRCehXZZ0wxJ63vrJdl0JcbVLvr2t"
                b"YNxfrJkDVXayHqkdEUkNWCzSBN/PfjpaeY1ZP2yYRDGF81ry+HKvIz3i2GupXY4NlugAmvY8i59"
                b"FIKTA5zUzIVSx89NpqbZmx0gLVmkmQ1kcXBLMCPCjhHaYZsIbbA+/qoapwsfFDKuxZG0cnuRfCk"
                b"cCtIsp7T5yMyEeqDEMMLQZPCcO2DKll7y3JCV5MBOphfReo88c7tj/apfArWl4KdLG11ZDq4W3d"
                b"1KVH/EccR4UoaxgFoi2XZf1pca79P55sn4ymJ4FqBHULi+0oCXXTg2uaV2eABoSAUx8JggFE8cK"
                b"TgnIgHArQOStEdJDMG++Htt1DOhVpY9tUoj3Ye6VYhHIJXX99bicCvqn7dP6+uv52dTkLenpdH0"
                b"ALzXOinGBESjDEWRMJBScxHiucGvtnC213cxBQDdIYRREs1A8ELBAbnSa5BFsIsJFqFKgvI+ONv"
                b"nl2DeblWD9xRsF7x/JmFc+1/Gvm2KE1TiE1MjDrFU7mQHEupeHkOE+4mhgAh25u9M15t7BDv0Ky"
                b"9Fcf5cqor6dW3fzZyfcPeycHzkwMtNUtMW/VqbMzx8icEU1pqywLJFooiDLGEpszT7SShaFaeMj"
                b"FLUGntvmcOyYJP73n8+TjcMUBxQftFx2sbd2XfjFO03uY/XdN+ZefQYtPvNaBICxlL08JcnyLaz"
                b"XKBGe5Ac9Y4IHSUODbLc0TY5EtXCtqXHAhCOosvkSQ5MgPHrQUHLktmKGY8McrDDlXPCpH0FISx"
                b"QzHClNLdI6qQqmLhc5HKT3ycOdYuRWHJwfrNFmO6rp/fn4t1EchzjBWn4AxhZDnzGmwlgamAnOR"
                b"exNU8FIo71iuWc5D7oxQjDGO4EqXU4eVcd55a+/EmImo05ubBJU7xNgWJA9aE+dzVaBDjfX7lhh"
                b"PFPmGCOtThA+cDV/4yNvPlZ9wL/kwpxFWKLJ4crGx/eqMsWnAo9ojag7a/VidnobT2zGb03t7el"
                b"7Pvae7//EkPMYUrqrGhqNZxCatWqF8LXZzOpuzd/8D4g+73g=="
            )
        ).decode("utf-8")
        row_payload_hash = "1df62357de89309db0cab846113d81d9be4cc030d47d13a3e75fff2834eabba6"
        cur.execute(
            """INSERT INTO language_text_projection_rows_v2 VALUES (
                ?, ?, ?, ?, ?, NULL, NULL,
                ?, ?, ?, ?,
                NULL, 0, '[]', '',
                ?, ?, ?, ?, ?
            )""",
            (
                "05e34962-99c7-5e4b-a56f-aed77de41e37",
                nb_id,
                chunk_id,
                doc_id,
                ver_id,
                "298149c5cb02cc02378767d9d30fcb486bb26680fa1fa5f655463bfd0c107e02",
                "74d1ac59-0d07-59c7-b22d-af7fdeadf876",
                "unicode_semantic_text",
                "und",
                lang_gen["generation_id"],
                "e8d534b3ccb202db965b9e3532545021525ad3d2fe582746d49069aac0f89674",
                row_payload,
                row_payload_hash,
                "2026-09-01T05:07:22.126096+00:00",
            ),
        )

        # representation_observations_v1
        cur.execute(
            """CREATE TABLE representation_observations_v1 (
                observation_id TEXT PRIMARY KEY,
                notebook_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                version_id TEXT NOT NULL,
                evidence_reference_digest TEXT NOT NULL,
                representation_type TEXT NOT NULL,
                input_content_hash TEXT NOT NULL,
                payload TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        rep_payload = zlib.decompress(
            base64.b64decode(
                b"eJy1lk2P3DYMhv+L0Vujhb4lz60oemqAAEGQS1EYFEXNuvHYA38MGgT730t7Zndn0ibIosllsZZ"
                b"Einz0kpxP1ZD+IpynavepUuuf0lKXt09Y5vthbOePDXYwbUs/Ub8cql116Okw3B2GTN10N9Pfcz"
                b"PScaSJ+hnmduin3dub718eXf26eXpVnaBbiB3thxONPeUm08xhDGP18KpC6No0wky52hXoJuKlo"
                b"S9tph7ZSN3Jy8J+GTf3TW73NM3sT1ON1mStYlBSFR0jKpuNsj7nXBdbCCFoTCQzZJ1zIGvBYG0D"
                b"BUx15NBwpPXqBuYt48wfc3tYg9VSeyGj0PGdijsZdsbdKWdrE3+WciflGvtjHk3LwVfHkfPrgcM"
                b"W0GeBDOw4tP0sbnGJRytx0tWVj5FO7cT77ImTvpO81/bHZW44+5mNm3uY7nmTYnbGJoOYOMacau"
                b"9STcYZ7ayTWjntIDOVQi7qwCxsLX0NgLLE2gfLfjvo9wvsqRnSROPpjHWkQuMK/fz483LsmMMf/"
                b"C/v8L2meviTc742WdPm/WXZ8s/OgwOVRQGqhQsBBESFwjO1IL1BimaldoujmT8e6WVye8eLt5J7"
                b"t/p4FtrStyv9ZqID9HOLzepmvXrCsT3OL0rbntOehmVEej69HT6f0NUDH/jQ9hsEmAEvuj9n9uL"
                b"6efMc3Xu1Rq1vSxXvl/7DWXK+JmURi4m6BGsNv7ZXIUdXaizowXtQASyQ9F5ZsoAlcYGAISRnMG"
                b"36G9ur5+yXruPFAZfDqrnbFy7JajQmiazBCYeIInGViShdUCxK4MvXgFnJW/l+tyDPcL+gkcPSz"
                b"W3XrpLudq8v0v7tEsLvbPneXGkDoR9YHtA1G8c1XLalrRrGdt/233bPo//XZ9s3m+nNRT1DPVFz"
                b"2jTfDzOlYfjweckwAi2xCIZBwukaRS01Ce5s5KOqTUm0mg+Iyzg+IT0/0hHG9YmeYD9p86lDns9"
                b"dpPv928jF8Z56Gj9X0GXvNl3M5I3XUbhklLCWgkgQipCULN+n6uQ2/fCYmP7dX6QnG4KTDIsYVq"
                b"EsoCQvoiWoDUGRHl9Sil/VzdtHmO+39zO3JXjdQJ7GkVkHEaFSPGukzLVFt5ZLAAarvZMh5ZSzk"
                b"QmKD5wDo9TZW6M5dKPC2vC/3FwpaqeLS4ItrXAqaG6uEoSPDE3KVGofq8/a81er5j8b0VXrWQvn"
                b"Ss2PI+N/97qrK54Zb23OfgNjSTlGlTwByKxcVqloDNll/iHgMKnoVdQ5pmCcUkozXJuiTPwyCRM"
                b"CfJWxMoVlnq3ILiZmDLWI2XuRMLqaHXp+vx/J+Dydfhjhh7VlfOwGyFfDS53H4j1PyuZSdvyj6+"
                b"Efq4JjfQ=="
            )
        ).decode("utf-8")
        cur.execute(
            """INSERT INTO representation_observations_v1 VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )""",
            (
                "d56a5a1d-fae9-577a-a81c-65497063ce83",
                "df9c20cf-85fe-529c-902e-2e9e68193fbe",
                "cde63628-5b31-44e7-ba7f-0eb452519b57",
                "fb42c33b-d2a5-5ccc-b4fe-80571534a617",
                "06e47750-85ee-5fed-afb6-84ea93eaf06c",
                "298149c5cb02cc02378767d9d30fcb486bb26680fa1fa5f655463bfd0c107e02",
                "unicode_semantic_text",
                "e8d534b3ccb202db965b9e3532545021525ad3d2fe582746d49069aac0f89674",
                rep_payload,
                "c3570da2584077ff3c0bc2f311853c47318d1a3103c13c9d2967e12eead8c19d",
                "2026-08-28T18:07:35.154938+00:00",
            ),
        )

        # language_observations_v2
        cur.execute(
            """CREATE TABLE language_observations_v2 (
                observation_id TEXT PRIMARY KEY,
                actor_id TEXT NOT NULL,
                notebook_id TEXT NOT NULL,
                source_id TEXT,
                document_id TEXT,
                version_id TEXT,
                target_scope TEXT NOT NULL,
                target_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        lang_payload = zlib.decompress(
            base64.b64decode(
                b"eJytVtuK5DYQ/RezbxkNsm6W+i0sgUAWFpKwLyGYUqnU7YzbbnzpZFjm31N2X2am92WXmZfGtlR"
                b"1jk7VKfXXoo//EE5jsflalMtPbqhN6yvg1A91k5bnD/O8PBQuWkg2aFFB8MLKQMJTMqLyKkJSGl"
                b"HZ4umuwL7LzXYeYGr6rk7NlsaJwylbbSI63u5tJMw6Y/AyabQQSRrvoCSggLqsUHotwSpjMHuls"
                b"sGQCs48EEyUaphWXolfpmZPnFxJ5YT0Qvk/S7+R1Ubb+9KaoP1PUm6kXHglmmg5Fm9vodvOsCXR"
                b"x5GG48pUbKmjoUGRoWkFtv1ISRzL4jmwHujYjLyVM5T38l7y2u7x0E87GmmV7cM0H1rm8xc/DpQ"
                b"XYsXT34zddId5qncw7hYlfFqkYMEi804xOBsDaauVNVaq0ioWWieVyXpVGZdMkC4AoMw+uMow7L"
                b"75j3W4HKPYZGhHuiu6fqLY9w83lUs5oJKYhbeZhFUBRZCKhKJAzpdB50iLQi/UuMlAXlmVbeRiW"
                b"yNsWSkBXoJwPkQrZczB+SXD2M8DEguVaaAOac1xUmLtjQmGLU31qZ8ClQa5D7zKlTGaD+rKKjHH"
                b"gBkdOG6ICgyQdK40ZABzTLoETUhWYyyu6UbsDyco6uY9p953tO/v932idrzfz+3UtM0iVbv5dJb"
                b"s8/NR/1ij74ojtPPSS7ibu4fiidk+NN0qH0yALYzjgvi4IP0YwBe1HF3dOGyedv3QTI/1KfV3sX"
                b"+R9OdL/Mczswt9Jt/1/3ZXJ6abOphlhRt5/f5sz1xGjFYp4z0oZX1mR+dgbArecbsmT1qRwQqqp"
                b"ChqCJWqFOoqJVTgg2cGz+14BdNv1vHXs8Ga8SSjfi3j86lT8Uakj7y25DCvERDaJg7L3Lna7AzK"
                b"E+DNkNcCcSZ7A7z04btZJfFse2Htbm5b/tjjvKduunF7joZLq6NICqywiCii4cnhpa1KHl3A4K+"
                b"66L1InrT8ER//cqbwG0d+0S9dDF3fNVy8+uxn7s+mIw6p2Tbbpvs+nEv+T6fYz2voK6CORT1Sfd"
                b"QLxFsHMOI8DFdJT0U6wLCU6Cr2dbhezXvad569bPpp2f9+l8058Xo/3nbQee31cTGR007xn4SoS"
                b"2EMVSJClYWkaBiv5Dtj7Z8jDeO3d410ZKrKShaLWKzM1zDk6IQ3BEETZOnwzWPlUtffL2J+OY2q"
                b"Azy2PaQXI6xc7zXc0R7qM+FiUz79Dw4K/38="
            )
        ).decode("utf-8")
        cur.execute(
            """INSERT INTO language_observations_v2 VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )""",
            (
                "e8252f5b-7854-5172-a80a-689b500bf968",
                "6b5ad593-7a98-509e-8ed4-782bad23cc25",
                "df9c20cf-85fe-529c-902e-2e9e68193fbe",
                "cde63628-5b31-44e7-ba7f-0eb452519b57",
                "fb42c33b-d2a5-5ccc-b4fe-80571534a617",
                "06e47750-85ee-5fed-afb6-84ea93eaf06c",
                "chunk",
                "69e14ccf382f744346d617d85f9cfc6a66a17a4ae06614e4acfbd31a3ece53cb",
                lang_payload,
                "b60ba9c6a9b6ae4d5c8efd78eef145aef83dddd6beadab5e22e06c4b94fcbdff",
                "2026-08-28T18:07:35.154938+00:00",
            ),
        )

        # script_observations_v1
        cur.execute(
            """CREATE TABLE script_observations_v1 (
                observation_id TEXT PRIMARY KEY,
                actor_id TEXT NOT NULL,
                notebook_id TEXT NOT NULL,
                source_id TEXT,
                document_id TEXT,
                version_id TEXT,
                target_scope TEXT NOT NULL,
                target_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        script_payload = zlib.decompress(
            base64.b64decode(
                b"eJytVtuK40YQ/Rexb5k2fb/4LQyBQAYWsmFeQjB9qbaVkSWji8mwzL+n2rI8Yy+Ezc682Gqpq87"
                b"pU3VK+lp14W+I41Ctv1as/OQamnRa+jh2/aZO5frTNJWLSgflk3KCGO8sUdQBsZAkMZYHn7iIka"
                b"vq5a6KXZvr7dT7se7aTaq3MIwY7myKlOfMvbDRSWWBGRpkFJlHXFPLUtSZGaMN9ZCSocl7xcFnJ"
                b"VmWrMLMPfgR0saPJ14JF2O9B0zOKdeEWsLtH8yuqVkLtWJKOmF/onRNaeGVYIRyLNy+UIREpraO"
                b"XQIyxL4+jGTZRI4FcFltejjWAx4HY5cAZlZ0Red9u+dDN+5ggJN4n8bp0CCrP/Gyh1zoVS9/IYO"
                b"6PUzjZueHHd4Dm5SQAWULyD4Fp1VwIJTgSirKmeIot0g8g7LcSJ2ko9p5H2m2ThuJsPv6H1RjZl"
                b"6ts28GuKvaboTQdU831UvZRU5jJlZlIIq7SBzlQDg40JY5kQMUlbowQH+ca3edgYmMJLDgSdlAF"
                b"POO2KQ1CdFiVyimU0glw9BNfQSULEMPbYRTjlmHU3+Mvt/CuJl7ygGTMWZheTZSCjymZiYhRxdz"
                b"1F5rz4yXHqjWTIL0MYckmBcQQYkYqku6IXaHGQraaY+p9y3su9UeS9UMq/3UjHVTt9vJN+sHX/6"
                b"38Pn1qF9O0XfV0TdT6ae4m9qn6gXZPtXtST4/+tj4YSiIzwXpPwC+nCryJv0jKwfnNx6bxl3X1+"
                b"PzZk78XdzfJP15ib8/81rIb7sj9C12xqXjF1emm3rI8gRb+3T/1apZK5dAC+tUCBxdGJjhyZtsI"
                b"3CjjLNF+0CtNy5gVzHqFVU8ZMiGmViEXJryAiXeqeavZ4vVwyymuBZzOfuDH9vqXUD3+KRkkNcA"
                b"0Td16Mv4uTjtjMlW9AcBl0a8f60NZlI3wKUVP8wtCfr6jbvbqWnwZhenPbTjjeFzkDwKEUjiXhE"
                b"VYyRB4vCwVBmGs8sj+FUDfRTJWcv/Y+VfzhR+w8hH8dbIvu1wYPtmc7b0XYWxgCEb9M62br8PZ8"
                b"n/MMd+PoVeAbUo6hE2R1Eg3juDY5z6/iLpXKSD70uJLmJf5uvFt/O+8/hFv49l/8e9bc6Jt9BCf"
                b"9tB52fXx41lhmiO3wpBMCIlGBJwiBAKQSIec0Gd+gen1fDt64ZqkMYoimIBipXxXe1z0MRK8E7g"
                b"ZwHV8Ydnym3f/L6I+TjPqYN/bjqf3syv09AZ4g72fnMmjNZ/+RekuANN"
            )
        ).decode("utf-8")
        cur.execute(
            """INSERT INTO script_observations_v1 VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )""",
            (
                "13f6d4d4-d58b-51a9-8d66-bc8593516dbd",
                "6b5ad593-7a98-509e-8ed4-782bad23cc25",
                "df9c20cf-85fe-529c-902e-2e9e68193fbe",
                "cde63628-5b31-44e7-ba7f-0eb452519b57",
                "fb42c33b-d2a5-5ccc-b4fe-80571534a617",
                "06e47750-85ee-5fed-afb6-84ea93eaf06c",
                "chunk",
                "69e14ccf382f744346d617d85f9cfc6a66a17a4ae06614e4acfbd31a3ece53cb",
                script_payload,
                "2318bd7bec136982acc1396fd51eb1878070f5ff215b2235547f0ff60049fcee",
                "2026-08-28T18:07:35.154938+00:00",
            ),
        )

        conn.commit()
    finally:
        conn.close()
