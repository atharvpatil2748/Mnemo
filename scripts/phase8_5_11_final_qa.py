"""Run the fixed 30-question Phase 8.5.11 Final-QA V2 evaluation."""

from __future__ import annotations

import argparse
import asyncio
import base64
import gc
import hashlib
import json
import sqlite3
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx
import numpy as np
from mnemo.models import FrozenMetadata
from mnemo.models.advanced_retrieval import RetrievalCompleteness
from mnemo.models.multimodal import (
    EvidenceAuthorityV2,
    EvidenceCandidateV2,
    EvidenceKindV2,
    EvidenceScoreComponentV2,
    FinalQARequestV2,
    MultimodalContextBudgetsV1,
    MultimodalGenerationRequestV1,
    MultimodalGenerationResultV1,
    MultimodalProviderCapabilitiesV1,
    MultimodalRetrievalDiagnosticsV2,
    MultimodalRetrievalResultV2,
    ProviderModalityState,
    evidence_candidate_v2_digest,
    evidence_candidate_v2_id,
)
from mnemo.retrieval.multimodal import FinalQAV2Orchestrator, MultimodalContextBuilder
from mnemo.storage.filesystem import FilesystemBlobStore
from mnemo.storage.sqlite import SQLiteStore
from sentence_transformers import SentenceTransformer

QUESTIONS: tuple[tuple[str, str, str], ...] = (
    (
        "Why did Jumman's old aunt call a village panchayat?",
        "Act 2. panch-parmeshwar-by-munshi-premchand.pdf",
        "text",
    ),
    ("What technical skills are listed in the resume?", "Atharv_Patil_RESUME_SDE.pdf", "text"),
    (
        "Which personal AI operating system project appears in the resume?",
        "Atharv_Patil_RESUME_SDE.pdf",
        "text",
    ),
    (
        "Who authored the Bhagavad-gita edition in this corpus?",
        "Bhagavad-gita As It Is with pics!",
        "text",
    ),
    (
        "What club role does the Coordinator Application describe?",
        "Coordinator Application 2026\N{EN DASH}27",
        "text",
    ),
    (
        "What does the health check-up spreadsheet schedule?",
        "Health Check Up Schedule List Date Vise",
        "structured",
    ),
    ("What current CPI is shown on the IITK transcript?", "IITK", "structured"),
    ("Which modules does InferenceGateway.js import?", "InferenceGateway.js", "code"),
    (
        "What prerequisite knowledge is listed for ME361?",
        "ME361_L1_fbd03201-7db3-4553-a6e5-06f24817f9ea (1)",
        "text",
    ),
    (
        "What equation is used as a measure of part complexity in the ME361 L2-L4 notes?",
        "ME361_L2-L4_08c3b677-872f-4073-8337-83ad44fa8b88.pdf",
        "text",
    ),
    (
        "What system is investigated in the ME333 experiment?",
        "ME333 - Exp2-LabReport_To_Submit.docx",
        "text",
    ),
    (
        "Which students are assigned to group 1 in the Monday ME381 sheet?",
        "ME381 Lab group A1 - Monday",
        "structured",
    ),
    ("Who is ranked first in the Y24 CPI table?", "Y24_CPI.csv", "structured"),
    (
        "Which concepts are highlighted in the SOC 473 lecture notes?",
        "SOC 473: Indian Society, Stratification & Religion | Lecture 1 Notes",
        "text",
    ),
    (
        "What two traditions are compared in the Valmiki Ramayana study?",
        "Valmiki Ramayana aur Ramakien Ek Tulnamatmak Adhyayan.pdf",
        "text",
    ),
    ("Which AI providers are allowed by aiSwitch.js?", "aiSwitch.js", "code"),
    ("Which web framework is used by app.py?", "app.py", "code"),
    ("How does the ARVSAL overview characterize the system?", "arvsal_v3_complete.txt", "text"),
    ("What unsafe claims does llmGuard.js attempt to block?", "llmGuard.js", "code"),
    ("What output format does codePrompt.js require?", "codePrompt.js", "code"),
    ("What language is the manuscript written in?", "manuscript.pdf", "multilingual"),
    (
        "What use cases motivate the AI subscription research document?",
        "research_8b4fd9e3-312a-487b-b035-995a66021bd0.md",
        "text",
    ),
    ("What role does server.js play in the application?", "server.js", "code"),
    ("Which models are warmed by ollamaWarmup.js?", "ollamaWarmup.js", "code"),
    ("What reasoning style does mathPrompt.js request?", "mathPrompt.js", "code"),
    (
        "What visible information is present on the boarding-pass image?",
        "boarding-pass-Atharv-Patil",
        "multimodal",
    ),
    (
        "PHYSICS_JEE_ADVANCED.pdf की स्कैन की गई छवि में कौन सा पाठ दिखता है?",
        "PHYSICS_JEE_ADVANCED.pdf",
        "ocr-hi",
    ),
    (
        "ME333 अहवालातील एम्बेड केलेल्या चित्राचे वर्णन काय आहे?",
        "ME333 - Exp2-LabReport_To_Submit.docx",
        "vision-mr",
    ),
    (
        "या स्वतंत्र IMG_20251006_075844487_HDR_AE प्रतिमेत काय दिसते?",
        "IMG_20251006_075844487_HDR_AE",
        "multimodal-mr",
    ),
    (
        "अथर्व के रिज्यूमे के कौशल बताइए, ME361 पाठ्यक्रम के नहीं।",
        "Atharv_Patil_RESUME_SDE.pdf",
        "cross-language-title",
    ),
)


