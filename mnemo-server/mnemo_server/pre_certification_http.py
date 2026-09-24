"""Operator-started, authenticated observation-only ASGI application."""

from .app import create_app
from .config import ServerConfig

app = create_app(
    ServerConfig.from_env(certified_production=True, pre_certification_observation=True),
    provision_tokenizer_on_startup=False,
    pre_certification_observation=True,
)
