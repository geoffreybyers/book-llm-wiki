# tests/test_ingest.py
from pathlib import Path

from book_summarizer.ingest import ingest_file
from book_summarizer.vault import bootstrap_vault, is_ingested, read_queue


def test_ingest_file_populates_vault(normal_epub: Path, tmp_vault: Path):
    bootstrap_vault(tmp_vault)
    result = ingest_file(normal_epub, tmp_vault)

    # Returns summary
    assert result["title"] == "The Test Book"
    assert result["author"] == "Test Author"
    assert result["status"] == "queued"

    # Raw file exists
    raw = tmp_vault / "raw" / "books" / "The Test Book - Test Author.md"
    assert raw.exists()

    # Collected and queue updated
    assert is_ingested(tmp_vault, "The Test Book", "Test Author")
    assert read_queue(tmp_vault) == [{"title": "The Test Book", "author": "Test Author"}]


def test_ingest_file_skips_already_ingested(normal_epub: Path, tmp_vault: Path):
    bootstrap_vault(tmp_vault)
    ingest_file(normal_epub, tmp_vault)
    result = ingest_file(normal_epub, tmp_vault)
    assert result["status"] == "skipped"
    assert len(read_queue(tmp_vault)) == 1


def test_ingest_pdf_origin_flags_low_quality(pdf_origin_epub: Path, tmp_vault: Path):
    bootstrap_vault(tmp_vault)
    result = ingest_file(pdf_origin_epub, tmp_vault)
    assert result["conversion_quality"] == "low"
    # Still queued for analysis (fallback path will handle it in Tier 2)
    assert result["status"] == "queued"