class EvaluationAuthorizer:
    def __init__(self, database: Path) -> None:
        self.database = database

    async def authorize_evidence(
        self, actor_id: UUID, notebook_id: UUID, candidate: EvidenceCandidateV2
    ) -> bool:
        del actor_id
        connection = sqlite3.connect(f"file:{self.database.as_posix()}?mode=ro", uri=True)
        try:
            scoped = connection.execute(
                "SELECT 1 FROM sources WHERE source_id=? AND notebook_id=? AND document_id=?",
                (str(candidate.source_id), str(notebook_id), str(candidate.document_id)),
            ).fetchone()
            if scoped is None:
                return False
            if candidate.chunk_id is not None:
                return (
                    connection.execute(
                        "SELECT 1 FROM chunks WHERE id=? AND document_id=? AND version_id=?",
                        (candidate.chunk_id, str(candidate.document_id), str(candidate.version_id)),
                    ).fetchone()
                    is not None
                )
            if candidate.occurrence_id is not None:
                return (
                    connection.execute(
                        "SELECT 1 FROM asset_occurrences WHERE occurrence_id=? "
                        "AND document_id=? AND version_id=?",
                        (
                            str(candidate.occurrence_id),
                            str(candidate.document_id),
                            str(candidate.version_id),
                        ),
                    ).fetchone()
                    is not None
                )
            return False
        finally:
            connection.close()

    async def generation_is_active(self, candidate: EvidenceCandidateV2) -> bool:
        if candidate.generation_id is None:
            return True
        connection = sqlite3.connect(f"file:{self.database.as_posix()}?mode=ro", uri=True)
        try:
            for table in ("ocr_results", "vision_results", "visual_embeddings"):
                if (
                    connection.execute(
                        f"SELECT 1 FROM {table} WHERE derivation_id=? AND generation_id=?",
                        (str(candidate.derivation_id), str(candidate.generation_id)),
                    ).fetchone()
                    is not None
                ):
                    return True
            return False
        finally:
            connection.close()


