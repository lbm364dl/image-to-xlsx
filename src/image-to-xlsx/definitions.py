import re

INF = 10**9

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

NOT_NUMBER = 0
ONE_NUMBER = 1
AT_LEAST_TWO_NUMBERS = 2
