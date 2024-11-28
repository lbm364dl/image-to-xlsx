import sys
import argparse

INF = 10**9


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert tables from image/pdf to xlsx."
    )
    parser.add_argument("input_path", type=str, help="Path to PDF or image file.")
    parser.add_argument(
        "--first-page",
        type=int,
        help="First page to process (for PDFs only, 1-indexed). Default start of document",
        default=1,
    )
    parser.add_argument(
        "--last-page",
        type=int,
        help="Last page to process (for PDFs only, 1-indexed). Default end of document",
        default=INF,
    )
    parser.add_argument(
        "--binarize",
        type=int,
        choices={0, 1},
        help="Use binarization, i.e. force black & white pixels (0 for no, 1 for yes). Default 0",
        default=0,
    )
    parser.add_argument(
        "--nlp-postprocess",
        type=int,
        choices={0, 1},
        help="Use non-free OpenAI to try to fix OCR misspellings (0 for no, 1 for yes). Default 0",
        default=0,
    )
    parser.add_argument(
        "--text-language",
        type=str,
        help="ISO2 language code for NLP postprocessing suggesting the language of the text for misspellings fixing. Default 'en'",
        default="en",
    )

    return parser.parse_args(args=(sys.argv[1:] or ["--help"]))
