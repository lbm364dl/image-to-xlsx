import numpy as np
import cv2
from PIL import Image


def binarize(img, method="otsu", block_size=None, constant=None):
    gray_img = np.array(img.convert("L"))
    binarized = None

    if method == "adaptive":
        binarized = cv2.adaptiveThreshold(
            gray_img,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            block_size,
            constant,
        )
    elif method == "otsu":
        _, binarized = cv2.threshold(
            gray_img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

    return Image.fromarray(binarized).convert("RGB")
