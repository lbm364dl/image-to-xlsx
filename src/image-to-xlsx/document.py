import pymupdf
import tempfile
from surya.input.load import load_from_file
from surya.settings import settings
from openpyxl import Workbook


class Document:
    def __init__(
        self,
        document,
        fixed_decimal_places=0,
        method="surya+paddle",
    ):
        self.method = method
        self.fixed_decimal_places = fixed_decimal_places

        with tempfile.NamedTemporaryFile() as f:
            f.write(document)

            if method == "pdf-text":
                self.pages = list(pymupdf.open(f.name).pages())
                self.text_lines = [None] * len(self.pages)
            else:
                self.pages, _, self.text_lines = load_from_file(
                    f.name, dpi=settings.IMAGE_DPI_HIGHRES, load_text_lines=True
                )
                self.text_lines = [
                    (line if line and line["blocks"] else None)
                    for line in self.text_lines
                ]

        self.workbook = Workbook()
        self.workbook.remove(self.workbook.active)
        self.footers_workbook = Workbook()
        self.footers_workbook.active.append([
            "page_number",
            "table_number",
            "footer_text",
        ])
