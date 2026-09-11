from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from mnemo_server.evaluation import transport_runtime as subject


class _Model:
    def __init__(self, **values: object) -> None:
        self.__dict__.update(values)

    def model_copy(self, *, update: dict[str, object]) -> _Model:
        values = dict(self.__dict__)
        values.update(update)
        return _Model(**values)


def test_configuration_uses_registry_or_validation_candidate(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "mnemo.toml").write_text("[mnemo]")
    selected = SimpleNamespace(database=tmp_path / "selected.db", blob_root=tmp_path / "files")
    calls: list[str] = []

    class Registry:
        def __init__(self, **_kwargs: object) -> None:
            calls.append("registry")

        def resolve(self, alias: str) -> object:
            calls.append(alias)
            return selected

    core = _Model(
        storage=_Model(
            sqlite=_Model(path=tmp_path / "old.db"), filesystem=_Model(root=tmp_path / "old")
        )
    )
    monkeypatch.setattr(subject, "ServerOwnedEvaluationNotebookRegistryV1", Registry)
    monkeypatch.setattr(subject.MnemoConfig, "from_file", lambda _path: core)
    monkeypatch.setattr(
        subject,
        "resolve_evaluation_notebook_validation_candidate_v1",
        lambda **_kwargs: calls.append("candidate") or selected,
    )

    configured, server = subject._configuration(tmp_path, "phase8_5", validation_candidate=False)
    assert configured.storage.sqlite.path == selected.database
    assert configured.storage.filesystem.root == selected.blob_root
    assert server.auth_mode == "api-key"
    assert calls == ["registry", "phase8_5"]

    subject._configuration(tmp_path, "phase8_6", validation_candidate=True)
    assert calls[-1] == "candidate"


@pytest.mark.parametrize("transport", ["http", "sse"])
def test_main_builds_real_transport_application_and_requires_port(
    transport: str, tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    core = _Model()
    config = _Model()
    monkeypatch.setattr(
        subject,
        "_arguments",
        lambda: SimpleNamespace(
            transport=transport,
            alias="phase8_6",
            port=8123,
            workspace=tmp_path,
            validation_candidate=True,
        ),
    )
    monkeypatch.setattr(subject, "_configuration", lambda *_args, **_kwargs: (core, config))
    observed: dict[str, object] = {}
    monkeypatch.setattr(
        subject,
        "create_app",
        lambda *args, **kwargs: (
            observed.update(kind="http", args=args, kwargs=kwargs) or "http-app"
        ),
    )
    monkeypatch.setattr(subject, "KnowledgeEngine", lambda *_args, **_kwargs: "engine")
    monkeypatch.setattr(subject, "build_retrieval_cursor_codec", lambda _config: "codec")
    monkeypatch.setattr(subject, "principal_from_claims", lambda claims: ("principal", claims))
    monkeypatch.setattr(subject, "create_mcp_server", lambda **_kwargs: "mcp-server")
    monkeypatch.setattr(
        subject,
        "create_sse_app",
        lambda **kwargs: observed.update(kind="sse", kwargs=kwargs) or "sse-app",
    )
    monkeypatch.setattr(
        subject.uvicorn,
        "run",
        lambda app, **kwargs: observed.update(app=app, uvicorn=kwargs),
    )

    assert subject.main() == 0
    assert observed["kind"] == transport
    assert observed["app"] == f"{transport}-app"
    assert observed["uvicorn"] == {"host": "127.0.0.1", "port": 8123, "log_level": "warning"}


def test_main_stdio_delegates_and_network_transports_reject_zero_port(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    args = SimpleNamespace(
        transport="stdio",
        alias="phase8_5",
        port=0,
        workspace=tmp_path,
        validation_candidate=False,
    )
    monkeypatch.setattr(subject, "_arguments", lambda: args)
    monkeypatch.setattr(subject, "_configuration", lambda *_args, **_kwargs: ("core", "server"))
    observed: list[object] = []

    async def run_stdio(core: object, server: object) -> None:
        observed.extend((core, server))

    monkeypatch.setattr(subject, "_run_stdio", run_stdio)
    assert subject.main() == 0
    assert observed == ["core", "server"]

    args.transport = "http"
    with pytest.raises(ValueError, match="require --port"):
        subject.main()


@pytest.mark.anyio
async def test_run_stdio_initializes_runs_and_always_shuts_down(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    events: list[str] = []

    class Engine:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            events.append("construct")

        async def initialize(self) -> None:
            events.append("initialize")

        async def shutdown(self) -> None:
            events.append("shutdown")

    class Streams:
        async def __aenter__(self) -> tuple[str, str]:
            events.append("streams-enter")
            return "read", "write"

        async def __aexit__(self, *_args: object) -> None:
            events.append("streams-exit")

    class Server:
        def create_initialization_options(self) -> str:
            return "options"

        async def run(self, read: str, write: str, options: str) -> None:
            assert (read, write, options) == ("read", "write", "options")
            events.append("run")

    monkeypatch.setattr(
        subject, "configure_stderr_logging", lambda _level: events.append("logging")
    )
    monkeypatch.setattr(subject, "KnowledgeEngine", Engine)
    monkeypatch.setattr(subject, "build_retrieval_cursor_codec", lambda _config: "codec")
    monkeypatch.setattr(subject, "principal_from_claims", lambda _claims: "principal")
    monkeypatch.setattr(subject, "create_mcp_server", lambda **_kwargs: Server())
    monkeypatch.setattr(subject, "stdio_server", lambda: Streams())

    await subject._run_stdio(_Model(), _Model())

    assert events == [
        "logging",
        "construct",
        "initialize",
        "streams-enter",
        "run",
        "streams-exit",
        "shutdown",
    ]
