import os
import numpy as np
import cv2
from definitions import OUTPUT_PATH
from unskewing import correct_skew
from binarization import binarize
from PIL import Image
from surya.settings import settings
from surya.model.table_rec.model import load_model as load_model
from surya.model.table_rec.processor import load_processor
from surya.model.detection.model import (
    load_model as load_det_model,
    load_processor as load_det_processor,
)
from surya.detection import batch_text_detection
from surya.layout import batch_layout_detection
from surya.tables import batch_table_recognition
from tabled.assignment import assign_rows_columns
from paddlex import create_pipeline


class Table:
    def __init__(self, image):
        self.image = image

        self.model = load_model()
        self.processor = load_processor()

        self.layout_model = load_det_model(checkpoint=settings.LAYOUT_MODEL_CHECKPOINT)
        self.layout_processor = load_det_processor(
            checkpoint=settings.LAYOUT_MODEL_CHECKPOINT
        )

        self.det_model = load_det_model()
        self.det_processor = load_det_processor()

        self.pipeline = create_pipeline(pipeline="OCR")

    def rotate(self, delta=0.05, limit=5, custom_angle=None):
        _, corrected = correct_skew(np.array(self.image), delta, limit, custom_angle)
        self.image = Image.fromarray(corrected)

    def binarize(self, method="otsu", block_size=None, constant=None):
        self.image = binarize(self.image, method, block_size, constant)

    def predict(self, heuristic_thresh=0.6):
        [self.line_prediction] = batch_text_detection(
            [self.image], self.det_model, self.det_processor
        )
        [self.layout_prediction] = batch_layout_detection(
            [self.image],
            self.layout_model,
            self.layout_processor,
            [self.line_prediction],
        )

        [table] = [
            bbox for bbox in self.layout_prediction.bboxes if bbox.label == "Table"
        ]
        bbox = table.bbox
        cropped_img = self.image.crop(bbox)

        [det_result] = batch_text_detection(
            [cropped_img], self.det_model, self.det_processor
        )
        cell_bboxes = [{"bbox": tb.bbox, "text": ""} for tb in det_result.bboxes]
        self.table = {"bbox": bbox, "img": cropped_img, "bboxes": cell_bboxes}

        [table_pred] = batch_table_recognition(
            [cropped_img], [cell_bboxes], self.model, self.processor
        )

        self.table["cells"] = assign_rows_columns(
            table_pred, self.table["img"].size, heuristic_thresh
        )
        self.table["pred"] = table_pred

    def is_numeric_cell(self, text, threshold=0.6):
        numeric = sum("0" <= c <= "9" for c in text)
        return numeric >= threshold * len(text)

    def build_table(self, img_pad=600, compute_prefix=10, show_cropped_bboxes=False):
        n = max(cell.row_ids[0] + 1 for cell in self.table["cells"])
        m = max(cell.col_ids[0] + 1 for cell in self.table["cells"])
        self.table_output = [[[] for _ in range(m)] for _ in range(n)]
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

        output = list(self.pipeline.predict(cropped_imgs))
        self.table_predict = output

        for cell, pred in zip(self.table["cells"], output):
            row_ids, col_ids = cell.row_ids, cell.col_ids
            row_id, col_id = row_ids[0], col_ids[0]
            add_text = " ".join(pred["rec_text"])
            if self.is_numeric_cell(add_text):
                add_text = add_text.replace(".", "").replace(",", "")
            if add_text:
                self.table_output[row_id][col_id].append(add_text)

        split_table = []
        for row in self.table_output:
            rows = []
            for j, col in enumerate(row):
                for i, part in enumerate(col):
                    if len(rows) <= i:
                        rows.append([""] * len(row))
                    rows[i][j] = part

            split_table += rows

        mean_row_length = sum(len("".join(row)) for row in split_table) / len(
            split_table
        )
        self.table_output = [
            row for row in split_table if len("".join(row)) / mean_row_length > 0.1
        ]

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
