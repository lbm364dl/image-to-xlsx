import os
from cli import parse_args
from utils import get_document_paths
from pathlib import Path


if __name__ == "__main__":
    args = parse_args()

    import pretrained
    from document import Document
    from page import Page

    root_dir_path, relative_paths = get_document_paths(args.input_path)
    for relative_path in relative_paths:
        print(f"Processing document {relative_path}")

        d = Document(
            relative_path,
            root_dir_path,
            args.use_pdf_text,
            args.fixed_decimal_places,
            args.extend_rows,
        )

        first_page = args.first_page - 1
        last_page = args.last_page - 1
        l = list(zip(d.pages, d.text_lines))
        for i, (page, text_lines) in enumerate(
            l[first_page : last_page + 1], first_page + 1
        ):
            p = Page(page, i, text_lines, d)

            if not args.use_pdf_text:
                p.set_models(**pretrained.all_models())

            p.process_page(
                unskew=args.unskew,
                binarize=args.binarize,
                nlp_postprocess=args.nlp_postprocess,
                nlp_postprocess_prompt_file=args.nlp_postprocess_prompt_file,
                text_language=args.text_language,
                show_detected_boxes=args.show_detected_boxes,
                compute_prefix=args.compute_prefix,
                image_pad=args.image_pad,
            )

        d.save_output()
