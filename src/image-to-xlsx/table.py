import numpy as np
import cv2
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
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import PatternFill, Border, Side
from openpyxl.comments import Comment


class Table:
    def __init__(
        self,
        whole_image,
        page,
        table_bbox,
    ):
        self.page = page
        self.footer_text = None
        self.image = whole_image
        self.table_bbox = table_bbox

        if page.document.method not in ("pdf-text", "paddleocr-vl"):
            self.cropped_img = self.image.crop(table_bbox)

    def is_numeric_cell(self, text, threshold=0.6):
        numeric = sum("0" <= c <= "9" for c in text)
        return numeric >= threshold * len(text)

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
            [cell_part["confidence"] for cell_part in cell if cell_part["confidence"] is not None]
        )
        confidence = conf_arr.mean() if conf_arr.size > 0 else None
        return {
            "text": " ".join(texts),
            "confidence": confidence if confidence is not None and not np.isnan(confidence) else None,
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
                    "cnt_dots": 0,
                    "cnt_commas": 0,
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

    def set_table_from_paddleocr_vl_markdown(self, markdown_text):
        """Parse PaddleOCR-VL table output into self.table_data.

        Supports HTML tables ("<table>...") and markdown pipe tables.
        """
        from html.parser import HTMLParser
        import html

        def parse_html_table(text):
            class _TableHTMLParser(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.rows = []
                    self._current_row = None
                    self._in_cell = False
                    self._cell_buf = []

                def handle_starttag(self, tag, attrs):
                    if tag == "tr":
                        self._current_row = []
                    elif tag in ("td", "th"):
                        self._in_cell = True
                        self._cell_buf = []

                def handle_endtag(self, tag):
                    if tag in ("td", "th") and self._in_cell:
                        cell_text = "".join(self._cell_buf).strip()
                        self._current_row.append(cell_text)
                        self._in_cell = False
                        self._cell_buf = []
                    elif tag == "tr" and self._current_row is not None:
                        if self._current_row:
                            self.rows.append(self._current_row)
                        self._current_row = None

                def handle_data(self, data):
                    if self._in_cell:
                        self._cell_buf.append(html.unescape(data))

            parser = _TableHTMLParser()
            parser.feed(text)
            return parser.rows

        def parse_markdown_table(text):
            lines = [line.strip() for line in text.strip().split("\n") if line.strip()]

            # Filter out separator lines (e.g., |---|---|)
            data_lines = []
            for line in lines:
                stripped = line.strip("|").strip()
                # A separator line consists only of dashes, pipes, colons, and spaces
                if stripped and not all(c in "-|: " for c in stripped):
                    data_lines.append(line)

            rows = []
            for line in data_lines:
                cells = line.split("|")
                if cells and cells[0].strip() == "":
                    cells = cells[1:]
                if cells and cells[-1].strip() == "":
                    cells = cells[:-1]
                rows.append([cell.strip() for cell in cells])

            return rows

        self.table_data = defaultdict(lambda: defaultdict(list))
        if "<table" in markdown_text.lower():
            rows = parse_html_table(markdown_text)
        else:
            rows = parse_markdown_table(markdown_text)

        for row_idx, row in enumerate(rows):
            for col_idx, cell_text in enumerate(row):
                self.table_data[row_idx][col_idx] = [
                    {"text": cell_text.strip(), "confidence": None}
                ]

    def set_table_from_surya(
        self,
        image_pad=100,
        show_detected_boxes=False,
    ):
        """Use surya's TableRecPredictor for structure and RecognitionPredictor for OCR."""
        import pretrained

        # 1. Detect table structure (rows, columns, cells)
        table_rec = pretrained.table_rec_predictor()
        [table_result] = table_rec([self.cropped_img])

        if show_detected_boxes:
            self.visualize_bboxes(
                self.cropped_img,
                [cell.bbox for cell in table_result.cells],
            )

        # 2. Crop each cell and run OCR
        rec = pretrained.recognition_predictor()
        det = pretrained.detection_predictor()

        cell_images = []
        cell_infos = []
        for cell in table_result.cells:
            cropped = self.cropped_img.crop(cell.bbox)
            cropped_arr = np.array(cropped.convert("RGB"))
            padded = np.pad(
                cropped_arr,
                ((image_pad, image_pad), (image_pad, image_pad), (0, 0)),
                mode="constant",
                constant_values=255,
            )
            cell_images.append(Image.fromarray(padded))
            cell_infos.append(cell)

        self.table_data = defaultdict(lambda: defaultdict(list))

        if cell_images:
            import torch

            # Process in batches to avoid CUDA OOM errors
            BATCH_SIZE = 8
            ocr_results = []
            for batch_start in range(0, len(cell_images), BATCH_SIZE):
                batch_imgs = cell_images[batch_start:batch_start + BATCH_SIZE]
                batch_results = rec(batch_imgs, det_predictor=det)
                ocr_results.extend(batch_results)
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

            for cell_info, ocr_result in zip(cell_infos, ocr_results):
                row_id = cell_info.row_id
                col_id = cell_info.col_id
                text = " ".join(line.text for line in ocr_result.text_lines)
                confidences = [
                    line.confidence for line in ocr_result.text_lines
                    if line.confidence is not None
                ]
                confidence = (
                    sum(confidences) / len(confidences) * 100
                    if confidences
                    else None
                )
                self.table_data[row_id][col_id].append(
                    {"text": text.strip(), "confidence": confidence}
                )

    def enrich_with_ocr_confidence(self, ocr_words):
        """Match OCR words to table cells by fuzzy text matching, assigning confidence.

        Args:
            ocr_words: list of {"text": str, "bbox": [x1,y1,x2,y2], "confidence": float}
                       sorted in reading order (top-to-bottom, left-to-right).
        """
        from difflib import SequenceMatcher

        if not ocr_words:
            return

        # Build a consumed-flags array so we greedily consume each OCR word once
        available = list(range(len(ocr_words)))

        # Walk cells in reading order (row-major)
        for row_idx in sorted(self.table_data.keys()):
            for col_idx in sorted(self.table_data[row_idx].keys()):
                parts = self.table_data[row_idx][col_idx]
                for part in parts:
                    if not part["text"].strip():
                        continue

                    # Find best fuzzy match among available OCR words
                    best_idx = None
                    best_ratio = 0.0
                    for avail_pos, ocr_idx in enumerate(available):
                        ocr_text = ocr_words[ocr_idx]["text"]
                        ratio = SequenceMatcher(
                            None, part["text"].lower(), ocr_text.lower()
                        ).ratio()
                        if ratio > best_ratio:
                            best_ratio = ratio
                            best_idx = avail_pos
                        # Perfect match — stop early
                        if ratio == 1.0:
                            break

                    # Accept match if similarity is above threshold
                    if best_idx is not None and best_ratio >= 0.5:
                        matched_ocr = ocr_words[available[best_idx]]
                        part["confidence"] = matched_ocr["confidence"]
                        # Remove from available pool
                        available.pop(best_idx)

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
