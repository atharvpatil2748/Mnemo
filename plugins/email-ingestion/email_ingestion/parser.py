"""Pure Email/MIME parser implementing ADR-0016."""

from __future__ import annotations

import codecs
import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser
from typing import Final, cast

from mnemo.interfaces.errors import ContractValidationError, UnsupportedError
from mnemo.interfaces.parser import ParserInterfaceV1
from mnemo.interfaces.parser_models import (
    ParseResult,
    RawBlock,
    RawImageBlock,
    RawTextBlock,
    TransientAsset,
)
from mnemo.interfaces.types import FileMetadata, ParserCapabilities
from mnemo.models import DocType, DocumentMetadata, FrozenMetadata

_SCHEMA_VERSION: Final = 1
_THREAD_PREFIX: Final = "mnemo-email-thread-v1\0"
_MESSAGE_ID_PATTERN: Final = re.compile(r"<([^<>]+)>")
_BARE_MESSAGE_ID_PATTERN: Final = re.compile(r"[^\s<>@]+@[^\s<>@]+")
_REPLY_DELIMITER_PATTERN: Final = re.compile(
    r"^(?:-{2,}\s*(?:original message|forwarded message)\s*-{2,}|on .+ wrote:)\s*$",
    re.IGNORECASE,
)
_HTML_BLOCK_TAGS: Final = frozenset(
    {
        "address",
        "article",
        "aside",
        "br",
        "div",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "p",
        "pre",
        "section",
        "tr",
    }
)
_HTML_VOID_TAGS: Final = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
_SIGNATURE_MARKERS: Final = frozenset(
    {"signature", "gmail_signature", "moz-signature", "email-signature"}
)
_QUOTE_MARKERS: Final = frozenset({"gmail_quote", "moz-cite-prefix"})


@dataclass(frozen=True, slots=True)
class _Address:
    name: str | None
    address: str

    def as_json(self) -> dict[str, object]:
        return {"name": self.name, "address": self.address}


@dataclass(frozen=True, slots=True)
class _BodySegment:
    text: str
    region: str
    body_format: str


@dataclass(frozen=True, slots=True)
class _Attachment:
    part_index: int
    filename: str | None
    mime_type: str
    content_id: str | None
    disposition: str | None
    inline: bool
    raw_bytes: bytes | None = None


@dataclass(frozen=True, slots=True)
class _SourceMessage:
    source_index: int
    raw_bytes: bytes
    message_id: str | None
    in_reply_to: str | None
    references: tuple[str, ...]
    subject: str | None
    sender: tuple[_Address, ...]
    recipients_to: tuple[_Address, ...]
    recipients_cc: tuple[_Address, ...]
    recipients_bcc: tuple[_Address, ...]
    timestamp: str | None
    segments: tuple[_BodySegment, ...]
    attachments: tuple[_Attachment, ...]


@dataclass(frozen=True, slots=True)
class _ResolvedMessage:
    source: _SourceMessage
    thread_correlation: str
    parent_source_index: int | None


