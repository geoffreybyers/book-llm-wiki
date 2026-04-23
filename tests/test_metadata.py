# tests/test_metadata.py
from pathlib import Path

from book_llm_wiki.metadata import extract_metadata


def test_extract_metadata_from_epub(normal_epub: Path):
    md = extract_metadata(normal_epub)
    assert md["title"] == "The Test Book"
    assert md["author"] == "Test Author"
    assert md["year"] == "2024"


def test_fallback_to_filename_for_markdown(tmp_path: Path):
    p = tmp_path / "Deep Work - Cal Newport.md"
    p.write_text("# Chapter 1\n")
    md = extract_metadata(p)
    assert md["title"] == "Deep Work"
    assert md["author"] == "Cal Newport"


def test_frontmatter_title_wins_over_filename(tmp_path: Path):
    p = tmp_path / "Wrong Name - Wrong Author.md"
    p.write_text("---\ntitle: Real Title\nauthor: Real Author\nyear: 2021\n---\n# C1\n")
    md = extract_metadata(p)
    assert md["title"] == "Real Title"
    assert md["author"] == "Real Author"
    assert md["year"] == "2021"


def test_filename_without_separator_gives_title_only(tmp_path: Path):
    p = tmp_path / "Standalone.md"
    p.write_text("# Stuff\n")
    md = extract_metadata(p)
    assert md["title"] == "Standalone"
    assert md["author"] == ""
