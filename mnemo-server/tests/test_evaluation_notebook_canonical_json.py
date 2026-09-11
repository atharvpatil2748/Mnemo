from __future__ import annotations

import json

import pytest
from mnemo_server.evaluation.canonical_json import (
    canonical_json_bytes_v1,
    canonical_json_sha256_v1,
)


@pytest.mark.parametrize(
    "value",
    [
        {"ascii": "value"},
        {"hindi": "यह बहुभाषी जाँच है"},
        {"marathi": "ही बहुभाषिक चाचणी आहे"},
        {"filename": "Coordinator Application 2026\u201327.pptx"},
        {"punctuation": "en\u2013dash em\u2014dash"},
        {"combining": "e\u0301", "precomposed": "é"},
        {"probe": ";|fi tud fefFkyk ds jktk FksA fdarq jktlh"},
        {"nested": {"दस्तऐवज": [3, 2, 1], "name": "परीक्षण"}},
    ],
)
def test_canonical_json_writer_and_validator_agree_for_unicode(value: object) -> None:
    persisted = json.loads(canonical_json_bytes_v1(value).decode("utf-8"))
    assert canonical_json_sha256_v1(value) == canonical_json_sha256_v1(persisted)


def test_canonical_json_is_independent_of_dictionary_insertion_order() -> None:
    first = {"b": {"मराठी": 2, "हिन्दी": 1}, "a": "2026\u201327"}
    second = {"a": "2026\u201327", "b": {"हिन्दी": 1, "मराठी": 2}}
    assert canonical_json_bytes_v1(first) == canonical_json_bytes_v1(second)
    assert canonical_json_sha256_v1(first) == canonical_json_sha256_v1(second)


def test_manifest_unicode_regression_writer_validator_identity() -> None:
    manifest = {
        "source_inventory": [{"relative_path": "Coordinator Application 2026\u201327.pptx"}],
        "semantic_probe": {"query": "भारत आणि मराठी दस्तऐवज"},
    }
    writer_digest = canonical_json_sha256_v1(manifest)
    validator_value = json.loads(canonical_json_bytes_v1(manifest).decode("utf-8"))
    assert writer_digest == canonical_json_sha256_v1(validator_value)


def test_canonical_json_rejects_non_finite_numbers() -> None:
    with pytest.raises(ValueError):
        canonical_json_bytes_v1({"score": float("nan")})
