"""Cached surya predictor instances for the 'surya' extraction method.

Predictors are loaded on demand and can be freed individually to save GPU memory.
"""

import os
import gc

# Defaults for single-page processing. Override with environment variables.
os.environ.setdefault("LAYOUT_BATCH_SIZE", "1")
os.environ.setdefault("TABLE_REC_BATCH_SIZE", "1")
os.environ.setdefault("RECOGNITION_BATCH_SIZE", "4")

_layout_predictor = None
_table_rec_predictor = None
_recognition_predictor = None
_detection_predictor = None


def _free_gpu():
    """Free GPU memory after unloading a model."""
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def layout_predictor():
    global _layout_predictor
    if _layout_predictor is None:
        from surya.foundation import FoundationPredictor
        from surya.layout import LayoutPredictor
        from surya.settings import settings

        _layout_predictor = LayoutPredictor(
            FoundationPredictor(checkpoint=settings.LAYOUT_MODEL_CHECKPOINT)
        )
    return _layout_predictor


def free_layout_predictor():
    global _layout_predictor
    _layout_predictor = None
    _free_gpu()


def table_rec_predictor():
    global _table_rec_predictor
    if _table_rec_predictor is None:
        from surya.table_rec import TableRecPredictor

        _table_rec_predictor = TableRecPredictor()
    return _table_rec_predictor


def free_table_rec_predictor():
    global _table_rec_predictor
    _table_rec_predictor = None
    _free_gpu()


def recognition_predictor():
    global _recognition_predictor
    if _recognition_predictor is None:
        from surya.foundation import FoundationPredictor
        from surya.recognition import RecognitionPredictor
        from surya.settings import settings

        _recognition_predictor = RecognitionPredictor(
            FoundationPredictor(checkpoint=settings.RECOGNITION_MODEL_CHECKPOINT)
        )
    return _recognition_predictor


def detection_predictor():
    global _detection_predictor
    if _detection_predictor is None:
        from surya.detection import DetectionPredictor

        _detection_predictor = DetectionPredictor()
    return _detection_predictor


def free_ocr_predictors():
    global _recognition_predictor, _detection_predictor
    _recognition_predictor = None
    _detection_predictor = None
    _free_gpu()


def clear_all_models():
    global _layout_predictor, _table_rec_predictor
    global _recognition_predictor, _detection_predictor
    _layout_predictor = None
    _table_rec_predictor = None
    _recognition_predictor = None
    _detection_predictor = None
    _free_gpu()
