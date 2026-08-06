"""Binary asset domain model."""

from dataclasses import dataclass, field
from uuid import UUID

from ._shared import (
    FrozenMetadata,
    identity_equal,
    require_non_empty,
    require_positive,
    require_sha256,
    require_uuid,
)


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class Asset:
    """Storage-independent metadata for an immutable local binary asset."""

    asset_id: UUID
    mime_type: str
    content_hash: str
    storage_uri: str
    width: int | None = None
    height: int | None = None
    metadata: FrozenMetadata = field(default_factory=FrozenMetadata)

    def __post_init__(self) -> None:
        """Validate the asset snapshot."""
        require_uuid(self.asset_id, "asset_id")
        require_non_empty(self.mime_type, "mime_type")
        require_sha256(self.content_hash, "content_hash")
        require_non_empty(self.storage_uri, "storage_uri")
        if self.width is not None:
            require_positive(self.width, "width")
        if self.height is not None:
            require_positive(self.height, "height")
        if not isinstance(self.metadata, FrozenMetadata):
            raise TypeError("metadata must be FrozenMetadata")

    def __eq__(self, other: object) -> bool:
        """Compare assets by stable identity."""
        return identity_equal(self, other, Asset, self.asset_id, getattr(other, "asset_id", None))

    def __hash__(self) -> int:
        """Hash the stable asset identity."""
        return hash(self.asset_id)
