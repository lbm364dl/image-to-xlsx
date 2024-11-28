import numpy as np
import pretrained
from table import Table
from unskewing import correct_skew
from binarization import binarize
from PIL import Image
from surya.detection import batch_text_detection
from surya.layout import batch_layout_detection


class Page:
    def __init__(
        self,
        image,
        page_num,
        model=None,
        processor=None,
        det_model=None,
        det_processor=None,
        layout_model=None,
        layout_processor=None,
        ocr_pipeline=None,
    ):
        self.image = image
        self.page_num = page_num
        self.model = model or pretrained.model()
        self.processor = processor or pretrained.processor()
        self.det_model = det_model or pretrained.det_model()
        self.det_processor = det_processor or pretrained.det_processor()
        self.layout_model = layout_model or pretrained.layout_model()
        self.layout_processor = layout_processor or pretrained.layout_processor()
        self.ocr_pipeline = ocr_pipeline or pretrained.ocr_pipeline()

    def rotate(self, delta=0.05, limit=5, custom_angle=None):
        _, corrected = correct_skew(np.array(self.image), delta, limit, custom_angle)
        self.image = Image.fromarray(corrected)

    def binarize(self, method="otsu", block_size=None, constant=None):
        self.image = binarize(self.image, method, block_size, constant)

    def detect_tables(self):
        [line_prediction] = batch_text_detection(
            [self.image], self.det_model, self.det_processor
        )
        [layout_prediction] = batch_layout_detection(
            [self.image],
            self.layout_model,
            self.layout_processor,
            [line_prediction],
        )

        return [bbox for bbox in layout_prediction.bboxes if bbox.label == "Table"]

    def recognize_tables_structure(
        self,
        heuristic_thresh=0.6,
        img_pad=100,
        compute_prefix=50,
        show_cropped_bboxes=False,
        nlp_postprocess=False,
    ):
        tables = self.detect_tables()

        for i, table in enumerate(tables):
            t = Table(
                self.image,
                table.bbox,
                self.model,
                self.processor,
                self.det_model,
                self.det_processor,
                self.ocr_pipeline,
            )
            t.recognize_structure(heuristic_thresh)
            t.build_table(img_pad, compute_prefix, show_cropped_bboxes)
            t.visualize_table_bboxes()

            if nlp_postprocess:
                t.nlp_postprocess()

            t.save_as_csv(f"page_{self.page_num}_table_{i + 1}.csv")