class GemmaFinalQAProvider:
    def __init__(self, database: Path, blobs: FilesystemBlobStore) -> None:
        self.database = database
        self.blobs = blobs
        self.calls = 0
        self.latencies: list[float] = []
        states = {kind.value: ProviderModalityState.SUPPORTED.value for kind in EvidenceKindV2}
        self._capabilities = MultimodalProviderCapabilitiesV1(
            provider="ollama",
            model="gemma4:e4b",
            profile="phase8.5.11-fixed-local/v1",
            configuration_digest=hashlib.sha256(b"gemma4:e4b:phase8.5.11:v1").hexdigest(),
            modality_states=FrozenMetadata(states),
            max_context_tokens=131_072,
            max_output_tokens=1_024,
        )
        self._client = httpx.AsyncClient(base_url="http://127.0.0.1:11434", timeout=180)

    def capabilities(self) -> MultimodalProviderCapabilitiesV1:
        return self._capabilities

    async def complete(
        self, request: MultimodalGenerationRequestV1
    ) -> MultimodalGenerationResultV1:
        images: list[str] = []
        connection = sqlite3.connect(f"file:{self.database.as_posix()}?mode=ro", uri=True)
        try:
            for handle in request.resource_handles[:2]:
                occurrence_id = handle.rsplit("/", 1)[-1]
                row = connection.execute(
                    "SELECT asset_id FROM asset_occurrences WHERE occurrence_id=?",
                    (occurrence_id,),
                ).fetchone()
                if row is None:
                    continue
                raw = await self.blobs.get_asset(UUID(row[0]))
                if raw is not None:
                    images.append(base64.b64encode(raw).decode("ascii"))
        finally:
            connection.close()
        correction = (
            "" if request.corrective_instruction is None else "\n" + request.corrective_instruction
        )
        user = (
            f"QUESTION:\n{request.query}\n\nEVIDENCE:\n{request.rendered_context}{correction}\n\n"
            "Answer only from the evidence. Cite each factual claim with exact [source:N] markers."
        )
        message: dict[str, object] = {"role": "user", "content": user}
        if images:
            message["images"] = images
        payload = {
            "model": "gemma4:e4b",
            "think": False,
            "stream": False,
            "options": {"temperature": 0, "num_predict": request.max_output_tokens},
            "messages": [
                {"role": "system", "content": request.system_prompt},
                message,
            ],
        }
        started = time.perf_counter()
        response = await self._client.post("/api/chat", json=payload)
        response.raise_for_status()
        elapsed = (time.perf_counter() - started) * 1000
        self.calls += 1
        self.latencies.append(elapsed)
        body = response.json()
        answer = str(body["message"]["content"]).strip()
        return MultimodalGenerationResultV1(
            answer=answer,
            provider="ollama",
            model="gemma4:e4b",
            prompt_tokens=int(body.get("prompt_eval_count", 0)),
            answer_tokens=max(1, min(request.max_output_tokens, int(body.get("eval_count", 1)))),
        )

    async def close(self) -> None:
        await self._client.aclose()


class ApproximateTokenCounter:
    @property
    def tokenizer_id(self) -> str:
        return "phase8.5.11:utf8-conservative/v1"

    def count(self, text: str) -> int:
        return max(1, (len(text.encode("utf-8")) + 2) // 3)


def _load_documents(database: Path) -> tuple[list[str], list[str]]:
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT d.document_id,json_extract(v.metadata,'$.title') title,"
            "group_concat(c.text,char(10)) content FROM documents d "
            "JOIN document_versions v ON v.version_id=d.current_version_id "
            "LEFT JOIN chunks c ON c.version_id=v.version_id GROUP BY d.document_id ORDER BY title"
        ).fetchall()
        return [str(row["title"]) for row in rows], [
            f"title: {row['title']}\n{str(row['content'] or '')[:2500]}" for row in rows
        ]
    finally:
        connection.close()


def _rank_documents(database: Path, model_path: Path) -> list[list[tuple[str, float]]]:
    titles, texts = _load_documents(database)
    model = SentenceTransformer(str(model_path), device="cpu", trust_remote_code=True)
    document_vectors = model.encode(
        texts, batch_size=4, normalize_embeddings=True, convert_to_numpy=True
    )
    rankings: list[list[tuple[str, float]]] = []
    for query, _, _ in QUESTIONS:
        vector = model.encode([query], normalize_embeddings=True, convert_to_numpy=True)[0]
        scores = document_vectors @ vector
        order = np.argsort(-scores)[:5]
        rankings.append([(titles[int(index)], float(scores[int(index)])) for index in order])
    del model, document_vectors
    gc.collect()
    return rankings


