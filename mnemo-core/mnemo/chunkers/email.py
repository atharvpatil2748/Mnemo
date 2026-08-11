"""Deterministic thread-aware chunking for canonical Email documents."""

import re
from dataclasses import dataclass, replace
from datetime import datetime

from mnemo.interfaces import (
    ChunkerCapabilities,
    ChunkingContext,
    TokenCounterInterfaceV1,
    UnsupportedError,
)
from mnemo.models import (
    Block,
    BlockSpan,
    ChunkDraft,
    ChunkPosition,
    ChunkType,
    DocType,
    FrozenMetadata,
    ImageBlock,
    ParsedDocument,
    TextBlock,
)

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?\u3002\uff01\uff1f])\s+")
_PARAGRAPH_BOUNDARY = re.compile(r"\n[ \t]*\n+")
_WORD_WITH_SPACE = re.compile(r"\S+(?:\s+|$)")
_LOCAL_ID = re.compile(r"^message-(\d{6})$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MESSAGE_ID = re.compile(r"^[^\s<>@]+@[^\s<>@]+$")
_DOCUMENT_KEYS = frozenset(
    {
        "parser.email.schema_version",
        "parser.email.container_format",
        "parser.email.messages",
    }
)
_MESSAGE_KEYS = frozenset(
    {
        "local_id",
        "source_index",
        "thread_correlation",
        "message_id",
        "in_reply_to",
        "references",
        "reply_to_local_id",
        "subject",
        "sender",
        "recipients",
        "timestamp",
        "attachments",
    }
)
_ADDRESS_KEYS = frozenset({"name", "address"})
_RECIPIENT_KEYS = frozenset({"to", "cc", "bcc"})
_ATTACHMENT_KEYS = frozenset(
    {"local_id", "filename", "mime_type", "content_id", "disposition", "inline"}
)
_BLOCK_KEYS = frozenset(
    {
        "parser.email.message_local_id",
        "parser.email.region",
        "parser.email.body_format",
        "parser.email.attachment_local_id",
    }
)
_REGIONS = frozenset({"body", "quoted", "signature"})
_BODY_FORMATS = frozenset({"plain", "html", "markdown"})


@dataclass(frozen=True, slots=True)
class _Message:
    local_id: str
    source_index: int
    thread_correlation: str
    message_id: str | None
    in_reply_to: str | None
    references: tuple[str, ...]
    reply_to_local_id: str | None
    subject: str | None
    sender: tuple[FrozenMetadata, ...]
    recipients: FrozenMetadata
    timestamp: str | None
    attachments: tuple[FrozenMetadata, ...]

    @property
    def attachment_ids(self) -> tuple[str, ...]:
        """Return the message-scoped attachment identifiers."""
        return tuple(_required_string(item, "local_id") for item in self.attachments)


@dataclass(frozen=True, slots=True)
class _Unit:
    text: str
    chunk_type: ChunkType
    source_span: BlockSpan
    message: _Message
    region: str
    body_format: str
    page_number: int | None
    attachment_local_ids: tuple[str, ...] = ()
    separator: str = "\n\n"
    mergeable: bool = True


class EmailChunker:
    """Chunk canonical ADR-0016 Email content without reparsing source bytes."""

    @property
    def supported_doc_types(self) -> tuple[DocType, ...]:
        """Return the sole classification owned by this strategy."""
        return (DocType.EMAIL,)

    def capabilities(self) -> ChunkerCapabilities:
        """Describe the implemented thread-aware behavior."""
        return ChunkerCapabilities(
            supported_doc_types=self.supported_doc_types,
            preserves_semantic_boundaries=True,
            supports_parent_child=True,
            supports_overlap=False,
            metadata=FrozenMetadata({"chunker.email.version": "v1"}),
        )

    def chunk(
        self,
        document: ParsedDocument,
        context: ChunkingContext,
        token_counter: TokenCounterInterfaceV1,
    ) -> tuple[ChunkDraft, ...]:
        """Return ordered message drafts for dispatcher finalization."""
        if not isinstance(document, ParsedDocument):
            raise TypeError("document must be ParsedDocument")
        if not isinstance(context, ChunkingContext):
            raise TypeError("context must be ChunkingContext")
        if not isinstance(token_counter, TokenCounterInterfaceV1):
            raise TypeError("token_counter must satisfy TokenCounterInterfaceV1")
        if document.doc_type is not DocType.EMAIL:
            raise UnsupportedError("EmailChunker supports only DocType.EMAIL")

        container_format, messages = self._validate_document(document)
        message_by_id = {message.local_id: message for message in messages}
        units = self._units(
            document,
            message_by_id,
            context.options.target_tokens,
            context.effective_max_tokens,
            token_counter,
        )
        packed = self._pack(
            units,
            context.options.target_tokens,
            context.effective_max_tokens,
            token_counter,
        )
        return self._drafts(packed, messages, container_format)

    def _validate_document(self, document: ParsedDocument) -> tuple[str, tuple[_Message, ...]]:
        metadata = document.metadata.metadata
        email_keys = {key for key in metadata if key.startswith("parser.email.")}
        if email_keys != _DOCUMENT_KEYS:
            raise UnsupportedError("Email document metadata does not match schema v1")
        if metadata["parser.email.schema_version"] != 1:
            raise UnsupportedError("unsupported parser.email.schema_version")
        container_format = metadata["parser.email.container_format"]
        if container_format not in {"eml", "mbox"}:
            raise UnsupportedError("invalid parser.email.container_format")
        manifest = metadata["parser.email.messages"]
        if not isinstance(manifest, tuple):
            raise UnsupportedError("parser.email.messages must be an immutable sequence")
        messages = tuple(self._message(item, index) for index, item in enumerate(manifest))
        if not messages:
            raise UnsupportedError("Email messages manifest must not be empty")
        if container_format == "eml" and len(messages) != 1:
            raise UnsupportedError("an eml document must contain exactly one message")
        self._validate_message_graph(messages)
        self._validate_blocks(document.blocks, messages)
        return container_format, messages

    def _message(self, value: object, index: int) -> _Message:
        if not isinstance(value, FrozenMetadata) or set(value) != _MESSAGE_KEYS:
            raise UnsupportedError("Email message manifest entry is malformed")
        local_id = _required_string(value, "local_id")
        match = _LOCAL_ID.fullmatch(local_id)
        if match is None or int(match.group(1)) != index:
            raise UnsupportedError("Email message local IDs must match canonical order")
        source_index = _non_negative_int(value, "source_index")
        thread = _required_string(value, "thread_correlation")
        if _SHA256.fullmatch(thread) is None:
            raise UnsupportedError("Email thread correlation must be lowercase SHA-256")
        message_id = _optional_identifier(value, "message_id")
        in_reply_to = _optional_identifier(value, "in_reply_to")
        references = _identifier_tuple(value, "references")
        reply_to = _optional_string(value, "reply_to_local_id")
        subject = _optional_string(value, "subject")
        sender = _address_tuple(value, "sender")
        recipients_value = value["recipients"]
        if (
            not isinstance(recipients_value, FrozenMetadata)
            or set(recipients_value) != _RECIPIENT_KEYS
        ):
            raise UnsupportedError("Email recipients metadata is malformed")
        for field in ("to", "cc", "bcc"):
            _address_tuple(recipients_value, field)
        timestamp = _optional_string(value, "timestamp")
        if timestamp is not None:
            try:
                parsed_timestamp = datetime.fromisoformat(timestamp)
            except ValueError as error:
                raise UnsupportedError("Email timestamp must be valid RFC3339") from error
            if parsed_timestamp.tzinfo is None:
                raise UnsupportedError("Email timestamp must include an offset")
        attachments = _attachment_tuple(value, "attachments", local_id)
        return _Message(
            local_id=local_id,
            source_index=source_index,
            thread_correlation=thread,
            message_id=message_id,
            in_reply_to=in_reply_to,
            references=references,
            reply_to_local_id=reply_to,
            subject=subject,
            sender=sender,
            recipients=recipients_value,
            timestamp=timestamp,
            attachments=attachments,
        )

    @staticmethod
    def _validate_message_graph(messages: tuple[_Message, ...]) -> None:
        if len({message.local_id for message in messages}) != len(messages):
            raise UnsupportedError("Email message local IDs must be unique")
        if len({message.source_index for message in messages}) != len(messages):
            raise UnsupportedError("Email source indexes must be unique")
        by_id = {message.local_id: message for message in messages}
        positions = {message.local_id: index for index, message in enumerate(messages)}
        identifier_occurrences: dict[str, list[str]] = {}
        for message in messages:
            if message.message_id is not None:
                identifier_occurrences.setdefault(message.message_id, []).append(message.local_id)
        seen_threads: set[str] = set()
        previous_thread: str | None = None
        thread_minima: list[int] = []
        for message in messages:
            if message.thread_correlation != previous_thread:
                if message.thread_correlation in seen_threads:
                    raise UnsupportedError("Email thread components must be contiguous")
                seen_threads.add(message.thread_correlation)
                thread_minima.append(message.source_index)
                previous_thread = message.thread_correlation
            else:
                thread_minima[-1] = min(thread_minima[-1], message.source_index)
            parent_id = message.reply_to_local_id
            expected_parent = _resolved_parent_local_id(message, identifier_occurrences)
            if parent_id != expected_parent:
                raise UnsupportedError("Email resolved reply relationship is inconsistent")
            if parent_id is None:
                continue
            parent = by_id.get(parent_id)
            if parent is None:
                raise UnsupportedError("Email reply relationship is dangling")
            if parent.thread_correlation != message.thread_correlation:
                raise UnsupportedError("Email reply relationship crosses thread components")
            if positions[parent_id] >= positions[message.local_id]:
                raise UnsupportedError("Email reply parent must precede its child")
        if thread_minima != sorted(thread_minima):
            raise UnsupportedError("Email thread components are not in canonical order")

    @staticmethod
    def _validate_blocks(blocks: tuple[Block, ...], messages: tuple[_Message, ...]) -> None:
        by_id = {message.local_id: message for message in messages}
        positions = {message.local_id: index for index, message in enumerate(messages)}
        previous_position = -1
        for block in blocks:
            email_keys = {key for key in block.metadata if key.startswith("parser.email.")}
            if not {
                "parser.email.message_local_id",
                "parser.email.region",
                "parser.email.body_format",
            }.issubset(email_keys) or not email_keys.issubset(_BLOCK_KEYS):
                raise UnsupportedError("Email block metadata does not match schema v1")
            local_id = block.metadata["parser.email.message_local_id"]
            if not isinstance(local_id, str) or local_id not in by_id:
                raise UnsupportedError("Email block references an unknown message")
            position = positions[local_id]
            if position < previous_position:
                raise UnsupportedError("Email blocks are not in canonical message order")
            previous_position = position
            region = block.metadata["parser.email.region"]
            body_format = block.metadata["parser.email.body_format"]
            if region not in _REGIONS or body_format not in _BODY_FORMATS:
                raise UnsupportedError("Email block region or body format is invalid")
            attachment_id = block.metadata.get("parser.email.attachment_local_id")
            if isinstance(block, ImageBlock):
                if not isinstance(attachment_id, str):
                    raise UnsupportedError("Email image block lacks attachment correlation")
                matching = tuple(
                    attachment
                    for attachment in by_id[local_id].attachments
                    if attachment["local_id"] == attachment_id
                )
                if len(matching) != 1 or matching[0]["inline"] is not True:
                    raise UnsupportedError("Email image attachment correlation is invalid")
            elif isinstance(block, TextBlock):
                if attachment_id is not None:
                    raise UnsupportedError("Email text block cannot reference an attachment")
            else:
                raise UnsupportedError("Email schema v1 supports only text and inline-image blocks")

    def _units(
        self,
        document: ParsedDocument,
        messages: dict[str, _Message],
        target: int,
        hard_max: int,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[_Unit, ...]:
        result: list[_Unit] = []
        for block in document.blocks:
            local_id = block.metadata["parser.email.message_local_id"]
            assert isinstance(local_id, str)
            message = messages[local_id]
            region = block.metadata["parser.email.region"]
            body_format = block.metadata["parser.email.body_format"]
            assert isinstance(region, str)
            assert isinstance(body_format, str)
            span = BlockSpan(start_ordinal=block.ordinal, end_ordinal=block.ordinal)
            if isinstance(block, ImageBlock):
                if block.alt_text is None:
                    continue
                if counter.count(block.alt_text) > hard_max:
                    raise UnsupportedError("atomic Email inline image exceeds token maximum")
                attachment_id = block.metadata["parser.email.attachment_local_id"]
                assert isinstance(attachment_id, str)
                result.append(
                    _Unit(
                        text=block.alt_text,
                        chunk_type=ChunkType.CAPTION,
                        source_span=span,
                        message=message,
                        region=region,
                        body_format=body_format,
                        page_number=block.page_number,
                        attachment_local_ids=(attachment_id,),
                        mergeable=False,
                    )
                )
                continue
            assert isinstance(block, TextBlock)
            parts = self._reduce_text(block.text, target, hard_max, counter)
            for part_index, part in enumerate(parts):
                result.append(
                    _Unit(
                        text=part,
                        chunk_type=ChunkType.PASSAGE,
                        source_span=span,
                        message=message,
                        region=region,
                        body_format=body_format,
                        page_number=block.page_number,
                        separator="\n\n" if part_index == 0 else " ",
                    )
                )
        return tuple(result)

    def _reduce_text(
        self,
        text: str,
        target: int,
        hard_max: int,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[str, ...]:
        if counter.count(text) <= target:
            return (text,)
        paragraphs = tuple(part.strip() for part in _PARAGRAPH_BOUNDARY.split(text) if part.strip())
        if len(paragraphs) > 1:
            result: list[str] = []
            for paragraph in paragraphs:
                result.extend(self._reduce_sentence(paragraph, target, hard_max, counter))
            return tuple(result)
        return self._reduce_sentence(text, target, hard_max, counter)

    def _reduce_sentence(
        self,
        text: str,
        target: int,
        hard_max: int,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[str, ...]:
        sentences = tuple(part.strip() for part in _SENTENCE_BOUNDARY.split(text) if part.strip())
        if len(sentences) > 1:
            result: list[str] = []
            for sentence in sentences:
                if counter.count(sentence) <= hard_max:
                    result.append(sentence)
                else:
                    result.extend(self._word_split(sentence, target, hard_max, counter))
            return tuple(result)
        if counter.count(text) <= hard_max:
            return (text,)
        return self._word_split(text, target, hard_max, counter)

    @staticmethod
    def _word_split(
        text: str,
        target: int,
        hard_max: int,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[str, ...]:
        words = tuple(match.group(0) for match in _WORD_WITH_SPACE.finditer(text))
        if not words:
            raise UnsupportedError("Email prose has no safe word boundary")
        result: list[str] = []
        current = ""
        for word_with_space in words:
            word = word_with_space.rstrip()
            if counter.count(word) > hard_max:
                raise UnsupportedError("Email word exceeds the effective token maximum")
            candidate = (current + word_with_space).rstrip()
            if current and counter.count(candidate) > target:
                result.append(current.rstrip())
                current = word_with_space
            else:
                current += word_with_space
        if current.strip():
            result.append(current.rstrip())
        return tuple(result)

    @staticmethod
    def _pack(
        units: tuple[_Unit, ...],
        target: int,
        hard_max: int,
        counter: TokenCounterInterfaceV1,
    ) -> tuple[_Unit, ...]:
        if not units:
            return ()
        result: list[_Unit] = []
        current = units[0]
        for unit in units[1:]:
            candidate = current.text + unit.separator + unit.text
            count = counter.count(candidate)
            if EmailChunker._can_merge(current, unit) and (
                count <= target or (counter.count(current.text) < 15 and count <= hard_max)
            ):
                current = replace(
                    current,
                    text=candidate,
                    source_span=BlockSpan(
                        start_ordinal=current.source_span.start_ordinal,
                        end_ordinal=unit.source_span.end_ordinal,
                    ),
                )
            else:
                result.append(current)
                current = unit
        if (
            result
            and counter.count(current.text) < 15
            and EmailChunker._can_merge(result[-1], current)
        ):
            candidate = result[-1].text + current.separator + current.text
            if counter.count(candidate) <= hard_max:
                previous = result.pop()
                current = replace(
                    previous,
                    text=candidate,
                    source_span=BlockSpan(
                        start_ordinal=previous.source_span.start_ordinal,
                        end_ordinal=current.source_span.end_ordinal,
                    ),
                )
        result.append(current)
        return tuple(result)

    @staticmethod
    def _can_merge(left: _Unit, right: _Unit) -> bool:
        return (
            left.mergeable
            and right.mergeable
            and left.message.local_id == right.message.local_id
            and left.region == right.region
            and left.body_format == right.body_format
            and right.source_span.start_ordinal <= left.source_span.end_ordinal + 1
        )

    @staticmethod
    def _drafts(
        units: tuple[_Unit, ...],
        messages: tuple[_Message, ...],
        container_format: str,
    ) -> tuple[ChunkDraft, ...]:
        position_by_message = {message.local_id: index for index, message in enumerate(messages)}
        chunk_counts: dict[str, int] = {}
        drafts: list[ChunkDraft] = []
        draft_messages: list[str] = []
        for unit in units:
            local_id = unit.message.local_id
            chunk_index = chunk_counts.get(local_id, 0)
            chunk_counts[local_id] = chunk_index + 1
            drafts.append(
                ChunkDraft(
                    text=unit.text,
                    chunk_type=unit.chunk_type,
                    position=ChunkPosition(
                        section_index=position_by_message[local_id],
                        chunk_index_in_section=chunk_index,
                        page_number=unit.page_number,
                    ),
                    heading_path=(),
                    source_span=unit.source_span,
                    parent_index=None,
                    metadata=_draft_metadata(unit, container_format),
                )
            )
            draft_messages.append(local_id)

        indexes_by_message: dict[str, list[int]] = {}
        for index, local_id in enumerate(draft_messages):
            indexes_by_message.setdefault(local_id, []).append(index)
        representatives: dict[str, int] = {}
        for local_id, indexes in indexes_by_message.items():
            representatives[local_id] = next(
                (
                    index
                    for index in indexes
                    if drafts[index].chunk_type is ChunkType.PASSAGE
                    and drafts[index].metadata["chunker.email.region"] == "body"
                ),
                indexes[0],
            )
        message_by_id = {message.local_id: message for message in messages}
        for index, local_id in enumerate(draft_messages):
            parent_local_id = message_by_id[local_id].reply_to_local_id
            parent_index = representatives.get(parent_local_id) if parent_local_id else None
            if parent_index is not None:
                if parent_index >= index:
                    raise UnsupportedError("Email reply draft parent must precede its child")
                drafts[index] = replace(drafts[index], parent_index=parent_index)
        return tuple(drafts)


def _draft_metadata(unit: _Unit, container_format: str) -> FrozenMetadata:
    message = unit.message
    values: dict[str, object] = {
        "chunker.email.strategy": "thread-aware-v1",
        "chunker.email.schema_version": 1,
        "chunker.email.container_format": container_format,
        "chunker.email.thread_correlation": message.thread_correlation,
        "chunker.email.message_local_id": message.local_id,
        "chunker.email.source_index": message.source_index,
        "chunker.email.message_id": message.message_id,
        "chunker.email.in_reply_to": message.in_reply_to,
        "chunker.email.references": message.references,
        "chunker.email.reply_to_local_id": message.reply_to_local_id,
        "chunker.email.subject": message.subject,
        "chunker.email.sender": message.sender,
        "chunker.email.recipients": message.recipients,
        "chunker.email.timestamp": message.timestamp,
        "chunker.email.attachments": message.attachments,
        "chunker.email.region": unit.region,
        "chunker.email.body_format": unit.body_format,
    }
    if unit.attachment_local_ids:
        values["chunker.email.attachment_local_ids"] = unit.attachment_local_ids
    return FrozenMetadata(values)


def _required_string(value: FrozenMetadata, field: str) -> str:
    result = value[field]
    if not isinstance(result, str) or not result:
        raise UnsupportedError(f"Email {field} must be a non-empty string")
    return result


def _optional_string(value: FrozenMetadata, field: str) -> str | None:
    result = value[field]
    if result is not None and (not isinstance(result, str) or not result):
        raise UnsupportedError(f"Email {field} must be null or a non-empty string")
    return result


def _optional_identifier(value: FrozenMetadata, field: str) -> str | None:
    result = _optional_string(value, field)
    if result is not None and _MESSAGE_ID.fullmatch(result) is None:
        raise UnsupportedError(f"Email {field} is not a canonical identifier")
    return result


def _identifier_tuple(value: FrozenMetadata, field: str) -> tuple[str, ...]:
    result = value[field]
    if not isinstance(result, tuple):
        raise UnsupportedError(f"Email {field} must contain canonical identifiers")
    identifiers: list[str] = []
    for item in result:
        if not isinstance(item, str) or _MESSAGE_ID.fullmatch(item) is None:
            raise UnsupportedError(f"Email {field} must contain canonical identifiers")
        identifiers.append(item)
    return tuple(identifiers)


def _non_negative_int(value: FrozenMetadata, field: str) -> int:
    result = value[field]
    if isinstance(result, bool) or not isinstance(result, int) or result < 0:
        raise UnsupportedError(f"Email {field} must be a non-negative integer")
    return result


def _address_tuple(value: FrozenMetadata, field: str) -> tuple[FrozenMetadata, ...]:
    result = value[field]
    if not isinstance(result, tuple):
        raise UnsupportedError(f"Email {field} must be an immutable address sequence")
    addresses: list[FrozenMetadata] = []
    for address in result:
        if not isinstance(address, FrozenMetadata) or set(address) != _ADDRESS_KEYS:
            raise UnsupportedError("Email address metadata is malformed")
        _optional_string(address, "name")
        _required_string(address, "address")
        addresses.append(address)
    return tuple(addresses)


def _attachment_tuple(
    value: FrozenMetadata, field: str, message_local_id: str
) -> tuple[FrozenMetadata, ...]:
    result = value[field]
    if not isinstance(result, tuple):
        raise UnsupportedError("Email attachments must be an immutable sequence")
    attachments: list[FrozenMetadata] = []
    identifiers: set[str] = set()
    prefix = f"{message_local_id}-attachment-"
    for attachment in result:
        if not isinstance(attachment, FrozenMetadata) or set(attachment) != _ATTACHMENT_KEYS:
            raise UnsupportedError("Email attachment metadata is malformed")
        local_id = _required_string(attachment, "local_id")
        suffix = local_id.removeprefix(prefix)
        if (
            not local_id.startswith(prefix)
            or len(suffix) != 6
            or not suffix.isdecimal()
            or local_id in identifiers
        ):
            raise UnsupportedError("Email attachment local ID is invalid or duplicated")
        identifiers.add(local_id)
        _optional_string(attachment, "filename")
        mime_type = _required_string(attachment, "mime_type")
        if mime_type != mime_type.lower() or "/" not in mime_type:
            raise UnsupportedError("Email attachment MIME type must be lowercase")
        _optional_identifier(attachment, "content_id")
        disposition = _optional_string(attachment, "disposition")
        if disposition is not None and disposition != disposition.lower():
            raise UnsupportedError("Email attachment disposition must be lowercase")
        if not isinstance(attachment["inline"], bool):
            raise UnsupportedError("Email attachment inline flag must be boolean")
        attachments.append(attachment)
    return tuple(attachments)


def _resolved_parent_local_id(
    message: _Message, identifier_occurrences: dict[str, list[str]]
) -> str | None:
    for candidate in (message.in_reply_to, *reversed(message.references)):
        if candidate is None:
            continue
        matches = identifier_occurrences.get(candidate, [])
        if len(matches) == 1 and matches[0] != message.local_id:
            return matches[0]
        if matches:
            return None
    return None
