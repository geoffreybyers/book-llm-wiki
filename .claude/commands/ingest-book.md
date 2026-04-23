---
description: Ingest books into the vault (Tier 1) — convert EPUBs to chapter-structured markdown, queue for analysis
argument-hint: "[<path> | --dir <path> | status | reset \"<Title> - <Author>\"]"
---

# /ingest-book

Tier 1 of the book pipeline. Thin wrapper over the `book_llm_wiki` Python CLI — **no LLM calls, no Opus quota**. Converts local books (EPUB/markdown) into chapter-structured markdown and adds them to the analysis queue for `/summarize-book`.

## Usage

```
/ingest-book                                    Default: batch ingest ./downloads/ under the repo root
/ingest-book <path>                             Convert and queue one book
/ingest-book --dir <path>                       Batch ingest a directory (recursive, idempotent)
/ingest-book status                             Show the collected.md dashboard
/ingest-book reset "<Title> - <Author>"        Re-queue an already-analyzed book
/ingest-book help                               Show this usage
```

## Dispatch rule

Inspect `$ARGUMENTS`. Match the first token (if any):

- `help`, `-h`, `--help` → print the Usage block above verbatim and exit.
- `status` → run `python3 -m book_llm_wiki status`. Print stdout verbatim.
- `reset` → strip the `reset` token. If what remains is empty, print `(reset requires a book identifier — try /ingest-book status to see options)` and exit. Otherwise run `python3 -m book_llm_wiki reset "<rest>"` and print stdout verbatim.
- Empty `$ARGUMENTS` → run `python3 -m book_llm_wiki ingest --dir "$(git rev-parse --show-toplevel)/downloads/"`.
- First token is `--dir` → run `python3 -m book_llm_wiki ingest --dir <path>`.
- First token is a path → run `python3 -m book_llm_wiki ingest <path>`.
- Anything else → print `(unknown argument: <token>)` then the Usage block and exit.

Print the CLI's stdout verbatim. Print stderr if exit code is non-zero.
