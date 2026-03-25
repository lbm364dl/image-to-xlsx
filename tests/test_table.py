"""Tests for the Table class — the core data processing layer."""

import pytest
from collections import defaultdict
from table import Table
from definitions import NOT_NUMBER, ONE_NUMBER, AT_LEAST_TWO_NUMBERS


def _make_table(stub_page, bbox=None):
    """Helper: create a Table attached to the stub_page fixture."""
    return Table(None, stub_page, bbox or [0, 0, 100, 100])


# ---------------------------------------------------------------------------
# set_table_from_service_response
# ---------------------------------------------------------------------------


class TestSetTableFromServiceResponse:
    def test_basic(self, stub_page, sample_service_cells):
        t = _make_table(stub_page)
        t.set_table_from_service_response(sample_service_cells)
        assert t.table_data[0][0][0]["text"] == "Year"
        assert t.table_data[0][0][0]["confidence"] == 99.0
        assert t.table_data[1][1][0]["text"] == "331,002,651"

    def test_empty_cells(self, stub_page):
        t = _make_table(stub_page)
        t.set_table_from_service_response([])
        assert len(t.table_data) == 0

    def test_null_confidence(self, stub_page):
        t = _make_table(stub_page)
        t.set_table_from_service_response(
            [{"row": 0, "col": 0, "text": "hello", "confidence": None}]
        )
        assert t.table_data[0][0][0]["confidence"] is None

    def test_missing_keys_default(self, stub_page):
        t = _make_table(stub_page)
        t.set_table_from_service_response([{"row": 0, "col": 0}])
        assert t.table_data[0][0][0]["text"] == ""
        assert t.table_data[0][0][0]["confidence"] is None

    def test_multiple_cells_same_position(self, stub_page):
        """Multiple service cells at same row/col append (like multi-word OCR)."""
        t = _make_table(stub_page)
        t.set_table_from_service_response(
            [
                {"row": 0, "col": 0, "text": "hello", "confidence": 90},
                {"row": 0, "col": 0, "text": "world", "confidence": 80},
            ]
        )
        assert len(t.table_data[0][0]) == 2
        assert t.table_data[0][0][0]["text"] == "hello"
        assert t.table_data[0][0][1]["text"] == "world"


# ---------------------------------------------------------------------------
# is_numeric_cell
# ---------------------------------------------------------------------------


class TestIsNumericCell:
    def test_pure_number(self, stub_page):
        t = _make_table(stub_page)
        assert t.is_numeric_cell("12345") is True

    def test_pure_text(self, stub_page):
        t = _make_table(stub_page)
        assert t.is_numeric_cell("hello") is False

    def test_mostly_numeric(self, stub_page):
        t = _make_table(stub_page)
        assert t.is_numeric_cell("12.34") is True  # 4/5 = 80%

    def test_empty_string(self, stub_page):
        t = _make_table(stub_page)
        # 0 >= 0.6*0 → True (vacuously numeric); callers handle this
        assert t.is_numeric_cell("") is True

    def test_mixed_below_threshold(self, stub_page):
        t = _make_table(stub_page)
        assert t.is_numeric_cell("a1b2", threshold=0.6) is False  # 50%


# ---------------------------------------------------------------------------
# join_cell_parts
# ---------------------------------------------------------------------------


class TestJoinCellParts:
    def test_single_part(self, stub_page):
        t = _make_table(stub_page)
        result = t.join_cell_parts([{"text": "hello", "confidence": 90.0}])
        assert result["text"] == "hello"
        assert result["confidence"] == 90.0

    def test_multiple_parts(self, stub_page):
        t = _make_table(stub_page)
        result = t.join_cell_parts(
            [
                {"text": "hello", "confidence": 80.0},
                {"text": "world", "confidence": 100.0},
            ]
        )
        assert result["text"] == "hello world"
        assert result["confidence"] == 90.0

    def test_none_confidence(self, stub_page):
        t = _make_table(stub_page)
        result = t.join_cell_parts([{"text": "x", "confidence": None}])
        assert result["confidence"] is None

    def test_mixed_confidence(self, stub_page):
        t = _make_table(stub_page)
        result = t.join_cell_parts(
            [
                {"text": "a", "confidence": None},
                {"text": "b", "confidence": 80.0},
            ]
        )
        assert result["confidence"] == 80.0


# ---------------------------------------------------------------------------
# clean_cell_text
# ---------------------------------------------------------------------------


class TestCleanCellText:
    def test_preserves_normal_text(self, stub_page):
        t = _make_table(stub_page)
        text, dots, commas = t.clean_cell_text("hello world", False)
        assert text == "hello world"
        assert dots == 0
        assert commas == 0

    def test_counts_dots_and_commas(self, stub_page):
        t = _make_table(stub_page)
        text, dots, commas = t.clean_cell_text("1,234.56", False)
        assert dots == 1
        assert commas == 1

    def test_removes_dots_and_commas(self, stub_page):
        t = _make_table(stub_page)
        text, dots, commas = t.clean_cell_text("1,234.56", True)
        assert text == "123456"