def _canonical_candidates(
    connection: sqlite3.Connection,
    notebook_id: UUID,
    ranking: list[tuple[str, float]],
) -> list[EvidenceCandidateV2]:
    candidates: list[EvidenceCandidateV2] = []
    for dense_rank, (title, score) in enumerate(ranking, 1):
        rows = connection.execute(
            "SELECT c.id,c.text,c.document_id,c.version_id,s.source_id,"
            "c.position_section_index,c.position_chunk_index,c.position_page_number "
            "FROM chunks c JOIN document_versions v ON v.version_id=c.version_id "
            "JOIN sources s ON s.document_id=c.document_id "
            "WHERE s.notebook_id=? AND json_extract(v.metadata,'$.title')=? "
            "ORDER BY c.rowid LIMIT 1",
            (str(notebook_id), title),
        ).fetchall()
        for (
            chunk_id,
            text,
            document_id,
            version_id,
            source_id,
            section_index,
            chunk_index,
            page_number,
        ) in rows:
            document_uuid, version_uuid = UUID(document_id), UUID(version_id)
            candidates.append(
                EvidenceCandidateV2(
                    candidate_id=evidence_candidate_v2_id(
                        kind=EvidenceKindV2.CANONICAL_CHUNK,
                        document_id=document_uuid,
                        version_id=version_uuid,
                        authoritative_id=chunk_id,
                    ),
                    notebook_id=notebook_id,
                    source_id=UUID(source_id),
                    document_id=document_uuid,
                    version_id=version_uuid,
                    kind=EvidenceKindV2.CANONICAL_CHUNK,
                    authority=EvidenceAuthorityV2.ORIGINAL,
                    authoritative_id=chunk_id,
                    chunk_id=chunk_id,
                    document_title=title,
                    content=text,
                    locator=FrozenMetadata(
                        {
                            "section_index": section_index,
                            "chunk_index": chunk_index,
                            "page_number": page_number,
                        }
                    ),
                    score_components=(
                        EvidenceScoreComponentV2(
                            method="bge-m3-document", rank=dense_rank, score=score
                        ),
                    ),
                    fused_score=score,
                    completeness=RetrievalCompleteness.PARTIAL,
                )
            )
    return candidates


def _derived_candidates(
    connection: sqlite3.Connection,
    notebook_id: UUID,
    expected_title: str,
    blob_root: Path,
) -> list[EvidenceCandidateV2]:
    candidates: list[EvidenceCandidateV2] = []
    common_sql = (
        " JOIN document_versions v ON v.version_id=r.version_id "
        "JOIN sources s ON s.document_id=r.document_id "
        "JOIN asset_occurrences o ON o.occurrence_id=r.occurrence_id "
        "JOIN asset_catalog a ON a.asset_id=o.asset_id "
        "WHERE s.notebook_id=? AND json_extract(v.metadata,'$.title')=? "
    )
    ocr = connection.execute(
        "SELECT r.derivation_id,r.generation_id,r.document_id,r.version_id,r.occurrence_id,"
        "r.asset_id,s.source_id,a.mime_type,group_concat(g.text,char(10)) content "
        "FROM ocr_results r JOIN ocr_regions g ON g.derivation_id=r.derivation_id"
        + common_sql
        + "GROUP BY r.derivation_id ORDER BY r.created_at DESC LIMIT 1",
        (str(notebook_id), expected_title),
    ).fetchone()
    if ocr is not None and ocr[8]:
        candidates.append(
            _derived_candidate(
                ocr, expected_title, notebook_id, EvidenceKindV2.OCR_REGION, str(ocr[8])
            )
        )
    vision = connection.execute(
        "SELECT r.derivation_id,r.generation_id,r.document_id,r.version_id,r.occurrence_id,"
        "r.asset_id,s.source_id,a.mime_type,r.payload "
        "FROM vision_results r" + common_sql + "ORDER BY r.created_at DESC LIMIT 1",
        (str(notebook_id), expected_title),
    ).fetchone()
    if vision is not None:
        payload = json.loads(vision[8])
        content = "\n".join(
            [
                *(item["text"] for item in payload["captions"]),
                *(item["value"] for item in payload["observations"]),
            ]
        )
        if content:
            candidates.append(
                _derived_candidate(
                    vision, expected_title, notebook_id, EvidenceKindV2.VISION_OBSERVATION, content
                )
            )
    occurrence = connection.execute(
        "SELECT o.occurrence_id,o.asset_id,o.document_id,o.version_id,s.source_id,"
        "a.mime_type,a.content_hash,a.width,a.height "
        "FROM asset_occurrences o JOIN asset_catalog a ON a.asset_id=o.asset_id "
        "JOIN document_versions v ON v.version_id=o.version_id "
        "JOIN sources s ON s.document_id=o.document_id "
        "WHERE s.notebook_id=? AND json_extract(v.metadata,'$.title')=? "
        "AND a.mime_type LIKE 'image/%' "
        "ORDER BY o.occurrence_id LIMIT 1",
        (str(notebook_id), expected_title),
    ).fetchone()
    if occurrence is not None:
        occurrence_id, asset_id, document_id, version_id, source_id, mime, digest, width, height = (
            occurrence
        )
        stored = list((blob_root / digest[:2] / digest[2:]).glob("raw.*"))
        size = stored[0].stat().st_size if len(stored) == 1 else 0
        document_uuid, version_uuid = UUID(document_id), UUID(version_id)
        candidates.append(
            EvidenceCandidateV2(
                candidate_id=evidence_candidate_v2_id(
                    kind=EvidenceKindV2.ASSET_OCCURRENCE,
                    document_id=document_uuid,
                    version_id=version_uuid,
                    authoritative_id=occurrence_id,
                ),
                notebook_id=notebook_id,
                source_id=UUID(source_id),
                document_id=document_uuid,
                version_id=version_uuid,
                kind=EvidenceKindV2.ASSET_OCCURRENCE,
                authority=EvidenceAuthorityV2.ORIGINAL,
                authoritative_id=occurrence_id,
                asset_id=UUID(asset_id),
                occurrence_id=UUID(occurrence_id),
                document_title=expected_title,
                content="Authorized original image evidence.",
                resource_handle=f"asset://occurrence/{occurrence_id}",
                media_type=mime,
                locator=FrozenMetadata(
                    {
                        "byte_size": size,
                        "decoded_pixels": 0 if width is None or height is None else width * height,
                    }
                ),
                score_components=(EvidenceScoreComponentV2(method="asset-occurrence", rank=1),),
                completeness=RetrievalCompleteness.PARTIAL,
            )
        )
    return candidates


