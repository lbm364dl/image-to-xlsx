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

    input_doc = os.path.join(INPUT_PATH, "saco_sample.pdf")
    d = Document(path=input_doc)

    for i, img in enumerate(d.pages[:1000]):
        t = Table(
            img,
            model,
            processor,
            det_model,
            det_processor,
            layout_model,
            layout_processor,
        )
        t.rotate(delta=0.1, limit=5)
        t.binarize(method="adaptive", block_size=31, constant=10)
        t.image.show()
        t.recognize_table_structure(heuristic_thresh=0.6)
        t.build_table(img_pad=100, compute_prefix=10**9, show_cropped_bboxes=False)
        print(t.table_output)
        t.save_as_csv(f"my_table_{i}.csv")
