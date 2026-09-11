"""Offline-only production adapters for the frozen Phase 8.5 multilingual profile."""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import math
import unicodedata
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from mnemo.interfaces.errors import (
    ContractValidationError,
    DependencyUnavailableError,
    IntegrityError,
    LifecycleError,
)
from mnemo.models.multilingual import (
    LanguageCapabilityState,
    LanguageCode,
    LanguageProviderProfile,
    MultilingualCandidate,
    MultilingualEmbedding,
    MultilingualEmbeddingInputV2,
    MultilingualEmbeddingProfile,
    MultilingualProviderReadinessV2,
    MultilingualQueryEmbeddingV2,
    MultilingualRerankScoreV2,
    ScriptCode,
    multilingual_embedding_id,
    multilingual_vector_hash,
)
from mnemo.models.multilingual_embeddings import (
    MultilingualEmbeddingInputV3,
    MultilingualEmbeddingV3,
    multilingual_embedding_v3_id,
)
from mnemo.models.multilingual_reranking import (
    MultilingualRerankCandidateV3,
    RerankerInputAuditV2,
    RerankerPairPolicyV1,
    RerankerPairPolicyV2,
    V2TypedCandidateAuditV1,
    render_contextual_provider_text,
)
from mnemo.models.processing import ProcessingTrustClass
from mnemo.phase85.models import ProviderReadinessResult
from mnemo.phase85.profiles import ModelProfileComponent
from mnemo.phase85.runtime import Phase85ProviderRegistration, Phase85ServiceRegistration
from mnemo.retrieval.reranker_candidates import RerankerCandidateBuilderV1

BGE_M3_MODEL = "BAAI/bge-m3"
BGE_M3_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
BGE_M3_DIMENSION = 1024
BGE_M3_MAX_BATCH = 32
BGE_M3_MAX_CONTEXT = 8192
BGE_M3_QUERY_PREPROCESSING = "bge-m3-query-v1"
BGE_M3_DOCUMENT_PREPROCESSING = "bge-m3-document-v1"

BGE_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
BGE_RERANKER_REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
BGE_RERANKER_PREPROCESSING = "bge-reranker-v2-m3-v1"
BGE_RERANKER_MAX_BATCH = 16
BGE_RERANKER_PAIR_TOKENS = 256
BGE_RERANKER_MAX_CANDIDATES = 200


@dataclass(frozen=True, slots=True, kw_only=True)
class BGERerankerExecutionProfileV1:
    """Runtime-only execution policy; it does not alter the frozen model profile."""

    device: Literal["cpu", "cuda"]
    batch_size: int
    allow_device_fallback: bool = False

    def __post_init__(self) -> None:
        if not 1 <= self.batch_size <= BGE_RERANKER_MAX_BATCH:
            raise ValueError("BGE reranker batch size exceeds the governed capability")
        if self.allow_device_fallback:
            raise ValueError("BGE reranker device fallback is not governed")


