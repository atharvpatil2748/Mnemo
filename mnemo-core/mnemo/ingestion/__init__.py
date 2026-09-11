"""Phase 3.9 ingestion and canonicalization boundary."""

from .canonicalizer import DocumentCanonicalizer
from .pipeline import IngestionPipeline, IngestionResultV2

__all__ = ["DocumentCanonicalizer", "IngestionPipeline", "IngestionResultV2"]
