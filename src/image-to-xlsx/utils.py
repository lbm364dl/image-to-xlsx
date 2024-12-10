import os
import glob
from pathlib import Path


def get_document_paths(input_path):
    doc_paths = []

    if os.path.isdir(input_path):
        input_dir = Path(input_path)

        all_paths = glob.glob(
            os.path.join("**", "*.*"), root_dir=input_dir, recursive=True
        )
        exclude_results = glob.glob(
            os.path.join("results/**", "*.*"), root_dir=input_dir, recursive=True
        )
        doc_paths = list(set(all_paths) - set(exclude_results))
        print(exclude_results)
        print(doc_paths)

        for file in doc_paths:
            print(file)

        # doc_paths = [
        #     input_dir / path
        #     for path in os.listdir(input_path)
        #     if not os.path.isdir(input_dir / path)
        # ]
    else:
        doc_paths = [input_path]

    return doc_paths
