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
        choices={"surya", "pdf-text", "paddleocr-vl", "glm-ocr"},
        help=textwrap.dedent("""\
        Extraction method. Default surya. Each method runs as a microservice:
        - surya: open source AI table recognition and OCR (surya-ocr)
        - paddleocr-vl: PaddleOCR Vision-Language model for document parsing
        - glm-ocr: GLM-OCR multimodal model via API (needs a running vLLM backend)
        - pdf-text: uses embedded PDF text (no OCR, no GPU needed)
        """),
        default="surya",
    )
    parser.add_argument(
        "--first-page",
        type=int,
        help="First page to process (1-indexed). Default start of document",
        default=1,
    )
    parser.add_argument(
        "--last-page",
        type=int,
        help="Last page to process (1-indexed). Default end of document",
        default=INF,
    )
    parser.add_argument(
        "--binarize",
        type=int,
        choices={0, 1},
        help="Force black & white pixels (0/1). Default 0",
        default=0,
    )
    parser.add_argument(
        "--unskew",
        type=int,
        choices={0, 1},
        help="Try to detect and undo image rotation (0/1). Default 0",
        default=0,
    )
    parser.add_argument(
        "--nlp-postprocess",
        type=int,
        choices={0, 1},
        help="Use OpenAI to fix OCR misspellings (0/1). Default 0",
        default=0,
    )
    parser.add_argument(
        "--nlp-postprocess-prompt-file",
        type=str,
        help="Custom prompt file for NLP postprocessing.",
        default=None,
    )
    parser.add_argument(
        "--text-language",
        type=str,
        help="ISO2 language code for NLP postprocessing. Default 'en'",
        default="en",
    )
    parser.add_argument(
        "--show-detected-boxes",
        type=int,
        choices={0, 1},
        help="Show detected boxes for debugging (0/1). Default 0",
        default=0,
    )
    parser.add_argument(
        "--extend-rows",
        type=int,
        choices={0, 1},
        help="Split multi-text cells into separate rows (0/1). Default 0",
        default=0,
    )
    parser.add_argument(
        "--image-pad",
        type=int,
        help="Padding pixels around cropped cells for OCR. Default 100",
        default=100,
    )
    parser.add_argument(
        "--compute-prefix",
        type=int,
        help="For debugging: compute only this many cells. Default all",
        default=INF,
    )
    parser.add_argument(
        "--fixed-decimal-places",
        type=int,
        help="Force a decimal point this many places from the right. Default 0",
        default=0,
    )
    parser.add_argument(
        "--overwrite-existing-result",
        type=int,
        choices={0, 1},
        help="Re-process already-processed documents (0/1). Default 0",
        default=0,
    )
    parser.add_argument(
        "--remove-dots-and-commas",
        type=int,
        choices={0, 1},
        help="Remove all dots and commas from output (0/1). Default 0",
        default=0,
    )
    parser.add_argument(
        "--fix-num-misspellings",
        type=int,
        choices={0, 1},
        help="Fix common digit-as-letter OCR errors (I->1, O->0, etc). Default 1",
        default=1,
    )
    parser.add_argument(
        "--decimal-separator",
        type=str,
        choices={",", "."},
        help="Decimal separator. Default dot (.)",
        default=".",
    )
    parser.add_argument(
        "--thousands-separator",
        type=str,
        choices={",", "."},
        help="Thousands separator. Default comma (,)",
        default=",",
    )
    parser.add_argument(
        "--dewarp",
        type=int,
        choices={0, 1},
        help="Dewarp document images before extraction using GeoTr AI (0/1). Default 0",
        default=0,
    )

    return parser.parse_args(args=(sys.argv[1:] or ["--help"]))