def _derived_candidate(
    row: sqlite3.Row | tuple[Any, ...],
    title: str,
    notebook_id: UUID,
    kind: EvidenceKindV2,
    content: str,
) -> EvidenceCandidateV2:
    derivation, generation, document, version, occurrence, asset, source, mime, _ = row
    document_id, version_id = UUID(document), UUID(version)
    return EvidenceCandidateV2(
        candidate_id=evidence_candidate_v2_id(
            kind=kind,
            document_id=document_id,
            version_id=version_id,
            authoritative_id=derivation,
        ),
        notebook_id=notebook_id,
        source_id=UUID(source),
        document_id=document_id,
        version_id=version_id,
        kind=kind,
        authority=EvidenceAuthorityV2.DERIVED,
        authoritative_id=derivation,
        asset_id=UUID(asset),
        occurrence_id=UUID(occurrence),
        derivation_id=UUID(derivation),
        generation_id=UUID(generation),
        document_title=title,
        content=content[:8_000],
        media_type=mime,
        locator=FrozenMetadata({"occurrence_id": occurrence}),
        provider="derived-store",
        model="evaluated-provider",
        score_components=(EvidenceScoreComponentV2(method=kind.value, rank=1),),
        completeness=RetrievalCompleteness.PARTIAL,
    )


