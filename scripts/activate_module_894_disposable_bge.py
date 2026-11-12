"""Activate a fully verified Full V2 alias only in eval-20261106-04.

This experiment uses the existing atomic alias-set storage transition. It does
not assert that this copied evaluation snapshot is a governed production build.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import sqlite3
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from mnemo.phase85.v2_activation_authorization import first_v2_deactivation_recovery_digest
from mnemo.retrieval.final_qa_snapshot import _decode
from mnemo.storage.sqlite import SQLiteStore
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "scratch/module_894_disposable/eval-20261106-04"
ACTOR = UUID("7ee69849-d87e-57d1-b2ef-29128d668a5e")
NOTEBOOK = UUID("df9c20cf-85fe-529c-902e-2e9e68193fbe")
TARGET_CHUNK = "523c5c88b522ce818212ffc42241706b731a767bb4dc5045ffa1a99e3392a0ca"
CAPABILITIES = (
    "representation_derivation_v2",
    "language_text_v2",
    "multilingual_embedding_v2",
    "multilingual_vector_v2",
)


async def run() -> dict[str, object]:
    if RUNTIME.resolve(strict=True) != RUNTIME or RUNTIME.is_symlink():
        raise ValueError("unexpected evaluation path")
    if (
        json.loads((ROOT / "config/production/runtime-selection.json").read_text())["state"]
        != "UNINDEXED"
    ):
        raise ValueError("production selector changed")
    build = json.loads((RUNTIME / "bge-build-result.json").read_text(encoding="utf-8"))
    census = json.loads((RUNTIME / "bge-prebuild-census.json").read_text(encoding="utf-8"))
    if build["active"] or build["embedding_count"] != build["items"]:
        raise ValueError("Full V2 build was incomplete or already active")
    if build["source_version_count"] != census["source_version_count"] != 44:
        raise ValueError("source-version census changed")
    if (
        sorted(build["no_searchable_evidence_version_ids"])
        != census["no_searchable_evidence_version_ids"]
    ):
        raise ValueError("no-evidence version record changed")
    if not SQLiteNotebookScopeAuthority(RUNTIME / "acl.db").permits(
        ACTOR, NOTEBOOK, operation="write"
    ):
        raise PermissionError("disposable owner grant is missing")
    database = RUNTIME / "mnemo.db"
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT g.capability,g.generation_id,g.state,g.item_count,g.model_identity,"
            "g.dimensions,c.completeness,c.failed_count,m.profile_fingerprint "
            "FROM index_generations g JOIN index_generation_coverage c USING(generation_id) "
            "JOIN multilingual_coverage_manifests_v2 m USING(generation_id) "
            "WHERE g.capability IN (?,?,?,?) ORDER BY CASE g.capability "
            "WHEN 'representation_derivation_v2' THEN 1 "
            "WHEN 'language_text_v2' THEN 2 "
            "WHEN 'multilingual_embedding_v2' THEN 3 ELSE 4 END",
            CAPABILITIES,
        ).fetchall()
        if len(rows) != 4 or tuple(row[0] for row in rows) != CAPABILITIES:
            raise ValueError("Full V2 generation set is incomplete")
        for row in rows:
            (
                capability,
                generation_id,
                state,
                count,
                model,
                dimensions,
                completeness,
                failures,
                fingerprint,
            ) = row
            expected_versions = set(census["embedding_eligible_version_ids"]) | set(
                census["no_searchable_evidence_version_ids"]
            )
            actual_versions = {
                value[0]
                for value in connection.execute(
                    "SELECT source_id FROM index_generation_sources "
                    "WHERE generation_id=? AND source_kind='version'",
                    (generation_id,),
                )
            }
            if (
                generation_id != build["generations"][capability]
                or state != "ready"
                or count != build["items"]
                or completeness != "complete"
                or failures != 0
                or fingerprint != build["profile_fingerprint"]
                or actual_versions != expected_versions
            ):
                raise ValueError(f"{capability} lacks exact complete coverage")
            if capability in CAPABILITIES[2:] and (
                model != "BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181"
                or dimensions != 1024
            ):
                raise ValueError("BGE-M3 model revision or dimension mismatch")
        spaces = connection.execute(
            "SELECT DISTINCT vector_space FROM multilingual_embeddings_v2 WHERE generation_id=?",
            (build["generations"]["multilingual_embedding_v2"],),
        ).fetchall()
        if spaces != [(build["vector_space"],)]:
            raise ValueError("document vector space differs from verified query profile")
        norms: list[float] = []
        target_embeddings = 0
        for source_id, document_id, version_id, notebook_id, payload in connection.execute(
            "SELECT source_id,document_id,version_id,notebook_id,payload "
            "FROM multilingual_embeddings_v2 WHERE generation_id=?",
            (build["generations"]["multilingual_embedding_v2"],),
        ):
            embedding = _decode(str(payload))
            source = embedding.source
            profile = embedding.profile
            if (
                source.source_id != UUID(source_id)
                or source.document_id != UUID(document_id)
                or source.version_id != UUID(version_id)
                or source.notebook_id != UUID(notebook_id)
                or profile.vector_space != build["vector_space"]
                or profile.dimension != 1024
                or profile.distance_metric != "cosine"
                or not profile.normalized
                or profile.revision != build["prebuild_census"]["model_revision"]
            ):
                raise ValueError("embedding vector or ancestry is incompatible")
            norm = math.sqrt(sum(value * value for value in embedding.vector))
            if abs(norm - 1.0) > 0.001:
                raise ValueError("BGE document vector is not L2-normalized")
            norms.append(norm)
            if source.chunk_id == TARGET_CHUNK:
                target_embeddings += 1
        if len(norms) != build["items"] or target_embeddings != 1:
            raise ValueError("embedding count or frozen target coverage differs")
        if connection.execute("SELECT COUNT(*) FROM active_multilingual_v2_alias_set").fetchone()[
            0
        ]:
            raise ValueError("evaluation alias already active")
    finally:
        connection.close()
    authorization = {
        "schema": "mnemo.module-894-disposable-alias-authorization/1",
        "basis": "project-owner request: Build and Validate Disposable BGE-M3 Full V2 Generation",
        "runtime": str(RUNTIME),
        "notebook_id": str(NOTEBOOK),
        "actor_id": str(ACTOR),
        "generations": [build["generations"][key] for key in CAPABILITIES],
        "profile_fingerprint": build["profile_fingerprint"],
        "vector_space": build["vector_space"],
        "scope": "disposable-evaluation-only",
        "embedding_norm_min": min(norms),
        "embedding_norm_max": max(norms),
        "target_embedding_count": target_embeddings,
    }
    authorization_digest = hashlib.sha256(
        json.dumps(authorization, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    authorization_id = uuid5(NAMESPACE_URL, authorization_digest)
    (RUNTIME / "bge-disposable-activation-authorization.json").open("x", encoding="utf-8").write(
        json.dumps(authorization, indent=2, sort_keys=True) + "\n"
    )
    store = SQLiteStore(database)
    await store.open()
    try:
        alias = await store.promote_multilingual_v2_alias_set(
            profile_fingerprint=build["profile_fingerprint"],
            generation_ids=tuple(UUID(build["generations"][key]) for key in CAPABILITIES),
            rollback_alias_set_digest=first_v2_deactivation_recovery_digest(
                profile_fingerprint=build["profile_fingerprint"]
            ),
            rollback_generation_ids=(),
            expected_active_alias_set_digest=None,
            activation_mode="first_v2_activation",
            recovery_mode="deactivate_v2_alias_set",
            authorization_id=authorization_id,
            authorization_digest=authorization_digest,
        )
    finally:
        await store.close()
    result = {
        "alias_set_digest": alias,
        "authorization_id": str(authorization_id),
        "authorization_digest": authorization_digest,
        "generation_ids": authorization["generations"],
        "runtime": str(RUNTIME),
        "scope": "disposable-evaluation-only",
    }
    (RUNTIME / "bge-disposable-activation-result.json").open("x", encoding="utf-8").write(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    return result


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), indent=2, sort_keys=True))
