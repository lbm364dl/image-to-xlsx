import os
import glob
import re
import configparser
import io
import math
import sys
from pathlib import Path
from PIL import Image
from definitions import MAX_TEXTRACT_DIMENSION


def file_extension(name):
    return name.split(".")[-1]


def save_workbook(workbook, where_to_save):
    if not workbook.sheetnames:
        sheet = workbook.create_sheet("Empty")
        sheet["A1"] = "Nothing detected"

    workbook.save(where_to_save)


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

    return Path(root_dir_path), [Path(p) for p in doc_paths]


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

    clean_footnotes = set()
    for footnote in all_footnotes:
        clean_text = clean_text.replace(footnote, "")
        clean_footnote = footnote.strip(" ()")
        if clean_footnote in "Oo":
            clean_footnote = "O"
        clean_footnotes.add(clean_footnote)

    return clean_text, sorted(clean_footnotes)


def maybe_reduce_resolution(img):
    width, height = img.size
    max_dim = max(width, height)
    if max_dim > MAX_TEXTRACT_DIMENSION:
        scale_factor = MAX_TEXTRACT_DIMENSION / max_dim
        new_size = (int(width * scale_factor), int(height * scale_factor))
        img = img.resize(new_size, Image.LANCZOS)

    return img


def _read_aws_credentials(file):
    config: configparser.ConfigParser = configparser.ConfigParser()
    config.read(Path.home() / ".aws" / file)
    return config


def get_aws_credentials():
    conf = _read_aws_credentials("config")
    credentials = _read_aws_credentials("credentials")
    return {
        "region_name": conf.get("default", "region", fallback=None),
        "aws_access_key_id": credentials.get(
            "default", "aws_access_key_id", fallback=None
        ),
        "aws_secret_access_key": credentials.get(
            "default", "aws_secret_access_key", fallback=None
        ),
    }


# https://stackoverflow.com/a/52281257
def image_below_size(im, target_size):
    # Min and Max quality
    q_min, q_max = 25, 96
    # Highest acceptable quality found
    result_img = None
    while q_min <= q_max:
        m = math.floor((q_min + q_max) / 2)

        # Encode into memory and get size
        buffer = io.BytesIO()
        im.save(buffer, format="JPEG", quality=m)
        s = buffer.getbuffer().nbytes

        if s <= target_size:
            result_img = buffer
            q_min = m + 1
        elif s > target_size:
            q_max = m - 1

    if result_img:
        return Image.open(result_img)
    else:
        raise Exception("No acceptable quality factor found")
