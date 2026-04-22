"""Book Summarizer CLI — dispatch to subcommands."""
import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="book-summarizer",
        description="Ingest local books and queue them for LLM analysis.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Convert and enqueue a book or directory")
    ingest.add_argument("path", nargs="?", help="Path to a single book file")
    ingest.add_argument("--dir", dest="directory", help="Batch ingest all books in a directory")

    sub.add_parser("status", help="Show the ingest queue and analysis status")

    reset = sub.add_parser("reset", help="Re-queue an already-analyzed book")
    reset.add_argument("book", help="Book identifier: '<Title> - <Author>'")

    args = parser.parse_args(argv)

    if args.command == "ingest":
        print("ingest: not implemented yet", file=sys.stderr)
        return 1
    if args.command == "status":
        print("status: not implemented yet", file=sys.stderr)
        return 1
    if args.command == "reset":
        print(f"reset: not implemented yet (would reset {args.book})", file=sys.stderr)
        return 1

    return 0
