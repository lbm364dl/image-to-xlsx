"""Document dewarping service.

Accepts a warped document image and returns the dewarped version using the
GeoTr model (trained on Inv3D). Downloads the checkpoint on first use.
"""

import io
import os
import sys

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image

# Add this directory to path so the dewarping package can be imported
sys.path.insert(0, os.path.dirname(__file__))

app = FastAPI(title="Dewarp Service")

_dewarp_fn = None


def _get_dewarp_fn():
    global _dewarp_fn
    if _dewarp_fn is None:
        from dewarping import dewarp_image

        _dewarp_fn = dewarp_image
    return _dewarp_fn


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
    """Release the dewarping model and free GPU memory."""
    global _dewarp_fn
    # The model is held inside the dewarping module; reset our reference
    # and try to clear the module-level model too.
    _dewarp_fn = None
    try:
        import dewarping

        if hasattr(dewarping, "_model"):
            dewarping._model = None
    except Exception:
        pass
    _free_gpu()
    return {"status": "unloaded"}


@app.post("/dewarp")
async def dewarp(image: UploadFile = File(...)):
    """Dewarp a document image and return the result as PNG."""
    try:
        contents = await image.read()
        pil_image = Image.open(io.BytesIO(contents)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image: {exc}")

    try:
        fn = _get_dewarp_fn()
        dewarped = fn(pil_image)
        buf = io.BytesIO()
        dewarped.save(buf, format="PNG")
        return Response(content=buf.getvalue(), media_type="image/png")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Dewarping failed: {exc}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
