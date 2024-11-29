It is highly recommended to use a virtual environment. Inside it you can then run
```
python -m pip install -r requirements.txt --no-deps
```
TODO: Currently it will probably fail in Windows due to some dependency errors.

For trying to reproduce the code if requirements.txt fails, do the following installs in order:
TODO: it seems this also fails (on runtime) due to some C++ segfault, again something about dependencies.

```
# install paddlepaddle
python -m pip install paddlepaddle==3.0.0b2 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
# install paddlex
python -m pip install https://paddle-model-ecology.bj.bcebos.com/paddlex/whl/paddlex-3.0.0b2-py3-none-any.whl
# install surya-ocr
python -m pip install surya-ocr
# install tabled-pdf
python -m pip install tabled-pdf
# install openai for postprocessing (optional)
python -m pip install openai
# override opencv version
python -m pip install opencv-python==4.5.5.64
```

The previous step-by-step installations will likely also install some nvidia dependencies along with surya-ocr,
which in theory should not, if you want to run on CPU. For this we should first manually install CPU version of pytorch...

```
# install torch
python -m pip install torch # Mac/Windows (should be CPU by default)
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu # Linux
# install paddlepaddle
python -m pip install paddlepaddle==3.0.0b2 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
# install paddlex
python -m pip install https://paddle-model-ecology.bj.bcebos.com/paddlex/whl/paddlex-3.0.0b2-py3-none-any.whl
# install surya-ocr
python -m pip install surya-ocr
# install tabled-pdf
python -m pip install tabled-pdf
# install openai for postprocessing (optional)
python -m pip install openai
# override opencv version
python -m pip install opencv-python==4.5.5.64
```

The previous step-by-step installation still fails. The only one that seems to work right now is Linux using --no-deps installation from requirements.txt,
which also includes some nvidia dependencies which again should not be needed for running on CPU but it seems they come with some libraries that fix
the C++ segfault. Still, these same nvidia dependencies seem to be the ones failing on Windows installation.
