# tests/test_vault.py
from pathlib import Path

from book_summarizer.vault import (
    append_collected_row,
    is_ingested,
    CollectedRow,
    bootstrap_vault,
    write_raw_book,
    raw_book_path,
)


def test_bootstrap_creates_expected_structure(tmp_vault: Path):
    bootstrap_vault(tmp_vault)
    expected_dirs = ["raw/books", "books", "entities", "concepts", "comparisons", "queries"]
    for d in expected_dirs:
        assert (tmp_vault / d).is_dir(), f"missing dir: {d}"
    expected_files = ["SCHEMA.md", "index.md", "log.md", "collected.md", "analysis_queue.md"]
    for f in expected_files:
        assert (tmp_vault / f).is_file(), f"missing file: {f}"

    # SCHEMA.md should contain the domain and placeholder taxonomy
    schema_text = (tmp_vault / "SCHEMA.md").read_text()
    assert "Book Summaries" in schema_text
    assert "Tag Taxonomy" in schema_text


def test_bootstrap_is_idempotent(tmp_vault: Path):
    bootstrap_vault(tmp_vault)
    (tmp_vault / "collected.md").write_text("custom-content\n")
    # Run again; existing files should NOT be overwritten
    bootstrap_vault(tmp_vault)
    assert (tmp_vault / "collected.md").read_text() == "custom-content\n"


def test_write_raw_book(tmp_vault: Path):
    dest = write_raw_book(
        vault_path=tmp_vault,
        title="Deep Work",
        author="Cal Newport",
        source_markdown_path=None,
        content="# Chapter 1 — Something\n\nBody.\n",
    )
    expected = tmp_vault / "raw" / "books" / "Deep Work - Cal Newport.md"
    assert dest == expected
    assert dest.read_text().startswith("# Chapter 1")


def test_raw_book_path_slugs_unsafe_chars(tmp_vault: Path):
    p = raw_book_path(tmp_vault, "Title: Subtitle / Slash", "Author Name")
    # Colons and slashes are replaced for filesystem safety
    assert ":" not in p.name
    assert "/" not in p.name.replace(" - ", "")
    assert p.parent == tmp_vault / "raw" / "books"


def test_append_collected_row_writes_entry(tmp_vault: Path):
    bootstrap_vault(tmp_vault)
    row = CollectedRow(
        title="Deep Work",
        author="Cal Newport",
        status="queued",
        chapters=15,
        conversion_quality="high",
        mode="structured",
        lens="",
        analyzed_at="",
        source=str(tmp_vault / "source.epub"),
    )
    append_collected_row(tmp_vault, row)
    text = (tmp_vault / "collected.md").read_text()
    assert "Deep Work" in text
    assert "Cal Newport" in text
    assert "queued" in text
    assert "high" in text


def test_is_ingested_after_append(tmp_vault: Path):
    bootstrap_vault(tmp_vault)
    assert is_ingested(tmp_vault, "Deep Work", "Cal Newport") is False
    row = CollectedRow(
        title="Deep Work", author="Cal Newport", status="queued",
        chapters=15, conversion_quality="high", mode="structured",
        lens="", analyzed_at="", source="/tmp/x.epub",
    )
    append_collected_row(tmp_vault, row)
    assert is_ingested(tmp_vault, "Deep Work", "Cal Newport") is True
