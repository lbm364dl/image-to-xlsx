import os
import pretrained

from definitions import INPUT_PATH
from document import Document
from table import Table

if __name__ == "__main__":
    model = pretrained.model
    processor = pretrained.processor
    layout_model = pretrained.layout_model
    layout_processor = pretrained.layout_processor
    det_model = pretrained.det_model
    det_processor = pretrained.det_processor
    ocr_pipeline = pretrained.ocr_pipeline

    input_doc = os.path.join(INPUT_PATH, "StatisticalAbstract.1949.imports.pp2.pdf")
    d = Document(path=input_doc)

    from_page = 0
    to_page = 0
    for i, img in enumerate(d.pages[from_page : to_page + 1], from_page):
        t = Table(
            img,
            model,
            processor,
            det_model,
            det_processor,
            layout_model,
            layout_processor,
            ocr_pipeline,
        )
        t.image.show()
        t.rotate(delta=0.1, limit=5)
        # t.binarize(method="otsu", block_size=31, constant=10)
        t.image.show()
        t.recognize_table_structure(heuristic_thresh=0.8)
        t.visualize_table_bboxes()
        t.build_table(img_pad=100, compute_prefix=10**9)

        # uses non-free openai API to try to fix misspelled words
        # you can skip it otherwise
        t.nlp_postprocess()

        print(t.table_output)
        t.save_as_csv(f"my_table_{i}.csv")
