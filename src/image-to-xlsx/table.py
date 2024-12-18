import os
import numpy as np
import cv2
import pretrained
import re
from utils import split_footnotes
from collections import defaultdict
from definitions import OUTPUT_PATH
from PIL import Image
from surya.detection import batch_text_detection
from surya.tables import batch_table_recognition
from surya.input.pdflines import get_table_blocks
from tabled.assignment import assign_rows_columns
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import PatternFill, Border, Side
from openpyxl.comments import Comment


class Table:
    def __init__(
        self,
        whole_image,
        text_lines,
        page,
        table_bbox,
        model=None,
        processor=None,
        det_model=None,
        det_processor=None,
        ocr_pipeline=None,
    ):
        self.page = page

        if not page.document.method == "pdf-text":
            self.text_lines = text_lines
            self.image = whole_image
            self.cropped_img = self.image.crop(table_bbox)
            self.table_bbox = table_bbox
            self.model = model or pretrained.model
            self.processor = processor or pretrained.processor
            self.det_model = det_model or pretrained.det_model
            self.det_processor = det_processor or pretrained.det_processor
            self.pipeline = ocr_pipeline or pretrained.ocr_pipeline

    def reject_large_bboxes(self, bboxes, thresh=30):
        return [tb for tb in bboxes if tb.bbox[3] - tb.bbox[1] <= thresh]

    def recognize_structure(self, heuristic_thresh=0.8):
        if self.text_lines:
            [table_blocks] = (
                get_table_blocks([self.table_bbox], self.text_lines, self.image.size)
                if self.text_lines is not None
                else []
            )
        else:
            table_blocks = []

        [det_result] = batch_text_detection(
            [self.cropped_img], self.det_model, self.det_processor
        )
        self.det_result = det_result
        det_result.bboxes = self.reject_large_bboxes(det_result.bboxes)

        if table_blocks:
            cell_bboxes = table_blocks
        else:
            cell_bboxes = [{"bbox": tb.bbox, "text": ""} for tb in det_result.bboxes]

        self.table = {
            "bbox": self.table_bbox,
            "img": self.cropped_img,
            "bboxes": cell_bboxes,
        }

        [table_pred] = batch_table_recognition(
            [self.cropped_img], [cell_bboxes], self.model, self.processor
        )

        self.table["cells"] = assign_rows_columns(
            table_pred, self.table["img"].size, heuristic_thresh
        )

    def is_numeric_cell(self, text, threshold=0.6):
        numeric = sum("0" <= c <= "9" for c in text)
        return numeric >= threshold * len(text)

    def get_cropped_cell_images(self, image_pad, compute_prefix, show_cropped_bboxes):
        cropped_imgs = []
        for cell in self.table["cells"][:compute_prefix]:
            cropped_img = np.array(self.table["img"].crop(cell.bbox))
            cropped_img = np.pad(
                cropped_img,
                ((image_pad, image_pad), (image_pad, image_pad), (0, 0)),
                mode="constant",
                constant_values=255,
            )
            if show_cropped_bboxes:
                Image.fromarray(cropped_img).show()
            cropped_imgs.append(cropped_img)

        return cropped_imgs

    def recognize_texts(self, image_pad, compute_prefix, show_cropped_bboxes):
        self.table_data = defaultdict(lambda: defaultdict(list))

        if self.text_lines:
            for cell in self.table["cells"]:
                row_ids, col_ids = cell.row_ids, cell.col_ids
                row_id, col_id = row_ids[0], col_ids[0]
                add_text = cell.text
                add_text = self.maybe_clean_numeric_cell(
                    ILLEGAL_CHARACTERS_RE.sub(r"", add_text)
                )
                if add_text:
                    self.table_data[row_id][col_id].append({
                        "text": add_text,
                        "confidence": None,
                    })
        else:
            cropped_imgs = self.get_cropped_cell_images(
                image_pad, compute_prefix, show_cropped_bboxes
            )
            output = self.pipeline.predict(cropped_imgs)

            for cell, pred in zip(self.table["cells"], output):
                row_ids, col_ids = cell.row_ids, cell.col_ids
                row_id, col_id = row_ids[0], col_ids[0]
                # print("pred", pred)
                # add_text = " ".join(pred["rec_text"])
                # add_text = self.maybe_clean_numeric_cell(add_text)

                # if add_text:
                self.table_data[row_id][col_id] += [
                    {"text": text, "confidence": confidence}
                    for text, confidence in zip(pred["rec_text"], pred["rec_score"])
                ]

    def set_table_from_pdf_text(self, table):
        self.table_data = defaultdict(dict)
        for i, row in enumerate(table.extract()):
            for j, col in enumerate(row):
                self.table_data[i][j] = [{"text": col, "confidence": None}]

    def set_table_from_textract_pickle(self, textract_table, id_to_block):
        # TODO: Check merged cells
        table_cells = [
            id_to_block[id]
            for relationship in textract_table.get("Relationships", [])
            for id in relationship["Ids"]
            if id_to_block[id]["BlockType"] == "CELL"
        ]

        self.table_data = defaultdict(lambda: defaultdict(list))
        for cell in table_cells:
            words = [
                id_to_block[id]
                for relationship in cell.get("Relationships", [])
                for id in relationship["Ids"]
                if id_to_block[id]["BlockType"] == "WORD"
            ]
            row, col = cell["RowIndex"], cell["ColumnIndex"]
            self.table_data[row - 1][col - 1] = [
                {"text": word["Text"], "confidence": word["Confidence"]}
                for word in words
            ]

    def add_to_sheet(self, sheet_name, table_matrix):
        thin_white_border = Border(
            left=Side(style="thin", color="FFFFFF"),
            right=Side(style="thin", color="FFFFFF"),
            top=Side(style="thin", color="FFFFFF"),
            bottom=Side(style="thin", color="FFFFFF"),
        )

        sheet = self.page.document.workbook.create_sheet(sheet_name)

        for i, row in enumerate(table_matrix, 1):
            for j, col in enumerate(row, 1):
                cell = sheet.cell(row=i, column=j, value=col["text"])
                cell_color = self.get_cell_color(col["confidence"])
                if cell_color:
                    cell.fill = PatternFill(start_color=cell_color, fill_type="solid")
                    cell.border = thin_white_border
                    if col["footnotes"]:
                        cell.comment = Comment(",".join(col["footnotes"]), "automatic")

    def get_cell_color(self, confidence):
        if not confidence:
            return None

        color_scale = [
            (95, "00C957"),  # Emerald Green
            (90, "00FF7F"),  # Spring Green
            (85, "C0FF00"),  # Yellow-Green
            (80, "FFFF00"),  # Yellow
            (70, "FFC000"),  # Light Orange
            (60, "FF8000"),  # Orange
            (50, "FF4000"),  # Orange-Red
            (40, "FF2000"),  # Deep Orange-Red
            (0, "FF0000"),  # Bright Red
        ]

        for threshold, color in color_scale:
            if confidence >= threshold:
                return color

        return "FF0000"

    def maybe_clean_numeric_cell(self, text):
        if self.is_numeric_cell(text):
            text = text.replace(".", "").replace(",", "")
            fixed_decimal_places = self.page.document.fixed_decimal_places
            if text and fixed_decimal_places > 0:
                text = text[:-fixed_decimal_places] + "." + text[-fixed_decimal_places:]
            return text
        else:
            return text

    def extend_rows(self):
        split_table = []
        for row in self.table_data.values():
            rows = []
            for j, col in row.items():
                for i, part in enumerate(col):
                    if len(rows) <= i:
                        rows.append(defaultdict(list))
                    rows[i][j].append(part)
                    assert len(rows[i][j]) == 1

            split_table += rows

        self.table_data = defaultdict(
            lambda: defaultdict(list), {i: row for i, row in enumerate(split_table)}
        )

    def join_cells_content(self, table_data):
        for i, row in enumerate(table_data):
            for j, col in enumerate(row):
                table_data[i][j] = " ".join(col)

        return table_data

    def join_cell_parts(self, cell):
        texts = [cell_part["text"] for cell_part in cell]
        conf_arr = np.array([
            cell_part["confidence"] for cell_part in cell if cell_part["confidence"]
        ])
        confidence = conf_arr.mean()
        return {
            "text": " ".join(texts),
            "confidence": confidence if not np.isnan(confidence) else None,
        }

    def clean_cell_text(self, cell_text):
        cell_text = ILLEGAL_CHARACTERS_RE.sub(r"", cell_text)
        if self.is_numeric_cell(cell_text):
            cell_text = cell_text.replace(".", "").replace(",", "")
            fixed_decimal_places = self.page.document.fixed_decimal_places
            if cell_text and fixed_decimal_places > 0:
                cell_text = (
                    cell_text[:-fixed_decimal_places]
                    + "."
                    + cell_text[-fixed_decimal_places:]
                )

        return cell_text

    def remove_low_content_rows(self, table_data):
        total_row_lengths = sum(len("".join(row)) for row in table_data)
        mean_row_length = (
            total_row_lengths / len(table_data) if len(table_data) > 0 else 0
        )
        return [row for row in table_data if len("".join(row)) / mean_row_length > 0.1]

    def as_clean_matrix(self):
        n = max([i + 1 for i in self.table_data.keys()], default=0)
        m = max(
            [j + 1 for cols in self.table_data.values() for j in cols.keys()], default=0
        )
        table_data = [
            [{"text": "", "confidence": None, "footnotes": []} for _ in range(m)]
            for _ in range(n)
        ]

        for row, cols in self.table_data.items():
            for col, cell in cols.items():
                cell = self.join_cell_parts(cell)
                cell["text"] = self.clean_cell_text(cell["text"])
                cell["text"], cell["footnotes"] = split_footnotes(cell["text"])
                if cell["footnotes"]:
                    print("cell with footnotes", cell)
                table_data[row][col] = cell

        return table_data

    def maybe_parse_numeric_cells(self, table_matrix):
        for i, row in enumerate(table_matrix):
            for j, col in enumerate(row):
                table_matrix[i][j]["text"], forced_numeric = (
                    self.maybe_parse_numeric_cell(col["text"])
                )
                # Override confidence so that someone has to review just in case
                if forced_numeric:
                    table_matrix[i][j]["confidence"] = 0.0

        return table_matrix

    def maybe_parse_numeric_cell(self, text):
        if self.is_numeric_cell(text):
            try:
                num = int(text)
                return num, False
            except ValueError:
                only_numeric = re.sub(r"\D", "", text)
                if only_numeric:
                    return int(only_numeric), True
                else:
                    return "", False
        else:
            return text, False

    def set_table_from_surya_paddle(
        self,
        image_pad=100,
        heuristic_thresh=0.8,
        compute_prefix=10**9,
        show_cropped_bboxes=False,
        show_detected_boxes=False,
    ):
        self.recognize_structure(heuristic_thresh)

        if show_detected_boxes:
            self.visualize_table_bboxes()

        self.recognize_texts(image_pad, compute_prefix, show_cropped_bboxes)
        # self.table_data = self.remove_low_content_rows(table_data)

    def nlp_postprocess(
        self, table_matrix, text_language="en", nlp_postprocess_prompt_file=None
    ):
        from postprocessing import nlp_clean

        return nlp_clean(table_matrix, text_language, nlp_postprocess_prompt_file)

    def save_as_csv(self, output_path):
        with open(output_path, "w", encoding="utf-8") as f_out:
            output = "\n".join([";".join(row) for row in self.table_data])
            f_out.write(output)

    def visualize_bboxes(self, img, bboxes):
        visualize_img = np.array(img, dtype=np.uint8)
        h, w, _ = visualize_img.shape
        bboxes = np.array(bboxes, dtype=np.int32)
        for [x1, y1, x2, y2] in bboxes:
            [x1, x2] = [min(max(0, x), w) for x in [x1, x2]]
            [y1, y2] = [min(max(0, y), h) for y in [y1, y2]]
            cv2.rectangle(
                visualize_img, (x1, y1), (x2, y2), color=(255, 0, 0), thickness=1
            )

        Image.fromarray(visualize_img).show()

    def visualize_table_bboxes(self):
        self.visualize_bboxes(
            self.table["img"], [c["bbox"] for c in self.table["bboxes"]]
        )