BGE_RERANKER_PRODUCTION_EXECUTION_V1 = BGERerankerExecutionProfileV1(
    device="cuda",
    batch_size=2,
    allow_device_fallback=False,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class BGERerankerInputObservationV1:
    """Read-only evidence for the exact pair consumed by the BGE runtime."""

    candidate_id: UUID
    rendered_input_hash: str
    retained_token_count: int
    query_token_count: int
    retained_query_token_count: int
    document_token_count: int
    retained_document_token_count: int
    query_truncated: bool
    document_truncated: bool


class MultilingualProviderReadinessProbe:
    """Bridge provider-owned lifecycle into the single Phase85Runtime registry."""

    def __init__(self, provider: Any) -> None:
        self._provider = provider

    async def probe(self, profile: object) -> ProviderReadinessResult:
        del profile
        await self._provider.initialize()
        result = await self._provider.readiness()
        return ProviderReadinessResult(
            available_locally=result.available_locally and result.exact_identity,
            loadable=result.loadable and result.exact_identity,
            initialized=result.initialized and result.exact_identity,
            reason_code=result.reason_code,
        )

    async def close(self) -> None:
        """Release the provider's executor/model reference during runtime shutdown."""
        await self._provider.close()


def multilingual_buildable_registrations(
    *,
    embedding_provider: BGEM3EmbeddingProvider,
    reranker: BGEMultilingualReranker,
    retrieval_service: object,
    profile_fingerprint: str,
) -> tuple[tuple[Phase85ProviderRegistration, ...], tuple[Phase85ServiceRegistration, ...]]:
    """Register implemented services only through BUILDABLE, never READY/ACTIVE."""
    providers = (
        Phase85ProviderRegistration(
            profile_id="multilingual_embedding",
            probe=MultilingualProviderReadinessProbe(embedding_provider),
        ),
        Phase85ProviderRegistration(
            profile_id="multilingual_reranker",
            probe=MultilingualProviderReadinessProbe(reranker),
        ),
    )
    services = (
        Phase85ServiceRegistration(
            capability_id="multilingual_retrieval",
            service=retrieval_service,
            ready=False,
            activate=False,
            generation_id=None,
            generation_active=False,
            profile_fingerprint=profile_fingerprint,
            exposed=False,
            behaviorally_verified=False,
            certified=False,
        ),
    )
    return providers, services


def preprocess_bge_m3_query(text: str) -> str:
    """Frozen query preprocessing: NFKC plus bounded whitespace, no prefix."""
    return _preprocess_text(text, "query")


def preprocess_bge_m3_document(text: str) -> str:
    """Frozen document preprocessing: NFKC plus bounded whitespace, no prefix."""
    return _preprocess_text(text, "document")


def _preprocess_text(text: str, name: str) -> str:
    if not isinstance(text, str):
        raise TypeError(f"{name} must be a string")
    value = " ".join(unicodedata.normalize("NFKC", text).split())
    if not value:
        raise ContractValidationError(f"{name} must not be empty")
    if len(value.encode("utf-8")) > 1_000_000:
        raise ContractValidationError(f"{name} exceeds the governed byte bound")
    return value


class BGEM3EmbeddingProvider:
    """Exact-revision BGE-M3 adapter with an ordered V2 batch contract."""

    def __init__(
        self,
        component: ModelProfileComponent,
        *,
        generation_id: UUID,
        cache_folder: Path,
        runtime_loader: Callable[[Path], Any] | None = None,
    ) -> None:
        _validate_embedding_component(component)
        if not isinstance(cache_folder, Path):
            raise TypeError("cache_folder must be a Path")
        self._component = component
        self._generation_id = generation_id
        self._cache_folder = cache_folder
        self._runtime_loader = runtime_loader
        self._runtime: Any | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._lock = asyncio.Lock()
        self._available = False
        self._loadable = False
        self._reason = "provider_not_initialized"
        self._profile = MultilingualEmbeddingProfile(
            provider=component.provider,
            model=component.model,
            revision=component.revision,
            profile=BGE_M3_QUERY_PREPROCESSING,
            generation_id=generation_id,
            dimension=BGE_M3_DIMENSION,
            normalized=True,
            distance_metric="cosine",
            preprocessing_digest=_digest(
                {
                    "query": BGE_M3_QUERY_PREPROCESSING,
                    "document": BGE_M3_DOCUMENT_PREPROCESSING,
                    "normalization": "l2",
                }
            ),
            languages=tuple(LanguageCode(item) for item in component.languages),
            scripts=tuple(ScriptCode(item) for item in component.scripts),
            capability_state=LanguageCapabilityState.UNAVAILABLE,
        )

    async def initialize(self) -> None:
        async with self._lock:
            if self._runtime is not None:
                return
            executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mnemo-bge-m3")
            try:
                runtime = await asyncio.get_running_loop().run_in_executor(
                    executor, self._load_runtime
                )
            except BaseException:
                executor.shutdown(wait=True, cancel_futures=True)
                self._reason = "provider_load_failed"
                raise
            self._executor = executor
            self._runtime = runtime
            self._available = True
            self._loadable = True
            self._reason = "provider_ready"

    async def close(self) -> None:
        async with self._lock:
            executor = self._executor
            self._executor = None
            self._runtime = None
            self._reason = "provider_closed"
            if executor is not None:
                await asyncio.to_thread(executor.shutdown, wait=True, cancel_futures=True)

    async def readiness(self) -> MultilingualProviderReadinessV2:
        return MultilingualProviderReadinessV2(
            available_locally=self._available,
            loadable=self._loadable,
            initialized=self._runtime is not None,
            exact_identity=True,
            reason_code=self._reason,
        )

    async def profile(self) -> MultilingualEmbeddingProfile:
        return replace(
            self._profile,
            capability_state=(
                LanguageCapabilityState.SUPPORTED
                if self._runtime is not None
                else LanguageCapabilityState.UNAVAILABLE
            ),
        )

    async def embed_query(self, *, query: str, language: str) -> MultilingualQueryEmbeddingV2:
        normalized = preprocess_bge_m3_query(query)
        vector = (await self._encode((normalized,)))[0]
        return MultilingualQueryEmbeddingV2(
            query_hash=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            language=LanguageCode(language),
            profile=await self.profile(),
            vector=vector,
            vector_hash=multilingual_vector_hash(vector),
        )

    async def embed_documents(
        self, inputs: tuple[MultilingualEmbeddingInputV2, ...]
    ) -> tuple[MultilingualEmbedding, ...]:
        if not isinstance(inputs, tuple):
            raise TypeError("inputs must be a tuple")
        if len(inputs) > BGE_M3_MAX_BATCH:
            raise ContractValidationError("BGE-M3 batch exceeds 32 inputs")
        if not inputs:
            return ()
        texts = tuple(preprocess_bge_m3_document(item.text) for item in inputs)
        vectors = await self._encode(texts)
        profile = await self.profile()
        now = datetime.now(UTC)
        return tuple(
            MultilingualEmbedding(
                embedding_id=multilingual_embedding_id(
                    notebook_id=item.source.notebook_id,
                    source_evidence_id=item.source.evidence_id,
                    source_hash=item.source.source_content_hash,
                    language=item.language,
                    profile=profile,
                ),
                notebook_id=item.source.notebook_id,
                source_evidence_id=item.source.evidence_id,
                source_hash=item.source.source_content_hash,
                language=item.language,
                profile=profile,
                vector=vector,
                vector_hash=multilingual_vector_hash(vector),
                created_at=now,
                source_reference=item.source,
            )
            for item, vector in zip(inputs, vectors, strict=True)
        )

    async def embed_documents_v3(
        self, inputs: tuple[MultilingualEmbeddingInputV3, ...]
    ) -> tuple[MultilingualEmbeddingV3, ...]:
        """Embed ordered authorized representations without narrowing language tags."""
        if not isinstance(inputs, tuple):
            raise TypeError("inputs must be a tuple")
        if len(inputs) > BGE_M3_MAX_BATCH:
            raise ContractValidationError("BGE-M3 batch exceeds 32 inputs")
        if not inputs:
            return ()
        texts = tuple(preprocess_bge_m3_document(item.text) for item in inputs)
        vectors = await self._encode(texts)
        profile = await self.profile()
        now = datetime.now(UTC)
        return tuple(
            MultilingualEmbeddingV3(
                embedding_id=multilingual_embedding_v3_id(
                    source=item.source,
                    representation=item.representation,
                    language=item.language,
                    profile=profile,
                ),
                source=item.source,
                representation=item.representation,
                language=item.language,
                profile=profile,
                vector=vector,
                vector_hash=multilingual_vector_hash(vector),
                source_hash=item.source.source_content_hash,
                representation_hash=item.representation.content_hash,
                language_observation_references=item.language_observation_references,
                script_observation_references=item.script_observation_references,
                created_at=now,
            )
            for item, vector in zip(inputs, vectors, strict=True)
        )

    async def _encode(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        runtime = self._runtime
        executor = self._executor
        if runtime is None or executor is None:
            raise LifecycleError("BGE-M3 provider accessed before initialization")
        values = await asyncio.get_running_loop().run_in_executor(executor, runtime.encode, texts)
        vectors = tuple(tuple(float(value) for value in row) for row in values)
        if len(vectors) != len(texts):
            raise IntegrityError("BGE-M3 returned missing or extra vectors")
        for vector in vectors:
            _validate_normalized_vector(vector, BGE_M3_DIMENSION)
        return vectors

    def _load_runtime(self) -> Any:
        snapshot = _resolve_snapshot(BGE_M3_MODEL, BGE_M3_REVISION, self._cache_folder)
        if self._runtime_loader is not None:
            runtime = self._runtime_loader(snapshot)
        else:
            try:
                sentence_transformers = importlib.import_module("sentence_transformers")
            except ImportError as error:
                raise DependencyUnavailableError(
                    "sentence-transformers multilingual extra is not installed"
                ) from error
            model = sentence_transformers.SentenceTransformer(
                str(snapshot),
                device="cpu",
                trust_remote_code=False,
                local_files_only=True,
            )
            model.max_seq_length = BGE_M3_MAX_CONTEXT
            runtime = _BGEM3Runtime(model)
        probe = tuple(tuple(float(value) for value in row) for row in runtime.encode(("probe",)))
        if len(probe) != 1:
            raise IntegrityError("BGE-M3 readiness probe returned invalid cardinality")
        _validate_normalized_vector(probe[0], BGE_M3_DIMENSION)
        return runtime


class BGEMultilingualReranker:
    """Independent multilingual reranker; it never falls back to V1 reranking."""

    def __init__(
        self,
        component: ModelProfileComponent,
        *,
        cache_folder: Path,
        execution: BGERerankerExecutionProfileV1 | None = None,
        runtime_loader: Callable[[Path], Any] | None = None,
    ) -> None:
        _validate_reranker_component(component)
        self._component = component
        self._cache_folder = cache_folder
        self._execution = execution or BGE_RERANKER_PRODUCTION_EXECUTION_V1
        self._runtime_loader = runtime_loader
        self._runtime: Any | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._lock = asyncio.Lock()
        self._available = False
        self._loadable = False
        self._reason = "provider_not_initialized"
        self._configuration_digest = _digest(
            {
                "model": BGE_RERANKER_MODEL,
                "revision": BGE_RERANKER_REVISION,
                "preprocessing": BGE_RERANKER_PREPROCESSING,
                "pair_max_length": BGE_RERANKER_PAIR_TOKENS,
                "device": self._execution.device,
                "batch": self._execution.batch_size,
                "allow_device_fallback": self._execution.allow_device_fallback,
            }
        )

    @property
    def configuration_digest(self) -> str:
        return self._configuration_digest

    @property
    def execution_profile(self) -> BGERerankerExecutionProfileV1:
        return self._execution

    def candidate_builder(
        self,
        resolver: Any,
        *,
        policy: RerankerPairPolicyV1 | RerankerPairPolicyV2 | None = None,
    ) -> RerankerCandidateBuilderV1:
        """Create the sole builder with the initialized exact tokenizer."""
        runtime = self._runtime
        if runtime is None:
            raise LifecycleError("reranker tokenizer accessed before initialization")
        return RerankerCandidateBuilderV1(
            resolver=resolver,
            tokenizer=runtime.tokenizer_adapter(),
            provider_id=self._component.provider,
            model_id=BGE_RERANKER_MODEL,
            model_revision=BGE_RERANKER_REVISION,
            provider_configuration_digest=self._configuration_digest,
            query_preprocessing_identity=BGE_M3_QUERY_PREPROCESSING,
            document_preprocessing_identity=BGE_M3_DOCUMENT_PREPROCESSING,
            preprocess_query=preprocess_bge_m3_query,
            preprocess_document=preprocess_bge_m3_document,
            policy=policy,
        )

    async def initialize(self) -> None:
        async with self._lock:
            if self._runtime is not None:
                return
            executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mnemo-bge-reranker")
            try:
                runtime = await asyncio.get_running_loop().run_in_executor(
                    executor, self._load_runtime
                )
            except BaseException:
                executor.shutdown(wait=True, cancel_futures=True)
                self._reason = "provider_load_failed"
                raise
            self._runtime = runtime
            self._executor = executor
            self._available = True
            self._loadable = True
            self._reason = "provider_ready"

    async def close(self) -> None:
        async with self._lock:
            executor = self._executor
            self._runtime = None
            self._executor = None
            self._reason = "provider_closed"
            if executor is not None:
                await asyncio.to_thread(executor.shutdown, wait=True, cancel_futures=True)

    async def readiness(self) -> MultilingualProviderReadinessV2:
        return MultilingualProviderReadinessV2(
            available_locally=self._available,
            loadable=self._loadable,
            initialized=self._runtime is not None,
            exact_identity=True,
            reason_code=self._reason,
        )

    async def profile(self) -> LanguageProviderProfile:
        return LanguageProviderProfile(
            provider=self._component.provider,
            model=BGE_RERANKER_MODEL,
            revision=BGE_RERANKER_REVISION,
            profile=BGE_RERANKER_PREPROCESSING,
            configuration_digest=self._configuration_digest,
            trust_class=ProcessingTrustClass.LOCAL,
            supported_languages=tuple(LanguageCode(item) for item in self._component.languages),
            supported_scripts=tuple(ScriptCode(item) for item in self._component.scripts),
            supported_directions=(),
            state=(
                LanguageCapabilityState.SUPPORTED
                if self._runtime is not None
                else LanguageCapabilityState.UNAVAILABLE
            ),
        )

    async def score(
        self, query: str, candidates: tuple[MultilingualCandidate, ...]
    ) -> tuple[MultilingualRerankScoreV2, ...]:
        normalized = _preprocess_text(query, "query")
        if len(candidates) > BGE_RERANKER_MAX_CANDIDATES:
            raise ContractValidationError("multilingual reranking accepts at most 200 candidates")
        texts = tuple(item.candidate.content for item in candidates)
        if any(text is None for text in texts):
            raise ContractValidationError("multilingual reranking requires bounded text content")
        runtime = self._runtime
        executor = self._executor
        if runtime is None or executor is None:
            raise LifecycleError("multilingual reranker accessed before initialization")
        scores = await asyncio.get_running_loop().run_in_executor(
            executor, runtime.predict, normalized, tuple(str(text) for text in texts)
        )
        values = tuple(float(score) for score in scores)
        if len(values) != len(candidates) or any(not math.isfinite(score) for score in values):
            raise IntegrityError("multilingual reranker returned malformed scores")
        return tuple(
            MultilingualRerankScoreV2(
                candidate_id=item.candidate.candidate_id,
                score=score,
                model=BGE_RERANKER_MODEL,
                revision=BGE_RERANKER_REVISION,
                preprocessing=BGE_RERANKER_PREPROCESSING,
            )
            for item, score in zip(candidates, values, strict=True)
        )

    async def rerank(
        self, query: str, candidates: tuple[MultilingualCandidate, ...]
    ) -> tuple[UUID, ...]:
        scores = await self.score(query, candidates)
        return tuple(
            item.candidate_id
            for item in sorted(scores, key=lambda item: (-item.score, str(item.candidate_id)))
        )

    async def score_candidates(
        self,
        *,
        query: str,
        candidates: tuple[MultilingualRerankCandidateV3, ...],
    ) -> tuple[MultilingualRerankScoreV2, ...]:
        """Score only builder-produced V3 candidates through the public adapter.

        V1 ``score`` remains available for compatibility.  V2 callers cannot
        supply arbitrary text: the typed candidate proves authorized evidence
        resolution and carries an input audit which the runtime recomputes.
        """
        normalized = _preprocess_text(query, "query")
        if len(candidates) > BGE_RERANKER_MAX_CANDIDATES:
            raise ContractValidationError("multilingual reranking accepts at most 200 candidates")
        if any(item.input_audit.query_hash != _text_hash(query) for item in candidates):
            raise ContractValidationError("reranker candidate query binding mismatch")
        provider_audits = tuple(
            item.input_audit
            for item in candidates
            if not isinstance(item.input_audit, V2TypedCandidateAuditV1)
        )
        if any(item.model_id != BGE_RERANKER_MODEL for item in provider_audits):
            raise ContractValidationError("reranker candidate model identity mismatch")
        if any(item.model_revision != BGE_RERANKER_REVISION for item in provider_audits):
            raise ContractValidationError("reranker candidate model revision mismatch")
        if any(
            item.provider_configuration_digest != self._configuration_digest
            for item in provider_audits
        ):
            raise ContractValidationError("reranker candidate configuration mismatch")
        runtime = self._runtime
        executor = self._executor
        if runtime is None or executor is None:
            raise LifecycleError("multilingual reranker accessed before initialization")
        scores = await asyncio.get_running_loop().run_in_executor(
            executor, runtime.predict_candidates, normalized, candidates
        )
        values = tuple(float(score) for score in scores)
        if len(values) != len(candidates) or any(not math.isfinite(score) for score in values):
            raise IntegrityError("multilingual reranker returned malformed scores")
        return tuple(
            MultilingualRerankScoreV2(
                candidate_id=item.candidate_id,
                score=score,
                model=BGE_RERANKER_MODEL,
                revision=BGE_RERANKER_REVISION,
                preprocessing=BGE_RERANKER_PREPROCESSING,
            )
            for item, score in zip(candidates, values, strict=True)
        )

    async def observe_candidate_inputs(
        self,
        *,
        query: str,
        candidates: tuple[MultilingualRerankCandidateV3, ...],
    ) -> tuple[BGERerankerInputObservationV1, ...]:
        """Observe the deterministic token pairs without scoring or changing state."""
        normalized = _preprocess_text(query, "query")
        runtime = self._runtime
        executor = self._executor
        if runtime is None or executor is None:
            raise LifecycleError("multilingual reranker accessed before initialization")
        return await asyncio.get_running_loop().run_in_executor(
            executor, runtime.observe_candidate_inputs, normalized, candidates
        )

    def _load_runtime(self) -> Any:
        snapshot = _resolve_snapshot(BGE_RERANKER_MODEL, BGE_RERANKER_REVISION, self._cache_folder)
        if self._runtime_loader is not None:
            runtime = self._runtime_loader(snapshot)
        else:
            try:
                module = importlib.import_module("sentence_transformers")
            except ImportError as error:
                raise DependencyUnavailableError(
                    "sentence-transformers multilingual reranking extra is not installed"
                ) from error
            if self._execution.device == "cuda":
                try:
                    torch = importlib.import_module("torch")
                except ImportError as error:
                    raise DependencyUnavailableError(
                        "governed CUDA reranker requires PyTorch"
                    ) from error
                if not bool(torch.cuda.is_available()):
                    raise DependencyUnavailableError(
                        "governed CUDA reranker is unavailable; CPU fallback is prohibited"
                    )
            model = module.CrossEncoder(
                str(snapshot),
                device=self._execution.device,
                max_length=BGE_RERANKER_PAIR_TOKENS,
                trust_remote_code=False,
                local_files_only=True,
                model_kwargs={"use_safetensors": True},
            )
            runtime = _BGERerankerRuntime(model, batch_size=self._execution.batch_size)
        probe = tuple(float(value) for value in runtime.predict("probe", ("probe",)))
        if len(probe) != 1 or not math.isfinite(probe[0]):
            raise IntegrityError("multilingual reranker readiness probe is invalid")
        return runtime


class _BGEM3Runtime:
    def __init__(self, model: Any) -> None:
        self._model = model

    def encode(self, texts: tuple[str, ...]) -> Any:
        return self._model.encode(
            list(texts),
            batch_size=min(BGE_M3_MAX_BATCH, len(texts)),
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )


class _BGERerankerRuntime:
    def __init__(self, model: Any, *, batch_size: int = BGE_RERANKER_MAX_BATCH) -> None:
        if not 1 <= batch_size <= BGE_RERANKER_MAX_BATCH:
            raise ValueError("BGE reranker runtime batch size is invalid")
        self._model = model
        self._batch_size = batch_size

    def predict(self, query: str, texts: tuple[str, ...]) -> tuple[float, ...]:
        values: list[float] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            raw = self._model.predict(
                [(query, text) for text in batch],
                batch_size=self._batch_size,
                show_progress_bar=False,
            )
            values.extend(float(value) for value in raw)
        return tuple(values)

    def tokenizer_adapter(self) -> _BGERerankerTokenizer:
        return _BGERerankerTokenizer(self._model.tokenizer)

    def predict_candidates(
        self,
        query: str,
        candidates: tuple[MultilingualRerankCandidateV3, ...],
    ) -> tuple[float, ...]:
        """Rebuild and verify the frozen pair input before provider execution."""
        rendered_pairs, _ = self._render_candidate_inputs(query, candidates)
        return self._score_rendered(rendered_pairs)

    def observe_candidate_inputs(
        self,
        query: str,
        candidates: tuple[MultilingualRerankCandidateV3, ...],
    ) -> tuple[BGERerankerInputObservationV1, ...]:
        """Return evidence from the same pair-rendering implementation used to score."""
        _, observations = self._render_candidate_inputs(query, candidates)
        return observations

    def _render_candidate_inputs(
        self,
        query: str,
        candidates: tuple[MultilingualRerankCandidateV3, ...],
    ) -> tuple[tuple[Any, ...], tuple[BGERerankerInputObservationV1, ...]]:
        tokenizer = self.tokenizer_adapter()
        rendered_pairs: list[Any] = []
        observations: list[BGERerankerInputObservationV1] = []
        for candidate in candidates:
            audit = candidate.input_audit
            query_ids = tokenizer.encode_without_special_tokens(query)
            if isinstance(audit, (RerankerInputAuditV2, V2TypedCandidateAuditV1)):
                contextual_text = render_contextual_provider_text(
                    title=candidate.title_metadata,
                    heading_path=candidate.heading_path,
                    semantic_text=candidate.semantic_text,
                )
                if _text_hash(contextual_text) != audit.contextual_text_hash:
                    raise IntegrityError("reranker candidate contextual hash mismatch")
                document = preprocess_bge_m3_document(contextual_text)
            else:
                document = preprocess_bge_m3_document(candidate.semantic_text)
            document_ids = tokenizer.encode_without_special_tokens(document)
            empty_pair = tokenizer.build_pair((), ())
            content_budget = BGE_RERANKER_PAIR_TOKENS - len(empty_pair.input_ids)
            kept_query = query_ids[: min(len(query_ids), 96, content_budget - 1)]
            kept_document = document_ids[: content_budget - len(kept_query)]
            rendered = tokenizer.build_pair(kept_query, kept_document)
            rendered_hash = _digest(
                {
                    "attention_mask": None
                    if rendered.attention_mask is None
                    else list(rendered.attention_mask),
                    "input_ids": list(rendered.input_ids),
                    "token_type_ids": None
                    if rendered.token_type_ids is None
                    else list(rendered.token_type_ids),
                }
            )
            if not isinstance(audit, V2TypedCandidateAuditV1) and (
                rendered_hash != audit.rendered_input_hash
            ):
                raise IntegrityError("reranker provider input differs from candidate audit")
            rendered_pairs.append(rendered)
            observations.append(
                BGERerankerInputObservationV1(
                    candidate_id=candidate.candidate_id,
                    rendered_input_hash=rendered_hash,
                    retained_token_count=len(rendered.input_ids),
                    query_token_count=len(query_ids),
                    retained_query_token_count=len(kept_query),
                    document_token_count=len(document_ids),
                    retained_document_token_count=len(kept_document),
                    query_truncated=len(kept_query) < len(query_ids),
                    document_truncated=len(kept_document) < len(document_ids),
                )
            )
        return tuple(rendered_pairs), tuple(observations)

    def _score_rendered(self, pairs: tuple[Any, ...]) -> tuple[float, ...]:
        """Score the exact audited token IDs; no second tokenizer truncation occurs."""
        if not pairs:
            return ()
        try:
            torch = importlib.import_module("torch")
        except ImportError as error:  # pragma: no cover - provider extra owns this
            raise DependencyUnavailableError("PyTorch reranker runtime is unavailable") from error
        values: list[float] = []
        self._model.eval()
        device = self._model.device
        for start in range(0, len(pairs), self._batch_size):
            batch = pairs[start : start + self._batch_size]
            records = []
            for item in batch:
                record: dict[str, list[int]] = {
                    "input_ids": list(item.input_ids),
                    "attention_mask": list(item.attention_mask or (1,) * len(item.input_ids)),
                }
                if item.token_type_ids is not None:
                    record["token_type_ids"] = list(item.token_type_ids)
                records.append(record)
            features = self._model.tokenizer.pad(records, padding=True, return_tensors="pt")
            features = {key: value.to(device) for key, value in features.items()}
            with torch.inference_mode():
                scores = self._model(features)["scores"]
                if self._model.activation_fn is not None:
                    scores = self._model.activation_fn(scores)
                if self._model.num_labels == 1 and scores.ndim > 1:
                    scores = scores.squeeze(-1)
            values.extend(float(item) for item in scores.detach().cpu().tolist())
        return tuple(values)


class _BGERerankerTokenizer:
    """Small deterministic adapter over the exact frozen HF tokenizer."""

    def __init__(self, tokenizer: Any) -> None:
        self._tokenizer = tokenizer

    @property
    def identity(self) -> str:
        return BGE_RERANKER_MODEL

    @property
    def revision(self) -> str:
        return BGE_RERANKER_REVISION

    @property
    def configuration_digest(self) -> str:
        return _digest(
            {
                "identity": self.identity,
                "revision": self.revision,
                "pair_max_tokens": BGE_RERANKER_PAIR_TOKENS,
                "query_max_content_tokens": 96,
            }
        )

    def encode_without_special_tokens(self, text: str) -> tuple[int, ...]:
        return tuple(
            int(item)
            for item in self._tokenizer.encode(text, add_special_tokens=False, truncation=False)
        )

    def build_pair(self, query_ids: tuple[int, ...], document_ids: tuple[int, ...]) -> Any:
        from mnemo.retrieval.reranker_candidates import RenderedRerankerPairV1

        build_inputs = getattr(self._tokenizer, "build_inputs_with_special_tokens", None)
        if callable(build_inputs):
            input_ids = tuple(
                int(item) for item in build_inputs(list(query_ids), list(document_ids))
            )
        else:
            # transformers 5 removed the public pair-building helper from the
            # slow XLM-R tokenizer. Freeze the documented XLM-R pair layout
            # (<s> A </s></s> B </s>) from exact tokenizer metadata rather
            # than re-tokenizing already-audited content.
            bos = getattr(self._tokenizer, "bos_token_id", None)
            sep = getattr(self._tokenizer, "sep_token_id", None)
            special_count = self._tokenizer.num_special_tokens_to_add(pair=True)
            if bos is None or sep is None or int(special_count) != 4:
                raise IntegrityError("frozen reranker tokenizer pair layout is unavailable")
            input_ids = (
                int(bos),
                *query_ids,
                int(sep),
                int(sep),
                *document_ids,
                int(sep),
            )
        create_token_types = getattr(self._tokenizer, "create_token_type_ids_from_sequences", None)
        token_types = (
            tuple(int(item) for item in create_token_types(list(query_ids), list(document_ids)))
            if callable(create_token_types)
            else tuple(0 for _ in input_ids)
        )
        return RenderedRerankerPairV1(
            input_ids=input_ids,
            attention_mask=tuple(1 for _ in input_ids),
            token_type_ids=token_types if token_types else None,
        )


def _resolve_snapshot(model: str, revision: str, cache_folder: Path) -> Path:
    """Resolve an exact operator-owned snapshot without consulting the network/hub API."""
    model_cache_name = "models--" + model.replace("/", "--")
    snapshot = (cache_folder / model_cache_name / "snapshots" / revision).resolve(strict=False)
    try:
        snapshot = snapshot.resolve(strict=True)
    except OSError as error:
        raise DependencyUnavailableError(
            "exact frozen model snapshot is unavailable locally"
        ) from error
    if snapshot.name != revision:
        raise IntegrityError("resolved model snapshot does not match frozen revision")
    required = (snapshot / "config.json", snapshot / "tokenizer_config.json")
    if any(not path.is_file() for path in required):
        raise IntegrityError("resolved model snapshot is incomplete")
    weights = tuple(snapshot.glob("*.safetensors")) + tuple(snapshot.glob("pytorch_model*.bin"))
    if not weights or any(path.stat().st_size < 1 for path in weights):
        raise IntegrityError("resolved model snapshot has no usable local weights")
    return snapshot


def _validate_embedding_component(component: ModelProfileComponent) -> None:
    expected = (
        component.provider == "sentence-transformers"
        and component.model == BGE_M3_MODEL
        and component.revision == BGE_M3_REVISION
        and component.dimensions == BGE_M3_DIMENSION
        and component.metric == "cosine"
        and component.normalization == "l2"
        and component.preprocessing == BGE_M3_QUERY_PREPROCESSING
        and component.max_batch == BGE_M3_MAX_BATCH
        and component.max_context_tokens == BGE_M3_MAX_CONTEXT
    )
    if not expected:
        raise ContractValidationError(
            "multilingual embedding component is not the frozen BGE-M3 profile"
        )


def _validate_reranker_component(component: ModelProfileComponent) -> None:
    expected = (
        component.provider == "sentence-transformers"
        and component.model == BGE_RERANKER_MODEL
        and component.revision == BGE_RERANKER_REVISION
        and component.preprocessing == BGE_RERANKER_PREPROCESSING
        and component.max_batch == BGE_RERANKER_MAX_BATCH
        and component.max_context_tokens == BGE_M3_MAX_CONTEXT
    )
    if not expected:
        raise ContractValidationError("multilingual reranker component is not the frozen profile")


def _validate_normalized_vector(vector: tuple[float, ...], dimension: int) -> None:
    if len(vector) != dimension or any(not math.isfinite(value) for value in vector):
        raise IntegrityError("multilingual embedding vector is malformed")
    norm = math.sqrt(sum(value * value for value in vector))
    if not math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=1e-5):
        raise IntegrityError("multilingual embedding vector is not L2 normalized")


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
