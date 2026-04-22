---
title: Book Summarizer — Design Spec
created: 2026-04-22
status: approved-for-planning
---

# Book Summarizer — Design Spec

## Purpose

Ingest local book files (EPUB primary, PDF best-effort, markdown pass-through) and produce structured book summaries that compound into an Obsidian LLM-wiki vault at `~/obsidian/book summaries/`. Structural parallel to `~/dev/podcast-llm-wiki/`, adapted for books.

## Non-goals (v1)

- Magazines and standalone articles (deferred to later projects).
- URL fetching or integration with `book-downloader` / Anna's Archive.
- High-quality PDF ingestion via `marker` or vision models. v1 accepts PDF on a best-effort basis.
- Cron/scheduled ingest wrapping. CLI is cron-able; no systemd unit.
- Web UI, TUI, or dashboard. `collected.md` in Obsidian is the dashboard.
- Cross-vault meta-vault unifying podcasts + books.
- LibraryThing integration (owned by `book-downloader`).
- Entity/concept tagging for passing mentions. Page creation gated by the same threshold as podcast-llm-wiki (2+ books OR central to one).

## Architecture

Two-tier pattern, mirroring `podcast-llm-wiki`:

```
TIER 1 — CLI (local, deterministic, cheap)
  book-summarizer ingest <path>
    ↓ detect format (epub | pdf | md)
    ↓ convert → chapter-structured markdown (one H1 per chapter)
    ↓ extract metadata (title, author, year)
    ↓ write raw/books/<Title> - <Author>.md
    ↓ append row to collected.md, enqueue in analysis_queue.md

TIER 2 — HUMAN-IN-LOOP (Claude Code slash command, Opus quota)
  /summarize-book
    ↓ pop next from analysis_queue.md
    ↓ prompt user for lens
    ↓ chapter detection pass (parse H1 boundaries)
    ↓ chapter summarization (parallel subagents, one per chapter) — Opus 4.7
    ↓ synthesis pass: TL;DR, Key Insights, Critical Pass, Concepts, Entities — Opus 4.7
    ↓ write books/<Title> - <Author>.md summary page
    ↓ upsert entities/ and concepts/ pages
    ↓ append comparisons/, queries/ pages when triggered
    ↓ update index.md and log.md
    ↓ mark analyzed in collected.md
```

### Fallback path

Map-reduce mode requires usable chapter structure. Fall back to single-pass summarization if any of these fire:

- Fewer than 3 chapters detected after filtering front/back matter.
- Largest chapter exceeds 60% of total book wordcount (detection failure, whole book collapsed into one "chapter").
- More than 80 chapters detected (over-segmentation, e.g. every paragraph became a heading).

Single-pass mode still produces TL;DR, Key Insights, Critical Pass, Concepts, and Entities. The "Chapter by Chapter" section is replaced with a note: `> Summarized in single-pass mode — chapter detection failed or chapters were absent.` The `summary_mode: single-pass` frontmatter field records this for later auditing.

### Parallelism

Chapter summarization uses the superpowers `dispatching-parallel-agents` pattern. Default `max_parallel_chapters: 5`. Tunable via `books.yaml`. All model calls use `claude-opus-4-7` for both chapter and synthesis passes.

## Project layout

```
~/dev/book-summarizer/
├── README.md
├── pyproject.toml
├── LICENSE
├── .env.example
├── .gitignore
├── books.yaml
├── books.yaml.example
├── book_summarizer/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── ingest.py
│   ├── convert/
│   │   ├── __init__.py
│   │   ├── epub.py
│   │   ├── pdf.py
│   │   └── markdown.py
│   ├── metadata.py
│   ├── vault.py
│   └── config.py
├── commands/
│   └── summarize-book.md
├── docs/
│   ├── analysis-template.md
│   ├── wiki-schema-template.md
│   └── lens-examples.md
├── tests/
│   └── test_convert_epub.py
├── logs/
└── collected_example.md
```

### CLI surface

- `book-summarizer ingest <path>` — convert and enqueue one book.
- `book-summarizer ingest --dir <path>` — batch ingest a directory; idempotent on already-ingested books.
- `book-summarizer status` — tabular view of `collected.md`.
- `book-summarizer reset <book>` — mark a book as unanalyzed so it can be re-summarized.

### Install

```bash
cd ~/dev/book-summarizer
pip install -e ".[dev]"
cp books.yaml.example books.yaml
ln -s ~/dev/book-summarizer/commands/summarize-book.md ~/.claude/commands/summarize-book.md
```

