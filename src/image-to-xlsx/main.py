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

    d = Document(args.input_path, results_dir, args.use_pdf_text)

    first_page = args.first_page - 1
    last_page = args.last_page - 1
    for i, page in enumerate(d.pages[first_page : last_page + 1], first_page + 1):
        p = Page(page, i, d, **pretrained.all_models())
        p.process_page(
            unskew=args.unskew,
            binarize=args.binarize,
            nlp_postprocess=args.nlp_postprocess,
            text_language=args.text_language,
            show_detected_boxes=args.show_detected_boxes,
        )

    d.save_output()
