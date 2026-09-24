"""Signed, generation-bound final evidence for a staged V2 re-key.

This authority verifies existing signed artifacts and does not promote a
credential generation or expose a transport. Production certification still
requires independently produced ADR-0076 evidence.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from mnemo_server.services.production_credentials import _write_new
from mnemo_server.services.v2_certification import (
    BGE_REVISION,
    PAIR_POLICY,
    STORE_IDENTITY,
    STORE_SHA256,
    WP17CertificationAuthorityV1,
    WP17GenerationBindingV2,
)
from mnemo_server.services.v2_reranker_lifecycle import (
    DurableRerankerActivationStoreV1,
    V2RerankerMode,
)

_SCHEMA = "mnemo.v2-final-certification/3"
_DOMAIN = b"mnemo.v2-final-evidence-generation/3"


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _final_key(certification_signing_key: bytes) -> bytes:
    return hmac.new(certification_signing_key, _DOMAIN, hashlib.sha256).digest()


class ProductionGenerationEvidenceAuthority:
    """Create and verify a new final-evidence file without touching old files."""

    def __init__(
        self,
        *,
        activation_path: Path,
        certificate_path: Path,
        transport_parity_path: Path,
        final_evidence_path: Path,
        cursor_signing_key: bytes,
        certification_signing_key: bytes,
        generation_binding: WP17GenerationBindingV2,
        model_profile_fingerprint: str,
        predecessor_final_evidence_sha256: str,
    ) -> None:
        paths = (
            activation_path.resolve(),
            certificate_path.resolve(),
            transport_parity_path.resolve(),
            final_evidence_path.resolve(),
        )
        if len(set(paths)) != len(paths):
            raise ValueError("GENERATION_EVIDENCE_PATH_OVERLAP")
        if any(
            len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest)
            for digest in (model_profile_fingerprint, predecessor_final_evidence_sha256)
        ):
            raise ValueError("GENERATION_EVIDENCE_IDENTITY_INVALID")
        self._activation_path = paths[0]
        self._certificate_path = paths[1]
        self._transport_path = paths[2]
        self._final_path = paths[3]
        self._cursor_key = cursor_signing_key
        self._cert_key = certification_signing_key
        self._binding = generation_binding
        self._profile = model_profile_fingerprint
        self._predecessor = predecessor_final_evidence_sha256

    @property
    def artifact_paths(self) -> tuple[Path, Path, Path]:
        return self._activation_path, self._certificate_path, self._final_path

    @property
    def transport_parity_path(self) -> Path:
        return self._transport_path

    @property
    def key_fingerprints(self) -> tuple[str, str]:
        """Non-secret digests used to bind the verifier to OS-stored keys."""
        return (
            hashlib.sha256(self._cursor_key).hexdigest(),
            hashlib.sha256(self._cert_key).hexdigest(),
        )

    def _validated_inputs(self) -> dict[str, Any]:
        activation = DurableRerankerActivationStoreV1(
            path=self._activation_path,
            signing_key=self._cursor_key,
            prohibited_paths=(self._certificate_path, self._final_path),
            credential_generation_id=self._binding.credential_generation_id,
            activation_generation_id=self._binding.activation_generation_id,
        ).load()
        if activation.desired_mode is not V2RerankerMode.BGE_V2_M3:
            raise RuntimeError("GENERATION_ACTIVATION_NOT_ACTIVE")
        activation_sha = _digest(self._activation_path)
        if activation_sha != self._binding.activation_state_sha256:
            raise RuntimeError("GENERATION_ACTIVATION_DIGEST_MISMATCH")
        certificate = WP17CertificationAuthorityV1.verify_generation(
            path=self._certificate_path,
            signing_key=self._cert_key,
            binding=self._binding,
        )
        if certificate["evidence_digests"].get("transport_parity") != _digest(self._transport_path):
            raise RuntimeError("GENERATION_TRANSPORT_EVIDENCE_MISMATCH")
        from .pre_certification_observation import (
            PreCertificationObservationAuthority,
            observation_root_for_convergence,
        )

        try:
            parity = json.loads(self._transport_path.read_text(encoding="utf-8"))
            campaign_id = UUID(str(parity["campaign_id"]))
            observer = PreCertificationObservationAuthority(
                generation_id=self._binding.credential_generation_id,
                signing_key=self._cert_key,
                observation_root=observation_root_for_convergence(
                    self._transport_path,
                    generation_id=self._binding.credential_generation_id,
                    campaign_id=campaign_id,
                ),
                campaign_id=campaign_id,
            )
            verified = observer.verify_convergence(self._transport_path)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            raise RuntimeError("GENERATION_PRE_CERTIFICATION_EVIDENCE_INVALID") from exc
        identity = verified["identity"]
        if (
            identity.get("database_identity") != STORE_IDENTITY
            or identity.get("database_sha256") != STORE_SHA256
            or identity.get("reranker_revision") != BGE_REVISION
            or identity.get("activation_sha256") != self._binding.activation_state_sha256
            or identity.get("model_profile_fingerprint") != self._profile
        ):
            raise RuntimeError("GENERATION_PRE_CERTIFICATION_IDENTITY_MISMATCH")
        return certificate

    def create(self) -> dict[str, Any]:
        """Write only a fresh generation file after signed inputs verify."""
        if self._final_path.exists():
            raise RuntimeError("GENERATION_FINAL_EVIDENCE_ALREADY_EXISTS")
        certificate = self._validated_inputs()
        binding = self._binding
        payload: dict[str, Any] = {
            "schema_version": _SCHEMA,
            "status": "PRODUCTION_CERTIFICATION_PASS",
            "credential_generation_id": str(binding.credential_generation_id),
            "activation_generation_id": str(binding.activation_generation_id),
            "certificate_generation_id": str(binding.certificate_generation_id),
            "final_evidence_generation_id": str(binding.final_evidence_generation_id),
            "production_store": {
                "governed_identity": STORE_IDENTITY,
                "sha256_after": STORE_SHA256,
            },
            "model_profile_fingerprint": self._profile,
            "reranker_revision": BGE_REVISION,
            "reranker_pair_policy": PAIR_POLICY,
            "activation_sha256": binding.activation_state_sha256,
            "certificate_sha256": _digest(self._certificate_path),
            "transport_parity_sha256": _digest(self._transport_path),
            "predecessor_final_evidence_sha256": self._predecessor,
            "governance": {"wp17_signature": certificate["signature"]},
        }
        payload["signature"] = hmac.new(
            _final_key(self._cert_key), _canonical(payload), hashlib.sha256
        ).hexdigest()
        _write_new(self._final_path, json.dumps(payload, sort_keys=True, indent=2) + "\n")
        self.verify()
        return payload

    def verify(self) -> dict[str, Any]:
        """Independently check final signature and the complete input chain."""
        try:
            payload = json.loads(self._final_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("GENERATION_FINAL_EVIDENCE_UNAVAILABLE") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("GENERATION_FINAL_EVIDENCE_INVALID")
        signature = payload.pop("signature", None)
        if not isinstance(signature, str) or not hmac.compare_digest(
            signature,
            hmac.new(_final_key(self._cert_key), _canonical(payload), hashlib.sha256).hexdigest(),
        ):
            raise RuntimeError("GENERATION_FINAL_EVIDENCE_SIGNATURE_INVALID")
        certificate = self._validated_inputs()
        binding = self._binding
        expected = {
            "credential_generation_id": str(binding.credential_generation_id),
            "activation_generation_id": str(binding.activation_generation_id),
            "certificate_generation_id": str(binding.certificate_generation_id),
            "final_evidence_generation_id": str(binding.final_evidence_generation_id),
            "production_store": {
                "governed_identity": STORE_IDENTITY,
                "sha256_after": STORE_SHA256,
            },
            "model_profile_fingerprint": self._profile,
            "reranker_revision": BGE_REVISION,
            "reranker_pair_policy": PAIR_POLICY,
            "activation_sha256": binding.activation_state_sha256,
            "certificate_sha256": _digest(self._certificate_path),
            "transport_parity_sha256": _digest(self._transport_path),
            "predecessor_final_evidence_sha256": self._predecessor,
            "governance": {"wp17_signature": certificate["signature"]},
        }
        if (
            payload.get("schema_version") != _SCHEMA
            or payload.get("status") != "PRODUCTION_CERTIFICATION_PASS"
            or any(payload.get(field) != value for field, value in expected.items())
        ):
            raise RuntimeError("GENERATION_FINAL_EVIDENCE_BINDING_INVALID")
        return {**payload, "signature": signature}
