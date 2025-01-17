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


def lowest_color():
    return "B22222"


def color_scale():
    return [
        (95, "00C957"),  # Emerald Green
        (90, "00FF7F"),  # Spring Green
        (85, "C0FF00"),  # Yellow-Green
        (80, "FFFF00"),  # Yellow
        (70, "FFC000"),  # Light Orange
        (60, "FF8000"),  # Orange
        (50, "FF4000"),  # Orange-Red
        (40, "FF2000"),  # Deep Orange-Red
        (0, lowest_color()),  # Crimson Red
    ]


def get_cell_color(confidence):
    if confidence is None:
        return None

    colors = color_scale()

    for threshold, color in colors:
        if confidence >= threshold:
            return color

    return lowest_color()


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
    if all_footnotes:
        print(all_footnotes, text)
    clean_footnotes = set()
    for footnote in all_footnotes:
        clean_text = clean_text.replace(footnote, "")
        clean_footnote = footnote.strip(" ()")
        if clean_footnote in "Oo":
            clean_footnote = "O"
        clean_footnotes.add(clean_footnote)

    return clean_text, sorted(clean_footnotes)
