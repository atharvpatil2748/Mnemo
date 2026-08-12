"""Acceptance and invariant tests for Phase 4 Module 4.7 EmailChunker."""

import builtins
import re
import socket
from dataclasses import FrozenInstanceError, dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from types import MappingProxyType
from typing import cast
from uuid import UUID

import pytest
from email_ingestion import EmailParser
from mnemo.chunkers import ChunkerDispatcher, EmailChunker
from mnemo.cleaner import DocumentCleaner
from mnemo.ingestion import DocumentCanonicalizer
from mnemo.interfaces import (
    ChunkerInterfaceV2,
    ChunkingContext,
    ChunkingOptions,
    DependencyUnavailableError,
    UnsupportedError,
)
from mnemo.interfaces.types import FileMetadata
from mnemo.models import (
    Asset,
    BlockSpan,
    ChunkType,
    DocType,
    DocumentMetadata,
    DocumentVersion,
    DocumentVersionStatus,
    FrozenMetadata,
    ImageBlock,
    ParsedDocument,
    TextBlock,
)
from mnemo.registry import PluginRegistry


class WordCounter:
    tokenizer_id = "tests/words;adapter=v1"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def count(self, text: str) -> int:
        self.calls.append(text)
        return len(re.findall(r"\S+", text))


class CharacterCounter:
    tokenizer_id = "tests/characters;adapter=v1"

    def count(self, text: str) -> int:
        return len(text)


class MissingCounter:
    tokenizer_id = "tests/missing;adapter=v1"

    def count(self, text: str) -> int:
        raise DependencyUnavailableError("tokenizer unavailable", retryable=False)


@dataclass(slots=True)
class Plugin:
    name: str = "email-test"
    version: str = "1.0.0"
    core_version_range: str = ">=0.1.0,<1.0.0"

    def capabilities(self) -> tuple[str, ...]:
        return ("chunker",)

    def register(self, registry: PluginRegistry) -> None:
        registry.register_chunker_v2(
            DocType.EMAIL,
            EmailChunker(),
            priority=10,
            plugin_name=self.name,
        )


def _address(name: str, address: str) -> dict[str, object]:
    return {"name": name, "address": address}


def _attachment(
    local_id: str, *, inline: bool = False, mime_type: str = "application/pdf"
) -> dict[str, object]:
    return {
        "local_id": local_id,
        "filename": "attachment.bin",
        "mime_type": mime_type,
        "content_id": "asset@example.com" if inline else None,
        "disposition": "inline" if inline else "attachment",
        "inline": inline,
    }


def _message(
    index: int,
    *,
    source_index: int | None = None,
    thread: str | None = None,
    message_id: str | None = None,
    reply_to: str | None = None,
    attachments: tuple[dict[str, object], ...] = (),
) -> dict[str, object]:
    local_id = f"message-{index:06d}"
    resolved_message_id = message_id if message_id is not None else f"m{index}@example.com"
    parent_message_id: str | None = None
    if reply_to is not None:
        parent_match = re.fullmatch(r"message-(\d{6})", reply_to)
        if parent_match is not None:
            parent_message_id = f"m{int(parent_match.group(1))}@example.com"
    return {
        "local_id": local_id,
        "source_index": index if source_index is None else source_index,
        "thread_correlation": thread or (str(index + 1) * 64)[:64],
        "message_id": resolved_message_id,
        "in_reply_to": parent_message_id,
        "references": (),
        "reply_to_local_id": reply_to,
        "subject": f"Subject {index}",
        "sender": (_address("Sender", f"sender{index}@example.com"),),
        "recipients": {
            "to": (_address("Recipient", "to@example.com"),),
            "cc": (),
            "bcc": (),
        },
        "timestamp": "2026-08-11T10:00:00+05:30",
        "attachments": attachments,
    }


