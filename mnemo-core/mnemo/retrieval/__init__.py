"""Phase 6 retrieval and grounded-answer components."""

from .advanced import AdvancedRetrievalService, RetrievalCursorCodec
from .advanced_sources import CanonicalAdvancedReranker, CanonicalTextAdvancedSource
from .answer import GroundedAnswerGenerator
from .citation import CitationEngine
from .comparison import (
    ComparisonRelation,
    DeterministicComparisonResultV1,
    DeterministicComparisonServiceV1,
)
from .context import ContextBuilder
from .dense import DenseRetriever
from .final_qa import FinalQAOrchestrator
from .final_qa_authorization import StorageEvidenceAuthorizerV2
from .final_qa_provider import LLMFinalQAV2Provider
from .full_multilingual_advanced_v2 import (
    FullMultilingualAdvancedSourceV2,
    QueryLanguageResolverV2,
    RegistryQueryLanguageResolverV2,
    V2AdvancedCandidateProjector,
)
from .full_multilingual_v2 import (
    AuthorizedMultilingualDenseSourceV2,
    AuthorizedMultilingualSparseSourceV2,
    FullMultilingualRetrievalApplicationV2,
    MultilingualOperationAdmissionV2,
    MultilingualSparseMatchV2,
    MultilingualV2ApplicationResult,
    MultilingualV2RetrievalCandidate,
)
from .fusion import MultiSourceRetriever
from .language_detection import (
    ConfiguredUnicodeScriptDetectorV1,
    DetectorRegistrationV1,
    LanguageDetectorRegistryV2,
    ScriptDetectorRegistryV1,
    UnknownLanguageDetectorV2,
)
from .multilingual import (
    ConservativeENHIMRDetector,
    MultilingualFinalQAService,
    MultilingualRetrievalPlanner,
    MultilingualRetrievalService,
    SQLiteMultilingualDenseSource,
    UnicodeLanguageDetector,
    detect_script,
    normalize_multilingual_text,
    resolve_answer_language,
    transliterate_devanagari,
)
from .multilingual_advanced import MultilingualAdvancedSourceV2
from .multilingual_dense_v2 import (
    MAX_ELIGIBLE_MULTILINGUAL_V2_VECTORS,
    MAX_RETURNED_MULTILINGUAL_V2_CANDIDATES,
    AuthorizedMultilingualDenseRetrievalV2,
    AuthorizedMultilingualSourceEnumeratorV2,
    MultilingualDenseMatchV2,
    MultilingualEmbeddingStoreV2,
    MultilingualQueryEmbedderV2,
)
from .multilingual_providers import (
    BGEM3EmbeddingProvider,
    BGEMultilingualReranker,
    MultilingualProviderReadinessProbe,
    multilingual_buildable_registrations,
    preprocess_bge_m3_document,
    preprocess_bge_m3_query,
)
from .multilingual_sparse_v2 import (
    AuthorizedMultilingualSparseRetrievalV2,
    MultilingualTextProjectionStoreV2,
)
from .multimodal import (
    MULTIMODAL_SYSTEM_PROMPT,
    FinalQAV2Orchestrator,
    MultimodalContextBuilder,
    MultimodalFusionReranker,
    candidate_from_advanced,
    candidates_from_retrieval,
)
from .multimodal_sources import (
    ProjectedMultilingualAdvancedSource,
    ProjectedMultimodalAdvancedSource,
)
from .parent import ParentRetriever
from .partitioned import (
    PartitionedRetrievalResultV1,
    PartitionedRetrievalServiceV1,
    RetrievalPartitionV1,
)
from .planner import QueryPlanner
from .reranker import CrossEncoderReranker, CrossEncoderRerankerPlugin, RerankingModule
from .reranker_candidates import (
    RERANKER_BUILDER_REVISION,
    RenderedRerankerPairV1,
    RerankerCandidateBuilderV1,
    RerankerTokenizerV1,
)
from .scope import StorageDocumentScopeResolverV1, StorageSourceAssociationReaderV1
from .sparse import SparseRetriever
from .structured import (
    CanonicalTableEvidenceExtractor,
    DelimitedTableEvidenceExtractor,
    ProjectedTableEvidenceExtractor,
    StructuredDatasetEvidenceExtractor,
    StructuredRetrievalService,
    compare_structured_values,
    observe_table_schema,
)
from .structured_datasets import StructuredDatasetRuntimeService
from .text_representations import (
    ConfiguredRepresentationDetectorV1,
    DeterministicTransformationRegistryV1,
    GovernedMappingRepresentationTransformerV1,
    RepresentationDetectionResultV1,
    RepresentationPipelineV1,
)

