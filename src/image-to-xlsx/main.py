from cli import parse_args
from utils import get_document_paths

INF = 10**9


def run(
    input_path,
    method="surya+paddle",
    unskew=0,
    binarize=0,
    nlp_postprocess=0,
    nlp_postprocess_prompt_file=None,
    text_language="en",
    show_detected_boxes=0,
    compute_prefix=INF,
    image_pad=100,
    fixed_decimal_places=0,
    extend_rows=0,
    first_page=1,
    last_page=INF,
    heuristic_thresh=0.6,
    textract_response_pickle_file=None,
    overwrite_existing_result=0,
    remove_dots_and_commas=0,
    decimal_separator=".",
    thousands_separator=",",
):
    from document import Document
    from page import Page

    root_dir_path, relative_paths = get_document_paths(input_path)
    for relative_path in relative_paths:
        print(f"Processing document {relative_path}")

        d = Document(
            relative_path,
            root_dir_path,
            fixed_decimal_places,
            method,
        )
        if not overwrite_existing_result and d.exists_output_dir():
            print("Skipping already processed document")
            continue

        l = list(zip(d.pages, d.text_lines))
        for i, (page, text_lines) in enumerate(
            l[first_page - 1 : last_page], first_page
        ):
            p = Page(page, i, text_lines, d)
            p.process_page(
                unskew=unskew,
                binarize=binarize,
                extend_rows=extend_rows,
                nlp_postprocess=nlp_postprocess,
                nlp_postprocess_prompt_file=nlp_postprocess_prompt_file,
                text_language=text_language,
                show_detected_boxes=show_detected_boxes,
                compute_prefix=compute_prefix,
                image_pad=image_pad,
                heuristic_thresh=heuristic_thresh,
                textract_response_pickle_file=textract_response_pickle_file,
                remove_dots_and_commas=remove_dots_and_commas,
                decimal_separator=decimal_separator,
                thousands_separator=thousands_separator,
            )

        d.save_output()


if __name__ == "__main__":
    args = parse_args()
    run(**vars(args))
