---
description: Pop the next queued book, run Opus 4.7 chapter-level summarization in parallel, synthesize, and write the LLM-wiki pages
argument-hint: "[count] [--match <slug>] [--lens <name>]"
---

# /summarize-book

You are the Tier 2 analysis engine for the Book Summarizer project. Your job is to take one (or N) queued books, run chapter-level summarization in parallel, synthesize the results, and update the Obsidian LLM-wiki vault.

## Phase 1 — Load configuration and resolve book

1. Read `/home/administrator/dev/book-summarizer/books.yaml` (fall back to `books.yaml.example` if missing). Extract:
   - `vault_path` (default `~/obsidian/book summaries`)
   - `max_parallel_chapters` (default 5)
   - `min_chapters_for_map_reduce`, `max_chapter_share_of_book`, `max_chapters` (fallback thresholds)
   - `lenses` (dict of lens name → prompt fragment)
   - `overrides` (per-book lens picks)

2. Parse `$ARGUMENTS`:
   - First positional arg: `count` (default 1)
   - `--match <slug>`: pick the first queue entry whose `Title - Author` contains `<slug>` (case-insensitive) instead of popping oldest
   - `--lens <name>`: force-apply this lens, skip the interactive menu

3. Read `{vault_path}/analysis_queue.md`. Find the target entry. If queue is empty, print `(queue empty)` and exit.

4. For each target book (one at a time), proceed through phases 2–6. Then pop it from the queue.

## Phase 2 — Lens selection

For the current book `<Title> - <Author>`:

1. If `overrides["<Title> - <Author>"].lens` exists, use that.
2. Else if `--lens <name>` was passed, use that.
3. Else present a menu to the user:

```
Book: <Title> — <Author>
Lenses available: general, self_help, business, philosophy, memoir, fiction
Which lens for this book? [general]:
```

Wait for the user to respond. If they press enter, use `general`.

## Phase 3 — Chapter detection

1. Read the raw markdown from `{vault_path}/raw/books/<Title> - <Author>/<Title> - <Author>.md`. Each book lives in its own subdirectory alongside an `images/` folder.

2. Split on `^# ` boundaries. Each H1 heading starts a new section.

3. Classify each section by heading prefix:
   - `# Chapter N — ...` → chapter (keep, ordered by N)
   - `# Front Matter — ...` → filtered
   - `# Back Matter — ...` → filtered
   - No prefix (or any other heading) → treat as chapter in a flat-mode raw file

4. Compute fallback triggers:
   - Chapter count < `min_chapters_for_map_reduce` (default 3) → single-pass
   - Chapter count > `max_chapters` (default 80) → single-pass
   - Largest chapter wordcount / total wordcount > `max_chapter_share_of_book` (default 0.60) → single-pass
   - Conversion quality in collected.md is `low` → single-pass

5. Set `summary_mode` = `map-reduce` or `single-pass`.

## Phase 4 — Chapter summarization (map-reduce mode only)

Use the `superpowers:dispatching-parallel-agents` pattern. Dispatch up to `max_parallel_chapters` subagents concurrently. Each subagent receives one chapter and returns a structured summary.

Per-chapter subagent prompt:

```
You are summarizing ONE chapter of a book. The book is {Title} by {Author}. The lens for this analysis is:

{lens text}

CHAPTER {N} — {chapter title}:

{chapter text}

Return a 3–6 sentence summary in this exact format:

### Chapter {N} — {chapter title}

<one paragraph, 3–6 sentences. What this chapter argues, the key example it uses, what changes by the end of the chapter.>

Do NOT include anything else. No TL;DR, no bullet points, no meta-commentary. Just the heading and the paragraph.
```

Save partial results as they come in to `{vault_path}/books/.partial/<Title>/chapter-{N}.md` so a crash is resumable.

If any chapter fails 3 times in a row (network, rate limit, context overflow), halt the run, keep the partials, leave the book in the queue, and report the failure to the user.

## Phase 5 — Synthesis pass

ONE model call with Opus 4.7. Input to the model:

1. The lens text.
2. Book metadata (title, author, year).
3. All chapter summaries concatenated.
4. Two strategically-selected full-text excerpts from the raw markdown:
   - The first ~500 words of the first chapter (establishes the thesis).
   - The last ~500 words of the last chapter (establishes the conclusion).

Instruct the model to produce the full summary page following this template exactly:

