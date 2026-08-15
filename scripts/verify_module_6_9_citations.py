"""Validate ADR-0045 against the real Module 6.8 golden handoff."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid5

from mnemo import __version__
from mnemo.config import RerankerConfig
from mnemo.interfaces import CompletionResult, Message
from mnemo.models import (
    CitationResolutionStatus,
    DocumentContextLabel,
    GroundedAnswerStatus,
    Notebook,
    RetrievalRerankResult,
    Session,
    Turn,
    TurnRole,
)
from mnemo.registry import PluginRegistry
from mnemo.retrieval import CitationEngine, ContextBuilder, GroundedAnswerGenerator
from mnemo.retrieval.context import _render, _serialize_fixed_input
from mnemo.retrieval.reranker import (
    MODEL_ID,
    MODEL_REVISION,
    CrossEncoderReranker,
    CrossEncoderRerankerPlugin,
    RerankingModule,
)
from mnemo.storage import CompositeStorage, SQLiteStore
from mnemo.tokenizers import O200KBaseTokenCounter
from verify_module_6_4_parent import _tokenizer_asset
from verify_module_6_5_fusion import EXPECTED_SHA256, ROOT
from verify_module_6_6_reranking import DATASET, M65_EVIDENCE, _real_fusion
from verify_module_6_7_context import _ControlledExtractor, _ExtractorPlugin
from verify_module_6_8_answer import _ControlledSynthesizer, _SynthesizerPlugin

EVIDENCE = ROOT / "docs" / "milestone-evidence" / "module-6.9-citations.json"


class _CitationSynthesizer(_ControlledSynthesizer):
    model = "controlled-citation-synthesizer-v1"

    async def complete(
        self,
        system: str,
        messages: tuple[Message, ...],
        structured_output: object = None,
        max_tokens: int = 1000,
    ) -> CompletionResult:
        self.calls.append((system, messages, structured_output, max_tokens))
        return CompletionResult(
            model=self.model,
            text=(
                "The passage presents duty as grounded guidance [source:1]. "
                "That evidence remains the basis of this answer [source:1]."
            ),
        )


class _Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value
        self.calls = 0

    def __call__(self) -> datetime:
        self.calls += 1
        return self.value


def _composite(sqlite: SQLiteStore) -> CompositeStorage:
    unused = cast(Any, object())
    return CompositeStorage(unused, sqlite, unused, unused)


async def _run() -> dict[str, object]:
    digest = sha256(DATASET.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256:
        raise AssertionError(f"golden corpus hash mismatch: {digest}")
    m65 = cast(dict[str, object], json.loads(M65_EVIDENCE.read_text(encoding="utf-8")))
    started = time.perf_counter()
    fusion, retrieval_storage, ollama, builtins = await _real_fusion(m65)
    reranker = CrossEncoderReranker(
        RerankerConfig(provider="sentence-transformers", model=MODEL_ID)
    )
    rerank_registry = PluginRegistry(core_version=__version__)
    rerank_registry.load_plugin(CrossEncoderRerankerPlugin(reranker))
    counter = O200KBaseTokenCounter(_tokenizer_asset())
    extractor = _ControlledExtractor(counter)
    context_registry = PluginRegistry(core_version=__version__)
    context_registry.load_plugin(_ExtractorPlugin(extractor))
    context_registry.freeze()
    synthesizer = _CitationSynthesizer()
    answer_registry = PluginRegistry(core_version=__version__)
    answer_registry.load_plugin(_SynthesizerPlugin(synthesizer))
    answer_registry.freeze()
    citation_sqlite: SQLiteStore | None = None
    try:
        await rerank_registry.execute_startup_hooks()
        rerank_registry.freeze()
        query = cast(str, m65["query"])
        rerank_result = await RerankingModule(rerank_registry).execute(query, fusion)
        if not isinstance(rerank_result, RetrievalRerankResult):
            raise AssertionError("real Module 6.6 handoff is unavailable")

        system_prompt = "Answer only from the attributed context."
        fixed = counter.count(_serialize_fixed_input(system_prompt, rerank_result, ()))
        mandatory = "\n\n".join(
            _render(index, item, item.fused_result.chunk.text, {})
            for index, item in enumerate(rerank_result.results[:3], 1)
        )
        budget = fixed + counter.count(mandatory)
        context_result = await ContextBuilder(context_registry, counter).build(
            rerank_result,
            context_budget=budget,
            system_prompt=system_prompt,
        )
        if not context_result.items:
            raise AssertionError("real Module 6.7 handoff is empty")
        answer_result = await GroundedAnswerGenerator(answer_registry, counter).generate(
            context_result,
            max_output_tokens=256,
        )
        if answer_result.status is not GroundedAnswerStatus.GENERATED:
            raise AssertionError("real Module 6.8 handoff is unavailable")
        if answer_result.answer is None:
            raise AssertionError("real Module 6.8 answer is unavailable")

        cited_item = context_result.items[0]
        chunk = cited_item.reranked_result.fused_result.chunk
        document = await retrieval_storage.get_document(chunk.document_id)
        if document is None:
            raise AssertionError("canonical real document is unavailable")
        version = next(item for item in document.versions if item.version_id == chunk.version_id)
        title = version.metadata.title or "Bhagavad-gita As It Is"
        label = DocumentContextLabel(
            document_id=chunk.document_id,
            version_id=chunk.version_id,
            title=title,
        )

        with TemporaryDirectory(prefix="mnemo-module-6-9-") as temporary:
            citation_sqlite = SQLiteStore(Path(temporary) / "citations.db")
            await citation_sqlite.open()
            composite = _composite(citation_sqlite)
            await citation_sqlite.upsert_document(document)
            turn_time = datetime.now(UTC)
            notebook = Notebook(
                notebook_id=uuid5(NAMESPACE_URL, "mnemo:module-6.9:notebook"),
                title="Module 6.9 acceptance",
                created_at=turn_time,
                updated_at=turn_time,
            )
            turn = Turn(
                turn_id=uuid5(NAMESPACE_URL, "mnemo:module-6.9:assistant-turn"),
                session_id=uuid5(NAMESPACE_URL, "mnemo:module-6.9:session"),
                sequence=0,
                role=TurnRole.ASSISTANT,
                content=answer_result.answer,
                created_at=turn_time,
            )
            session = Session(
                session_id=turn.session_id,
                notebook_id=notebook.notebook_id,
                created_at=turn_time,
                updated_at=turn_time,
                turns=(turn,),
            )
            await citation_sqlite.upsert_notebook(notebook)
            await citation_sqlite.upsert_session(session)
            persisted_session = await citation_sqlite.get_session(session.session_id)
            if persisted_session is None or persisted_session.turns != (turn,):
                raise AssertionError("assistant turn was not persisted before Module 6.9")

            clock = _Clock(turn_time + timedelta(seconds=1))
            engine = CitationEngine(composite, clock)
            citation_started = time.perf_counter()
            first = await engine.resolve_and_persist(
                answer_result,
                assistant_turn=turn,
                document_labels=(label,),
            )
            citation_seconds = time.perf_counter() - citation_started
            second = await engine.resolve_and_persist(
                answer_result,
                assistant_turn=turn,
                document_labels=(label,),
            )
            reloaded = await composite.get_citations_for_turn(turn.turn_id)

            if first.status is not CitationResolutionStatus.RESOLVED or not first.persisted:
                raise AssertionError("citation resolution did not persist")
            if first.answer_result is not answer_result or first.assistant_turn is not turn:
                raise AssertionError("Module 6.9 replaced retained provenance")
            if first.citations != second.citations or first.citations != reloaded:
                raise AssertionError("deterministic citation upsert did not converge")
            if len(first.citations) != 1:
                raise AssertionError("repeated markers did not deduplicate")
            citation = first.citations[0]
            expected_id = uuid5(
                NAMESPACE_URL,
                f"mnemo:citation:v1:{str(turn.turn_id).lower()}:1:{chunk.id}",
            )
            if citation.citation_id != expected_id:
                raise AssertionError("citation identity is not canonical UUIDv5")
            if citation.verbatim_quote != chunk.text:
                raise AssertionError("citation does not contain the complete canonical quote")
            if (citation.document_id, citation.version_id) != (
                chunk.document_id,
                chunk.version_id,
            ):
                raise AssertionError("exact document/version identity changed")
            if citation.document_title != title:
                raise AssertionError("exact-version document label was not used")
            if clock.calls != 2:
                raise AssertionError("clock was not called once per cited invocation")
            await citation_sqlite.close()
            citation_sqlite = None
            return {
                "verdict": "PASS",
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "dataset": str(DATASET.relative_to(ROOT)).replace("\\", "/"),
                "dataset_sha256": digest,
                "pipeline": "real Modules 6.5 -> 6.6 -> 6.7 -> 6.8 -> 6.9",
                "query": answer_result.query,
                "context_items": len(context_result.items),
                "answer": answer_result.answer,
                "repeated_source_marker": 1,
                "citation_count": len(first.citations),
                "citation_id": str(citation.citation_id),
                "turn_id": str(turn.turn_id),
                "chunk_id": citation.chunk_id,
                "document_id": str(citation.document_id),
                "version_id": str(citation.version_id),
                "document_title": citation.document_title,
                "page_number": citation.page_number,
                "quote_character_count": len(citation.verbatim_quote),
                "clock_calls_for_two_executions": clock.calls,
                "sqlite_reload_count": len(reloaded),
                "deterministic_repeat": True,
                "repeated_marker_deduplicated": True,
                "exact_canonical_quote": True,
                "exact_document_version": True,
                "provenance_object_preserved": True,
                "assistant_turn_pre_persisted": True,
                "citation_storage_path": "CompositeStorage -> SQLiteStore",
                "direct_backend_access_by_module_6_9": False,
                "historical_retrieval_storage_mutated": False,
                "citation_resolution_seconds": citation_seconds,
                "total_acceptance_seconds": time.perf_counter() - started,
                "reranker_model_id": MODEL_ID,
                "reranker_model_revision": MODEL_REVISION,
            }
    finally:
        if citation_sqlite is not None:
            await citation_sqlite.close()
        await rerank_registry.execute_shutdown_hooks()
        await ollama._client.aclose()
        await retrieval_storage.close()
        del builtins


def main() -> int:
    evidence = asyncio.run(_run())
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
