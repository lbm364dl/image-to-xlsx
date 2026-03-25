"""Surya OCR extraction service.

Receives a page image, detects tables via LayoutPredictor, extracts cell
structure with TableRecPredictor, and OCRs each cell with RecognitionPredictor.

Returns the unified extraction JSON format.
"""

import gc
import io
import os

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image

os.environ.setdefault("LAYOUT_BATCH_SIZE", "1")
os.environ.setdefault("TABLE_REC_BATCH_SIZE", "1")
os.environ.setdefault("RECOGNITION_BATCH_SIZE", "4")

app = FastAPI(title="Surya OCR Service")

# ---------------------------------------------------------------------------
# Lazy-loaded model singletons
# ---------------------------------------------------------------------------

_layout_predictor = None
_table_rec_predictor = None
_recognition_predictor = None
_detection_predictor = None


def _free_gpu():
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def get_layout_predictor():
    global _layout_predictor
    if _layout_predictor is None:
        from surya.foundation import FoundationPredictor
        from surya.layout import LayoutPredictor
        from surya.settings import settings

        _layout_predictor = LayoutPredictor(
            FoundationPredictor(checkpoint=settings.LAYOUT_MODEL_CHECKPOINT)
        )
    return _layout_predictor


def get_table_rec_predictor():
    global _table_rec_predictor
    if _table_rec_predictor is None:
        from surya.table_rec import TableRecPredictor

        _table_rec_predictor = TableRecPredictor()
    return _table_rec_predictor


def get_recognition_predictor():
    global _recognition_predictor
    if _recognition_predictor is None:
        from surya.foundation import FoundationPredictor
        from surya.recognition import RecognitionPredictor
        from surya.settings import settings

        _recognition_predictor = RecognitionPredictor(
            FoundationPredictor(checkpoint=settings.RECOGNITION_MODEL_CHECKPOINT)
        )
    return _recognition_predictor


def get_detection_predictor():
    global _detection_predictor
    if _detection_predictor is None:
        from surya.detection import DetectionPredictor

        _detection_predictor = DetectionPredictor()
    return _detection_predictor


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/unload")
def unload():
    """Release all models and free GPU memory."""
    global _layout_predictor, _table_rec_predictor
    global _recognition_predictor, _detection_predictor
    _layout_predictor = None
    _table_rec_predictor = None
    _recognition_predictor = None
    _detection_predictor = None
    _free_gpu()
    return {"status": "unloaded"}


@app.post("/extract")
async def extract(
    image: UploadFile = File(...),
    image_pad: int = Form(100),
):
    """Extract tables from a page image using Surya OCR."""
    try:
        contents = await image.read()
        page_image = Image.open(io.BytesIO(contents)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image: {exc}")

    try:
        import torch

        lp = get_layout_predictor()
        [layout_pred] = lp([page_image])
        table_bboxes = [b for b in layout_pred.bboxes if b.label == "Table"]

        table_rec = get_table_rec_predictor()
        rec = get_recognition_predictor()
        det = get_detection_predictor()

        tables = []
        for table_bbox in table_bboxes:
            bbox = list(table_bbox.bbox)
            cropped = page_image.crop(bbox)

            # Detect cell structure
            [table_result] = table_rec([cropped])

            # Crop + pad each cell for OCR
            cell_images = []
            cell_infos = []
            for cell in table_result.cells:
                cell_crop = cropped.crop(cell.bbox)
                arr = np.array(cell_crop.convert("RGB"))
                padded = np.pad(
                    arr,
                    ((image_pad, image_pad), (image_pad, image_pad), (0, 0)),
                    mode="constant",
                    constant_values=255,
                )
                cell_images.append(Image.fromarray(padded))
                cell_infos.append(cell)

            # Batch OCR
            cells = []
            if cell_images:
                BATCH_SIZE = 8
                ocr_results = []
                for i in range(0, len(cell_images), BATCH_SIZE):
                    batch = cell_images[i : i + BATCH_SIZE]
                    ocr_results.extend(rec(batch, det_predictor=det))
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()

                for cell_info, ocr_result in zip(cell_infos, ocr_results):
                    text = " ".join(line.text for line in ocr_result.text_lines)
                    confidences = [
                        line.confidence
                        for line in ocr_result.text_lines
                        if line.confidence is not None
                    ]
                    confidence = (
                        sum(confidences) / len(confidences) * 100
                        if confidences
                        else None
                    )
                    cells.append(
                        {
                            "row": cell_info.row_id,
                            "col": cell_info.col_id,
                            "text": text.strip(),
                            "confidence": confidence,
                        }
                    )

            tables.append({"bbox": bbox, "cells": cells})

        return JSONResponse({"tables": tables})

    except Exception as exc:
        _free_gpu()
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