## Vault structure

Top-level Obsidian vault at `~/obsidian/book summaries/`:

```
~/obsidian/book summaries/
├── SCHEMA.md
├── index.md
├── log.md
├── collected.md
├── analysis_queue.md
│
├── raw/
│   └── books/
│       └── <Title> - <Author>.md
│
├── books/
│   └── <Title> - <Author>.md
│
├── entities/
│   └── <Name>.md
│
├── concepts/
│   └── <name>.md
│
├── comparisons/
│   └── <slug> - contradiction.md
│
└── queries/
    └── verify-<book-slug>.md
```

Mirrors `podcast-llm-wiki` vault structure with two adaptations: `episodes/` → `books/`, `raw/transcripts/` → `raw/books/`.

### Filename conventions

- Book summary pages: `<Title> - <Author>.md` (no `- summary` suffix — the folder and vault already imply it).
- Entity pages: `<Name>.md` (e.g. `Jim Collins.md`, `Harvard Business School.md`).
- Concept pages: `<name>.md` (e.g. `flywheel effect.md`, `deliberate practice.md`).
- Comparison pages: `<slug> - contradiction.md`.

### Page-creation thresholds

Create an entity/concept page when it appears in **2+ books** OR is **central to one book**. Below that threshold, the mention stays in the book's summary page only. Same rule as podcast-llm-wiki.

### Wikilink rules

- Every book summary links to every entity/concept page it created or updated.
- Every entity/concept page back-links to every book that cited it.
- When a claim in a new book contradicts a prior book, a `comparisons/<slug> - contradiction.md` page is created automatically with wikilinks both directions.

## Summary page template

Canonical structure. Parallel to `podcast-llm-wiki/docs/analysis-template.md` with chapter references instead of timestamps.

```markdown
---
title: <Book Title>
author: <Author Name>
year: <Publication Year>
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: book
tags: [from taxonomy in SCHEMA.md]
raw_path: raw/books/<Title> - <Author>.md
isbn: <if available>
pages: <if available>
summary_mode: map-reduce | single-pass
lens: <lens name from books.yaml>
---

# <Book Title> — <Author>

## TL;DR

Three sentences. The thesis, the new thing, why it matters.

## Key Insights

5–10 insights, ranked by novelty (not order in the book).

- **Bolded claim:** one-paragraph explanation. [Ch. N]

## Critical Pass

- **Steelman(s) of the strongest argument(s) (1–3):** Steelman each distinct
  thesis separately. Cap at 3; anything more belongs in Key Insights. Never pad.
- **Weak claims / unsupported assertions:** Claims resting on anecdote,
  cherry-picked studies, or authority. N/A for fiction, memoir, poetry.
- **Factual claims requiring verification:** Specific empirical claims worth
  checking. If 3+, auto-create `queries/verify-<slug>.md`.
- **Contradictions with prior books (if any):** `[[wikilinks]]` to prior book
  summaries taking the opposite position.

## Concepts

Strict `::`-delimited format. Parsed programmatically.

- name :: 1-line definition :: [Ch. N]

## Entities

Strict `::`-delimited format. Parsed programmatically.

- name :: type (person|org|study|product) :: 1-line context :: [Ch. N]

## Chapter by Chapter

### Chapter 1 — <Chapter Title>

One paragraph (3–6 sentences). What the chapter argues, the key example,
what changes by the end.

### Chapter 2 — <Chapter Title>

...

## Follow-ups

- Open questions raised by the book
- Things to look up
- Books this one is in conversation with
```

In single-pass mode, the `## Chapter by Chapter` section is replaced with the fallback notice.

## Conversion & chapter detection

### EPUB (primary input)

Uses `epub2md` (already installed, Node.js, v1.6.2). Tested capabilities:

- `epub2md -i` — metadata (title, author).
- `epub2md -s` — structured JSON of chapter hierarchy with anchors and paths.
- `epub2md -c` (without `--merge`) — one markdown file per section, filenames
  encode order and title (e.g. `05-Chapter_1__Deep_Work_Is_Valuable.md`).

**Default path (properly-structured EPUBs, majority of library):**

