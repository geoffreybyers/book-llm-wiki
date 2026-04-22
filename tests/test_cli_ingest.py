# tests/test_cli_ingest.py
import subprocess
import sys
from pathlib import Path


def test_cli_ingest_end_to_end(normal_epub: Path, tmp_vault: Path, tmp_path: Path):
    # Prepare a books.yaml pointing at tmp_vault
    cfg = tmp_path / "books.yaml"
    cfg.write_text(
        f"defaults:\n  vault_path: {tmp_vault}\n"
        "  default_lens: general\n"
        "lenses:\n  general: test\n"
    )

    result = subprocess.run(
        [sys.executable, "-m", "book_summarizer", "--config", str(cfg),
         "ingest", str(normal_epub)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "The Test Book" in result.stdout
    assert (tmp_vault / "raw" / "books" / "The Test Book - Test Author.md").exists()


def test_cli_status_prints_ingested_books(normal_epub: Path, tmp_vault: Path, tmp_path: Path):
    cfg = tmp_path / "books.yaml"
    cfg.write_text(
        f"defaults:\n  vault_path: {tmp_vault}\n  default_lens: general\n"
        "lenses:\n  general: test\n"
    )
    # Ingest first
    subprocess.run(
        [sys.executable, "-m", "book_summarizer", "--config", str(cfg),
         "ingest", str(normal_epub)],
        check=True, capture_output=True,
    )
    # Now status
    result = subprocess.run(
        [sys.executable, "-m", "book_summarizer", "--config", str(cfg), "status"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "The Test Book" in result.stdout
    assert "queued" in result.stdout


def test_cli_reset_requeues_analyzed_book(normal_epub: Path, tmp_vault: Path, tmp_path: Path):
    cfg = tmp_path / "books.yaml"
    cfg.write_text(
        f"defaults:\n  vault_path: {tmp_vault}\n  default_lens: general\n"
        "lenses:\n  general: test\n"
    )
    subprocess.run(
        [sys.executable, "-m", "book_summarizer", "--config", str(cfg),
         "ingest", str(normal_epub)],
        check=True, capture_output=True,
    )
    # Simulate "analyzed" state by rewriting collected.md manually
    collected = tmp_vault / "collected.md"
    text = collected.read_text().replace("| queued ", "| analyzed ")
    collected.write_text(text)

    result = subprocess.run(
        [sys.executable, "-m", "book_summarizer", "--config", str(cfg),
         "reset", "The Test Book - Test Author"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "re-queued" in result.stdout

    # collected.md flipped back to queued
    assert "queued" in collected.read_text()
    # analysis_queue.md contains the book again
    q = (tmp_vault / "analysis_queue.md").read_text()
    assert "The Test Book - Test Author" in q
