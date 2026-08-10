"""Phase 3.9 ingestion and canonicalization boundary."""

from .canonicalizer import DocumentCanonicalizer
from .pipeline import IngestionPipeline

__all__ = ["DocumentCanonicalizer", "IngestionPipeline"]
