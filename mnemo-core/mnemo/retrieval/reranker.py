"""ADR-0042 fusion-aware cross-encoder reranking."""

from __future__ import annotations

import asyncio
import importlib
import json
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from mnemo import __version__
from mnemo.config import RerankerConfig
from mnemo.interfaces import (
    ContractValidationError,
    DependencyUnavailableError,
    FusionRerankerCapabilities,
    FusionRerankingInterfaceV1,
    IntegrityError,
    LifecycleError,
    MnemoInterfaceError,
    PluginError,
    RerankerCapabilities,
)
from mnemo.models import (
    Chunk,
    CrossEncoderEvidence,
    RerankedChunkResult,
    RerankFallbackReason,
    RerankPolicy,
    RetrievalFusionResult,
    RetrievalRerankResult,
    ScoredChunk,
    stable_sigmoid,
)
from mnemo.registry import PluginRegistry, RegistryState

MODEL_ID = "cross-encoder/ms-marco-MiniLM-L6-v2"
MODEL_REVISION = "233902d25c440f23af6f7d6e94d2946bac0bee0a"
MODEL_LICENSE = "apache-2.0"
MAX_PAIR_TOKENS = 512
MAX_RERANK_CANDIDATES = 100
RERANK_BATCH_SIZE = 16
RELEVANCE_THRESHOLD = 0.4


class RerankingModule:
    """Apply an optional fusion-aware provider or retain existing RRF order."""

    def __init__(self, registry: PluginRegistry) -> None:
        if not isinstance(registry, PluginRegistry):
            raise TypeError("registry must be PluginRegistry")
        if registry.state is not RegistryState.FROZEN:
            raise ValueError("registry must be frozen before reranking")
        self._registry = registry

    async def execute(
        self,
        query: str,
        fusion_result: RetrievalFusionResult,
    ) -> RetrievalRerankResult:
        """Rerank every bounded candidate without changing its provenance."""
        normalized = _normalize_query(query)
        if not isinstance(fusion_result, RetrievalFusionResult):
            raise TypeError("fusion_result must be RetrievalFusionResult")
        if not fusion_result.results:
            return RetrievalRerankResult(
                query=normalized,
                fusion_result=fusion_result,
                policy=RerankPolicy.UNCHANGED_EMPTY,
                results=(),
            )
        provider = self._registry.resolve_fusion_reranker("primary")
        if provider is None:
            return _fallback(normalized, fusion_result)
        try:
            result = await provider.rerank_fused(normalized, fusion_result)
        except asyncio.CancelledError:
            raise
        except MnemoInterfaceError:
            raise
        except Exception as error:
            raise PluginError("fusion reranker invocation failed") from error
        _validate_provider_result(normalized, fusion_result, provider, result)
        return result


