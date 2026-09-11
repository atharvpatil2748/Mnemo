"""Server-owned composition boundary for the internal Full Multilingual V2 runtime."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from mnemo.engine import KnowledgeEngine
from mnemo.phase85.v2_evaluation_runtime import (
    ComposedFullMultilingualV2Runtime,
    FullMultilingualV2EvaluationRuntimeFactory,
    V2RuntimeCompositionDependencies,
    V2RuntimeIdentityV1,
)

from .authorization import CentralAuthorizationServiceV1


@runtime_checkable
class FullMultilingualV2ServerDependencyAssemblerV1(Protocol):  # pragma: no cover
    """Server-side seam that will own the five security-sensitive adapters."""

    async def assemble_v2_runtime_dependencies(
        self,
        *,
        engine: KnowledgeEngine,
        authorization: CentralAuthorizationServiceV1,
    ) -> V2RuntimeCompositionDependencies: ...


class ServerOwnedFullMultilingualV2RegistrationV1:
    """Build the internal core factory without exposing it through a transport.

    Core defines contracts and application composition.  The server owns the
    authenticated principal boundary and the central authorization service,
    so it also owns production dependency registration.  The assembler remains
    unimplemented until the separately authorized five-adapter phase.
    """

    registration_id = "mnemo.server.full-multilingual-v2-registration/1"

    def __init__(
        self,
        *,
        engine: KnowledgeEngine,
        identity: V2RuntimeIdentityV1,
        assembler: FullMultilingualV2ServerDependencyAssemblerV1,
    ) -> None:
        if not isinstance(assembler, FullMultilingualV2ServerDependencyAssemblerV1):
            raise TypeError("assembler must implement the governed server V2 registration port")
        self._engine = engine
        self._identity = identity
        self._assembler = assembler

    async def build_internal_factory(self) -> FullMultilingualV2EvaluationRuntimeFactory:
        """Create one factory using the server-owned authorization authority."""
        authorization = CentralAuthorizationServiceV1(self._engine)
        dependencies = await self._assembler.assemble_v2_runtime_dependencies(
            engine=self._engine,
            authorization=authorization,
        )
        return FullMultilingualV2EvaluationRuntimeFactory(
            identity=self._identity,
            dependencies=dependencies,
        )

    async def compose_internal_runtime(self) -> ComposedFullMultilingualV2Runtime:
        """Compose internally; this method performs no public registration."""
        factory = await self.build_internal_factory()
        return await factory.compose()
