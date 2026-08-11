"""Offline-only adapter for a separately provisioned o200k_base asset."""

import importlib
from hashlib import sha256
from pathlib import Path
from typing import Final, Protocol, cast

from mnemo.interfaces import ContractValidationError, DependencyUnavailableError

O200K_BASE_ASSET_NAME: Final = "o200k_base.tiktoken"
O200K_BASE_ASSET_SHA256: Final = "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"
O200K_BASE_ASSET_SIZE: Final = 3_613_922
O200K_BASE_UPSTREAM_URL: Final = (
    "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken"
)
O200K_BASE_TOKENIZER_ID: Final = (
    "mnemo/o200k_base;adapter=v1;engine=tiktoken-0.13.0;asset-sha256=" + O200K_BASE_ASSET_SHA256
)

# Copied from tiktoken 0.13.0's MIT-licensed openai_public.o200k_base
# constructor. The upstream copyright notice is retained in THIRD_PARTY_NOTICES.
_O200K_PATTERN: Final = (
    r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*"
    r"[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?|"
    r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+"
    r"[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?|"
    r"\p{N}{1,3}| ?[^\s\p{L}\p{N}]+[\r\n/]*|\s*[\r\n]+|"
    r"\s+(?!\S)|\s+"
)


class _Encoding(Protocol):
    def encode_ordinary(self, text: str) -> list[int]: ...


class _TiktokenModule(Protocol):
    def Encoding(
        self,
        *,
        name: str,
        pat_str: str,
        mergeable_ranks: dict[bytes, int],
        special_tokens: dict[str, int],
    ) -> _Encoding: ...


class _TiktokenLoadModule(Protocol):
    def load_tiktoken_bpe(self, path: str, *, expected_hash: str) -> dict[bytes, int]: ...


class O200KBaseTokenCounter:
    """Count tokens using a verified local asset without runtime networking."""

    __slots__ = ("_encoding",)

    def __init__(self, asset_path: Path) -> None:
        """Verify and load a provisioned o200k_base vocabulary."""
        path = Path(asset_path)
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise DependencyUnavailableError(
                f"provisioned tokenizer asset is unavailable: {path}", retryable=False
            ) from exc
        if len(payload) != O200K_BASE_ASSET_SIZE or sha256(payload).hexdigest() != (
            O200K_BASE_ASSET_SHA256
        ):
            raise DependencyUnavailableError(
                "provisioned tokenizer asset failed size or SHA-256 verification",
                retryable=False,
            )
        try:
            tiktoken = cast(_TiktokenModule, importlib.import_module("tiktoken"))
            loader = cast(_TiktokenLoadModule, importlib.import_module("tiktoken.load"))
            ranks = loader.load_tiktoken_bpe(str(path), expected_hash=O200K_BASE_ASSET_SHA256)
            self._encoding = tiktoken.Encoding(
                name="mnemo_o200k_base",
                pat_str=_O200K_PATTERN,
                mergeable_ranks=ranks,
                special_tokens={"<|endoftext|>": 199999, "<|endofprompt|>": 200018},
            )
        except Exception as exc:
            raise DependencyUnavailableError(
                "provisioned tokenizer asset could not be loaded", retryable=False
            ) from exc

    @property
    def tokenizer_id(self) -> str:
        """Return the frozen tokenizer contract identity."""
        return O200K_BASE_TOKENIZER_ID

    def count(self, text: str) -> int:
        """Count ordinary text exactly as supplied."""
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        if any(0xD800 <= ord(character) <= 0xDFFF for character in text):
            raise ContractValidationError("text contains an unpaired Unicode surrogate")
        return len(self._encoding.encode_ordinary(text))
