import pymupdf
import pypdfium2
import tempfile
from surya.input.load import load_from_file
from surya.settings import settings
from openpyxl import Workbook
from utils import file_extension
from PIL import Image
from io import BytesIO


class Document:
    def __init__(
        self,
        document,
        fixed_decimal_places=0,
        method="surya+paddle",
    ):
        self.method = method
        self.fixed_decimal_places = fixed_decimal_places
        self.extension = file_extension(document["name"])
        self.tot_pages = 1

        if self.extension == "pdf":
            self.pdf = pymupdf.open("pdf", document["content"])
            self.tot_pages = self.pdf.page_count

        self.set_page_nums(document["pages"])
        self.load_pages(document["content"], method)

        self.workbook = Workbook()
        self.workbook.remove(self.workbook.active)
        self.footers_workbook = Workbook()
        self.footers_workbook.active.append([
            "page_number",
            "table_number",
            "footer_text",
        ])

    def set_page_nums(self, page_ranges):
        self.page_nums = set()
        for start, end in page_ranges:
            self.page_nums |= set(range(start, min(self.tot_pages, end) + 1))

    def load_pages(self, document, method):
        if self.extension == "pdf":
            if method == "pdf-text":
                self.pages = {i: self.pdf.load_page(i) for i in self.page_nums}
            else:
                pdf = pypdfium2.PdfDocument(BytesIO(document))
                self.pages = dict(zip(self.page_nums, pdf.render(
                    pypdfium2.PdfBitmap.to_pil,
                    page_indices=self.page_nums,
                    scale=2,
                )))
        else:
            self.pages = {1: Image.open(BytesIO(document))}