# ---------------------------------------------------------------------------
# maybe_parse_numeric_cell
# ---------------------------------------------------------------------------


class TestMaybeParseNumericCell:
    def _cell(self, text, dots=0, commas=0):
        return {"text": text, "cnt_dots": dots, "cnt_commas": commas}

    def test_non_numeric_passthrough(self, stub_page):
        t = _make_table(stub_page)
        result, cnt = t.maybe_parse_numeric_cell(
            self._cell("hello"), ".", ",", True
        )
        assert result == "hello"
        assert cnt == NOT_NUMBER

    def test_simple_integer(self, stub_page):
        t = _make_table(stub_page)
        result, cnt = t.maybe_parse_numeric_cell(
            self._cell("12345"), ".", ",", False
        )
        assert result == 12345.0
        assert cnt == NOT_NUMBER

    def test_decimal_dot(self, stub_page):
        t = _make_table(stub_page)
        result, cnt = t.maybe_parse_numeric_cell(
            self._cell("123.45", dots=1), ".", ",", False
        )
        assert result == 123.45

    def test_decimal_comma(self, stub_page):
        t = _make_table(stub_page)
        result, cnt = t.maybe_parse_numeric_cell(
            self._cell("123,45", commas=1), ",", ".", False
        )
        assert result == 123.45

    def test_thousands_separator_removed(self, stub_page):
        t = _make_table(stub_page)
        result, cnt = t.maybe_parse_numeric_cell(
            self._cell("1,234,567", commas=2), ".", ",", False
        )
        assert result == 1234567.0

    def test_misspelling_fix(self, stub_page):
        t = _make_table(stub_page)
        # "O" → 0: input needs ≥60% digits to pass is_numeric_cell
        result, cnt = t.maybe_parse_numeric_cell(
            self._cell("1O0"), ".", ",", True
        )
        assert result == 100.0

    def test_fixed_decimal_places(self, stub_page):
        stub_page.document.fixed_decimal_places = 2
        t = _make_table(stub_page)
        result, cnt = t.maybe_parse_numeric_cell(
            self._cell("12345"), ".", ",", False
        )
        assert result == 123.45
        stub_page.document.fixed_decimal_places = 0


# ---------------------------------------------------------------------------
# extend_rows
# ---------------------------------------------------------------------------


class TestExtendRows:
    def test_basic_extend(self, stub_page):
        t = _make_table(stub_page)
        t.table_data = defaultdict(lambda: defaultdict(list))
        t.table_data[0][0] = [
            {"text": "line1", "confidence": 90},
            {"text": "line2", "confidence": 80},
        ]
        t.table_data[0][1] = [
            {"text": "col2", "confidence": 95},
        ]
        t.extend_rows()
        # Should have 2 rows now
        assert len(t.table_data) == 2
        assert t.table_data[0][0][0]["text"] == "line1"
        assert t.table_data[1][0][0]["text"] == "line2"


# ---------------------------------------------------------------------------
# as_clean_matrix
# ---------------------------------------------------------------------------


class TestAsCleanMatrix:
    def test_basic(self, stub_page, sample_service_cells):
        t = _make_table(stub_page)
        t.set_table_from_service_response(sample_service_cells)
        matrix = t.as_clean_matrix(False)
        assert len(matrix) == 3  # 3 rows
        assert len(matrix[0]) == 3  # 3 columns
        assert matrix[0][0]["text"] == "Year"
        assert matrix[0][0]["confidence"] == 99.0

    def test_empty_table(self, stub_page):
        t = _make_table(stub_page)
        t.set_table_from_service_response([])
        matrix = t.as_clean_matrix(False)
        assert matrix == []


# ---------------------------------------------------------------------------
# add_to_sheet (Excel output)
# ---------------------------------------------------------------------------


class TestAddToSheet:
    def test_writes_to_workbook(self, stub_page, sample_service_cells):
        t = _make_table(stub_page)
        t.set_table_from_service_response(sample_service_cells)
        matrix = t.as_clean_matrix(False)
        matrix = t.overwrite_seminumeric_cells_confidence(matrix, ".", ",", True)
        t.add_to_sheet(1, 1, matrix, "footer text")

        wb = stub_page.document.workbook
        assert "page_1_table_1" in wb.sheetnames
        sheet = wb["page_1_table_1"]
        assert sheet.cell(1, 1).value == "Year"
        assert sheet.cell(2, 1).value == "2020"

    def test_footer_recorded(self, stub_page, sample_service_cells):
        t = _make_table(stub_page)
        t.set_table_from_service_response(sample_service_cells)
        matrix = t.as_clean_matrix(False)
        matrix = t.overwrite_seminumeric_cells_confidence(matrix, ".", ",", True)
        t.add_to_sheet(1, 1, matrix, "my footer")

        fw = stub_page.document.footers_workbook
        rows = list(fw.active.iter_rows(values_only=True))
        assert rows[-1] == (1, 1, "my footer")
