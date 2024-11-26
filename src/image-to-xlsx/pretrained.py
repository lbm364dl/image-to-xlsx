from paddlex import create_pipeline
from surya.settings import settings
from surya.model.table_rec.model import load_model as load_model
from surya.model.table_rec.processor import load_processor
from surya.model.detection.model import (
    load_model as load_det_model,
    load_processor as load_det_processor,
)

model = load_model()
processor = load_processor()
layout_model = load_det_model(checkpoint=settings.LAYOUT_MODEL_CHECKPOINT)
layout_processor = load_det_processor(checkpoint=settings.LAYOUT_MODEL_CHECKPOINT)
det_model = load_det_model()
det_processor = load_det_processor()
ocr_pipeline = create_pipeline(pipeline="OCR")
