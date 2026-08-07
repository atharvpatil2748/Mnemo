"""Phase 2 storage backends for Mnemo core."""

from .filesystem import FilesystemBlobStore

__all__ = [
    "FilesystemBlobStore",
]
