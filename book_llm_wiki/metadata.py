"""Extract title/author/year from EPUB, PDF, or markdown input."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from book_llm_wiki.convert.epub import epub_info


def _parse_parent_dir(path: Path) -> dict:
    """Parse the immediate parent directory name as 'Title - Author'.

    The downloader convention is `~/downloads/{Title - Author}/<file>.epub`,
    which is the curated source of truth for canonical naming. Splitting
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
    embedded file metadata (EPUB OPF / markdown frontmatter), then file-stem
    parsing. The parent-dir convention is the curated canonical naming and
    overrides EPUB OPF, which is routinely malformed. Filename is the weakest
    signal, used only when neither parent dir nor embedded metadata yields a
    title. Year always prefers embedded metadata since filenames rarely carry it.
    """
    path = Path(path)
    ext = path.suffix.lower()

    parent_guess = _parse_parent_dir(path)
    filename_guess = _parse_filename(path)

    embedded = {}
    if ext == ".epub":
        info = epub_info(path)
        embedded = {"title": info.get("title"), "author": info.get("author"), "year": info.get("year")}
    elif ext in {".md", ".markdown"}:
        fm = _extract_markdown_frontmatter(path)
        embedded = {"title": fm.get("title"), "author": fm.get("author"), "year": fm.get("year")}

    title = parent_guess.get("title") or embedded.get("title") or filename_guess.get("title", "")
    author = parent_guess.get("author") or embedded.get("author") or filename_guess.get("author", "")
    year = embedded.get("year") or filename_guess.get("year")

    return {"title": title, "author": author, "year": year}
