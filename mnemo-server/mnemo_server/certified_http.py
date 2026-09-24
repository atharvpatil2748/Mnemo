"""Server-owned certified V2 HTTP entrypoint."""

from .app import create_app
from .config import ServerConfig

app = create_app(ServerConfig.from_env(certified_production=True))
