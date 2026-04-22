# tests/test_environment.py
"""External-tool environment checks. epub2md is required; pandoc is optional
(only needed for PDF input, which is best-effort in v1)."""
import shutil

import pytest


def test_epub2md_installed():
    assert shutil.which("epub2md") is not None, (
        "epub2md not found on PATH. Install with: npm install -g epub2md"
    )


def test_pandoc_installed_or_skip():
    if shutil.which("pandoc") is None:
        pytest.skip(
            "pandoc not on PATH. Required only for PDF input (best-effort in v1). "
            "Install with: apt install pandoc  (or brew install pandoc)"
        )
