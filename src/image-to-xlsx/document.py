import os
import pymupdf
import shutil
from surya.input.load import load_from_file
from surya.settings import settings
from pathlib import Path
from openpyxl import Workbook


class Document:
    def __init__(
        self,
        relative_path,
        input_dir,
        results_dir,
        use_pdf_text=0,
        fixed_decimal_places=0,
        extend_rows=0,
    ):
        self.use_pdf_text = use_pdf_text
        real_path = os.path.join(input_dir, relative_path)
        self.path = Path(real_path)

        if use_pdf_text:
            self.pages = list(pymupdf.open(self.path).pages())
            self.text_lines = [None] * len(self.pages)
        else:
            self.pages, _, self.text_lines = load_from_file(
                real_path, dpi=settings.IMAGE_DPI_HIGHRES, load_text_lines=True
            )
            self.text_lines = [
                (line if line and line["blocks"] else None) for line in self.text_lines
            ]

        self.fixed_decimal_places = fixed_decimal_places
        self.extend_rows = extend_rows
        self.file_name = self.path.stem
        self.extension = self.path.suffix
        self.document_results_dir = results_dir / self.file_name
        self.document_results_dir.mkdir(parents=True, exist_ok=True)
        self.workbook = Workbook()
        self.workbook.remove(self.workbook.active)

    def save_output(self):
        self.workbook.save(self.document_results_dir / f"{self.file_name}_output.xlsx")
        shutil.copy(self.path, self.document_results_dir)
