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
        page,
        page_num,
        text_lines,
        document,
    ):
        self.page = page
        self.page_num = page_num
        self.text_lines = text_lines
        self.document = document
        self.model = None
        self.processor = None
        self.det_model = None
        self.det_processor = None
        self.layout_model = None
        self.layout_processor = None
        self.ocr_pipeline = None

    def set_models(
        self,
        model=None,
        processor=None,
        det_model=None,
        det_processor=None,
        layout_model=None,
        layout_processor=None,
        ocr_pipeline=None,
    ):
        self.model = model or pretrained.model()
        self.processor = processor or pretrained.processor()
        self.det_model = det_model or pretrained.det_model()
        self.det_processor = det_processor or pretrained.det_processor()
        self.layout_model = layout_model or pretrained.layout_model()
        self.layout_processor = layout_processor or pretrained.layout_processor()
        self.ocr_pipeline = ocr_pipeline or pretrained.ocr_pipeline()

    def rotate(self, delta=0.05, limit=5, custom_angle=None):
        _, corrected = correct_skew(np.array(self.page), delta, limit, custom_angle)
        self.page = Image.fromarray(corrected)

    def binarize(self, method="otsu", block_size=None, constant=None):
        self.page = binarize(self.page, method, block_size, constant)

    def detect_tables(self):
        [line_prediction] = batch_text_detection(
            [self.page], self.det_model, self.det_processor
        )
        [layout_prediction] = batch_layout_detection(
            [self.page],
            self.layout_model,
            self.layout_processor,
            [line_prediction],
        )

        return [bbox for bbox in layout_prediction.bboxes if bbox.label == "Table"]

    def process_page(self, **kwargs):
        get_page_tables_method = {
            "surya+paddle": self.get_page_tables_surya_plus_paddle,
            "pdf-text": self.get_page_tables_with_pdf_text,
        }

        tables = get_page_tables_method[self.document.method](**kwargs)

        for i, table in enumerate(tables):
            if kwargs.get("extend_rows"):
                table.extend_rows()

            sheet = self.document.workbook.create_sheet(
                f"page_{self.page_num}_table_{i + 1}"
            )
            print("my_table_data", table.table_data)
            table_matrix = table.as_clean_matrix()
            print("my_table_matrix", table_matrix[:5])
            if kwargs.get("nlp_postprocess"):
                table_matrix = table.nlp_postprocess(
                    table_matrix,
                    kwargs.get("text_language"),
                    kwargs.get("nlp_postprocess_prompt_file"),
                )
                print("my_table_matrix_after_nlp", table_matrix[:5])

            for row in table_matrix:
                sheet.append([cell["text"] for cell in row])

    def get_page_tables_surya_plus_paddle(self, **kwargs):
        self.set_models(**pretrained.all_models())

        if kwargs.get("unskew"):
            self.rotate(delta=0.05, limit=5)

        if kwargs.get("binarize"):
            self.binarize(method="otsu", block_size=31, constant=10)

        tables = []
        for table in self.detect_tables():
            t = Table(
                self.page,
                self.text_lines,
                self,
                table.bbox,
                self.model,
                self.processor,
                self.det_model,
                self.det_processor,
                self.ocr_pipeline,
            )

            t.set_table_from_surya_paddle(
                image_pad=kwargs.get("image_pad"),
                heuristic_thresh=kwargs.get("heuristic_thresh"),
                compute_prefix=kwargs.get("compute_prefix"),
                show_cropped_bboxes=kwargs.get("show_cropped_bboxes"),
                show_detected_boxes=kwargs.get("show_detected_boxes"),
            )
            tables.append(t)

        return tables

    def get_page_tables_with_pdf_text(self, **kwargs):
        tables = []
        for table in self.page.find_tables(strategy="text").tables:
            t = Table(
                self.page,
                self.text_lines,
                self,
                table.bbox,
            )
            t.set_table_from_pdf_text(table)
            tables.append(t)

        return tables
