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
        root_dir_path,
        fixed_decimal_places=0,
        method="surya+paddle",
    ):
        self.method = method
        real_path = os.path.join(root_dir_path, relative_path)
        self.path = Path(real_path)

        if method == "pdf-text":
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
        self.file_name = self.path.stem
        self.extension = self.path.suffix
        self.root_dir_path = Path(root_dir_path)
        self.relative_path = Path(relative_path)
        self.workbook = Workbook()
        self.workbook.remove(self.workbook.active)
        self.footers_workbook = Workbook()
        self.footers_workbook.active.append([
            "page_number",
            "table_number",
            "footer_text",
        ])

    def save_output(self):
        stem = self.relative_path.stem
        output_dir = (self.root_dir_path / "results" / self.relative_path).parent / stem
        output_dir.mkdir(parents=True, exist_ok=True)
        output_xlsx_path = output_dir / f"{self.relative_path.stem}.xlsx"
        self.workbook.save(output_xlsx_path)
        shutil.copy(self.path, output_dir)
        footers_xlsx_path = output_dir / f"footers_{self.relative_path.stem}.xlsx"
        self.footers_workbook.save(footers_xlsx_path)
