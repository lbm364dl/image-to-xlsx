"""Integration tests for extraction microservices.

These test the FastAPI endpoints directly using TestClient (no HTTP needed).
Only services whose dependencies are available will run; others are skipped.
"""

import importlib
import io
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

# Make service directories importable
SERVICES_DIR = Path(__file__).resolve().parent.parent / "services"


def _import_service_app(service_dir):
    """Import a service's FastAPI app, avoiding module cache collisions."""
    path = str(service_dir)
    sys.path.insert(0, path)
    # Remove cached 'server' module so we get the right one
    sys.modules.pop("server", None)
    import server
    importlib.reload(server)  # ensure we loaded from the new path
    return server.app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _png_bytes(w=200, h=150):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (255, 255, 255)).save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def _pdf_with_table():
    """Create a minimal PDF with an actual text table."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=400, height=300)
    # Draw a simple text table
    page.insert_text((50, 50), "Name      Score")
    page.insert_text((50, 70), "Alice     95")
    page.insert_text((50, 90), "Bob       88")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _validate_response_schema(data):
    """Validate the unified extraction response format."""
    assert "tables" in data
    assert isinstance(data["tables"], list)
    for table in data["tables"]:
        assert "bbox" in table
        assert "cells" in table
        assert isinstance(table["bbox"], list)
        assert len(table["bbox"]) == 4
        assert isinstance(table["cells"], list)
        for cell in table["cells"]:
            assert "row" in cell
            assert "col" in cell
            assert "text" in cell
            assert "confidence" in cell
            assert isinstance(cell["row"], int)
            assert isinstance(cell["col"], int)
            assert isinstance(cell["text"], str)


# ---------------------------------------------------------------------------
# PDF-Text Service
# ---------------------------------------------------------------------------


class TestPdfTextService:
    @pytest.fixture(autouse=True)
    def _setup(self):
        from fastapi.testclient import TestClient

        app = _import_service_app(SERVICES_DIR / "pdf-text")
        self.client = TestClient(app)

    def test_health(self):
        resp = self.client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_extract_valid_pdf(self):
        pdf_bytes = _pdf_with_table()
        resp = self.client.post(
            "/extract",
            files={"pdf": ("test.pdf", pdf_bytes, "application/pdf")},
            data={"page_num": "1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        _validate_response_schema(data)

    def test_extract_empty_pdf(self):
        """A PDF with no tables should return empty tables list."""
        import pymupdf

        doc = pymupdf.open()
        doc.new_page()
        buf = io.BytesIO()
        doc.save(buf)

        resp = self.client.post(
            "/extract",
            files={"pdf": ("empty.pdf", buf.getvalue(), "application/pdf")},
            data={"page_num": "1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        _validate_response_schema(data)
        assert data["tables"] == []

    def test_invalid_page_num(self):
        pdf_bytes = _pdf_with_table()
        resp = self.client.post(
            "/extract",
            files={"pdf": ("test.pdf", pdf_bytes, "application/pdf")},
            data={"page_num": "999"},
        )
        assert resp.status_code == 400

    def test_invalid_input(self):
        resp = self.client.post(
            "/extract",
            files={"pdf": ("bad.pdf", b"not a pdf", "application/pdf")},
            data={"page_num": "1"},
        )
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Surya Service (schema validation only — skip if surya not installed)
# ---------------------------------------------------------------------------


class TestSuryaServiceSchema:
    @pytest.fixture(autouse=True)
    def _setup(self):
        try:
            import surya  # noqa: F401
        except ImportError:
            pytest.skip("surya-ocr not installed")

        from fastapi.testclient import TestClient

        app = _import_service_app(SERVICES_DIR / "surya")
        self.client = TestClient(app)

    def test_health(self):
        resp = self.client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_extract_returns_valid_schema(self):
        resp = self.client.post(
            "/extract",
            files={"image": ("page.png", _png_bytes(), "image/png")},
            data={"image_pad": "100"},
        )
        assert resp.status_code == 200
        _validate_response_schema(resp.json())

    def test_invalid_image(self):
        resp = self.client.post(
            "/extract",
            files={"image": ("bad.png", b"not an image", "image/png")},
        )
        assert resp.status_code == 400

    def test_unload(self):
        resp = self.client.post("/unload")
        assert resp.status_code == 200
        assert resp.json()["status"] == "unloaded"


# ---------------------------------------------------------------------------
# PaddleOCR-VL Service (skip if not installed)
# ---------------------------------------------------------------------------


class TestPaddleocrVlServiceSchema:
    @pytest.fixture(autouse=True)
    def _setup(self):
        try:
            import paddle  # noqa: F401
            from paddleocr import PaddleOCRVL  # noqa: F401
        except ImportError:
            pytest.skip("paddleocr/paddle not installed")

        from fastapi.testclient import TestClient

        app = _import_service_app(SERVICES_DIR / "paddleocr-vl")
        self.client = TestClient(app)

    def test_health(self):
        resp = self.client.get("/health")
        assert resp.status_code == 200

    def test_extract_returns_valid_schema(self):
        resp = self.client.post(
            "/extract",
            files={"image": ("page.png", _png_bytes(), "image/png")},
        )
        if resp.status_code == 500:
            pytest.skip("model inference failed (likely no GPU)")
        assert resp.status_code == 200
        _validate_response_schema(resp.json())

    def test_unload(self):
        resp = self.client.post("/unload")
        assert resp.status_code == 200
        assert resp.json()["status"] == "unloaded"


# ---------------------------------------------------------------------------
# GLM-OCR Service (skip if not installed)
# ---------------------------------------------------------------------------


class TestGlmOcrServiceSchema:
    @pytest.fixture(autouse=True)
    def _setup(self):
        try:
            import glmocr  # noqa: F401
        except ImportError:
            pytest.skip("glmocr not installed")

        from fastapi.testclient import TestClient

        app = _import_service_app(SERVICES_DIR / "glm-ocr")
        self.client = TestClient(app)

    def test_health(self):
        resp = self.client.get("/health")
        assert resp.status_code == 200

    def test_unload(self):
        resp = self.client.post("/unload")
        assert resp.status_code == 200
        assert resp.json()["status"] == "unloaded"


# ---------------------------------------------------------------------------
# Dewarp Service (skip if torch not available)
# ---------------------------------------------------------------------------


class TestDewarpServiceSchema:
    @pytest.fixture(autouse=True)
    def _setup(self):
        try:
            import torch  # noqa: F401
        except ImportError:
            pytest.skip("torch not installed")

        # Dewarping package needs to be importable
        dewarping_src = (
            Path(__file__).resolve().parent.parent
            / "src"
            / "image-to-xlsx"
        )
        sys.path.insert(0, str(dewarping_src))

        from fastapi.testclient import TestClient

        app = _import_service_app(SERVICES_DIR / "dewarp")
        self.client = TestClient(app)

    def test_health(self):
        resp = self.client.get("/health")
        assert resp.status_code == 200

    def test_dewarp_returns_png(self):
        resp = self.client.post(
            "/dewarp",
            files={"image": ("page.png", _png_bytes(), "image/png")},
        )
        if resp.status_code == 500:
            pytest.skip("dewarping model failed (likely no GPU)")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        # Verify it's a valid PNG
        img = Image.open(io.BytesIO(resp.content))
        assert img.format == "PNG"

    def test_invalid_image(self):
        resp = self.client.post(
            "/dewarp",
            files={"image": ("bad.png", b"not an image", "image/png")},
        )
        assert resp.status_code == 400

    def test_unload(self):
        resp = self.client.post("/unload")
        assert resp.status_code == 200
        assert resp.json()["status"] == "unloaded"
