"""Versioned, typed immutable snapshots for ADR-0056 provenance replay."""

from __future__ import annotations

import importlib
import json
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from mnemo.interfaces import IntegrityError
from mnemo.models import FinalQAResult, FrozenMetadata, GroundedAnswerResult

SNAPSHOT_SCHEMA_VERSION = 1


def encode_validated_snapshot(answer: GroundedAnswerResult) -> str:
    return _encode({"kind": "validated", "answer": answer})


def decode_validated_snapshot(payload: str) -> GroundedAnswerResult:
    decoded = _decode(payload)
    if not isinstance(decoded, dict) or decoded.get("kind") != "validated":
        raise IntegrityError("invalid final-QA validated snapshot")
    answer = decoded.get("answer")
    if not isinstance(answer, GroundedAnswerResult):
        raise IntegrityError("validated snapshot does not retain GroundedAnswerResult")
    return answer


def encode_published_snapshot(result: FinalQAResult) -> str:
    return _encode({"kind": "published", "result": result})


def decode_published_snapshot(payload: str) -> FinalQAResult:
    decoded = _decode(payload)
    if not isinstance(decoded, dict) or decoded.get("kind") != "published":
        raise IntegrityError("invalid final-QA published snapshot")
    result = decoded.get("result")
    if not isinstance(result, FinalQAResult):
        raise IntegrityError("published snapshot does not retain FinalQAResult")
    return result


def _encode(value: Any) -> str:
    objects: dict[str, dict[str, Any]] = {}
    identities: dict[int, str] = {}

    def encode(item: Any) -> Any:
        if item is None or isinstance(item, (int, float, bool)):
            return item
        if isinstance(item, UUID):
            return {"$uuid": str(item)}
        if isinstance(item, datetime):
            return {"$datetime": item.isoformat()}
        if isinstance(item, date):
            return {"$date": item.isoformat()}
        if isinstance(item, Enum):
            return {"$enum": _class_name(type(item)), "value": item.value}
        if isinstance(item, str):
            return item
        if isinstance(item, FrozenMetadata):
            return {"$frozen_metadata": {key: encode(value) for key, value in item.items()}}
        if isinstance(item, tuple):
            return {"$tuple": [encode(value) for value in item]}
        if isinstance(item, frozenset):
            return {"$frozenset": [encode(value) for value in sorted(item, key=repr)]}
        if isinstance(item, dict):
            return {"$dict": [[encode(key), encode(value)] for key, value in item.items()]}
        identity = id(item)
        if identity in identities:
            return {"$ref": identities[identity]}
        reference = str(len(identities) + 1)
        identities[identity] = reference
        if isinstance(item, BaseModel):
            objects[reference] = {
                "kind": "pydantic",
                "type": _class_name(type(item)),
                "fields": {key: encode(value) for key, value in item.model_dump().items()},
            }
        elif is_dataclass(item):
            objects[reference] = {
                "kind": "dataclass",
                "type": _class_name(type(item)),
                "fields": {field.name: encode(getattr(item, field.name)) for field in fields(item)},
            }
        else:
            raise IntegrityError(f"unsupported final-QA snapshot value: {type(item).__name__}")
        return {"$ref": reference}

    return json.dumps(
        {"schema_version": SNAPSHOT_SCHEMA_VERSION, "objects": objects, "payload": encode(value)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _decode(payload: str) -> Any:
    try:
        envelope = json.loads(payload)
    except json.JSONDecodeError as error:
        raise IntegrityError("invalid final-QA snapshot JSON") from error
    if not isinstance(envelope, dict) or envelope.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise IntegrityError("unsupported final-QA snapshot schema")
    objects = envelope.get("objects")
    if not isinstance(objects, dict):
        raise IntegrityError("invalid final-QA snapshot object table")
    decoded: dict[str, Any] = {}
    visiting: set[str] = set()

    def decode(item: Any) -> Any:
        if not isinstance(item, dict):
            return item
        if "$uuid" in item:
            return UUID(item["$uuid"])
        if "$datetime" in item:
            return datetime.fromisoformat(item["$datetime"])
        if "$date" in item:
            return date.fromisoformat(item["$date"])
        if "$enum" in item:
            return _load_model_class(item["$enum"])(item["value"])
        if "$frozen_metadata" in item:
            return FrozenMetadata(
                {key: decode(value) for key, value in item["$frozen_metadata"].items()}
            )
        if "$tuple" in item:
            return tuple(decode(value) for value in item["$tuple"])
        if "$frozenset" in item:
            return frozenset(decode(value) for value in item["$frozenset"])
        if "$dict" in item:
            return {decode(key): decode(value) for key, value in item["$dict"]}
        if "$ref" not in item:
            raise IntegrityError("invalid final-QA snapshot value")
        reference = item["$ref"]
        if not isinstance(reference, str) or reference not in objects:
            raise IntegrityError("unknown final-QA snapshot reference")
        if reference in decoded:
            return decoded[reference]
        if reference in visiting:
            raise IntegrityError("cyclic final-QA snapshot provenance is unsupported")
        record = objects[reference]
        if not isinstance(record, dict) or record.get("kind") not in {"pydantic", "dataclass"}:
            raise IntegrityError("invalid final-QA snapshot object record")
        visiting.add(reference)
        fields_data = {key: decode(value) for key, value in record.get("fields", {}).items()}
        cls = _load_model_class(record.get("type"))
        value = (
            cls.model_validate(fields_data) if record["kind"] == "pydantic" else cls(**fields_data)
        )
        visiting.remove(reference)
        decoded[reference] = value
        return value

    return decode(envelope.get("payload"))


def _class_name(value: type[Any]) -> str:
    if not value.__module__.startswith("mnemo.models"):
        raise IntegrityError("final-QA snapshot type is outside the model boundary")
    return f"{value.__module__}:{value.__qualname__}"


def _load_model_class(name: object) -> type[Any]:
    if not isinstance(name, str) or ":" not in name:
        raise IntegrityError("invalid final-QA snapshot type")
    module_name, qualname = name.split(":", 1)
    if not module_name.startswith("mnemo.models.") or "." in qualname:
        raise IntegrityError("final-QA snapshot type is not permitted")
    try:
        cls = getattr(importlib.import_module(module_name), qualname)
    except (ImportError, AttributeError) as error:
        raise IntegrityError("unknown final-QA snapshot model type") from error
    if not isinstance(cls, type):
        raise IntegrityError("invalid final-QA snapshot model type")
    return cls
