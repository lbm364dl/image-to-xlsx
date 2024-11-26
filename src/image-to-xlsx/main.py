import numpy as np
import os
import cv2

from definitions import INPUT_PATH, OUTPUT_PATH
from unskewing import correct_skew
from binarization import binarize
from PIL import Image
from surya.input.load import load_from_file
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
    def __init__(
        self, input_path, rotation_delta=1, rotation_limit=5, custom_angle=None
    ):
        self.images, _, _ = load_from_file(input_path, dpi=settings.IMAGE_DPI_HIGHRES)
        self.rotate(
            delta=rotation_delta, limit=rotation_limit, custom_angle=custom_angle
        )

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
        for i, image in enumerate(self.images):
            _, corrected = correct_skew(np.array(image), delta, limit, custom_angle)
            self.images[i] = Image.fromarray(corrected)

    def binarize(self, method="otsu", block_size=None, constant=None):
        for i, img in enumerate(self.images):
            self.images[i] = binarize(img, method, block_size, constant)

    def predict(self, heuristic_thresh=0.6):
        self.line_predictions = batch_text_detection(
            self.images, self.det_model, self.det_processor
        )
        self.layout_predictions = batch_layout_detection(
            self.images, self.layout_model, self.layout_processor, self.line_predictions
        )
        self.table_cells = []
        self.tables = []
        for pred, img in zip(self.layout_predictions, self.images):
            [table] = [bbox for bbox in pred.bboxes if bbox.label == "Table"]
            bbox = table.bbox
            cropped_img = img.crop(bbox)

            [det_result] = batch_text_detection(
                [cropped_img], self.det_model, self.det_processor
            )
            cell_bboxes = [{"bbox": tb.bbox, "text": ""} for tb in det_result.bboxes]
            table = {"bbox": bbox, "img": cropped_img, "bboxes": cell_bboxes}
            self.tables.append(table)

        table_preds = batch_table_recognition(
            [d["img"] for d in self.tables],
            [d["bboxes"] for d in self.tables],
            self.model,
            self.processor,
        )
        for table_pred, table in zip(table_preds, self.tables):
            table["cells"] = assign_rows_columns(
                table_pred, table["img"].size, heuristic_thresh
            )
            table["pred"] = table_pred

    def is_numeric_cell(self, text, threshold=0.6):
        numeric = sum("0" <= c <= "9" for c in text)
        return numeric >= threshold * len(text)

    def build_table(
        self, pages="all", img_pad=600, compute_prefix=10, show_cropped_bboxes=False
    ):
        self.my_tables_predict = []
        process_tables = self.tables if pages == "all" else self.tables[:pages]
        for i, table in enumerate(process_tables):
            n = max(cell.row_ids[0] + 1 for cell in table["cells"])
            m = max(cell.col_ids[0] + 1 for cell in table["cells"])
            table_output = [[[] for _ in range(m)] for _ in range(n)]
            cropped_imgs = []
            for cell in table["cells"][:compute_prefix]:
                cropped_img = np.array(table["img"].crop(cell.bbox))
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
            self.my_tables_predict.append(output)

            for cell, pred in zip(table["cells"], output):
                row_ids, col_ids = cell.row_ids, cell.col_ids
                row_id, col_id = row_ids[0], col_ids[0]
                add_text = " ".join(pred["rec_text"])
                if self.is_numeric_cell(add_text):
                    add_text = add_text.replace(".", "").replace(",", "")
                if add_text:
                    table_output[row_id][col_id].append(add_text)

            output_path = os.path.join(OUTPUT_PATH, f"my_custom_table_{i}.csv")
            with open(output_path, "w") as f_out:
                split_table = []
                for row in table_output:
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
                output = "\n".join([
                    ";".join(row)
                    for row in split_table
                    if len("".join(row)) / mean_row_length > 0.1
                ])
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


if __name__ == "__main__":
    input_doc = os.path.join(INPUT_PATH, "saco_sample.pdf")
    t = Table(input_doc, rotation_delta=0.1, rotation_limit=5)
    # t.binarize(method="adaptive", block_size=31, constant=10)
    t.images[0].show()
    t.predict(heuristic_thresh=0.6)
    t.build_table(pages=1, img_pad=100, compute_prefix=50, show_cropped_bboxes=False)
