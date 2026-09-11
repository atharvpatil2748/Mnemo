"""WP-10 Stage-1 contracts: BUILDABLE without readiness or certification claims."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from mnemo.interfaces.errors import (
    ContractValidationError,
    DependencyUnavailableError,
    IntegrityError,
    LifecycleError,
)
from mnemo.models import (
    EvidenceAuthorityV2,
    EvidenceCandidateV2,
    EvidenceKindV2,
    EvidenceLineageOriginV3,
    FrozenMetadata,
    LanguageCapabilityState,
    LanguageCode,
    LanguageConfidence,
    LanguageDerivationKind,
    LanguageDetectionSource,
    LanguageEvidenceKindV2,
    LanguageEvidenceKindV3,
    LanguageEvidenceReferenceV2,
    LanguageEvidenceReferenceV3,
    LanguageProviderProfile,
    LanguageRegion,
    MultilingualEmbeddingInputV2,
    MultilingualPathSelection,
    MultilingualProviderReadinessV2,
    MultilingualRerankScoreV2,
    MultilingualRetrievalPath,
    ProcessingConsent,
    ProcessingPolicyDecision,
    ProcessingTrustClass,
    RetrievalCompleteness,
    ScriptCode,
    evidence_candidate_v2_id,
)
from mnemo.phase85 import (
    DeterministicTransliterationProvider,
    LanguageEvidenceInputV2,
    LanguageObservationDerivationBuilder,
    MultilingualEmbeddingGenerationBuilder,
    multilingual_generation_plan,
)
from mnemo.phase85.multilingual import _scope
from mnemo.phase85.profiles import ModelProfileComponent
from mnemo.retrieval import (
    BGEM3EmbeddingProvider,
    BGEMultilingualReranker,
    ConservativeENHIMRDetector,
    MultilingualRetrievalPlanner,
    SQLiteMultilingualDenseSource,
    multilingual_buildable_registrations,
    preprocess_bge_m3_document,
    preprocess_bge_m3_query,
)
from mnemo.retrieval.multilingual import CONSERVATIVE_DETECTOR_CONFIGURATION_DIGEST
from mnemo.retrieval.multilingual_providers import (
    BGE_RERANKER_MAX_BATCH,
    BGERerankerExecutionProfileV1,
    _BGEM3Runtime,
    _BGERerankerRuntime,
    _resolve_snapshot,
)
from mnemo.storage.sqlite import SQLiteStore

ACTOR = UUID(int=1)
NOTEBOOK = UUID(int=2)
SOURCE = UUID(int=3)
DOCUMENT = UUID(int=4)
VERSION = UUID(int=5)
GENERATION = UUID(int=6)
NOW = datetime(2026, 8, 29, tzinfo=UTC)


def _run(value):  # type: ignore[no-untyped-def]
    return asyncio.run(value)


def _reference(
    text: str,
    *,
    kind: LanguageEvidenceKindV2 = LanguageEvidenceKindV2.CANONICAL_CHUNK,
) -> LanguageEvidenceReferenceV2:
    derived = kind is not LanguageEvidenceKindV2.CANONICAL_CHUNK
    return LanguageEvidenceReferenceV2(
        notebook_id=NOTEBOOK,
        source_id=SOURCE,
        document_id=DOCUMENT,
        version_id=VERSION,
        kind=kind,
        evidence_id="chunk-1" if not derived else "derivation-1",
        source_content_hash=hashlib.sha256(text.encode()).hexdigest(),
        chunk_id="a" * 64 if not derived else None,
        occurrence_id=UUID(int=7) if derived else None,
        derivation_id=UUID(int=8) if derived else None,
        source_generation_id=UUID(int=9) if derived else None,
    )


def _embedding_component() -> ModelProfileComponent:
    return ModelProfileComponent(
        provider="sentence-transformers",
        model="BAAI/bge-m3",
        revision="5617a9f61b028005a4858fdac845db406aefb181",
        license="mit",
        dimensions=1024,
        metric="cosine",
        normalization="l2",
        preprocessing="bge-m3-query-v1",
        languages=("en", "hi", "mr"),
        scripts=("Latn", "Deva"),
        modalities=("text",),
        max_batch=32,
        max_context_tokens=8192,
    )


def _reranker_component() -> ModelProfileComponent:
    return ModelProfileComponent(
        provider="sentence-transformers",
        model="BAAI/bge-reranker-v2-m3",
        revision="953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
        license="apache-2.0",
        preprocessing="bge-reranker-v2-m3-v1",
        languages=("en", "hi", "mr"),
        scripts=("Latn", "Deva"),
        modalities=("text",),
        max_batch=16,
        max_context_tokens=8192,
    )


class _EmbeddingRuntime:
    def encode(self, texts: tuple[str, ...]):  # type: ignore[no-untyped-def]
        return tuple((1.0,) + (0.0,) * 1023 for _ in texts)


class _RerankerRuntime:
    def predict(self, query: str, texts: tuple[str, ...]) -> tuple[float, ...]:
        del query
        return tuple(float(len(text)) for text in texts)


class _RecordingCrossEncoder:
    def __init__(self) -> None:
        self.calls: list[tuple[list[tuple[str, str]], int]] = []

    def predict(
        self,
        pairs: list[tuple[str, str]],
        *,
        batch_size: int,
        show_progress_bar: bool,
    ) -> tuple[float, ...]:
        assert not show_progress_bar
        self.calls.append((pairs, batch_size))
        return tuple(float(len(document)) for _, document in pairs)


def test_language_evidence_reference_v2_is_typed_and_path_free() -> None:
    canonical = _reference("canonical")
    assert canonical.kind is LanguageEvidenceKindV2.CANONICAL_CHUNK
    assert "path" not in canonical.identity_payload()
    assert len(canonical.identity_digest) == 64
    with pytest.raises(ValueError, match="cannot claim derived"):
        replace(canonical, occurrence_id=UUID(int=99))
    with pytest.raises(ValueError, match="requires occurrence"):
        LanguageEvidenceReferenceV2(
            notebook_id=NOTEBOOK,
            source_id=SOURCE,
            document_id=DOCUMENT,
            version_id=VERSION,
            kind=LanguageEvidenceKindV2.OCR_REGION,
            evidence_id="ocr",
            source_content_hash="a" * 64,
        )


def test_language_evidence_references_enforce_each_provenance_shape() -> None:
    """Canonical, asset-derived, and derived identities cannot exchange provenance fields."""
    base_v2 = _reference("canonical")
    occurrence = UUID(int=20)
    derivation = UUID(int=21)
    generation = UUID(int=22)

    for kind in (LanguageEvidenceKindV2.OCR_REGION, LanguageEvidenceKindV2.VISION_DERIVATION):
        value = replace(
            base_v2,
            kind=kind,
            chunk_id=None,
            occurrence_id=occurrence,
            derivation_id=derivation,
            source_generation_id=generation,
        )
        assert value.occurrence_id == occurrence
        with pytest.raises(ValueError, match="cannot claim a canonical chunk"):
            replace(value, chunk_id="a" * 64)
        with pytest.raises(ValueError, match="requires source generation"):
            replace(value, source_generation_id=None)

    language_derivation = replace(
        base_v2,
        kind=LanguageEvidenceKindV2.LANGUAGE_DERIVATION,
        chunk_id=None,
        derivation_id=derivation,
        source_generation_id=generation,
    )
    assert language_derivation.derivation_id == derivation
    with pytest.raises(ValueError, match="requires derivation and generation"):
        replace(language_derivation, derivation_id=None)

    canonical_v3 = LanguageEvidenceReferenceV3.from_v2(base_v2)
    assert canonical_v3.chunk_id == base_v2.chunk_id
    with pytest.raises(ValueError, match="cannot claim derived lineage"):
        replace(canonical_v3, occurrence_id=occurrence)

    asset_v3 = replace(
        canonical_v3,
        lineage_origin=EvidenceLineageOriginV3.NATIVE_V3,
        kind=LanguageEvidenceKindV3.OCR_OCCURRENCE,
        chunk_id=None,
        occurrence_id=occurrence,
        derivation_id=derivation,
        source_generation_id=generation,
    )
    assert asset_v3.kind is LanguageEvidenceKindV3.OCR_OCCURRENCE
    with pytest.raises(ValueError, match="requires occurrence"):
        replace(asset_v3, occurrence_id=None)
    with pytest.raises(ValueError, match="cannot claim a parent"):
        replace(asset_v3, parent_evidence_reference_digest="a" * 64)

    native_derived = replace(
        canonical_v3,
        lineage_origin=EvidenceLineageOriginV3.NATIVE_V3,
        kind=LanguageEvidenceKindV3.REPRESENTATION_DERIVATION,
        chunk_id=None,
        derivation_id=derivation,
        source_generation_id=generation,
        parent_evidence_reference_digest="b" * 64,
    )
    assert native_derived.parent_evidence_reference_digest == "b" * 64
    with pytest.raises(ValueError, match="requires its parent"):
        replace(native_derived, parent_evidence_reference_digest=None)
    with pytest.raises(ValueError, match="no V2 upgrade form"):
        replace(native_derived, lineage_origin=EvidenceLineageOriginV3.LEGACY_V2_UPGRADE)


def test_governed_detector_is_conservative_and_uncalibrated() -> None:
    detector = ConservativeENHIMRDetector(clock=lambda: NOW)

    async def scenario() -> None:
        english = await detector.detect(
            actor_id=ACTOR, notebook_id=NOTEBOOK, target_id="en", text="the system and this"
        )
        hindi = await detector.detect(
            actor_id=ACTOR, notebook_id=NOTEBOOK, target_id="hi", text="यह है और"
        )
        marathi = await detector.detect(
            actor_id=ACTOR, notebook_id=NOTEBOOK, target_id="mr", text="हे आहे आणि"
        )
        ambiguous = await detector.detect(
            actor_id=ACTOR, notebook_id=NOTEBOOK, target_id="und", text="कर्म धर्म"
        )
        markerless = await detector.detect(
            actor_id=ACTOR, notebook_id=NOTEBOOK, target_id="latin", text="alpha beta"
        )
        assert [english.language.value, hindi.language.value, marathi.language.value] == [
            "en",
            "hi",
            "mr",
        ]
        assert ambiguous.language.value == markerless.language.value == "und"
        assert all(
            not item.confidence.calibrated
            for item in (english, hindi, marathi, ambiguous, markerless)
        )
        assert english.configuration_digest == CONSERVATIVE_DETECTOR_CONFIGURATION_DIGEST

    _run(scenario())


def test_bge_preprocessing_and_ordered_embedding_contract(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    snapshot = tmp_path / "5617a9f61b028005a4858fdac845db406aefb181"
    snapshot.mkdir()
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "mnemo.retrieval.multilingual_providers._resolve_snapshot",
        lambda model, revision, cache: snapshot,
    )
    provider = BGEM3EmbeddingProvider(
        _embedding_component(),
        generation_id=GENERATION,
        cache_folder=tmp_path,
        runtime_loader=lambda path: _EmbeddingRuntime(),
    )
    assert preprocess_bge_m3_query("  A\u00a0B ") == "A B"
    assert preprocess_bge_m3_document("  क  ख ") == "क ख"

    async def scenario() -> None:
        await provider.initialize()
        ready = await provider.readiness()
        assert ready.initialized and ready.exact_identity
        query = await provider.embed_query(query="the and", language="en")
        assert len(query.vector) == 1024 and query.vector[0] == 1.0
        first = MultilingualEmbeddingInputV2(
            source=_reference("first"), text="first", language=LanguageCode("en")
        )
        second = MultilingualEmbeddingInputV2(
            source=replace(_reference("second"), evidence_id="chunk-2", chunk_id="b" * 64),
            text="second",
            language=LanguageCode("mr"),
        )
        values = await provider.embed_documents((first, second))
        assert [item.source_evidence_id for item in values] == ["chunk-1", "chunk-2"]
        assert all(item.profile.vector_space == query.profile.vector_space for item in values)
        await provider.close()

    _run(scenario())
    with pytest.raises(ContractValidationError, match="frozen BGE-M3"):
        BGEM3EmbeddingProvider(
            _embedding_component().model_copy(update={"dimensions": 768}),
            generation_id=GENERATION,
            cache_folder=tmp_path,
        )


def test_bge_reranker_is_bounded_and_stably_tied(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    snapshot = tmp_path / "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
    snapshot.mkdir()
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "mnemo.retrieval.multilingual_providers._resolve_snapshot",
        lambda model, revision, cache: snapshot,
    )
    provider = BGEMultilingualReranker(
        _reranker_component(),
        cache_folder=tmp_path,
        runtime_loader=lambda path: _RerankerRuntime(),
    )

    async def scenario() -> None:
        await provider.initialize()
        candidates = (_candidate(1, "same"), _candidate(2, "longer text"))
        identities = await provider.rerank("query", candidates)
        assert identities == (
            candidates[1].candidate.candidate_id,
            candidates[0].candidate.candidate_id,
        )
        with pytest.raises(ContractValidationError, match="at most 200"):
            await provider.rerank("query", candidates * 101)
        await provider.close()

    _run(scenario())


def test_bge_typed_candidate_scoring_enforces_all_runtime_bindings(tmp_path: Path) -> None:
    """Typed candidate scoring rejects caller drift before provider execution."""
    provider = BGEMultilingualReranker(_reranker_component(), cache_folder=tmp_path)
    query = "governed query"

    class Runtime:
        scores: tuple[float, ...] = (0.75,)

        def predict_candidates(self, normalized, candidates):  # type: ignore[no-untyped-def]
            assert normalized == query
            assert len(candidates) == 1
            return self.scores

        def observe_candidate_inputs(self, normalized, candidates):  # type: ignore[no-untyped-def]
            return (normalized, candidates[0].candidate_id)

    runtime = Runtime()
    audit = SimpleNamespace(
        query_hash=hashlib.sha256(query.encode()).hexdigest(),
        model_id="BAAI/bge-reranker-v2-m3",
        model_revision="953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
        provider_configuration_digest=provider.configuration_digest,
        semantic_text_hash="a" * 64,
    )
    candidate = SimpleNamespace(candidate_id=UUID(int=10), input_audit=audit)

    async def scenario() -> None:
        with pytest.raises(LifecycleError, match="before initialization"):
            await provider.score_candidates(query=query, candidates=(candidate,))
        provider._runtime = runtime
        provider._executor = ThreadPoolExecutor(max_workers=1)
        scores = await provider.score_candidates(query=query, candidates=(candidate,))
        assert scores[0].candidate_id == candidate.candidate_id
        assert scores[0].score == 0.75
        assert await provider.observe_candidate_inputs(query=query, candidates=(candidate,)) == (
            query,
            candidate.candidate_id,
        )

        def changed(**values: object) -> SimpleNamespace:
            return SimpleNamespace(**{**vars(audit), **values})

        cases = (
            (changed(query_hash="b" * 64), "query binding"),
            (changed(model_id="wrong"), "model identity"),
            (changed(model_revision="wrong"), "model revision"),
            (changed(provider_configuration_digest="b" * 64), "configuration"),
        )
        for bad_audit, message in cases:
            with pytest.raises(ContractValidationError, match=message):
                await provider.score_candidates(
                    query=query,
                    candidates=(
                        SimpleNamespace(
                            candidate_id=candidate.candidate_id,
                            input_audit=bad_audit,
                        ),
                    ),
                )
        with pytest.raises(ContractValidationError, match="at most 200"):
            await provider.score_candidates(query=query, candidates=(candidate,) * 201)
        with pytest.raises(ContractValidationError, match="query must not be empty"):
            await provider.score_candidates(query=" ", candidates=())

        runtime.scores = ()
        with pytest.raises(IntegrityError, match="malformed scores"):
            await provider.score_candidates(query=query, candidates=(candidate,))
        runtime.scores = (float("nan"),)
        with pytest.raises(IntegrityError, match="malformed scores"):
            await provider.score_candidates(query=query, candidates=(candidate,))
        await provider.close()
        with pytest.raises(LifecycleError, match="before initialization"):
            await provider.observe_candidate_inputs(query=query, candidates=(candidate,))

    _run(scenario())


def test_bge_provider_lifecycle_and_embedding_failures_are_explicit(tmp_path: Path) -> None:
    """Provider lifecycle and malformed-vector branches fail closed without fallback."""
    provider = BGEM3EmbeddingProvider(
        _embedding_component(),
        generation_id=GENERATION,
        cache_folder=tmp_path,
        runtime_loader=lambda path: _EmbeddingRuntime(),
    )

    async def scenario() -> None:
        with pytest.raises(LifecycleError, match="before initialization"):
            await provider.embed_query(query="query", language="en")
        assert await provider.embed_documents(()) == ()
        with pytest.raises(TypeError, match="tuple"):
            await provider.embed_documents([])  # type: ignore[arg-type]
        with pytest.raises(ContractValidationError, match="batch exceeds"):
            await provider.embed_documents(tuple(_embedding_input(index) for index in range(33)))

        provider._runtime = _MalformedEmbeddingRuntime(((1.0,),))
        provider._executor = ThreadPoolExecutor(max_workers=1)
        with pytest.raises(IntegrityError, match="malformed"):
            await provider.embed_query(query="query", language="en")
        await provider.close()
        assert (await provider.readiness()).reason_code == "provider_closed"

    _run(scenario())


def test_bge_provider_initialization_and_input_boundaries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """BGE adapters reject invalid input and preserve explicit lifecycle failure state."""
    with pytest.raises(TypeError, match="query must be a string"):
        preprocess_bge_m3_query(1)  # type: ignore[arg-type]
    with pytest.raises(ContractValidationError, match="byte bound"):
        preprocess_bge_m3_document("x" * 1_000_001)
    with pytest.raises(TypeError, match="cache_folder"):
        BGEM3EmbeddingProvider(
            _embedding_component(),
            generation_id=GENERATION,
            cache_folder="cache",  # type: ignore[arg-type]
        )

    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    monkeypatch.setattr(
        "mnemo.retrieval.multilingual_providers._resolve_snapshot",
        lambda *_args: snapshot,
    )
    failed = BGEM3EmbeddingProvider(
        _embedding_component(),
        generation_id=GENERATION,
        cache_folder=tmp_path,
        runtime_loader=lambda _path: (_ for _ in ()).throw(RuntimeError("load failed")),
    )
    healthy = BGEM3EmbeddingProvider(
        _embedding_component(),
        generation_id=GENERATION,
        cache_folder=tmp_path,
        runtime_loader=lambda _path: _EmbeddingRuntime(),
    )
    reranker = BGEMultilingualReranker(_reranker_component(), cache_folder=tmp_path)

    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="load failed"):
            await failed.initialize()
        assert (await failed.readiness()).reason_code == "provider_load_failed"
        await healthy.initialize()
        runtime = healthy._runtime
        await healthy.initialize()
        assert healthy._runtime is runtime
        with pytest.raises(LifecycleError, match="tokenizer"):
            reranker.candidate_builder(object())
        assert reranker.execution_profile.batch_size == 2
        assert (await reranker.profile()).state is LanguageCapabilityState.UNAVAILABLE
        await healthy.close()

    _run(scenario())

    class RecordingModel:
        def encode(self, texts, **kwargs):  # type: ignore[no-untyped-def]
            assert texts == ["a", "b"]
            assert kwargs["normalize_embeddings"] is True
            return ((1.0,), (2.0,))

    assert _BGEM3Runtime(RecordingModel()).encode(("a", "b")) == ((1.0,), (2.0,))


def test_embedding_generation_builder_requires_governed_language_and_ordered_batches() -> None:
    """The projection builder authorizes inputs and fails closed on provider drift."""
    source = _reference("governed text")
    input_value = LanguageEvidenceInputV2(
        actor_id=ACTOR,
        source=source,
        text="governed text",
        declared_language=LanguageCode("en"),
        declared_script=ScriptCode("Latn"),
        metadata_source=LanguageDetectionSource.EXPLICIT_METADATA,
    )

    class Store:
        def __init__(self) -> None:
            self.values: list[object] = []

        async def put_multilingual_embedding(self, value: object) -> None:
            self.values.append(value)

    class Authorizer:
        allowed = True

        async def authorize_language_evidence(self, actor_id, evidence):  # type: ignore[no-untyped-def]
            return self.allowed and actor_id == ACTOR and evidence == source

    class Provider:
        def __init__(self, generation_id: UUID, *, cardinality: int = 1) -> None:
            self.generation_id = generation_id
            self.cardinality = cardinality

        async def profile(self):  # type: ignore[no-untyped-def]
            return SimpleNamespace(generation_id=self.generation_id)

        async def embed_documents(self, inputs):  # type: ignore[no-untyped-def]
            return tuple(
                SimpleNamespace(embedding_id=UUID(int=index + 1))
                for index in range(self.cardinality)
            )

    async def scenario() -> None:
        store = Store()
        authorizer = Authorizer()
        provider = Provider(GENERATION)
        builder = MultilingualEmbeddingGenerationBuilder(
            store=store,
            provider=provider,
            authorizer=authorizer,
            generation_id=GENERATION,
            inputs=(input_value,),
        )
        result = await builder.build(GENERATION)
        assert result.succeeded_count == 1 and len(store.values) == 1
        with pytest.raises(IntegrityError, match="generation identity"):
            await builder.build(UUID(int=99))
        provider.generation_id = UUID(int=98)
        with pytest.raises(IntegrityError, match="another generation"):
            await builder.build(GENERATION)
        provider.generation_id = GENERATION
        authorizer.allowed = False
        with pytest.raises(IntegrityError, match="authorization"):
            await builder.build(GENERATION)
        authorizer.allowed = True
        provider.cardinality = 0
        with pytest.raises(IntegrityError, match="batch cardinality"):
            await builder.build(GENERATION)
        unobserved = replace(
            input_value,
            declared_language=None,
            declared_script=None,
            metadata_source=None,
        )
        with pytest.raises(IntegrityError, match="requires a persisted"):
            await MultilingualEmbeddingGenerationBuilder(
                store=store,
                provider=Provider(GENERATION),
                authorizer=authorizer,
                generation_id=GENERATION,
                inputs=(unobserved,),
            ).build(GENERATION)

    _run(scenario())


def test_multilingual_value_models_reject_invalid_confidence_profile_and_readiness() -> None:
    """Core multilingual value objects keep confidence, capabilities, and scores well-formed."""
    assert LanguageConfidence(value=0.5, calibrated=True).value == 0.5
    with pytest.raises(ValueError, match="between 0 and 1"):
        LanguageConfidence(value=1.1, calibrated=True)
    with pytest.raises(ValueError, match="positive"):
        LanguageRegion(order=0)
    profile = LanguageProviderProfile(
        provider="provider",
        model="model",
        revision="revision",
        profile="profile",
        configuration_digest="a" * 64,
        trust_class=ProcessingTrustClass.LOCAL,
        supported_languages=(LanguageCode("en"),),
        supported_scripts=(ScriptCode("Latn"),),
        supported_directions=("en->hi",),
        state=LanguageCapabilityState.SUPPORTED,
    )
    assert profile.supports_direction(LanguageCode("en"), LanguageCode("hi"))
    with pytest.raises(ValueError, match="supported_languages"):
        replace(profile, supported_languages=(LanguageCode("en"), LanguageCode("en")))
    with pytest.raises(ValueError, match="supported_scripts"):
        replace(profile, supported_scripts=(ScriptCode("Latn"), ScriptCode("Latn")))
    with pytest.raises(ValueError, match="loadable"):
        MultilingualProviderReadinessV2(
            available_locally=False,
            loadable=True,
            initialized=False,
            exact_identity=False,
        )
    with pytest.raises(ValueError, match="exact frozen"):
        MultilingualProviderReadinessV2(
            available_locally=True,
            loadable=True,
            initialized=True,
            exact_identity=False,
        )
    with pytest.raises(ValueError, match="score"):
        MultilingualRerankScoreV2(
            candidate_id=UUID(int=1),
            score=float("nan"),
            model="model",
            revision="revision",
            preprocessing="profile",
        )


class _MalformedEmbeddingRuntime:
    def __init__(self, values: tuple[tuple[float, ...], ...]) -> None:
        self._values = values

    def encode(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        del texts
        return self._values


def _embedding_input(index: int) -> MultilingualEmbeddingInputV2:
    return MultilingualEmbeddingInputV2(
        source=replace(
            _reference(f"text-{index}"),
            evidence_id=f"chunk-{index}",
            chunk_id=f"{index + 1:064x}",
        ),
        text=f"text-{index}",
        language=LanguageCode("en"),
    )


def test_reranker_execution_policy_and_batched_runtime() -> None:
    """The local reranker honors governed batch boundaries and rejects fallback."""
    with pytest.raises(ValueError, match="batch size"):
        BGERerankerExecutionProfileV1(device="cpu", batch_size=0)
    with pytest.raises(ValueError, match="fallback"):
        BGERerankerExecutionProfileV1(device="cpu", batch_size=1, allow_device_fallback=True)
    with pytest.raises(ValueError, match="batch size"):
        _BGERerankerRuntime(_RecordingCrossEncoder(), batch_size=BGE_RERANKER_MAX_BATCH + 1)

    model = _RecordingCrossEncoder()
    runtime = _BGERerankerRuntime(model, batch_size=2)
    assert runtime.predict("q", ("a", "bb", "ccc")) == (1.0, 2.0, 3.0)
    assert [len(pairs) for pairs, _ in model.calls] == [2, 1]
    assert all(batch_size == 2 for _, batch_size in model.calls)


def test_reranker_runtime_audits_exact_pairs_and_scores_governed_batches(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Exact token pairs, truncation evidence, and tensor scoring share one path."""

    class Value:
        def __init__(self, values):  # type: ignore[no-untyped-def]
            self.values = values
            self.ndim = 2

        def to(self, device: str):  # type: ignore[no-untyped-def]
            assert device == "cuda"
            return self

        def squeeze(self, _axis: int):
            self.ndim = 1
            return self

        def detach(self):
            return self

        def cpu(self):
            return self

        def tolist(self):  # type: ignore[no-untyped-def]
            return self.values

    class Tokenizer:
        bos_token_id = 0
        sep_token_id = 2

        @staticmethod
        def encode(text: str, **_kwargs: object) -> list[int]:
            return list(range(10, 10 + len(text.split())))

        @staticmethod
        def num_special_tokens_to_add(*, pair: bool) -> int:
            assert pair is True
            return 4

        @staticmethod
        def pad(records, **_kwargs):  # type: ignore[no-untyped-def]
            assert records
            return {"input_ids": Value([record["input_ids"] for record in records])}

    class Model:
        tokenizer = Tokenizer()
        device = "cuda"
        activation_fn = staticmethod(lambda scores: scores)
        num_labels = 1

        def eval(self) -> None:
            self.evaluated = True

        def __call__(self, features):  # type: ignore[no-untyped-def]
            return {"scores": Value([float(len(item)) for item in features["input_ids"].values])}

    class Inference:
        def __enter__(self):
            return None

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(inference_mode=Inference))
    runtime = _BGERerankerRuntime(Model(), batch_size=1)
    tokenizer = runtime.tokenizer_adapter()
    assert tokenizer.identity == "BAAI/bge-reranker-v2-m3"
    assert len(tokenizer.configuration_digest) == 64
    document = preprocess_bge_m3_document("document text")
    rendered = tokenizer.build_pair(
        tokenizer.encode_without_special_tokens("query"),
        tokenizer.encode_without_special_tokens(document),
    )
    rendered_hash = hashlib.sha256(
        json.dumps(
            {
                "attention_mask": list(rendered.attention_mask),
                "input_ids": list(rendered.input_ids),
                "token_type_ids": list(rendered.token_type_ids),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    candidate = SimpleNamespace(
        candidate_id=uuid4(),
        semantic_text="document text",
        title_metadata=None,
        heading_path=(),
        input_audit=SimpleNamespace(rendered_input_hash=rendered_hash),
    )
    observations = runtime.observe_candidate_inputs("query", (candidate,))
    assert observations[0].rendered_input_hash == rendered_hash
    assert observations[0].query_truncated is False
    scores = runtime.predict_candidates("query", (candidate,))
    assert scores == (float(len(rendered.input_ids)),)
    assert runtime.predict_candidates("query", ()) == ()
    candidate.input_audit.rendered_input_hash = "0" * 64
    with pytest.raises(IntegrityError, match="provider input differs"):
        runtime.observe_candidate_inputs("query", (candidate,))


def test_exact_snapshot_resolution_is_offline_and_integrity_bound(tmp_path: Path) -> None:
    """Snapshot resolution rejects absence, incomplete metadata, and unusable weights."""
    revision = "a" * 40
    with pytest.raises(DependencyUnavailableError, match="unavailable locally"):
        _resolve_snapshot("owner/model", revision, tmp_path)

    snapshot = tmp_path / "models--owner--model" / "snapshots" / revision
    snapshot.mkdir(parents=True)
    with pytest.raises(IntegrityError, match="incomplete"):
        _resolve_snapshot("owner/model", revision, tmp_path)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    (snapshot / "tokenizer_config.json").write_text("{}", encoding="utf-8")
    with pytest.raises(IntegrityError, match="usable local weights"):
        _resolve_snapshot("owner/model", revision, tmp_path)
    (snapshot / "model.safetensors").write_bytes(b"weights")
    assert _resolve_snapshot("owner/model", revision, tmp_path) == snapshot.resolve()


def _candidate(index: int, text: str):  # type: ignore[no-untyped-def]
    document = UUID(int=100 + index)
    version = UUID(int=200 + index)
    identity = f"chunk-{index}"
    candidate = EvidenceCandidateV2(
        candidate_id=evidence_candidate_v2_id(
            kind=EvidenceKindV2.CANONICAL_CHUNK,
            document_id=document,
            version_id=version,
            authoritative_id=identity,
        ),
        notebook_id=NOTEBOOK,
        source_id=SOURCE,
        document_id=document,
        version_id=version,
        kind=EvidenceKindV2.CANONICAL_CHUNK,
        authority=EvidenceAuthorityV2.ORIGINAL,
        authoritative_id=identity,
        chunk_id=f"{index:064x}",
        content=text,
        completeness=RetrievalCompleteness.COMPLETE,
    )
    selection = MultilingualPathSelection(
        path=MultilingualRetrievalPath.MULTILINGUAL_DENSE,
        target_language=LanguageCode("en"),
        state=LanguageCapabilityState.SUPPORTED,
        profile="fixture",
        reason="fixture",
    )
    from mnemo.models import MultilingualCandidate

    return MultilingualCandidate(
        candidate=candidate,
        evidence_language=LanguageCode("en"),
        evidence_script=ScriptCode("Latn"),
        paths=(selection,),
        source_ranks=FrozenMetadata({"multilingual_dense": index}),
        fused_score=1.0,
        final_rank=index,
    )


class _LanguageAuthorizer:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed

    async def authorize_language_evidence(
        self, actor_id: UUID, source: LanguageEvidenceReferenceV2
    ) -> bool:
        return self.allowed and actor_id == ACTOR and source.notebook_id == NOTEBOOK


def test_derivation_builder_is_authorized_and_idempotent(tmp_path: Path) -> None:
    text = "यह है और"
    reference = _reference(text)
    profile = LanguageProviderProfile(
        provider="mnemo-local",
        model="deterministic-devanagari-transliteration",
        revision="1",
        profile="devanagari-latin-derived-v1",
        configuration_digest="a" * 64,
        trust_class=ProcessingTrustClass.LOCAL,
        supported_languages=(LanguageCode("hi"), LanguageCode("mr")),
        supported_scripts=(ScriptCode("Deva"), ScriptCode("Latn")),
        supported_directions=(),
        state=LanguageCapabilityState.SUPPORTED,
    )

    async def scenario() -> None:
        store = SQLiteStore(tmp_path / "isolated-stage1.db")
        await store.open()
        transformer = DeterministicTransliterationProvider(profile)
        await transformer.initialize()
        builder = LanguageObservationDerivationBuilder(
            store=store,
            detector=ConservativeENHIMRDetector(clock=lambda: NOW),
            authorizer=_LanguageAuthorizer(),
            transformer=transformer,
            generation_id=GENERATION,
            preprocessing_digest="b" * 64,
            consent=ProcessingConsent(
                decision=ProcessingPolicyDecision.ALLOWED,
                policy_version="wp10-stage1/1",
                decided_at=NOW,
                reason_code="local-deterministic",
            ),
            inputs=(
                LanguageEvidenceInputV2(
                    actor_id=ACTOR,
                    source=reference,
                    text=text,
                    declared_language=LanguageCode("hi"),
                    declared_script=ScriptCode("Deva"),
                    metadata_source=LanguageDetectionSource.PARSER,
                ),
            ),
        )
        first = await builder.build(GENERATION)
        second = await builder.build(GENERATION)
        assert first == second and first.failed_count == 0
        denied = replace(builder._inputs[0], actor_id=UUID(int=99))
        denied_builder = LanguageObservationDerivationBuilder(
            store=store,
            detector=ConservativeENHIMRDetector(clock=lambda: NOW),
            authorizer=_LanguageAuthorizer(),
            transformer=transformer,
            generation_id=GENERATION,
            preprocessing_digest="b" * 64,
            consent=builder._consent,
            inputs=(denied,),
        )
        with pytest.raises(IntegrityError, match="authorization"):
            await denied_builder.build(GENERATION)
        await store.close()

    _run(scenario())


class _Catalog:
    def __init__(
        self,
        references: tuple[LanguageEvidenceReferenceV2, ...],
        candidates: dict[str, EvidenceCandidateV2],
    ) -> None:
        self.references = references
        self.candidates = candidates
        self.authorized_before_resolve = False

    async def authorized_language_sources(
        self, *, actor_id: UUID, notebook_id: UUID, limit: int
    ) -> tuple[LanguageEvidenceReferenceV2, ...]:
        assert actor_id == ACTOR and notebook_id == NOTEBOOK and limit == 10_000
        self.authorized_before_resolve = True
        return self.references

    async def resolve_language_evidence(
        self, *, actor_id: UUID, source: LanguageEvidenceReferenceV2
    ) -> EvidenceCandidateV2:
        assert self.authorized_before_resolve and actor_id == ACTOR
        return self.candidates[source.evidence_id]


def test_sqlite_dense_source_authorizes_before_bounded_scoring(
    monkeypatch,
    tmp_path: Path,  # type: ignore[no-untyped-def]
) -> None:
    from mnemo.models import (
        AdvancedRetrievalMode,
        DeduplicationPolicy,
        EvidenceRepresentation,
        ExpansionPolicy,
        PositionalScopeV2,
        RankingPolicyV2,
        RetrievalBudgetsV2,
        RetrievalPlanV2,
        RetrievalScopeV2,
    )

    snapshot = tmp_path / "5617a9f61b028005a4858fdac845db406aefb181"
    snapshot.mkdir()
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "mnemo.retrieval.multilingual_providers._resolve_snapshot",
        lambda model, revision, cache: snapshot,
    )
    provider = BGEM3EmbeddingProvider(
        _embedding_component(),
        generation_id=GENERATION,
        cache_folder=tmp_path,
        runtime_loader=lambda path: _EmbeddingRuntime(),
    )
    first_text, second_text = "the first and", "the second and"
    first = _reference(first_text)
    second = replace(
        _reference(second_text),
        source_id=UUID(int=30),
        document_id=UUID(int=31),
        version_id=UUID(int=32),
        evidence_id="chunk-2",
        chunk_id="b" * 64,
    )
    first_candidate = _evidence_for_reference(first, first_text)
    second_candidate = _evidence_for_reference(second, second_text)
    catalog = _Catalog(
        (first, second),
        {first.evidence_id: first_candidate, second.evidence_id: second_candidate},
    )

    async def scenario() -> None:
        store = SQLiteStore(tmp_path / "isolated-dense.db")
        await store.open()
        await provider.initialize()
        embeddings = await provider.embed_documents(
            (
                MultilingualEmbeddingInputV2(
                    source=first, text=first_text, language=LanguageCode("en")
                ),
                MultilingualEmbeddingInputV2(
                    source=second, text=second_text, language=LanguageCode("en")
                ),
            )
        )
        for embedding in embeddings:
            await store.put_multilingual_embedding(embedding)
        dense = SQLiteMultilingualDenseSource(store=store, provider=provider, catalog=catalog)
        detector = ConservativeENHIMRDetector(clock=lambda: NOW)
        plan = await MultilingualRetrievalPlanner(detector).plan(
            actor_id=ACTOR,
            notebook_id=NOTEBOOK,
            query="the query and",
            base_plan=RetrievalPlanV2(
                query="the query and",
                mode=AdvancedRetrievalMode.RANKED,
                scope=RetrievalScopeV2(notebook_id=NOTEBOOK),
                position=PositionalScopeV2(),
                representations=(EvidenceRepresentation.MULTILINGUAL_TEXT,),
                budgets=RetrievalBudgetsV2(
                    recall_limit=10,
                    expansion_limit=0,
                    fusion_limit=10,
                    rerank_limit=10,
                    result_limit=2,
                    max_serialized_bytes=100_000,
                    max_content_characters=10_000,
                ),
                expansion_policy=ExpansionPolicy.NONE,
                deduplication_policy=DeduplicationPolicy.AUTHORITATIVE_IDENTITY,
                ranking_policy=RankingPolicyV2.SOURCE_RANK_FUSION,
            ),
            target_languages=(LanguageCode("en"),),
            dense_profile=LanguageProviderProfile(
                provider="sentence-transformers",
                model="BAAI/bge-m3",
                revision="5617a9f61b028005a4858fdac845db406aefb181",
                profile="bge-m3-query-v1",
                configuration_digest="c" * 64,
                trust_class=ProcessingTrustClass.LOCAL,
                supported_languages=(LanguageCode("en"), LanguageCode("hi"), LanguageCode("mr")),
                supported_scripts=(ScriptCode("Latn"), ScriptCode("Deva")),
                supported_directions=(),
                state=LanguageCapabilityState.SUPPORTED,
            ),
            translation_profile=None,
            transliteration_enabled=False,
        )
        values = await dense.retrieve(plan, MultilingualRetrievalPath.MULTILINGUAL_DENSE, "en", 2)
        assert catalog.authorized_before_resolve
        identities = [item.candidate.authoritative_id for item in values]
        assert sorted(identities) == ["chunk-1", "chunk-2"]
        repeated = await dense.retrieve(plan, MultilingualRetrievalPath.MULTILINGUAL_DENSE, "en", 2)
        assert [item.candidate.authoritative_id for item in repeated] == identities
        with pytest.raises(ContractValidationError, match="through 1000"):
            await dense.retrieve(plan, MultilingualRetrievalPath.MULTILINGUAL_DENSE, "en", 1001)
        await provider.close()
        await store.close()

    _run(scenario())


def _evidence_for_reference(
    reference: LanguageEvidenceReferenceV2, text: str
) -> EvidenceCandidateV2:
    return EvidenceCandidateV2(
        candidate_id=evidence_candidate_v2_id(
            kind=EvidenceKindV2.CANONICAL_CHUNK,
            document_id=reference.document_id,
            version_id=reference.version_id,
            authoritative_id=reference.evidence_id,
        ),
        notebook_id=reference.notebook_id,
        source_id=reference.source_id,
        document_id=reference.document_id,
        version_id=reference.version_id,
        kind=EvidenceKindV2.CANONICAL_CHUNK,
        authority=EvidenceAuthorityV2.ORIGINAL,
        authoritative_id=reference.evidence_id,
        chunk_id=reference.chunk_id,
        content=text,
        completeness=RetrievalCompleteness.COMPLETE,
    )


def test_runtime_registration_stops_at_buildable(
    monkeypatch,
    tmp_path: Path,  # type: ignore[no-untyped-def]
) -> None:
    from mnemo import MnemoConfig, Phase85Runtime

    embed_snapshot = tmp_path / "5617a9f61b028005a4858fdac845db406aefb181"
    rerank_snapshot = tmp_path / "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
    for snapshot in (embed_snapshot, rerank_snapshot):
        snapshot.mkdir()
        (snapshot / "config.json").write_text("{}", encoding="utf-8")

    def resolve(model: str, revision: str, cache: Path) -> Path:
        del model, cache
        return embed_snapshot if revision.startswith("5617") else rerank_snapshot

    monkeypatch.setattr("mnemo.retrieval.multilingual_providers._resolve_snapshot", resolve)
    embedding = BGEM3EmbeddingProvider(
        _embedding_component(),
        generation_id=GENERATION,
        cache_folder=tmp_path,
        runtime_loader=lambda path: _EmbeddingRuntime(),
    )
    reranker = BGEMultilingualReranker(
        _reranker_component(),
        cache_folder=tmp_path,
        runtime_loader=lambda path: _RerankerRuntime(),
    )
    root = Path(__file__).resolve().parents[3]
    config = MnemoConfig.from_file(root / "mnemo.toml")
    identity_runtime = Phase85Runtime(config, engine_ready=False)
    providers, services = multilingual_buildable_registrations(
        embedding_provider=embedding,
        reranker=reranker,
        retrieval_service=object(),
        profile_fingerprint=identity_runtime.active_profile.fingerprint,
    )
    runtime = Phase85Runtime(
        config,
        engine_ready=True,
        provider_registrations=providers,
        service_registrations=services,
    )
    _run(runtime.initialize())
    state = runtime.capability_status("multilingual_retrieval").state
    assert state.buildable
    assert not state.ready
    assert not state.active
    assert not state.exposed
    assert not state.behaviorally_verified
    assert not state.certified
    _run(runtime.shutdown())
    assert not _run(embedding.readiness()).initialized
    assert not _run(reranker.readiness()).initialized


def test_generation_plan_is_deterministic_and_dependency_bound() -> None:
    first = multilingual_generation_plan(
        profile_fingerprint="a" * 64,
        source_version_ids=(VERSION,),
        detector_digest=CONSERVATIVE_DETECTOR_CONFIGURATION_DIGEST,
        language_preprocessing_digest="b" * 64,
    )
    second = multilingual_generation_plan(
        profile_fingerprint="a" * 64,
        source_version_ids=(VERSION,),
        detector_digest=CONSERVATIVE_DETECTOR_CONFIGURATION_DIGEST,
        language_preprocessing_digest="b" * 64,
    )
    assert first == second
    assert first.language_text.capability == "language_text"
    assert first.language_text.source_generation_ids == (first.language_derivation.generation_id,)
    assert first.multilingual_vector.capability == "multilingual_vector"
    assert first.multilingual_vector.source_generation_ids == (
        first.multilingual_embedding.generation_id,
    )
    assert first.multilingual_embedding.dimensions == 1024


def test_language_evidence_input_and_scope_contracts_fail_closed() -> None:
    source = _reference("source text")
    with pytest.raises(ValueError, match="must not be empty"):
        LanguageEvidenceInputV2(actor_id=ACTOR, source=source, text=" ")
    with pytest.raises(ValueError, match="source hash"):
        LanguageEvidenceInputV2(actor_id=ACTOR, source=source, text="different")
    with pytest.raises(ValueError, match="provide language, script, and source together"):
        LanguageEvidenceInputV2(
            actor_id=ACTOR,
            source=source,
            text="source text",
            declared_language=LanguageCode("en"),
        )
    with pytest.raises(ValueError, match="cannot be supplied"):
        LanguageEvidenceInputV2(
            actor_id=ACTOR,
            source=source,
            text="source text",
            declared_language=LanguageCode("en"),
            declared_script=ScriptCode("Latn"),
            metadata_source=LanguageDetectionSource.LIGHTWEIGHT_DETECTOR,
        )
    assert _scope(LanguageEvidenceKindV2.CANONICAL_CHUNK).value == "chunk"
    assert _scope(LanguageEvidenceKindV2.OCR_REGION).value == "ocr_region"
    assert _scope(LanguageEvidenceKindV2.VISION_DERIVATION).value == "asset"


def test_deterministic_transliterator_lifecycle_and_operation_boundaries() -> None:
    provider = DeterministicTransliterationProvider(SimpleNamespace(name="profile"))  # type: ignore[arg-type]
    unsupported = SimpleNamespace(kind=LanguageDerivationKind.TRANSLATION)
    unchanged = SimpleNamespace(
        kind=LanguageDerivationKind.TRANSLITERATION,
        source_text="plain latin",
    )

    async def scenario() -> None:
        assert (await provider.readiness()).reason_code == "provider_not_initialized"
        assert (await provider.capabilities()).name == "profile"  # type: ignore[union-attr]
        with pytest.raises(IntegrityError, match="not initialized"):
            await provider.transform(unsupported)  # type: ignore[arg-type]
        await provider.initialize()
        assert (await provider.readiness()).reason_code == "provider_ready"
        with pytest.raises(IntegrityError, match="transliteration only"):
            await provider.transform(unsupported)  # type: ignore[arg-type]
        with pytest.raises(IntegrityError, match="no governed derived representation"):
            await provider.transform(unchanged)  # type: ignore[arg-type]
        await provider.close()
        assert not (await provider.readiness()).initialized

    _run(scenario())
