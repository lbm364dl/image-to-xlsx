import numpy as np
import cv2
import pretrained
import re
from utils import split_footnotes, get_cell_color
from collections import defaultdict
from definitions import (
    MISSPELLINGS,
    MISSPELLINGS_REGEX,
    NOT_NUMBER,
    ONE_NUMBER,
    AT_LEAST_TWO_NUMBERS,
)
from PIL import Image
from surya.detection import batch_text_detection
from surya.tables import batch_table_recognition
from tabled.assignment import assign_rows_columns
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import PatternFill, Border, Side
from openpyxl.comments import Comment


class Table:
    def __init__(
        self,
        whole_image,
        page,
        table_bbox,
        model=None,
        processor=None,
        det_model=None,
        det_processor=None,
        ocr_pipeline=None,
    ):
        self.page = page
        self.footer_text = None

        if not page.document.method == "pdf-text":
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

        cropped_imgs = self.get_cropped_cell_images(
            image_pad, compute_prefix, show_cropped_bboxes
        )
        output = self.pipeline.predict(cropped_imgs)

        for cell, pred in zip(self.table["cells"], output):
            row_ids, col_ids = cell.row_ids, cell.col_ids
            row_id, col_id = row_ids[0], col_ids[0]

            self.table_data[row_id][col_id] += [
                {"text": text, "confidence": confidence * 100}
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

        self.footer_text = self.get_table_footer_text(textract_table, id_to_block)

    def get_table_footer_text(self, table, id_to_block):
        return "\n".join(
            [
                " ".join(
                    [
                        id_to_block[id]["Text"]
                        for rel in footer.get("Relationships", [])
                        if rel["Type"] == "CHILD"
                        for id in rel["Ids"]
                        if id_to_block[id]["BlockType"] == "WORD"
                    ]
                )
                for rel in table.get("Relationships", [])
                if rel["Type"] == "TABLE_FOOTER"
                for footer in [id_to_block[id] for id in rel["Ids"]]
            ]
        )

    def add_to_sheet(self, page_num, table_num, table_matrix, footer_text):
        thin_white_border = Border(
            left=Side(style="thin", color="FFFFFF"),
            right=Side(style="thin", color="FFFFFF"),
            top=Side(style="thin", color="FFFFFF"),
            bottom=Side(style="thin", color="FFFFFF"),
        )
        thick_blue_border = Border(
            left=Side(style="thick", color="0000FF"),
            right=Side(style="thick", color="0000FF"),
            top=Side(style="thick", color="0000FF"),
            bottom=Side(style="thick", color="0000FF"),
        )
        thick_violet_border = Border(
            left=Side(style="thick", color="FF00FF"),
            right=Side(style="thick", color="FF00FF"),
            top=Side(style="thick", color="FF00FF"),
            bottom=Side(style="thick", color="FF00FF"),
        )

        self.page.document.footers_workbook.active.append(
            [
                page_num,
                table_num,
                footer_text,
            ]
        )

        sheet_name = f"page_{page_num}_table_{table_num}"
        sheet = self.page.document.workbook.create_sheet(sheet_name)

        for i, row in enumerate(table_matrix, 1):
            for j, col in enumerate(row, 1):
                cell = sheet.cell(row=i, column=j, value=col["text"])
                cell_color = get_cell_color(col["confidence"])
                if cell_color:
                    cell.fill = PatternFill(start_color=cell_color, fill_type="solid")
                    cell.border = [
                        thin_white_border,
                        thick_violet_border,
                        thick_blue_border,
                    ][col["cnt_numbers"]]

                    if col["footnotes"]:
                        cell.comment = Comment(",".join(col["footnotes"]), "automatic")

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

    def join_cell_parts(self, cell):
        texts = [cell_part["text"] for cell_part in cell]
        conf_arr = np.array(
            [cell_part["confidence"] for cell_part in cell if cell_part["confidence"]]
        )
        confidence = conf_arr.mean()
        return {
            "text": " ".join(texts),
            "confidence": confidence if not np.isnan(confidence) else None,
        }

    def clean_cell_text(self, cell_text, remove_dots_and_commas):
        cell_text = ILLEGAL_CHARACTERS_RE.sub(r"", cell_text)
        dots = sum(c == "." for c in cell_text)
        commas = sum(c == "," for c in cell_text)

        if remove_dots_and_commas:
            cell_text = cell_text.replace(".", "").replace(",", "")

        return cell_text, dots, commas

    def remove_low_content_rows(self, table_data):
        total_row_lengths = sum(len("".join(row)) for row in table_data)
        mean_row_length = (
            total_row_lengths / len(table_data) if len(table_data) > 0 else 0
        )
        return [row for row in table_data if len("".join(row)) / mean_row_length > 0.1]

    def as_clean_matrix(self, remove_dots_and_commas):
        n = max([i + 1 for i in self.table_data.keys()], default=0)
        m = max(
            [j + 1 for cols in self.table_data.values() for j in cols.keys()], default=0
        )
        table_data = [
            [
                {
                    "text": "",
                    "confidence": None,
                    "footnotes": [],
                    "cnt_numbers": 0,
                }
                for _ in range(m)
            ]
            for _ in range(n)
        ]

        for row, cols in self.table_data.items():
            for col, cell in cols.items():
                cell = self.join_cell_parts(cell)
                cell["text"], cell["cnt_dots"], cell["cnt_commas"] = (
                    self.clean_cell_text(cell["text"], remove_dots_and_commas)
                )
                cell["text"], cell["footnotes"] = split_footnotes(cell["text"])
                table_data[row][col] = {**cell, "cnt_numbers": 0}

        return table_data

    def overwrite_seminumeric_cells_confidence(
        self, table_matrix, decimal_separator, thousands_separator, fix_num_misspellings
    ):
        for i, row in enumerate(table_matrix):
            for j, col in enumerate(row):
                _, cnt_numbers = self.maybe_parse_numeric_cell(
                    col,
                    decimal_separator,
                    thousands_separator,
                    fix_num_misspellings,
                )
                # If true, will add a thick border to the cell for review
                table_matrix[i][j]["cnt_numbers"] = cnt_numbers

        return table_matrix

    def maybe_parse_numeric_cells(
        self, table_matrix, decimal_separator, thousands_separator, fix_num_misspellings
    ):
        for i, row in enumerate(table_matrix):
            for j, col in enumerate(row):
                table_matrix[i][j]["text"], _ = self.maybe_parse_numeric_cell(
                    col,
                    decimal_separator,
                    thousands_separator,
                    fix_num_misspellings,
                )

        return table_matrix

    def cell_to_float(self, value):
        precision = self.page.document.fixed_decimal_places
        return float(value) / 10**precision

    def maybe_parse_numeric_cell(
        self, cell, decimal_separator, thousands_separator, fix_num_misspellings
    ):
        text = cell["text"]
        if not self.is_numeric_cell(text):
            return text, NOT_NUMBER

        text = text.replace(thousands_separator, "")
        if decimal_separator == ",":
            one_number = cell["cnt_commas"] <= 1
            text = text.replace(decimal_separator, ".")
        else:
            one_number = cell["cnt_dots"] <= 1

        if fix_num_misspellings:
            text = MISSPELLINGS_REGEX.sub(
                lambda x: str(MISSPELLINGS[x.group()]), text.upper()
            )

        try:
            return self.cell_to_float(text), NOT_NUMBER
        except ValueError:
            if not one_number:
                return text, AT_LEAST_TWO_NUMBERS if text else NOT_NUMBER
            maybe_sign = "-" if text.startswith("-") else ""
            only_numeric = maybe_sign + re.sub(r"[^.0-9]", "", text)

            if only_numeric:
                try:
                    return self.cell_to_float(only_numeric), ONE_NUMBER
                except ValueError:
                    return only_numeric, NOT_NUMBER
            else:
                return "", NOT_NUMBER

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
