import pickle
import cv2
import numpy as np
import io
from collections import defaultdict
from PIL import Image
from surya.input.load import load_from_file
from surya.settings import settings


def visualize_bboxes(img, bboxes):
    visualize_img = np.array(img, dtype=np.uint8)
    h, w, _ = visualize_img.shape
    bboxes = np.array(bboxes, dtype=np.int32)
    for [x1, y1, x2, y2] in bboxes:
        [x1, x2] = [min(max(0, x), w) for x in [x1, x2]]
        [y1, y2] = [min(max(0, y), h) for y in [y1, y2]]
        cv2.rectangle(visualize_img, (x1, y1), (x2, y2), color=(255, 0, 0), thickness=1)

    Image.fromarray(visualize_img).show()


def visualize_polys(img, polys):
    visualize_img = np.array(img, dtype=np.uint8)
    h, w, _ = visualize_img.shape
    bboxes = np.array(bboxes, dtype=np.int32)
    for [x1, y1, x2, y2] in bboxes:
        [x1, x2] = [min(max(0, x), w) for x in [x1, x2]]
        [y1, y2] = [min(max(0, y), h) for y in [y1, y2]]
        cv2.rectangle(visualize_img, (x1, y1), (x2, y2), color=(255, 0, 0), thickness=1)

    Image.fromarray(visualize_img).show()


def to_int(img, y, x):
    w, h = img.size
    return int(y * h), int(x * w)


def visualize_block_type(img, blocks):
    bboxes = []
    for block in blocks:
        box = block["Geometry"]["BoundingBox"]
        y, x = to_int(img, box["Top"], box["Left"])
        height, width = to_int(img, box["Height"], box["Width"])
        bboxes.append([x, y, x + width, y + height])

    visualize_bboxes(img, bboxes)


def process_table(table, id_to_block, table_idx):
    # TODO: Check merged cells
    table_cells = [
        id_to_block[id]
        for relationship in table.get("Relationships", [])
        for id in relationship["Ids"]
        if id_to_block[id]["BlockType"] == "CELL"
    ]

    n, m = 1, 1
    table = defaultdict(dict)
    for cell in table_cells:
        words = [
            id_to_block[id]
            for relationship in cell.get("Relationships", [])
            for id in relationship["Ids"]
            if id_to_block[id]["BlockType"] == "WORD"
        ]
        row, col = cell["RowIndex"], cell["ColumnIndex"]
        n, m = max(n, row), max(m, row)
        table[row][col] = " ".join([word["Text"] for word in words])

    output_table = [[[] for _ in range(m)] for _ in range(n)]
    for row, cols in table.items():
        for col, text in cols.items():
            output_table[row-1][col-1].append(text)

    for row in output_table:
        print(row)

    with open(f"test_justin2_{table_idx}.csv", "w") as f_out:
        f_out.write('\n'.join(';'.join(' '.join(col) for col in row) for row in output_table).replace('"', ""))


document_path = "inputs/StatisticalAbstract/StatisticalAbstract.16.exports.pp1.pdf"
pages, _, text_lines = load_from_file(
    document_path, dpi=settings.IMAGE_DPI_HIGHRES, load_text_lines=True
)
img = pages[1]

with open("test_output_justin2.pkl", "rb") as f:
    loaded_dict = pickle.load(f)

blocks = loaded_dict["Blocks"]
tables = [block for block in blocks if block["BlockType"] == "TABLE"]
id_to_block = {block["Id"]: block for block in blocks}

for i, table in enumerate(tables):
    print("Processing table...")
    process_table(table, id_to_block, i)

# visualize_block_type(
#     img, [block for block in loaded_dict["Blocks"] if block["BlockType"] == "CELL"]
# )
