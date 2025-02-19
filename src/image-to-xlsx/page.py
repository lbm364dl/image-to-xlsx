import numpy as np
import pretrained
import pickle
import io
import boto3
import time
from definitions import MAX_TEXTRACT_SYNC_SIZE
from table import Table
from unskewing import correct_skew
from binarization import binarize
from PIL import Image
from surya.detection import batch_text_detection
from surya.layout import batch_layout_detection
from utils import maybe_reduce_resolution, get_aws_credentials


class Page:
    def __init__(
        self,
        page,
        page_num,
        document,
    ):
        self.page = page
        self.page_num = page_num
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

    def rotate(self, delta=0.5, limit=5, custom_angle=None):
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
            "textract": self.get_page_tables_textract,
            "textract-pickle-debug": self.get_page_tables_textract_pickle,
        }

        tables = get_page_tables_method[self.document.method](**kwargs)

        for i, table in enumerate(tables):
            if kwargs.get("extend_rows"):
                table.extend_rows()

            table_matrix = table.as_clean_matrix(kwargs.get("remove_dots_and_commas"))
            table_matrix = table.overwrite_seminumeric_cells_confidence(
                table_matrix,
                kwargs.get("decimal_separator"),
                kwargs.get("thousands_separator"),
            )

            if kwargs.get("nlp_postprocess"):
                table_matrix = table.nlp_postprocess(
                    table_matrix,
                    kwargs.get("text_language"),
                    kwargs.get("nlp_postprocess_prompt_file"),
                )

            table_matrix = table.maybe_parse_numeric_cells(
                table_matrix,
                kwargs.get("decimal_separator"),
                kwargs.get("thousands_separator"),
            )

            table.add_to_sheet(self.page_num, i + 1, table_matrix, table.footer_text)

    def get_page_tables_surya_plus_paddle(self, **kwargs):
        self.set_models(**pretrained.all_models())

        if kwargs.get("unskew"):
            self.rotate(delta=0.5, limit=5)

        if kwargs.get("binarize"):
            self.binarize(method="otsu", block_size=31, constant=10)

        tables = []
        for table in self.detect_tables():
            t = Table(
                self.page,
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
                self,
                table.bbox,
            )
            t.set_table_from_pdf_text(table)
            tables.append(t)

        return tables

    def get_page_tables_textract(self, **kwargs):
        if kwargs.get("unskew"):
            self.rotate(delta=0.5, limit=5)

        if kwargs.get("binarize"):
            self.binarize(method="otsu", block_size=31, constant=10)

        response = self.get_textract_response()
        return self.build_textract_tables_from_response(response)

    def get_page_tables_textract_pickle(self, **kwargs):
        with open(kwargs.get("textract_response_pickle_file"), "rb") as f:
            response = pickle.load(f)

        return self.build_textract_tables_from_response(response)

    def get_textract_response(self):
        self.page = maybe_reduce_resolution(self.page)
        textract = boto3.client("textract", **get_aws_credentials())
        img_byte_arr = io.BytesIO()
        self.page.save(img_byte_arr, format="PNG")
        img_byte_arr = img_byte_arr.getvalue()

        # Analyze file directly (small enough)
        if len(img_byte_arr) <= MAX_TEXTRACT_SYNC_SIZE:
            return textract.analyze_document(
                Document={"Bytes": img_byte_arr},
                FeatureTypes=["TABLES"],
            )
        # Too large, first upload to S3 and run asynchronous textract
        else:
            # Upload the document to S3
            bucket_name = "test-textract-large-files"
            file_name = "tmp_extract_page"
            s3 = boto3.client("s3", **get_aws_credentials())
            s3.put_object(Bucket=bucket_name, Key=file_name, Body=img_byte_arr)

            # Call Textract to analyze the document
            response = textract.start_document_analysis(
                DocumentLocation={
                    "S3Object": {"Bucket": bucket_name, "Name": file_name}
                },
                FeatureTypes=["TABLES"],  # Extract tables and forms; omit for raw text
            )

            job_id = response["JobId"]

            # Poll for job completion
            while True:
                response = textract.get_document_analysis(JobId=job_id)
                status = response["JobStatus"]
                if status in ["SUCCEEDED", "FAILED"]:
                    break
                time.sleep(5)

            # Delete the file from S3 after processing
            s3.delete_object(Bucket=bucket_name, Key=file_name)
            print(f"Deleted {file_name} from bucket {bucket_name}")

            return response

    def build_textract_tables_from_response(self, response):
        blocks = response["Blocks"]
        file_tables = [block for block in blocks if block["BlockType"] == "TABLE"]
        id_to_block = {block["Id"]: block for block in blocks}

        tables = []
        for table in file_tables:
            bbox = self.get_textract_table_bbox(table)
            t = Table(self.page, self, bbox)
            t.set_table_from_textract_pickle(table, id_to_block)
            tables.append(t)

        return tables

    def get_textract_table_bbox(self, table):
        bbox = table["Geometry"]["BoundingBox"]
        y, x = self.to_int(self.page, bbox["Top"], bbox["Left"])
        height, width = self.to_int(self.page, bbox["Height"], bbox["Width"])
        return [x, y, x + width, y + height]

    def to_int(self, img, y, x):
        w, h = img.size
        return int(y * h), int(x * w)