def _block_metadata(
    local_id: str,
    *,
    region: str = "body",
    body_format: str = "plain",
    attachment_id: str | None = None,
) -> FrozenMetadata:
    values: dict[str, object] = {
        "parser.email.message_local_id": local_id,
        "parser.email.region": region,
        "parser.email.body_format": body_format,
    }
    if attachment_id is not None:
        values["parser.email.attachment_local_id"] = attachment_id
    return FrozenMetadata(values)


def _document(
    messages: tuple[dict[str, object], ...],
    blocks: tuple[TextBlock | ImageBlock, ...],
    *,
    container: str = "mbox",
) -> ParsedDocument:
    return ParsedDocument(
        blocks=blocks,
        metadata=DocumentMetadata(
            content_hash="a" * 64,
            metadata=FrozenMetadata(
                {
                    "parser.email.schema_version": 1,
                    "parser.email.container_format": container,
                    "parser.email.messages": messages,
                }
            ),
        ),
        language="en",
        doc_type=DocType.EMAIL,
    )


def _text_block(
    ordinal: int,
    message_index: int,
    text: str,
    *,
    region: str = "body",
    body_format: str = "plain",
) -> TextBlock:
    return TextBlock(
        ordinal=ordinal,
        text=text,
        metadata=_block_metadata(
            f"message-{message_index:06d}", region=region, body_format=body_format
        ),
    )


def _words(count: int, prefix: str = "word") -> str:
    return " ".join(f"{prefix}{index}" for index in range(count))


