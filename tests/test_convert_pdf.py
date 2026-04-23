# tests/test_convert_pdf.py
from pathlib import Path
from unittest.mock import patch

import pytest

from book_llm_wiki.convert.pdf import convert_pdf_to_markdown


def test_convert_pdf_requires_existing_file(tmp_path: Path):
    out = tmp_path / "out.md"
    with pytest.raises(FileNotFoundError):
        convert_pdf_to_markdown(tmp_path / "nope.pdf", out)


def test_convert_pdf_flags_low_quality_when_few_headings(tmp_path: Path):
    src = tmp_path / "fake.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    out = tmp_path / "out.md"

    def fake_pandoc(*args, **kwargs):
        out.write_text("No headings in this output. Just prose. " * 1500)
        class R:
            returncode = 0
        return R()

    with patch("book_llm_wiki.convert.pdf.shutil.which", return_value="/usr/bin/pandoc"), \
         patch("book_llm_wiki.convert.pdf.subprocess.run", side_effect=fake_pandoc):
        result = convert_pdf_to_markdown(src, out)

    assert result.conversion_quality == "low"
    assert result.chapter_count == 0


def test_convert_pdf_flags_high_quality_when_many_headings(tmp_path: Path):
    src = tmp_path / "fake.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    out = tmp_path / "out.md"

    def fake_pandoc(*args, **kwargs):
        out.write_text(
            "# Chapter 1\n\nStuff.\n\n"
            "# Chapter 2\n\nMore stuff.\n\n"
            "# Chapter 3\n\nEven more stuff.\n\n"
            "# Chapter 4\n\nYet more.\n"
        )
        class R:
            returncode = 0
        return R()

    with patch("book_llm_wiki.convert.pdf.shutil.which", return_value="/usr/bin/pandoc"), \
         patch("book_llm_wiki.convert.pdf.subprocess.run", side_effect=fake_pandoc):
        result = convert_pdf_to_markdown(src, out)

    assert result.conversion_quality == "high"
    assert result.chapter_count == 4
