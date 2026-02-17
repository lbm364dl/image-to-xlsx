"""High-level dewarping API using the GeoTr model.

Downloads the pre-trained GeoTr checkpoint (trained on Inv3D) from Google
Drive on first use, then runs inference to dewarp document images.

Usage
-----
    from dewarping import dewarp_image
    from PIL import Image

    img = Image.open("warped_document.jpg")
    dewarped = dewarp_image(img)          # returns a PIL Image
"""

import os
import cv2
import numpy as np
import torch
import torch.nn.functional as F
from pathlib import Path
from PIL import Image

from .geotr_model import GeoTr

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODEL_RESOLUTION = 288  # GeoTr expects 288x288 input
MODEL_URL = "https://drive.google.com/uc?id=17wSb997P8pDnfobhX2M206oQwlOZ-0dK"
MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_PATH = MODEL_DIR / "geotr_inv3d.ckpt"

# Module-level cached model (loaded once, reused across calls)
_cached_model = None


# ---------------------------------------------------------------------------
# Model download helpers
# ---------------------------------------------------------------------------

def is_model_downloaded() -> bool:
    """Check whether the GeoTr checkpoint already exists on disk."""
    return MODEL_PATH.is_file()


def download_model() -> Path:
    """Download the GeoTr@Inv3D checkpoint from Google Drive.

    Uses *gdown* for reliable Google-Drive downloads.  The file is saved
    to ``dewarping/models/geotr_inv3d.ckpt``.
    """
    import gdown

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[dewarping] Downloading GeoTr model to {MODEL_PATH} ...")
    gdown.download(MODEL_URL, str(MODEL_PATH), quiet=False)
    print("[dewarping] Download complete.")
    return MODEL_PATH


# ---------------------------------------------------------------------------
# Utility functions (self-contained replacements for inv3d_util)
# ---------------------------------------------------------------------------

def _scale_image(image: np.ndarray, resolution: int) -> np.ndarray:
    """Resize an HxWxC uint8 image to (resolution, resolution)."""
    return cv2.resize(image, (resolution, resolution), interpolation=cv2.INTER_AREA)


def _median_blur(x: torch.Tensor) -> torch.Tensor:
    """Cheap 3x3 box blur on the channel dimension (replaces inv3d_util.misc.median_blur)."""
    n, c, h, w = x.shape
    kernel = torch.ones((1, 1, 3, 3), device=x.device, dtype=x.dtype) / 9.0
    x = x.reshape(n * c, 1, h, w)
    x = torch.nn.ReplicationPad2d(1)(x)
    x = F.conv2d(x, kernel)
    x = x.reshape(n, c, h, w)
    return x


def _apply_map_torch(
    image: torch.Tensor,
    bm: torch.Tensor,
    resolution=None,
) -> torch.Tensor:
    """Apply a backward-map to an image using grid_sample (replaces inv3d_util.mapping.apply_map_torch)."""
    # image: (N, C, H, W),  bm: (N, 2, H, W)
    if resolution is not None:
        if isinstance(resolution, int):
            resolution = (resolution, resolution)
        bm = F.interpolate(bm, size=resolution, mode="bilinear", align_corners=True)

    input_dtype = image.dtype
    image = image.double()
    # bm: (N, 2, H, W) -> (N, H, W, 2)
    bm = bm.permute(0, 2, 3, 1).double()
    bm = (bm * 2) - 1
    bm = torch.roll(bm, shifts=1, dims=-1)

    res = F.grid_sample(input=image, grid=bm, align_corners=True)
    return res.to(input_dtype)


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

def _load_model(device: torch.device) -> GeoTr:
    """Load the GeoTr model from the downloaded checkpoint."""
    global _cached_model
    if _cached_model is not None:
        return _cached_model

    if not is_model_downloaded():
        download_model()

    # PyTorch Lightning checkpoint → extract raw state_dict
    ckpt = torch.load(str(MODEL_PATH), map_location=device, weights_only=False)
    state_dict = ckpt.get("state_dict", ckpt)

    # Strip the "model." prefix that PL adds
    cleaned = {}
    for k, v in state_dict.items():
        new_key = k.replace("model.", "", 1) if k.startswith("model.") else k
        cleaned[new_key] = v

    model = GeoTr(num_attn_layers=6)
    model.load_state_dict(cleaned, strict=False)
    model.to(device)
    model.eval()

    _cached_model = model
    return model


def clear_model_cache():
    """Release the cached model to free memory."""
    global _cached_model
    _cached_model = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def dewarp_image(pil_image: Image.Image) -> Image.Image:
    """Dewarp a document image using GeoTr.

    Parameters
    ----------
    pil_image : PIL.Image.Image
        RGB (or RGBA) document image, any resolution.

    Returns
    -------
    PIL.Image.Image
        The dewarped image at the original resolution.
    """
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = _load_model(device)

    # Convert to numpy RGB
    image_rgb = np.array(pil_image.convert("RGB"))
    original_h, original_w = image_rgb.shape[:2]

    # Scale to model resolution
    image_scaled = _scale_image(image_rgb, MODEL_RESOLUTION)

    # Prepare tensor: (1, 3, H, W) float32 in [0, 1]
    image_tensor = torch.from_numpy(image_scaled).permute(2, 0, 1).unsqueeze(0).float() / 255.0
    image_tensor = image_tensor.to(device)

    # Run inference
    with torch.no_grad():
        out_bm = model(image_tensor)
        # Post-process backward map (same as LitGeoTr.forward)
        out_bm = out_bm.permute(0, 1, 3, 2) / MODEL_RESOLUTION  # rearrange "b c h w -> b c w h"
        out_bm = _median_blur(out_bm)
        out_bm = torch.clamp(out_bm, min=0, max=1)

    # Unwarp the original full-resolution image
    out_bm = out_bm.cpu()
    image_full = torch.from_numpy(image_rgb).permute(2, 0, 1).unsqueeze(0).float() / 255.0
    dewarped_tensor = _apply_map_torch(
        image_full, out_bm, resolution=(original_h, original_w)
    )

    # Convert back to PIL
    dewarped_np = (dewarped_tensor.squeeze(0).permute(1, 2, 0) * 255).clamp(0, 255).byte().numpy()
    return Image.fromarray(dewarped_np)
