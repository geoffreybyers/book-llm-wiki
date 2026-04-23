# tests/test_convert_markdown.py
from pathlib import Path

from book_llm_wiki.convert.markdown import convert_markdown_to_markdown


def test_structured_markdown_passes_through(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text(
        "# Chapter 1\nX.\n# Chapter 2\nY.\n# Chapter 3\nZ.\n"
    )
    out = tmp_path / "out.md"
    result = convert_markdown_to_markdown(src, out)
    assert result.conversion_quality == "high"
    assert result.chapter_count == 3
    assert out.read_text() == src.read_text()


def test_unstructured_markdown_is_low_quality(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text("Just prose, no headings at all. " * 500)
    out = tmp_path / "out.md"
    result = convert_markdown_to_markdown(src, out)
    assert result.conversion_quality == "low"
    assert result.chapter_count == 0
