import os
import glob
from pathlib import Path


def get_document_paths(input_path):
    doc_paths = []

    if os.path.isdir(input_path):
        root_dir_path = Path(input_path)

        all_paths = glob.glob(
            os.path.join("**", "*.*"), root_dir=root_dir_path, recursive=True
        )
        exclude_results = glob.glob(
            os.path.join("results/**", "*.*"), root_dir=root_dir_path, recursive=True
        )
        doc_paths = list(set(all_paths) - set(exclude_results))
    else:
        root_dir_path = os.path.dirname(input_path)
        doc_paths = [os.path.basename(input_path)]

    return root_dir_path, doc_paths
