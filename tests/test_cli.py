# tests/test_cli.py
import subprocess
import sys


def test_cli_help_lists_subcommands():
    result = subprocess.run(
        [sys.executable, "-m", "book_summarizer", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "ingest" in result.stdout
    assert "status" in result.stdout
    assert "reset" in result.stdout
