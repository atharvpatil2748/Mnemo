"""Acceptance tests for the ADR-0016 Email ingestion boundary."""

from __future__ import annotations

import builtins
import hashlib
import socket
import uuid
from dataclasses import FrozenInstanceError
from email.message import EmailMessage
from importlib import metadata as importlib_metadata
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from email_ingestion import EmailIngestionPlugin, EmailParser, plugin
from mnemo.cleaner import DocumentCleaner
from mnemo.ingestion import DocumentCanonicalizer
from mnemo.interfaces.errors import ContractValidationError, UnsupportedError
from mnemo.interfaces.parser import ParserInterfaceV1
from mnemo.interfaces.parser_models import ParseResult, RawImageBlock, RawTextBlock
from mnemo.interfaces.storage import StorageInterfaceV1
from mnemo.interfaces.types import FileMetadata
from mnemo.models import DocType, FrozenMetadata, ParsedDocument
from mnemo.parsers import ParserRouter
from mnemo.registry import CapabilityKind, PluginRegistry


def _metadata(data: bytes, mime_type: str = "message/rfc822") -> FileMetadata:
    return FileMetadata(
        content_hash=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        mime_type=mime_type,
    )


def _eml(
    body: str = "Body text.",
    *,
    message_id: str | None = "root@example.com",
    in_reply_to: str | None = None,
    references: tuple[str, ...] = (),
    subject: str = "Example",
    sender: str = "Alice <alice@example.com>",
) -> bytes:
    headers = [
        f"From: {sender}",
        "To: Bob <bob@example.com>",
        "Cc: Carol <carol@example.com>",
        "Bcc: Dan <dan@example.com>",
        f"Subject: {subject}",
        "Date: Tue, 11 Aug 2026 10:00:00 +0530",
        "Content-Type: text/plain; charset=utf-8",
    ]
    if message_id is not None:
        headers.append(f"Message-ID: <{message_id}>")
    if in_reply_to is not None:
        headers.append(f"In-Reply-To: <{in_reply_to}>")
    if references:
        headers.append("References: " + " ".join(f"<{item}>" for item in references))
    return ("\r\n".join(headers) + "\r\n\r\n" + body + "\r\n").encode()


def _mbox(*messages: bytes) -> bytes:
    return b"".join(
        b"From sender@example.com Tue Aug 11 10:00:00 2026\n" + message + b"\n"
        for message in messages
    )


def _parse(
    data: bytes, filename: str = "mail.eml", mime_type: str = "message/rfc822"
) -> ParseResult:
    return EmailParser().parse(data, filename, _metadata(data, mime_type))


def _messages(result: ParseResult) -> tuple[FrozenMetadata, ...]:
    value = result.metadata.metadata["parser.email.messages"]
    assert isinstance(value, tuple)
    assert all(isinstance(item, FrozenMetadata) for item in value)
    return cast(tuple[FrozenMetadata, ...], value)


def _metadata_tuple(value: object) -> tuple[FrozenMetadata, ...]:
    assert isinstance(value, tuple)
    assert all(isinstance(item, FrozenMetadata) for item in value)
    return cast(tuple[FrozenMetadata, ...], value)


def test_parser_protocol_capabilities_and_exact_plugin_registration() -> None:
    parser = EmailParser()
    assert isinstance(parser, ParserInterfaceV1)
    assert parser.supported_formats == (".eml", "message/rfc822", ".mbox", "application/mbox")
    assert parser.capabilities().supports_images
    assert parser.capabilities().metadata["plugin.email-ingestion.thread_aware"] is True

    registry = PluginRegistry(core_version="0.20.0")
    registry.load_plugin(plugin)
    assert isinstance(plugin, EmailIngestionPlugin)
    assert all(registry.resolve_parser(slot) is not None for slot in parser.supported_formats)
    registrations = registry.list_registrations(CapabilityKind.PARSER)
    assert tuple(item.slot for item in registrations) == tuple(sorted(parser.supported_formats))
    assert registry.resolve_parser(".msg") is None
    assert registry.list_registrations(CapabilityKind.CHUNKER) == ()


