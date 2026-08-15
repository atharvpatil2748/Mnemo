"""Official clean Phase 0-6 / M6 golden-corpus verification."""

from __future__ import annotations

import asyncio
import json
import platform
import sqlite3
import sys
import time
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from mnemo import __version__
from mnemo.config import LLMConfig, LLMRoleConfig, RerankerConfig
from mnemo.engine import FinalQAComponents, KnowledgeEngine
from mnemo.models import (
    DocType,
    DocumentContextLabel,
    FinalQARequest,
    FinalQAStatus,
    MetadataFilter,
    Session,
    Turn,
    TurnRole,
)
from mnemo.tokenizers import O200KBaseTokenCounter
from verify_phase_4_5_milestones import (
    DATASET,
    EXPECTED_DATASET_SHA256,
    RUNS_DIR,
    _config,
    _registry,
    _run_id,
    _run_m4,
    _run_m5,
    _tokenizer_asset,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "milestone-evidence" / "m6-phase-6.json"
QUESTION = (
    "What does the Bhagavad Gita teach about duty? "
    "You MUST cite your claims using the exact format [source:N] (e.g. [source:1])."
)
MODEL = "gemma4:e4b"


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _schema_version(path: Path) -> int:
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT MAX(version) FROM schema_versions").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


async def _main() -> int:
    started = time.perf_counter()
    digest = sha256(DATASET.read_bytes()).hexdigest()
    _assert(digest == EXPECTED_DATASET_SHA256, "golden PDF digest changed")
    run_id = _run_id()
    base_config = _config(run_id)
    bootstrap_registry = _registry(base_config)
    bootstrap_storage = None
    engine: KnowledgeEngine | None = None
    try:
        m4, chunks, bootstrap_storage = await _run_m4(bootstrap_registry, base_config)
        document = await bootstrap_storage.get_document(chunks[0].document_id)
        _assert(document is not None, "fresh canonical document is unavailable")
        current = next(
            version
            for version in document.versions
            if version.version_id == document.current_version_id
        )
        title = current.metadata.title
        _assert(bool(title and title.strip()), "fresh document title is unavailable")
        m5 = await _run_m5(bootstrap_registry, base_config, chunks, bootstrap_storage, run_id)
        await bootstrap_storage.close()
        bootstrap_storage = None

        role = LLMRoleConfig(provider="ollama", model=MODEL, max_context_tokens=8192)
        config = base_config.model_copy(
            update={
                "llm": LLMConfig(
                    planner=role,
                    synthesizer=role,
                    extractor=role,
                    classifier=role,
                ),
                "reranker": RerankerConfig(
                    provider="sentence-transformers",
                    model="cross-encoder/ms-marco-MiniLM-L6-v2",
                ),
            }
        )
        token_counter = O200KBaseTokenCounter(_tokenizer_asset())
        clock_calls = 0

        def clock() -> datetime:
            nonlocal clock_calls
            clock_calls += 1
            return datetime.now(UTC)

        engine = KnowledgeEngine(
            config,
            final_qa_components=FinalQAComponents(token_counter=token_counter, clock=clock),
        )
        await engine.initialize()
        storage = engine.storage
        notebook_id = uuid5(NAMESPACE_URL, f"mnemo-m6.2-notebook:{run_id}")
        source_id = uuid5(NAMESPACE_URL, f"mnemo-m6.2-source:{run_id}")
        session_id = uuid5(NAMESPACE_URL, f"mnemo-m6-session:{run_id}")
        user_turn_id = uuid5(NAMESPACE_URL, f"mnemo-m6-user:{run_id}")
        assistant_turn_id = uuid5(NAMESPACE_URL, f"mnemo-m6-assistant:{run_id}")
        now = datetime.now(UTC)
        user_turn = Turn(
            turn_id=user_turn_id,
            session_id=session_id,
            sequence=0,
            role=TurnRole.USER,
            content=QUESTION,
            created_at=now,
        )
        await storage.upsert_session(
            Session(
                session_id=session_id,
                notebook_id=notebook_id,
                created_at=now,
                updated_at=now,
                title="M6 golden verification",
                turns=(user_turn,),
            )
        )
        headings = tuple(
            dict.fromkeys(
                heading for chunk in chunks for heading in chunk.heading_path if heading.strip()
            )
        )[:40]
        request = FinalQARequest(
            query=QUESTION,
            metadata_filter=MetadataFilter(
                notebook_id=notebook_id,
                source_ids=(source_id,),
                doc_types=(DocType.BOOK,),
            ),
            global_limit=6,
            context_budget=5000,
            system_prompt="Answer only from the supplied Bhagavad Gita context.",
            max_output_tokens=1000,
            session_id=session_id,
            user_turn_id=user_turn_id,
            assistant_turn_id=assistant_turn_id,
            table_of_contents=headings,
            source_titles=(title,),
            document_labels=(
                DocumentContextLabel(
                    document_id=chunks[0].document_id,
                    version_id=chunks[0].version_id,
                    title=title,
                ),
            ),
        )
        qa_started = time.perf_counter()
        result = await engine.final_qa.execute(request)
        qa_seconds = time.perf_counter() - qa_started
        _assert(
            result.status is FinalQAStatus.CITATION_RESOLVED,
            f"M6 answer was not cited: {result.status.value}\nAnswer: {result.answer}",
        )
        _assert(result.answer is not None and "[source:" in result.answer, "answer has no marker")
        _assert(bool(result.citations), "answer has no resolved citations")
        context = result.citation_result.answer_result.context_result
        by_source = {item.source_number: item for item in context.items}
        citation_checks: list[dict[str, object]] = []
        for citation in result.citations:
            item = by_source.get(citation.source_number)
            if item is None:
                raise AssertionError("citation source is not selected context")
            chunk = item.reranked_result.fused_result.chunk
            _assert(citation.chunk_id == chunk.id, "citation chunk identity differs")
            _assert(citation.document_id == chunk.document_id, "citation document differs")
            _assert(citation.version_id == chunk.version_id, "citation version differs")
            _assert(citation.verbatim_quote == chunk.text, "citation quote is not canonical text")
            persisted = await storage.get_citations_for_turn(citation.turn_id)
            _assert(citation in persisted, "citation did not reload through storage facade")
            citation_checks.append(
                {
                    "citation_id": str(citation.citation_id),
                    "turn_id": str(citation.turn_id),
                    "source_number": citation.source_number,
                    "chunk_id": citation.chunk_id,
                    "document_id": str(citation.document_id),
                    "version_id": str(citation.version_id),
                    "title": citation.document_title,
                    "heading_path": list(citation.heading_path),
                    "page_number": citation.page_number,
                    "quote_sha256": sha256(citation.verbatim_quote.encode()).hexdigest(),
                    "exact_canonical_quote": True,
                }
            )
        session = await storage.get_session(session_id)
        if session is None or len(session.turns) != 2:
            raise AssertionError("assistant turn was not persisted")
        fusion = context.rerank_result.fusion_result
        generation = result.citation_result.answer_result.generation_evidence
        if generation is None:
            raise AssertionError("generated answer has no generation evidence")
        evidence = {
            "verdict": "PASS",
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "version": __version__,
            "run_id": run_id,
            "dataset": str(DATASET.relative_to(ROOT)).replace("\\", "/"),
            "dataset_sha256": digest,
            "source_pdf_preserved": DATASET.is_file(),
            "old_acceptance_data_reused": False,
            "fresh_run_directory": str((RUNS_DIR / run_id).relative_to(ROOT)).replace("\\", "/"),
            "document_id": str(chunks[0].document_id),
            "version_id": str(chunks[0].version_id),
            "source_id": str(source_id),
            "notebook_id": str(notebook_id),
            "document_title": title,
            "fresh_chunk_count": len(chunks),
            "fresh_embedding_count": m5["input_chunks"],
            "qdrant_collection": m5["qdrant_collection"],
            "qdrant_point_count": m5["qdrant_exact_count"],
            "embedding_model": m5["ollama_model"],
            "embedding_dimensions": m5["embedding_dimensions"],
            "sqlite_schema_version": _schema_version(config.storage.sqlite.path),
            "query": result.query,
            "planner_subqueries": len(fusion.plan.sub_queries),
            "retrieval_invocations": len(fusion.invocations),
            "fusion_candidates": len(fusion.results),
            "reranking_candidates": len(context.rerank_result.results),
            "context_selected": len(context.items),
            "context_omitted": len(context.omitted_results),
            "context_tokens": context.context_tokens,
            "answer": result.answer,
            "answer_model": generation.model,
            "answer_token_count": generation.answer_token_count,
            "final_qa_status": result.status.value,
            "citation_count": len(result.citations),
            "citations": citation_checks,
            "assistant_turn_id": str(assistant_turn_id),
            "assistant_turn_sequence": session.turns[-1].sequence,
            "clock_calls": clock_calls,
            "nested_provenance_preserved": result.citation_result.answer_result.context_result
            is context,
            "qa_seconds": qa_seconds,
            "total_seconds": time.perf_counter() - started,
            "m4": m4,
            "m5": m5,
            "environment": {
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "llm_provider": "ollama",
                "llm_model": MODEL,
                "tokenizer": token_counter.tokenizer_id,
            },
        }
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(json.dumps(evidence, indent=2, ensure_ascii=True))
        return 0
    finally:
        if engine is not None:
            await engine.shutdown()
        if bootstrap_storage is not None:
            await bootstrap_storage.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
