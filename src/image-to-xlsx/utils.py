import os
import glob
import re
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


def split_footnotes(text):
    clean_text = text
    end_footnote = re.findall(r"\s\(?\S+?\)", text)
    start_footnote = re.findall(r"\(?\S+?\)\s", text)
    only_footnote = re.findall(r"^\(?\S+?\)$", text)
    circle_footnote_after = re.findall(r"(\s[Oo])(?=$|\s)", text)
    circle_footnote_before = re.findall(r"(?:^|\s)([Oo]\s)", text)
    all_footnotes = (
        end_footnote
        + start_footnote
        + circle_footnote_after
        + circle_footnote_before
        + only_footnote
    )
    clean_footnotes = set()
    for footnote in all_footnotes:
        clean_text = clean_text.replace(footnote, "")
        clean_footnote = footnote.strip(" ()")
        if clean_footnote in "Oo":
            clean_footnote = "O"
        clean_footnotes.add(clean_footnote)

    return clean_text, sorted(clean_footnotes)
