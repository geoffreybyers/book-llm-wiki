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
