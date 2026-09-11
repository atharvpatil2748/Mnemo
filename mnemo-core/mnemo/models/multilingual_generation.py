"""Coverage evidence for dependency-complete Full Multilingual V2 generations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from ._shared import require_non_empty, require_sha256, require_utc


@dataclass(frozen=True, slots=True, kw_only=True)
class MultilingualCoverageManifestV2:
    generation_id: UUID
    capability: str
    profile_fingerprint: str
    dependency_digest: str
    expected_count: int
    succeeded_count: int
    failed_count: int
    skipped_count: int
    language_tags: tuple[str, ...]
    script_codes: tuple[str, ...]
    representation_types: tuple[str, ...]
    source_kinds: tuple[str, ...]
    provenance_complete: bool
    authorization_compatible: bool
    rollback_metadata_digest: str
    item_identity_digest: str
    created_at: datetime

    def __post_init__(self) -> None:
        require_non_empty(self.capability, "capability")
        for value, name in (
            (self.profile_fingerprint, "profile_fingerprint"),
            (self.dependency_digest, "dependency_digest"),
            (self.rollback_metadata_digest, "rollback_metadata_digest"),
            (self.item_identity_digest, "item_identity_digest"),
        ):
            require_sha256(value, name)
        require_utc(self.created_at, "created_at")
        counts = (
            self.expected_count,
            self.succeeded_count,
            self.failed_count,
            self.skipped_count,
        )
        if any(value < 0 for value in counts):
            raise ValueError("coverage counts must be non-negative")
        if self.succeeded_count + self.failed_count + self.skipped_count != (self.expected_count):
            raise ValueError("coverage counts do not account for expected items")
        for values, name in (
            (self.language_tags, "language_tags"),
            (self.script_codes, "script_codes"),
            (self.representation_types, "representation_types"),
            (self.source_kinds, "source_kinds"),
        ):
            if tuple(sorted(set(values))) != values:
                raise ValueError(f"{name} must be sorted and unique")

    @property
    def complete(self) -> bool:
        return (
            self.failed_count == 0
            and self.succeeded_count + self.skipped_count == self.expected_count
            and self.provenance_complete
            and self.authorization_compatible
        )

    @property
    def coverage_digest(self) -> str:
        payload = {
            "generation_id": str(self.generation_id),
            "capability": self.capability,
            "languages": self.language_tags,
            "scripts": self.script_codes,
            "representations": self.representation_types,
            "source_kinds": self.source_kinds,
            "item_identity_digest": self.item_identity_digest,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