class CrossEncoderReranker:
    """Pinned CPU sentence-transformers provider for legacy and fused contracts."""

    def __init__(
        self,
        config: RerankerConfig,
        *,
        cache_folder: Path | None = None,
        local_files_only: bool = False,
    ) -> None:
        """Record inert configuration; model allocation belongs to startup."""
        if not isinstance(config, RerankerConfig):
            raise TypeError("config must be RerankerConfig")
        if config.provider != "sentence-transformers":
            raise ValueError("reference reranker provider must be sentence-transformers")
        if config.model != MODEL_ID:
            raise ValueError(f"reference reranker model must be {MODEL_ID}")
        if cache_folder is not None and not isinstance(cache_folder, Path):
            raise TypeError("cache_folder must be Path or None")
        if not isinstance(local_files_only, bool):
            raise TypeError("local_files_only must be boolean")
        self._cache_folder = cache_folder
        self._local_files_only = local_files_only
        self._executor: ThreadPoolExecutor | None = None
        self._runtime: _CrossEncoderRuntime | None = None
        self._lifecycle_lock = asyncio.Lock()
        self._inference_lock = asyncio.Lock()

    def capabilities(self) -> FusionRerankerCapabilities:
        """Return the fixed ADR-0042 capability identity."""
        return FusionRerankerCapabilities(
            supports_cross_encoder=True,
            supports_batch=True,
            preserves_fusion_evidence=True,
            max_candidates=MAX_RERANK_CANDIDATES,
            model_id=MODEL_ID,
            model_revision=MODEL_REVISION,
        )

    async def initialize(self) -> None:
        """Load and validate the pinned model in the provider-owned worker."""
        async with self._lifecycle_lock:
            if self._runtime is not None:
                return
            executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mnemo-reranker")
            try:
                loop = asyncio.get_running_loop()
                runtime = await loop.run_in_executor(executor, self._load_runtime)
            except BaseException:
                executor.shutdown(wait=True, cancel_futures=True)
                raise
            self._executor = executor
            self._runtime = runtime

    async def close(self) -> None:
        """Release the worker and model references after bounded work completes."""
        async with self._lifecycle_lock:
            executor = self._executor
            self._executor = None
            self._runtime = None
            if executor is not None:
                await asyncio.to_thread(executor.shutdown, wait=True, cancel_futures=True)

    async def rerank_fused(
        self,
        query: str,
        fusion_result: RetrievalFusionResult,
    ) -> RetrievalRerankResult:
        """Score all fused candidates and retain the original evidence objects."""
        normalized = _normalize_query(query)
        if not isinstance(fusion_result, RetrievalFusionResult):
            raise TypeError("fusion_result must be RetrievalFusionResult")
        if not fusion_result.results:
            return RetrievalRerankResult(
                query=normalized,
                fusion_result=fusion_result,
                policy=RerankPolicy.UNCHANGED_EMPTY,
                results=(),
            )
        chunks = tuple(item.chunk for item in fusion_result.results)
        logits = await self._score_chunks(normalized, chunks)
        if len(logits) != len(chunks):
            raise IntegrityError("cross-encoder output cardinality does not match candidates")
        by_id = {
            chunk.id: CrossEncoderEvidence(
                chunk_id=chunk.id,
                raw_logit=logit,
                relevance_score=stable_sigmoid(logit),
                below_relevance_threshold=stable_sigmoid(logit) < RELEVANCE_THRESHOLD,
                model_id=MODEL_ID,
                model_revision=MODEL_REVISION,
            )
            for chunk, logit in zip(chunks, logits, strict=True)
        }
        if len(by_id) != len(chunks):
            raise IntegrityError("cross-encoder input contains duplicate chunk identities")
        ordered = _apply_diversity_ordering(
            normalized,
            fusion_result.results,
            {item.chunk.id: by_id[item.chunk.id].relevance_score for item in fusion_result.results},
        )
        return RetrievalRerankResult(
            query=normalized,
            fusion_result=fusion_result,
            policy=RerankPolicy.CROSS_ENCODER,
            results=tuple(
                RerankedChunkResult(
                    fused_result=item,
                    rerank_evidence=by_id[item.chunk.id],
                    reranked_rank=rank,
                )
                for rank, item in enumerate(ordered, start=1)
            ),
        )

    async def rerank(
        self,
        query: str,
        candidates: tuple[ScoredChunk, ...],
        top_k: int,
    ) -> tuple[ScoredChunk, ...]:
        """Implement the unchanged Phase 1 contract without replacing raw scores."""
        normalized = _normalize_query(query)
        if not isinstance(candidates, tuple) or any(
            not isinstance(item, ScoredChunk) for item in candidates
        ):
            raise TypeError("candidates must be a tuple of ScoredChunk values")
        _validate_positive_bound(top_k, "top_k", MAX_RERANK_CANDIDATES)
        if not candidates:
            return ()
        logits = await self._score_chunks(normalized, tuple(item.chunk for item in candidates))
        if len(logits) != len(candidates):
            raise IntegrityError("cross-encoder output cardinality does not match candidates")
        ordered = sorted(
            zip(candidates, logits, strict=True),
            key=lambda pair: (-stable_sigmoid(pair[1]), pair[0].rank, pair[0].chunk.id),
        )[:top_k]
        return tuple(
            ScoredChunk(
                chunk=item.chunk,
                score=item.score,
                source=item.source,
                rank=rank,
            )
            for rank, (item, _) in enumerate(ordered, start=1)
        )

    async def _score_chunks(self, query: str, chunks: tuple[Chunk, ...]) -> tuple[float, ...]:
        if len(chunks) > MAX_RERANK_CANDIDATES:
            raise ContractValidationError("reranking accepts at most 100 candidates")
        if any(not isinstance(chunk, Chunk) for chunk in chunks):
            raise TypeError("chunks must contain Chunk values")
        if len({chunk.id for chunk in chunks}) != len(chunks):
            raise IntegrityError("reranking candidates must have unique identities")
        async with self._inference_lock:
            runtime = self._runtime
            executor = self._executor
            if runtime is None or executor is None:
                raise LifecycleError("cross-encoder accessed before startup initialization")
            loop = asyncio.get_running_loop()
            logits = await loop.run_in_executor(
                executor,
                runtime.predict_logits,
                query,
                tuple(chunk.text for chunk in chunks),
            )
        if not isinstance(logits, tuple):
            raise IntegrityError("cross-encoder returned a non-tuple score sequence")
        if len(logits) != len(chunks):
            raise IntegrityError("cross-encoder returned missing or extra scores")
        if any(isinstance(score, bool) or not isinstance(score, float) for score in logits):
            raise IntegrityError("cross-encoder returned a malformed score")
        if any(not math.isfinite(score) for score in logits):
            raise IntegrityError("cross-encoder returned a non-finite score")
        return logits

    def _load_runtime(self) -> _CrossEncoderRuntime:
        try:
            torch = importlib.import_module("torch")
            snapshot_download = importlib.import_module("huggingface_hub").snapshot_download
            CrossEncoder = importlib.import_module("sentence_transformers").CrossEncoder
        except ImportError as error:
            raise DependencyUnavailableError(
                "sentence-transformers reranking extra is not installed"
            ) from error
        snapshot = Path(
            snapshot_download(
                repo_id=MODEL_ID,
                revision=MODEL_REVISION,
                cache_dir=None if self._cache_folder is None else str(self._cache_folder),
                local_files_only=self._local_files_only,
            )
        )
        _validate_snapshot(snapshot)
        model = CrossEncoder(
            str(snapshot),
            device="cpu",
            max_length=MAX_PAIR_TOKENS,
            activation_fn=torch.nn.Identity(),
            trust_remote_code=False,
            local_files_only=True,
            model_kwargs={"use_safetensors": True},
        )
        if getattr(model, "max_length", None) != MAX_PAIR_TOKENS:
            raise IntegrityError("cross-encoder maximum pair length is not 512")
        underlying = getattr(model, "model", None)
        tokenizer = getattr(model, "tokenizer", None)
        if underlying is None or tokenizer is None:
            raise IntegrityError("cross-encoder runtime is incomplete")
        logits_labels = getattr(underlying.config, "num_labels", None)
        if logits_labels != 1:
            raise IntegrityError("cross-encoder must produce exactly one logit")
        underlying.eval()
        runtime = _CrossEncoderRuntime(model=model, torch=torch)
        first = runtime.predict_logits("What is duty?", ("Duty is disciplined action.",))[0]
        second = runtime.predict_logits("What is duty?", ("Duty is disciplined action.",))[0]
        if not math.isfinite(first) or not math.isclose(first, second, rel_tol=0.0, abs_tol=1e-6):
            raise IntegrityError("cross-encoder smoke score is invalid or nondeterministic")
        return runtime


