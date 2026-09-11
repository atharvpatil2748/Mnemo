"""Deterministic helpers for oversized semantic structures.

These helpers never relax the caller's token ceiling.  They descend through
structure (rows, columns, cells, paragraphs, sentences, and words) and fail
closed when an indivisible token cannot fit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mnemo.interfaces import TokenCounterInterfaceV1, UnsupportedError

_PARAGRAPH_BOUNDARY = re.compile(r"\n[ \t]*\n+")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_LINE_BOUNDARY = re.compile(r"\r?\n")
_WORD_UNIT = re.compile(r"\s*\S+")


@dataclass(frozen=True, slots=True)
class TableRowPart:
    """One ordered projection of a table row and its matching headers."""

    column_indexes: tuple[int, ...]
    headers: tuple[tuple[str, ...], ...]
    cells: tuple[str, ...]
    cell_part_index: int = 0
    cell_total_parts: int = 1


def split_exact_text(
    text: str,
    *,
    target: int,
    hard_max: int,
    counter: TokenCounterInterfaceV1,
    label: str,
) -> tuple[str, ...]:
    """Split text at the deepest necessary safe boundary without losing bytes."""
    if counter.count(text) <= hard_max:
        return (text,)
    if target <= 0 or hard_max <= 0 or target > hard_max:
        raise ValueError("subdivision token budgets are invalid")
    parts = _split_recursive(text, target, hard_max, counter, 0, label)
    if "".join(parts) != text:
        raise AssertionError("exact-text subdivision did not conserve source text")
    if any(counter.count(part) > hard_max for part in parts):
        raise AssertionError("exact-text subdivision exceeded its hard maximum")
    return parts


def split_table_row(
    headers: tuple[tuple[str, ...], ...],
    row: tuple[str, ...],
    *,
    target: int,
    hard_max: int,
    counter: TokenCounterInterfaceV1,
) -> tuple[TableRowPart, ...]:
    """Project an oversized row by columns, then split only oversized cells."""
    width = len(row)
    if any(len(header) != width for header in headers):
        raise UnsupportedError("table header width does not match the oversized row")

    result: list[TableRowPart] = []
    current: list[int] = []
    for column in range(width):
        candidate = (*current, column)
        if current and counter.count(_render_projection(headers, row, candidate)) > target:
            result.append(_part(headers, row, tuple(current)))
            current = []
            candidate = (column,)
        if counter.count(_render_projection(headers, row, candidate)) > hard_max:
            if current:
                result.append(_part(headers, row, tuple(current)))
                current = []
            result.extend(
                _split_table_cell(
                    headers,
                    row,
                    column,
                    target=target,
                    hard_max=hard_max,
                    counter=counter,
                )
            )
        else:
            current.append(column)
    if current:
        result.append(_part(headers, row, tuple(current)))

    reconstructed = ["" for _ in row]
    for part in result:
        for column, cell in zip(part.column_indexes, part.cells, strict=True):
            reconstructed[column] += cell
    if tuple(reconstructed) != row:
        raise AssertionError("table-row subdivision did not conserve cell content")
    if any(counter.count(render_table_part(part)) > hard_max for part in result):
        raise AssertionError("table-row subdivision exceeded its hard maximum")
    return tuple(result)


def render_table_part(part: TableRowPart) -> str:
    """Render the structural payload of a row projection as deterministic TSV."""
    rows = (*part.headers, part.cells)
    return "\n".join("\t".join(row) for row in rows).strip()


def _split_recursive(
    text: str,
    target: int,
    hard_max: int,
    counter: TokenCounterInterfaceV1,
    level: int,
    label: str,
) -> tuple[str, ...]:
    if counter.count(text) <= hard_max:
        return (text,)
    boundaries = (_PARAGRAPH_BOUNDARY, _SENTENCE_BOUNDARY, _LINE_BOUNDARY)
    if level < len(boundaries):
        units = _segments_ending_at_boundaries(text, boundaries[level])
        if len(units) > 1:
            reduced: list[str] = []
            for unit in units:
                reduced.extend(_split_recursive(unit, target, hard_max, counter, level + 1, label))
            return _pack_exact(tuple(reduced), target, hard_max, counter)
        return _split_recursive(text, target, hard_max, counter, level + 1, label)

    words = tuple(match.group(0) for match in _WORD_UNIT.finditer(text))
    trailing = text[sum(len(word) for word in words) :]
    if trailing:
        words = (*words, trailing)
    if not words or "".join(words) != text:
        raise UnsupportedError(f"{label} has no deterministic textual boundary")
    if any(counter.count(word) > hard_max for word in words):
        raise UnsupportedError(f"{label} contains an indivisible token over the maximum")
    return _pack_exact(words, target, hard_max, counter)


def _segments_ending_at_boundaries(text: str, pattern: re.Pattern[str]) -> tuple[str, ...]:
    result: list[str] = []
    start = 0
    for match in pattern.finditer(text):
        result.append(text[start : match.end()])
        start = match.end()
    if start < len(text):
        result.append(text[start:])
    return tuple(part for part in result if part)


def _pack_exact(
    units: tuple[str, ...],
    target: int,
    hard_max: int,
    counter: TokenCounterInterfaceV1,
) -> tuple[str, ...]:
    result: list[str] = []
    current = ""
    for unit in units:
        candidate = current + unit
        if current and counter.count(candidate) > target:
            result.append(current)
            current = unit
        else:
            current = candidate
        if counter.count(current) > hard_max:
            raise UnsupportedError("semantic subdivision unit exceeds the token maximum")
    if current:
        result.append(current)
    return tuple(result)


def _render_projection(
    headers: tuple[tuple[str, ...], ...], row: tuple[str, ...], columns: tuple[int, ...]
) -> str:
    projected = tuple(tuple(header[index] for index in columns) for header in headers)
    values = tuple(row[index] for index in columns)
    return "\n".join("\t".join(value) for value in (*projected, values)).strip()


def _part(
    headers: tuple[tuple[str, ...], ...], row: tuple[str, ...], columns: tuple[int, ...]
) -> TableRowPart:
    return TableRowPart(
        column_indexes=columns,
        headers=tuple(tuple(header[index] for index in columns) for header in headers),
        cells=tuple(row[index] for index in columns),
    )


def _split_table_cell(
    headers: tuple[tuple[str, ...], ...],
    row: tuple[str, ...],
    column: int,
    *,
    target: int,
    hard_max: int,
    counter: TokenCounterInterfaceV1,
) -> tuple[TableRowPart, ...]:
    projected_headers = tuple((header[column],) for header in headers)
    header_text = "\n".join(header[column] for header in headers).strip()
    header_tokens = counter.count(header_text)
    separator_tokens = counter.count("\n") if header_text else 0
    available_hard = hard_max - header_tokens - separator_tokens
    available_target = min(target, available_hard)
    if available_hard <= 0:
        raise UnsupportedError("table header context alone exceeds the token maximum")
    pieces = split_exact_text(
        row[column],
        target=max(1, available_target),
        hard_max=available_hard,
        counter=counter,
        label="table cell",
    )
    total = len(pieces)
    return tuple(
        TableRowPart(
            column_indexes=(column,),
            headers=projected_headers,
            cells=(piece,),
            cell_part_index=index,
            cell_total_parts=total,
        )
        for index, piece in enumerate(pieces)
    )
