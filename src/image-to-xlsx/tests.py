from main import run
import os
from pathlib import Path
import shutil


def test_surya_plus_paddle():
    input_path = Path("inputs/sample_table.png")
    output_dir = Path("inputs/results/sample_table")
    assert not os.path.isfile(output_dir / "sample_table.png")
    assert not os.path.isfile(output_dir / "sample_table.xlsx")
    run(input_path)
    assert os.path.isfile(output_dir / "sample_table.png")
    assert os.path.isfile(output_dir / "sample_table.xlsx")
    shutil.rmtree(output_dir)


def test_with_pdf_text():
    input_path = Path("inputs/StatisticalAbstract.1840.exports.pdf")
    output_dir = Path("inputs/results/StatisticalAbstract.1840.exports")
    assert not os.path.isfile(output_dir / "StatisticalAbstract.1840.exports.pdf")
    assert not os.path.isfile(output_dir / "StatisticalAbstract.1840.exports.xlsx")
    run(input_path, method="pdf-text")
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
