"""Governed separation of V2 exposure from BGE reranker activation."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID

from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import PrincipalContextV1
from mnemo.interfaces.advanced_retrieval import AdvancedRetrievalSourceV1
from mnemo.interfaces.multilingual import MultilingualCandidateRerankerV3
from mnemo.models.multilingual import MultilingualRerankScoreV2
from mnemo.models.multilingual_reranking import (
    RERANKER_PAIR_POLICY_V2_ID,
    V2_TYPED_CANDIDATE_BUILDER_ID,
    MultilingualRerankCandidateV3,
)
from mnemo.phase85.profiles import ModelProfileComponent
from mnemo.phase85.v2_readiness import V2ReadinessSnapshot, project_v2_readiness
from mnemo.retrieval.full_multilingual_v2 import (
    PASS_THROUGH_RERANKER_ID,
    PassThroughV2RerankerV1,
)
from mnemo.retrieval.multilingual_providers import (
    BGE_RERANKER_MODEL,
    BGE_RERANKER_PRODUCTION_EXECUTION_V1,
    BGE_RERANKER_REVISION,
    BGEMultilingualReranker,
)


class V2RerankerMode(StrEnum):
    PASS_THROUGH = "PASS_THROUGH"
    BGE_V2_M3 = "BGE_V2_M3"


@dataclass(frozen=True, slots=True, kw_only=True)
class RerankerActivationEvidenceV1:
    v2_exposed: bool
    production_evaluation_passed: bool
    production_store_identity: str
    expected_production_store_identity: str
    candidate_builder_id: str = V2_TYPED_CANDIDATE_BUILDER_ID
    model: str = BGE_RERANKER_MODEL
    revision: str = BGE_RERANKER_REVISION
    pair_policy: str = RERANKER_PAIR_POLICY_V2_ID
    device: str = "cuda"
    batch_size: int = 2
    cpu_fallback: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class RerankerActivationRecordV1:
    previous_mode: V2RerankerMode
    active_mode: V2RerankerMode
    activated_at: str
    model: str
    revision: str
    candidate_builder_id: str
    pair_policy: str
    device: str
    batch_size: int
    cpu_fallback: bool


_DURABLE_STATE_SCHEMA = "mnemo.v2-reranker-activation-state/1"


@dataclass(frozen=True, slots=True, kw_only=True)
class DurableRerankerActivationStateV1:
    """Authenticated desired reranker state retained outside the corpus store."""

    sequence: int
    desired_mode: V2RerankerMode
    updated_at: str
    updated_by_actor_id: UUID | None
    activation_evidence: RerankerActivationEvidenceV1 | None
    signature: str

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("durable activation sequence must be non-negative")
        has_evidence = self.activation_evidence is not None
        if (self.desired_mode is V2RerankerMode.BGE_V2_M3) is not has_evidence:
            raise ValueError("BGE durable state and activation evidence must agree")


class DurableRerankerActivationStoreV1:
    """Atomic HMAC-authenticated state file; never stores corpus data."""

    def __init__(
        self, *, path: Path, signing_key: bytes, prohibited_paths: tuple[Path, ...]
    ) -> None:
        if len(signing_key) < 32:
            raise ValueError("durable activation signing key must contain at least 32 bytes")
        resolved = path.resolve()
        if any(resolved == item.resolve() for item in prohibited_paths):
            raise ValueError("durable activation state cannot use a protected database path")
        self._path = resolved
        self._key = bytes(signing_key)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> DurableRerankerActivationStateV1:
        if not self._path.exists():
            return DurableRerankerActivationStateV1(
                sequence=0,
                desired_mode=V2RerankerMode.PASS_THROUGH,
                updated_at="not-persisted",
                updated_by_actor_id=None,
                activation_evidence=None,
                signature="",
            )
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError("DURABLE_BGE_ACTIVATION_STATE_MALFORMED") from error
        if not isinstance(raw, dict) or raw.get("schema_version") != _DURABLE_STATE_SCHEMA:
            raise RuntimeError("DURABLE_BGE_ACTIVATION_STATE_MALFORMED")
        signature = raw.pop("signature", None)
        if not isinstance(signature, str) or not hmac.compare_digest(signature, self._sign(raw)):
            raise RuntimeError("DURABLE_BGE_ACTIVATION_STATE_SIGNATURE_INVALID")
        try:
            evidence_raw = raw.get("activation_evidence")
            evidence = (
                None if evidence_raw is None else RerankerActivationEvidenceV1(**evidence_raw)
            )
            actor_raw = raw.get("updated_by_actor_id")
            return DurableRerankerActivationStateV1(
                sequence=int(raw["sequence"]),
                desired_mode=V2RerankerMode(str(raw["desired_mode"])),
                updated_at=str(raw["updated_at"]),
                updated_by_actor_id=None if actor_raw is None else UUID(str(actor_raw)),
                activation_evidence=evidence,
                signature=signature,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError("DURABLE_BGE_ACTIVATION_STATE_MALFORMED") from error

    def commit(
        self,
        *,
        desired_mode: V2RerankerMode,
        principal: PrincipalContextV1,
        evidence: RerankerActivationEvidenceV1 | None,
    ) -> DurableRerankerActivationStateV1:
        previous = self.load()
        unsigned: dict[str, Any] = {
            "schema_version": _DURABLE_STATE_SCHEMA,
            "sequence": previous.sequence + 1,
            "desired_mode": desired_mode.value,
            "updated_at": datetime.now(UTC).isoformat(),
            "updated_by_actor_id": str(principal.actor_id),
            "activation_evidence": None if evidence is None else asdict(evidence),
        }
        signature = self._sign(unsigned)
        payload = {**unsigned, "signature": signature}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self._path.parent, prefix=f".{self._path.name}.", suffix=".tmp"
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._path)
        finally:
            temporary.unlink(missing_ok=True)
        return DurableRerankerActivationStateV1(
            sequence=int(unsigned["sequence"]),
            desired_mode=desired_mode,
            updated_at=str(unsigned["updated_at"]),
            updated_by_actor_id=principal.actor_id,
            activation_evidence=evidence,
            signature=signature,
        )

    def _sign(self, value: dict[str, Any]) -> str:
        encoded = json.dumps(
            value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hmac.new(self._key, encoded, hashlib.sha256).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class RerankerExecutionObservationV1:
    """Auditable proof of the last router execution without changing candidates."""

    mode: V2RerankerMode
    model: str
    revision: str
    pair_policy: str
    device: str
    batch_size: int
    cpu_fallback: bool
    candidate_count: int
    score_count: int
    score_digest: str


class GovernedV2RerankerRouterV1:
    """Stable V3 reranker port whose explicit mode is governed independently."""

    def __init__(self) -> None:
        self._mode = V2RerankerMode.PASS_THROUGH
        self._delegate: MultilingualCandidateRerankerV3 = PassThroughV2RerankerV1()
        self._activation: RerankerActivationRecordV1 | None = None
        self._last_execution: RerankerExecutionObservationV1 | None = None

    @property
    def mode(self) -> V2RerankerMode:
        return self._mode

    @property
    def activation_record(self) -> RerankerActivationRecordV1 | None:
        return self._activation

    @property
    def last_execution(self) -> RerankerExecutionObservationV1 | None:
        return self._last_execution

    async def score_candidates(
        self,
        *,
        query: str,
        candidates: tuple[MultilingualRerankCandidateV3, ...],
    ) -> tuple[MultilingualRerankScoreV2, ...]:
        scores = await self._delegate.score_candidates(query=query, candidates=candidates)
        activation = self._activation
        self._last_execution = RerankerExecutionObservationV1(
            mode=self._mode,
            model=(activation.model if activation is not None else PASS_THROUGH_RERANKER_ID),
            revision=(activation.revision if activation is not None else "1"),
            pair_policy=(
                activation.pair_policy
                if activation is not None
                else "identity-preserve-fused-order"
            ),
            device=(activation.device if activation is not None else "none"),
            batch_size=(activation.batch_size if activation is not None else 0),
            cpu_fallback=(activation.cpu_fallback if activation is not None else False),
            candidate_count=len(candidates),
            score_count=len(scores),
            score_digest=hashlib.sha256(
                json.dumps(
                    [
                        {
                            "candidate_id": str(item.candidate_id),
                            "score": item.score,
                            "model": item.model,
                            "revision": item.revision,
                        }
                        for item in scores
                    ],
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
        )
        return scores

    def _activate(
        self, delegate: MultilingualCandidateRerankerV3, record: RerankerActivationRecordV1
    ) -> None:
        if self._mode is not V2RerankerMode.PASS_THROUGH:
            raise RuntimeError("BGE_RERANKER_ALREADY_ACTIVE")
        self._delegate = delegate
        self._mode = V2RerankerMode.BGE_V2_M3
        self._activation = record

    def _restore_pass_through(self) -> MultilingualCandidateRerankerV3:
        if self._mode is not V2RerankerMode.BGE_V2_M3:
            raise RuntimeError("BGE_RERANKER_NOT_ACTIVE")
        previous = self._delegate
        self._delegate = PassThroughV2RerankerV1()
        self._mode = V2RerankerMode.PASS_THROUGH
        self._activation = None
        return previous


class RerankerActivationAuthorityV1:
    """Only authority permitted to transition PASS_THROUGH <-> BGE_V2_M3."""

    def __init__(
        self,
        *,
        router: GovernedV2RerankerRouterV1,
        component: ModelProfileComponent,
        model_cache: Path,
        reranker_factory: Callable[[], BGEMultilingualReranker] | None = None,
    ) -> None:
        self._router = router
        self._component = component
        self._model_cache = model_cache
        self._reranker_factory = reranker_factory

    async def activate(self, evidence: RerankerActivationEvidenceV1) -> RerankerActivationRecordV1:
        expected = BGE_RERANKER_PRODUCTION_EXECUTION_V1
        valid = (
            evidence.v2_exposed
            and evidence.production_evaluation_passed
            and evidence.production_store_identity == evidence.expected_production_store_identity
            and evidence.candidate_builder_id == V2_TYPED_CANDIDATE_BUILDER_ID
            and evidence.model == BGE_RERANKER_MODEL
            and evidence.revision == BGE_RERANKER_REVISION
            and evidence.pair_policy == RERANKER_PAIR_POLICY_V2_ID
            and evidence.device == expected.device == "cuda"
            and evidence.batch_size == expected.batch_size == 2
            and evidence.cpu_fallback is expected.allow_device_fallback is False
        )
        if not valid:
            raise RuntimeError("BGE_ACTIVATION_EVIDENCE_INVALID")
        reranker = (
            self._reranker_factory()
            if self._reranker_factory is not None
            else BGEMultilingualReranker(
                self._component,
                cache_folder=self._model_cache,
                execution=expected,
            )
        )
        await reranker.initialize()
        record = RerankerActivationRecordV1(
            previous_mode=V2RerankerMode.PASS_THROUGH,
            active_mode=V2RerankerMode.BGE_V2_M3,
            activated_at=datetime.now(UTC).isoformat(),
            model=evidence.model,
            revision=evidence.revision,
            candidate_builder_id=evidence.candidate_builder_id,
            pair_policy=evidence.pair_policy,
            device=evidence.device,
            batch_size=evidence.batch_size,
            cpu_fallback=evidence.cpu_fallback,
        )
        try:
            self._router._activate(reranker, record)
        except BaseException:
            await reranker.close()
            raise
        return record

    async def rollback(self) -> V2RerankerMode:
        reranker = self._router._restore_pass_through()
        close = getattr(reranker, "close", None)
        if not callable(close):
            raise RuntimeError("BGE_RERANKER_ROLLBACK_CLOSE_MISSING")
        await close()
        return self._router.mode


class DurableRerankerActivationAuthorityV1:
    """Server-owned durable activation/rollback authority with restart restore."""

    def __init__(
        self,
        *,
        runtime_authority: RerankerActivationAuthorityV1,
        router: GovernedV2RerankerRouterV1,
        store: DurableRerankerActivationStoreV1,
        authorized_operator_actor_id: UUID | None,
    ) -> None:
        self._runtime = runtime_authority
        self._router = router
        self._store = store
        self._authorized_operator_actor_id = authorized_operator_actor_id

    @property
    def state_path(self) -> Path:
        return self._store.path

    def desired_state(self) -> DurableRerankerActivationStateV1:
        return self._store.load()

    async def restore(self) -> V2RerankerMode:
        """Restore only an authenticated exact state record during server startup."""
        state = self._store.load()
        if state.desired_mode is V2RerankerMode.PASS_THROUGH:
            if self._router.mode is not V2RerankerMode.PASS_THROUGH:
                raise RuntimeError("DURABLE_BGE_RESTORE_RUNTIME_NOT_PASS_THROUGH")
            return self._router.mode
        evidence = state.activation_evidence
        if evidence is None:
            raise RuntimeError("DURABLE_BGE_ACTIVATION_STATE_MALFORMED")
        await self._runtime.activate(evidence)
        return self._router.mode

    async def activate(
        self,
        *,
        principal: PrincipalContextV1,
        evidence: RerankerActivationEvidenceV1,
    ) -> RerankerActivationRecordV1:
        self._authorize(principal)
        record = await self._runtime.activate(evidence)
        try:
            self._store.commit(
                desired_mode=V2RerankerMode.BGE_V2_M3,
                principal=principal,
                evidence=evidence,
            )
        except BaseException:
            await self._runtime.rollback()
            raise
        return record

    async def rollback(self, *, principal: PrincipalContextV1) -> V2RerankerMode:
        self._authorize(principal)
        mode = await self._runtime.rollback()
        try:
            self._store.commit(
                desired_mode=V2RerankerMode.PASS_THROUGH,
                principal=principal,
                evidence=None,
            )
        except BaseException as error:
            raise RuntimeError("DURABLE_BGE_ROLLBACK_STATE_COMMIT_FAILED") from error
        return mode

    def _authorize(self, principal: PrincipalContextV1) -> None:
        if (
            not isinstance(principal, PrincipalContextV1)
            or not principal.authenticated
            or self._authorized_operator_actor_id is None
            or principal.actor_id != self._authorized_operator_actor_id
        ):
            raise PermissionError("authorized server operator principal is required")


class V2ExposureAuthorityV1:
    """Sole exposure transition; it cannot activate or load a reranker model."""

    async def expose(
        self,
        *,
        engine: KnowledgeEngine,
        source: AdvancedRetrievalSourceV1,
        readiness: V2ReadinessSnapshot,
        reranker: GovernedV2RerankerRouterV1,
    ) -> V2ReadinessSnapshot:
        if not readiness.v2_active or readiness.v2_exposed:
            raise RuntimeError("V2_EXPOSURE_READINESS_INCOMPLETE")
        if reranker.mode is not V2RerankerMode.PASS_THROUGH:
            raise RuntimeError("V2_EXPOSURE_REQUIRES_PASS_THROUGH")
        if reranker.activation_record is not None:
            raise RuntimeError("V2_EXPOSURE_CANNOT_ACTIVATE_BGE")
        exposed = project_v2_readiness(replace(readiness.inputs, runtime_exposure_selected=True))
        if not exposed.v2_exposed:
            raise RuntimeError("V2_EXPOSURE_TRANSITION_FAILED")
        await engine.install_exposed_full_multilingual_v2(source=source, readiness=exposed)
        return exposed
