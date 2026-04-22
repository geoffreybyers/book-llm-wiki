# tests/test_convert_dispatch.py
from pathlib import Path

import pytest

from book_summarizer.convert import convert, detect_format


def test_detect_format_by_extension(tmp_path: Path):
    (tmp_path / "book.epub").touch()
    (tmp_path / "book.pdf").touch()
    (tmp_path / "book.md").touch()
    (tmp_path / "book.markdown").touch()
    assert detect_format(tmp_path / "book.epub") == "epub"
    assert detect_format(tmp_path / "book.pdf") == "pdf"
    assert detect_format(tmp_path / "book.md") == "markdown"
    assert detect_format(tmp_path / "book.markdown") == "markdown"


def test_detect_format_rejects_unknown(tmp_path: Path):
    (tmp_path / "book.xyz").touch()
    with pytest.raises(ValueError):
        detect_format(tmp_path / "book.xyz")


def test_convert_dispatches_to_epub(normal_epub: Path, tmp_path: Path):
    out = tmp_path / "out.md"
    result = convert(normal_epub, out)
    assert result.conversion_quality == "high"
    assert result.chapter_count == 3
    assert result.mode == "structured"