def test_installed_entry_point_discovers_plugin() -> None:
    points = importlib_metadata.entry_points(group="mnemo.plugins")
    point = next(item for item in points if item.name == "email_ingestion")
    loaded = point.load()
    assert isinstance(loaded, EmailIngestionPlugin)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("filename", "mime_type"),
    [
        ("mail.eml", "application/octet-stream"),
        ("mail.bin", "message/rfc822"),
        ("mail.mbox", "application/octet-stream"),
        ("mail.bin", "application/mbox"),
    ],
)
async def test_router_resolves_approved_extension_and_mime_slots(
    filename: str, mime_type: str
) -> None:
    data = _eml()
    if filename.endswith(".mbox") or mime_type == "application/mbox":
        data = _mbox(data)
    registry = PluginRegistry(core_version="0.20.0")
    registry.load_plugin(plugin)
    storage = AsyncMock(spec=StorageInterfaceV1)
    storage.get_document_by_content_hash.return_value = None
    router = ParserRouter(registry, storage)
    with patch.object(router, "_detect_mime", return_value=mime_type):
        result = await router.route(data, filename)
    assert isinstance(result, ParseResult)
    assert result.doc_type is DocType.EMAIL


@pytest.mark.anyio
async def test_msg_is_not_registered_and_router_reports_unsupported() -> None:
    registry = PluginRegistry(core_version="0.20.0")
    registry.load_plugin(plugin)
    storage = AsyncMock(spec=StorageInterfaceV1)
    storage.get_document_by_content_hash.return_value = None
    router = ParserRouter(registry, storage)
    with (
        patch.object(router, "_detect_mime", return_value="application/vnd.ms-outlook"),
        pytest.raises(UnsupportedError),
    ):
        await router.route(b"not-msg", "mail.msg")
    with pytest.raises(UnsupportedError):
        _parse(b"not-msg", "mail.msg", "application/vnd.ms-outlook")


def test_eml_metadata_schema_headers_addresses_and_timestamp() -> None:
    data = _eml(subject="=?utf-8?q?Pr=C3=BCfung?=", message_id="Local@EXAMPLE.COM")
    result = _parse(data)
    assert result.doc_type is DocType.EMAIL
    assert result.metadata.metadata["parser.email.schema_version"] == 1
    assert result.metadata.metadata["parser.email.container_format"] == "eml"
    (record,) = _messages(result)
    assert record["local_id"] == "message-000000"
    assert record["source_index"] == 0
    assert record["message_id"] == "Local@example.com"
    assert record["subject"] == "Prüfung"
    assert record["timestamp"] == "2026-08-11T10:00:00+05:30"
    sender = record["sender"]
    assert isinstance(sender, tuple)
    assert sender[0] == FrozenMetadata({"name": "Alice", "address": "alice@example.com"})
    recipients = record["recipients"]
    assert isinstance(recipients, FrozenMetadata)
    assert tuple(item["address"] for item in _metadata_tuple(recipients["to"])) == (
        "bob@example.com",
    )
    assert tuple(item["address"] for item in _metadata_tuple(recipients["cc"])) == (
        "carol@example.com",
    )
    assert tuple(item["address"] for item in _metadata_tuple(recipients["bcc"])) == (
        "dan@example.com",
    )


def test_missing_and_invalid_optional_headers_are_null_or_empty() -> None:
    data = b"Content-Type: text/plain; charset=utf-8\r\nDate: invalid\r\n\r\nHello\r\n"
    result = _parse(data)
    (record,) = _messages(result)
    assert record["message_id"] is None
    assert record["in_reply_to"] is None
    assert record["references"] == ()
    assert record["subject"] is None
    assert record["sender"] == ()
    assert record["timestamp"] is None


def test_bare_folded_identifiers_comments_and_reference_chain_are_canonical() -> None:
    data = (
        b"Message-ID: bare@EXAMPLE.COM\r\n"
        b"In-Reply-To: (comment) <parent@EXAMPLE.COM>\r\n"
        b"References: <root@EXAMPLE.COM>\r\n\t<parent@EXAMPLE.COM>\r\n"
        b"Date: Tue, 11 Aug 2026 10:00:00\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n\r\nBody\r\n"
    )
    (record,) = _messages(_parse(data))
    assert record["message_id"] == "bare@example.com"
    assert record["in_reply_to"] == "parent@example.com"
    assert record["references"] == ("root@example.com", "parent@example.com")
    assert record["timestamp"] is None


