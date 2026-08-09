# tests/test_ingest.py
from pathlib import Path

from book_llm_wiki.ingest import ingest_file, ingest_directory
from book_llm_wiki.vault import (
    _read_collected_rows,
    bootstrap_vault,
    is_ingested,
    read_queue,
)


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
    # Build two EPUBs in nested subdirs (mirroring downloader layout)
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


def _good_epub(path: Path, title: str, author: str) -> Path:
    from tests.conftest import _build_epub
    return _build_epub(path, title, author, "2020", sections=[
        ("Cover", "x"), ("Chapter 1", "a " * 40), ("Chapter 2", "b " * 40),
    ])


def test_ingest_directory_skips_underscore_prefixed_paths(tmp_path: Path, tmp_vault: Path):
    """Housekeeping files and quarantine dirs are not books.

    `_STATUS.md` and `downloads/_quarantine_wrong_match/` were both being
    ingested, adding junk rows that reappeared on every run.
    """
    quarantine = tmp_path / "_quarantine_wrong_match"
    quarantine.mkdir()
    _good_epub(quarantine / "wrong.epub", "Wrong Match", "Nobody")
    (tmp_path / "_STATUS.md").write_text("# scratch notes\n", encoding="utf-8")

    good_dir = tmp_path / "Real Book - Rita"
    good_dir.mkdir()
    _good_epub(good_dir / "real.epub", "Real Book", "Rita")

    results = ingest_directory(tmp_path, tmp_vault)

    titles = {r["title"] for r in results}
    assert titles == {"Real Book"}
    assert not is_ingested(tmp_vault, "Wrong Match", "Nobody")
    assert not is_ingested(tmp_vault, "_STATUS", "")


def test_ingest_directory_continues_past_unreadable_file(tmp_path: Path, tmp_vault: Path):
    """One corrupt EPUB must not abort the whole run.

    A truncated/corrupt file raises BadZipFile out of extract_metadata, which
    used to propagate and kill the entire directory ingest.
    """
    bad_dir = tmp_path / "Broken Book - Bob"
    bad_dir.mkdir()
    (bad_dir / "broken.epub").write_bytes(b"this is definitely not a zip file")

    for name, title, author in [("Aaa - Ann", "Aaa", "Ann"), ("Zzz - Zed", "Zzz", "Zed")]:
        d = tmp_path / name
        d.mkdir()
        _good_epub(d / "book.epub", title, author)

    results = ingest_directory(tmp_path, tmp_vault)

    assert len(results) == 3
    by_status = {}
    for r in results:
        by_status.setdefault(r["status"], []).append(r["title"])
    assert sorted(by_status["queued"]) == ["Aaa", "Zzz"]
    assert len(by_status["failed"]) == 1

    # The good books really landed in the vault
    assert is_ingested(tmp_vault, "Aaa", "Ann")
    assert is_ingested(tmp_vault, "Zzz", "Zed")


def test_ingest_file_reports_unreadable_file_as_failed(tmp_path: Path, tmp_vault: Path):
    """A corrupt file is reported as failed rather than raising."""
    bootstrap_vault(tmp_vault)
    bad = tmp_path / "corrupt.epub"
    bad.write_bytes(b"not a zip")

    result = ingest_file(bad, tmp_vault)

    assert result["status"] == "failed"
    assert result["chapters"] == 0
    assert "BadZipFile" in result["error"]


def test_ingest_file_writes_nothing_for_unreadable_file(tmp_path: Path, tmp_vault: Path):
    """No collected row: the only available title would be the raw filename."""
    bootstrap_vault(tmp_vault)
    bad = tmp_path / "Some Book - Author - deadbeef.epub"
    bad.write_bytes(b"not a zip")

    ingest_file(bad, tmp_vault)
    ingest_file(bad, tmp_vault)

    assert _read_collected_rows(tmp_vault) == []
    assert read_queue(tmp_vault) == []
