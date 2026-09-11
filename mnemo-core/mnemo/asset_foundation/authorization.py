"""Occurrence-scoped authorization for future asset operations."""

import logging
from dataclasses import dataclass
from uuid import UUID

from mnemo.interfaces.asset_catalog import AssetCatalogStoreV1
from mnemo.interfaces.errors import NotFoundError
from mnemo.models import AssetOccurrence
from mnemo.models._shared import require_optional_non_empty, require_uuid

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetAccessContext:
    """Existing authentication identity bound to one notebook scope."""

    notebook_id: UUID
    actor_id: str | None = None

    def __post_init__(self) -> None:
        require_uuid(self.notebook_id, "notebook_id")
        require_optional_non_empty(self.actor_id, "actor_id")


class AssetAuthorizationService:
    """Fail closed without treating asset or occurrence IDs as capabilities."""

    def __init__(self, catalog: AssetCatalogStoreV1) -> None:
        if not isinstance(catalog, AssetCatalogStoreV1):
            raise TypeError("catalog must implement AssetCatalogStoreV1")
        self._catalog = catalog

    async def authorize_occurrence(
        self,
        context: AssetAccessContext,
        occurrence_id: UUID,
    ) -> AssetOccurrence:
        """Resolve only through notebook/source/document/version membership."""
        if not isinstance(context, AssetAccessContext):
            raise TypeError("context must be AssetAccessContext")
        require_uuid(occurrence_id, "occurrence_id")
        occurrence = await self._catalog.get_authorized_asset_occurrence(
            notebook_id=context.notebook_id,
            occurrence_id=occurrence_id,
        )
        if occurrence is None:
            _LOGGER.warning(
                "asset occurrence authorization denied notebook_id=%s occurrence_id=%s",
                context.notebook_id,
                occurrence_id,
            )
            raise NotFoundError("asset occurrence was not found")
        _LOGGER.info(
            "asset occurrence authorization granted notebook_id=%s occurrence_id=%s",
            context.notebook_id,
            occurrence_id,
        )
        return occurrence
