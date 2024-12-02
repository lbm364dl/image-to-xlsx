import numpy as np
import pretrained
from table import Table
from unskewing import correct_skew
from binarization import binarize
from PIL import Image
from surya.detection import batch_text_detection
from surya.layout import batch_layout_detection
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE


class Page:
    def __init__(
        self,
        image,
        page_num,
        document,
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
        self.document = document
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
        if self.document.use_pdf_text:
            return self.image.find_tables(strategy="text").tables
        else:
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
        text_language="en",
        show_detected_boxes=False,
    ):
        tables = self.detect_tables()

        for i, table in enumerate(tables):
            table_output = None
            t = Table(
                self.image,
                self,
                table.bbox,
                self.model,
                self.processor,
                self.det_model,
                self.det_processor,
                self.ocr_pipeline,
            )
            if self.document.use_pdf_text:
                table_output = table.extract()
                for i, row in enumerate(table_output):
                    for j, col in enumerate(row):
                        table_output[i][j] = ILLEGAL_CHARACTERS_RE.sub(r"", col)
                t.table_output = table_output
            else:
                t.recognize_structure(heuristic_thresh)
                t.build_table(img_pad, compute_prefix, show_cropped_bboxes)

                if show_detected_boxes:
                    t.visualize_table_bboxes()

            if nlp_postprocess:
                t.nlp_postprocess(text_language)

            sheet = self.document.workbook.create_sheet(
                f"page_{self.page_num}_table_{i + 1}"
            )
            for row in t.table_output:
                sheet.append(row)

    def process_page(
        self,
        unskew=False,
        binarize=False,
        nlp_postprocess=False,
        text_language="en",
        show_detected_boxes=False,
    ):
        if self.document.use_pdf_text:
            self.recognize_tables_structure(
                nlp_postprocess=nlp_postprocess,
                text_language=text_language,
                show_detected_boxes=show_detected_boxes,
            )
        else:
            self.image.show()
            if unskew:
                self.rotate(delta=0.05, limit=5)
            self.image.show()

            if binarize:
                self.binarize(method="otsu", block_size=31, constant=10)
                self.image.show()

            self.recognize_tables_structure(
                heuristic_thresh=0.6,
                img_pad=100,
                compute_prefix=50,
                nlp_postprocess=nlp_postprocess,
                text_language=text_language,
                show_detected_boxes=show_detected_boxes,
            )