def test_message_identifier_normalization_and_correlation_golden_vector() -> None:
    data = _eml(message_id="Root@Example.COM (comment)")
    result = _parse(data)
    (record,) = _messages(result)
    assert record["message_id"] == "Root@example.com"
    assert record["thread_correlation"] == (
        "d2f2071e59ef6b62c67e75e95619e3b0273170585e1e3723874950abdd0e4dfe"
    )


def test_raw_hash_correlation_golden_vector_without_identifiers() -> None:
    data = _eml(message_id=None)
    raw_hash = hashlib.sha256(data).hexdigest()
    expected = hashlib.sha256(f"mnemo-email-thread-v1\0raw-sha256:{raw_hash}".encode()).hexdigest()
    (record,) = _messages(_parse(data))
    assert record["thread_correlation"] == expected


def test_mbox_orders_parent_before_child_and_threads_by_first_occurrence() -> None:
    child = _eml("Child", message_id="child@example.com", in_reply_to="root@example.com")
    independent = _eml("Independent", message_id="other@example.com")
    parent = _eml("Parent", message_id="root@example.com")
    result = _parse(_mbox(child, independent, parent), "mail.mbox", "application/mbox")
    records = _messages(result)
    assert tuple(record["source_index"] for record in records) == (2, 0, 1)
    assert records[1]["reply_to_local_id"] == records[0]["local_id"]
    assert records[0]["thread_correlation"] == records[1]["thread_correlation"]
    assert records[2]["thread_correlation"] != records[0]["thread_correlation"]
    assert tuple(block.text for block in result.blocks if isinstance(block, RawTextBlock)) == (
        "Parent",
        "Child",
        "Independent",
    )


def test_dangling_ambiguous_self_and_cyclic_relationships_are_not_fabricated() -> None:
    dangling = _eml("D", message_id="d@example.com", in_reply_to="missing@example.com")
    duplicate_one = _eml("One", message_id="same@example.com")
    duplicate_two = _eml("Two", message_id="same@example.com")
    ambiguous = _eml("A", message_id="a@example.com", in_reply_to="same@example.com")
    self_ref = _eml("Self", message_id="self@example.com", in_reply_to="self@example.com")
    cycle_a = _eml("CA", message_id="ca@example.com", in_reply_to="cb@example.com")
    cycle_b = _eml("CB", message_id="cb@example.com", in_reply_to="ca@example.com")
    result = _parse(
        _mbox(dangling, duplicate_one, duplicate_two, ambiguous, self_ref, cycle_a, cycle_b),
        "mail.mbox",
        "application/mbox",
    )
    records = _messages(result)
    assert len(records) == 7
    by_source = {record["source_index"]: record for record in records}
    assert all(by_source[index]["reply_to_local_id"] is None for index in (0, 3, 4, 5, 6))
    assert [by_source[index]["message_id"] for index in (1, 2)] == [
        "same@example.com",
        "same@example.com",
    ]


def test_dangling_in_reply_to_falls_back_to_uniquely_resolved_last_reference() -> None:
    root = _eml(message_id="root@example.com")
    child = _eml(
        message_id="child@example.com",
        in_reply_to="missing@example.com",
        references=("root@example.com",),
    )
    records = _messages(_parse(_mbox(root, child), "mail.mbox", "application/mbox"))
    assert records[1]["reply_to_local_id"] == "message-000000"


def test_repeated_messages_are_preserved_and_parsing_is_deterministic() -> None:
    message = _eml("Repeated")
    data = _mbox(message, message)
    first = _parse(data, "mail.mbox", "application/mbox")
    second = _parse(data, "mail.mbox", "application/mbox")
    assert first == second
    assert len(_messages(first)) == 2
    assert tuple(record["source_index"] for record in _messages(first)) == (0, 1)


def test_plain_quote_signature_and_block_metadata() -> None:
    data = _eml("Current body.\r\n> Previous line.\r\n-- \r\nAlice")
    result = _parse(data)
    blocks = tuple(block for block in result.blocks if isinstance(block, RawTextBlock))
    assert tuple(block.metadata["parser.email.region"] for block in blocks) == (
        "body",
        "quoted",
        "signature",
    )
    assert all(
        block.metadata["parser.email.message_local_id"] == "message-000000" for block in blocks
    )
    assert all(block.metadata["parser.email.body_format"] == "plain" for block in blocks)
    assert "> Previous line." in blocks[1].text
    assert "Alice" in blocks[2].text


