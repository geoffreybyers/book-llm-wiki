# Book Analysis Template

> Canonical structure for `/summarize-book` output. The wiki writer parses
> the `## Entities` and `## Concepts` sections programmatically using the
> strict ` :: ` delimiter. Any other section may be edited freely; the
> format below is the contract.

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
