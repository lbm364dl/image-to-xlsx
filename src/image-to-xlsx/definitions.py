import os
import re

INF = 10**9
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH = os.path.join(ROOT_DIR, "input")
OUTPUT_PATH = os.path.join(ROOT_DIR, "output")
ONE_MB = 1024 * 1024
MAX_TEXTRACT_DIMENSION = 3495
# 5 MB
MAX_TEXTRACT_SYNC_SIZE = 5 * 1024 * 1024
MISSPELLINGS = {
    "H": 4,
    "U": 4,
    "u": 4,
    "I": 1,
    "Y": 7,
    "y": 7,
    "b": 6,
    "G": 6,
    "O": 0,
    "o": 0,
    "g": 9,
}
MISSPELLINGS_REGEX = re.compile("|".join(MISSPELLINGS.keys()))
