from document import Document
from page import Page
from cli import parse_args
from utils import get_document_paths, save_workbook
from definitions import INF
import os
import shutil


def run(
    document,
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
    heuristic_thresh=0.6,
    textract_response_pickle_file=None,
    remove_dots_and_commas=0,
    decimal_separator=".",
    thousands_separator=",",
    **kwargs,
):
    d = Document(
        document,
        fixed_decimal_places,
        method,
    )

    for i, page in sorted(d.pages.items()):
        print(f"    Processing page {i}")
        p = Page(page, i, d)
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

    return d.workbook, d.footers_workbook


def save_output(table_workbook, footers_workbook, output_dir, file_name):
    output_dir.mkdir(parents=True, exist_ok=True)
    output_xlsx_path = output_dir / f"{file_name}.xlsx"
    save_workbook(table_workbook, output_xlsx_path)
    shutil.copy(real_path, output_dir)
    footers_xlsx_path = output_dir / f"footers_{file_name}.xlsx"
    save_workbook(footers_workbook, footers_xlsx_path)


if __name__ == "__main__":
    args = parse_args()

    from document import Document
    from page import Page

    root_dir_path, relative_paths = get_document_paths(args.input_path)

    for relative_path in relative_paths:
        print(f"Processing document {relative_path}")
        output_dir = (
            root_dir_path / "results" / relative_path
        ).parent / relative_path.stem

        if not args.overwrite_existing_result and os.path.isdir(output_dir):
            print("Skipping already processed document")
            continue

        real_path = os.path.join(root_dir_path, relative_path)
        with open(real_path, "rb") as f:
            document = {
                "name": str(relative_path),
                "content": f.read(),
                "pages": [(args.first_page, args.last_page)],
            }
            table_workbook, footers_workbook = run(document, **vars(args))
            save_output(
                table_workbook, footers_workbook, output_dir, relative_path.stem
            )
