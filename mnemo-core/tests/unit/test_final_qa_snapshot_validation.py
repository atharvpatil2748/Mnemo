from __future__ import annotations

from datetime import UTC, date, datetime
from enum import Enum
from uuid import UUID

import pytest
from mnemo.interfaces import IntegrityError
from mnemo.models import FrozenMetadata
from mnemo.retrieval.final_qa_snapshot import _decode, _encode, _load_model_class


class ForeignEnum(Enum):
    VALUE = "value"


def test_snapshot_codec_round_trips_supported_nested_primitives() -> None:
    value = {
        "uuid": UUID(int=1),
        "datetime": datetime(2026, 1, 1, tzinfo=UTC),
        "date": date(2026, 1, 2),
        "metadata": FrozenMetadata({"nested": (1, 2)}),
        "tuple": ("x",),
        "set": frozenset({"b", "a"}),
        "dict": {1: "one"},
    }
    assert _decode(_encode(value)) == value


@pytest.mark.parametrize(
    "payload",
    (
        "not-json",
        "[]",
        '{"schema_version":99,"objects":{},"payload":null}',
        '{"schema_version":1,"objects":[],"payload":null}',
        '{"schema_version":1,"objects":{},"payload":{"unknown":1}}',
        '{"schema_version":1,"objects":{},"payload":{"$ref":"missing"}}',
        '{"schema_version":1,"objects":{},"payload":{"$ref":1}}',
        '{"schema_version":1,"objects":{"1":[]},"payload":{"$ref":"1"}}',
        '{"schema_version":1,"objects":{"1":{"kind":"other"}},"payload":{"$ref":"1"}}',
        '{"schema_version":1,"objects":{"1":{"kind":"dataclass",'
        '"type":"mnemo.models.multimodal:Missing","fields":{}}},"payload":{"$ref":"1"}}',
        '{"schema_version":1,"objects":{"1":{"kind":"dataclass",'
        '"type":"mnemo.models.multimodal:EvidenceCandidateV2","fields":'
        '{"self":{"$ref":"1"}}}},"payload":{"$ref":"1"}}',
    ),
)
def test_snapshot_decoder_rejects_malformed_or_untrusted_envelopes(payload: str) -> None:
    with pytest.raises((IntegrityError, TypeError)):
        _decode(payload)


def test_snapshot_encoder_and_model_loader_enforce_model_boundary() -> None:
    with pytest.raises(IntegrityError, match="unsupported"):
        _encode(object())
    with pytest.raises(IntegrityError, match="outside the model boundary"):
        _encode(ForeignEnum.VALUE)
    for name in (None, "missing-colon", "os:path.join", "mnemo.models.multimodal:A.B"):
        with pytest.raises(IntegrityError):
            _load_model_class(name)
    assert _load_model_class("mnemo.models.multimodal:EvidenceCandidateV2").__name__ == (
        "EvidenceCandidateV2"
    )
