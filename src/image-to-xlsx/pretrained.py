from paddlex import create_pipeline
from surya.settings import settings
from surya.model.table_rec.model import load_model as load_model
from surya.model.table_rec.processor import load_processor
from surya.model.detection.model import (
    load_model as load_det_model,
    load_processor as load_det_processor,
)


def model():
    return load_model()


def processor():
    return load_processor()


def layout_model():
    return load_det_model(checkpoint=settings.LAYOUT_MODEL_CHECKPOINT)


def layout_processor():
    return load_det_processor(checkpoint=settings.LAYOUT_MODEL_CHECKPOINT)


def det_model():
    return load_det_model()


def det_processor():
    return load_det_processor()


def ocr_pipeline():
    return create_pipeline(pipeline="OCR")


def all_models():
    return {
        "model": model(),
        "processor": processor(),
        "layout_model": layout_model(),
        "layout_processor": layout_processor(),
        "det_model": det_model(),
        "det_processor": det_processor(),
        "ocr_pipeline": ocr_pipeline(),
    }
