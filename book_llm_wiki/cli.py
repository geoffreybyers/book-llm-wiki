"""Book Summarizer CLI — dispatch to subcommands."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from book_llm_wiki.config import load_config
from book_llm_wiki.ingest import ingest_directory, ingest_file


DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "books.yaml"


def _cmd_ingest(args, cfg) -> int:
    if args.directory:
        results = ingest_directory(Path(args.directory).expanduser(), cfg.vault_path)
    elif args.path:
        results = [ingest_file(Path(args.path).expanduser(), cfg.vault_path)]
    else:
        print("ingest: provide a path or --dir", file=sys.stderr)
        return 2

    for r in results:
        status = r["status"]
        icon = {"queued": "✓", "skipped": "-", "failed": "x"}.get(status, "?")
        print(f"{icon} [{status:<7}] {r['title']} — {r['author']} "
              f"(chapters={r.get('chapters','')}, quality={r.get('conversion_quality','')})")
    return 0


def _cmd_status(args, cfg) -> int:
    from book_llm_wiki.vault import _read_collected_rows
    rows = _read_collected_rows(cfg.vault_path)
    if not rows:
        print("(no books ingested)")
        return 0

    widths = {k: max(len(k), max(len(r[k]) for r in rows)) for k in rows[0]}
    header = " | ".join(f"{k:<{widths[k]}}" for k in rows[0])
    print(header)
    print("-" * len(header))
    for r in rows:
        print(" | ".join(f"{r[k]:<{widths[k]}}" for k in rows[0]))
    return 0


def _cmd_reset(args, cfg) -> int:
    """Flip status from 'analyzed' back to 'queued' in collected.md,
    and re-add to analysis_queue.md."""
    from book_llm_wiki.vault import _read_collected_rows, enqueue_for_analysis, COLLECTED_HEADER
    key = args.book
    # Accept either "Title - Author" or just "Title"
    target_title = key.split(" - ")[0].strip()
    target_author = key.split(" - ", 1)[1].strip() if " - " in key else None

    rows = _read_collected_rows(cfg.vault_path)
    found = []
    new_rows = []
    for r in rows:
        match = r["title"] == target_title and (target_author is None or r["author"] == target_author)
        if match:
            r = dict(r)
            r["status"] = "queued"
            r["analyzed_at"] = ""
            r["lens"] = ""
            found.append((r["title"], r["author"]))
        new_rows.append(r)

    if not found:
        print(f"reset: no book matching '{key}' in collected.md", file=sys.stderr)
        return 1

    # Rewrite collected.md
    collected = Path(cfg.vault_path) / "collected.md"
    lines = [COLLECTED_HEADER.rstrip() + "\n"]
    for r in new_rows:
        cells = [r["title"], r["author"], r["status"], r["chapters"],
                 r["conversion_quality"], r["mode"], r["lens"],
                 r["analyzed_at"], r["source"]]
        cells = [c.replace("|", "\\|") for c in cells]
        lines.append("| " + " | ".join(cells) + " |\n")
    collected.write_text("".join(lines))

    for t, a in found:
        enqueue_for_analysis(cfg.vault_path, t, a)
        print(f"re-queued: {t} — {a}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="book-llm-wiki",
        description="Ingest local books and queue them for LLM analysis.",
    )
    parser.add_argument(
        "--config", default=None,
        help=f"Path to books.yaml (default: {DEFAULT_CONFIG})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Convert and enqueue a book or directory")
    ingest.add_argument("path", nargs="?", help="Path to a single book file")
    ingest.add_argument("--dir", dest="directory", help="Batch ingest a directory")

    sub.add_parser("status", help="Show ingest queue and analysis status")

    reset = sub.add_parser("reset", help="Re-queue a previously-analyzed book")
    reset.add_argument("book", help="Book identifier: '<Title> - <Author>' or '<Title>'")

    args = parser.parse_args(argv)

    cfg_path = Path(args.config) if args.config else DEFAULT_CONFIG
    if not cfg_path.exists():
        print(f"config not found: {cfg_path}. Copy books.yaml.example to books.yaml.",
              file=sys.stderr)
        return 2
    cfg = load_config(cfg_path)

    if args.command == "ingest":
        return _cmd_ingest(args, cfg)
    if args.command == "status":
        return _cmd_status(args, cfg)
    if args.command == "reset":
        return _cmd_reset(args, cfg)
    return 2