def test_standard_reply_delimiter_marks_remaining_plain_text_quoted() -> None:
    data = _eml("Reply.\r\n-----Original Message-----\r\nEarlier body.")
    blocks = tuple(block for block in _parse(data).blocks if isinstance(block, RawTextBlock))
    assert tuple(block.metadata["parser.email.region"] for block in blocks) == ("body", "quoted")
    assert "Earlier body." in blocks[1].text


def test_html_regions_are_structural_and_source_content_is_retained() -> None:
    data = (
        b"Message-ID: <html@example.com>\r\n"
        b"Content-Type: text/html; charset=utf-8\r\n\r\n"
        b"<p>Current &amp; exact</p><blockquote>Quoted</blockquote>"
        b"<div class='gmail_signature'>Signed</div>"
    )
    blocks = tuple(block for block in _parse(data).blocks if isinstance(block, RawTextBlock))
    assert tuple(block.metadata["parser.email.region"] for block in blocks) == (
        "body",
        "quoted",
        "signature",
    )
    assert tuple(block.metadata["parser.email.body_format"] for block in blocks) == (
        "html",
        "html",
        "html",
    )
    assert blocks[0].text == "Current & exact"


def test_multipart_alternative_prefers_plain_without_duplicate_html() -> None:
    data = (
        b"Message-ID: <alt@example.com>\r\n"
        b"Content-Type: multipart/alternative; boundary=alt\r\n\r\n"
        b"--alt\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<p>HTML</p>\r\n"
        b"--alt\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nPlain\r\n"
        b"--alt--\r\n"
    )
    result = _parse(data)
    texts = tuple(block.text for block in result.blocks if isinstance(block, RawTextBlock))
    assert texts == ("Plain",)


def test_multipart_alternative_falls_back_to_valid_html() -> None:
    data = (
        b"Message-ID: <alt@example.com>\r\n"
        b"Content-Type: multipart/alternative; boundary=alt\r\n\r\n"
        b"--alt\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n\xff\r\n"
        b"--alt\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<p>HTML fallback</p>\r\n"
        b"--alt--\r\n"
    )
    result = _parse(data)
    (block,) = tuple(block for block in result.blocks if isinstance(block, RawTextBlock))
    assert block.text == "HTML fallback"
    assert block.metadata["parser.email.body_format"] == "html"


def test_multipart_alternative_with_no_decodable_text_fails() -> None:
    data = (
        b"Content-Type: multipart/alternative; boundary=alt\r\n\r\n"
        b"--alt\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n\xff\r\n"
        b"--alt\r\nContent-Type: text/html; charset=utf-8\r\n\r\n\xfe\r\n"
        b"--alt--\r\n"
    )
    with pytest.raises(ContractValidationError, match="no decodable textual body"):
        _parse(data)


def test_multipart_mixed_records_ordinary_attachment() -> None:
    message = EmailMessage()
    message["Message-ID"] = "<mixed@example.com>"
    message.set_content("Body")
    message.add_attachment(b"payload", maintype="application", subtype="pdf", filename="file.pdf")
    result = _parse(message.as_bytes(policy=message.policy))
    (record,) = _messages(result)
    attachments = record["attachments"]
    attachments = _metadata_tuple(attachments)
    assert len(attachments) == 1
    attachment = attachments[0]
    assert attachment["filename"] == "file.pdf"
    assert attachment["mime_type"] == "application/pdf"
    assert attachment["inline"] is False
    assert result.extracted_assets == ()


def test_multipart_mixed_uses_one_body_and_records_remaining_text_part() -> None:
    data = (
        b"MIME-Version: 1.0\r\n"
        b"Content-Type: multipart/mixed; boundary=x\r\n\r\n"
        b"--x\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nBody\r\n"
        b"--x\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nAttached text\r\n"
        b"--x--\r\n"
    )
    result = _parse(data)
    assert tuple(block.text for block in result.blocks if isinstance(block, RawTextBlock)) == (
        "Body",
    )
    attachments = _metadata_tuple(_messages(result)[0]["attachments"])
    assert len(attachments) == 1
    assert attachments[0]["mime_type"] == "text/plain"


