"""ADR-0016 Email ingestion parser plugin."""

from .parser import EmailParser
from .plugin import EmailIngestionPlugin, plugin

__all__ = ["EmailIngestionPlugin", "EmailParser", "plugin"]
