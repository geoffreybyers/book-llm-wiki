# Book Summarizer

Two-tier book-to-wiki pipeline. Tier 1 is a Python CLI that converts local
EPUBs into chapter-structured markdown and queues them for analysis. Tier 2
is a Claude Code slash command (`/summarize-book`) that runs Opus 4.7 across
chapters in parallel and writes a compounding Obsidian LLM wiki.

## Install

```bash
cd ~/dev/book-summarizer
pip install -e ".[dev]"
cp books.yaml.example books.yaml
ln -s ~/dev/book-summarizer/commands/summarize-book.md ~/.claude/commands/summarize-book.md
```

## Usage

```bash
# Ingest a book
python -m book_summarizer ingest path/to/book.epub

# Batch ingest a directory
python -m book_summarizer ingest --dir ~/dev/book-downloader/downloads/

# Show queue status
python -m book_summarizer status

# Re-queue a book
python -m book_summarizer reset "Deep Work - Cal Newport"
```

Then in Claude Code:

```
/summarize-book
```

See `docs/superpowers/specs/2026-04-22-book-summarizer-design.md` for the full design.
