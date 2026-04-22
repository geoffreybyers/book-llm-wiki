# tests/test_convert_epub.py
from pathlib import Path

from book_summarizer.convert.epub import epub_info, epub_structure


def test_epub_info_returns_title_and_author(normal_epub: Path):
    info = epub_info(normal_epub)
    assert info["title"] == "The Test Book"
    assert info["author"] == "Test Author"


def test_epub_structure_returns_ordered_sections(normal_epub: Path):
    sections = epub_structure(normal_epub)
    names = [s["name"] for s in sections]
    assert names == [
        "Cover",
        "Title Page",
        "Chapter 1: Origins",
        "Chapter 2: Growth",
        "Chapter 3: Reflection",
        "Notes",
        "Copyright",
    ]
