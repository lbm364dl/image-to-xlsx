import os

# Workaround: PaddlePaddle's default auto_growth GPU allocator can enter
# an infinite ioctl loop on some driver/GPU combos (e.g. RTX A2000, driver 580).
# Must be set before importing paddle anywhere.
os.environ.setdefault("FLAGS_allocator_strategy", "naive_best_fit")

import numpy as np
import pickle
import io
import time
from definitions import MAX_TEXTRACT_SYNC_SIZE, ONE_MB
from table import Table
from unskewing import correct_skew
from binarization import binarize
from PIL import Image
from utils import image_below_size, maybe_reduce_resolution, get_aws_credentials

# Cached PaddleOCR-VL pipeline (loaded once, reused across pages)
_paddleocr_vl_pipeline = None
# Cached standalone OCR engine for confidence scoring
_paddleocr_ocr_engine = None
# Last dewarped page image (stored so it can be included in the results zip)
_last_dewarped_image = None


def clear_gpu_memory():
    """Release all cached GPU models/pipelines and free GPU memory."""
    import gc

    # Clear cached PaddleOCR-VL pipeline
    global _paddleocr_vl_pipeline
    _paddleocr_vl_pipeline = None

    # Clear cached OCR engine
    global _paddleocr_ocr_engine
    _paddleocr_ocr_engine = None

    # Clear dewarped image reference
    global _last_dewarped_image
    _last_dewarped_image = None

    # Clear cached surya predictors
    try:
        import pretrained
        pretrained.clear_all_models()
    except ImportError:
        pass

        # Clear dewarping model cache
        try:
            from dewarping.dewarp import clear_model_cache
            clear_model_cache()
        except ImportError:
            pass
            torch.cuda.empty_cache()
    except ImportError:
        pass

    try:
        import paddle
        paddle.device.cuda.empty_cache()
    except (ImportError, Exception):
        pass


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

    def dewarp(self):
        """Dewarp the page image using GeoTr (doc-matcher)."""
        from dewarping import dewarp_image as _dewarp
        global _last_dewarped_image
        self.page = _dewarp(self.page)
        _last_dewarped_image = self.page.copy()

    @staticmethod
    def get_last_dewarped_image():
        """Return the most recently dewarped image (or None)."""
        return _last_dewarped_image

    @staticmethod
    def reset_last_dewarped_image():
        global _last_dewarped_image
        _last_dewarped_image = None

    def rotate(self, delta=0.5, limit=5, custom_angle=None):
        _, corrected = correct_skew(np.array(self.page), delta, limit, custom_angle)
        self.page = Image.fromarray(corrected)

    def binarize(self, method="otsu", block_size=None, constant=None):
        self.page = binarize(self.page, method, block_size, constant)

    def detect_tables(self):
        import pretrained

        lp = pretrained.layout_predictor()
        layout_predictions = lp([self.page])
        layout_prediction = layout_predictions[0]

        return [bbox for bbox in layout_prediction.bboxes if bbox.label == "Table"]

    def process_page(self, **kwargs):
        get_page_tables_method = {
            "surya": self.get_page_tables_surya,
            "pdf-text": self.get_page_tables_with_pdf_text,
            "textract": self.get_page_tables_textract,
            "textract-pickle-debug": self.get_page_tables_textract_pickle,
            "paddleocr-vl": self.get_page_tables_paddleocr_vl,
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
                kwargs.get("fix_num_misspellings"),
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
                kwargs.get("fix_num_misspellings"),
            )

            table.add_to_sheet(self.page_num, i + 1, table_matrix, table.footer_text)

    def get_page_tables_surya(self, **kwargs):
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
            )

            t.set_table_from_surya(
                image_pad=kwargs.get("image_pad"),
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
        import boto3

        self.page = self.page.convert("RGB")
        self.page = maybe_reduce_resolution(self.page)
        self.page = image_below_size(self.page, ONE_MB)
        textract = boto3.client("textract", **get_aws_credentials())
        img_byte_arr = io.BytesIO()
        self.page.save(img_byte_arr, format="JPEG")
        img_byte_arr = img_byte_arr.getvalue()

        # Analyze file directly (small enough after auto resize below 1MB)
        assert len(img_byte_arr) <= MAX_TEXTRACT_SYNC_SIZE

        return textract.analyze_document(
            Document={"Bytes": img_byte_arr},
            FeatureTypes=["TABLES"],
        )

    @staticmethod
    def _run_ocr_for_confidence(image):
        """Run standalone PP-OCRv5 OCR on an image and return word-level results.

        Returns a list of dicts sorted in reading order (top→bottom, left→right):
            [{"text": str, "bbox": [x1,y1,x2,y2], "confidence": float}, ...]
        """
        from paddleocr import PaddleOCR

        global _paddleocr_ocr_engine
        if _paddleocr_ocr_engine is None:
            _paddleocr_ocr_engine = PaddleOCR(lang="en")
        engine = _paddleocr_ocr_engine

        result = engine.predict(np.array(image))
        if not result:
            return []

        res_json = result[0].json["res"]
        rec_texts = res_json.get("rec_texts", [])
        rec_scores = res_json.get("rec_scores", [])
        rec_boxes = res_json.get("rec_boxes", [])

        words = []
        for text, score, bbox in zip(rec_texts, rec_scores, rec_boxes):
            # bbox is [x1, y1, x2, y2]
            words.append({
                "text": text.strip(),
                "bbox": bbox,
                "confidence": score * 100,  # normalise to 0-100 scale
            })

        # Sort in reading order: top-to-bottom, then left-to-right
        words.sort(key=lambda w: (w["bbox"][1], w["bbox"][0]))
        return words

    def get_page_tables_paddleocr_vl(self, **kwargs):
        import tempfile
        from paddleocr import PaddleOCRVL

        os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

        device = kwargs.get("paddleocr_vl_device")
        if device is None:
            import paddle
            device = "gpu:0" if paddle.device.cuda.device_count() > 0 else "cpu"

        global _paddleocr_vl_pipeline
        if _paddleocr_vl_pipeline is None:
            _paddleocr_vl_pipeline = PaddleOCRVL(device=device)
        pipeline = _paddleocr_vl_pipeline

        # Save the page image to a temp file for PaddleOCR-VL input
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
            if isinstance(self.page, Image.Image):
                self.page.save(tmp_path)
            else:
                Image.fromarray(np.array(self.page)).save(tmp_path)

        try:
            output = pipeline.predict(tmp_path)
            tables = []
            for res in output:
                res_json = res.json["res"]
                parsing_res_list = res_json.get("parsing_res_list", [])
                for block in parsing_res_list:
                    if block.get("block_label") == "table":
                        markdown_content = block.get("block_content", "")
                        if not markdown_content.strip():
                            continue
                        bbox = block.get("block_bbox", [0, 0, 0, 0])
                        if hasattr(bbox, "tolist"):
                            bbox = bbox.tolist()
                        t = Table(self.page, self, bbox)
                        t.set_table_from_paddleocr_vl_markdown(markdown_content)
                        tables.append(t)

            # Optionally enrich cells with OCR confidence scores
            if kwargs.get("use_ocr_confidence") and tables:
                ocr_words = self._run_ocr_for_confidence(self.page)
                for t in tables:
                    t.enrich_with_ocr_confidence(ocr_words)

            return tables
        finally:
            os.unlink(tmp_path)

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
