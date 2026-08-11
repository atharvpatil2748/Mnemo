"""Provisioning and offline tokenizer acceptance tests."""

from pathlib import Path
from shutil import copyfile

import pytest
from mnemo.interfaces import ContractValidationError, DependencyUnavailableError
from mnemo.tokenizers import O200K_BASE_TOKENIZER_ID, O200KBaseTokenCounter
from mnemo_server import cli
from mnemo_server.tokenizer_provisioning import (
    provision_tokenizer,
    provisioned_tokenizer_path,
)


def _provisioned_asset() -> Path:
    path = provisioned_tokenizer_path()
    if not path.is_file():
        pytest.skip("run `mnemo provision-tokenizer` before tokenizer acceptance tests")
    return path


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", 0),
        ("hello", 1),
        ("  spaces\tand\nlines", 5),
        ("line1\nline2", 5),
        ("line1\r\nline2", 5),
        ("caf\u00e9", 2),
        ("cafe\u0301", 3),
        ("\u0928\u092e\u0938\u094d\u0924\u0947 \u0926\u0941\u0928\u093f\u092f\u093e", 5),
        ("\u4f60\u597d\uff0c\u4e16\u754c", 3),
        ("a\u0301", 2),
        ("\U0001f468\u200d\U0001f469\u200d\U0001f467\u200d\U0001f466", 11),
        ("def f(x: int) -> int:\n    return x * 2", 15),
        ("\u222b\u2080\u00b9 x\u00b2 dx = \u2153", 12),
        ("<|endoftext|>", 7),
    ],
)
def test_frozen_golden_vectors(text: str, expected: int) -> None:
    counter = O200KBaseTokenCounter(_provisioned_asset())
    assert counter.tokenizer_id == O200K_BASE_TOKENIZER_ID
    assert counter.count(text) == expected
    assert counter.count(text) == expected


def test_counter_rejects_missing_corrupt_and_surrogate(tmp_path: Path) -> None:
    with pytest.raises(DependencyUnavailableError):
        O200KBaseTokenCounter(tmp_path / "missing.tiktoken")
    corrupt = tmp_path / "corrupt.tiktoken"
    corrupt.write_bytes(b"invalid")
    with pytest.raises(DependencyUnavailableError):
        O200KBaseTokenCounter(corrupt)
    counter = O200KBaseTokenCounter(_provisioned_asset())
    with pytest.raises(ContractValidationError):
        counter.count("\ud800")
    with pytest.raises(TypeError):
        counter.count(1)  # type: ignore[arg-type]


def test_air_gapped_import_is_verified_and_atomic(tmp_path: Path) -> None:
    installed = provision_tokenizer(source=_provisioned_asset(), data_root=tmp_path)
    assert installed == provisioned_tokenizer_path(tmp_path)
    assert installed.read_bytes() == _provisioned_asset().read_bytes()
    manifest = installed.with_suffix(".json").read_text(encoding="utf-8")
    assert O200K_BASE_TOKENIZER_ID in manifest


def test_explicit_download_uses_frozen_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _provisioned_asset()

    def fake_retrieve(url: str, filename: Path) -> tuple[str, None]:
        assert url.startswith("https://openaipublic.blob.core.windows.net/")
        copyfile(source, filename)
        return str(filename), None

    monkeypatch.setattr(
        "mnemo_server.tokenizer_provisioning.urllib.request.urlretrieve", fake_retrieve
    )
    installed = provision_tokenizer(data_root=tmp_path)
    assert O200KBaseTokenCounter(installed).count("hello") == 1


def test_cli_import_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "mnemo",
            "provision-tokenizer",
            "--from-file",
            str(_provisioned_asset()),
            "--data-root",
            str(tmp_path),
        ],
    )
    assert cli.main() == 0
    assert str(provisioned_tokenizer_path(tmp_path)) in capsys.readouterr().out