def _context(document: ParsedDocument, *, target: int = 20, maximum: int = 40) -> ChunkingContext:
    return ChunkingContext(
        document_version=DocumentVersion(
            version_id=UUID(int=1),
            document_id=UUID(int=2),
            content_hash=document.metadata.content_hash,
            metadata=document.metadata,
            status=DocumentVersionStatus.CURRENT,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        options=ChunkingOptions(target_tokens=target, max_tokens=maximum),
    )


def _registry() -> PluginRegistry:
    registry = PluginRegistry(core_version="0.20.0")
    registry.load_plugin(Plugin())
    registry.freeze()
    return registry


def _eml(
    body: str,
    *,
    message_id: str,
    in_reply_to: str | None = None,
    subject: str = "Integration",
) -> bytes:
    headers = [
        "From: Alice <alice@example.com>",
        "To: Bob <bob@example.com>",
        f"Subject: {subject}",
        "Date: Tue, 11 Aug 2026 10:00:00 +0530",
        f"Message-ID: <{message_id}>",
        "Content-Type: text/plain; charset=utf-8",
    ]
    if in_reply_to is not None:
        headers.append(f"In-Reply-To: <{in_reply_to}>")
    return ("\r\n".join(headers) + "\r\n\r\n" + body + "\r\n").encode()


def _mbox(*messages: bytes) -> bytes:
    return b"".join(
        b"From sender@example.com Tue Aug 11 10:00:00 2026\n" + message + b"\n"
        for message in messages
    )


def _canonical(data: bytes, filename: str, mime_type: str) -> ParsedDocument:
    parsed = EmailParser().parse(
        data,
        filename,
        FileMetadata(
            content_hash=sha256(data).hexdigest(),
            size_bytes=len(data),
            mime_type=mime_type,
        ),
    )
    cleaned = DocumentCleaner().clean(parsed)
    assets = {
        transient.parser_local_id: Asset(
            asset_id=UUID(int=index + 10),
            mime_type=transient.mime_type,
            content_hash=sha256(transient.raw_bytes).hexdigest(),
            storage_uri=f"blob://{index}",
        )
        for index, transient in enumerate(cleaned.extracted_assets)
    }
    return DocumentCanonicalizer().canonicalize(cleaned, MappingProxyType(assets))


def test_v2_contract_capabilities_and_registration_isolation() -> None:
    chunker = EmailChunker()
    assert isinstance(chunker, ChunkerInterfaceV2)
    assert chunker.supported_doc_types == (DocType.EMAIL,)
    capabilities = chunker.capabilities()
    assert capabilities.supports_parent_child
    assert capabilities.preserves_semantic_boundaries
    assert not capabilities.supports_overlap
    registry = _registry()
    assert isinstance(registry.resolve_chunker_v2(DocType.EMAIL), EmailChunker)
    assert registry.resolve_chunker(DocType.EMAIL) is None


def test_single_eml_preserves_structured_message_context_without_headings() -> None:
    document = _document(
        (_message(0),),
        (_text_block(0, 0, _words(18)),),
        container="eml",
    )
    (draft,) = EmailChunker().chunk(document, _context(document), WordCounter())
    assert draft.chunk_type is ChunkType.PASSAGE
    assert draft.heading_path == ()
    assert draft.parent_index is None
    assert draft.source_span == BlockSpan(start_ordinal=0, end_ordinal=0)
    assert draft.metadata["chunker.email.subject"] == "Subject 0"
    assert draft.metadata["chunker.email.message_id"] == "m0@example.com"
    assert draft.metadata["chunker.email.timestamp"] == "2026-08-11T10:00:00+05:30"
    sender = draft.metadata["chunker.email.sender"]
    recipients = draft.metadata["chunker.email.recipients"]
    assert isinstance(sender, tuple) and isinstance(recipients, FrozenMetadata)
    sender_entries = cast(tuple[FrozenMetadata, ...], sender)
    recipient_entries = cast(tuple[FrozenMetadata, ...], recipients["to"])
    assert sender_entries[0]["address"] == "sender0@example.com"
    assert recipient_entries[0]["address"] == "to@example.com"


def test_threads_are_isolated_and_manifest_order_is_preserved() -> None:
    first_thread = "a" * 64
    second_thread = "b" * 64
    messages = (
        _message(0, thread=first_thread),
        _message(1, thread=first_thread, reply_to="message-000000"),
        _message(2, thread=second_thread),
    )
    blocks = tuple(_text_block(i, i, _words(16, f"m{i}")) for i in range(3))
    drafts = EmailChunker().chunk(
        _document(messages, blocks), _context(_document(messages, blocks)), WordCounter()
    )
    assert tuple(draft.metadata["chunker.email.message_local_id"] for draft in drafts) == (
        "message-000000",
        "message-000001",
        "message-000002",
    )
    assert drafts[1].parent_index == 0
    assert drafts[2].parent_index is None
    assert drafts[0].metadata["chunker.email.thread_correlation"] == first_thread
    assert drafts[2].metadata["chunker.email.thread_correlation"] == second_thread


def test_multiple_roots_and_missing_retrievable_parent_remain_valid() -> None:
    messages = (
        _message(0, thread="a" * 64),
        _message(1, thread="a" * 64, reply_to="message-000000"),
        _message(2, thread="b" * 64),
    )
    blocks = (
        _text_block(0, 1, _words(16, "child")),
        _text_block(1, 2, _words(16, "root")),
    )
    document = _document(messages, blocks)
    drafts = EmailChunker().chunk(document, _context(document), WordCounter())
    assert tuple(draft.parent_index for draft in drafts) == (None, None)


def test_reply_hierarchy_uses_parent_body_representative_for_all_child_drafts() -> None:
    messages = (
        _message(0, thread="a" * 64),
        _message(1, thread="a" * 64, reply_to="message-000000"),
    )
    blocks = (
        _text_block(0, 0, _words(20, "parent")),
        _text_block(1, 1, _words(20, "childa")),
        _text_block(2, 1, _words(20, "childb"), region="quoted"),
    )
    document = _document(messages, blocks)
    drafts = EmailChunker().chunk(document, _context(document), WordCounter())
    assert tuple(draft.parent_index for draft in drafts) == (None, 0, 0)


def test_body_quoted_and_signature_regions_remain_distinct_and_source_authored() -> None:
    blocks = (
        _text_block(0, 0, _words(16, "body")),
        _text_block(1, 0, _words(16, "quote"), region="quoted"),
        _text_block(2, 0, _words(16, "signature"), region="signature"),
    )
    document = _document((_message(0),), blocks, container="eml")
    drafts = EmailChunker().chunk(document, _context(document), WordCounter())
    assert tuple(draft.metadata["chunker.email.region"] for draft in drafts) == (
        "body",
        "quoted",
        "signature",
    )
    assert tuple(draft.text for draft in drafts) == tuple(block.text for block in blocks)


@pytest.mark.parametrize("body_format", ["plain", "html", "markdown"])
def test_approved_body_formats_are_consumed_without_reparsing(body_format: str) -> None:
    block = _text_block(0, 0, _words(16), body_format=body_format)
    document = _document((_message(0),), (block,), container="eml")
    (draft,) = EmailChunker().chunk(document, _context(document), WordCounter())
    assert draft.text == block.text
    assert draft.metadata["chunker.email.body_format"] == body_format


def test_contiguous_body_blocks_pack_with_valid_provenance() -> None:
    blocks = (_text_block(0, 0, _words(8, "a")), _text_block(1, 0, _words(8, "b")))
    document = _document((_message(0),), blocks, container="eml")
    (draft,) = EmailChunker().chunk(document, _context(document), WordCounter())
    assert draft.source_span == BlockSpan(start_ordinal=0, end_ordinal=1)
    assert draft.text == f"{blocks[0].text}\n\n{blocks[1].text}"


def test_same_block_semantic_splits_share_block_span_and_respect_maximum() -> None:
    block = _text_block(0, 0, f"{_words(18, 'one')}. {_words(18, 'two')}.")
    document = _document((_message(0),), (block,), container="eml")
    counter = WordCounter()
    drafts = EmailChunker().chunk(document, _context(document, target=20, maximum=25), counter)
    assert len(drafts) == 2
    assert {draft.source_span for draft in drafts} == {BlockSpan(start_ordinal=0, end_ordinal=0)}
    assert all(counter.count(draft.text) <= 25 for draft in drafts)


def test_word_fallback_never_truncates_and_uses_supplied_counter() -> None:
    text = _words(45)
    document = _document((_message(0),), (_text_block(0, 0, text),), container="eml")
    counter = WordCounter()
    drafts = EmailChunker().chunk(document, _context(document, target=20, maximum=30), counter)
    assert " ".join(draft.text for draft in drafts) == text
    assert counter.calls
    assert all(counter.count(draft.text) <= 30 for draft in drafts)


def test_atomic_inline_image_preserves_attachment_correlation() -> None:
    attachment_id = "message-000000-attachment-000001"
    message = _message(
        0,
        attachments=(_attachment(attachment_id, inline=True, mime_type="image/png"),),
    )
    image = ImageBlock(
        ordinal=0,
        asset_id=UUID(int=9),
        alt_text="descriptive inline image caption with enough words for retrieval context",
        metadata=_block_metadata("message-000000", attachment_id=attachment_id),
    )
    document = _document((message,), (image,), container="eml")
    (draft,) = EmailChunker().chunk(
        document, _context(document, target=40, maximum=80), WordCounter()
    )
    assert draft.chunk_type is ChunkType.CAPTION
    assert draft.metadata["chunker.email.attachment_local_ids"] == (attachment_id,)
    attachments = cast(tuple[FrozenMetadata, ...], draft.metadata["chunker.email.attachments"])
    assert attachments[0]["local_id"] == attachment_id


def test_inline_image_without_alt_text_emits_no_fabricated_content() -> None:
    attachment_id = "message-000000-attachment-000001"
    message = _message(0, attachments=(_attachment(attachment_id, inline=True),))
    image = ImageBlock(
        ordinal=0,
        asset_id=UUID(int=9),
        alt_text=None,
        metadata=_block_metadata("message-000000", attachment_id=attachment_id),
    )
    document = _document((message,), (image,), container="eml")
    assert EmailChunker().chunk(document, _context(document), WordCounter()) == ()


def test_oversized_atomic_image_and_word_fail_closed() -> None:
    attachment_id = "message-000000-attachment-000001"
    message = _message(0, attachments=(_attachment(attachment_id, inline=True),))
    image = ImageBlock(
        ordinal=0,
        asset_id=UUID(int=9),
        alt_text="x" * 41,
        metadata=_block_metadata("message-000000", attachment_id=attachment_id),
    )
    image_document = _document((message,), (image,), container="eml")
    with pytest.raises(UnsupportedError, match="inline image"):
        EmailChunker().chunk(image_document, _context(image_document), CharacterCounter())
    word_document = _document((_message(0),), (_text_block(0, 0, "x" * 41),), container="eml")
    with pytest.raises(UnsupportedError, match="word exceeds"):
        EmailChunker().chunk(word_document, _context(word_document), CharacterCounter())


def test_empty_message_emits_no_placeholder_and_short_leaf_is_dispatcher_filtered() -> None:
    empty = _document((_message(0),), (), container="eml")
    assert EmailChunker().chunk(empty, _context(empty), WordCounter()) == ()
    short = _document((_message(0),), (_text_block(0, 0, "brief reply"),), container="eml")
    result = ChunkerDispatcher(_registry(), WordCounter()).dispatch(short, _context(short))
    assert result == ()


@pytest.mark.parametrize(
    "metadata",
    [
        FrozenMetadata(),
        FrozenMetadata(
            {
                "parser.email.schema_version": 2,
                "parser.email.container_format": "eml",
                "parser.email.messages": (),
            }
        ),
        FrozenMetadata(
            {
                "parser.email.schema_version": 1,
                "parser.email.container_format": "eml",
                "parser.email.messages": (),
                "parser.email.unknown": True,
            }
        ),
    ],
)
def test_missing_incompatible_or_unknown_email_schema_fails(metadata: FrozenMetadata) -> None:
    document = ParsedDocument(
        blocks=(),
        metadata=DocumentMetadata(content_hash="a" * 64, metadata=metadata),
        language="en",
        doc_type=DocType.EMAIL,
    )
    with pytest.raises(UnsupportedError):
        EmailChunker().chunk(document, _context(document), WordCounter())


@pytest.mark.parametrize(
    "messages",
    [
        (_message(1),),
        (_message(0, reply_to="message-999999"),),
        (
            _message(0, thread="a" * 64, reply_to="message-000001"),
            _message(1, thread="a" * 64, reply_to="message-000000"),
        ),
        (
            _message(0, thread="a" * 64),
            _message(1, thread="b" * 64),
            _message(2, thread="a" * 64),
        ),
    ],
)
def test_invalid_local_ids_reply_graph_or_thread_partition_fails(
    messages: tuple[dict[str, object], ...],
) -> None:
    document = _document(messages, ())
    with pytest.raises(UnsupportedError):
        EmailChunker().chunk(document, _context(document), WordCounter())


@pytest.mark.parametrize(
    "metadata",
    [
        _block_metadata("message-999999"),
        _block_metadata("message-000000", region="unknown"),
        _block_metadata("message-000000", body_format="unknown"),
    ],
)
def test_invalid_block_message_region_or_format_fails(metadata: FrozenMetadata) -> None:
    document = _document(
        (_message(0),),
        (TextBlock(ordinal=0, text=_words(16), metadata=metadata),),
        container="eml",
    )
    with pytest.raises(UnsupportedError):
        EmailChunker().chunk(document, _context(document), WordCounter())


def test_invalid_or_cross_message_attachment_correlation_fails() -> None:
    attachment_id = "message-000001-attachment-000001"
    messages = (
        _message(0),
        _message(1, attachments=(_attachment(attachment_id, inline=True),)),
    )
    image = ImageBlock(
        ordinal=0,
        asset_id=UUID(int=9),
        alt_text="image text",
        metadata=_block_metadata("message-000000", attachment_id=attachment_id),
    )
    document = _document(messages, (image,))
    with pytest.raises(UnsupportedError, match="attachment correlation"):
        EmailChunker().chunk(document, _context(document), WordCounter())


def test_noncanonical_block_message_order_fails() -> None:
    messages = (_message(0, thread="a" * 64), _message(1, thread="a" * 64))
    blocks = (_text_block(0, 1, _words(16)), _text_block(1, 0, _words(16)))
    document = _document(messages, blocks)
    with pytest.raises(UnsupportedError, match="canonical message order"):
        EmailChunker().chunk(document, _context(document), WordCounter())


def test_wrong_document_type_and_missing_counter_fail_without_fallback() -> None:
    email = _document((_message(0),), (_text_block(0, 0, _words(16)),), container="eml")
    generic = replace(email, doc_type=DocType.GENERIC)
    with pytest.raises(UnsupportedError, match=r"DocType\.EMAIL"):
        EmailChunker().chunk(generic, _context(generic), WordCounter())
    with pytest.raises(DependencyUnavailableError):
        EmailChunker().chunk(email, _context(email), MissingCounter())


def test_output_is_deterministic_immutable_and_identity_free() -> None:
    document = _document((_message(0),), (_text_block(0, 0, _words(18)),), container="eml")
    first = EmailChunker().chunk(document, _context(document), WordCounter())
    second = EmailChunker().chunk(document, _context(document), WordCounter())
    assert first == second
    assert not hasattr(first[0], "id")
    assert not hasattr(first[0], "parent_chunk_id")
    assert not hasattr(first[0], "sibling_ids")
    with pytest.raises(FrozenInstanceError):
        first[0].text = "changed"  # type: ignore[misc]


def test_chunker_has_no_network_filesystem_uuid_or_source_parser_access() -> None:
    document = _document((_message(0),), (_text_block(0, 0, _words(18)),), container="eml")
    with (
        pytest.MonkeyPatch.context() as monkeypatch,
    ):
        monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: pytest.fail("network"))
        monkeypatch.setattr(builtins, "open", lambda *args, **kwargs: pytest.fail("filesystem"))
        drafts = EmailChunker().chunk(document, _context(document), WordCounter())
    assert len(drafts) == 1


