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
from mnemo.chunkers.email import (
    _address_tuple,
    _attachment_tuple,
    _identifier_tuple,
    _Message,
    _non_negative_int,
    _optional_identifier,
    _optional_string,
    _required_string,
)
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
    TableBlock,
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
    registry = PluginRegistry(core_version="0.20.1")
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


def test_message_attachment_ids_property() -> None:
    msg = _Message(
        local_id="message-000000",
        source_index=0,
        thread_correlation="a" * 64,
        message_id="m0@example.com",
        in_reply_to=None,
        references=(),
        reply_to_local_id=None,
        subject="Sub",
        sender=(FrozenMetadata({"name": "A", "address": "a@example.com"}),),
        recipients=FrozenMetadata({"to": (), "cc": (), "bcc": ()}),
        timestamp="2026-08-11T10:00:00+00:00",
        attachments=(FrozenMetadata({"local_id": "att-1"}),),
    )
    assert msg.attachment_ids == ("att-1",)


def test_chunk_validates_argument_types() -> None:
    doc = _document((_message(0),), (_text_block(0, 0, _words(5)),), container="eml")
    ctx = _context(doc)
    counter = WordCounter()
    with pytest.raises(TypeError, match="document must be ParsedDocument"):
        EmailChunker().chunk("invalid", ctx, counter)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="context must be ChunkingContext"):
        EmailChunker().chunk(doc, "invalid", counter)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="token_counter must satisfy TokenCounterInterfaceV1"):
        EmailChunker().chunk(doc, ctx, object())  # type: ignore[arg-type]


def test_chunk_validates_container_format_and_manifest() -> None:
    doc = _document((_message(0),), (_text_block(0, 0, _words(5)),), container="zip")
    with pytest.raises(UnsupportedError, match=r"invalid parser\.email\.container_format"):
        EmailChunker().chunk(doc, _context(doc), WordCounter())

    meta_dict = dict(doc.metadata.metadata)
    meta_dict["parser.email.container_format"] = "mbox"
    meta_dict["parser.email.messages"] = "not-a-tuple"
    invalid_doc = replace(
        doc,
        metadata=DocumentMetadata(
            content_hash="a" * 64,
            metadata=FrozenMetadata(meta_dict),
        ),
    )
    with pytest.raises(
        UnsupportedError, match=r"parser\.email\.messages must be an immutable sequence"
    ):
        EmailChunker().chunk(invalid_doc, _context(invalid_doc), WordCounter())

    empty_doc = _document((), (), container="mbox")
    with pytest.raises(UnsupportedError, match="Email messages manifest must not be empty"):
        EmailChunker().chunk(empty_doc, _context(empty_doc), WordCounter())

    eml_multi = _document(
        (_message(0), _message(1)),
        (_text_block(0, 0, _words(5)), _text_block(1, 1, _words(5))),
        container="eml",
    )
    with pytest.raises(UnsupportedError, match="an eml document must contain exactly one message"):
        EmailChunker().chunk(eml_multi, _context(eml_multi), WordCounter())


def test_chunk_validates_message_entry_fields() -> None:
    m0 = dict(_message(0))
    del m0["local_id"]
    doc = _document((FrozenMetadata(m0),), (_text_block(0, 0, _words(5)),), container="eml")
    with pytest.raises(UnsupportedError, match="Email message manifest entry is malformed"):
        EmailChunker().chunk(doc, _context(doc), WordCounter())

    doc_thread = _document(
        (_message(0, thread="not-a-sha256-hex"),),
        (_text_block(0, 0, _words(5)),),
        container="eml",
    )
    with pytest.raises(
        UnsupportedError, match="Email thread correlation must be lowercase SHA-256"
    ):
        EmailChunker().chunk(doc_thread, _context(doc_thread), WordCounter())

    m_rec = dict(_message(0))
    m_rec["recipients"] = FrozenMetadata({"to": ()})
    doc_rec = _document((FrozenMetadata(m_rec),), (_text_block(0, 0, _words(5)),), container="eml")
    with pytest.raises(UnsupportedError, match="Email recipients metadata is malformed"):
        EmailChunker().chunk(doc_rec, _context(doc_rec), WordCounter())

    m_time = dict(_message(0))
    m_time["timestamp"] = "not-rfc3339"
    doc_time = _document(
        (FrozenMetadata(m_time),), (_text_block(0, 0, _words(5)),), container="eml"
    )
    with pytest.raises(UnsupportedError, match="Email timestamp must be valid RFC3339"):
        EmailChunker().chunk(doc_time, _context(doc_time), WordCounter())

    m_naive = dict(_message(0))
    m_naive["timestamp"] = "2026-08-11T10:00:00"
    doc_naive = _document(
        (FrozenMetadata(m_naive),), (_text_block(0, 0, _words(5)),), container="eml"
    )
    with pytest.raises(UnsupportedError, match="Email timestamp must include an offset"):
        EmailChunker().chunk(doc_naive, _context(doc_naive), WordCounter())

    doc_dup_src = _document(
        (_message(0, source_index=0), _message(1, source_index=0)),
        (_text_block(0, 0, _words(5)), _text_block(1, 1, _words(5))),
        container="mbox",
    )
    with pytest.raises(UnsupportedError, match="Email source indexes must be unique"):
        EmailChunker().chunk(doc_dup_src, _context(doc_dup_src), WordCounter())