1. Call `epub2md -i` → extract title, author.
2. Call `epub2md -c` → per-section markdown files.
3. Call `epub2md -s` → parse structure JSON; classify each section as chapter, front matter, or back matter (Cover, Copyright, Dedication, Index, Notes, Table of Contents, About the Author, etc., identified by name pattern).
4. Concatenate **all** sections into a single markdown file. Prefix each section's H1 heading by class:
   - Front matter: `# Front Matter — <Title>`
   - Chapter: `# Chapter N — <Title>` (N increments only across chapters, skipping front/back matter)
   - Back matter: `# Back Matter — <Title>`

   All sections are preserved in the raw file so a human can read the whole book from it. The Tier 2 chapter detection pass filters `Front Matter —` and `Back Matter —` sections when counting chapters for the fallback decision and when assigning per-chapter parallel subagents.
5. Write to `raw/books/<Title> - <Author>.md`.

**PDF-origin EPUB edge case:**

Detect via:
- EPUB manifest contains `generator="pdftohtml"`, OR
- Content files contain `pdftohtml` string references, OR
- `spine_item_count << toc_chapter_count` (heuristic).

For PDF-origin EPUBs:
- Flag `conversion_quality: low` in `collected.md`.
- Use `epub2md -c --merge` (flat output).
- Let the fallback path in Tier 2 produce a single-pass summary.
- Do not attempt anchor-slicing. That complexity is not worth carrying for a minority edge case.

Observed distribution: of 10 sampled books from `~/dev/book-downloader/downloads/`, 1 was PDF-origin (Atomic Habits), 9 were properly structured. ~10% fallback rate is acceptable.

### PDF input (best-effort)

v1 uses `pandoc` as a first attempt. If it produces fewer than 3 H1 headings in a PDF of >100 pages, flag `conversion_quality: low` and route to the fallback path. No `marker` integration in v1.

### Markdown input (pass-through)

Scan for existing `# ` / `## ` headings. If ≥ 3 look like chapters, use them. Otherwise flag as `low-structure` and route to the fallback path.

### Chapter detection pass (Tier 2, deterministic)

Reads `raw/books/<Title> - <Author>.md`. Splits on `^# ` boundaries. Filters any section whose heading starts with `Front Matter —` or `Back Matter —`. Yields `(chapter_number, chapter_title, chapter_text)` tuples. No LLM.

### Metadata extraction

- **EPUB**: `epub2md -i`, which exposes OPF `<metadata>` fields.
- **PDF**: PDF metadata first, else filename `<Title> - <Author>.pdf`.
- **Markdown**: YAML frontmatter if present, else filename.

## Configuration

Two files:
- `books.yaml` (committed) — schema, defaults, lens definitions.
- `books.local.yaml` (gitignored) — secrets, local overrides. Merged over `books.yaml` at load time.

### `books.yaml.example`

```yaml
defaults:
  vault_path: ~/obsidian/book summaries
  chapter_model: claude-opus-4-7
  synthesis_model: claude-opus-4-7
  max_parallel_chapters: 5
  min_chapters_for_map_reduce: 3
  max_chapter_share_of_book: 0.60
  max_chapters: 80
  default_lens: general

lenses:
  general: |
    Standard non-fiction analytical lens. Extract the central thesis,
    the top 5-10 novel claims, and apply the Critical Pass. Prefer
    claims that are falsifiable; flag those that aren't.

  self_help: |
    Self-help and productivity books. The central risk is confident
    prose wrapping thin evidence. For every claim, ask: is this
    supported by cited studies, or by anecdote and authority? Weak
    claims and facts-to-verify are the most important sections here.

  business: |
    Business and strategy books. Claims often rest on survivorship
    bias ("study 10 successful companies, extract common traits").
    In the Critical Pass, explicitly flag reasoning that could apply
    equally to failed companies.

  philosophy: |
    Philosophy and ideas books. Steelman each argument charitably.
    Weak-claims is less about empirical support and more about
    internal consistency — does the conclusion follow from the premises?

  memoir: |
    Memoir and biography. Weak-claims and facts-to-verify largely
    N/A. Focus on TL;DR, Key Insights (what the subject learned,
    not claims about the world), and Chapter by Chapter. Critical
    Pass reduced to steelman only.

  fiction: |
    Fiction. Critical Pass is N/A — no empirical claims to verify.
    Focus on plot, themes, Key Insights (character arcs, thematic
    claims the author makes implicitly), and Chapter by Chapter.

overrides:
  # "The 7 Habits of Highly Effective People - Stephen R. Covey":
  #   lens: self_help
```

### Lens selection

At `/summarize-book` time, resolved in this order:

1. `overrides[<book>].lens` in `books.yaml` if set.
2. `/summarize-book --lens <name>` flag if passed.
3. Interactive menu prompting the user, defaulting to `general`.

