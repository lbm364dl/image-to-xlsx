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

For trying to reproduce the code if requirements.txt or requirements_windows.txt fails, do the following installs in order:

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

To use the program, you can run `python main.py --help` from src/image-to-xlsx to see the help for all options:

```
usage: main.py [-h] [--first-page FIRST_PAGE] [--last-page LAST_PAGE] [--binarize {0,1}] [--nlp-postprocess {0,1}] [--text-language TEXT_LANGUAGE] input_path

Convert tables from image/pdf to xlsx.

positional arguments:
  input_path            Path to PDF or image file.

options:
  -h, --help            show this help message and exit
  --first-page FIRST_PAGE
                        First page to process (for PDFs only, 1-indexed). Default start of document
  --last-page LAST_PAGE
                        Last page to process (for PDFs only, 1-indexed). Default end of document
  --binarize {0,1}      Use binarization, i.e. force black & white pixels (0 for no, 1 for yes). Default 0
  --nlp-postprocess {0,1}
                        Use non-free OpenAI to try to fix OCR misspellings (0 for no, 1 for yes). Default 0
  --text-language TEXT_LANGUAGE
                        ISO2 language code for NLP postprocessing suggesting the language of the text for misspellings fixing. Default 'en'
```
For example, you can run `python main.py path/to/input.pdf`.