def test_chunk_validates_thread_ordering_and_reply_consistency() -> None:
    m0 = _message(0, thread="a" * 64, message_id="m0@example.com")
    m1 = _message(1, thread="b" * 64, reply_to="message-000000")
    doc_cross = _document(
        (m0, m1),
        (_text_block(0, 0, _words(5)), _text_block(1, 1, _words(5))),
        container="mbox",
    )
    with pytest.raises(
        UnsupportedError, match="Email reply relationship crosses thread components"
    ):
        EmailChunker().chunk(doc_cross, _context(doc_cross), WordCounter())

    m_t1 = _message(0, source_index=5, thread="a" * 64)
    m_t2 = _message(1, source_index=1, thread="b" * 64)
    doc_unsorted_threads = _document(
        (m_t1, m_t2),
        (_text_block(0, 0, _words(5)), _text_block(1, 1, _words(5))),
        container="mbox",
    )
    with pytest.raises(
        UnsupportedError, match="Email thread components are not in canonical order"
    ):
        EmailChunker().chunk(doc_unsorted_threads, _context(doc_unsorted_threads), WordCounter())


def test_chunk_validates_block_types_and_metadata() -> None:
    bad_meta_block = TextBlock(
        ordinal=0,
        text="hi",
        metadata=FrozenMetadata({"parser.email.message_local_id": "message-000000"}),
    )
    doc_bad_meta = _document((_message(0),), (bad_meta_block,), container="eml")
    with pytest.raises(UnsupportedError, match="Email block metadata does not match schema v1"):
        EmailChunker().chunk(doc_bad_meta, _context(doc_bad_meta), WordCounter())

    bad_region_block = _text_block(0, 0, "hi", region="unknown_region")
    doc_bad_region = _document((_message(0),), (bad_region_block,), container="eml")
    with pytest.raises(UnsupportedError, match="Email block region or body format is invalid"):
        EmailChunker().chunk(doc_bad_region, _context(doc_bad_region), WordCounter())

    text_with_att = TextBlock(
        ordinal=0,
        text="hi",
        metadata=_block_metadata("message-000000", attachment_id="att-1"),
    )
    doc_text_att = _document((_message(0),), (text_with_att,), container="eml")
    with pytest.raises(UnsupportedError, match="Email text block cannot reference an attachment"):
        EmailChunker().chunk(doc_text_att, _context(doc_text_att), WordCounter())

    tbl_block = TableBlock(
        ordinal=0,
        rows=(("c1", "c2"), ("v1", "v2")),
        metadata=_block_metadata("message-000000"),
    )
    doc_tbl = _document((_message(0),), (tbl_block,), container="eml")  # type: ignore[arg-type]
    with pytest.raises(
        UnsupportedError, match="Email schema v1 supports only text and inline-image blocks"
    ):
        EmailChunker().chunk(doc_tbl, _context(doc_tbl), WordCounter())


def test_chunk_multi_paragraph_and_sentence_reduction() -> None:
    p1 = _words(35, "alpha")
    p2 = _words(35, "beta")
    multi_p_text = f"{p1}\n\n{p2}"
    doc = _document((_message(0),), (_text_block(0, 0, multi_p_text),), container="eml")
    ctx = _context(doc, target=15, maximum=25)
    drafts = EmailChunker().chunk(doc, ctx, WordCounter())
    assert len(drafts) > 1

    long_sentence = _words(40, "gamma")
    doc_long = _document((_message(0),), (_text_block(0, 0, long_sentence),), container="eml")
    ctx_tight = _context(doc_long, target=15, maximum=20)
    drafts_split = EmailChunker().chunk(doc_long, ctx_tight, WordCounter())
    assert len(drafts_split) > 1


