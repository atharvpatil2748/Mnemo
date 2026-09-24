"""Run the non-activating, identity-bound Phase 8.5 production BGE evaluation."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import platform
import sqlite3
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from mnemo.engine import KnowledgeEngine
from mnemo.models.advanced_retrieval import AdvancedRetrievalMode, EvidenceRepresentation
from mnemo.models.multilingual import LanguageCode
from mnemo.retrieval.multilingual_providers import (
    BGE_RERANKER_MODEL,
    BGE_RERANKER_PAIR_TOKENS,
    BGE_RERANKER_PRODUCTION_EXECUTION_V1,
    BGE_RERANKER_REVISION,
)
from mnemo_server.config import ServerConfig
from mnemo_server.evaluation.production_parity_bge import (
    ProductionParityBGEEvaluationLeaseV1,
)
from mnemo_server.runtime_config import resolve_mnemo_runtime_config
from mnemo_server.schemas.retrieval_v2 import EvidenceScopeRequest, EvidenceSearchRequest
from mnemo_server.services.authorization import principal_from_claims
from mnemo_server.services.durable_reranker_activation import (
    restore_production_reranker_activation,
)
from mnemo_server.services.full_multilingual_v2_startup import (
    IDENTITY_MANIFEST,
    install_production_full_multilingual_v2,
)
from mnemo_server.services.pre_certification_observation import (
    resolve_pre_certification_observation,
)
from mnemo_server.services.production_store_readiness import (
    ProductionV2ReadinessEvidenceBuilderV1,
)
from mnemo_server.services.retrieval_v2 import (
    EvidenceRetrievalApplicationService,
    build_retrieval_cursor_codec,
)
from mnemo_server.services.v2_reranker_lifecycle import V2RerankerMode

ROOT = Path(__file__).resolve().parents[1]
QUERY_SET = ROOT / "scratch/phase8_5_identity_bound_queries.json"
CENSUS = ROOT / (
    "docs/governance/proposals/phase8_5_full_multilingual_architecture/"
    "V2_CORPUS_REPRESENTATION_CENSUS.json"
)


def _output_path(environment_name: str, default_name: str) -> Path:
    configured = os.environ.get(environment_name)
    return Path(configured).resolve() if configured else ROOT / "scratch" / default_name


MAPPING_OUTPUT = _output_path(
    "MNEMO_CERT_MAPPING_OUTPUT", "mnemo-v2-production-parity-query-mapping.json"
)
RESULT_OUTPUT = _output_path(
    "MNEMO_CERT_RESULT_OUTPUT", "mnemo-v2-production-parity-bge-evaluation.json"
)
PER_QUERY_OUTPUT = _output_path(
    "MNEMO_CERT_PER_QUERY_OUTPUT", "mnemo-v2-production-parity-bge-evaluation-per-query.json"
)
CHECKPOINT_OUTPUT = _output_path(
    "MNEMO_CERT_CHECKPOINT_OUTPUT",
    "mnemo-v2-production-parity-bge-evaluation-checkpoint.json",
)
EXPECTED_DATABASE_SHA256 = "3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c"
PAIR_POLICY = "bge-reranker-v2-m3-pair-256-contextual-v1"
INTERNAL_K = 50
REQUESTED_K_VALUES = (1, 5, 10, 25, 50)
DYNAMIC_K_PROBE_QUERY = "What does the Bhagavad Gita teach about duty and action?"


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def write_json(path: Path, value: object) -> None:
    encoded = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if os.environ.get("MNEMO_WP17_STAGED_REHEARSAL") == "1" and path in {
        MAPPING_OUTPUT,
        RESULT_OUTPUT,
        PER_QUERY_OUTPUT,
    }:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            stream.write(encoded)
        return
    path.write_text(encoded, encoding="utf-8")


def database_state(path: Path) -> dict[str, Any]:
    wal = path.with_name(path.name + "-wal")
    shm = path.with_name(path.name + "-shm")
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro&immutable=1", uri=True)
    try:
        counts = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("documents", "document_versions", "sources", "chunks")
        }
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign_keys = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        notebook_rows = connection.execute("SELECT notebook_id FROM notebooks").fetchall()
    finally:
        connection.close()
    if len(notebook_rows) != 1:
        raise RuntimeError("PRODUCTION_PARITY_QUERY_MAPPING_INVALID")
    return {
        "path": path.as_posix(),
        "sha256": digest_file(path),
        "size_bytes": path.stat().st_size,
        "wal_bytes": wal.stat().st_size if wal.exists() else 0,
        "shm_bytes": shm.stat().st_size if shm.exists() else 0,
        "counts": counts,
        "integrity_check": integrity,
        "foreign_key_violations": foreign_keys,
        "notebook_id": str(notebook_rows[0][0]),
    }


def build_identity_mapping(database: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    queries = json.loads(QUERY_SET.read_text(encoding="utf-8"))
    census = json.loads(CENSUS.read_text(encoding="utf-8"))
    files_by_name: dict[str, list[dict[str, Any]]] = {}
    for item in census["corpus_files"]:
        files_by_name.setdefault(str(item["name"]), []).append(item)
    documents_by_hash: dict[str, list[dict[str, Any]]] = {}
    for item in census["documents"]:
        documents_by_hash.setdefault(str(item["corpus_file_hash"]), []).append(item)
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro&immutable=1", uri=True)
    rows: list[dict[str, Any]] = []
    ambiguous: list[str] = []
    unresolved: list[str] = []
    try:
        for query in queries:
            qid = str(query["qid"])
            matches = files_by_name.get(str(query["target_file"]), [])
            if len(matches) != 1:
                (ambiguous if len(matches) > 1 else unresolved).append(qid)
                continue
            manifest_item = matches[0]
            identity_matches = documents_by_hash.get(str(manifest_item["sha256"]), [])
            if len(identity_matches) != 1:
                (ambiguous if len(identity_matches) > 1 else unresolved).append(qid)
                continue
            identity = identity_matches[0]
            document_id = str(identity["document_id"])
            version_id = str(identity["version_id"])
            source_ids = tuple(str(item) for item in identity["source_ids"])
            db_identity = connection.execute(
                """SELECT d.document_id,v.version_id,v.content_hash
                   FROM documents d JOIN document_versions v
                     ON v.version_id=d.current_version_id
                   WHERE d.document_id=? AND v.version_id=?""",
                (document_id, version_id),
            ).fetchall()
            source_rows = connection.execute(
                "SELECT source_id FROM sources WHERE document_id=? ORDER BY source_id",
                (document_id,),
            ).fetchall()
            chunks = tuple(
                str(item[0])
                for item in connection.execute(
                    "SELECT id FROM chunks WHERE document_id=? AND version_id=? ORDER BY id",
                    (document_id, version_id),
                ).fetchall()
            )
            golden = ROOT / "goldenDataset/Phase 8.5 Evaluation Corpus" / str(query["target_file"])
            valid = (
                len(db_identity) == 1
                and str(db_identity[0][2]) == str(manifest_item["sha256"])
                and tuple(str(item[0]) for item in source_rows) == tuple(sorted(source_ids))
                and golden.is_file()
                and digest_file(golden) == str(manifest_item["sha256"])
                and bool(chunks)
            )
            if not valid:
                unresolved.append(qid)
                continue
            rows.append(
                {
                    **query,
                    "manifest_source_identity": str(manifest_item["sha256"]),
                    "document_id": document_id,
                    "version_id": version_id,
                    "source_ids": list(source_ids),
                    "relevant_chunk_count": len(chunks),
                    "example_relevant_chunk_ids": list(chunks[:3]),
                    "mapping_status": "RESOLVED",
                }
            )
    finally:
        connection.close()
    summary = {
        "schema_version": "mnemo.production-parity-query-mapping/1",
        "query_set": QUERY_SET.relative_to(ROOT).as_posix(),
        "query_set_sha256": digest_file(QUERY_SET),
        "census": CENSUS.relative_to(ROOT).as_posix(),
        "census_sha256": digest_file(CENSUS),
        "total": len(queries),
        "resolved": len(rows),
        "ambiguous": len(ambiguous),
        "unresolved": len(unresolved),
        "ambiguous_qids": ambiguous,
        "unresolved_qids": unresolved,
        "relevance_unit": "canonical document/version identity; every matching chunk is relevant",
        "rows": rows,
    }
    return rows, summary


def metric_summary(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    ranks = [row["target_rank"] for row in rows]
    n = len(ranks)
    reciprocal = [0.0 if rank is None else 1.0 / int(rank) for rank in ranks]
    ndcg = [
        0.0 if rank is None or int(rank) > 10 else 1.0 / math.log2(int(rank) + 1) for rank in ranks
    ]
    return {
        "n": n,
        "recall_at_1": sum(rank == 1 for rank in ranks) / n,
        "recall_at_5": sum(rank is not None and rank <= 5 for rank in ranks) / n,
        "recall_at_10": sum(rank is not None and rank <= 10 for rank in ranks) / n,
        "mrr": sum(reciprocal) / n,
        "ndcg_at_10": sum(ndcg) / n,
    }


async def execute() -> dict[str, Any]:
    started = time.perf_counter()
    staged = os.environ.get("MNEMO_WP17_STAGED_REHEARSAL") == "1"
    configured_model_cache = os.environ.get("MNEMO_SERVER_FULL_MULTILINGUAL_V2_MODEL_CACHE")
    if not configured_model_cache:
        raise RuntimeError("WP17_REHEARSAL_MODEL_CACHE_MISSING")
    model_cache = Path(configured_model_cache).resolve(strict=True)
    if staged and (
        not all(
            os.environ.get(name)
            for name in (
                "MNEMO_CERT_MAPPING_OUTPUT",
                "MNEMO_CERT_RESULT_OUTPUT",
                "MNEMO_CERT_PER_QUERY_OUTPUT",
                "MNEMO_CERT_CHECKPOINT_OUTPUT",
            )
        )
        or any(path.exists() for path in (MAPPING_OUTPUT, RESULT_OUTPUT, PER_QUERY_OUTPUT))
    ):
        raise RuntimeError("WP17_REHEARSAL_OUTPUTS_MUST_BE_NEW")
    torch = __import__("torch")
    if not torch.cuda.is_available():
        raise RuntimeError("BGE_CUDA_UNAVAILABLE")
    config = resolve_mnemo_runtime_config(config_path=ROOT / "mnemo.toml")
    database = config.storage.sqlite.path.resolve()
    before = database_state(database)
    if before["sha256"] != EXPECTED_DATABASE_SHA256:
        raise RuntimeError("PRODUCTION_STORE_CONFIGURATION_MISMATCH")
    mapping_rows, mapping = build_identity_mapping(database)
    write_json(MAPPING_OUTPUT, mapping)
    if mapping["resolved"] != mapping["total"] or mapping["ambiguous"] or mapping["unresolved"]:
        raise RuntimeError("PRODUCTION_PARITY_QUERY_MAPPING_INVALID")

    server = (
        ServerConfig.from_env(certified_production=True, pre_certification_observation=True)
        if staged
        else ServerConfig(
            production_mode=True,
            auth_mode="api-key",
            api_key=os.environ.get("MNEMO_SERVER_API_KEY"),
            delivery_cursor_secret=os.environ.get("MNEMO_SERVER_DELIVERY_CURSOR_SECRET"),
            full_multilingual_v2_enabled=True,
            full_multilingual_v2_reranker_mode="PASS_THROUGH",
            full_multilingual_v2_model_cache=model_cache,
            final_qa_operational_store_path=(
                ROOT / "scratch/phase8_5_full_multilingual_v2/operational/final_qa_v2.db"
            ),
            mcp_stdio_principal_subject="mnemo-production-stdio",
            production_rerank_candidate_limit=INTERNAL_K,
            max_advanced_elapsed_milliseconds=30_000,
        )
    )
    observation_identity = None
    if staged:
        _, observation_identity, _ = resolve_pre_certification_observation(
            server_config=server, root=ROOT, mnemo_config=config
        )
        if server.full_multilingual_v2_model_cache != model_cache:
            raise RuntimeError("WP17_REHEARSAL_MODEL_CACHE_MISMATCH")
    engine = KnowledgeEngine(
        config,
        advanced_retrieval_cursor_codec=build_retrieval_cursor_codec(server),
        certified_read_only=staged,
    )
    installed = None
    lease = None
    per_query: list[dict[str, Any]] = []
    dynamic_k: list[dict[str, Any]] = []
    checkpoint: dict[str, Any] = {
        "schema_version": "mnemo.production-parity-bge-checkpoint/1",
        "status": "INCOMPLETE",
        "completed_qids": [],
        "records": [],
    }
    write_json(CHECKPOINT_OUTPUT, checkpoint)
    await engine.initialize()
    try:
        readiness_evidence, readiness = await ProductionV2ReadinessEvidenceBuilderV1(
            workspace_root=ROOT,
            mnemo_config=config,
            server_config=server,
            identity_manifest=ROOT / IDENTITY_MANIFEST,
            pre_certification_observation=staged,
        ).build()
        installed = await install_production_full_multilingual_v2(
            engine=engine,
            production_config=config,
            workspace_root=ROOT,
            model_cache=model_cache,
            readiness=readiness,
        )
        if staged:
            await restore_production_reranker_activation(
                installed=installed,
                config=server,
                workspace_root=ROOT,
                production_store_path=database,
            )
        expected_mode = V2RerankerMode.BGE_V2_M3 if staged else V2RerankerMode.PASS_THROUGH
        if installed.reranker.mode is not expected_mode:
            raise RuntimeError("PRODUCTION_EVALUATION_RERANKER_MODE_MISMATCH")
        principal = principal_from_claims({"sub": "mnemo-production-parity-evaluator"})
        notebook_id = UUID(str(before["notebook_id"]))
        service = EvidenceRetrievalApplicationService(engine, server)
        for requested_k in REQUESTED_K_VALUES:
            response = await service.execute(
                EvidenceSearchRequest(
                    query=DYNAMIC_K_PROBE_QUERY,
                    mode=AdvancedRetrievalMode.RANKED,
                    scope=EvidenceScopeRequest(notebook_id=notebook_id),
                    representations=(EvidenceRepresentation.MULTILINGUAL_TEXT,),
                    candidate_budget=INTERNAL_K,
                    evidence_budget=requested_k,
                ),
                principal,
            )
            dynamic_k.append(
                {
                    "requested_k": requested_k,
                    "returned": len(response.items),
                    "internal_reranker_candidate_pool_k": response.limits[
                        "internal_reranker_candidate_pool_k"
                    ],
                    "accepted": len(response.items) == requested_k,
                }
            )
        if not all(
            row["accepted"] and row["internal_reranker_candidate_pool_k"] == INTERNAL_K
            for row in dynamic_k
        ):
            raise RuntimeError("PRODUCTION_PARITY_CANDIDATE_MISMATCH")

        torch.cuda.reset_peak_memory_stats()
        lease = await ProductionParityBGEEvaluationLeaseV1.open(
            engine=engine,
            installed=installed,
            workspace_root=ROOT,
            model_cache=model_cache,
            pre_certification_observation=staged,
        )
        if lease.reranker.execution_profile != BGE_RERANKER_PRODUCTION_EXECUTION_V1:
            raise RuntimeError("BGE_CPU_FALLBACK_DETECTED")
        for index, mapping_row in enumerate(mapping_rows, 1):
            request = EvidenceSearchRequest(
                query=str(mapping_row["query"]),
                mode=AdvancedRetrievalMode.RANKED,
                scope=EvidenceScopeRequest(notebook_id=notebook_id),
                representations=(EvidenceRepresentation.MULTILINGUAL_TEXT,),
                candidate_budget=INTERNAL_K,
                evidence_budget=INTERNAL_K,
            )
            plan = request.to_plan(
                max_candidate_budget=server.max_advanced_candidate_budget,
                max_evidence_budget=server.max_advanced_evidence_budget,
                max_response_bytes=server.max_advanced_response_bytes,
                max_content_characters=server.max_advanced_content_characters,
                max_rerank_candidates=server.production_rerank_candidate_limit,
                production_candidate_pool_k=server.production_rerank_candidate_limit,
            )
            query_started = time.perf_counter()
            result = await lease.runtime.application.retrieve(
                principal=principal,
                plan=plan,
                query_language=LanguageCode(str(mapping_row["query_language"])),
            )
            if result.omissions or result.reranked_count != INTERNAL_K:
                raise RuntimeError("PRODUCTION_PARITY_CANDIDATE_MISMATCH")
            provider_order = tuple(
                sorted(
                    (item.candidate for item in result.candidates),
                    key=lambda item: item.input_ordinal,
                )
            )
            if tuple(item.input_ordinal for item in provider_order) != tuple(range(INTERNAL_K)):
                raise RuntimeError("PRODUCTION_PARITY_CANDIDATE_MISMATCH")
            observations = await lease.reranker.observe_candidate_inputs(
                query=plan.query, candidates=provider_order
            )
            if (
                len(observations) != INTERNAL_K
                or tuple(item.candidate_id for item in observations)
                != tuple(item.candidate_id for item in provider_order)
                or any(
                    item.retained_token_count > BGE_RERANKER_PAIR_TOKENS for item in observations
                )
            ):
                raise RuntimeError("RERANKER_PAIR_POLICY_MISMATCH")
            target_rank = next(
                (
                    item.final_rank
                    for item in result.candidates
                    if str(item.candidate.source_reference.document_id)
                    == mapping_row["document_id"]
                    and str(item.candidate.source_reference.version_id) == mapping_row["version_id"]
                ),
                None,
            )
            record = {
                "qid": mapping_row["qid"],
                "query": mapping_row["query"],
                "direction": mapping_row["direction"],
                "format": mapping_row["format"],
                "target": {
                    "manifest_source_identity": mapping_row["manifest_source_identity"],
                    "document_id": mapping_row["document_id"],
                    "version_id": mapping_row["version_id"],
                },
                "target_rank": target_rank,
                "target_in_candidate_pool": target_rank is not None,
                "candidate_pool_digest": canonical_digest(
                    [
                        {
                            "candidate_id": str(item.candidate_id),
                            "document_id": str(item.source_reference.document_id),
                            "version_id": str(item.source_reference.version_id),
                            "chunk_id": item.source_reference.evidence_id,
                            "input_ordinal": item.input_ordinal,
                            "semantic_text_hash": item.semantic_text_hash,
                            "contextual_text_hash": item.input_audit.contextual_text_hash,
                        }
                        for item in provider_order
                    ]
                ),
                "candidate_pool": [
                    {
                        "candidate_id": str(item.candidate_id),
                        "document_id": str(item.source_reference.document_id),
                        "version_id": str(item.source_reference.version_id),
                        "source_id": str(item.source_reference.source_id),
                        "chunk_id": item.source_reference.evidence_id,
                        "input_ordinal": item.input_ordinal,
                        "semantic_text_hash": item.semantic_text_hash,
                        "contextual_text_hash": item.input_audit.contextual_text_hash,
                        "title": item.title_metadata,
                        "heading_path": list(item.heading_path),
                    }
                    for item in provider_order
                ],
                "reranked": [
                    {
                        "rank": item.final_rank,
                        "candidate_id": str(item.candidate.candidate_id),
                        "document_id": str(item.candidate.source_reference.document_id),
                        "version_id": str(item.candidate.source_reference.version_id),
                        "chunk_id": item.candidate.source_reference.evidence_id,
                        "score": item.reranker_score,
                    }
                    for item in result.candidates
                ],
                "pair_audit": [
                    {**asdict(item), "candidate_id": str(item.candidate_id)}
                    for item in observations
                ],
                "elapsed_seconds": time.perf_counter() - query_started,
            }
            per_query.append(record)
            checkpoint["completed_qids"] = [item["qid"] for item in per_query]
            checkpoint["records"] = per_query
            write_json(CHECKPOINT_OUTPUT, checkpoint)
            print(
                f"[{index:02d}/{len(mapping_rows)}] {mapping_row['qid']} "
                f"target_rank={target_rank} seconds={record['elapsed_seconds']:.2f}",
                flush=True,
            )
        checkpoint["status"] = "COMPLETE"
        write_json(CHECKPOINT_OUTPUT, checkpoint)
        if installed.reranker.mode is not expected_mode:
            raise RuntimeError("PRODUCTION_EVALUATION_MUTATED_ACTIVE_ROUTER")
        readiness_payload = readiness_evidence.payload()
    finally:
        if lease is not None:
            await lease.close()
        if installed is not None:
            await installed.close()
        await engine.shutdown()

    after = database_state(database)
    if before != after or after["sha256"] != EXPECTED_DATABASE_SHA256:
        raise RuntimeError("PRODUCTION_STATE_MUTATION")
    metrics = metric_summary(per_query)
    if staged:
        thresholds = json.loads(
            (ROOT / "scratch/mnemo-v2-threshold-certification.json").read_text(encoding="utf-8")
        )
        if any(
            float(metrics.get(name, -1)) < float(thresholds.get("floors", {}).get(name, 2))
            for name in ("recall_at_1", "recall_at_5", "recall_at_10", "mrr", "ndcg_at_10")
        ):
            raise RuntimeError("WP17_REHEARSAL_EVALUATION_THRESHOLD_FAILED")
    result = {
        "schema_version": "mnemo.v2-production-parity-bge-evaluation/1",
        "status": "PRODUCTION_PARITY_EVALUATION_PASS",
        "generated_at": datetime.now(UTC).isoformat(),
        "production_store": {
            "governed_identity": readiness_payload["production_store"][
                "governed_database_identity"
            ],
            "before": before,
            "after": after,
            "byte_identical": before == after,
        },
        "store_parity": readiness_payload["component_store_identities"],
        "evaluation_database_excluded": readiness_payload[
            "prohibited_database_absent_from_production_bindings"
        ],
        "query_mapping": {key: value for key, value in mapping.items() if key != "rows"},
        "candidate_protocol": {
            "application_service_id": lease.runtime.application.application_service_id
            if lease is not None
            else "closed-production-runtime",
            "candidate_builder_id": lease.runtime.parity.candidate_builder_id
            if lease is not None
            else "mnemo.v2-typed-candidate-builder/1",
            "retrieval_candidate_k": INTERNAL_K,
            "reranker_candidate_k": INTERNAL_K,
            "rrf_k": 60,
            "candidate_parity": "PASS",
        },
        "dynamic_k": dynamic_k,
        "reranker": {
            "model": BGE_RERANKER_MODEL,
            "revision": BGE_RERANKER_REVISION,
            "pair_policy_id": PAIR_POLICY,
            "maximum_pair_tokens": BGE_RERANKER_PAIR_TOKENS,
            "query_max_content_tokens": 96,
            "query_representation": "NFKC + bounded whitespace",
            "candidate_representation": "[title | heading_path] + authorized semantic text",
            "truncation": "deterministic retain-head; unused query budget assigned to document",
            "device": "cuda",
            "batch_size": 2,
            "cpu_fallback": False,
        },
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(0),
            "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
            "oom_retries": 0,
            "elapsed_seconds": time.perf_counter() - started,
        },
        "metrics": metrics,
        "candidate_coverage": {
            "k50": sum(row["target_in_candidate_pool"] for row in per_query),
            "total": len(per_query),
        },
        "baseline": {
            "status": "BASELINE_NOT_IDENTITY_EQUIVALENT",
            "reason": (
                "historical ms-marco Golden A/B used the 67-document canonical "
                "database and a different candidate protocol"
            ),
        },
        "bge_active_after_evaluation": staged,
        "serving_reranker_mode_after_evaluation": ("BGE_V2_M3" if staged else "PASS_THROUGH"),
        "lifecycle": {
            "DECLARED": True,
            "IMPLEMENTED": True,
            "CONFIGURED": True,
            "BUILDABLE": True,
            "READY": True,
            "ACTIVE": not staged,
            "EXPOSED": not staged,
            "EVALUATED": False,
            "VERIFIED": False,
            "CERTIFIED": False,
        },
        "artifacts": {
            "mapping": MAPPING_OUTPUT.relative_to(ROOT).as_posix(),
            "per_query": PER_QUERY_OUTPUT.relative_to(ROOT).as_posix(),
            "checkpoint": CHECKPOINT_OUTPUT.relative_to(ROOT).as_posix(),
        },
        "blockers": [],
    }
    if staged and observation_identity is not None:
        result["credential_generation_id"] = observation_identity.credential_generation_id
        result["activation_state_sha256"] = observation_identity.activation_sha256
        result["semantic_runtime_identity"] = asdict(observation_identity)
        result["scope"] = "ISOLATED_WP17_REHEARSAL"
        result["global_generation_active"] = False
        result["public_production_exposed"] = False
    write_json(PER_QUERY_OUTPUT, per_query)
    write_json(RESULT_OUTPUT, result)
    return result


def main() -> None:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    try:
        result = asyncio.run(execute())
    except BaseException as error:
        failure = {
            "schema_version": "mnemo.v2-production-parity-bge-evaluation/1",
            "status": "PRODUCTION_PARITY_EVALUATION_BLOCKED",
            "failure_code": str(error),
            "failure_type": type(error).__name__,
            "generated_at": datetime.now(UTC).isoformat(),
            "bge_activated": False,
        }
        write_json(RESULT_OUTPUT, failure)
        raise
    print(json.dumps({"status": result["status"], "metrics": result["metrics"]}))


if __name__ == "__main__":
    main()