Rationale: genre is often ambiguous at ingest; lens chosen at analysis time allows contextual decisions.

### `.env`

```bash
# Only needed if CLI ever calls Anthropic API directly (not in v1).
ANTHROPIC_API_KEY=sk-ant-...
```

### Excluded from config (deliberately)

- Chapter-summary word counts (model decides).
- Output style knobs (edit the template, not config).
- Per-genre tag taxonomies (owned by vault `SCHEMA.md`).

## Invocation examples

### Ingest

```bash
# Single book
python -m book_summarizer ingest "~/dev/book-downloader/downloads/Deep Work - Cal Newport/Deep Work - Cal Newport - 8e4567c95342c815b075cf9376542d33.epub"

# Batch (idempotent)
python -m book_summarizer ingest --dir "~/dev/book-downloader/downloads/"

# Status
python -m book_summarizer status

# Re-queue
python -m book_summarizer reset "Deep Work - Cal Newport"
```

### Analyze

```
/summarize-book
/summarize-book 3
/summarize-book --match deep
/summarize-book --lens business
```

## Wiki writer behavior

After the synthesis pass produces the summary:

1. Parse strict `::` Concepts and Entities sections.
2. For each concept/entity:
   - Check if page exists.
   - If yes, append citation to the existing page and bump `updated` date.
   - If no, check threshold (central to this book OR already cited in ≥1 other book). If met, create new page. Otherwise leave as plain text in summary only.
3. Scan Critical Pass → "Contradictions with prior books" for `[[wikilinks]]`. For each net-new contradiction, create `comparisons/<slug> - contradiction.md`.
4. Scan Critical Pass → "Factual claims requiring verification". If 3+ items, create `queries/verify-<book-slug>.md`.
5. Append action to `log.md`.
6. Update `index.md` (author index, topic index, date-read list).
7. Mark book as `analyzed` in `collected.md`.

## Error handling

- **Ingest errors** (corrupt EPUB, unreadable PDF): logged to `collected.md` with error column. Book is skipped, not queued. Retry via `book-summarizer reset <book>` after inspection.
- **LLM errors** (API failure, rate limit, context overflow mid-chapter): slash command fails gracefully, preserves partial chapter summaries as sidecar files under `books/.partial/<Title>/chapter-N.md`, leaves book in queue. Next run resumes from partial state.
- **Wiki-writer errors** (malformed `::` format, malformed lens output): fall back to writing raw model output to the summary file with a warning comment at the top. Wiki sidecars (entities, concepts, comparisons, queries) are not touched. Preserves the work for hand-fixing.

## Testing

- **Golden-file test** `tests/test_convert_epub.py`: ingest a known-good EPUB (Deep Work), assert chapter count == 15, assert raw/ file structure. Offline. No LLM.
- **PDF-origin detection test**: ingest Atomic Habits, assert `conversion_quality: low` in the written `collected.md` row.
- **No LLM-in-the-loop tests.** Summarization quality judged by human review, not asserts.

## Dependencies

### Runtime (Tier 1 CLI)

- Python 3.11+
- `epub2md` v1.6.2+ (already installed globally via npm)
- `pandoc` (for PDF and markdown fallback)
- Standard library: `argparse`, `json`, `pathlib`, `subprocess`, `zipfile`, `xml.etree`, `re`
- Third-party: `pyyaml` (config loading)

### Runtime (Tier 2 slash command)

- Claude Code with Opus quota
- superpowers `dispatching-parallel-agents` pattern

### Dev

- `pytest`

No new heavy deps. No `ebooklib`, no `marker`, no `html2text`, no Anthropic SDK in Tier 1.

## Success criteria

v1 ships when:

1. `python -m book_summarizer ingest <path>` successfully converts a properly-structured EPUB and writes `raw/books/<Title> - <Author>.md` with one `# Chapter N` per chapter.
2. `book-summarizer status` shows a tabular queue.
3. `/summarize-book` runs end-to-end on a queued book, produces a summary file matching the template, and updates `collected.md` and `log.md`.
4. Running `/summarize-book` a second time on a different book creates entity/concept pages that link to both books where thresholds are met.
5. Ingesting a PDF-origin EPUB (Atomic Habits) flags `conversion_quality: low`, runs through the fallback single-pass path, and produces a usable summary without the Chapter by Chapter section.

## Open questions for implementation

None. All decisions have been made during brainstorming. Ready for `superpowers:writing-plans`.
