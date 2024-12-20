import sys
import argparse
import textwrap

INF = 10**9


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert tables from image/pdf to xlsx.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("input_path", type=str, help="Path to PDF or image file.")
    parser.add_argument(
        "--method",
        type=str,
        choices={"surya+paddle", "pdf-text", "textract", "textract-pickle-debug"},
        help=textwrap.dedent("""\
        Method to use for table recognition. Default surya+paddle. Methods:
        - surya+paddle: opensource AI table recognition using surya library and OCR each cell using Paddle
        - pdf-text: use PyMuPDF library to recognize the table (using internal PDF text), if you know the PDF comes with text
        """),
        default="surya+paddle",
    )
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
        "--unskew",
        type=int,
        choices={0, 1},
        help="Try to detect and undo image rotation (0 for no, 1 for yes). Default 0",
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
        "--nlp-postprocess-prompt-file",
        type=str,
        help="Use a custom prompt message for NLP postprocessing. Indicate the path of the text file with the prompt message. By default, a generic one for cleaning cell typos is used.",
        default=None,
    )
    parser.add_argument(
        "--text-language",
        type=str,
        help="ISO2 language code for NLP postprocessing suggesting the language of the text for misspellings fixing. Default 'en'",
        default="en",
    )
    parser.add_argument(
        "--show-detected-boxes",
        type=int,
        choices={0, 1},
        help="Open image with detected boxes for each table for debugging (0 for no, 1 for yes). Default 0",
        default=0,
    )
    parser.add_argument(
        "--extend-rows",
        type=int,
        choices={0, 1},
        help="If there is a row that tries to include several texts into the same cell, try to extend to a new row below (0 for no, 1 for yes). Default 0, meaning all texts to the same cell are just joined with a space separator",
        default=0,
    )
    parser.add_argument(
        "--image-pad",
        type=int,
        help="When running OCR for each individual cell, add this amount of pixels in padding on the cropped image on all four sides. More or less padding may help for better OCR text recognition. Default 100 pixels",
        default=100,
    )
    parser.add_argument(
        "--compute-prefix",
        type=int,
        help="For debugging, compute only this amount of cells in the output table, since it can take too long to compute all of them. Default all cells",
        default=INF,
    )
    parser.add_argument(
        "--fixed-decimal-places",
        type=int,
        help="Forcefully write a decimal point this number of places to the left of the last digit. By default no decimal points are added.",
        default=0,
    )
    parser.add_argument(
        "--textract-response-pickle-file",
        type=str,
        help="Path to pkl file with Textract response for a particular page. Use for debugging and not calling the API all the time",
        default=None,
    )
    parser.add_argument(
        "--overwrite-existing-result",
        type=int,
        choices={0, 1},
        help="Process document even if it was already processed before (i.e. it has its individual results directory already created). Default 0 (i.e. skip document)",
        default=0,
    )

    return parser.parse_args(args=(sys.argv[1:] or ["--help"]))
