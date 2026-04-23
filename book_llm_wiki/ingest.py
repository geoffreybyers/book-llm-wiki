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

SUPPORTED_EXTS = {".epub", ".pdf", ".md", ".markdown"}


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

    meta = extract_metadata(src)
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
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS and not str(p).startswith(str(vault_path))
    )
    for path in candidates:
        results.append(ingest_file(path, vault_path))
    return results
