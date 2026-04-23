# tests/test_smoke_real_books.py
"""Optional smoke tests against real EPUBs from ~/dev/book-downloader/downloads/.

These tests validate end-to-end behavior against actual books. They skip if
the books are not present locally (e.g. CI).
"""
from pathlib import Path

import pytest

from book_summarizer.ingest import ingest_file
from book_summarizer.vault import bootstrap_vault

DEEP_WORK = Path(
    "/home/administrator/dev/book-downloader/downloads/Deep Work - Cal Newport/"
    "Deep Work - Cal Newport - 8e4567c95342c815b075cf9376542d33.epub"
)


@pytest.mark.skipif(not DEEP_WORK.exists(), reason="Deep Work EPUB not available locally")
def test_deep_work_ingest_produces_chapter_structure(tmp_vault: Path):
    bootstrap_vault(tmp_vault)
    result = ingest_file(DEEP_WORK, tmp_vault)
    assert result["status"] == "queued"
    assert result["title"] == "Deep Work"
    assert result["conversion_quality"] == "high"
    assert result["chapters"] >= 10  # Deep Work has ~15 chapter-classed sections

    raw = tmp_vault / "raw" / "books" / "Deep Work - Cal Newport.md"
    assert raw.exists()
    text = raw.read_text()
    # At least 10 explicit chapter headings
    chapter_headings = [l for l in text.splitlines() if l.startswith("# Chapter ")]
    assert len(chapter_headings) >= 10