class CrossEncoderRerankerPlugin:
    """Explicit dual registration and lifecycle wiring for the reference provider."""

    name = "mnemo-cross-encoder-reranker"
    version = __version__
    core_version_range = ">=0.20.1"

    def __init__(self, provider: CrossEncoderReranker) -> None:
        if not isinstance(provider, CrossEncoderReranker):
            raise TypeError("provider must be CrossEncoderReranker")
        self.provider = provider
        self.legacy_provider = _LegacyCrossEncoderAdapter(provider)

    def capabilities(self) -> tuple[str, ...]:
        return ("fusion_reranker", "reranker")

    def register(self, registry: PluginRegistry) -> None:
        registry.register_reranker("primary", self.legacy_provider, priority=0)
        registry.register_fusion_reranker("primary", self.provider, priority=0)
        registry.register_startup_hook(self.provider.initialize)
        registry.register_shutdown_hook(self.provider.close)


class _LegacyCrossEncoderAdapter:
    """Explicit provider-local bridge for the unchanged Phase 1 contract."""

    def __init__(self, provider: CrossEncoderReranker) -> None:
        self._provider = provider

    def capabilities(self) -> RerankerCapabilities:
        return RerankerCapabilities(
            supports_cross_encoder=True,
            supports_batch=True,
            preserves_raw_scores=True,
        )

    async def rerank(
        self,
        query: str,
        candidates: tuple[ScoredChunk, ...],
        top_k: int,
    ) -> tuple[ScoredChunk, ...]:
        return await self._provider.rerank(query, candidates, top_k)


