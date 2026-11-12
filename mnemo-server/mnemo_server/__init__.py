"""Mnemo server package."""

import sys
from typing import TYPE_CHECKING, Any

try:
    import pymupdf

    sys.modules.setdefault("fitz", pymupdf)
except ImportError:
    pass

from .config import ServerConfig
from .dependencies import get_engine

if TYPE_CHECKING:
    from .app import create_app

__version__ = "0.25.0"


def __getattr__(name: str) -> Any:
    """Keep the public app factory while MCP-only processes avoid HTTP startup imports."""
    if name == "create_app":
        from .app import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ServerConfig",
    "__version__",
    "create_app",
    "get_engine",
]
