"""Ingest orchestration: convert → write raw → update collected.md + queue."""
from __future__ import annotations

from pathlib import Path

from book_llm_wiki.convert import convert
from book_llm_wiki.metadata import extract_metadata
from book_llm_wiki.vault import (
    CollectedRow,
    append_collected_row,
    bootstrap_vault,
    enqueue_for_analysis,
    is_ingested,
    raw_book_path,
    write_raw_book,
)

SUPPORTED_EXTS = {".epub", ".azw3", ".mobi", ".pdf", ".md", ".markdown"}


def _is_housekeeping(path: Path, root: Path) -> bool:
    """True for `_`-prefixed files/dirs under root — not books.

    Covers scratch notes like `downloads/_STATUS.md` and quarantine folders
    like `downloads/_quarantine_wrong_match/`, which otherwise get ingested as
    books and reappear on every run. Only path parts below `root` are checked,
    so a root that itself starts with `_` still works.
    """
    return any(part.startswith("_") for part in path.relative_to(root).parts)


def ingest_file(src: Path, vault_path: Path) -> dict:
    """Convert a book, write raw markdown, update vault metadata files.

    Returns a summary dict with keys: title, author, status, chapters,
    conversion_quality, mode.

    status is one of: 'queued' (newly ingested), 'skipped' (already present),
    'failed' (conversion error).
    """
    src = Path(src).resolve()
    vault_path = Path(vault_path)
    bootstrap_vault(vault_path)

    try:
        meta = extract_metadata(src)
    except Exception as e:
        # Corrupt/unreadable file. Report it but write nothing to the vault:
        # with no readable metadata the only available title is the raw
        # filename, and a row under that name is junk the user has to clean up.
        # Staying out of collected.md means the file is re-reported (and
        # re-tried) on the next run, which is the visibility we want.
        return {
            "title": src.stem, "author": "", "status": "failed",
            "chapters": 0, "conversion_quality": "low", "mode": "flat",
            "error": f"{type(e).__name__}: {e}",
        }

    title = (meta.get("title") or "").strip()
    author = (meta.get("author") or "").strip()

    if is_ingested(vault_path, title, author):
        return {
            "title": title,
            "author": author,
            "status": "skipped",
            "chapters": 0,
            "conversion_quality": "",
            "mode": "",
        }

    raw_target = raw_book_path(vault_path, title, author)
    try:
        result = convert(src, raw_target)
    except Exception as e:
        row = CollectedRow(
            title=title, author=author, status=f"failed: {type(e).__name__}",
            chapters=0, conversion_quality="low", mode="flat",
            lens="", analyzed_at="", source=str(src),
        )
        append_collected_row(vault_path, row)
        return {
            "title": title, "author": author, "status": "failed",
            "chapters": 0, "conversion_quality": "low", "mode": "flat",
            "error": str(e),
        }

    row = CollectedRow(
        title=title, author=author, status="queued",
        chapters=result.chapter_count,
        conversion_quality=result.conversion_quality,
        mode=result.mode,
        lens="", analyzed_at="",
        source=str(src),
    )
    append_collected_row(vault_path, row)
    enqueue_for_analysis(vault_path, title, author)

    return {
        "title": title, "author": author, "status": "queued",
        "chapters": result.chapter_count,
        "conversion_quality": result.conversion_quality,
        "mode": result.mode,
    }


def ingest_directory(directory: Path, vault_path: Path) -> list[dict]:
    """Recursively find all supported files in directory and ingest each.

    Skips already-ingested books (by Title + Author match against collected.md).
    """
    directory = Path(directory).resolve()
    vault_path = Path(vault_path).resolve()
    if not directory.is_dir():
        raise NotADirectoryError(str(directory))

    results = []
    # Sort for stable order
    candidates = sorted(
        p for p in directory.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
        and not str(p).startswith(str(vault_path))
        and not _is_housekeeping(p, directory)
    )
    for path in candidates:
        try:
            results.append(ingest_file(path, vault_path))
        except Exception as e:
            # Backstop: ingest_file handles the failures it knows about, but a
            # single unexpected one still must not take down the whole run.
            results.append({
                "title": path.stem, "author": "", "status": "failed",
                "chapters": 0, "conversion_quality": "low", "mode": "flat",
                "error": f"{type(e).__name__}: {e}",
            })
    return results
