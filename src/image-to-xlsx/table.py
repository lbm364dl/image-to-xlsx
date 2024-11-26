import os
import numpy as np
import cv2
import pretrained
from definitions import OUTPUT_PATH
from unskewing import correct_skew
from binarization import binarize
from PIL import Image
from surya.detection import batch_text_detection
from surya.layout import batch_layout_detection
from surya.tables import batch_table_recognition
from tabled.assignment import assign_rows_columns


class Table:
    def __init__(
        self,
        image,
        model=None,
        processor=None,
        det_model=None,
        det_processor=None,
        layout_model=None,
        layout_processor=None,
        ocr_pipeline=None,
    ):
        self.image = image
        self.model = model or pretrained.model
        self.processor = processor or pretrained.processor
        self.det_model = det_model or pretrained.det_model
        self.det_processor = det_processor or pretrained.det_processor
        self.layout_model = layout_model or pretrained.layout_model
        self.layout_processor = layout_processor or pretrained.layout_processor
        self.pipeline = ocr_pipeline or pretrained.ocr_pipeline

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

    def recognize_table_structure(self, heuristic_thresh=0.6):
        [table] = self.detect_tables()
        cropped_img = self.image.crop(table.bbox)

        [det_result] = batch_text_detection(
            [cropped_img], self.det_model, self.det_processor
        )
        cell_bboxes = [{"bbox": tb.bbox, "text": ""} for tb in det_result.bboxes]
        self.table = {"bbox": table.bbox, "img": cropped_img, "bboxes": cell_bboxes}

        [table_pred] = batch_table_recognition(
            [cropped_img], [cell_bboxes], self.model, self.processor
        )

        self.table["cells"] = assign_rows_columns(
            table_pred, self.table["img"].size, heuristic_thresh
        )

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
        n = max(cell.row_ids[0] + 1 for cell in self.table["cells"])
        m = max(cell.col_ids[0] + 1 for cell in self.table["cells"])
        table_output = [[[] for _ in range(m)] for _ in range(n)]
        cropped_imgs = self.get_cropped_cell_images(
            img_pad, compute_prefix, show_cropped_bboxes
        )
        output = self.pipeline.predict(cropped_imgs)

        for cell, pred in zip(self.table["cells"], output):
            row_ids, col_ids = cell.row_ids, cell.col_ids
            row_id, col_id = row_ids[0], col_ids[0]
            add_text = " ".join(pred["rec_text"])
            if self.is_numeric_cell(add_text):
                add_text = add_text.replace(".", "").replace(",", "")
            if add_text:
                table_output[row_id][col_id].append(add_text)

        return table_output

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
        mean_row_length = total_row_lengths / len(table_output)
        return [
            row for row in table_output if len("".join(row)) / mean_row_length > 0.1
        ]

    def build_table(self, img_pad=100, compute_prefix=10**9, show_cropped_bboxes=False):
        table_output = self.recognize_texts(
            img_pad, compute_prefix, show_cropped_bboxes
        )
        table_output = self.extend_rows(table_output)
        self.table_output = self.remove_low_content_rows(table_output)

    def save_as_csv(self, csv_name):
        output_path = os.path.join(OUTPUT_PATH, csv_name)
        with open(output_path, "w") as f_out:
            output = "\n".join([";".join(row) for row in self.table_output])
            print(output)
            f_out.write(output)

    def visualize_bboxes(self, img, bboxes):
        visualize_img = np.array(img, dtype=np.uint8)
        bboxes = np.array(bboxes, dtype=np.uint32)
        for [x1, y1, x2, y2] in bboxes:
            cv2.rectangle(
                visualize_img, (x1, y1), (x2, y2), color=(255, 0, 0), thickness=1
            )

        Image.fromarray(visualize_img).show()

    def visualize_table_bboxes(self, table):
        self.visualize_bboxes(table["img"], [c["bbox"] for c in table["bboxes"]])
