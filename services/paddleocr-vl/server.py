"""PaddleOCR-VL extraction service.

Receives a page image, runs PaddleOCR-VL 1.5 for document parsing,
and returns detected tables in the unified extraction format.
"""

import io
import os
import tempfile

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image

os.environ.setdefault("FLAGS_allocator_strategy", "naive_best_fit")
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

app = FastAPI(title="PaddleOCR-VL Service")

_pipeline = None


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        import paddle
        from paddleocr import PaddleOCRVL

        device = os.environ.get("PADDLEOCR_DEVICE")
        if device is None:
            device = "gpu:0" if paddle.device.cuda.device_count() > 0 else "cpu"
        _pipeline = PaddleOCRVL(device=device)
    return _pipeline


# ---------------------------------------------------------------------------
# Table parsing helpers (HTML / markdown)
# ---------------------------------------------------------------------------


def _parse_html_table(text):
    import html as html_mod
    from html.parser import HTMLParser

    class _P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows = []
            self._row = None
            self._in_cell = False
            self._buf = []

        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self._row = []
            elif tag in ("td", "th"):
                self._in_cell = True
                self._buf = []

        def handle_endtag(self, tag):
            if tag in ("td", "th") and self._in_cell:
                self._row.append("".join(self._buf).strip())
                self._in_cell = False
            elif tag == "tr" and self._row is not None:
                if self._row:
                    self.rows.append(self._row)
                self._row = None

        def handle_data(self, data):
            if self._in_cell:
                self._buf.append(html_mod.unescape(data))

    p = _P()
    p.feed(text)
    return p.rows


def _parse_markdown_table(text):
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    rows = []
    for line in lines:
        stripped = line.strip("|").strip()
        if not stripped or all(c in "-|: " for c in stripped):
            continue
        cells = line.split("|")
        if cells and cells[0].strip() == "":
            cells = cells[1:]
        if cells and cells[-1].strip() == "":
            cells = cells[:-1]
        rows.append([c.strip() for c in cells])
    return rows


def _rows_to_cells(rows):
    return [
        {"row": r, "col": c, "text": text.strip(), "confidence": None}
        for r, row in enumerate(rows)
        for c, text in enumerate(row)
    ]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _free_gpu():
    import gc

    gc.collect()
    try:
        import paddle

        paddle.device.cuda.empty_cache()
    except Exception:
        pass


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/unload")
def unload():
    """Release the pipeline and free GPU memory."""
    global _pipeline
    _pipeline = None
    _free_gpu()
    return {"status": "unloaded"}


@app.post("/extract")
async def extract(image: UploadFile = File(...)):
    """Extract tables from a page image using PaddleOCR-VL."""
    try:
        contents = await image.read()
        pil_image = Image.open(io.BytesIO(contents))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image: {exc}")

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
        pil_image.save(tmp_path)

    try:
        pipeline = get_pipeline()
        output = pipeline.predict(tmp_path)
        tables = []

        for res in output:
            res_json = res.json["res"]
            for block in res_json.get("parsing_res_list", []):
                if block.get("block_label") != "table":
                    continue
                content = block.get("block_content", "").strip()
                if not content:
                    continue
                bbox = block.get("block_bbox", [0, 0, 0, 0])
                if hasattr(bbox, "tolist"):
                    bbox = bbox.tolist()

                if "<table" in content.lower():
                    rows = _parse_html_table(content)
                else:
                    rows = _parse_markdown_table(content)

                tables.append({"bbox": list(bbox), "cells": _rows_to_cells(rows)})

        return JSONResponse({"tables": tables})

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}")
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