def test_multipart_related_correlates_inline_image_and_transient_asset() -> None:
    data = (
        b"Message-ID: <related@example.com>\r\n"
        b"Content-Type: multipart/related; boundary=rel\r\n\r\n"
        b"--rel\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<p>Body</p>\r\n"
        b"--rel\r\nContent-Type: image/png\r\nContent-ID: <img@example.com>\r\n"
        b"Content-Disposition: inline; filename=image.png\r\n"
        b"Content-Transfer-Encoding: base64\r\n\r\naW1hZ2U=\r\n--rel--\r\n"
    )
    result = _parse(data)
    assert len(result.extracted_assets) == 1
    image = next(block for block in result.blocks if isinstance(block, RawImageBlock))
    attachment_id = image.metadata["parser.email.attachment_local_id"]
    assert image.parser_local_id == attachment_id
    assert result.extracted_assets[0].parser_local_id == attachment_id
    (record,) = _messages(result)
    attachment = _metadata_tuple(record["attachments"])[0]
    assert attachment["content_id"] == "img@example.com"
    assert attachment["inline"] is True


def test_multipart_related_start_parameter_selects_declared_root() -> None:
    data = (
        b"Message-ID: <related@example.com>\r\n"
        b'Content-Type: multipart/related; boundary=rel; start="<body@example.com>"\r\n\r\n'
        b"--rel\r\nContent-Type: image/png\r\nContent-ID: <img@example.com>\r\n"
        b"Content-Transfer-Encoding: base64\r\n\r\naW1hZ2U=\r\n"
        b"--rel\r\nContent-Type: text/html; charset=utf-8\r\n"
        b"Content-ID: <body@example.com>\r\n\r\n<p>Selected body</p>\r\n--rel--\r\n"
    )
    result = _parse(data)
    assert any(
        isinstance(block, RawTextBlock) and block.text == "Selected body" for block in result.blocks
    )
    assert len(result.extracted_assets) == 1


def test_nested_message_rfc822_is_attachment_not_thread_member() -> None:
    nested = EmailMessage()
    nested["Message-ID"] = "<nested@example.com>"
    nested.set_content("Nested")
    outer = EmailMessage()
    outer["Message-ID"] = "<outer@example.com>"
    outer.set_content("Outer")
    outer.add_attachment(nested)
    result = _parse(outer.as_bytes(policy=outer.policy))
    assert len(_messages(result)) == 1
    (record,) = _messages(result)
    assert any(
        item["mime_type"] == "message/rfc822" for item in _metadata_tuple(record["attachments"])
    )
    assert all(
        not isinstance(block, RawTextBlock) or "Nested" not in block.text for block in result.blocks
    )


def test_declared_charset_transfer_encoding_and_unicode() -> None:
    data = (
        b"Message-ID: <charset@example.com>\r\n"
        b"Content-Type: text/plain; charset=iso-8859-1\r\n"
        b"Content-Transfer-Encoding: quoted-printable\r\n\r\nOl=E1\r\n"
    )
    (block,) = tuple(block for block in _parse(data).blocks if isinstance(block, RawTextBlock))
    assert block.text == "Olá"


def test_invalid_base64_and_empty_inline_image_fail_closed() -> None:
    invalid_base64 = (
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"Content-Transfer-Encoding: base64\r\n\r\n%%%\r\n"
    )
    with pytest.raises(ContractValidationError, match="transfer encoding"):
        _parse(invalid_base64)

    empty_image = (
        b"Content-Type: multipart/related; boundary=x\r\n\r\n"
        b"--x\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nBody\r\n"
        b"--x\r\nContent-Type: image/png\r\nContent-Disposition: inline\r\n\r\n"
        b"--x--\r\n"
    )
    with pytest.raises(ContractValidationError, match="inline image payload"):
        _parse(empty_image)