```
---
title: {Title}
author: {Author}
year: {Year}
created: {today}
updated: {today}
type: book
tags: [<from SCHEMA.md taxonomy; pick 1-3 genre tags + applicable meta tags>]
raw_path: raw/books/{Title} - {Author}/{Title} - {Author}.md
isbn: ''
pages: ''
summary_mode: {map-reduce | single-pass}
lens: {lens_name}
---

# {Title} — {Author}

## TL;DR

<three sentences: thesis, new thing, why it matters>

## Key Insights

<5-10 ranked by novelty, each a bolded-claim + paragraph, with [Ch. N] references>

## Critical Pass

- **Steelman(s) of the strongest argument(s) (1–3):** <charitable reconstruction of the book's strongest positions. Cap at 3.>
- **Weak claims / unsupported assertions:** <specific claims resting on anecdote, cherry-picked studies, or authority. Write "N/A" for fiction, memoir, or poetry.>
- **Factual claims requiring verification:** <specific empirical claims worth checking, as a bulleted list>
- **Contradictions with prior books (if any):** <[[wikilinks]] to prior book summaries in this vault that take the opposite position, with one-line explanations>

## Concepts

<strict `::`-delimited, one per line:>
- name :: 1-line definition :: [Ch. N]

## Entities

<strict `::`-delimited, one per line:>
- name :: type (person|org|study|product) :: 1-line context :: [Ch. N]

## Chapter by Chapter

<concatenated chapter summaries from Phase 4, in order. In single-pass mode, replace this section with:>

> Summarized in single-pass mode — chapter detection failed or chapters were absent.

## Follow-ups

- <open questions raised by the book>
- <things to look up>
- <books this one is in conversation with>
```

For single-pass mode, the chapter summaries input is replaced with the full raw markdown (truncated if > 150K tokens).

Write the result to `{vault_path}/books/<Title> - <Author>.md`.

## Phase 6 — Wiki writer

After the summary file is written:

1. **Parse Concepts and Entities sections.** Split each bullet on ` :: `. If any bullet fails to parse (wrong number of fields, missing type for entity), write a warning comment at the top of the summary file (`<!-- warning: <N> malformed Entities/Concepts bullets — wiki pages not created -->`) and skip steps 2–5. This preserves the model's output even if the parser fails.

2. **For each concept:**
   - Check if `{vault_path}/concepts/<name>.md` exists.
   - If yes, append a citation: a line like `- Cited in [[<Title> - <Author>]] ([Ch. N]): <1-line definition>`, and bump `updated:` in frontmatter.
   - If no, check the threshold:
     - Does it appear in any other book summary already in the vault? (grep `{vault_path}/books/*.md` for the concept name, case-insensitive).
     - Is it in ≥2 books (this one + at least 1 other)? Or: is the model's 1-line definition marked (by convention, ending with `[central]`) as central to this book?
     - If threshold met, create the page with frontmatter + the definition + the first citation.
     - Otherwise, leave as plain text in the summary only.

3. **For each entity:** same logic, in `{vault_path}/entities/<Name>.md`.

4. **Critical Pass → Contradictions with prior books:** For each `[[wikilink]]` in that subsection that points to another book summary, create `{vault_path}/comparisons/<slug> - contradiction.md` with frontmatter and two-way wikilinks to both books. If the comparison page already exists, append a new section listing the new disagreement.

5. **Critical Pass → Factual claims requiring verification:** If there are ≥3 bullets, create `{vault_path}/queries/verify-<book-slug>.md` with each item as a bullet + back-link to the book.

6. **Append to log.md:**

```markdown
## YYYY-MM-DD HH:MM
- Analyzed [[<Title> - <Author>]] with lens `{lens_name}` ({map-reduce|single-pass})
- Created/updated: <N> concepts, <M> entities
- Contradictions: <count>
- Verify queries: <count>
```

7. **Update index.md:**
   - Add `[[<Title> - <Author>]]` to the By Author section under the author's heading (create heading if it doesn't exist).
   - Extract the primary genre tag from the summary frontmatter, add to By Topic.
   - Prepend to By Date Analyzed with today's date.

8. **Mark as analyzed in collected.md:**
   - Find the row for `<Title> - <Author>`.
   - Change `status: queued` → `status: analyzed`.
   - Set `lens: <lens_name>` and `analyzed_at: YYYY-MM-DD`.

9. **Remove from analysis_queue.md.**

10. Clean up `{vault_path}/books/.partial/<Title>/` (delete the directory on success).

## Phase 7 — User summary

After each book, print a short summary:

```
✓ Analyzed: {Title} — {Author}
  Mode: {map-reduce|single-pass}
  Lens: {lens_name}
  Chapters summarized: {N} (of {total})
  Entities created/updated: {E}
  Concepts created/updated: {C}
  Contradictions flagged: {X}
  Verify queries created: {V}
  Summary file: {vault_path}/books/{Title} - {Author}.md
```

If `count > 1`, repeat for each book in turn. If `count > 1` AND any book in the sequence fails, stop and report which books remain in the queue.

## Error handling

- **Malformed Concepts/Entities bullets:** preserve model output with warning comment; do not attempt to create entity/concept pages from broken input.
- **Rate limit or API failure mid-chapter:** save partial chapter summaries to `.partial/`, leave book in queue, report to user.
- **No queued books:** print `(queue empty)` and exit 0.
- **Raw file missing** (someone deleted it): remove the broken entry from the queue and skip; do not fail the whole run.
