import os
import numpy as np
import cv2
import pretrained
from definitions import OUTPUT_PATH
from PIL import Image
from surya.detection import batch_text_detection
from surya.tables import batch_table_recognition
from surya.input.pdflines import get_table_blocks
from tabled.assignment import assign_rows_columns
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE


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
        if not page.document.use_pdf_text:
            self.page = page
            self.text_lines = text_lines
            self.image = whole_image
            self.cropped_img = self.image.crop(table_bbox)
            self.table_bbox = table_bbox
            self.model = model or pretrained.model
            self.processor = processor or pretrained.processor
            self.det_model = det_model or pretrained.det_model
            self.det_processor = det_processor or pretrained.det_processor
            self.pipeline = ocr_pipeline or pretrained.ocr_pipeline

    def recognize_structure(self, heuristic_thresh=0.6):
        if self.text_lines:
            [table_blocks] = get_table_blocks([self.table_bbox], self.text_lines, self.image.size) if self.text_lines is not None else []
        else:
            table_blocks = []

        [det_result] = batch_text_detection(
            [self.cropped_img], self.det_model, self.det_processor
        )
        self.det_result = det_result

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

        # print(table_pred.rows)
        # my_bboxes = [list(map(int, row.bbox)) for row in table_pred.rows]
        # print(my_bboxes)
        # self.visualize_bboxes(self.cropped_img, my_bboxes)
        # print('det_result', det_result)
        # self.visualize_bboxes(self.cropped_img, [col.bbox for col in det_result.vertical_lines])

        self.table["cells"] = assign_rows_columns(
            table_pred, self.table["img"].size, heuristic_thresh
        )
        # print("table cells", self.table["cells"])

    def is_numeric_cell(self, text, threshold=0.6):
        numeric = sum("0" <= c <= "9" for c in text)
        return numeric >= threshold * len(text)

    def get_cropped_cell_images(self, img_pad, compute_prefix, show_cropped_bboxes):
        cropped_imgs = []
        for cell in self.table["cells"][:compute_prefix]:
            cropped_img = np.array(self.table["img"].crop(cell.bbox))
            cropped_img = np.pad(
                cropped_img,
                ((img_pad, img_pad), (img_pad, img_pad), (0, 0)),
                mode="constant",
                constant_values=255,
            )
            if show_cropped_bboxes:
                Image.fromarray(cropped_img).show()
            cropped_imgs.append(cropped_img)

        return cropped_imgs

    def recognize_texts(self, img_pad, compute_prefix, show_cropped_bboxes):
        n = max((cell.row_ids[0] + 1 for cell in self.table["cells"]), default=0)
        m = max((cell.col_ids[0] + 1 for cell in self.table["cells"]), default=0)
        table_output = [[[] for _ in range(m)] for _ in range(n)]

        if self.text_lines:
            for cell in self.table["cells"]:
                row_ids, col_ids = cell.row_ids, cell.col_ids
                row_id, col_id = row_ids[0], col_ids[0]
                add_text = cell.text
                add_text = self.maybe_clean_numeric_cell(ILLEGAL_CHARACTERS_RE.sub(r"", add_text))
                if add_text:
                    table_output[row_id][col_id].append(add_text)
        else:
            cropped_imgs = self.get_cropped_cell_images(
                img_pad, compute_prefix, show_cropped_bboxes
            )
            output = self.pipeline.predict(cropped_imgs)

            for cell, pred in zip(self.table["cells"], output):
                row_ids, col_ids = cell.row_ids, cell.col_ids
                row_id, col_id = row_ids[0], col_ids[0]
                add_text = " ".join(pred["rec_text"])
                add_text = self.maybe_clean_numeric_cell(add_text)
                if add_text:
                    table_output[row_id][col_id].append(add_text)

        return table_output

    def set_table_from_pdf_text(self, table):
        self.table_output = table.extract()
        for i, row in enumerate(self.table_output):
            for j, col in enumerate(row):
                self.table_output[i][j] = self.maybe_clean_numeric_cell(
                    ILLEGAL_CHARACTERS_RE.sub(r"", col)
                )

    def maybe_clean_numeric_cell(self, text):
        if self.is_numeric_cell(text):
            return text.replace(".", "").replace(",", "")
        else:
            return text

    def extend_rows(self, table_output):
        split_table = []
        for row in table_output:
            rows = []
            for j, col in enumerate(row):
                for i, part in enumerate(col):
                    if len(rows) <= i:
                        rows.append([""] * len(row))
                    rows[i][j] = part

            split_table += rows

        return split_table

    def remove_low_content_rows(self, table_output):
        total_row_lengths = sum(len("".join(row)) for row in table_output)
        mean_row_length = total_row_lengths / len(table_output) if len(table_output) > 0 else 0
        return [
            row for row in table_output if len("".join(row)) / mean_row_length > 0.1
        ]

    def build_table(self, img_pad=100, compute_prefix=10**9, show_cropped_bboxes=False):
        table_output = self.recognize_texts(
            img_pad, compute_prefix, show_cropped_bboxes
        )
        # print('table_output')
        # for row in table_output:
        #     print(row)
        table_output = self.extend_rows(table_output)
        self.table_output = self.remove_low_content_rows(table_output)

    def nlp_postprocess(self, text_language="en"):
        from postprocessing import nlp_clean

        self.table_output = nlp_clean(self.table_output, text_language)

    def save_as_csv(self, output_path):
        with open(output_path, "w", encoding="utf-8") as f_out:
            output = "\n".join([";".join(row) for row in self.table_output])
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
