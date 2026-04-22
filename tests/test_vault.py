# tests/test_vault.py
from pathlib import Path

from book_summarizer.vault import bootstrap_vault


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
