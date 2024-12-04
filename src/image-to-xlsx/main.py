import os
from cli import parse_args
from utils import get_document_paths
from pathlib import Path


if __name__ == "__main__":
    args = parse_args()

    import pretrained
    from document import Document
    from page import Page

    input_dir = Path(os.path.dirname(args.input_path))
    results_dir = input_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    for path in get_document_paths(args.input_path):
        print(f"Processing document {path}")

        d = Document(path, results_dir, args.use_pdf_text)

        first_page = args.first_page - 1
        last_page = args.last_page - 1
        l = list(zip(d.pages, d.text_lines))
        for i, (page, text_lines) in enumerate(l[first_page : last_page + 1], first_page + 1):
            p = Page(page, i, text_lines, d)

            if not args.use_pdf_text:
                p.set_models(**pretrained.all_models())

            p.process_page(
                unskew=args.unskew,
                binarize=args.binarize,
                nlp_postprocess=args.nlp_postprocess,
                text_language=args.text_language,
                show_detected_boxes=args.show_detected_boxes,
            )

        d.save_output()
