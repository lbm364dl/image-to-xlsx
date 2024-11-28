import os
from cli import parse_args
from pathlib import Path


if __name__ == "__main__":
    args = parse_args()

    import pretrained
    from document import Document
    from page import Page

    input_dir = Path(os.path.dirname(args.input_path))
    results_dir = input_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    d = Document(args.input_path, results_dir)

    first_page = args.first_page - 1
    last_page = args.last_page - 1
    for i, img in enumerate(d.pages[first_page : last_page + 1], first_page + 1):
        p = Page(img, i, d.document_results_dir, **pretrained.all_models())
        p.image.show()
        p.rotate(delta=0.1, limit=5)

        if args.binarize:
            p.binarize(method="otsu", block_size=31, constant=10)
            p.image.show()

        p.recognize_tables_structure(
            heuristic_thresh=0.6,
            img_pad=100,
            compute_prefix=50,
            nlp_postprocess=args.nlp_postprocess,
            text_language=args.text_language,
        )
