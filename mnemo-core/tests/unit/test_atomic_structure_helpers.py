"""Exact-conservation tests for structure-aware oversized text subdivision."""

from __future__ import annotations

import pytest
from mnemo.chunkers.atomic_structures import (
    render_table_part,
    split_exact_text,
    split_table_row,
)
from mnemo.interfaces import UnsupportedError


class CharacterCounter:
    def count(self, text: str) -> int:
        return len(text)


def test_exact_text_descends_through_paragraph_sentence_line_and_word_boundaries() -> None:
    counter = CharacterCounter()
    samples = (
        "alpha beta\n\ngamma delta\n\nepsilon zeta",
        "Alpha beta. Gamma delta? Epsilon zeta!",
        "alpha beta\ngamma delta\nepsilon zeta",
        "alpha beta gamma delta epsilon zeta",
        "alpha beta ",
    )
    for text in samples:
        parts = split_exact_text(text, target=12, hard_max=15, counter=counter, label="text")
        assert "".join(parts) == text
        assert all(len(part) <= 15 for part in parts)
    assert split_exact_text("small", target=2, hard_max=8, counter=counter, label="text") == (
        "small",
    )
    for target, hard_max in ((0, 4), (3, 0), (5, 4)):
        with pytest.raises(ValueError, match="budgets"):
            split_exact_text(
                "oversized", target=target, hard_max=hard_max, counter=counter, label="x"
            )
    with pytest.raises(UnsupportedError, match="indivisible token"):
        split_exact_text("unbreakable", target=3, hard_max=4, counter=counter, label="word")


def test_table_rows_split_by_columns_then_cells_without_losing_content() -> None:
    counter = CharacterCounter()
    headers = (("A", "B", "C"),)
    row = ("one", "two", "three")
    parts = split_table_row(headers, row, target=7, hard_max=12, counter=counter)
    rebuilt = ["", "", ""]
    for part in parts:
        assert render_table_part(part)
        for index, cell in zip(part.column_indexes, part.cells, strict=True):
            rebuilt[index] += cell
    assert tuple(rebuilt) == row

    oversized = ("short", "many small words that must split exactly", "tail")
    divided = split_table_row(headers, oversized, target=12, hard_max=16, counter=counter)
    cell_parts = [part for part in divided if part.column_indexes == (1,)]
    assert len(cell_parts) > 1
    assert [part.cell_part_index for part in cell_parts] == list(range(len(cell_parts)))
    assert all(part.cell_total_parts == len(cell_parts) for part in cell_parts)
    assert "".join(part.cells[0] for part in cell_parts) == oversized[1]


def test_table_row_rejects_width_header_and_indivisible_cell_failures() -> None:
    counter = CharacterCounter()
    with pytest.raises(UnsupportedError, match="header width"):
        split_table_row((("only",),), ("a", "b"), target=10, hard_max=20, counter=counter)
    with pytest.raises(UnsupportedError, match="header context"):
        split_table_row(
            (("header-is-too-long",),),
            ("cell",),
            target=4,
            hard_max=5,
            counter=counter,
        )
    with pytest.raises(UnsupportedError, match="indivisible token"):
        split_table_row(
            (("H",),),
            ("unbreakable",),
            target=4,
            hard_max=7,
            counter=counter,
        )
