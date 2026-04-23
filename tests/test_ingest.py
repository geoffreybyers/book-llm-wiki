# tests/test_ingest.py
from pathlib import Path

from book_summarizer.ingest import ingest_file, ingest_directory
from book_summarizer.vault import bootstrap_vault, is_ingested, read_queue


def test_ingest_file_populates_vault(normal_epub: Path, tmp_vault: Path):
    bootstrap_vault(tmp_vault)
    result = ingest_file(normal_epub, tmp_vault)

    # Returns summary
    assert result["title"] == "The Test Book"
    assert result["author"] == "Test Author"
    assert result["status"] == "queued"

    # Raw file exists
    raw = tmp_vault / "raw" / "books" / "The Test Book - Test Author" / "The Test Book - Test Author.md"
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


def test_ingest_directory_processes_all_epubs(tmp_path: Path, tmp_vault: Path):
    from tests.conftest import _build_epub
    # Build two EPUBs in nested subdirs (mirroring book-downloader layout)
    a_dir = tmp_path / "Book A - Alice/"
    b_dir = tmp_path / "Book B - Bob/"
    a_dir.mkdir()
    b_dir.mkdir()
    _build_epub(a_dir / "a.epub", "Book A", "Alice", "2020", sections=[
        ("Cover", "x"), ("Chapter 1", "a "*40), ("Chapter 2", "b "*40), ("Chapter 3", "c "*40)
    ])
    _build_epub(b_dir / "b.epub", "Book B", "Bob", "2021", sections=[
        ("Cover", "x"), ("Chapter 1", "a "*40), ("Chapter 2", "b "*40), ("Chapter 3", "c "*40)
    ])

    bootstrap_vault(tmp_vault)
    results = ingest_directory(tmp_path, tmp_vault)
    assert len(results) == 2
    statuses = [r["status"] for r in results]
    assert statuses == ["queued", "queued"]

    # Second call is idempotent
    results2 = ingest_directory(tmp_path, tmp_vault)
    statuses2 = [r["status"] for r in results2]
    assert statuses2 == ["skipped", "skipped"]
