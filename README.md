# Book Summarizer

Two-tier book-to-wiki pipeline. Tier 1 is a Python CLI that converts local
EPUBs into chapter-structured markdown and queues them for analysis. Tier 2
is a Claude Code slash command (`/summarize-book`) that runs Opus 4.7 across
chapters in parallel and writes a compounding Obsidian LLM wiki.

## Requirements

- Python 3.11+
- [Claude Code](https://claude.com/claude-code) (for Tier 2 analysis)
- An Obsidian vault (or any directory) to serve as the wiki output

## Install

```bash
cd ~/dev/book-summarizer
pip install -e ".[dev]"
cp books.yaml.example books.yaml
ln -s ~/dev/book-summarizer/commands/summarize-book.md ~/.claude/commands/summarize-book.md
```

Edit `books.yaml` to point `vault_path` at your Obsidian vault (or any
output directory). The example paths in this repo (`~/obsidian/book summaries`,
`~/dev/book-downloader/downloads/`) are placeholders — replace with your own.

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

See `docs/analysis-template.md` and `docs/lens-examples.md` for the analysis
structure and available lenses.

## License

MIT — see [LICENSE](LICENSE).
