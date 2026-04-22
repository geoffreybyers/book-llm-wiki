# tests/test_smoke_real_books.py
"""Optional smoke tests against real EPUBs from ~/dev/book-downloader/downloads/.

These tests validate end-to-end behavior against actual books. They skip if
the books are not present locally (e.g. CI).
"""
from pathlib import Path

import pytest

from book_summarizer.ingest import ingest_file
from book_summarizer.vault import bootstrap_vault, _read_collected_rows

DEEP_WORK = Path(
    "/home/administrator/dev/book-downloader/downloads/Deep Work - Cal Newport/"
    "Deep Work - Cal Newport - 8e4567c95342c815b075cf9376542d33.epub"
)
ATOMIC_HABITS_DIR = Path(
    "/home/administrator/dev/book-downloader/downloads/Atomic Habits - James Clear/"
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


@pytest.mark.skipif(not ATOMIC_HABITS_DIR.exists(), reason="Atomic Habits not available locally")
def test_atomic_habits_flags_pdf_origin(tmp_vault: Path):
    epubs = list(ATOMIC_HABITS_DIR.glob("*.epub"))
    assert epubs, f"no EPUB in {ATOMIC_HABITS_DIR}"
    bootstrap_vault(tmp_vault)
    result = ingest_file(epubs[0], tmp_vault)
    assert result["conversion_quality"] == "low"
    rows = _read_collected_rows(tmp_vault)
    assert any(r["conversion_quality"] == "low" for r in rows)
