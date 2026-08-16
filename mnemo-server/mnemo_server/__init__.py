"""Mnemo server package."""

import sys

try:
    import pymupdf

    sys.modules.setdefault("fitz", pymupdf)
except ImportError:
    pass

from .app import create_app
from .config import ServerConfig
from .dependencies import get_engine

__version__ = "0.22.0"

__all__ = [
    "ServerConfig",
    "__version__",
    "create_app",
    "get_engine",
]
