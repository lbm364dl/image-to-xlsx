"""Tests for Document class — PDF/image loading and page management."""

import io
import pytest
from PIL import Image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_png_bytes(w=100, h=80):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 200, 200)).save(buf, format="PNG")
    return buf.getvalue()


def _make_pdf_bytes():
    """Create a minimal valid single-page PDF."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=200, height=300)
    page.insert_text((50, 100), "Hello World")
    # Insert a table-like structure
    page.insert_text((50, 150), "Col1    Col2")
    page.insert_text((50, 170), "val1    val2")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Document init
# ---------------------------------------------------------------------------


class TestDocumentInit:
    def test_image_document(self, make_document):
        content = _make_png_bytes()
        doc = make_document(content, name="photo.png", method="surya")
        assert doc.extension == "png"
        assert doc.tot_pages == 1
        assert 1 in doc.pages
        assert isinstance(doc.pages[1], Image.Image)
        assert doc.pdf_bytes is None

    def test_pdf_document(self, make_document):
        content = _make_pdf_bytes()
        doc = make_document(content, name="report.pdf", method="surya")
        assert doc.extension == "pdf"
        assert doc.tot_pages == 1
        assert 1 in doc.pages
        assert isinstance(doc.pages[1], Image.Image)
        assert doc.pdf_bytes == content

    def test_pdf_text_method_stores_bytes(self, make_document):
        content = _make_pdf_bytes()
        doc = make_document(content, name="report.pdf", method="pdf-text")
        assert doc.pdf_bytes == content
        # pdf-text stores None pages (extraction handled by service)
        assert doc.pages[1] is None

    def test_workbooks_created(self, make_document):
        content = _make_png_bytes()
        doc = make_document(content, name="img.png")
        assert doc.workbook is not None
        assert doc.footers_workbook is not None
        # Main workbook starts empty
        assert len(doc.workbook.sheetnames) == 0
        # Footers workbook has header row
        rows = list(doc.footers_workbook.active.iter_rows(values_only=True))
        assert rows[0] == ("page_number", "table_number", "footer_text")


# ---------------------------------------------------------------------------
# Page ranges
# ---------------------------------------------------------------------------


class TestPageRanges:
    def test_single_page(self, make_document):
        content = _make_pdf_bytes()
        doc = make_document(content, name="report.pdf")
        assert doc.page_nums == {1}

    def test_out_of_range_clipped(self):
        """Requesting pages beyond doc length clips to actual page count."""
        from document import Document

        content = _make_pdf_bytes()  # 1-page PDF
        doc_dict = {
            "name": "report.pdf",
            "content": content,
            "pages": [(1, 999)],
        }
        doc = Document(doc_dict, method="surya")
        assert doc.page_nums == {1}

    def test_multiple_ranges(self):
        from document import Document
        import pymupdf

        # Create a 5-page PDF
        pdf_doc = pymupdf.open()
        for _ in range(5):
            pdf_doc.new_page()
        buf = io.BytesIO()
        pdf_doc.save(buf)
        content = buf.getvalue()

        doc_dict = {
            "name": "big.pdf",
            "content": content,
            "pages": [(1, 2), (4, 5)],
        }
        doc = Document(doc_dict, method="surya")
        assert doc.page_nums == {1, 2, 4, 5}
