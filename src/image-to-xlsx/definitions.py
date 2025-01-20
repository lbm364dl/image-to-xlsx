import os

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH = os.path.join(ROOT_DIR, "input")
OUTPUT_PATH = os.path.join(ROOT_DIR, "output")
MAX_TEXTRACT_DIMENSION = 3495
# 5 MB
MAX_TEXTRACT_SYNC_SIZE = 5 * 1024 * 1024
