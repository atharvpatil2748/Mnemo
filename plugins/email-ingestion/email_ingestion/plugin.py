"""Plugin registration for the ADR-0016 Email parser."""

from dataclasses import dataclass

from mnemo.registry import PluginRegistry

from .parser import EmailParser


@dataclass(frozen=True, slots=True)
class EmailIngestionPlugin:
    """Register the optional Email parser in approved V1 slots."""

    name: str = "email-ingestion"
    version: str = "0.21.1"
    core_version_range: str = ">=0.18.0,<1"

    def capabilities(self) -> tuple[str, ...]:
        """Advertise only the parser capability."""
        return ("parser",)

    def register(self, registry: PluginRegistry) -> None:
        """Register deterministic extension and MIME aliases."""
        parser = EmailParser()
        for slot in parser.supported_formats:
            registry.register_parser(slot, parser, priority=0)


plugin = EmailIngestionPlugin()
