# tests/test_convert_kindle.py
import shutil
from pathlib import Path

import pytest

from book_llm_wiki.convert.kindle import (
    KINDLE_EXTS,
    convert_kindle_to_epub,
    is_kindle_format,
)


def test_is_kindle_format_recognises_extensions(tmp_path: Path):
    assert is_kindle_format(tmp_path / "book.azw3")
    assert is_kindle_format(tmp_path / "book.mobi")
    assert is_kindle_format(tmp_path / "BOOK.AZW3")  # case-insensitive
    assert not is_kindle_format(tmp_path / "book.epub")
    assert not is_kindle_format(tmp_path / "book.pdf")


def test_kindle_exts_contains_expected():
    assert ".azw3" in KINDLE_EXTS
    assert ".mobi" in KINDLE_EXTS


def test_convert_kindle_rejects_non_kindle(tmp_path: Path):
    src = tmp_path / "book.epub"
    src.touch()
    with pytest.raises(ValueError):
        convert_kindle_to_epub(src)


@pytest.mark.skipif(
    shutil.which("ebook-convert") is None,
    reason="calibre's ebook-convert not installed",
)
def test_convert_kindle_produces_epub(tmp_path: Path):
    """End-to-end: needs calibre. Uses any .azw3 fixture if present, else skip."""
    fixtures_dir = Path(__file__).parent / "fixtures"
    azw3_fixtures = list(fixtures_dir.glob("*.azw3")) if fixtures_dir.exists() else []
    if not azw3_fixtures:
        pytest.skip("No .azw3 fixture available for end-to-end test")
    out = convert_kindle_to_epub(azw3_fixtures[0])
    try:
        assert out.exists()
        assert out.suffix == ".epub"
        assert out.stat().st_size > 0
    finally:
        shutil.rmtree(out.parent, ignore_errors=True)
