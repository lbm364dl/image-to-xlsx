import os

from definitions import INPUT_PATH
from document import Document
from table import Table

if __name__ == "__main__":
    input_doc = os.path.join(INPUT_PATH, "saco_sample.pdf")
    d = Document(path=input_doc)
    
    for img in d.pages[:1]:
        t = Table(img)
        t.rotate(delta=0.1, limit=5)
        t.image.show()
        t.binarize(method="adaptive", block_size=31, constant=10)
        t.image.show()
        t.predict(heuristic_thresh=0.6)
        t.build_table(img_pad=100, compute_prefix=50, show_cropped_bboxes=False)
        print(t.table_output)
        t.save_as_csv("my_table.csv")

