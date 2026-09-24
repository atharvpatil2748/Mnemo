"""Server-owned, non-activating BGE production-parity evaluation lease."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mnemo.engine import KnowledgeEngine
from mnemo.phase85.profiles import ModelProfileDocument, profile_snapshot
from mnemo.phase85.v2_evaluation_runtime import ComposedFullMultilingualV2Runtime
from mnemo.retrieval.multilingual_providers import (
    BGE_RERANKER_PRODUCTION_EXECUTION_V1,
    BGEMultilingualReranker,
)

from mnemo_server.services.full_multilingual_v2_production import (
    ProductionFullMultilingualV2ServerDependencyAssemblerV1,
)
from mnemo_server.services.full_multilingual_v2_registration import (
    ServerOwnedFullMultilingualV2RegistrationV1,
)
from mnemo_server.services.full_multilingual_v2_startup import (
    PROFILE_NAME,
    PROFILE_PATH,
    InstalledFullMultilingualV2RuntimeV1,
)
from mnemo_server.services.v2_reranker_lifecycle import V2RerankerMode


@dataclass(slots=True, kw_only=True)
class ProductionParityBGEEvaluationLeaseV1:
    """Own a BGE evaluator that is structurally detached from the active router."""

    runtime: ComposedFullMultilingualV2Runtime
    reranker: BGEMultilingualReranker
    assembler: ProductionFullMultilingualV2ServerDependencyAssemblerV1
    installed: InstalledFullMultilingualV2RuntimeV1
    expected_mode: V2RerankerMode

    @classmethod
    async def open(
        cls,
        *,
        engine: KnowledgeEngine,
        installed: InstalledFullMultilingualV2RuntimeV1,
        workspace_root: Path,
        model_cache: Path,
        pre_certification_observation: bool = False,
    ) -> ProductionParityBGEEvaluationLeaseV1:
        expected_mode = (
            V2RerankerMode.BGE_V2_M3
            if pre_certification_observation
            else V2RerankerMode.PASS_THROUGH
        )
        if installed.reranker.mode is not expected_mode or (
            (installed.reranker.activation_record is not None) is not pre_certification_observation
        ):
            raise RuntimeError("PRODUCTION_EVALUATION_REQUIRES_INACTIVE_BGE")
        profile = profile_snapshot(
            ModelProfileDocument.from_file(workspace_root.resolve() / PROFILE_PATH).select(
                PROFILE_NAME
            )
        )
        reranker = BGEMultilingualReranker(
            profile.components["multilingual_reranker"],
            cache_folder=model_cache,
            execution=BGE_RERANKER_PRODUCTION_EXECUTION_V1,
        )
        await reranker.initialize()
        assembler = installed.assembler.for_nonactivating_evaluation(reranker=reranker)
        try:
            runtime = await ServerOwnedFullMultilingualV2RegistrationV1(
                engine=engine,
                identity=installed.assembler.identity,
                assembler=assembler,
            ).compose_internal_runtime()
        except BaseException:
            await assembler.close()
            await reranker.close()
            raise
        if installed.reranker.mode is not expected_mode:
            await assembler.close()
            await reranker.close()
            raise RuntimeError("PRODUCTION_EVALUATION_MUTATED_ACTIVE_ROUTER")
        return cls(
            runtime=runtime,
            reranker=reranker,
            assembler=assembler,
            installed=installed,
            expected_mode=expected_mode,
        )

    async def close(self) -> None:
        await self.assembler.close()
        await self.reranker.close()
        if self.installed.reranker.mode is not self.expected_mode or (
            (self.installed.reranker.activation_record is not None)
            is not (self.expected_mode is V2RerankerMode.BGE_V2_M3)
        ):
            raise RuntimeError("PRODUCTION_EVALUATION_MUTATED_ACTIVE_ROUTER")
