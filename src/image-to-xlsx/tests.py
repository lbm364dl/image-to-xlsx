from main import run
from utils import split_footnotes
import os
from pathlib import Path
import shutil


def test_surya_plus_paddle():
    input_path = Path("inputs/sample_table.png")
    output_dir = Path("inputs/results/sample_table")
    assert not os.path.isfile(output_dir / "sample_table.png")
    assert not os.path.isfile(output_dir / "sample_table.xlsx")
    run(input_path, unskew=1)
    assert os.path.isfile(output_dir / "sample_table.png")
    assert os.path.isfile(output_dir / "sample_table.xlsx")
    shutil.rmtree(output_dir)


def test_with_pdf_text():
    input_path = Path("inputs/StatisticalAbstract.1840.exports.pdf")
    output_dir = Path("inputs/results/StatisticalAbstract.1840.exports")
    assert not os.path.isfile(output_dir / "StatisticalAbstract.1840.exports.pdf")
    assert not os.path.isfile(output_dir / "StatisticalAbstract.1840.exports.xlsx")
    run(input_path, last_page=1, method="pdf-text")
    assert os.path.isfile(output_dir / "StatisticalAbstract.1840.exports.pdf")
    assert os.path.isfile(output_dir / "StatisticalAbstract.1840.exports.xlsx")
    shutil.rmtree(output_dir)


def test_textract():
    input_path = Path("inputs/StatisticalAbstract.1840.exports.pdf")
    output_dir = Path("inputs/results/StatisticalAbstract.1840.exports")
    assert not os.path.isfile(output_dir / "StatisticalAbstract.1840.exports.pdf")
    assert not os.path.isfile(output_dir / "StatisticalAbstract.1840.exports.xlsx")
    run(input_path, last_page=1, method="textract")
    assert os.path.isfile(output_dir / "StatisticalAbstract.1840.exports.pdf")
    assert os.path.isfile(output_dir / "StatisticalAbstract.1840.exports.xlsx")
    shutil.rmtree(output_dir)


def test_with_nlp_postprocess():
    input_path = Path("inputs/StatisticalAbstract.1840.exports.pdf")
    output_dir = Path("inputs/results/StatisticalAbstract.1840.exports")
    assert not os.path.isfile(output_dir / "StatisticalAbstract.1840.exports.pdf")
    assert not os.path.isfile(output_dir / "StatisticalAbstract.1840.exports.xlsx")
    run(input_path, last_page=1, method="pdf-text", nlp_postprocess=1)
    assert os.path.isfile(output_dir / "StatisticalAbstract.1840.exports.pdf")
    assert os.path.isfile(output_dir / "StatisticalAbstract.1840.exports.xlsx")
    shutil.rmtree(output_dir)


def test_extend_rows():
    input_path = Path("inputs/StatisticalAbstract.1840.exports.pdf")
    output_dir = Path("inputs/results/StatisticalAbstract.1840.exports")
    assert not os.path.isfile(output_dir / "StatisticalAbstract.1840.exports.pdf")
    assert not os.path.isfile(output_dir / "StatisticalAbstract.1840.exports.xlsx")
    run(input_path, last_page=1, extend_rows=1)
    assert os.path.isfile(output_dir / "StatisticalAbstract.1840.exports.pdf")
    assert os.path.isfile(output_dir / "StatisticalAbstract.1840.exports.xlsx")
    shutil.rmtree(output_dir)


def test_split_footnotes():
    s = "3) O 5) 545343 O o (4)"
    assert split_footnotes(s) == ("545343", ["3", "4", "5", "O"])
    s = "(3) 545343"
    assert split_footnotes(s) == ("545343", ["3"])
    s = "545343 6)"
    assert split_footnotes(s) == ("545343", ["6"])
    s = "Hongrie O 1)"
    assert split_footnotes(s) == ("Hongrie", ["1", "O"])
    s = "Hongrie o"
    assert split_footnotes(s) == ("Hongrie", ["O"])
    s = "Hongrie 0"
    assert split_footnotes(s) == ("Hongrie", ["O"])
    s = "0 Hongrie 0"
    assert split_footnotes(s) == ("Hongrie", ["O"])
    s = "12 034"
    assert split_footnotes(s) == ("12 034", [])
    s = "10 434"
    assert split_footnotes(s) == ("10 434", [])
    s = "10 034"
    assert split_footnotes(s) == ("10 034", [])
    s = "b)"
    assert split_footnotes(s) == ("", ["b"])
    s = "(3)"
    assert split_footnotes(s) == ("", ["3"])