def _retrieval(query: str, candidates: list[EvidenceCandidateV2]) -> MultimodalRetrievalResultV2:
    unique = {candidate.candidate_id: candidate for candidate in candidates}
    ranked = tuple(
        replace(value, final_rank=index) for index, value in enumerate(unique.values(), 1)
    )
    query_fingerprint = hashlib.sha256(query.encode("utf-8")).hexdigest()
    snapshot = hashlib.sha256(
        json.dumps(
            [(str(value.candidate_id), evidence_candidate_v2_digest(value)) for value in ranked],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    counts = Counter(value.kind.value for value in ranked)
    return MultimodalRetrievalResultV2(
        query=query,
        query_fingerprint=query_fingerprint,
        snapshot_identity=snapshot,
        completeness=RetrievalCompleteness.PARTIAL,
        candidates=ranked,
        diagnostics=MultimodalRetrievalDiagnosticsV2(
            recalled=len(ranked),
            deduplicated=len(candidates) - len(ranked),
            fused=len(ranked),
            reranked=0,
            returned=len(ranked),
            modality_counts=FrozenMetadata(dict(counts)),
            omitted_reasons=FrozenMetadata({"dense_backend": "evaluation-profile"}),
            elapsed_milliseconds=0,
        ),
    )


async def _run(args: argparse.Namespace) -> None:
    database = args.database.resolve(strict=True)
    rankings = _rank_documents(database, args.embedding.resolve(strict=True))
    store = SQLiteStore(database)
    blobs = FilesystemBlobStore(args.blobs.resolve(strict=True))
    await store.open()
    await blobs.open()
    provider = GemmaFinalQAProvider(database, blobs)
    authorizer = EvaluationAuthorizer(database)
    counter = ApproximateTokenCounter()
    orchestrator = FinalQAV2Orchestrator(
        store=store,
        provider=provider,
        context_builder=MultimodalContextBuilder(authorizer, counter),
        token_counter=counter,
        authorizer=authorizer,
    )
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    notebook_id = UUID(
        connection.execute("SELECT notebook_id FROM notebooks LIMIT 1").fetchone()[0]
    )
    actor_id = uuid5(NAMESPACE_URL, "mnemo:phase8.5.11:evaluator")
    results: list[dict[str, Any]] = []
    replay_verified = False
    try:
        for index, ((query, expected, category), ranking) in enumerate(
            zip(QUESTIONS, rankings, strict=True), 1
        ):
            candidates = _canonical_candidates(connection, notebook_id, ranking)
            if category in {"multimodal", "ocr-hi", "vision-mr", "multimodal-mr"}:
                candidates = [
                    *_derived_candidates(connection, notebook_id, expected, args.blobs.resolve()),
                    *candidates,
                ]
            retrieval = _retrieval(query, candidates[:8])
            assistant_turn_id = uuid5(NAMESPACE_URL, f"mnemo:phase8.5.11:qa:{index}")
            request = FinalQARequestV2(
                actor_id=actor_id,
                notebook_id=notebook_id,
                session_id=uuid5(NAMESPACE_URL, "mnemo:phase8.5.11:qa-session"),
                user_turn_id=uuid5(NAMESPACE_URL, f"mnemo:phase8.5.11:user:{index}"),
                assistant_turn_id=assistant_turn_id,
                query=query,
                retrieval_result=retrieval,
                context_budgets=MultimodalContextBudgetsV1(
                    max_items=8,
                    max_tokens=12_000,
                    max_bytes=500_000,
                    max_assets=2,
                    max_asset_bytes=15_000_000,
                    max_decoded_pixels=30_000_000,
                ),
                system_prompt=(
                    "Answer concisely from Mnemo evidence and preserve source provenance."
                ),
                max_output_tokens=300,
            )
            started = time.perf_counter()
            record: dict[str, Any] = {
                "number": index,
                "query": query,
                "category": category,
                "expected_document": expected,
                "retrieved_documents": [item.document_title for item in retrieval.candidates],
            }
            try:
                answer = await orchestrator.execute(request)
                cited = [item.document_title for item in answer.citations]
                record.update(
                    {
                        "status": answer.status.value,
                        "answer": answer.answer,
                        "citations": cited,
                        "retry_count": answer.retry_count,
                        "retrieval_hit": expected in record["retrieved_documents"],
                        "citation_hit": expected in cited,
                        "passed": bool(answer.answer) and expected in cited,
                    }
                )
                if index == 1:
                    calls = provider.calls
                    replay = await orchestrator.execute(request)
                    replay_verified = replay == answer and provider.calls == calls
            except Exception as error:
                record.update(
                    {
                        "status": "failed",
                        "error_type": type(error).__name__,
                        "error": str(error),
                        "passed": False,
                    }
                )
            record["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
            results.append(record)
            print(
                f"[{index:02d}/30] {'PASS' if record['passed'] else 'FAIL'} {expected}", flush=True
            )
    finally:
        connection.close()
        await provider.close()
        await blobs.close()
        await store.close()
    passed = sum(bool(item["passed"]) for item in results)
    output = {
        "profile": "phase8.5.11/final-qa-v2/gemma4-e4b/v1",
        "questions": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": passed / len(results),
        "provider_calls": provider.calls,
        "zero_generation_replay": replay_verified,
        "provider_latency_ms": provider.latencies,
        "average_provider_latency_ms": (
            sum(provider.latencies) / len(provider.latencies) if provider.latencies else None
        ),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in output.items() if key != "results"}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--blobs", type=Path, required=True)
    parser.add_argument("--embedding", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