def test_email_chunker_metadata_helpers_validation() -> None:
    with pytest.raises(UnsupportedError, match="must be a non-empty string"):
        _required_string(FrozenMetadata({"key": ""}), "key")
    with pytest.raises(UnsupportedError, match="must be a non-empty string"):
        _required_string(FrozenMetadata({"key": 123}), "key")

    with pytest.raises(UnsupportedError, match="must be null or a non-empty string"):
        _optional_string(FrozenMetadata({"key": ""}), "key")
    with pytest.raises(UnsupportedError, match="must be null or a non-empty string"):
        _optional_string(FrozenMetadata({"key": 123}), "key")

    with pytest.raises(UnsupportedError, match="is not a canonical identifier"):
        _optional_identifier(FrozenMetadata({"key": "not an id with spaces"}), "key")

    with pytest.raises(UnsupportedError, match="must contain canonical identifiers"):
        _identifier_tuple(FrozenMetadata({"key": "not-a-tuple"}), "key")
    with pytest.raises(UnsupportedError, match="must contain canonical identifiers"):
        _identifier_tuple(FrozenMetadata({"key": ("bad id with spaces",)}), "key")

    with pytest.raises(UnsupportedError, match="must be a non-negative integer"):
        _non_negative_int(FrozenMetadata({"key": -1}), "key")
    with pytest.raises(UnsupportedError, match="must be a non-negative integer"):
        _non_negative_int(FrozenMetadata({"key": True}), "key")
    with pytest.raises(UnsupportedError, match="must be a non-negative integer"):
        _non_negative_int(FrozenMetadata({"key": "not-int"}), "key")

    with pytest.raises(UnsupportedError, match="must be an immutable address sequence"):
        _address_tuple(FrozenMetadata({"key": "not-a-tuple"}), "key")
    with pytest.raises(UnsupportedError, match="Email address metadata is malformed"):
        _address_tuple(FrozenMetadata({"key": (FrozenMetadata({}),)}), "key")

    with pytest.raises(UnsupportedError, match="must be an immutable sequence"):
        _attachment_tuple(FrozenMetadata({"key": "not-a-tuple"}), "key", "message-000000")
    with pytest.raises(UnsupportedError, match="Email attachment metadata is malformed"):
        _attachment_tuple(FrozenMetadata({"key": (FrozenMetadata({}),)}), "key", "message-000000")
    bad_mime = _attachment("message-000000-attachment-000000", mime_type="APPLICATION/PDF")
    with pytest.raises(UnsupportedError, match="Email attachment MIME type must be lowercase"):
        _attachment_tuple(
            FrozenMetadata({"key": (FrozenMetadata(bad_mime),)}), "key", "message-000000"
        )
    bad_disp = dict(_attachment("message-000000-attachment-000000"))
    bad_disp["disposition"] = "ATTACHMENT"
    with pytest.raises(UnsupportedError, match="Email attachment disposition must be lowercase"):
        _attachment_tuple(
            FrozenMetadata({"key": (FrozenMetadata(bad_disp),)}), "key", "message-000000"
        )
    bad_inline = dict(_attachment("message-000000-attachment-000000"))
    bad_inline["inline"] = "not-a-bool"
    with pytest.raises(UnsupportedError, match="Email attachment inline flag must be boolean"):
        _attachment_tuple(
            FrozenMetadata({"key": (FrozenMetadata(bad_inline),)}), "key", "message-000000"
        )

    img_no_att = ImageBlock(
        ordinal=0,
        asset_id=UUID(int=9),
        metadata=FrozenMetadata(
            {
                "parser.email.message_local_id": "message-000000",
                "parser.email.region": "body",
                "parser.email.body_format": "plain",
            }
        ),
    )
    doc_img = _document((_message(0),), (img_no_att,), container="eml")
    with pytest.raises(UnsupportedError, match="Email image block lacks attachment correlation"):
        EmailChunker().chunk(doc_img, _context(doc_img), WordCounter())
