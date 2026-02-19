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
# Cached GLM-OCR parser (loaded once, reused across pages)
_glm_ocr_parser = None
# Last dewarped page image (stored so it can be included in the results zip)
_last_dewarped_image = None


def clear_gpu_memory():
    """Release all cached GPU models/pipelines and free GPU memory."""
    import gc

    # Clear cached PaddleOCR-VL pipeline
    global _paddleocr_vl_pipeline
    _paddleocr_vl_pipeline = None

    # Clear cached GLM-OCR parser
    global _glm_ocr_parser
    if _glm_ocr_parser is not None:
        try:
            _glm_ocr_parser.close()
        except Exception:
            pass
        _glm_ocr_parser = None

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
            "glm-ocr": self.get_page_tables_glm_ocr,
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

            return tables
        finally:
            os.unlink(tmp_path)

    def get_page_tables_glm_ocr(self, **kwargs):
        """Extract tables using the GLM-OCR SDK with local pipeline.

        Requires a running GLM-OCR inference server (vLLM, SGLang, or Ollama).
        The SDK handles layout detection (PP-DocLayout-V3) locally and sends
        cropped regions to the OCR server for recognition.
        """
        import tempfile
        import json
        import yaml
        from glmocr import GlmOcr

        api_host = kwargs.get("glm_ocr_host", "localhost")
        api_port = int(kwargs.get("glm_ocr_port", 8081))
        api_key = kwargs.get("glm_ocr_api_key") or None
        model_name = kwargs.get("glm_ocr_model", "glm-ocr")

        global _glm_ocr_parser
        if _glm_ocr_parser is None:
            # Create a temporary config YAML for the SDK
            ocr_api_config = {
                "api_host": api_host,
                "api_port": api_port,
                "connect_timeout": 300,
                "request_timeout": 300,
                # Set model name explicitly — OCRApiConfig has a duplicate 'model'
                # field definition which confuses Pydantic; setting it at YAML-load
                # time ensures it is passed in every request body.
                "model": model_name or "zai-org/GLM-OCR",
            }
            if api_key:
                ocr_api_config["api_key"] = api_key
            config = {
                "pipeline": {
                    "maas": {"enabled": False},
                    "ocr_api": ocr_api_config,
                    "enable_layout": False,
                },
            }

            fd, config_path = tempfile.mkstemp(suffix=".yaml")
            try:
                with os.fdopen(fd, "w") as f:
                    yaml.dump(config, f)
                _glm_ocr_parser = GlmOcr(config_path=config_path)
            finally:
                try:
                    os.unlink(config_path)
                except OSError:
                    pass

        # Save page image to a temp file
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
            if isinstance(self.page, Image.Image):
                self.page.save(tmp_path)
            else:
                Image.fromarray(np.array(self.page)).save(tmp_path)

        try:
            result = _glm_ocr_parser.parse(tmp_path, save_layout_visualization=False)

            # --- DEBUG: inspect raw API response ---
            print("[GLM-OCR DEBUG] json_result type:", type(result.json_result))
            print("[GLM-OCR DEBUG] json_result repr:", repr(result.json_result)[:500])
            print("[GLM-OCR DEBUG] markdown_result:", repr(result.markdown_result)[:500])
            # --- END DEBUG ---

            tables = []

            # Extract tables from structured JSON result (layout detection mode)
            json_result = result.json_result
            if isinstance(json_result, str):
                try:
                    json_result = json.loads(json_result)
                except (json.JSONDecodeError, TypeError):
                    json_result = []

            if isinstance(json_result, list):
                for page_data in json_result:
                    if not isinstance(page_data, list):
                        continue
                    for block in page_data:
                        if not isinstance(block, dict):
                            continue
                        content = block.get("content", "")
                        label = block.get("label", "")
                        # With enable_layout=False the model labels everything as
                        # 'text'. Detect tables by checking for HTML/markdown table
                        # markup in the content regardless of label.
                        is_table = label == "table" or (
                            content and (
                                "<table" in content.lower()
                                or (content.count("|") > 2 and "\n" in content)
                            )
                        )
                        if not is_table or not content.strip():
                            continue
                        bbox = block.get("bbox_2d") or [0, 0, 0, 0]
                        if hasattr(bbox, "tolist"):
                            bbox = bbox.tolist()
                        t = Table(self.page, self, bbox)
                        t.set_table_from_paddleocr_vl_markdown(content)
                        if t.table_data:
                            tables.append(t)

            # Fallback: parse tables from the markdown result
            if not tables and result.markdown_result:
                tables = self._extract_tables_from_markdown(result.markdown_result)

            print("[GLM-OCR DEBUG] tables found:", len(tables))
            return tables
        finally:
            os.unlink(tmp_path)

    def _extract_tables_from_markdown(self, markdown_content):
        """Parse markdown content and extract all table blocks as Table objects."""
        import re

        tables = []
        # Match HTML tables
        html_table_pattern = re.compile(
            r"<table[^>]*>.*?</table>", re.DOTALL | re.IGNORECASE
        )
        # Match markdown pipe tables (at least 2 rows with pipes)
        md_table_pattern = re.compile(
            r"(?:^|\n)"
            r"((?:\|[^\n]+\|\s*\n){2,})",
            re.MULTILINE,
        )

        found_tables = []

        # Find HTML tables
        for match in html_table_pattern.finditer(markdown_content):
            found_tables.append(match.group(0))

        # Find markdown pipe tables (only in non-HTML parts)
        remaining = html_table_pattern.sub("", markdown_content)
        for match in md_table_pattern.finditer(remaining):
            table_text = match.group(1).strip()
            if table_text:
                found_tables.append(table_text)

        for table_text in found_tables:
            bbox = [0, 0, 0, 0]
            t = Table(self.page, self, bbox)
            t.set_table_from_paddleocr_vl_markdown(table_text)
            # Only add if the table has actual data
            if t.table_data and len(t.table_data) > 0:
                tables.append(t)

        return tables

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
