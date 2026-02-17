"""Document image dewarping using GeoTr from the doc-matcher project.

Based on: https://github.com/FelixHertlein/doc-matcher
Paper: "DocMatcher: Document Image Dewarping via Structural and Textual
       Line Matching" (WACV 2025)

This module extracts and self-contains the GeoTr dewarping model so it can
run standalone without pulling in the full doc-matcher pipeline.
"""

from .dewarp import dewarp_image, is_model_downloaded, download_model

__all__ = ["dewarp_image", "is_model_downloaded", "download_model"]
