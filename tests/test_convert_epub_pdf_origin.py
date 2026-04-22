# tests/test_convert_epub_pdf_origin.py
from pathlib import Path

from book_summarizer.convert.epub import is_pdf_origin


def test_detect_pdf_origin_via_generator(pdf_origin_epub: Path):
    assert is_pdf_origin(pdf_origin_epub) is True


def test_normal_epub_is_not_pdf_origin(normal_epub: Path):
    assert is_pdf_origin(normal_epub) is False