def test_end_to_end_eml_boundary_to_dispatcher_finalization() -> None:
    data = _eml(_words(18), message_id="single@example.com")
    document = _canonical(data, "mail.eml", "message/rfc822")
    chunks = ChunkerDispatcher(_registry(), WordCounter()).dispatch(document, _context(document))
    assert len(chunks) == 1
    assert chunks[0].source_span == BlockSpan(start_ordinal=0, end_ordinal=0)
    assert re.fullmatch(r"[0-9a-f]{64}", chunks[0].id)
    assert chunks[0].metadata["chunker.email.message_local_id"] == "message-000000"


def test_end_to_end_mbox_materializes_parent_and_symmetric_siblings() -> None:
    root = _eml(_words(18, "root"), message_id="root@example.com")
    child_one = _eml(
        _words(18, "one"), message_id="one@example.com", in_reply_to="root@example.com"
    )
    child_two = _eml(
        _words(18, "two"), message_id="two@example.com", in_reply_to="root@example.com"
    )
    data = _mbox(root, child_one, child_two)
    document = _canonical(data, "mail.mbox", "application/mbox")
    chunks = ChunkerDispatcher(_registry(), WordCounter()).dispatch(document, _context(document))
    assert len(chunks) == 3
    assert chunks[1].parent_chunk_id == chunks[0].id
    assert chunks[2].parent_chunk_id == chunks[0].id
    assert chunks[1].sibling_ids == (chunks[2].id,)
    assert chunks[2].sibling_ids == (chunks[1].id,)
    assert all(chunk.heading_path == () for chunk in chunks)
    assert all(chunk.metadata["chunker.email.thread_correlation"] for chunk in chunks)
