"""Extract title/author/year from EPUB, PDF, or markdown input."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from book_summarizer.convert.epub import epub_info


def _parse_filename(path: Path) -> dict:
    stem = path.stem
    # Common conventions: "Title - Author.ext" or "Title - Author - <hash>.ext"
    parts = [p.strip() for p in stem.split(" - ")]
    if len(parts) >= 2:
        # If the last chunk looks like a 32-hex md5 or similar, drop it
        if re.fullmatch(r"[0-9a-f]{20,}", parts[-1], re.IGNORECASE):
            parts = parts[:-1]
    if len(parts) >= 2:
        return {"title": parts[0], "author": parts[1], "year": None}
    return {"title": parts[0], "author": "", "year": None}


def _extract_markdown_frontmatter(path: Path) -> dict:
    text = path.read_text()
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    try:
        data = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        return {}
    return {
        "title": data.get("title"),
        "author": data.get("author"),
        "year": str(data["year"]) if data.get("year") is not None else None,
    }


def extract_metadata(path: Path) -> dict:
    """Return {'title': str, 'author': str, 'year': str | None}."""
    path = Path(path)
    ext = path.suffix.lower()

    filename_guess = _parse_filename(path)

    if ext == ".epub":
        info = epub_info(path)
        return {
            "title": info.get("title") or filename_guess["title"],
            "author": info.get("author") or filename_guess["author"],
            "year": info.get("year") or filename_guess["year"],
        }

    if ext in {".md", ".markdown"}:
        fm = _extract_markdown_frontmatter(path)
        return {
            "title": fm.get("title") or filename_guess["title"],
            "author": fm.get("author") or filename_guess["author"],
            "year": fm.get("year") or filename_guess["year"],
        }

    # PDF and unknown: use filename only (PDF metadata extraction deferred)
    return filename_guess
