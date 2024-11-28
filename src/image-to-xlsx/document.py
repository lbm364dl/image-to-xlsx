from surya.input.load import load_from_file
from surya.settings import settings
from pathlib import Path


class Document:
    def __init__(self, input_path, results_dir):
        self.pages, _, _ = load_from_file(input_path, dpi=settings.IMAGE_DPI_HIGHRES)
        self.path = Path(input_path)
        self.file_name = self.path.stem
        self.extension = self.path.suffix
        self.document_results_dir = results_dir / self.file_name
        self.document_results_dir.mkdir(parents=True, exist_ok=True)
