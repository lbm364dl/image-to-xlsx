"""GLM-OCR extraction service.

Wraps the glmocr SDK which runs PP-DocLayout-V3 locally for layout detection
and sends cropped regions to a vLLM/SGLang/Ollama backend for OCR.

Configure the LLM backend via environment variables:
  LLM_HOST  (default: localhost)
  LLM_PORT  (default: 8000)
  LLM_API_KEY  (optional)
  LLM_MODEL  (default: glm-ocr)
"""

import io
import json
import os
import re
import tempfile

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image

app = FastAPI(title="GLM-OCR Service")

_parser = None

LLM_HOST = os.environ.get("LLM_HOST", "localhost")
LLM_PORT = int(os.environ.get("LLM_PORT", "8000"))
LLM_API_KEY = os.environ.get("LLM_API_KEY") or None
LLM_MODEL = os.environ.get("LLM_MODEL", "glm-ocr")


def _get_parser():
    global _parser
    if _parser is not None:
        return _parser

    import yaml
    from glmocr import GlmOcr

    config = {
        "pipeline": {
            "maas": {"enabled": False},
            "ocr_api": {
                "api_host": LLM_HOST,
                "api_port": LLM_PORT,
                "connect_timeout": 300,
                "request_timeout": 300,
            },
            "enable_layout": True,
        },
    }
    if LLM_API_KEY:
        config["pipeline"]["ocr_api"]["api_key"] = LLM_API_KEY
    if LLM_MODEL:
        config["pipeline"]["ocr_api"]["model"] = LLM_MODEL

    fd, config_path = tempfile.mkstemp(suffix=".yaml")
    try:
        with os.fdopen(fd, "w") as f:
            yaml.dump(config, f)
        _parser = GlmOcr(config_path=config_path)
    finally:
        try:
            os.unlink(config_path)
        except OSError:
            pass

    return _parser


# ---------------------------------------------------------------------------
# Table parsing helpers
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


def _tables_from_markdown(markdown_content):
    """Fallback: extract tables from raw markdown when no structured JSON."""
    html_pat = re.compile(r"<table[^>]*>.*?</table>", re.DOTALL | re.IGNORECASE)
    md_pat = re.compile(r"(?:^|\n)((?:\|[^\n]+\|\s*\n){2,})", re.MULTILINE)

    tables = []
    for m in html_pat.finditer(markdown_content):
        rows = _parse_html_table(m.group(0))
        if rows:
            tables.append({"bbox": [0, 0, 0, 0], "cells": _rows_to_cells(rows)})

    remaining = html_pat.sub("", markdown_content)
    for m in md_pat.finditer(remaining):
        rows = _parse_markdown_table(m.group(1).strip())
        if rows:
            tables.append({"bbox": [0, 0, 0, 0], "cells": _rows_to_cells(rows)})

    return tables


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _free_gpu():
    import gc

    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/unload")
def unload():
    """Release the parser and free GPU memory."""
    global _parser
    _parser = None
    _free_gpu()
    return {"status": "unloaded"}


@app.post("/extract")
async def extract(image: UploadFile = File(...)):
    """Extract tables from a page image using GLM-OCR."""
    try:
        contents = await image.read()
        pil_image = Image.open(io.BytesIO(contents))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image: {exc}")

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
        pil_image.save(tmp_path)

    try:
        parser = _get_parser()
        result = parser.parse(tmp_path, save_layout_visualization=False)
        tables = []

        json_result = result.json_result
        if isinstance(json_result, str):
            try:
                json_result = json.loads(json_result)
            except (json.JSONDecodeError, TypeError):
                json_result = []

        if isinstance(json_result, list):
            for page_data in json_result:
                if not isinstance(page_data, list):
                    continue
                for block in page_data:
                    if not isinstance(block, dict) or block.get("label") != "table":
                        continue
                    content = block.get("content", "").strip()
                    if not content:
                        continue
                    bbox = block.get("bbox_2d") or [0, 0, 0, 0]
                    if hasattr(bbox, "tolist"):
                        bbox = bbox.tolist()

                    if "<table" in content.lower():
                        rows = _parse_html_table(content)
                    else:
                        rows = _parse_markdown_table(content)

                    if rows:
                        tables.append(
                            {"bbox": list(bbox), "cells": _rows_to_cells(rows)}
                        )

        if not tables and result.markdown_result:
            tables = _tables_from_markdown(result.markdown_result)

        return JSONResponse({"tables": tables})

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}")
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
