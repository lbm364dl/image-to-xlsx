"""PDF text extraction service.

Accepts raw PDF bytes and a 1-indexed page number. Uses PyMuPDF to extract
tables directly from embedded PDF text (no OCR). Very fast, no GPU needed.
"""

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

app = FastAPI(title="PDF Text Extraction Service")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/extract")
async def extract(
    pdf: UploadFile = File(...),
    page_num: int = Form(1),
):
    """Extract tables from an embedded-text PDF page."""
    try:
        contents = await pdf.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read PDF: {exc}")

    try:
        import pymupdf

        doc = pymupdf.open("pdf", contents)
        if page_num < 1 or page_num > doc.page_count:
            raise HTTPException(
                status_code=400,
                detail=f"page_num {page_num} out of range (1..{doc.page_count})",
            )

        page = doc.load_page(page_num - 1)
        found = page.find_tables(strategy="text")

        tables = []
        for table in found.tables:
            bbox = list(table.bbox)
            cells = []
            for row_idx, row in enumerate(table.extract()):
                for col_idx, text in enumerate(row):
                    cells.append(
                        {
                            "row": row_idx,
                            "col": col_idx,
                            "text": text or "",
                            "confidence": None,
                        }
                    )
            tables.append({"bbox": bbox, "cells": cells})

        return JSONResponse({"tables": tables})

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
