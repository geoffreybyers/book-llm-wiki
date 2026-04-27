# tests/test_smoke_real_books.py
"""Optional smoke tests against real EPUBs from ``<repo>/downloads/``.

These tests validate end-to-end behavior against actual books. They skip if
the books are not present locally (e.g. CI).
"""
from pathlib import Path

import pytest

from book_llm_wiki.ingest import ingest_file
from book_llm_wiki.vault import bootstrap_vault

REPO_ROOT = Path(__file__).resolve().parents[1]
DEEP_WORK = (
    REPO_ROOT
    / "downloads"
    / "Deep Work - Cal Newport"
    / "Deep Work - Cal Newport - 8e4567c95342c815b075cf9376542d33.epub"
)


@pytest.mark.skipif(not DEEP_WORK.exists(), reason="Deep Work EPUB not available locally")
def test_deep_work_ingest_produces_chapter_structure(tmp_vault: Path):
    bootstrap_vault(tmp_vault)
    result = ingest_file(DEEP_WORK, tmp_vault)
    assert result["status"] == "queued"
    assert result["title"] == "Deep Work"
    assert result["conversion_quality"] == "high"
    # Deep Work has 8 chapter-classed sections (Chapters 1-3, Rules 1-4,
    # Conclusion) once Parts are correctly excluded from the chapter count.
    assert result["chapters"] >= 8

    raw = tmp_vault / "raw" / "books" / "Deep Work - Cal Newport" / "Deep Work - Cal Newport.md"
    assert raw.exists()
    text = raw.read_text()
    # 8 explicit chapter headings (Parts are now their own class, not chapters)
    chapter_headings = [l for l in text.splitlines() if l.startswith("# Chapter ")]
    assert len(chapter_headings) >= 8
    # Images folder copied next to the markdown
    assert (raw.parent / "images").is_dir(), "images folder should be copied alongside the markdown"
