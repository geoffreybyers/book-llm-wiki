# tests/test_environment.py
"""Assert external tools required by Tier 1 are installed."""
import shutil


def test_epub2md_installed():
    assert shutil.which("epub2md") is not None, (
        "epub2md not found on PATH. Install with: npm install -g epub2md"
    )


def test_pandoc_installed():
    assert shutil.which("pandoc") is not None, (
        "pandoc not found on PATH. Install with: apt install pandoc  (or brew install pandoc)"
    )
