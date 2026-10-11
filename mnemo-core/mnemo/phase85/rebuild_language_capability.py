"""Governed, provider-scoped query admission for isolated multilingual rebuilds."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from mnemo.phase85.profiles import ModelProfileComponent


@dataclass(frozen=True, slots=True)
class RebuildLanguageCapability:
    """Open-language capability is not a claim of retrieval quality certification."""

    identity: str
    scope: str
    operations: frozenset[str]

    def permits(self, operation: str) -> bool:
        return operation in self.operations


def load_rebuild_language_capability(
    *, path: Path, component: ModelProfileComponent
) -> RebuildLanguageCapability:
    raw = json.loads(path.read_text(encoding="utf-8"))
    expected_keys = {
        "schema",
        "provider",
        "model",
        "revision",
        "dimensions",
        "scope",
        "operations",
        "claim_source_digest",
    }
    if not isinstance(raw, dict) or set(raw) != expected_keys:
        raise ValueError("rebuild language capability schema is invalid")
    if (
        raw["schema"] != "mnemo.rebuild-language-capability/1"
        or raw["provider"] != component.provider
        or raw["model"] != component.model
        or raw["revision"] != component.revision
        or raw["dimensions"] != component.dimensions
        or raw["scope"] != "multilingual_unenumerated"
        or raw["operations"] != ["document_embedding", "query_embedding"]
        or not isinstance(raw["claim_source_digest"], str)
        or raw["claim_source_digest"]
        not in {claim.claim_source_digest for claim in component.language_claims}
    ):
        raise ValueError("rebuild language capability does not match the model profile")
    identity = hashlib.sha256(
        json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return RebuildLanguageCapability(
        identity=identity,
        scope=raw["scope"],
        operations=frozenset(raw["operations"]),
    )