__all__ = [
    "MULTIMODAL_SYSTEM_PROMPT",
    "AdvancedRetrievalService",
    "CanonicalAdvancedReranker",
    "CanonicalTableEvidenceExtractor",
    "CanonicalTextAdvancedSource",
    "CitationEngine",
    "ComparisonRelation",
    "ContextBuilder",
    "CrossEncoderReranker",
    "CrossEncoderRerankerPlugin",
    "DelimitedTableEvidenceExtractor",
    "DenseRetriever",
    "DeterministicComparisonResultV1",
    "DeterministicComparisonServiceV1",
    "FinalQAOrchestrator",
    "FinalQAV2Orchestrator",
    "FullMultilingualRetrievalApplicationV2",
    "GovernedMappingRepresentationTransformerV1",
    "GroundedAnswerGenerator",
    "LLMFinalQAV2Provider",
    "MultiSourceRetriever",
    "MultimodalContextBuilder",
    "MultimodalFusionReranker",
    "ParentRetriever",
    "PartitionedRetrievalResultV1",
    "PartitionedRetrievalServiceV1",
    "ProjectedMultilingualAdvancedSource",
    "ProjectedMultimodalAdvancedSource",
    "ProjectedTableEvidenceExtractor",
    "QueryPlanner",
    "RerankingModule",
    "RetrievalCursorCodec",
    "RetrievalPartitionV1",
    "SparseRetriever",
    "StorageDocumentScopeResolverV1",
    "StorageEvidenceAuthorizerV2",
    "StorageSourceAssociationReaderV1",
    "StructuredDatasetEvidenceExtractor",
    "StructuredDatasetRuntimeService",
    "StructuredRetrievalService",
    "candidate_from_advanced",
    "candidates_from_retrieval",
    "compare_structured_values",
    "observe_table_schema",
]

__all__ += [
    "MAX_ELIGIBLE_MULTILINGUAL_V2_VECTORS",
    "MAX_RETURNED_MULTILINGUAL_V2_CANDIDATES",
    "RERANKER_BUILDER_REVISION",
    "AuthorizedMultilingualDenseRetrievalV2",
    "AuthorizedMultilingualDenseSourceV2",
    "AuthorizedMultilingualSourceEnumeratorV2",
    "AuthorizedMultilingualSparseRetrievalV2",
    "AuthorizedMultilingualSparseSourceV2",
    "BGEM3EmbeddingProvider",
    "BGEMultilingualReranker",
    "ConfiguredRepresentationDetectorV1",
    "ConfiguredUnicodeScriptDetectorV1",
    "ConservativeENHIMRDetector",
    "DetectorRegistrationV1",
    "DeterministicTransformationRegistryV1",
    "FullMultilingualAdvancedSourceV2",
    "LanguageDetectorRegistryV2",
    "MultilingualAdvancedSourceV2",
    "MultilingualDenseMatchV2",
    "MultilingualEmbeddingStoreV2",
    "MultilingualFinalQAService",
    "MultilingualOperationAdmissionV2",
    "MultilingualProviderReadinessProbe",
    "MultilingualQueryEmbedderV2",
    "MultilingualRetrievalPlanner",
    "MultilingualRetrievalService",
    "MultilingualSparseMatchV2",
    "MultilingualTextProjectionStoreV2",
    "MultilingualV2ApplicationResult",
    "MultilingualV2RetrievalCandidate",
    "QueryLanguageResolverV2",
    "RegistryQueryLanguageResolverV2",
    "RenderedRerankerPairV1",
    "RepresentationDetectionResultV1",
    "RepresentationPipelineV1",
    "RerankerCandidateBuilderV1",
    "RerankerTokenizerV1",
    "SQLiteMultilingualDenseSource",
    "ScriptDetectorRegistryV1",
    "UnicodeLanguageDetector",
    "UnknownLanguageDetectorV2",
    "V2AdvancedCandidateProjector",
    "detect_script",
    "multilingual_buildable_registrations",
    "normalize_multilingual_text",
    "preprocess_bge_m3_document",
    "preprocess_bge_m3_query",
    "resolve_answer_language",
    "transliterate_devanagari",
]
