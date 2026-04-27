"""Kindle format preprocessing — converts .azw3/.mobi to .epub via calibre."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


KINDLE_EXTS = {".azw3", ".mobi"}


def is_kindle_format(path: Path) -> bool:
    return Path(path).suffix.lower() in KINDLE_EXTS


def convert_kindle_to_epub(src: Path) -> Path:
    """Run calibre's ebook-convert to produce a temp .epub. Returns the temp path.

    Caller is responsible for cleanup (typically via tempfile.TemporaryDirectory
    in the calling scope, or by passing the parent dir as tempdir).
    """
    src = Path(src).resolve()
    if not is_kindle_format(src):
        raise ValueError(f"Not a Kindle format: {src.suffix}")
    if shutil.which("ebook-convert") is None:
        raise RuntimeError(
            "ebook-convert not found in PATH. Install calibre to convert "
            ".azw3/.mobi files (e.g. `apt install calibre`)."
        )
    tmp_dir = Path(tempfile.mkdtemp(prefix="book-llm-wiki-kindle-"))
    out = tmp_dir / (src.stem + ".epub")
    proc = subprocess.run(
        ["ebook-convert", str(src), str(out)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(
            f"ebook-convert failed (exit {proc.returncode}): {proc.stderr[-500:]}"
        )
    return out
