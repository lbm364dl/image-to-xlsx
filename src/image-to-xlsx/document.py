from surya.input.load import load_from_file
from surya.settings import settings

class Document:
    def __init__(self, path):
        self.pages, _, _ = load_from_file(path, dpi=settings.IMAGE_DPI_HIGHRES)