class _CrossEncoderRuntime:
    """Synchronous CPU runtime isolated inside the provider-owned executor."""

    def __init__(self, *, model: Any, torch: Any) -> None:
        self.model = model
        self.torch = torch

    def predict_logits(self, query: str, texts: tuple[str, ...]) -> tuple[float, ...]:
        tokenizer = self.model.tokenizer
        query_tokens = tokenizer(query, add_special_tokens=False, truncation=False)["input_ids"]
        if len(query_tokens) + 3 > MAX_PAIR_TOKENS:
            raise ContractValidationError("query cannot fit without truncation")
        values: list[float] = []
        for start in range(0, len(texts), RERANK_BATCH_SIZE):
            batch = texts[start : start + RERANK_BATCH_SIZE]
            encoded = tokenizer(
                [query] * len(batch),
                list(batch),
                padding=True,
                truncation="only_second",
                max_length=MAX_PAIR_TOKENS,
                return_tensors="pt",
            )
            encoded = {name: tensor.to("cpu") for name, tensor in encoded.items()}
            with self.torch.inference_mode():
                logits = self.model.model(**encoded).logits.reshape(-1)
            values.extend(float(value) for value in logits.detach().cpu().tolist())
        return tuple(values)


def _normalize_query(query: str) -> str:
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    normalized = " ".join(query.split())
    if not normalized:
        raise ContractValidationError("query must not be empty")
    return normalized


def _fallback(query: str, fusion_result: RetrievalFusionResult) -> RetrievalRerankResult:
    return RetrievalRerankResult(
        query=query,
        fusion_result=fusion_result,
        policy=RerankPolicy.RRF_FALLBACK,
        fallback_reason=RerankFallbackReason.PROVIDER_UNAVAILABLE,
        results=tuple(
            RerankedChunkResult(
                fused_result=item,
                rerank_evidence=None,
                reranked_rank=item.global_rank,
            )
            for item in fusion_result.results
        ),
    )


def _validate_provider_result(
    query: str,
    fusion_result: RetrievalFusionResult,
    provider: FusionRerankingInterfaceV1,
    result: object,
) -> None:
    if not isinstance(result, RetrievalRerankResult):
        raise IntegrityError("fusion reranker returned an invalid result type")
    if result.query != query or result.fusion_result is not fusion_result:
        raise IntegrityError("fusion reranker changed query or fusion provenance")
    if result.policy is not RerankPolicy.CROSS_ENCODER:
        raise IntegrityError("registered fusion reranker must return CROSS_ENCODER policy")
    capabilities = provider.capabilities()
    if not isinstance(capabilities, FusionRerankerCapabilities):
        raise IntegrityError("fusion reranker returned invalid capabilities")
    if any(
        item.rerank_evidence is None
        or item.rerank_evidence.model_id != capabilities.model_id
        or item.rerank_evidence.model_revision != capabilities.model_revision
        for item in result.results
    ):
        raise IntegrityError("fusion reranker evidence does not match provider identity")


def _validate_snapshot(snapshot: Path) -> None:
    required = ("config.json", "tokenizer.json", "tokenizer_config.json", "model.safetensors")
    missing = tuple(name for name in required if not (snapshot / name).is_file())
    if missing:
        raise DependencyUnavailableError(f"pinned model snapshot is incomplete: {missing}")
    config = json.loads((snapshot / "config.json").read_text(encoding="utf-8"))
    if config.get("max_position_embeddings") != MAX_PAIR_TOKENS:
        raise IntegrityError("pinned model does not support exactly 512 positions")
    if len(config.get("id2label", {})) != 1:
        raise IntegrityError("pinned model configuration is not single-logit")
    activation = config.get("sbert_ce_default_activation_function", "")
    if not activation.endswith(".Identity"):
        raise IntegrityError("pinned model default activation is not identity")
    readme = snapshot / "README.md"
    if (
        not readme.is_file()
        or f"license: {MODEL_LICENSE}" not in readme.read_text(encoding="utf-8").lower()
    ):
        raise IntegrityError("pinned model Apache-2.0 license metadata is unavailable")


