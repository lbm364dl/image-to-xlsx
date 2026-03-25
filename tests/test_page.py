"""Tests for Page — verifies HTTP delegation and preprocessing."""

import io
import json
from unittest.mock import patch, MagicMock

import numpy as np
import pytest
from PIL import Image

from page import Page, _image_to_png, _post_image, _build_tables


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _white_image(w=100, h=80):
    return Image.new("RGB", (w, h), (255, 255, 255))


def _fake_response(tables_json, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = tables_json
    resp.raise_for_status.return_value = None
    return resp


def _fake_png_response(image):
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    resp = MagicMock()
    resp.status_code = 200
    resp.content = buf.getvalue()
    resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# _image_to_png
# ---------------------------------------------------------------------------


class TestImageToPng:
    def test_pil_image(self):
        img = _white_image()
        png = _image_to_png(img)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"

    def test_numpy_array(self):
        arr = np.ones((50, 60, 3), dtype=np.uint8) * 128
        png = _image_to_png(arr)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"

    def test_roundtrip(self):
        img = _white_image(30, 40)
        png = _image_to_png(img)
        recovered = Image.open(io.BytesIO(png))
        assert recovered.size == (30, 40)


# ---------------------------------------------------------------------------
# _build_tables
# ---------------------------------------------------------------------------


class TestBuildTables:
    def test_builds_correct_count(self, stub_page, multi_table_response):
        tables = _build_tables(multi_table_response, None, stub_page)
        assert len(tables) == 2

    def test_first_table_data(self, stub_page, sample_service_response):
        tables = _build_tables(sample_service_response, None, stub_page)
        assert len(tables) == 1
        t = tables[0]
        assert t.table_data[0][0][0]["text"] == "Year"
        assert t.table_bbox == [10, 20, 500, 400]

    def test_empty_response(self, stub_page, empty_service_response):
        tables = _build_tables(empty_service_response, None, stub_page)
        assert tables == []


# ---------------------------------------------------------------------------
# Page._extract_surya (mocked HTTP)
# ---------------------------------------------------------------------------


class TestExtractSurya:
    @patch("page.requests.post")
    def test_calls_service(self, mock_post, stub_page, sample_service_response):
        mock_post.return_value = _fake_response(sample_service_response)
        p = Page(_white_image(), 1, stub_page.document)
        tables = p._extract_surya()
        assert len(tables) == 1
        assert mock_post.called
        url_called = mock_post.call_args[0][0]
        assert "/extract" in url_called

    @patch("page.requests.post")
    def test_passes_image_pad(self, mock_post, stub_page, sample_service_response):
        mock_post.return_value = _fake_response(sample_service_response)
        p = Page(_white_image(), 1, stub_page.document)
        p._extract_surya(image_pad=200)
        _, kwargs = mock_post.call_args
        assert kwargs["data"]["image_pad"] == "200"

    @patch("page.requests.post")
    def test_unskew_called(self, mock_post, stub_page, sample_service_response):
        mock_post.return_value = _fake_response(sample_service_response)
        p = Page(_white_image(200, 200), 1, stub_page.document)
        with patch.object(p, "rotate") as mock_rotate:
            p._extract_surya(unskew=True)
            mock_rotate.assert_called_once()

    @patch("page.requests.post")
    def test_binarize_called(self, mock_post, stub_page, sample_service_response):
        mock_post.return_value = _fake_response(sample_service_response)
        p = Page(_white_image(200, 200), 1, stub_page.document)
        with patch.object(p, "binarize_image") as mock_bin:
            p._extract_surya(binarize=True)
            mock_bin.assert_called_once()


# ---------------------------------------------------------------------------
# Page._extract_paddleocr_vl
# ---------------------------------------------------------------------------


class TestExtractPaddleocrVl:
    @patch("page.requests.post")
    def test_calls_service(self, mock_post, stub_page, sample_service_response):
        mock_post.return_value = _fake_response(sample_service_response)
        p = Page(_white_image(), 1, stub_page.document)
        tables = p._extract_paddleocr_vl()
        assert len(tables) == 1


# ---------------------------------------------------------------------------
# Page._extract_glm_ocr
# ---------------------------------------------------------------------------


class TestExtractGlmOcr:
    @patch("page.requests.post")
    def test_calls_service(self, mock_post, stub_page, sample_service_response):
        mock_post.return_value = _fake_response(sample_service_response)
        p = Page(_white_image(), 1, stub_page.document)
        tables = p._extract_glm_ocr()
        assert len(tables) == 1


# ---------------------------------------------------------------------------
# Page._extract_pdf_text
# ---------------------------------------------------------------------------


class TestExtractPdfText:
    @patch("page.requests.post")
    def test_sends_pdf_bytes(self, mock_post, stub_page, sample_service_response):
        mock_post.return_value = _fake_response(sample_service_response)
        stub_page.document.pdf_bytes = b"%PDF-1.4 fake"
        p = Page(None, 3, stub_page.document)
        tables = p._extract_pdf_text()
        assert len(tables) == 1
        # Verify pdf bytes were sent
        _, kwargs = mock_post.call_args
        sent_pdf = kwargs["files"]["pdf"]
        assert sent_pdf[1] == b"%PDF-1.4 fake"
        assert kwargs["data"]["page_num"] == "3"


# ---------------------------------------------------------------------------
# Page.dewarp (mocked HTTP)
# ---------------------------------------------------------------------------


class TestDewarp:
    @patch("page.requests.post")
    def test_dewarp_replaces_image(self, mock_post, stub_page):
        dewarped_img = _white_image(80, 60)
        mock_post.return_value = _fake_png_response(dewarped_img)
        original = _white_image(100, 100)
        p = Page(original, 1, stub_page.document)
        p.dewarp()
        assert p.page.size == (80, 60)

    @patch("page.requests.post")
    def test_stores_last_dewarped(self, mock_post, stub_page):
        mock_post.return_value = _fake_png_response(_white_image())
        p = Page(_white_image(), 1, stub_page.document)
        Page.reset_last_dewarped_image()
        assert Page.get_last_dewarped_image() is None
        p.dewarp()
        assert Page.get_last_dewarped_image() is not None


# ---------------------------------------------------------------------------
# Page.process_page (full pipeline, mocked HTTP)
# ---------------------------------------------------------------------------


class TestProcessPage:
    @patch("page.requests.post")
    def test_full_pipeline(self, mock_post, stub_page, sample_service_response):
        mock_post.return_value = _fake_response(sample_service_response)
        p = Page(_white_image(), 1, stub_page.document)
        p.process_page(
            decimal_separator=".",
            thousands_separator=",",
            fix_num_misspellings=True,
        )
        wb = stub_page.document.workbook
        assert len(wb.sheetnames) == 1
        assert "page_1_table_1" in wb.sheetnames

    @patch("page.requests.post")
    def test_empty_result(self, mock_post, stub_page, empty_service_response):
        mock_post.return_value = _fake_response(empty_service_response)
        p = Page(_white_image(), 1, stub_page.document)
        p.process_page(
            decimal_separator=".",
            thousands_separator=",",
            fix_num_misspellings=True,
        )
        wb = stub_page.document.workbook
        assert len(wb.sheetnames) == 0
