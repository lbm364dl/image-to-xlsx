"""Tests for utility functions."""

import pytest
from utils import split_footnotes, get_cell_color, file_extension


# ---------------------------------------------------------------------------
# split_footnotes
# ---------------------------------------------------------------------------


class TestSplitFootnotes:
    def test_mixed_footnotes(self):
        text = "3) O 5) 545343 O o (4)"
        clean, notes = split_footnotes(text)
        assert clean == "545343"
        assert notes == ["3", "4", "5", "O"]

    def test_start_footnote(self):
        assert split_footnotes("(3) 545343") == ("545343", ["3"])

    def test_end_footnote(self):
        assert split_footnotes("545343 6)") == ("545343", ["6"])

    def test_circle_footnote(self):
        assert split_footnotes("Hongrie O 1)") == ("Hongrie", ["1", "O"])

    def test_lowercase_circle(self):
        assert split_footnotes("Hongrie o") == ("Hongrie", ["O"])

    def test_digit_zero_not_footnote(self):
        assert split_footnotes("Hongrie 0") == ("Hongrie 0", [])

    def test_number_with_space_not_footnote(self):
        for text in ["12 034", "10 434", "10 034"]:
            clean, notes = split_footnotes(text)
            assert clean == text
            assert notes == []

    def test_parenthesized_footnote_only(self):
        assert split_footnotes("(3)") == ("", ["3"])
        assert split_footnotes("b)") == ("", ["b"])

    def test_no_false_positive_on_normal_text(self):
        text = "China, other than electrical"
        assert split_footnotes(text) == (text, [])

    def test_embedded_o_not_footnote(self):
        assert split_footnotes("lasto") == ("lasto", [])


# ---------------------------------------------------------------------------
# get_cell_color
# ---------------------------------------------------------------------------


class TestGetCellColor:
    def test_none_confidence(self):
        assert get_cell_color(None) is None

    def test_high_confidence_green(self):
        assert get_cell_color(96) == "00C957"

    def test_low_confidence_red(self):
        color = get_cell_color(10)
        assert color is not None
        assert color != "00C957"  # not green

    def test_zero_confidence(self):
        assert get_cell_color(0) is not None

    def test_perfect_confidence(self):
        assert get_cell_color(100) == "00C957"

    def test_boundary_95(self):
        assert get_cell_color(95) == "00C957"
        assert get_cell_color(94.9) != "00C957"


# ---------------------------------------------------------------------------
# file_extension
# ---------------------------------------------------------------------------


class TestFileExtension:
    def test_pdf(self):
        assert file_extension("document.pdf") == "pdf"

    def test_png(self):
        assert file_extension("photo.png") == "png"

    def test_nested_path(self):
        assert file_extension("some/path/file.jpg") == "jpg"

    def test_multiple_dots(self):
        assert file_extension("archive.tar.gz") == "gz"