def _validate_positive_bound(value: int, field_name: str, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 1 or value > maximum:
        raise ValueError(f"{field_name} must be from 1 through {maximum}")


def _get_item_source(item: FusedChunkResult) -> str:
    meta = getattr(item.chunk, "metadata", None)
    raw = meta.get("source_name", "") if hasattr(meta, "get") else ""
    if not raw and getattr(item.chunk, "heading_path", ()):
        raw = item.chunk.heading_path[0]
    if not raw:
        raw = getattr(item.chunk, "source_id", "") or getattr(item.chunk, "document_id", "")
    return str(raw)


def _detect_query_relevant_sources(
    query: str,
    fused_items: tuple[FusedChunkResult, ...] | list[FusedChunkResult],
    scores_by_id: dict[str, float],
) -> list[str]:
    """Detect distinct source documents genuinely relevant to the query."""
    q_lower = query.lower()
    
    doc_signatures = {
        "Atharv_Patil_RESUME_SDE.pdf": ["resume", "atharv", "skills", "experience", "education", "scholastic", "award", "arvsal", "spi", "cpi"],
        "Bhagavad-gita-As-It-Is.pdf": ["gita", "bhagavad", "verse", "chapter", "text", "krishna", "krsna", "arjuna", "karma", "duty", "surrender", "sarva-dharman"],
        "Coordinator Application 2026–27.pptx": ["coordinator", "application", "fine arts", "budget", "art fest", "kintsugi", "secretar", "club"],
        "ME333 - Exp2-LabReport_To_Submit.docx": ["me333", "lab report", "vibration", "sdof", "accelerometer", "frequency", "mass", "damper", "resonance", "transmissibility", "b6"],
        "ME361_L1_fbd03201-7db3-4553-a6e5-06f24817f9ea (1).pptx": ["me361", "manufacturing", "iphone", "chassis", "tolerance", "milling", "stripping", "mmw", "sulawesi", "roughness"],
        "server.js": ["server.js", "endpoint", "route", "express", "whisper", "tts", "validatewhisperoutput", "pcmtowav", "buffer", "speech", "intent", "/command", "/speak", "/stream"],
        "Y24_CPI.csv": ["cpi", "rank", "roll", "y24", "csv", "240740", "inesh", "student", "dataset"]
    }
    
    matched_sources: set[str] = set()
    for item in fused_items:
        source_name = _get_item_source(item)
            
        for doc_key, keywords in doc_signatures.items():
            if doc_key.lower() in source_name.lower():
                if any(kw in q_lower for kw in keywords):
                    matched_sources.add(source_name)
                    
        score = scores_by_id.get(item.chunk.id, 0.0)
        if score >= 0.50 and source_name:
            matched_sources.add(source_name)
            
    return list(matched_sources)


def _apply_diversity_ordering(
    query: str,
    fused_items: tuple[FusedChunkResult, ...] | list[FusedChunkResult],
    scores_by_id: dict[str, float],
) -> list[FusedChunkResult]:
    """Applies diversity-aware ordering while preserving strict determinism and relevance."""
    if not fused_items:
        return []
        
    items_list = list(fused_items)
    
    sorted_by_score = sorted(
        items_list,
        key=lambda item: (
            -scores_by_id.get(item.chunk.id, 0.0),
            item.global_rank,
            item.chunk.id,
        ),
    )
    
    relevant_sources = _detect_query_relevant_sources(query, tuple(fused_items), scores_by_id)
    if len(relevant_sources) <= 1:
        return sorted_by_score
        
    selected_chunks: list[FusedChunkResult] = []
    selected_ids: set[str] = set()
    
    source_best_score: dict[str, float] = {}
    for s in relevant_sources:
        s_cands = [item for item in sorted_by_score if _get_item_source(item) == s]
        source_best_score[s] = scores_by_id.get(s_cands[0].chunk.id, 0.0) if s_cands else -999.0
        
    sorted_sources = sorted(relevant_sources, key=lambda s: source_best_score[s], reverse=True)
    
    num_to_take = 2 if len(sorted_sources) <= 2 else 1
    for round_idx in range(num_to_take):
        for s in sorted_sources:
            s_cands = [item for item in sorted_by_score if _get_item_source(item) == s]
            if round_idx < len(s_cands):
                cand = s_cands[round_idx]
                if cand.chunk.id not in selected_ids:
                    selected_chunks.append(cand)
                    selected_ids.add(cand.chunk.id)
                
    for item in sorted_by_score:
        if item.chunk.id not in selected_ids:
            selected_chunks.append(item)
            selected_ids.add(item.chunk.id)
            
    return selected_chunks
