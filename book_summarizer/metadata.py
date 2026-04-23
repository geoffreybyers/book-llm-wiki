"""Extract title/author/year from EPUB, PDF, or markdown input."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from book_summarizer.convert.epub import epub_info


def _parse_parent_dir(path: Path) -> dict:
    """Parse the immediate parent directory name as 'Title - Author'.

    The book-downloader convention is `~/downloads/{Title - Author}/<file>.epub`,
    which is the user's curated source of truth for canonical naming. Splitting
    the parent dir on the FIRST ' - ' handles authors with hyphenated names and
    titles that contain em-dashes without the typical ' - ' spacing.
    """
    parent = path.parent.name
    parts = [p.strip() for p in parent.split(" - ", 1)]
    if len(parts) == 2 and parts[0] and parts[1]:
        return {"title": parts[0], "author": parts[1], "year": None}
    return {}


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
    """Return {'title': str, 'author': str, 'year': str | None}.

    Priority for (title, author): parent directory name `Title - Author`, then
    file stem parsing, then embedded file metadata. The parent-dir convention
    is the user's curated canonical naming and overrides EPUB OPF metadata,
    which is routinely malformed (author in title, "Last, First" inversions).
    EPUB/markdown-frontmatter year is still preferred since filenames rarely
    carry it.
    """
    path = Path(path)
    ext = path.suffix.lower()

    parent_guess = _parse_parent_dir(path)
    filename_guess = _parse_filename(path)
    primary = parent_guess or filename_guess

    embedded_year = None
    if ext == ".epub":
        info = epub_info(path)
        embedded_year = info.get("year")
    elif ext in {".md", ".markdown"}:
        fm = _extract_markdown_frontmatter(path)
        embedded_year = fm.get("year")

    return {
        "title": primary.get("title", ""),
        "author": primary.get("author", ""),
        "year": embedded_year or primary.get("year"),
    }
