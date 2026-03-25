"""Page processing — delegates extraction to microservices via HTTP."""

import io
import os

import numpy as np
import requests
from PIL import Image

from binarization import binarize
from table import Table
from unskewing import correct_skew

# ---------------------------------------------------------------------------
# Service URLs (configure via environment variables or docker-compose)
# ---------------------------------------------------------------------------
SURYA_SERVICE_URL = os.environ.get("SURYA_SERVICE_URL", "http://localhost:8001")
PADDLEOCR_VL_SERVICE_URL = os.environ.get(
    "PADDLEOCR_VL_SERVICE_URL", "http://localhost:8002"
)
GLM_OCR_SERVICE_URL = os.environ.get("GLM_OCR_SERVICE_URL", "http://localhost:8003")
PDF_TEXT_SERVICE_URL = os.environ.get("PDF_TEXT_SERVICE_URL", "http://localhost:8004")
DEWARP_SERVICE_URL = os.environ.get("DEWARP_SERVICE_URL", "http://localhost:8005")

_REQUEST_TIMEOUT = int(os.environ.get("SERVICE_TIMEOUT", "300"))

# Last dewarped page image (stored so it can be included in the results zip)
_last_dewarped_image = None


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _image_to_png(image):
    """Serialize a PIL Image (or array) to PNG bytes."""
    buf = io.BytesIO()
    if isinstance(image, Image.Image):
        image.convert("RGB").save(buf, format="PNG")
    else:
        Image.fromarray(np.array(image)).save(buf, format="PNG")
    return buf.getvalue()


def _post_image(url, image, **extra_fields):
    """POST an image to an extraction service, return the JSON response."""
    png = _image_to_png(image)
    resp = requests.post(
        f"{url}/extract",
        files={"image": ("page.png", png, "image/png")},
        data=extra_fields,
        timeout=_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _build_tables(data, page_image, page_obj):
    """Convert the unified service JSON into a list of Table objects."""
    tables = []
    for entry in data["tables"]:
        t = Table(page_image, page_obj, entry["bbox"])
        t.set_table_from_service_response(entry["cells"])
        tables.append(t)
    return tables


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------


class Page:
    def __init__(self, page, page_num, document):
        self.page = page
        self.page_num = page_num
        self.document = document

    # -- Preprocessing (lightweight, stays in the main app) -----------------

    def dewarp(self):
        """Dewarp via the dewarp microservice."""
        global _last_dewarped_image
        png = _image_to_png(self.page)
        resp = requests.post(
            f"{DEWARP_SERVICE_URL}/dewarp",
            files={"image": ("page.png", png, "image/png")},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        self.page = Image.open(io.BytesIO(resp.content)).convert("RGB")
        _last_dewarped_image = self.page.copy()

    @staticmethod
    def get_last_dewarped_image():
        return _last_dewarped_image

    @staticmethod
    def reset_last_dewarped_image():
        global _last_dewarped_image
        _last_dewarped_image = None

    def rotate(self, delta=0.5, limit=5, custom_angle=None):
        _, corrected = correct_skew(np.array(self.page), delta, limit, custom_angle)
        self.page = Image.fromarray(corrected)

    def binarize_image(self, method="otsu", block_size=None, constant=None):
        self.page = binarize(self.page, method, block_size, constant)

    # -- Extraction (delegates to microservices) ----------------------------

    def process_page(self, **kwargs):
        methods = {
            "surya": self._extract_surya,
            "pdf-text": self._extract_pdf_text,
            "paddleocr-vl": self._extract_paddleocr_vl,
            "glm-ocr": self._extract_glm_ocr,
        }

        tables = methods[self.document.method](**kwargs)

        for i, table in enumerate(tables):
            if kwargs.get("extend_rows"):
                table.extend_rows()

            matrix = table.as_clean_matrix(kwargs.get("remove_dots_and_commas"))
            matrix = table.overwrite_seminumeric_cells_confidence(
                matrix,
                kwargs.get("decimal_separator"),
                kwargs.get("thousands_separator"),
                kwargs.get("fix_num_misspellings"),
            )

            if kwargs.get("nlp_postprocess"):
                matrix = table.nlp_postprocess(
                    matrix,
                    kwargs.get("text_language"),
                    kwargs.get("nlp_postprocess_prompt_file"),
                )

            matrix = table.maybe_parse_numeric_cells(
                matrix,
                kwargs.get("decimal_separator"),
                kwargs.get("thousands_separator"),
                kwargs.get("fix_num_misspellings"),
            )

            table.add_to_sheet(self.page_num, i + 1, matrix, table.footer_text)

    def _extract_surya(self, **kwargs):
        if kwargs.get("unskew"):
            self.rotate()
        if kwargs.get("binarize"):
            self.binarize_image(method="otsu", block_size=31, constant=10)
        data = _post_image(
            SURYA_SERVICE_URL,
            self.page,
            image_pad=str(kwargs.get("image_pad", 100)),
        )
        return _build_tables(data, self.page, self)

    def _extract_paddleocr_vl(self, **kwargs):
        data = _post_image(PADDLEOCR_VL_SERVICE_URL, self.page)
        return _build_tables(data, self.page, self)

    def _extract_glm_ocr(self, **kwargs):
        data = _post_image(GLM_OCR_SERVICE_URL, self.page)
        return _build_tables(data, self.page, self)

    def _extract_pdf_text(self, **kwargs):
        resp = requests.post(
            f"{PDF_TEXT_SERVICE_URL}/extract",
            files={"pdf": ("doc.pdf", self.document.pdf_bytes, "application/pdf")},
            data={"page_num": str(self.page_num)},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return _build_tables(data, None, self)
