"""Execute isolated, generation-bound WP-17 checks without production promotion."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import mcp.types as mcp_types
from httpx import ASGITransport, AsyncClient
from mnemo.models.advanced_retrieval import AdvancedRetrievalMode, EvidenceRepresentation
from mnemo.phase85.profiles import ModelProfileDocument, profile_snapshot
from mnemo_server.app import create_app
from mnemo_server.config import ServerConfig
from mnemo_server.mcp.server import create_pre_certification_mcp_server
from mnemo_server.schemas.retrieval_v2 import EvidenceScopeRequest, EvidenceSearchRequest
from mnemo_server.services.authorization import principal_from_claims
from mnemo_server.services.full_multilingual_v2_startup import PROFILE_NAME, PROFILE_PATH
from mnemo_server.services.pre_certification_observation import (
    resolve_pre_certification_observation,
)
from mnemo_server.services.production_credentials import (
    CredentialKind,
    CredentialState,
    ProductionCredentialRegistry,
    WindowsCredentialStore,
    _write_new,
)
from mnemo_server.services.production_runtime_binding import repository_root
from mnemo_server.services.retrieval_v2 import EvidenceRetrievalApplicationService
from mnemo_server.services.v2_certification import (
    BGE_REVISION,
    STORE_IDENTITY,
    STORE_SHA256,
    WP17CertificationAuthorityV1,
    WP17EvidencePathsV1,
    WP17GenerationBindingV2,
)
from mnemo_server.services.v2_reranker_lifecycle import (
    DurableRerankerActivationAuthorityV1,
    DurableRerankerActivationStoreV1,
    RerankerActivationAuthorityV1,
    V2RerankerMode,
)

SCHEMA = "mnemo.wp17-generation-rehearsal/1"
DOMAIN = b"mnemo.wp17-generation-rehearsal/1"
METRICS = ("recall_at_1", "recall_at_5", "recall_at_10", "mrr", "ndcg_at_10")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def document(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("WP17_REHEARSAL_DOCUMENT_INVALID")
    return value


def signed_artifact(
    *,
    path: Path,
    kind: str,
    status: str,
    identity: dict[str, str],
    checks: dict[str, bool],
    details: dict[str, Any],
    key: bytes,
    executed_at: str | None = None,
    additional: dict[str, Any] | None = None,
) -> None:
    if not checks or not all(checks.values()):
        raise RuntimeError(f"WP17_REHEARSAL_CHECK_FAILED:{kind}")
    payload: dict[str, Any] = {
        "schema_version": SCHEMA,
        "evidence_type": kind,
        "status": status,
        "credential_generation_id": identity["credential_generation_id"],
        "activation_state_sha256": identity["activation_sha256"],
        "identity": identity,
        "scope": "ISOLATED_WP17_REHEARSAL",
        "global_generation_active": False,
        "public_production_exposed": False,
        "executed_at": executed_at or datetime.now(UTC).isoformat(),
        "checks": checks,
        "details": details,
    }
    payload.update(additional or {})
    evidence_key = hmac.new(key, DOMAIN, hashlib.sha256).digest()
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    payload["signature"] = hmac.new(evidence_key, canonical, hashlib.sha256).hexdigest()
    _write_new(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


async def execute(run_dir: Path) -> dict[str, Any]:
    root = repository_root()
    config = ServerConfig.from_env(certified_production=True, pre_certification_observation=True)
    core, observed_identity, observation_authority = resolve_pre_certification_observation(
        server_config=config, root=root
    )
    identity = asdict(observed_identity)
    generation_id = UUID(observed_identity.credential_generation_id)
    registry_path = config.credential_registry_path
    if registry_path is None:
        raise RuntimeError("WP17_REGISTRY_UNAVAILABLE")
    registry = ProductionCredentialRegistry(
        path=(root / registry_path).resolve(), secret_store=WindowsCredentialStore()
    )
    expected_parent = registry.path.parent / "wp17_rehearsal" / str(generation_id)
    if run_dir.parent.resolve() != expected_parent.resolve() or not run_dir.is_dir():
        raise RuntimeError("WP17_RUN_DIRECTORY_INVALID")
    registry_document = registry.load()
    selected = [x for x in registry_document.generations if x.generation_id == generation_id]
    if len(selected) != 1 or selected[0].state is not CredentialState.PROVISIONED:
        raise RuntimeError("WP17_GENERATION_NOT_STAGED")
    record = selected[0]
    if (
        registry_document.active_generation_id is not None
        or record.activation_path is None
        or record.activation_sha256 != observed_identity.activation_sha256
        or record.observation_convergence_path is None
        or record.observation_convergence_sha256 is None
    ):
        raise RuntimeError("WP17_GENERATION_AUTHORITY_INVALID")
    activation_path = Path(record.activation_path)
    convergence_path = Path(record.observation_convergence_path)
    if (
        digest(activation_path) != record.activation_sha256
        or digest(convergence_path) != record.observation_convergence_sha256
        or observation_authority.verify_convergence(convergence_path)["identity"] != identity
    ):
        raise RuntimeError("WP17_SIGNED_BINDING_INVALID")
    key = registry.retrieve(generation_id, CredentialKind.CERTIFICATION_SIGNING).encode()
    cursor = registry.retrieve(generation_id, CredentialKind.DELIVERY_CURSOR)
    activation_key = hmac.new(
        cursor.encode(), b"mnemo.v2-reranker-activation-state/1", hashlib.sha256
    ).digest()
    activation_doc = document(activation_path)
    activation_generation = UUID(str(activation_doc["activation_generation_id"]))
    activation_store = DurableRerankerActivationStoreV1(
        path=activation_path,
        signing_key=activation_key,
        prohibited_paths=(core.storage.sqlite.path,),
        credential_generation_id=generation_id,
        activation_generation_id=activation_generation,
    )
    activation = activation_store.load()
    activation_checks = {
        "signature_verified": activation.desired_mode is V2RerankerMode.BGE_V2_M3,
        "revision_verified": bool(
            activation.activation_evidence is not None
            and activation.activation_evidence.revision == BGE_REVISION
            and activation.activation_evidence.production_store_identity == STORE_IDENTITY
        ),
    }
    if not all(activation_checks.values()):
        raise RuntimeError("WP17_ACTIVATION_INVALID")

    evaluation_path = run_dir / "evaluation.json"
    evaluation = document(evaluation_path)
    thresholds_path = root / "scratch/mnemo-v2-threshold-certification.json"
    floors = document(thresholds_path)["floors"]
    metrics = evaluation.get("metrics", {})
    checkpoint_path = run_dir / "checkpoint.json"
    evaluation_checks = {
        "frozen_inputs_verified": (
            evaluation.get("status") == "PRODUCTION_PARITY_EVALUATION_PASS"
            and evaluation.get("credential_generation_id") == str(generation_id)
            and evaluation.get("semantic_runtime_identity") == identity
            and evaluation.get("production_store", {}).get("before", {}).get("sha256")
            == STORE_SHA256
            and evaluation.get("production_store", {}).get("after", {}).get("sha256")
            == STORE_SHA256
            and evaluation.get("reranker", {}).get("revision") == BGE_REVISION
            and evaluation.get("reranker", {}).get("device") == "cuda"
            and evaluation.get("reranker", {}).get("cpu_fallback") is False
        ),
        "candidate_protocol_verified": (
            document(checkpoint_path).get("status") == "COMPLETE"
            and evaluation.get("candidate_protocol", {}).get("candidate_parity") == "PASS"
            and metrics.get("n") == 18
            and all(float(metrics.get(name, -1)) >= float(floors[name]) for name in METRICS)
        ),
    }
    if not all(evaluation_checks.values()):
        raise RuntimeError("WP17_EVALUATION_INVALID")

    app = create_app(
        server_config=config,
        pre_certification_observation=True,
        provision_tokenizer_on_startup=False,
    )
    if config.auth_mode != "api-key":
        raise RuntimeError("WP17_AUTH_MODE_UNSUPPORTED")
    model_cache = config.full_multilingual_v2_model_cache
    if model_cache is None:
        raise RuntimeError("WP17_MODEL_CACHE_UNAVAILABLE")
    api_key = registry.retrieve(generation_id, CredentialKind.API_KEY)
    url = "/internal/pre-certification/observe"
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://wp17-isolated") as client,
    ):
        anonymous = await client.get(url)
        invalid = await client.get(url, headers={"X-API-Key": "invalid"})
        authorized = await client.get(url, headers={"X-API-Key": api_key})
        override = await client.get(
            url, params={"database_path": "historical.db"}, headers={"X-API-Key": api_key}
        )
        chat = await client.post("/v2/notebooks/unknown/final-qa", headers={"X-API-Key": api_key})
        mutation = await client.post("/v1/notebooks", headers={"X-API-Key": api_key})
        installed = app.state.full_multilingual_v2_runtime
        principal = principal_from_claims({"sub": record.service_subject})
        mcp = create_pre_certification_mcp_server(
            principal_provider=lambda: principal,
            runtime_provider=lambda: (
                app.state.engine,
                installed,
                observed_identity,
                app.state.pre_certification_authority,
            ),
            transport="stdio",
        )
        listed = await mcp.request_handlers[mcp_types.ListToolsRequest](
            mcp_types.ListToolsRequest(method="tools/list")
        )
        listing = getattr(listed, "root", listed)
        tool_names = [tool.name for tool in getattr(listing, "tools", [])]
        security_checks = {
            "authentication_enforced": authorized.status_code == 200,
            "unauthorized_access_rejected": (
                anonymous.status_code in {401, 403} and invalid.status_code in {401, 403}
            ),
            "restricted_tool_surface_verified": (
                tool_names == ["observe_runtime"]
                and chat.status_code == 404
                and mutation.status_code == 404
                and override.status_code == 200
                and override.json().get("identity") == identity
            ),
        }
        if not all(security_checks.values()):
            raise RuntimeError("WP17_SECURITY_CHECK_FAILED")
        operator = principal_from_claims({"sub": config.reranker_activation_operator_subject})
        if not operator.authenticated:
            raise RuntimeError("WP17_OPERATOR_UNAUTHENTICATED")
        isolated_path = run_dir / "isolated-activation-state.json"
        _write_new(isolated_path, activation_path.read_text(encoding="utf-8"))
        isolated_store = DurableRerankerActivationStoreV1(
            path=isolated_path,
            signing_key=activation_key,
            prohibited_paths=(core.storage.sqlite.path,),
            credential_generation_id=generation_id,
            activation_generation_id=activation_generation,
        )
        isolated_store.load()
        initial_mode = installed.reranker.mode
        authority = DurableRerankerActivationAuthorityV1(
            runtime_authority=installed.reranker_activation,
            router=installed.reranker,
            store=isolated_store,
            authorized_operator_actor_id=operator.actor_id,
        )
        rolled_back = await authority.rollback(principal=operator)
        profile = profile_snapshot(
            ModelProfileDocument.from_file(root / PROFILE_PATH).select(PROFILE_NAME)
        )

        def restored_authority() -> DurableRerankerActivationAuthorityV1:
            return DurableRerankerActivationAuthorityV1(
                runtime_authority=RerankerActivationAuthorityV1(
                    router=installed.reranker,
                    component=profile.components["multilingual_reranker"],
                    model_cache=model_cache,
                ),
                router=installed.reranker,
                store=DurableRerankerActivationStoreV1(
                    path=isolated_path,
                    signing_key=activation_key,
                    prohibited_paths=(core.storage.sqlite.path,),
                    credential_generation_id=generation_id,
                    activation_generation_id=activation_generation,
                ),
                authorized_operator_actor_id=operator.actor_id,
            )

        after_first_restart = restored_authority()
        pass_through = await after_first_restart.restore()
        evidence = activation.activation_evidence
        if evidence is None:
            raise RuntimeError("WP17_ACTIVATION_EVIDENCE_MISSING")
        await after_first_restart.activate(principal=operator, evidence=evidence)
        reactivated = installed.reranker.mode
        await installed.reranker_activation.rollback()
        after_second_restart = restored_authority()
        bge_restored = await after_second_restart.restore()
        notebook = UUID(str(evaluation["production_store"]["before"]["notebook_id"]))
        service = EvidenceRetrievalApplicationService(app.state.engine, config)
        response = await service.execute(
            EvidenceSearchRequest(
                query="What does the Bhagavad Gita teach about duty and action?",
                mode=AdvancedRetrievalMode.RANKED,
                scope=EvidenceScopeRequest(notebook_id=notebook),
                representations=(EvidenceRepresentation.MULTILINGUAL_TEXT,),
                candidate_budget=50,
                evidence_budget=5,
            ),
            principal,
        )
        last = installed.reranker.last_execution
        rollback_checks = {
            "pass_through_after_restart": (
                initial_mode is V2RerankerMode.BGE_V2_M3
                and rolled_back is V2RerankerMode.PASS_THROUGH
                and pass_through is V2RerankerMode.PASS_THROUGH
            ),
            "reactivated_after_rollback": reactivated is V2RerankerMode.BGE_V2_M3,
            "bge_restored_after_second_restart": (
                bge_restored is V2RerankerMode.BGE_V2_M3
                and isolated_store.load().desired_mode is V2RerankerMode.BGE_V2_M3
            ),
        }
        final_checks = {
            "rehearsal_bge_execution_verified": bool(
                last is not None
                and last.mode is V2RerankerMode.BGE_V2_M3
                and last.revision == BGE_REVISION
                and last.device == "cuda"
                and last.cpu_fallback is False
                and last.candidate_count == last.score_count == 50
                and len(response.items) == 5
            )
        }
        if not all(rollback_checks.values()) or not all(final_checks.values()):
            raise RuntimeError("WP17_ROLLBACK_OR_FINAL_STATE_FAILED")
        isolated_final_hash = digest(isolated_path)
        execution_details = None if last is None else asdict(last)

    if (
        registry.load().active_generation_id is not None
        or digest(activation_path) != identity["activation_sha256"]
    ):
        raise RuntimeError("WP17_LIVE_AUTHORITY_CHANGED")
    if any(
        (core.storage.sqlite.path.with_name(core.storage.sqlite.path.name + suffix)).exists()
        for suffix in ("-wal", "-shm", "-journal")
    ):
        raise RuntimeError("WP17_PRODUCTION_SIDECAR_CREATED")
    signed_artifact(
        path=run_dir / "wp17-evaluation.json",
        kind="evaluation",
        status="PRODUCTION_PARITY_EVALUATION_PASS",
        identity=identity,
        checks=evaluation_checks,
        details={
            "evaluation_sha256": digest(evaluation_path),
            "per_query_sha256": digest(run_dir / "per-query.json"),
            "mapping_sha256": digest(run_dir / "mapping.json"),
            "checkpoint_sha256": digest(checkpoint_path),
            "thresholds_sha256": digest(thresholds_path),
        },
        additional={"metrics": metrics},
        executed_at=str(evaluation["generated_at"]),
        key=key,
    )
    signed_artifact(
        path=run_dir / "wp17-activation.json",
        kind="activation",
        status="PASS",
        identity=identity,
        checks=activation_checks,
        details={"signed_activation_sha256": digest(activation_path)},
        additional={"activation_generation_id": str(activation_generation)},
        key=key,
    )
    signed_artifact(
        path=run_dir / "wp17-security.json",
        kind="security",
        status="PASS",
        identity=identity,
        checks=security_checks,
        details={
            "anonymous_status": anonymous.status_code,
            "invalid_auth_status": invalid.status_code,
            "authorized_status": authorized.status_code,
            "chat_status": chat.status_code,
            "mutation_status": mutation.status_code,
            "tool_names": tool_names,
        },
        key=key,
    )
    signed_artifact(
        path=run_dir / "wp17-rollback.json",
        kind="rollback",
        status="PASS",
        identity=identity,
        checks=rollback_checks,
        details={"isolated_activation_state_sha256": isolated_final_hash},
        key=key,
    )
    signed_artifact(
        path=run_dir / "wp17-final-active-state.json",
        kind="final_active_state",
        status="PASS",
        identity=identity,
        checks=final_checks,
        details={"actual_reranker_execution": execution_details},
        additional={
            "bge_active": True,
            "reranker_mode": "BGE_V2_M3",
            "production_store_sha256": STORE_SHA256,
        },
        key=key,
    )
    return {
        "status": "WP17_GENERATION_REHEARSAL_EVIDENCE_CREATED",
        "generation_id": str(generation_id),
        "evidence_hashes": {
            kind: digest(run_dir / f"wp17-{kind}.json")
            for kind in ("evaluation", "activation", "security", "rollback")
        },
        "final_active_state_sha256": digest(run_dir / "wp17-final-active-state.json"),
    }


def verify(run_dir: Path) -> dict[str, Any]:
    """Read-only, independent WP-17 authority check of the complete evidence graph."""
    root = repository_root()
    config = ServerConfig.from_env(certified_production=True, pre_certification_observation=True)
    _, identity, observer = resolve_pre_certification_observation(server_config=config, root=root)
    registry_path = config.credential_registry_path
    if registry_path is None:
        raise RuntimeError("WP17_REGISTRY_UNAVAILABLE")
    registry = ProductionCredentialRegistry(
        path=(root / registry_path).resolve(), secret_store=WindowsCredentialStore()
    )
    generation_id = UUID(identity.credential_generation_id)
    if (
        run_dir.parent.resolve()
        != (registry.path.parent / "wp17_rehearsal" / str(generation_id)).resolve()
    ):
        raise RuntimeError("WP17_RUN_DIRECTORY_INVALID")
    document_ = registry.load()
    record = next(x for x in document_.generations if x.generation_id == generation_id)
    if (
        record.state is not CredentialState.PROVISIONED
        or document_.active_generation_id is not None
        or record.activation_path is None
        or record.observation_convergence_path is None
        or record.activation_sha256 != identity.activation_sha256
    ):
        raise RuntimeError("WP17_GENERATION_NOT_STAGED")
    convergence_path = Path(record.observation_convergence_path)
    observer.verify_convergence(convergence_path)
    activation_generation = UUID(
        str(document(Path(record.activation_path))["activation_generation_id"])
    )
    key = registry.retrieve(generation_id, CredentialKind.CERTIFICATION_SIGNING).encode()
    operator = principal_from_claims({"sub": config.reranker_activation_operator_subject})
    if not operator.authenticated:
        raise RuntimeError("WP17_OPERATOR_UNAUTHENTICATED")
    binding = WP17GenerationBindingV2(
        credential_generation_id=generation_id,
        activation_generation_id=activation_generation,
        certificate_generation_id=uuid4(),
        final_evidence_generation_id=uuid4(),
        activation_state_sha256=identity.activation_sha256,
        predecessor_certificate_sha256=digest(
            root / "scratch/phase8_5_full_multilingual_v2/operational/certification.json"
        ),
    )
    evidence = WP17EvidencePathsV1(
        amendment=root / "scratch/mnemo-v2-governance-amendment.json",
        approval=root / "scratch/mnemo-v2-decision7-approval.json",
        qrels=root / "scratch/mnemo-v2-qrel-certification.json",
        thresholds=root / "scratch/mnemo-v2-threshold-certification.json",
        evaluation=run_dir / "wp17-evaluation.json",
        wp16=root / "scratch/mnemo-v2-wp16-certification.json",
        activation=run_dir / "wp17-activation.json",
        transport_parity=convergence_path,
        security=run_dir / "wp17-security.json",
        rollback=run_dir / "wp17-rollback.json",
        final_active_state=run_dir / "wp17-final-active-state.json",
    )
    result = WP17CertificationAuthorityV1(
        state_path=run_dir / "generation-certificate.json",
        signing_key=key,
        authorized_operator_actor_id=operator.actor_id,
        prohibited_paths=(
            root / "scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db",
        ),
        generation_binding=binding,
    ).verify_generation_rehearsal(evidence=evidence)
    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 3 and sys.argv[1] == "verify":
        print(json.dumps(verify(Path(sys.argv[2]).resolve(strict=True)), sort_keys=True))
    elif len(sys.argv) == 2:
        print(
            json.dumps(asyncio.run(execute(Path(sys.argv[1]).resolve(strict=True))), sort_keys=True)
        )
    else:
        raise SystemExit("usage: run_wp17_generation_rehearsal.py [verify] RUN_DIR")
