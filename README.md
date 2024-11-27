For trying to reproduce the code if requirements.txt fails, do the following installs in order.
It seems this was enough for my case.

```
# install numpy
python -m pip install numpy
# install paddlepaddle
python -m pip install paddlepaddle==3.0.0b2 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
# install paddlex
python -m pip install https://paddle-model-ecology.bj.bcebos.com/paddlex/whl/paddlex-3.0.0b1-py3-none-any.whl
# install surya-ocr
python -m pip install surya-ocr
# install tabled-pdf
python -m pip install tabled-pdf
# install openai for postprocessing
python -m pip install openai
# install python-dotenv for reading env vars
python -m pip install python-dotenv
```