@pytest.mark.parametrize(
    "data",
    [
        b"Content-Type: text/plain; charset=unknown-x\r\n\r\ntext\r\n",
        b"Content-Type: text/plain; charset=utf-8\r\n\r\n\xff\r\n",
        (
            b"Content-Type: multipart/mixed; boundary=missing\r\n\r\n"
            b"body without a valid boundary\r\n"
        ),
    ],
)
def test_invalid_charset_or_malformed_mime_fails_complete_parse(data: bytes) -> None:
    with pytest.raises(ContractValidationError):
        _parse(data)


def test_empty_body_remains_manifest_only_without_fabricated_text() -> None:
    data = b"Message-ID: <empty@example.com>\r\nSubject: Empty\r\n\r\n"
    result = _parse(data)
    assert len(_messages(result)) == 1
    assert result.blocks == ()


def test_empty_invalid_and_escaped_mbox_inputs_are_deterministic() -> None:
    with pytest.raises(ContractValidationError, match="contains no messages"):
        _parse(b"", "mail.mbox", "application/mbox")
    with pytest.raises(ContractValidationError, match="must begin with a From separator"):
        _parse(b"not an mbox\n", "mail.mbox", "application/mbox")
    with pytest.raises(ContractValidationError, match="contains no valid messages"):
        _parse(b"From sender date\n\n", "mail.mbox", "application/mbox")

    message = _eml("Line\r\n>From escaped source line")
    result = _parse(_mbox(message), "mail.mbox", "application/mbox")
    assert any(
        isinstance(block, RawTextBlock) and "From escaped source line" in block.text
        for block in result.blocks
    )


def test_unknown_container_format_fails_without_guessing() -> None:
    data = _eml()
    with pytest.raises(ContractValidationError, match="unsupported Email container format"):
        _parse(data, "mail.bin", "application/octet-stream")


def test_metadata_is_immutable_and_serializable_by_frozen_contract() -> None:
    result = _parse(_eml())
    metadata = result.metadata.metadata
    assert hash(metadata)
    with pytest.raises(TypeError):
        metadata["parser.email.schema_version"] = 2  # type: ignore[index]
    record = _messages(result)[0]
    with pytest.raises(TypeError):
        record["subject"] = "Changed"  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        result.blocks[0].ordinal = 4  # type: ignore[misc]


def test_caller_cannot_inject_parser_email_namespace() -> None:
    data = _eml()
    metadata = FileMetadata(
        content_hash=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        mime_type="message/rfc822",
        metadata=FrozenMetadata({"parser.email.schema_version": 99}),
    )
    with pytest.raises(ContractValidationError):
        EmailParser().parse(data, "mail.eml", metadata)


def test_cleaner_and_canonicalizer_preserve_email_metadata_exactly() -> None:
    parsed = _parse(_eml("Body.\r\n> Quote.\r\n-- \r\nSignature"))
    cleaned = DocumentCleaner().clean(parsed)
    assert cleaned.metadata.metadata == parsed.metadata.metadata
    assert tuple(block.metadata for block in cleaned.blocks) == tuple(
        block.metadata for block in parsed.blocks
    )
    canonical = DocumentCanonicalizer().canonicalize(cleaned, {})
    assert isinstance(canonical, ParsedDocument)
    assert canonical.doc_type is DocType.EMAIL
    assert canonical.metadata.metadata == parsed.metadata.metadata
    assert tuple(block.metadata for block in canonical.blocks) == tuple(
        block.metadata for block in cleaned.blocks
    )


def test_inline_asset_survives_ingestion_boundary_with_external_resolution() -> None:
    data = (
        b"Message-ID: <image@example.com>\r\n"
        b"Content-Type: multipart/related; boundary=x\r\n\r\n"
        b"--x\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<p>Body</p>\r\n"
        b"--x\r\nContent-Type: image/png\r\nContent-Disposition: inline\r\n"
        b"Content-Transfer-Encoding: base64\r\n\r\naW1hZ2U=\r\n--x--\r\n"
    )
    parsed = _parse(data)
    assert len(parsed.extracted_assets) == 1
    assert isinstance(
        next(block for block in parsed.blocks if isinstance(block, RawImageBlock)), RawImageBlock
    )


def test_parser_has_no_network_filesystem_uuid_clock_or_storage_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("forbidden side effect")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(uuid, "uuid4", forbidden)
    with patch("time.time", forbidden):
        result = _parse(_eml("Pure parser"))
    assert result.blocks
