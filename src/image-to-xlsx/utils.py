import os
from pathlib import Path


def get_document_paths(input_path):
    doc_paths = []

    if os.path.isdir(input_path):
        input_dir = Path(input_path)
        doc_paths = [
            input_dir / path
            for path in os.listdir(input_path)
            if not os.path.isdir(input_dir / path)
        ]
    else:
        doc_paths = [input_path]

    return doc_paths
