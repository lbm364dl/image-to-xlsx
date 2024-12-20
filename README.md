WIP

It is highly recommended to use a virtual environment. After cloning this repository, from its root directory do:

Linux:
```
python3 -m venv env
source env/bin/activate
python -m pip install -r requirements.txt --no-deps
```

Windows:
```
python3 -m venv env
env\Scripts\activate
python -m pip install -r requirements_windows.txt --no-deps
```

For trying to reproduce the code if `requirements.txt` or `requirements_windows.txt` fails, do the following installs in order:

```
# install torch (choose one)
python -m pip install torch # Mac/Windows (should be CPU by default)
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu # Linux
# install paddlepaddle
python -m pip install paddlepaddle==3.0.0b2 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
# install paddlex
python -m pip install https://paddle-model-ecology.bj.bcebos.com/paddlex/whl/paddlex-3.0.0b2-py3-none-any.whl
# install tabled-pdf
python -m pip install tabled-pdf==0.1.4
# install openai for postprocessing (optional)
python -m pip install openai
```

To use the program, you can run `python main.py --help` from `src/image-to-xlsx` to see the help for all options:

```
usage: main.py [-h] [--method {textract,pdf-text,surya+paddle,textract-pickle-debug}] [--first-page FIRST_PAGE] [--last-page LAST_PAGE] [--binarize {0,1}] [--unskew {0,1}]
               [--nlp-postprocess {0,1}] [--nlp-postprocess-prompt-file NLP_POSTPROCESS_PROMPT_FILE] [--text-language TEXT_LANGUAGE] [--show-detected-boxes {0,1}]
               [--extend-rows {0,1}] [--image-pad IMAGE_PAD] [--compute-prefix COMPUTE_PREFIX] [--fixed-decimal-places FIXED_DECIMAL_PLACES]
               [--textract-response-pickle-file TEXTRACT_RESPONSE_PICKLE_FILE]
               input_path

Convert tables from image/pdf to xlsx.

positional arguments:
  input_path            Path to PDF or image file.

options:
  -h, --help            show this help message and exit
  --method {textract,pdf-text,surya+paddle,textract-pickle-debug}
                        Method to use for table recognition. Default surya+paddle. Methods:
                        - surya+paddle: opensource AI table recognition using surya library and OCR each cell using Paddle
                        - pdf-text: use PyMuPDF library to recognize the table (using internal PDF text), if you know the PDF comes with text
  --first-page FIRST_PAGE
                        First page to process (for PDFs only, 1-indexed). Default start of document
  --last-page LAST_PAGE
                        Last page to process (for PDFs only, 1-indexed). Default end of document
  --binarize {0,1}      Use binarization, i.e. force black & white pixels (0 for no, 1 for yes). Default 0
  --unskew {0,1}        Try to detect and undo image rotation (0 for no, 1 for yes). Default 0
  --nlp-postprocess {0,1}
                        Use non-free OpenAI to try to fix OCR misspellings (0 for no, 1 for yes). Default 0
  --nlp-postprocess-prompt-file NLP_POSTPROCESS_PROMPT_FILE
                        Use a custom prompt message for NLP postprocessing. Indicate the path of the text file with the prompt message. By default, a generic one for cleaning cell typo
s is used.
  --text-language TEXT_LANGUAGE
                        ISO2 language code for NLP postprocessing suggesting the language of the text for misspellings fixing. Default 'en'
  --show-detected-boxes {0,1}
                        Open image with detected boxes for each table for debugging (0 for no, 1 for yes). Default 0
  --extend-rows {0,1}   If there is a row that tries to include several texts into the same cell, try to extend to a new row below (0 for no, 1 for yes). Default 0, meaning all texts t
o the same cell are just joined with a space separator
  --image-pad IMAGE_PAD
                        When running OCR for each individual cell, add this amount of pixels in padding on the cropped image on all four sides. More or less padding may help for better
 OCR text recognition. Default 100 pixels
  --compute-prefix COMPUTE_PREFIX
                        For debugging, compute only this amount of cells in the output table, since it can take too long to compute all of them. Default all cells
  --fixed-decimal-places FIXED_DECIMAL_PLACES
                        Forcefully write a decimal point this number of places to the left of the last digit. By default no decimal points are added.
  --textract-response-pickle-file TEXTRACT_RESPONSE_PICKLE_FILE
                        Path to pkl file with Textract response for a particular page. Use for debugging and not calling the API all the time
```
For example, you can run `python main.py path/to/input.pdf`.