class _SemanticHTMLExtractor(HTMLParser):
    """Extract ordered text regions from explicit HTML structure."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._quote_depth = 0
        self._signature_depth = 0
        self._stack: list[tuple[str, bool, bool]] = []
        self.events: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        values = {
            token.lower()
            for key, value in attrs
            if key.lower() in {"class", "id"} and value
            for token in value.split()
        }
        is_quote = lowered == "blockquote" or bool(values & _QUOTE_MARKERS)
        is_signature = bool(values & _SIGNATURE_MARKERS)
        if lowered not in _HTML_VOID_TAGS:
            self._stack.append((lowered, is_quote, is_signature))
        if is_quote:
            self._quote_depth += 1
        if is_signature:
            self._signature_depth += 1
        if lowered in _HTML_BLOCK_TAGS:
            self._append_text("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _HTML_VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in _HTML_BLOCK_TAGS:
            self._append_text("\n")
        for index in range(len(self._stack) - 1, -1, -1):
            stack_tag, was_quote, was_signature = self._stack[index]
            if stack_tag != lowered:
                continue
            del self._stack[index:]
            if was_quote:
                self._quote_depth -= 1
            if was_signature:
                self._signature_depth -= 1
            break

    def handle_data(self, data: str) -> None:
        self._append_text(data)

    def _append_text(self, text: str) -> None:
        region = "signature" if self._signature_depth else "quoted" if self._quote_depth else "body"
        self.events.append((region, text))


class EmailParser(ParserInterfaceV1):
    """Parse `.eml` and `mbox` bytes into immutable Email semantic metadata."""

    @property
    def supported_formats(self) -> tuple[str, ...]:
        return (".eml", "message/rfc822", ".mbox", "application/mbox")

    def capabilities(self) -> ParserCapabilities:
        return ParserCapabilities(
            supported_formats=self.supported_formats,
            supports_tables=False,
            supports_images=True,
            supports_math=False,
            supports_ocr=False,
            metadata=FrozenMetadata({"plugin.email-ingestion.thread_aware": True}),
        )

    def parse(self, data: bytes, filename: str, metadata: FileMetadata) -> ParseResult:
        """Parse one source Email container without external side effects."""
        container_format = _container_format(filename, metadata.mime_type)
        raw_messages = (data,) if container_format == "eml" else _split_mbox(data)
        if not raw_messages:
            raise ContractValidationError("Email container contains no messages")

        sources = tuple(
            _parse_source_message(raw, source_index)
            for source_index, raw in enumerate(raw_messages)
        )
        resolved = _resolve_and_order(sources)
        blocks, assets, message_records = _materialize(resolved)

        inherited: dict[str, object] = dict(metadata.metadata)
        if any(key.startswith("parser.email.") for key in inherited):
            raise ContractValidationError("caller metadata cannot define parser.email.* keys")
        inherited.update(
            {
                "parser.email.schema_version": _SCHEMA_VERSION,
                "parser.email.container_format": container_format,
                "parser.email.messages": message_records,
            }
        )
        title = next((item.source.subject for item in resolved if item.source.subject), None)
        return ParseResult(
            blocks=blocks,
            extracted_assets=assets,
            metadata=DocumentMetadata(
                content_hash=metadata.content_hash,
                title=title or filename or "Untitled Email",
                metadata=FrozenMetadata(inherited),
            ),
            language="en",
            doc_type=DocType.EMAIL,
        )


def _container_format(filename: str, mime_type: str | None) -> str:
    lowered_name = filename.lower()
    lowered_mime = mime_type.lower() if mime_type else None
    if lowered_name.endswith(".msg"):
        raise UnsupportedError("Outlook .msg is not supported by email-ingestion V1")
    if lowered_mime == "application/mbox" or lowered_name.endswith(".mbox"):
        return "mbox"
    if lowered_mime == "message/rfc822" or lowered_name.endswith(".eml"):
        return "eml"
    raise ContractValidationError("unsupported Email container format")


def _split_mbox(data: bytes) -> tuple[bytes, ...]:
    if not data:
        return ()
    lines = data.splitlines(keepends=True)
    messages: list[bytes] = []
    current: list[bytes] | None = None
    for line in lines:
        if line.startswith(b"From "):
            if current is not None:
                raw = b"".join(current)
                if raw.strip():
                    messages.append(raw)
            current = []
            continue
        if current is None:
            if line.strip():
                raise ContractValidationError("mbox data must begin with a From separator")
            continue
        current.append(line[1:] if line.startswith(b">From ") else line)
    if current is not None:
        raw = b"".join(current)
        if raw.strip():
            messages.append(raw)
    if not messages:
        raise ContractValidationError("mbox container contains no valid messages")
    return tuple(messages)


def _parse_source_message(raw: bytes, source_index: int) -> _SourceMessage:
    try:
        message = BytesParser(policy=policy.default).parsebytes(raw)
    except Exception as error:
        raise ContractValidationError("Email MIME parsing failed") from error
    _reject_defects(message)
    segments, attachments = _extract_message_content(message)
    return _SourceMessage(
        source_index=source_index,
        raw_bytes=raw,
        message_id=_single_message_id(message.get("Message-ID")),
        in_reply_to=_single_message_id(message.get("In-Reply-To")),
        references=_message_ids(message.get("References")),
        subject=_optional_header(message, "Subject"),
        sender=_addresses(message, "From"),
        recipients_to=_addresses(message, "To"),
        recipients_cc=_addresses(message, "Cc"),
        recipients_bcc=_addresses(message, "Bcc"),
        timestamp=_timestamp(message),
        segments=segments,
        attachments=attachments,
    )


def _reject_defects(message: Message) -> None:
    for part in message.walk():
        if part.defects:
            names = ", ".join(type(defect).__name__ for defect in part.defects)
            raise ContractValidationError(f"malformed Email MIME structure: {names}")


def _optional_header(message: Message, name: str) -> str | None:
    value = message.get(name)
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text if text and "\ufffd" not in text else None


def _addresses(message: Message, name: str) -> tuple[_Address, ...]:
    values = message.get_all(name, [])
    parsed = getaddresses([str(value) for value in values])
    return tuple(
        _Address(name=display.strip() or None, address=address.strip())
        for display, address in parsed
        if address.strip() and "\ufffd" not in display and "\ufffd" not in address
    )


def _timestamp(message: Message) -> str | None:
    value = message.get("Date")
    if value is None:
        return None
    try:
        parsed = parsedate_to_datetime(str(value))
    except (TypeError, ValueError, OverflowError):
        return None
    if not isinstance(parsed, datetime) or parsed.tzinfo is None:
        return None
    return parsed.isoformat(timespec="seconds")


def _remove_comments(value: str) -> str:
    result: list[str] = []
    depth = 0
    escaped = False
    for character in value:
        if escaped:
            if depth == 0:
                result.append(character)
            escaped = False
            continue
        if character == "\\":
            escaped = True
            if depth == 0:
                result.append(character)
            continue
        if character == "(":
            depth += 1
            continue
        if character == ")" and depth:
            depth -= 1
            continue
        if depth == 0:
            result.append(character)
    return "".join(result)


def _canonical_message_id(value: str) -> str | None:
    compact = re.sub(r"[ \t\r\n]+", "", _remove_comments(value)).strip("<>")
    if _BARE_MESSAGE_ID_PATTERN.fullmatch(compact) is None:
        return None
    left, right = compact.rsplit("@", 1)
    return f"{left}@{right.lower()}"


def _message_ids(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    text = _remove_comments(str(value))
    bracketed = _MESSAGE_ID_PATTERN.findall(text)
    candidates = bracketed if bracketed else text.split()
    normalized = tuple(
        identifier
        for candidate in candidates
        if (identifier := _canonical_message_id(candidate)) is not None
    )
    return normalized


def _single_message_id(value: object) -> str | None:
    identifiers = _message_ids(value)
    return identifiers[0] if len(identifiers) == 1 else None


def _extract_message_content(
    message: Message,
) -> tuple[tuple[_BodySegment, ...], tuple[_Attachment, ...]]:
    indices = {id(part): index for index, part in enumerate(message.walk())}
    attachments: list[_Attachment] = []
    segments = _extract_entity(message, indices, attachments, related_inline=False)
    return (
        tuple(segment for segment in segments if segment.text.strip()),
        tuple(sorted(attachments, key=lambda attachment: attachment.part_index)),
    )


def _extract_entity(
    part: Message,
    indices: dict[int, int],
    attachments: list[_Attachment],
    *,
    related_inline: bool,
) -> list[_BodySegment]:
    content_type = part.get_content_type().lower()
    if content_type == "message/rfc822":
        _append_attachment(part, indices, attachments, inline=False)
        return []

    if part.is_multipart():
        children = _multipart_children(part)
        subtype = part.get_content_subtype().lower()
        if subtype == "alternative":
            selected = _select_alternative(children)
            return _extract_entity(selected, indices, attachments, related_inline=False)
        if subtype == "related":
            root = _related_root(part, children)
            related_segments = _extract_entity(root, indices, attachments, related_inline=False)
            for child in children:
                if child is root:
                    continue
                _append_attachment(child, indices, attachments, inline=True)
            return related_segments
        if subtype == "mixed":
            body_candidate: Message | None = None
            for child in children:
                if _can_be_body(child):
                    body_candidate = child
                    break
            if body_candidate is None:
                for child in children:
                    _append_attachment(child, indices, attachments, inline=False)
                return []
            mixed_segments = _extract_entity(
                body_candidate, indices, attachments, related_inline=False
            )
            for child in children:
                if child is not body_candidate:
                    _append_attachment(child, indices, attachments, inline=False)
            return mixed_segments
        collected: list[_BodySegment] = []
        for child in children:
            if _is_attachment(child):
                _append_attachment(child, indices, attachments, inline=related_inline)
            else:
                collected.extend(
                    _extract_entity(child, indices, attachments, related_inline=related_inline)
                )
        return collected

    if _is_attachment(part) or not content_type.startswith("text/"):
        _append_attachment(part, indices, attachments, inline=related_inline)
        return []

    text = _decode_text(part)
    if not text:
        return []
    if content_type == "text/html":
        return list(_split_html_regions(text))
    body_format = "markdown" if content_type == "text/markdown" else "plain"
    return list(_split_plain_regions(text, body_format))


def _can_be_body(part: Message) -> bool:
    if _is_attachment(part):
        return False
    if not part.is_multipart():
        return part.get_content_type().lower() in {
            "text/plain",
            "text/html",
            "text/markdown",
        }
    return part.get_content_subtype().lower() in {"alternative", "related"}


def _select_alternative(children: tuple[Message, ...]) -> Message:
    for preferred in ("text/plain", "text/html"):
        for child in children:
            if child.get_content_type().lower() != preferred or _is_attachment(child):
                continue
            try:
                _decode_text(child)
            except ContractValidationError:
                continue
            return child
    raise ContractValidationError("multipart/alternative has no decodable textual body")


def _multipart_children(part: Message) -> tuple[Message, ...]:
    payload = part.get_payload()
    if not isinstance(payload, list) or any(not isinstance(item, Message) for item in payload):
        raise ContractValidationError("multipart Email payload is structurally invalid")
    return tuple(cast(Message, item) for item in payload)


def _related_root(part: Message, children: tuple[Message, ...]) -> Message:
    if not children:
        raise ContractValidationError("multipart/related contains no parts")
    start = part.get_param("start")
    normalized_start = _canonical_message_id(str(start)) if start else None
    if normalized_start is not None:
        for child in children:
            if _single_message_id(child.get("Content-ID")) == normalized_start:
                return child
    return children[0]


def _is_attachment(part: Message) -> bool:
    disposition = part.get_content_disposition()
    return disposition == "attachment" or part.get_filename() is not None


def _append_attachment(
    part: Message,
    indices: dict[int, int],
    attachments: list[_Attachment],
    *,
    inline: bool,
) -> None:
    index = indices.get(id(part))
    if index is None:
        raise ContractValidationError("MIME part has no deterministic preorder index")
    disposition = part.get_content_disposition()
    content_id = _single_message_id(part.get("Content-ID"))
    source_inline = inline or disposition == "inline"
    raw: bytes | None = None
    if source_inline and part.get_content_maintype().lower() == "image":
        payload = part.get_payload(decode=True)
        _raise_new_defects(part)
        if not isinstance(payload, bytes) or not payload:
            raise ContractValidationError("inline image payload cannot be decoded")
        raw = payload
    attachments.append(
        _Attachment(
            part_index=index,
            filename=part.get_filename(),
            mime_type=part.get_content_type().lower(),
            content_id=content_id,
            disposition=disposition.lower() if disposition else None,
            inline=source_inline,
            raw_bytes=raw,
        )
    )


def _decode_text(part: Message) -> str:
    payload = part.get_payload(decode=True)
    _raise_new_defects(part)
    if not isinstance(payload, bytes):
        raise ContractValidationError("textual MIME payload cannot be transfer-decoded")
    charset = part.get_content_charset() or "utf-8"
    try:
        codecs.lookup(charset)
        return payload.decode(charset, errors="strict")
    except (LookupError, UnicodeDecodeError) as error:
        raise ContractValidationError(f"textual MIME payload is not valid {charset}") from error


def _raise_new_defects(part: Message) -> None:
    if part.defects:
        names = ", ".join(type(defect).__name__ for defect in part.defects)
        raise ContractValidationError(f"malformed Email transfer encoding: {names}")


def _split_plain_regions(text: str, body_format: str) -> tuple[_BodySegment, ...]:
    lines = text.splitlines(keepends=True)
    if not lines and text:
        lines = [text]
    events: list[tuple[str, str]] = []
    quoted_mode = False
    signature_mode = False
    for line in lines:
        stripped = line.rstrip("\r\n")
        if stripped == "-- ":
            signature_mode = True
        elif _REPLY_DELIMITER_PATTERN.fullmatch(stripped.strip()):
            quoted_mode = True
        if signature_mode:
            region = "signature"
        elif quoted_mode or line.lstrip().startswith(">"):
            region = "quoted"
        else:
            region = "body"
        events.append((region, line))
    return _group_region_events(events, body_format)


def _split_html_regions(text: str) -> tuple[_BodySegment, ...]:
    extractor = _SemanticHTMLExtractor()
    try:
        extractor.feed(text)
        extractor.close()
    except Exception as error:
        raise ContractValidationError("HTML Email body cannot be parsed") from error
    return _group_region_events(extractor.events, "html")


def _group_region_events(
    events: list[tuple[str, str]], body_format: str
) -> tuple[_BodySegment, ...]:
    grouped: list[_BodySegment] = []
    current_region: str | None = None
    buffer: list[str] = []
    for region, text in events:
        if current_region is not None and region != current_region:
            content = "".join(buffer).strip()
            if content:
                grouped.append(
                    _BodySegment(text=content, region=current_region, body_format=body_format)
                )
            buffer.clear()
        current_region = region
        buffer.append(text)
    if current_region is not None:
        content = "".join(buffer).strip()
        if content:
            grouped.append(
                _BodySegment(text=content, region=current_region, body_format=body_format)
            )
    return tuple(grouped)


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, value: str) -> None:
        self.parent.setdefault(value, value)

    def find(self, value: str) -> str:
        root = self.parent[value]
        while root != self.parent[root]:
            root = self.parent[root]
        current = value
        while current != root:
            following = self.parent[current]
            self.parent[current] = root
            current = following
        return root

    def union(self, left: str, right: str) -> None:
        self.add(left)
        self.add(right)
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def _resolve_and_order(sources: tuple[_SourceMessage, ...]) -> tuple[_ResolvedMessage, ...]:
    union = _UnionFind()
    directed_edges: list[tuple[str, str]] = []
    message_nodes: list[tuple[str, ...]] = []
    for source in sources:
        identifiers = source.references + ((source.in_reply_to,) if source.in_reply_to else ())
        if source.message_id:
            identifiers += (source.message_id,)
        message_nodes.append(identifiers)
        for identifier in identifiers:
            union.add(identifier)
        for edge_parent, edge_child in zip(source.references, source.references[1:], strict=False):
            union.union(edge_parent, edge_child)
            directed_edges.append((edge_parent, edge_child))
        if source.message_id:
            candidate_parent = source.in_reply_to or (
                source.references[-1] if source.references else None
            )
            if candidate_parent:
                union.union(candidate_parent, source.message_id)
                directed_edges.append((candidate_parent, source.message_id))

    identifier_occurrences: dict[str, list[int]] = defaultdict(list)
    for source in sources:
        if source.message_id:
            identifier_occurrences[source.message_id].append(source.source_index)

    raw_parents: dict[int, int | None] = {}
    for source in sources:
        raw_parents[source.source_index] = _resolved_parent(source, identifier_occurrences)
    cyclic = _cyclic_sources(raw_parents)
    parents = {index: None if index in cyclic else parent for index, parent in raw_parents.items()}

    indegree: dict[str, int] = defaultdict(int)
    for parent, child in directed_edges:
        if parent != child:
            indegree[child] += 1
            indegree.setdefault(parent, 0)

    visit_order: list[str] = []
    for source in sources:
        for identifier in source.references:
            if identifier not in visit_order:
                visit_order.append(identifier)
        if source.in_reply_to and source.in_reply_to not in visit_order:
            visit_order.append(source.in_reply_to)
        if source.message_id and source.message_id not in visit_order:
            visit_order.append(source.message_id)

    component_identifiers: dict[str, set[str]] = defaultdict(set)
    for identifier in union.parent:
        component_identifiers[union.find(identifier)].add(identifier)
    component_seed: dict[str, str] = {}
    for component, component_ids in component_identifiers.items():
        roots = {identifier for identifier in component_ids if indegree[identifier] == 0}
        if roots:
            seed = next(identifier for identifier in visit_order if identifier in roots)
        else:
            seed = min(component_ids)
        component_seed[component] = seed

    correlations: dict[int, str] = {}
    for source, identifiers in zip(sources, message_nodes, strict=True):
        if identifiers:
            seed = component_seed[union.find(identifiers[0])]
        else:
            raw_hash = hashlib.sha256(source.raw_bytes).hexdigest()
            seed = f"raw-sha256:{raw_hash}"
        correlations[source.source_index] = hashlib.sha256(
            f"{_THREAD_PREFIX}{seed}".encode()
        ).hexdigest()

    by_thread: dict[str, list[int]] = defaultdict(list)
    for source in sources:
        by_thread[correlations[source.source_index]].append(source.source_index)
    thread_order = sorted(by_thread, key=lambda key: min(by_thread[key]))
    ordered_indices: list[int] = []
    for thread in thread_order:
        ordered_indices.extend(_topological_order(by_thread[thread], parents))
    source_by_index = {source.source_index: source for source in sources}
    return tuple(
        _ResolvedMessage(
            source=source_by_index[index],
            thread_correlation=correlations[index],
            parent_source_index=parents[index],
        )
        for index in ordered_indices
    )


def _resolved_parent(
    source: _SourceMessage, identifier_occurrences: dict[str, list[int]]
) -> int | None:
    candidates = (source.in_reply_to, *reversed(source.references))
    for candidate in candidates:
        if candidate is None:
            continue
        matches = identifier_occurrences.get(candidate, [])
        if len(matches) == 1 and matches[0] != source.source_index:
            return matches[0]
        if matches:
            return None
    return None


def _cyclic_sources(parents: dict[int, int | None]) -> set[int]:
    cyclic: set[int] = set()
    for start in parents:
        path: list[int] = []
        positions: dict[int, int] = {}
        current: int | None = start
        while current is not None and current not in positions:
            positions[current] = len(path)
            path.append(current)
            current = parents.get(current)
        if current is not None and current in positions:
            cyclic.update(path[positions[current] :])
    return cyclic


def _topological_order(indices: list[int], parents: dict[int, int | None]) -> list[int]:
    allowed = set(indices)
    children: dict[int, list[int]] = defaultdict(list)
    indegree = {index: 0 for index in indices}
    for child in indices:
        parent = parents[child]
        if parent is not None and parent in allowed:
            children[parent].append(child)
            indegree[child] += 1
    ready = sorted(index for index, count in indegree.items() if count == 0)
    result: list[int] = []
    while ready:
        current = ready.pop(0)
        result.append(current)
        for child in sorted(children[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort()
    if len(result) != len(indices):
        raise ContractValidationError("Email message ordering contains a cycle")
    return result


def _materialize(
    resolved: tuple[_ResolvedMessage, ...],
) -> tuple[tuple[RawBlock, ...], tuple[TransientAsset, ...], tuple[dict[str, object], ...]]:
    local_ids = {
        item.source.source_index: f"message-{index:06d}" for index, item in enumerate(resolved)
    }
    blocks: list[RawBlock] = []
    assets: list[TransientAsset] = []
    records: list[dict[str, object]] = []
    for item in resolved:
        source = item.source
        local_id = local_ids[source.source_index]
        attachment_records: list[dict[str, object]] = []
        for attachment in source.attachments:
            attachment_id = f"{local_id}-attachment-{attachment.part_index:06d}"
            attachment_records.append(
                {
                    "local_id": attachment_id,
                    "filename": attachment.filename,
                    "mime_type": attachment.mime_type,
                    "content_id": attachment.content_id,
                    "disposition": attachment.disposition,
                    "inline": attachment.inline,
                }
            )
            if attachment.raw_bytes is not None:
                metadata = FrozenMetadata(
                    {
                        "parser.email.message_local_id": local_id,
                        "parser.email.region": "body",
                        "parser.email.body_format": "html",
                        "parser.email.attachment_local_id": attachment_id,
                    }
                )
                assets.append(
                    TransientAsset(
                        parser_local_id=attachment_id,
                        raw_bytes=attachment.raw_bytes,
                        mime_type=attachment.mime_type,
                    )
                )
                blocks.append(
                    RawImageBlock(
                        ordinal=len(blocks),
                        parser_local_id=attachment_id,
                        alt_text=attachment.filename,
                        metadata=metadata,
                    )
                )
        for segment in source.segments:
            blocks.append(
                RawTextBlock(
                    ordinal=len(blocks),
                    text=segment.text,
                    metadata=FrozenMetadata(
                        {
                            "parser.email.message_local_id": local_id,
                            "parser.email.region": segment.region,
                            "parser.email.body_format": segment.body_format,
                        }
                    ),
                )
            )
        records.append(
            {
                "local_id": local_id,
                "source_index": source.source_index,
                "thread_correlation": item.thread_correlation,
                "message_id": source.message_id,
                "in_reply_to": source.in_reply_to,
                "references": source.references,
                "reply_to_local_id": (
                    local_ids[item.parent_source_index]
                    if item.parent_source_index is not None
                    else None
                ),
                "subject": source.subject,
                "sender": tuple(address.as_json() for address in source.sender),
                "recipients": {
                    "to": tuple(address.as_json() for address in source.recipients_to),
                    "cc": tuple(address.as_json() for address in source.recipients_cc),
                    "bcc": tuple(address.as_json() for address in source.recipients_bcc),
                },
                "timestamp": source.timestamp,
                "attachments": tuple(attachment_records),
            }
        )
    return tuple(blocks), tuple(assets), tuple(records)
