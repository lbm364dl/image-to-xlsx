import os
import pretrained

from definitions import INPUT_PATH
from document import Document
from page import Page

if __name__ == "__main__":
    model = pretrained.model
    processor = pretrained.processor
    layout_model = pretrained.layout_model
    layout_processor = pretrained.layout_processor
    det_model = pretrained.det_model
    det_processor = pretrained.det_processor
    ocr_pipeline = pretrained.ocr_pipeline

    input_doc = os.path.join(INPUT_PATH, "two_tables.jpg")
    d = Document(path=input_doc)

    from_page = 0
    to_page = 0
    for i, img in enumerate(d.pages[from_page : to_page + 1], from_page):
        p = Page(
            img,
            i,
            model,
            processor,
            det_model,
            det_processor,
            layout_model,
            layout_processor,
            ocr_pipeline,
        )
        p.image.show()
        p.rotate(delta=0.1, limit=5)
        # p.binarize(method="otsu", block_size=31, constant=10)
        p.recognize_tables_structure(
            heuristic_thresh=0.6, img_pad=100, compute_prefix=10**9
        )
