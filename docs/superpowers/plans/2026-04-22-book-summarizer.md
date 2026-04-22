# Book Summarizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a two-tier book-to-wiki pipeline: a Python CLI (Tier 1) that ingests EPUBs/PDFs/markdown into chapter-structured markdown in an Obsidian vault, and a Claude Code slash command (Tier 2) that runs Opus 4.7 summarization with parallel chapter subagents and writes a compounding LLM wiki.

**Architecture:** Two-tier pattern mirroring `~/dev/podcast-llm-wiki/`. Tier 1 is deterministic Python that shells out to `epub2md` for EPUB conversion and writes raw markdown + queue files. Tier 2 is a `.md` slash command file describing the full LLM orchestration (chapter detection, parallel subagents, synthesis, wiki writer) to be executed inside Claude Code.

**Tech Stack:** Python 3.11+, PyYAML, pytest, epub2md (Node.js, already installed), pandoc, Claude Code with Opus quota.

---

## File Structure

### Tier 1 — Python package

| Path | Responsibility | ~Lines |
|---|---|---|
| `pyproject.toml` | Package definition, script entry point, deps | 25 |
| `.gitignore` | Python + project-specific ignores | 15 |
| `.env.example` | Env var template (unused in v1) | 5 |
| `README.md` | Install + usage | 50 |
| `books.yaml.example` | Config template | 60 |
| `book_summarizer/__init__.py` | Version constant | 2 |
| `book_summarizer/__main__.py` | `python -m book_summarizer` entry | 5 |
| `book_summarizer/cli.py` | argparse, dispatch to subcommands | 80 |
| `book_summarizer/config.py` | Load books.yaml + books.local.yaml | 50 |
| `book_summarizer/metadata.py` | Title/author/year from EPUB/PDF/md | 70 |
| `book_summarizer/convert/__init__.py` | Format detection + dispatch | 40 |
| `book_summarizer/convert/epub.py` | epub2md subprocess + classification + PDF-origin detection | 180 |
| `book_summarizer/convert/pdf.py` | pandoc wrapper | 50 |
| `book_summarizer/convert/markdown.py` | Pass-through + heading scan | 40 |
| `book_summarizer/vault.py` | Bootstrap + collected.md + analysis_queue.md + raw/ write | 180 |
| `book_summarizer/ingest.py` | Orchestrate convert → write vault | 80 |

### Tier 2 — Claude Code slash command

| Path | Responsibility | ~Lines |
|---|---|---|
| `commands/summarize-book.md` | Full Tier 2 prompt: queue pop → lens → chapter detection → parallel summarize → synthesize → wiki writer | 250 |

### Static docs (human-readable reference)

| Path | Responsibility |
|---|---|
| `docs/analysis-template.md` | Canonical summary structure (human-readable copy of what Tier 2 emits) |
| `docs/lens-examples.md` | Starter lens library. The canonical lens list lives in `books.yaml`. |

SCHEMA.md content lives in `book_summarizer/vault.py::SCHEMA_TEMPLATE` (single source of truth, rendered into each new vault on bootstrap). No duplicate docs file.

### Tests

| Path | What it covers |
|---|---|
| `tests/conftest.py` | Fixture: synthesize a minimal test EPUB + tmp vault dir |
| `tests/test_config.py` | Load, merge books.yaml + books.local.yaml |
| `tests/test_metadata.py` | Parse EPUB metadata from fixture |
| `tests/test_convert_epub.py` | End-to-end EPUB → structured markdown with fixture |
| `tests/test_convert_epub_pdf_origin.py` | PDF-origin detection flags low quality |
| `tests/test_convert_markdown.py` | Pass-through heading scan |
| `tests/test_vault.py` | Bootstrap + collected.md + analysis_queue.md round-trip |
| `tests/test_ingest.py` | Single-file + batch + idempotency |

---

## Phases and Checkpoints

- **Phase A** (Tasks 1–5): Scaffolding, config, test fixtures.
- **Phase B** (Tasks 6–11): Conversion pipeline (EPUB, PDF, markdown).
- **Phase C** (Tasks 12–13): Metadata.
- **Phase D** (Tasks 14–17): Vault writer.
- **Phase E** (Tasks 18–19): Ingest orchestration.
- **Phase F** (Tasks 20–22): CLI subcommands.
- **Phase G** (Tasks 23–25): Docs + Tier 1 smoke test.
- **🛑 Checkpoint 1** — Tier 1 ships. Ingest real books, confirm raw markdown quality before continuing.
- **Phase H** (Task 26): Tier 2 slash command.
- **Phase I** (Task 27): Tier 2 smoke test.
- **🛑 Checkpoint 2** — v1 ships.

---

## Phase A: Scaffolding

### Task 1: Project metadata files

**Files:**
- Create: `/home/administrator/dev/book-summarizer/pyproject.toml`
- Create: `/home/administrator/dev/book-summarizer/.gitignore`
- Create: `/home/administrator/dev/book-summarizer/.env.example`
- Create: `/home/administrator/dev/book-summarizer/README.md`

- [ ] **Step 1: Write pyproject.toml**

```toml
[project]
name = "book-summarizer"
version = "0.1.0"
description = "Two-tier book-to-wiki pipeline: local CLI converts EPUBs, Claude Code slash command summarizes into an Obsidian LLM wiki."
requires-python = ">=3.11"
dependencies = [
    "PyYAML>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
]

[project.scripts]
book-summarizer = "book_summarizer.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["book_summarizer*"]
```

- [ ] **Step 2: Write .gitignore**

```
# Python
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.venv/
venv/
dist/
build/

# Local config
books.local.yaml
.env

# Logs
logs/
```

- [ ] **Step 3: Write .env.example**

```bash
# Not needed in v1. Tier 1 CLI does not call the Anthropic API directly
# (all LLM work happens in the Tier 2 slash command, which uses Claude
# Code's own auth). Keeping this file so future additions have a place
# to land.
ANTHROPIC_API_KEY=
```

- [ ] **Step 4: Write README.md stub**

```markdown
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
```

- [ ] **Step 5: Commit**

```bash
cd /home/administrator/dev/book-summarizer
git add pyproject.toml .gitignore .env.example README.md
git commit -m "feat: project scaffolding"
```

---

### Task 2: Package skeleton with CLI entry

**Files:**
- Create: `/home/administrator/dev/book-summarizer/book_summarizer/__init__.py`
- Create: `/home/administrator/dev/book-summarizer/book_summarizer/__main__.py`
- Create: `/home/administrator/dev/book-summarizer/book_summarizer/cli.py`
- Create: `/home/administrator/dev/book-summarizer/book_summarizer/convert/__init__.py`
- Test: `/home/administrator/dev/book-summarizer/tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Create `/home/administrator/dev/book-summarizer/tests/__init__.py` (empty) and:

```python
# tests/test_cli.py
import subprocess
import sys


def test_cli_help_lists_subcommands():
    result = subprocess.run(
        [sys.executable, "-m", "book_summarizer", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "ingest" in result.stdout
    assert "status" in result.stdout
    assert "reset" in result.stdout
```

- [ ] **Step 2: Run test, verify it fails**

```bash
cd /home/administrator/dev/book-summarizer
pip install -e ".[dev]"
pytest tests/test_cli.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'book_summarizer'` or similar.

- [ ] **Step 3: Write package skeleton**

`book_summarizer/__init__.py`:
```python
__version__ = "0.1.0"
```

`book_summarizer/__main__.py`:
```python
from book_summarizer.cli import main

if __name__ == "__main__":
    main()
```

`book_summarizer/convert/__init__.py`:
```python
# package marker; functions added in later tasks
```

`book_summarizer/cli.py`:
```python
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
```

- [ ] **Step 4: Run test, verify it passes**

```bash
pytest tests/test_cli.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add book_summarizer/ tests/
git commit -m "feat: package skeleton with CLI subcommand dispatch"
```

---

### Task 3: Config loading with book.yaml + books.local.yaml merge

**Files:**
- Create: `/home/administrator/dev/book-summarizer/books.yaml.example`
- Create: `/home/administrator/dev/book-summarizer/book_summarizer/config.py`
- Test: `/home/administrator/dev/book-summarizer/tests/test_config.py`

- [ ] **Step 1: Write books.yaml.example**

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

- [ ] **Step 2: Write the failing test**

```python
# tests/test_config.py
import textwrap
from pathlib import Path

from book_summarizer.config import load_config


def test_load_config_from_single_file(tmp_path: Path):
    cfg_file = tmp_path / "books.yaml"
    cfg_file.write_text(textwrap.dedent("""
        defaults:
          vault_path: ~/obsidian/book summaries
          max_parallel_chapters: 5
          default_lens: general
        lenses:
          general: |
            Standard lens text.
    """))
    cfg = load_config(cfg_file)
    assert cfg.vault_path.name == "book summaries"
    assert cfg.max_parallel_chapters == 5
    assert cfg.default_lens == "general"
    assert "Standard lens text" in cfg.lenses["general"]


def test_local_yaml_overrides_main(tmp_path: Path):
    main = tmp_path / "books.yaml"
    local = tmp_path / "books.local.yaml"
    main.write_text(textwrap.dedent("""
        defaults:
          vault_path: /should/be/overridden
          max_parallel_chapters: 5
          default_lens: general
        lenses: {general: "main"}
    """))
    local.write_text(textwrap.dedent("""
        defaults:
          vault_path: /local/path
          max_parallel_chapters: 3
    """))
    cfg = load_config(main, local_path=local)
    assert str(cfg.vault_path) == "/local/path"
    assert cfg.max_parallel_chapters == 3
    assert cfg.default_lens == "general"  # untouched
    assert cfg.lenses["general"] == "main"  # untouched


def test_missing_config_raises(tmp_path: Path):
    import pytest
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")
```

- [ ] **Step 3: Run test, verify it fails**

```bash
pytest tests/test_config.py -v
```

Expected: FAIL with `ImportError` or `ModuleNotFoundError` on `load_config`.

- [ ] **Step 4: Write config.py**

```python
"""Load books.yaml and merge books.local.yaml overrides."""
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Config:
    vault_path: Path
    chapter_model: str = "claude-opus-4-7"
    synthesis_model: str = "claude-opus-4-7"
    max_parallel_chapters: int = 5
    min_chapters_for_map_reduce: int = 3
    max_chapter_share_of_book: float = 0.60
    max_chapters: int = 80
    default_lens: str = "general"
    lenses: dict[str, str] = field(default_factory=dict)
    overrides: dict[str, dict] = field(default_factory=dict)


def _deep_merge(base: dict, overlay: dict) -> dict:
    result = dict(base)
    for key, val in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def load_config(path: Path, local_path: Path | None = None) -> Config:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    with path.open() as fh:
        data = yaml.safe_load(fh) or {}

    if local_path is None:
        local_path = path.parent / "books.local.yaml"
    if local_path.exists():
        with local_path.open() as fh:
            local = yaml.safe_load(fh) or {}
        data = _deep_merge(data, local)

    defaults = data.get("defaults", {})
    vault_path = Path(defaults.get("vault_path", "~/obsidian/book summaries")).expanduser()

    return Config(
        vault_path=vault_path,
        chapter_model=defaults.get("chapter_model", "claude-opus-4-7"),
        synthesis_model=defaults.get("synthesis_model", "claude-opus-4-7"),
        max_parallel_chapters=defaults.get("max_parallel_chapters", 5),
        min_chapters_for_map_reduce=defaults.get("min_chapters_for_map_reduce", 3),
        max_chapter_share_of_book=defaults.get("max_chapter_share_of_book", 0.60),
        max_chapters=defaults.get("max_chapters", 80),
        default_lens=defaults.get("default_lens", "general"),
        lenses=data.get("lenses", {}),
        overrides=data.get("overrides", {}),
    )
```

- [ ] **Step 5: Run test, verify it passes**

```bash
pytest tests/test_config.py -v
```

Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add books.yaml.example book_summarizer/config.py tests/test_config.py
git commit -m "feat: config loading with books.local.yaml override"
```

---

### Task 4: Synthetic EPUB test fixture

Reason: we need a stable, committed EPUB fixture for tests (using real books makes tests non-reproducible and commits binary bloat). A minimal ~5 KB EPUB that exercises the spine + NCX is enough.

**Files:**
- Create: `/home/administrator/dev/book-summarizer/tests/conftest.py`
- Create: `/home/administrator/dev/book-summarizer/tests/fixtures/__init__.py` (empty)

- [ ] **Step 1: Write conftest.py with EPUB fixture builder**

```python
# tests/conftest.py
"""Pytest fixtures: minimal synthetic EPUBs and temp vaults."""
from pathlib import Path
import zipfile

import pytest


MIMETYPE = "application/epub+zip"

CONTAINER_XML = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

CONTENT_OPF_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{title}</dc:title>
    <dc:creator>{author}</dc:creator>
    <dc:date>{year}</dc:date>
    <dc:identifier id="BookId">urn:uuid:test-{title_slug}</dc:identifier>
    <dc:language>en</dc:language>
{extra_metadata}
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
{manifest_items}
  </manifest>
  <spine toc="ncx">
{spine_items}
  </spine>
</package>
"""

NCX_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="urn:uuid:test"/></head>
  <docTitle><text>{title}</text></docTitle>
  <navMap>
{nav_points}
  </navMap>
</ncx>
"""

NAV_POINT_TEMPLATE = """    <navPoint id="{id}" playOrder="{order}">
      <navLabel><text>{label}</text></navLabel>
      <content src="{src}"/>
    </navPoint>"""

HTML_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{title}</title></head>
<body>
<h1>{title}</h1>
<p>{body}</p>
</body>
</html>
"""


def _build_epub(
    out_path: Path,
    title: str,
    author: str,
    year: str,
    sections: list[tuple[str, str]],  # [(section_label, body_text), ...]
    extra_metadata: str = "",
) -> Path:
    """Build a minimal valid EPUB at out_path."""
    title_slug = title.lower().replace(" ", "-")
    manifest_items = []
    spine_items = []
    nav_points = []
    html_files = {}
    for i, (label, body) in enumerate(sections, start=1):
        item_id = f"s{i}"
        href = f"section-{i}.xhtml"
        manifest_items.append(f'    <item id="{item_id}" href="{href}" media-type="application/xhtml+xml"/>')
        spine_items.append(f'    <itemref idref="{item_id}"/>')
        nav_points.append(NAV_POINT_TEMPLATE.format(id=item_id, order=i, label=label, src=href))
        html_files[href] = HTML_TEMPLATE.format(title=label, body=body)

    content_opf = CONTENT_OPF_TEMPLATE.format(
        title=title,
        author=author,
        year=year,
        title_slug=title_slug,
        manifest_items="\n".join(manifest_items),
        spine_items="\n".join(spine_items),
        extra_metadata=extra_metadata,
    )
    ncx = NCX_TEMPLATE.format(title=title, nav_points="\n".join(nav_points))

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # mimetype must be first and uncompressed per EPUB spec
        zf.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/toc.ncx", ncx)
        for href, html in html_files.items():
            zf.writestr(f"OEBPS/{href}", html)

    return out_path


@pytest.fixture
def normal_epub(tmp_path: Path) -> Path:
    """A properly-structured EPUB with 3 chapters + front/back matter."""
    out = tmp_path / "normal.epub"
    sections = [
        ("Cover", "Cover image placeholder."),
        ("Title Page", "Title page."),
        ("Chapter 1: Origins", "The first chapter talks about origins. " * 40),
        ("Chapter 2: Growth", "The second chapter talks about growth. " * 40),
        ("Chapter 3: Reflection", "The third chapter reflects. " * 40),
        ("Notes", "Reference notes."),
        ("Copyright", "(c) Test Author."),
    ]
    return _build_epub(out, title="The Test Book", author="Test Author", year="2024", sections=sections)


@pytest.fixture
def pdf_origin_epub(tmp_path: Path) -> Path:
    """A PDF-origin EPUB detectable via generator metadata."""
    out = tmp_path / "pdf_origin.epub"
    sections = [
        ("Cover", "<p>Generated by pdftohtml 0.36</p>"),
        ("Content", "Wall of text with no real chapter boundaries. " * 200),
    ]
    extra = '    <meta name="generator" content="pdftohtml 0.36"/>'
    return _build_epub(
        out,
        title="PDF Origin Book",
        author="Ghost Author",
        year="2020",
        sections=sections,
        extra_metadata=extra,
    )


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    """An empty tmp dir to use as a vault root."""
    v = tmp_path / "book summaries"
    v.mkdir()
    return v
```

- [ ] **Step 2: Verify fixture builds a valid EPUB**

Quick sanity check:

```bash
pytest -q --collect-only tests/
```

Expected: no errors collecting (fixtures themselves don't need tests here — they're exercised by later tasks).

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: synthetic EPUB fixture builder"
```

---

### Task 5: Verify epub2md is available

**Files:**
- Create: `/home/administrator/dev/book-summarizer/tests/test_environment.py`

- [ ] **Step 1: Write a smoke test that asserts epub2md and pandoc are on PATH**

```python
# tests/test_environment.py
"""Assert external tools required by Tier 1 are installed."""
import shutil


def test_epub2md_installed():
    assert shutil.which("epub2md") is not None, (
        "epub2md not found on PATH. Install with: npm install -g epub2md"
    )


def test_pandoc_installed():
    assert shutil.which("pandoc") is not None, (
        "pandoc not found on PATH. Install with: apt install pandoc  (or brew install pandoc)"
    )
```

- [ ] **Step 2: Run test, verify it passes (your machine already has both)**

```bash
pytest tests/test_environment.py -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_environment.py
git commit -m "test: verify epub2md and pandoc are available"
```

---

## Phase B: Conversion pipeline

### Task 6: epub2md subprocess wrappers

**Files:**
- Create: `/home/administrator/dev/book-summarizer/book_summarizer/convert/epub.py`
- Test: `/home/administrator/dev/book-summarizer/tests/test_convert_epub.py`

- [ ] **Step 1: Write failing test for info + structure fetchers**

```python
# tests/test_convert_epub.py
from pathlib import Path

from book_summarizer.convert.epub import epub_info, epub_structure


def test_epub_info_returns_title_and_author(normal_epub: Path):
    info = epub_info(normal_epub)
    assert info["title"] == "The Test Book"
    assert info["author"] == "Test Author"


def test_epub_structure_returns_ordered_sections(normal_epub: Path):
    sections = epub_structure(normal_epub)
    names = [s["name"] for s in sections]
    assert names == [
        "Cover",
        "Title Page",
        "Chapter 1: Origins",
        "Chapter 2: Growth",
        "Chapter 3: Reflection",
        "Notes",
        "Copyright",
    ]
```

- [ ] **Step 2: Run test, verify it fails**

```bash
pytest tests/test_convert_epub.py -v
```

Expected: FAIL with `ImportError` on `epub_info`.

- [ ] **Step 3: Implement `epub_info` and `epub_structure`**

`book_summarizer/convert/epub.py`:
```python
"""EPUB → chapter-structured markdown, via epub2md subprocess.

epub2md (Node.js, already installed globally) exposes three modes we use:
  - `epub2md -i <epub>` prints metadata
  - `epub2md -s <epub>` prints structure as ANSI-colorized JS literals
  - `epub2md -c <epub>` writes one .md per section to a directory next to
    the source epub

Because the JSON output of `-s` is NOT valid JSON (it's a Node console.log
of a JS object with ANSI colors), we parse metadata and structure by
re-reading the EPUB zip directly. This gives us robust, colorless output.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path


OPF_NS = {
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
}
NCX_NS = {"ncx": "http://www.daisy.org/z3986/2005/ncx/"}
CONTAINER_NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}


def _read_zip_text(zf: zipfile.ZipFile, name: str) -> str:
    return zf.read(name).decode("utf-8")


def _find_opf_path(zf: zipfile.ZipFile) -> str:
    container = ET.fromstring(_read_zip_text(zf, "META-INF/container.xml"))
    rootfile = container.find(".//c:rootfile", CONTAINER_NS)
    if rootfile is None:
        raise ValueError("EPUB missing rootfile in container.xml")
    return rootfile.attrib["full-path"]


def epub_info(epub_path: Path) -> dict:
    """Return {'title': str, 'author': str, 'year': str | None, 'generator': str | None}."""
    with zipfile.ZipFile(epub_path) as zf:
        opf_path = _find_opf_path(zf)
        opf = ET.fromstring(_read_zip_text(zf, opf_path))
        metadata = opf.find("opf:metadata", OPF_NS)
        title_el = metadata.find("dc:title", OPF_NS) if metadata is not None else None
        creator_el = metadata.find("dc:creator", OPF_NS) if metadata is not None else None
        date_el = metadata.find("dc:date", OPF_NS) if metadata is not None else None
        generator = None
        if metadata is not None:
            for meta in metadata.findall("opf:meta", OPF_NS):
                if meta.attrib.get("name") == "generator":
                    generator = meta.attrib.get("content")
                    break
        year = None
        if date_el is not None and date_el.text:
            m = re.search(r"(\d{4})", date_el.text)
            if m:
                year = m.group(1)
        return {
            "title": (title_el.text or "").strip() if title_el is not None else "",
            "author": (creator_el.text or "").strip() if creator_el is not None else "",
            "year": year,
            "generator": generator,
        }


def epub_structure(epub_path: Path) -> list[dict]:
    """Return list of {'name': str, 'src': str} in navMap/playOrder."""
    with zipfile.ZipFile(epub_path) as zf:
        opf_path = _find_opf_path(zf)
        opf_dir = str(Path(opf_path).parent) + "/" if "/" in opf_path else ""
        opf = ET.fromstring(_read_zip_text(zf, opf_path))

        # Find NCX path
        manifest = opf.find("opf:manifest", OPF_NS)
        ncx_href = None
        for item in manifest.findall("opf:item", OPF_NS):
            if item.attrib.get("media-type") == "application/x-dtbncx+xml":
                ncx_href = item.attrib["href"]
                break
        if ncx_href is None:
            return []

        ncx_path = f"{opf_dir}{ncx_href}"
        ncx = ET.fromstring(_read_zip_text(zf, ncx_path))
        nav_points = []
        for np in ncx.iter(f"{{{NCX_NS['ncx']}}}navPoint"):
            label_el = np.find("ncx:navLabel/ncx:text", NCX_NS)
            content_el = np.find("ncx:content", NCX_NS)
            if label_el is None or content_el is None:
                continue
            try:
                order = int(np.attrib.get("playOrder", "0"))
            except ValueError:
                order = 0
            nav_points.append({
                "name": (label_el.text or "").strip(),
                "src": content_el.attrib.get("src", ""),
                "order": order,
            })
        nav_points.sort(key=lambda d: d["order"])
        return [{"name": n["name"], "src": n["src"]} for n in nav_points]


def run_epub2md_convert(epub_path: Path, out_dir: Path, merge: bool = False) -> Path:
    """Run `epub2md -c [--merge]` writing to out_dir. Returns the output directory path."""
    if shutil.which("epub2md") is None:
        raise RuntimeError("epub2md is not installed. Run: npm install -g epub2md")

    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["epub2md", "-c"]
    if merge:
        cmd.append("-m")
    cmd.append(str(epub_path))

    # epub2md writes output in the current working directory based on the epub filename.
    subprocess.run(cmd, check=True, cwd=out_dir, capture_output=True)

    # epub2md creates a subdirectory named after the EPUB (without extension)
    epub_stem = epub_path.stem
    produced = out_dir / epub_stem
    if not produced.exists():
        raise RuntimeError(
            f"epub2md did not produce expected output at {produced}. "
            f"Contents of {out_dir}: {list(out_dir.iterdir())}"
        )
    return produced
```

- [ ] **Step 4: Run info + structure tests, verify pass**

```bash
pytest tests/test_convert_epub.py::test_epub_info_returns_title_and_author tests/test_convert_epub.py::test_epub_structure_returns_ordered_sections -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add book_summarizer/convert/epub.py tests/test_convert_epub.py
git commit -m "feat: epub metadata and structure parsers"
```

---

### Task 7: Section classifier (front / chapter / back matter)

**Files:**
- Modify: `/home/administrator/dev/book-summarizer/book_summarizer/convert/epub.py`
- Modify: `/home/administrator/dev/book-summarizer/tests/test_convert_epub.py`

- [ ] **Step 1: Append failing tests for classify_section**

Add to `tests/test_convert_epub.py`:

```python
from book_summarizer.convert.epub import classify_section, SectionClass


def test_classify_obvious_front_matter():
    assert classify_section("Cover") == SectionClass.FRONT
    assert classify_section("Title Page") == SectionClass.FRONT
    assert classify_section("Copyright") == SectionClass.BACK  # copyright is back per spec listing
    assert classify_section("Dedication") == SectionClass.FRONT
    assert classify_section("Epigraph") == SectionClass.FRONT
    assert classify_section("Welcome") == SectionClass.FRONT


def test_classify_obvious_back_matter():
    assert classify_section("Notes") == SectionClass.BACK
    assert classify_section("Index") == SectionClass.BACK
    assert classify_section("About the Author") == SectionClass.BACK
    assert classify_section("Newsletters") == SectionClass.BACK
    assert classify_section("Also by Cal Newport") == SectionClass.BACK
    assert classify_section("footnotes") == SectionClass.BACK
    assert classify_section("Table of Contents") == SectionClass.BACK


def test_classify_chapters_and_parts():
    assert classify_section("Chapter 1: Origins") == SectionClass.CHAPTER
    assert classify_section("1 The Surprising Power of Atomic Habits") == SectionClass.CHAPTER
    assert classify_section("Introduction") == SectionClass.CHAPTER
    assert classify_section("Introduction: My Story") == SectionClass.CHAPTER
    assert classify_section("Conclusion") == SectionClass.CHAPTER
    assert classify_section("PART 1: The Idea") == SectionClass.CHAPTER
    assert classify_section("Rule #1: Work Deeply") == SectionClass.CHAPTER
    assert classify_section("The Fundamentals") == SectionClass.CHAPTER  # unknown → default chapter
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/test_convert_epub.py -k classify -v
```

Expected: FAIL with `ImportError` on `classify_section` / `SectionClass`.

- [ ] **Step 3: Implement classifier**

Append to `book_summarizer/convert/epub.py`:

```python
from enum import Enum


class SectionClass(str, Enum):
    FRONT = "front"
    CHAPTER = "chapter"
    BACK = "back"


# Patterns to identify non-chapter matter by section name.
# Each pattern is a lowercase substring or regex that decides the class.
_FRONT_PATTERNS = [
    re.compile(r"^cover$"),
    re.compile(r"^title page$"),
    re.compile(r"^half title$"),
    re.compile(r"^dedication$"),
    re.compile(r"^epigraph$"),
    re.compile(r"^welcome$"),
    re.compile(r"^praise for\b"),
    re.compile(r"^also by\b"),  # "also by X" at the start is front matter when it precedes chapters;
    # but our heuristic treats 'also by' as back matter (see below). Handle via BACK list.
    re.compile(r"^acknowledg[e]?ments?$"),  # can appear front OR back; when front, rare. default front.
    re.compile(r"^foreword$"),
    re.compile(r"^preface$"),
    re.compile(r"^prologue$"),
]

_BACK_PATTERNS = [
    re.compile(r"^notes$"),
    re.compile(r"^footnotes$"),
    re.compile(r"^endnotes$"),
    re.compile(r"^index$"),
    re.compile(r"^glossary$"),
    re.compile(r"^bibliography$"),
    re.compile(r"^references$"),
    re.compile(r"^copyright$"),
    re.compile(r"^colophon$"),
    re.compile(r"^about the author$"),
    re.compile(r"^about the publisher$"),
    re.compile(r"^newsletter"),
    re.compile(r"^newsletters"),
    re.compile(r"^table of contents$"),
    re.compile(r"^contents$"),
    re.compile(r"^also by\b"),
    re.compile(r"^appendix\b"),  # treat appendices as back matter for summarization purposes
]


_CHAPTER_PATTERNS = [
    re.compile(r"^(chapter|chap\.?)\s+\d+\b", re.IGNORECASE),
    re.compile(r"^\d+\s+\S", re.IGNORECASE),  # "1 The Surprising..."
    re.compile(r"^introduction(:|$|\s)", re.IGNORECASE),
    re.compile(r"^conclusion(:|$|\s)", re.IGNORECASE),
    re.compile(r"^epilogue(:|$|\s)", re.IGNORECASE),
    re.compile(r"^part\s+[ivx\d]+", re.IGNORECASE),  # PART 1, Part II
    re.compile(r"^rule\s+#?\d+", re.IGNORECASE),     # Rule #1, Rule 2
    re.compile(r"^the\s+\w+\s+law\b", re.IGNORECASE),
]


def classify_section(name: str) -> SectionClass:
    """Heuristic classifier for an EPUB section name."""
    n = (name or "").strip()
    n_lower = n.lower()

    # Front-matter wins first for exact-name matches that are unambiguously front.
    for pat in _FRONT_PATTERNS:
        if pat.match(n_lower):
            # "also by" is front-pattern-looking but we've also listed it as back.
            # Prefer back disposition because it typically appears after chapters
            # in spine order.
            for back_pat in _BACK_PATTERNS:
                if back_pat.match(n_lower):
                    return SectionClass.BACK
            return SectionClass.FRONT

    for pat in _BACK_PATTERNS:
        if pat.match(n_lower):
            return SectionClass.BACK

    for pat in _CHAPTER_PATTERNS:
        if pat.search(n):
            return SectionClass.CHAPTER

    # Unknown label → default to chapter (better to include uncertain sections
    # than filter them out; synthesis will weight accordingly).
    return SectionClass.CHAPTER
```

- [ ] **Step 4: Run classify tests, verify pass**

```bash
pytest tests/test_convert_epub.py -k classify -v
```

Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add book_summarizer/convert/epub.py tests/test_convert_epub.py
git commit -m "feat: section classifier for EPUB front/back matter"
```

---

### Task 8: PDF-origin detection

**Files:**
- Modify: `/home/administrator/dev/book-summarizer/book_summarizer/convert/epub.py`
- Create: `/home/administrator/dev/book-summarizer/tests/test_convert_epub_pdf_origin.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_convert_epub_pdf_origin.py
from pathlib import Path

from book_summarizer.convert.epub import is_pdf_origin


def test_detect_pdf_origin_via_generator(pdf_origin_epub: Path):
    assert is_pdf_origin(pdf_origin_epub) is True


def test_normal_epub_is_not_pdf_origin(normal_epub: Path):
    assert is_pdf_origin(normal_epub) is False
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/test_convert_epub_pdf_origin.py -v
```

Expected: FAIL with `ImportError` on `is_pdf_origin`.

- [ ] **Step 3: Implement is_pdf_origin**

Append to `book_summarizer/convert/epub.py`:

```python
def is_pdf_origin(epub_path: Path) -> bool:
    """True if EPUB shows signs of being derived from a PDF.

    Signals (any one triggers):
      - <meta name="generator" content="pdftohtml..."> in the OPF
      - Content files contain 'pdftohtml' string references
      - spine item count << TOC chapter count (>= 3x more TOC entries)
    """
    info = epub_info(epub_path)
    gen = (info.get("generator") or "").lower()
    if "pdftohtml" in gen:
        return True

    with zipfile.ZipFile(epub_path) as zf:
        # Scan HTML/XHTML content files for the pdftohtml marker
        for name in zf.namelist():
            if name.lower().endswith((".html", ".xhtml")):
                try:
                    body = _read_zip_text(zf, name)
                except (UnicodeDecodeError, KeyError):
                    continue
                if "pdftohtml" in body.lower():
                    return True

        # Compare spine vs TOC counts
        opf_path = _find_opf_path(zf)
        opf = ET.fromstring(_read_zip_text(zf, opf_path))
        spine = opf.find("opf:spine", OPF_NS)
        spine_count = len(spine.findall("opf:itemref", OPF_NS)) if spine is not None else 0

    toc_count = len(epub_structure(epub_path))
    if spine_count > 0 and toc_count >= spine_count * 3:
        return True
    return False
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/test_convert_epub_pdf_origin.py -v
```

Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add book_summarizer/convert/epub.py tests/test_convert_epub_pdf_origin.py
git commit -m "feat: PDF-origin EPUB detection"
```

---

### Task 9: End-to-end EPUB conversion to chapter-structured markdown

This is the heart of Tier 1. Orchestrates epub2md + structure + classifier into a single markdown output.

**Files:**
- Modify: `/home/administrator/dev/book-summarizer/book_summarizer/convert/epub.py`
- Modify: `/home/administrator/dev/book-summarizer/tests/test_convert_epub.py`

- [ ] **Step 1: Append failing end-to-end test**

Add to `tests/test_convert_epub.py`:

```python
from book_summarizer.convert.epub import convert_epub_to_markdown


def test_convert_normal_epub_produces_chapter_headings(normal_epub: Path, tmp_path: Path):
    out = tmp_path / "out.md"
    result = convert_epub_to_markdown(normal_epub, out)
    text = out.read_text()

    # All sections appear
    assert "# Front Matter — Cover" in text
    assert "# Front Matter — Title Page" in text
    assert "# Chapter 1 — Chapter 1: Origins" in text
    assert "# Chapter 2 — Chapter 2: Growth" in text
    assert "# Chapter 3 — Chapter 3: Reflection" in text
    assert "# Back Matter — Notes" in text
    assert "# Back Matter — Copyright" in text

    # Result metadata is correct
    assert result.chapter_count == 3
    assert result.conversion_quality == "high"


def test_convert_pdf_origin_uses_merged_flat_mode(pdf_origin_epub: Path, tmp_path: Path):
    out = tmp_path / "out.md"
    result = convert_epub_to_markdown(pdf_origin_epub, out)
    assert result.conversion_quality == "low"
    assert result.chapter_count == 0  # unreliable — flat mode does not emit class-prefixed H1s
    # File still exists with some content
    assert out.exists()
    assert out.stat().st_size > 0
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/test_convert_epub.py -k convert_ -v
```

Expected: FAIL with `ImportError` on `convert_epub_to_markdown`.

- [ ] **Step 3: Implement convert_epub_to_markdown**

Append to `book_summarizer/convert/epub.py`:

```python
@dataclass
class ConversionResult:
    chapter_count: int
    conversion_quality: str  # 'high' or 'low'
    mode: str  # 'structured' or 'flat'


def _read_section_markdown(section_md_dir: Path, section_index: int) -> str:
    """epub2md writes section .md files with a `NN-slugified_name.md` naming
    convention. Pick the Nth file by leading number (1-indexed, matching our
    navMap order)."""
    candidates = sorted(section_md_dir.glob(f"{section_index:02d}-*.md"))
    if not candidates:
        # epub2md sometimes uses zero-padded or non-padded numbers; try plain int
        candidates = sorted(section_md_dir.glob(f"{section_index}-*.md"))
    if not candidates:
        return ""
    return candidates[0].read_text()


def convert_epub_to_markdown(epub_path: Path, out_path: Path) -> ConversionResult:
    """Convert an EPUB to a single chapter-structured markdown file.

    Properly-structured EPUBs: one `# Chapter N — <Title>` per chapter, plus
    `# Front Matter — <Title>` / `# Back Matter — <Title>` for everything else.

    PDF-origin EPUBs: flat merge; no class-prefixed H1s emitted. Result
    conversion_quality == 'low'.
    """
    import tempfile

    out_path.parent.mkdir(parents=True, exist_ok=True)

    if is_pdf_origin(epub_path):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            run_epub2md_convert(epub_path, td_path, merge=True)
            # In merge mode, epub2md writes a single `<epub-stem>.md` in the
            # subdirectory <epub-stem>/. Copy it verbatim.
            merged_dir = td_path / epub_path.stem
            merged_md = merged_dir / f"{epub_path.stem}.md"
            if not merged_md.exists():
                # Some epub2md versions write at the top of merged_dir
                mds = list(merged_dir.glob("*.md"))
                if not mds:
                    raise RuntimeError(f"epub2md merge mode produced no markdown in {merged_dir}")
                merged_md = mds[0]
            out_path.write_text(merged_md.read_text())
        return ConversionResult(chapter_count=0, conversion_quality="low", mode="flat")

    # Structured mode
    structure = epub_structure(epub_path)
    if not structure:
        # No NCX → fall back to flat merge, flagged low
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            run_epub2md_convert(epub_path, td_path, merge=True)
            merged_dir = td_path / epub_path.stem
            mds = list(merged_dir.glob("*.md"))
            if mds:
                out_path.write_text(mds[0].read_text())
        return ConversionResult(chapter_count=0, conversion_quality="low", mode="flat")

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        section_dir = run_epub2md_convert(epub_path, td_path, merge=False)

        chapter_num = 0
        parts: list[str] = []
        for i, section in enumerate(structure, start=1):
            name = section["name"]
            cls = classify_section(name)
            if cls == SectionClass.CHAPTER:
                chapter_num += 1
                heading = f"# Chapter {chapter_num} — {name}"
            elif cls == SectionClass.FRONT:
                heading = f"# Front Matter — {name}"
            else:
                heading = f"# Back Matter — {name}"
            body = _read_section_markdown(section_dir, i)
            parts.append(f"{heading}\n\n{body.strip()}\n")

        out_path.write_text("\n".join(parts))

    return ConversionResult(
        chapter_count=chapter_num,
        conversion_quality="high",
        mode="structured",
    )
```

- [ ] **Step 4: Run end-to-end tests, verify pass**

```bash
pytest tests/test_convert_epub.py -k convert_ -v
```

Expected: PASS (2 tests).

- [ ] **Step 5: Run full convert suite**

```bash
pytest tests/test_convert_epub.py tests/test_convert_epub_pdf_origin.py -v
```

Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add book_summarizer/convert/epub.py tests/test_convert_epub.py
git commit -m "feat: end-to-end EPUB → chapter-structured markdown"
```

---

### Task 10: PDF conversion via pandoc

**Files:**
- Create: `/home/administrator/dev/book-summarizer/book_summarizer/convert/pdf.py`
- Create: `/home/administrator/dev/book-summarizer/tests/test_convert_pdf.py`

- [ ] **Step 1: Write failing test (no test PDF needed — we test the function logic paths with a fake PDF path)**

```python
# tests/test_convert_pdf.py
from pathlib import Path
from unittest.mock import patch

import pytest

from book_summarizer.convert.pdf import convert_pdf_to_markdown


def test_convert_pdf_requires_existing_file(tmp_path: Path):
    out = tmp_path / "out.md"
    with pytest.raises(FileNotFoundError):
        convert_pdf_to_markdown(tmp_path / "nope.pdf", out)


def test_convert_pdf_flags_low_quality_when_few_headings(tmp_path: Path):
    src = tmp_path / "fake.pdf"
    src.write_bytes(b"%PDF-1.4 stub")  # not real; we'll mock pandoc
    out = tmp_path / "out.md"

    def fake_pandoc(*args, **kwargs):
        out.write_text("No headings in this output. Just prose. " * 500)

        class R:
            returncode = 0
        return R()

    with patch("book_summarizer.convert.pdf.subprocess.run", side_effect=fake_pandoc):
        result = convert_pdf_to_markdown(src, out)

    assert result.conversion_quality == "low"
    assert result.chapter_count == 0


def test_convert_pdf_flags_high_quality_when_many_headings(tmp_path: Path):
    src = tmp_path / "fake.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    out = tmp_path / "out.md"

    def fake_pandoc(*args, **kwargs):
        out.write_text(
            "# Chapter 1\n\nStuff.\n\n"
            "# Chapter 2\n\nMore stuff.\n\n"
            "# Chapter 3\n\nEven more stuff.\n\n"
            "# Chapter 4\n\nYet more.\n"
        )

        class R:
            returncode = 0
        return R()

    with patch("book_summarizer.convert.pdf.subprocess.run", side_effect=fake_pandoc):
        result = convert_pdf_to_markdown(src, out)

    assert result.conversion_quality == "high"
    assert result.chapter_count == 4
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/test_convert_pdf.py -v
```

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement convert_pdf_to_markdown**

`book_summarizer/convert/pdf.py`:
```python
"""PDF → markdown via pandoc. Best-effort; flags low quality on sparse output."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PdfConversionResult:
    chapter_count: int
    conversion_quality: str  # 'high' or 'low'


def convert_pdf_to_markdown(pdf_path: Path, out_path: Path) -> PdfConversionResult:
    """Run pandoc on a PDF and score structural quality by H1 count.

    The result markdown is left at out_path regardless of quality. `low`
    quality books get routed to the single-pass fallback in Tier 2.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(str(pdf_path))
    if shutil.which("pandoc") is None:
        raise RuntimeError("pandoc not installed. Run: apt install pandoc")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["pandoc", "-f", "pdf", "-t", "markdown", "-o", str(out_path), str(pdf_path)],
        check=True,
        capture_output=True,
    )

    text = out_path.read_text()
    h1_count = sum(1 for line in text.splitlines() if line.startswith("# "))
    # Threshold from spec: < 3 H1s on a > 100-page PDF → low.
    # We don't have reliable page counts for all PDFs; approximate by content length.
    is_long = len(text) > 50_000  # ~100 pages of prose
    if h1_count < 3 and is_long:
        quality = "low"
        chapter_count = 0
    else:
        quality = "high"
        chapter_count = h1_count

    return PdfConversionResult(chapter_count=chapter_count, conversion_quality=quality)
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/test_convert_pdf.py -v
```

Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add book_summarizer/convert/pdf.py tests/test_convert_pdf.py
git commit -m "feat: PDF → markdown via pandoc with quality scoring"
```

---

### Task 11: Markdown pass-through with heading scan

**Files:**
- Create: `/home/administrator/dev/book-summarizer/book_summarizer/convert/markdown.py`
- Create: `/home/administrator/dev/book-summarizer/tests/test_convert_markdown.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_convert_markdown.py
from pathlib import Path

from book_summarizer.convert.markdown import convert_markdown_to_markdown


def test_structured_markdown_passes_through(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text(
        "# Chapter 1\nX.\n# Chapter 2\nY.\n# Chapter 3\nZ.\n"
    )
    out = tmp_path / "out.md"
    result = convert_markdown_to_markdown(src, out)
    assert result.conversion_quality == "high"
    assert result.chapter_count == 3
    assert out.read_text() == src.read_text()


def test_unstructured_markdown_is_low_quality(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text("Just prose, no headings at all. " * 500)
    out = tmp_path / "out.md"
    result = convert_markdown_to_markdown(src, out)
    assert result.conversion_quality == "low"
    assert result.chapter_count == 0
```

- [ ] **Step 2: Run, verify fail**

```bash
pytest tests/test_convert_markdown.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement**

`book_summarizer/convert/markdown.py`:
```python
"""Markdown pass-through: copy source verbatim, score structural quality."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MarkdownConversionResult:
    chapter_count: int
    conversion_quality: str  # 'high' or 'low'


def convert_markdown_to_markdown(src: Path, out_path: Path) -> MarkdownConversionResult:
    if not src.exists():
        raise FileNotFoundError(str(src))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, out_path)

    text = out_path.read_text()
    h1_count = sum(1 for line in text.splitlines() if line.startswith("# "))
    if h1_count >= 3:
        return MarkdownConversionResult(chapter_count=h1_count, conversion_quality="high")
    return MarkdownConversionResult(chapter_count=0, conversion_quality="low")
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/test_convert_markdown.py -v
```

Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add book_summarizer/convert/markdown.py tests/test_convert_markdown.py
git commit -m "feat: markdown pass-through with heading-based quality score"
```

---

## Phase C: Metadata

### Task 12: Metadata extraction with filename fallback

**Files:**
- Create: `/home/administrator/dev/book-summarizer/book_summarizer/metadata.py`
- Create: `/home/administrator/dev/book-summarizer/tests/test_metadata.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_metadata.py
from pathlib import Path

from book_summarizer.metadata import extract_metadata


def test_extract_metadata_from_epub(normal_epub: Path):
    md = extract_metadata(normal_epub)
    assert md["title"] == "The Test Book"
    assert md["author"] == "Test Author"
    assert md["year"] == "2024"


def test_fallback_to_filename_for_markdown(tmp_path: Path):
    p = tmp_path / "Deep Work - Cal Newport.md"
    p.write_text("# Chapter 1\n")
    md = extract_metadata(p)
    assert md["title"] == "Deep Work"
    assert md["author"] == "Cal Newport"


def test_frontmatter_title_wins_over_filename(tmp_path: Path):
    p = tmp_path / "Wrong Name - Wrong Author.md"
    p.write_text("---\ntitle: Real Title\nauthor: Real Author\nyear: 2021\n---\n# C1\n")
    md = extract_metadata(p)
    assert md["title"] == "Real Title"
    assert md["author"] == "Real Author"
    assert md["year"] == "2021"


def test_filename_without_separator_gives_title_only(tmp_path: Path):
    p = tmp_path / "Standalone.md"
    p.write_text("# Stuff\n")
    md = extract_metadata(p)
    assert md["title"] == "Standalone"
    assert md["author"] == ""
```

- [ ] **Step 2: Run, verify fail**

```bash
pytest tests/test_metadata.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement**

`book_summarizer/metadata.py`:
```python
"""Extract title/author/year from EPUB, PDF, or markdown input."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from book_summarizer.convert.epub import epub_info


def _parse_filename(path: Path) -> dict:
    stem = path.stem
    # Common conventions: "Title - Author.ext" or "Title - Author - <hash>.ext"
    parts = [p.strip() for p in stem.split(" - ")]
    if len(parts) >= 2:
        # If the last chunk looks like a 32-hex md5 or similar, drop it
        if re.fullmatch(r"[0-9a-f]{20,}", parts[-1], re.IGNORECASE):
            parts = parts[:-1]
    if len(parts) >= 2:
        return {"title": parts[0], "author": parts[1], "year": None}
    return {"title": parts[0], "author": "", "year": None}


def _extract_markdown_frontmatter(path: Path) -> dict:
    text = path.read_text()
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    try:
        data = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        return {}
    return {
        "title": data.get("title"),
        "author": data.get("author"),
        "year": str(data["year"]) if data.get("year") is not None else None,
    }


def extract_metadata(path: Path) -> dict:
    """Return {'title': str, 'author': str, 'year': str | None}."""
    path = Path(path)
    ext = path.suffix.lower()

    filename_guess = _parse_filename(path)

    if ext == ".epub":
        info = epub_info(path)
        return {
            "title": info.get("title") or filename_guess["title"],
            "author": info.get("author") or filename_guess["author"],
            "year": info.get("year") or filename_guess["year"],
        }

    if ext in {".md", ".markdown"}:
        fm = _extract_markdown_frontmatter(path)
        return {
            "title": fm.get("title") or filename_guess["title"],
            "author": fm.get("author") or filename_guess["author"],
            "year": fm.get("year") or filename_guess["year"],
        }

    # PDF and unknown: use filename only (PDF metadata extraction deferred)
    return filename_guess
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/test_metadata.py -v
```

Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add book_summarizer/metadata.py tests/test_metadata.py
git commit -m "feat: metadata extraction with YAML frontmatter + filename fallback"
```

---

### Task 13: Format detection + unified convert() dispatcher

**Files:**
- Modify: `/home/administrator/dev/book-summarizer/book_summarizer/convert/__init__.py`
- Create: `/home/administrator/dev/book-summarizer/tests/test_convert_dispatch.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_convert_dispatch.py
from pathlib import Path

import pytest

from book_summarizer.convert import convert, detect_format


def test_detect_format_by_extension(tmp_path: Path):
    (tmp_path / "book.epub").touch()
    (tmp_path / "book.pdf").touch()
    (tmp_path / "book.md").touch()
    (tmp_path / "book.markdown").touch()
    assert detect_format(tmp_path / "book.epub") == "epub"
    assert detect_format(tmp_path / "book.pdf") == "pdf"
    assert detect_format(tmp_path / "book.md") == "markdown"
    assert detect_format(tmp_path / "book.markdown") == "markdown"


def test_detect_format_rejects_unknown(tmp_path: Path):
    (tmp_path / "book.xyz").touch()
    with pytest.raises(ValueError):
        detect_format(tmp_path / "book.xyz")


def test_convert_dispatches_to_epub(normal_epub: Path, tmp_path: Path):
    out = tmp_path / "out.md"
    result = convert(normal_epub, out)
    assert result.conversion_quality == "high"
    assert result.chapter_count == 3
    assert result.mode == "structured"
```

- [ ] **Step 2: Run, verify fail**

```bash
pytest tests/test_convert_dispatch.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement**

Rewrite `book_summarizer/convert/__init__.py`:
```python
"""Format detection and convert() dispatcher."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from book_summarizer.convert.epub import convert_epub_to_markdown
from book_summarizer.convert.pdf import convert_pdf_to_markdown
from book_summarizer.convert.markdown import convert_markdown_to_markdown


@dataclass
class UnifiedConversionResult:
    chapter_count: int
    conversion_quality: str
    mode: str
    source_format: str


def detect_format(path: Path) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".epub":
        return "epub"
    if ext == ".pdf":
        return "pdf"
    if ext in {".md", ".markdown"}:
        return "markdown"
    raise ValueError(f"Unsupported format: {ext}")


def convert(src: Path, out_path: Path) -> UnifiedConversionResult:
    fmt = detect_format(src)
    if fmt == "epub":
        r = convert_epub_to_markdown(src, out_path)
        return UnifiedConversionResult(
            chapter_count=r.chapter_count,
            conversion_quality=r.conversion_quality,
            mode=r.mode,
            source_format="epub",
        )
    if fmt == "pdf":
        r = convert_pdf_to_markdown(src, out_path)
        return UnifiedConversionResult(
            chapter_count=r.chapter_count,
            conversion_quality=r.conversion_quality,
            mode="structured" if r.conversion_quality == "high" else "flat",
            source_format="pdf",
        )
    # markdown
    r = convert_markdown_to_markdown(src, out_path)
    return UnifiedConversionResult(
        chapter_count=r.chapter_count,
        conversion_quality=r.conversion_quality,
        mode="structured" if r.conversion_quality == "high" else "flat",
        source_format="markdown",
    )
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/test_convert_dispatch.py -v
```

Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add book_summarizer/convert/__init__.py tests/test_convert_dispatch.py
git commit -m "feat: format detection and convert() dispatcher"
```

---

## Phase D: Vault writer

### Task 14: Vault bootstrap

**Files:**
- Create: `/home/administrator/dev/book-summarizer/book_summarizer/vault.py`
- Create: `/home/administrator/dev/book-summarizer/tests/test_vault.py`

- [ ] **Step 1: Write failing test for bootstrap**

```python
# tests/test_vault.py
from pathlib import Path

from book_summarizer.vault import bootstrap_vault


def test_bootstrap_creates_expected_structure(tmp_vault: Path):
    bootstrap_vault(tmp_vault)
    expected_dirs = ["raw/books", "books", "entities", "concepts", "comparisons", "queries"]
    for d in expected_dirs:
        assert (tmp_vault / d).is_dir(), f"missing dir: {d}"
    expected_files = ["SCHEMA.md", "index.md", "log.md", "collected.md", "analysis_queue.md"]
    for f in expected_files:
        assert (tmp_vault / f).is_file(), f"missing file: {f}"

    # SCHEMA.md should contain the domain and placeholder taxonomy
    schema_text = (tmp_vault / "SCHEMA.md").read_text()
    assert "Book Summaries" in schema_text
    assert "Tag Taxonomy" in schema_text


def test_bootstrap_is_idempotent(tmp_vault: Path):
    bootstrap_vault(tmp_vault)
    (tmp_vault / "collected.md").write_text("custom-content\n")
    # Run again; existing files should NOT be overwritten
    bootstrap_vault(tmp_vault)
    assert (tmp_vault / "collected.md").read_text() == "custom-content\n"
```

- [ ] **Step 2: Run, verify fail**

```bash
pytest tests/test_vault.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement bootstrap**

`book_summarizer/vault.py`:
```python
"""Obsidian LLM-wiki vault writer: bootstrap, collected.md, analysis_queue.md, raw/books."""
from __future__ import annotations

import datetime as dt
from pathlib import Path


SCHEMA_TEMPLATE = """# Wiki Schema — Book Summaries

> Generated by book-summarizer on {date}. Edit freely; the /summarize-book
> slash command reads this file to know your conventions, but only updates
> index.md and log.md automatically. The tag taxonomy below is the contract:
> new tags must be added here BEFORE being used on a page.

## Domain

This wiki covers **books**: analyzed book summaries and the entities
(people, organizations, studies, products) and concepts (ideas, mechanisms,
frameworks) they cite, plus cross-book comparisons and verify queries.

## Conventions

- File names: `<Title> - <Author>.md` for books. Entities and concepts use
  their own names (`Jim Collins.md`, `flywheel effect.md`). Comparisons use
  `<slug> - contradiction.md`.
- Every wiki page starts with YAML frontmatter.
- Use `[[wikilinks]]` to link between pages.
- Book summaries must link to every entity/concept page they touch.
- Entity/concept pages back-link to every book that cited them.
- Bump the `updated` date when a page is modified.
- Every new page must be added to index.md under the correct section.
- Every analyze action is appended to log.md.

## Frontmatter (book page)

```yaml
---
title: <Book Title>
author: <Author Name>
year: <Publication Year>
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: book
tags: [from taxonomy below]
raw_path: raw/books/<Title> - <Author>.md
isbn: <if available>
pages: <if available>
summary_mode: map-reduce | single-pass
lens: <lens name>
---
```

## Tag Taxonomy

- genre: non-fiction, fiction, self-help, business, philosophy, memoir, biography, science, history
- meta: contradiction, controversy, weak-claim, unverified, verified, critical-pass

## Page Creation Thresholds

- **Create an entity/concept page** when mentioned in 2+ books OR central to one.
- **Add to existing page** when a new book mentions it.
- **DON'T create a page** for passing mentions.
- **Split a page** when it exceeds ~200 lines.

## Update Policy

When new information conflicts with existing content:
1. Check publication dates — newer books do not automatically supersede older
   ones (philosophy is not chronology).
2. If genuinely contradictory, note both positions with wikilinks and create a
   `comparisons/<slug> - contradiction.md` page.
3. Flag for user review in the next analyze run.
"""

INDEX_TEMPLATE = """# Index — Book Summaries

## By Author

_(populated by /summarize-book)_

## By Topic

_(populated by /summarize-book)_

## By Date Analyzed

_(populated by /summarize-book)_
"""

LOG_TEMPLATE = """# Action Log

> Append-only. Every /summarize-book run adds an entry.

"""

COLLECTED_HEADER = """# Collected Books

> One row per ingested book. Edit with /summarize-book or via CLI.

| Title | Author | Status | Chapters | Conversion | Mode | Lens | Analyzed At | Source |
|---|---|---|---|---|---|---|---|---|
"""

ANALYSIS_QUEUE_HEADER = """# Analysis Queue

> Oldest-first. /summarize-book pops from here.

"""


def bootstrap_vault(vault_path: Path) -> None:
    """Ensure vault folder structure and index files exist. Idempotent."""
    vault_path = Path(vault_path)
    vault_path.mkdir(parents=True, exist_ok=True)

    for sub in ("raw/books", "books", "entities", "concepts", "comparisons", "queries"):
        (vault_path / sub).mkdir(parents=True, exist_ok=True)

    today = dt.date.today().isoformat()
    defaults = [
        ("SCHEMA.md", SCHEMA_TEMPLATE.format(date=today)),
        ("index.md", INDEX_TEMPLATE),
        ("log.md", LOG_TEMPLATE),
        ("collected.md", COLLECTED_HEADER),
        ("analysis_queue.md", ANALYSIS_QUEUE_HEADER),
    ]
    for name, content in defaults:
        p = vault_path / name
        if not p.exists():
            p.write_text(content)
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/test_vault.py::test_bootstrap_creates_expected_structure tests/test_vault.py::test_bootstrap_is_idempotent -v
```

Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add book_summarizer/vault.py tests/test_vault.py
git commit -m "feat: vault bootstrap with SCHEMA.md, index.md, log.md, collected.md"
```

---

### Task 15: Write raw book markdown

**Files:**
- Modify: `/home/administrator/dev/book-summarizer/book_summarizer/vault.py`
- Modify: `/home/administrator/dev/book-summarizer/tests/test_vault.py`

- [ ] **Step 1: Append failing test**

```python
# tests/test_vault.py (append)
from book_summarizer.vault import write_raw_book, raw_book_path


def test_write_raw_book(tmp_vault: Path):
    dest = write_raw_book(
        vault_path=tmp_vault,
        title="Deep Work",
        author="Cal Newport",
        source_markdown_path=None,
        content="# Chapter 1 — Something\n\nBody.\n",
    )
    expected = tmp_vault / "raw" / "books" / "Deep Work - Cal Newport.md"
    assert dest == expected
    assert dest.read_text().startswith("# Chapter 1")


def test_raw_book_path_slugs_unsafe_chars(tmp_vault: Path):
    p = raw_book_path(tmp_vault, "Title: Subtitle / Slash", "Author Name")
    # Colons and slashes are replaced for filesystem safety
    assert ":" not in p.name
    assert "/" not in p.name.replace(" - ", "")
    assert p.parent == tmp_vault / "raw" / "books"
```

- [ ] **Step 2: Run, verify fail**

```bash
pytest tests/test_vault.py -k raw -v
```

Expected: FAIL.

- [ ] **Step 3: Implement**

Append to `book_summarizer/vault.py`:
```python
import re
import shutil


def _safe_filename(s: str) -> str:
    """Replace filesystem-unsafe characters for Obsidian compatibility.

    Obsidian supports almost everything, but we normalize anyway:
      - colon, slash, backslash, question mark, asterisk, less/greater, pipe → underscore
      - strip leading/trailing whitespace
    """
    s = s.strip()
    return re.sub(r'[:\\/?*<>|"]', "_", s)


def raw_book_path(vault_path: Path, title: str, author: str) -> Path:
    """Canonical raw/books/<Title> - <Author>.md path."""
    safe_title = _safe_filename(title)
    safe_author = _safe_filename(author) if author else "Unknown"
    return Path(vault_path) / "raw" / "books" / f"{safe_title} - {safe_author}.md"


def write_raw_book(
    vault_path: Path,
    title: str,
    author: str,
    source_markdown_path: Path | None,
    content: str | None = None,
) -> Path:
    """Write the raw chapter-structured markdown for a book.

    Either provide `source_markdown_path` (copied) or `content` (written directly).
    """
    dest = raw_book_path(vault_path, title, author)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if source_markdown_path is not None and content is not None:
        raise ValueError("Provide source_markdown_path OR content, not both")
    if source_markdown_path is not None:
        shutil.copyfile(source_markdown_path, dest)
    elif content is not None:
        dest.write_text(content)
    else:
        raise ValueError("Provide source_markdown_path OR content")
    return dest
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/test_vault.py -k raw -v
```

Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add book_summarizer/vault.py tests/test_vault.py
git commit -m "feat: write raw book markdown with filesystem-safe naming"
```

---

### Task 16: collected.md row append + is-already-ingested check

**Files:**
- Modify: `/home/administrator/dev/book-summarizer/book_summarizer/vault.py`
- Modify: `/home/administrator/dev/book-summarizer/tests/test_vault.py`

- [ ] **Step 1: Append failing tests**

```python
# tests/test_vault.py (append)
from book_summarizer.vault import (
    append_collected_row,
    is_ingested,
    CollectedRow,
)


def test_append_collected_row_writes_entry(tmp_vault: Path):
    bootstrap_vault(tmp_vault)
    row = CollectedRow(
        title="Deep Work",
        author="Cal Newport",
        status="queued",
        chapters=15,
        conversion_quality="high",
        mode="structured",
        lens="",
        analyzed_at="",
        source=str(tmp_vault / "source.epub"),
    )
    append_collected_row(tmp_vault, row)
    text = (tmp_vault / "collected.md").read_text()
    assert "Deep Work" in text
    assert "Cal Newport" in text
    assert "queued" in text
    assert "high" in text


def test_is_ingested_after_append(tmp_vault: Path):
    bootstrap_vault(tmp_vault)
    assert is_ingested(tmp_vault, "Deep Work", "Cal Newport") is False
    row = CollectedRow(
        title="Deep Work", author="Cal Newport", status="queued",
        chapters=15, conversion_quality="high", mode="structured",
        lens="", analyzed_at="", source="/tmp/x.epub",
    )
    append_collected_row(tmp_vault, row)
    assert is_ingested(tmp_vault, "Deep Work", "Cal Newport") is True
```

- [ ] **Step 2: Run, verify fail**

```bash
pytest tests/test_vault.py -k collected -v
```

Expected: FAIL.

- [ ] **Step 3: Implement**

Append to `book_summarizer/vault.py`:
```python
from dataclasses import dataclass


@dataclass
class CollectedRow:
    title: str
    author: str
    status: str            # 'queued' | 'analyzed' | 'failed'
    chapters: int
    conversion_quality: str  # 'high' | 'low'
    mode: str              # 'structured' | 'flat'
    lens: str              # '' when not yet analyzed
    analyzed_at: str       # '' when not yet analyzed
    source: str            # absolute source path

    def to_row(self) -> str:
        cols = [
            self.title,
            self.author,
            self.status,
            str(self.chapters),
            self.conversion_quality,
            self.mode,
            self.lens,
            self.analyzed_at,
            self.source,
        ]
        # Escape pipes in cell values to avoid breaking markdown table
        cols = [c.replace("|", "\\|") for c in cols]
        return "| " + " | ".join(cols) + " |"


def append_collected_row(vault_path: Path, row: CollectedRow) -> None:
    collected = Path(vault_path) / "collected.md"
    if not collected.exists():
        collected.write_text(COLLECTED_HEADER)
    with collected.open("a") as fh:
        fh.write(row.to_row() + "\n")


def _read_collected_rows(vault_path: Path) -> list[dict]:
    collected = Path(vault_path) / "collected.md"
    if not collected.exists():
        return []
    rows = []
    header_passed = False
    for line in collected.read_text().splitlines():
        if line.startswith("|---"):
            header_passed = True
            continue
        if not header_passed:
            continue
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 9:
            continue
        rows.append({
            "title": cells[0],
            "author": cells[1],
            "status": cells[2],
            "chapters": cells[3],
            "conversion_quality": cells[4],
            "mode": cells[5],
            "lens": cells[6],
            "analyzed_at": cells[7],
            "source": cells[8],
        })
    return rows


def is_ingested(vault_path: Path, title: str, author: str) -> bool:
    for row in _read_collected_rows(vault_path):
        if row["title"] == title and row["author"] == author:
            return True
    return False
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/test_vault.py -k collected -v
```

Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add book_summarizer/vault.py tests/test_vault.py
git commit -m "feat: collected.md row append + is_ingested check"
```

---

### Task 17: analysis_queue.md enqueue

**Files:**
- Modify: `/home/administrator/dev/book-summarizer/book_summarizer/vault.py`
- Modify: `/home/administrator/dev/book-summarizer/tests/test_vault.py`

- [ ] **Step 1: Append failing test**

```python
# tests/test_vault.py (append)
from book_summarizer.vault import enqueue_for_analysis, read_queue


def test_enqueue_and_read_queue(tmp_vault: Path):
    bootstrap_vault(tmp_vault)
    enqueue_for_analysis(tmp_vault, "Deep Work", "Cal Newport")
    enqueue_for_analysis(tmp_vault, "Atomic Habits", "James Clear")
    queue = read_queue(tmp_vault)
    assert queue == [
        {"title": "Deep Work", "author": "Cal Newport"},
        {"title": "Atomic Habits", "author": "James Clear"},
    ]


def test_enqueue_is_deduplicated(tmp_vault: Path):
    bootstrap_vault(tmp_vault)
    enqueue_for_analysis(tmp_vault, "Deep Work", "Cal Newport")
    enqueue_for_analysis(tmp_vault, "Deep Work", "Cal Newport")
    queue = read_queue(tmp_vault)
    assert len(queue) == 1
```

- [ ] **Step 2: Run, verify fail**

```bash
pytest tests/test_vault.py -k queue -v
```

Expected: FAIL.

- [ ] **Step 3: Implement**

Append to `book_summarizer/vault.py`:
```python
def read_queue(vault_path: Path) -> list[dict]:
    q_file = Path(vault_path) / "analysis_queue.md"
    if not q_file.exists():
        return []
    out = []
    for line in q_file.read_text().splitlines():
        if line.startswith("- "):
            entry = line[2:].strip()
            # Format: "Title - Author"
            if " - " in entry:
                title, author = entry.split(" - ", 1)
                out.append({"title": title.strip(), "author": author.strip()})
    return out


def enqueue_for_analysis(vault_path: Path, title: str, author: str) -> None:
    existing = read_queue(vault_path)
    for row in existing:
        if row["title"] == title and row["author"] == author:
            return  # already queued
    q_file = Path(vault_path) / "analysis_queue.md"
    if not q_file.exists():
        q_file.write_text(ANALYSIS_QUEUE_HEADER)
    with q_file.open("a") as fh:
        fh.write(f"- {title} - {author}\n")
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/test_vault.py -k queue -v
```

Expected: PASS (2 tests).

- [ ] **Step 5: Run full vault suite**

```bash
pytest tests/test_vault.py -v
```

Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add book_summarizer/vault.py tests/test_vault.py
git commit -m "feat: analysis_queue.md enqueue with dedup"
```

---

## Phase E: Ingest orchestration

### Task 18: Single-file ingest

**Files:**
- Create: `/home/administrator/dev/book-summarizer/book_summarizer/ingest.py`
- Create: `/home/administrator/dev/book-summarizer/tests/test_ingest.py`

- [ ] **Step 1: Write failing end-to-end test**

```python
# tests/test_ingest.py
from pathlib import Path

from book_summarizer.ingest import ingest_file
from book_summarizer.vault import bootstrap_vault, is_ingested


def test_ingest_file_populates_vault(normal_epub: Path, tmp_vault: Path):
    bootstrap_vault(tmp_vault)
    result = ingest_file(normal_epub, tmp_vault)

    # Returns summary
    assert result["title"] == "The Test Book"
    assert result["author"] == "Test Author"
    assert result["status"] == "queued"

    # Raw file exists
    raw = tmp_vault / "raw" / "books" / "The Test Book - Test Author.md"
    assert raw.exists()

    # Collected and queue updated
    assert is_ingested(tmp_vault, "The Test Book", "Test Author")
    from book_summarizer.vault import read_queue
    assert read_queue(tmp_vault) == [{"title": "The Test Book", "author": "Test Author"}]


def test_ingest_file_skips_already_ingested(normal_epub: Path, tmp_vault: Path):
    bootstrap_vault(tmp_vault)
    ingest_file(normal_epub, tmp_vault)
    result = ingest_file(normal_epub, tmp_vault)
    assert result["status"] == "skipped"
    from book_summarizer.vault import read_queue
    assert len(read_queue(tmp_vault)) == 1


def test_ingest_pdf_origin_flags_low_quality(pdf_origin_epub: Path, tmp_vault: Path):
    bootstrap_vault(tmp_vault)
    result = ingest_file(pdf_origin_epub, tmp_vault)
    assert result["conversion_quality"] == "low"
    # Still queued for analysis (fallback path will handle it in Tier 2)
    assert result["status"] == "queued"
```

- [ ] **Step 2: Run, verify fail**

```bash
pytest tests/test_ingest.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement**

`book_summarizer/ingest.py`:
```python
"""Ingest orchestration: convert → write raw → update collected.md + queue."""
from __future__ import annotations

from pathlib import Path

from book_summarizer.convert import convert
from book_summarizer.metadata import extract_metadata
from book_summarizer.vault import (
    CollectedRow,
    append_collected_row,
    bootstrap_vault,
    enqueue_for_analysis,
    is_ingested,
    raw_book_path,
    write_raw_book,
)


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
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/test_ingest.py -v
```

Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add book_summarizer/ingest.py tests/test_ingest.py
git commit -m "feat: single-file ingest with idempotency"
```

---

### Task 19: Batch ingest with --dir

**Files:**
- Modify: `/home/administrator/dev/book-summarizer/book_summarizer/ingest.py`
- Modify: `/home/administrator/dev/book-summarizer/tests/test_ingest.py`

- [ ] **Step 1: Append failing test**

```python
# tests/test_ingest.py (append)
from book_summarizer.ingest import ingest_directory


def test_ingest_directory_processes_all_epubs(tmp_path: Path, tmp_vault: Path):
    from tests.conftest import _build_epub
    # Build two EPUBs in nested subdirs (mirroring book-downloader layout)
    a_dir = tmp_path / "Book A - Alice/"
    b_dir = tmp_path / "Book B - Bob/"
    a_dir.mkdir()
    b_dir.mkdir()
    _build_epub(a_dir / "a.epub", "Book A", "Alice", "2020", sections=[
        ("Cover", "x"), ("Chapter 1", "a "*40), ("Chapter 2", "b "*40), ("Chapter 3", "c "*40)
    ])
    _build_epub(b_dir / "b.epub", "Book B", "Bob", "2021", sections=[
        ("Cover", "x"), ("Chapter 1", "a "*40), ("Chapter 2", "b "*40), ("Chapter 3", "c "*40)
    ])

    bootstrap_vault(tmp_vault)
    results = ingest_directory(tmp_path, tmp_vault)
    assert len(results) == 2
    statuses = [r["status"] for r in results]
    assert statuses == ["queued", "queued"]

    # Second call is idempotent
    results2 = ingest_directory(tmp_path, tmp_vault)
    statuses2 = [r["status"] for r in results2]
    assert statuses2 == ["skipped", "skipped"]
```

- [ ] **Step 2: Run, verify fail**

```bash
pytest tests/test_ingest.py -k directory -v
```

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement**

Append to `book_summarizer/ingest.py`:
```python
SUPPORTED_EXTS = {".epub", ".pdf", ".md", ".markdown"}


def ingest_directory(directory: Path, vault_path: Path) -> list[dict]:
    """Recursively find all supported files in directory and ingest each.

    Skips already-ingested books (by Title + Author match against collected.md).
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise NotADirectoryError(str(directory))

    results = []
    # Sort for stable order
    candidates = sorted(
        p for p in directory.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    )
    for path in candidates:
        results.append(ingest_file(path, vault_path))
    return results
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/test_ingest.py -v
```

Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add book_summarizer/ingest.py tests/test_ingest.py
git commit -m "feat: batch directory ingest with idempotent skip"
```

---

## Phase F: CLI subcommands

### Task 20: Wire CLI ingest command

**Files:**
- Modify: `/home/administrator/dev/book-summarizer/book_summarizer/cli.py`
- Create: `/home/administrator/dev/book-summarizer/tests/test_cli_ingest.py`

- [ ] **Step 1: Write failing CLI integration test**

```python
# tests/test_cli_ingest.py
import subprocess
import sys
from pathlib import Path


def test_cli_ingest_end_to_end(normal_epub: Path, tmp_vault: Path, tmp_path: Path):
    # Prepare a books.yaml pointing at tmp_vault
    cfg = tmp_path / "books.yaml"
    cfg.write_text(
        f"defaults:\n  vault_path: {tmp_vault}\n"
        "  default_lens: general\n"
        "lenses:\n  general: test\n"
    )

    result = subprocess.run(
        [sys.executable, "-m", "book_summarizer", "--config", str(cfg),
         "ingest", str(normal_epub)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "The Test Book" in result.stdout
    assert (tmp_vault / "raw" / "books" / "The Test Book - Test Author.md").exists()
```

- [ ] **Step 2: Run, verify fail**

```bash
pytest tests/test_cli_ingest.py -v
```

Expected: FAIL (CLI prints "ingest: not implemented yet").

- [ ] **Step 3: Rewrite cli.py**

```python
"""Book Summarizer CLI — dispatch to subcommands."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from book_summarizer.config import load_config
from book_summarizer.ingest import ingest_directory, ingest_file


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
    from book_summarizer.vault import _read_collected_rows
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
    from book_summarizer.vault import _read_collected_rows, enqueue_for_analysis, COLLECTED_HEADER
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
        prog="book-summarizer",
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
```

- [ ] **Step 4: Run CLI ingest test, verify pass**

```bash
pytest tests/test_cli_ingest.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add book_summarizer/cli.py tests/test_cli_ingest.py
git commit -m "feat: wire CLI ingest, status, reset subcommands"
```

---

### Task 21: CLI status command test

**Files:**
- Modify: `/home/administrator/dev/book-summarizer/tests/test_cli_ingest.py`

- [ ] **Step 1: Append test for status subcommand**

```python
# tests/test_cli_ingest.py (append)

def test_cli_status_prints_ingested_books(normal_epub: Path, tmp_vault: Path, tmp_path: Path):
    cfg = tmp_path / "books.yaml"
    cfg.write_text(
        f"defaults:\n  vault_path: {tmp_vault}\n  default_lens: general\n"
        "lenses:\n  general: test\n"
    )
    # Ingest first
    subprocess.run(
        [sys.executable, "-m", "book_summarizer", "--config", str(cfg),
         "ingest", str(normal_epub)],
        check=True, capture_output=True,
    )
    # Now status
    result = subprocess.run(
        [sys.executable, "-m", "book_summarizer", "--config", str(cfg), "status"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "The Test Book" in result.stdout
    assert "queued" in result.stdout
```

- [ ] **Step 2: Run, verify pass**

```bash
pytest tests/test_cli_ingest.py::test_cli_status_prints_ingested_books -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_cli_ingest.py
git commit -m "test: CLI status subcommand integration"
```

---

### Task 22: CLI reset command test

**Files:**
- Modify: `/home/administrator/dev/book-summarizer/tests/test_cli_ingest.py`

- [ ] **Step 1: Append failing test**

```python
# tests/test_cli_ingest.py (append)

def test_cli_reset_requeues_analyzed_book(normal_epub: Path, tmp_vault: Path, tmp_path: Path):
    cfg = tmp_path / "books.yaml"
    cfg.write_text(
        f"defaults:\n  vault_path: {tmp_vault}\n  default_lens: general\n"
        "lenses:\n  general: test\n"
    )
    subprocess.run(
        [sys.executable, "-m", "book_summarizer", "--config", str(cfg),
         "ingest", str(normal_epub)],
        check=True, capture_output=True,
    )
    # Simulate "analyzed" state by rewriting collected.md manually
    collected = tmp_vault / "collected.md"
    text = collected.read_text().replace("| queued ", "| analyzed ")
    collected.write_text(text)

    result = subprocess.run(
        [sys.executable, "-m", "book_summarizer", "--config", str(cfg),
         "reset", "The Test Book - Test Author"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "re-queued" in result.stdout

    # collected.md flipped back to queued
    assert "queued" in collected.read_text()
    # analysis_queue.md contains the book again
    q = (tmp_vault / "analysis_queue.md").read_text()
    assert "The Test Book - Test Author" in q
```

- [ ] **Step 2: Run, verify pass**

```bash
pytest tests/test_cli_ingest.py::test_cli_reset_requeues_analyzed_book -v
```

Expected: PASS.

- [ ] **Step 3: Run full test suite**

```bash
pytest -v
```

Expected: PASS (all).

- [ ] **Step 4: Commit**

```bash
git add tests/test_cli_ingest.py
git commit -m "test: CLI reset subcommand integration"
```

---

## Phase G: Docs + Tier 1 smoke test

### Task 23: Static docs

**Files:**
- Create: `/home/administrator/dev/book-summarizer/docs/analysis-template.md`
- Create: `/home/administrator/dev/book-summarizer/docs/wiki-schema-template.md`
- Create: `/home/administrator/dev/book-summarizer/docs/lens-examples.md`

- [ ] **Step 1: Write analysis-template.md** (reference copy of what Tier 2 should emit)

```markdown
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
```

- [ ] **Step 2: Skip `wiki-schema-template.md`**

The canonical SCHEMA.md content lives in `book_summarizer/vault.py::SCHEMA_TEMPLATE` (written in Task 14) and gets rendered into every new vault on bootstrap. A duplicate docs file would only create drift. If a future maintainer needs to edit the schema, they edit `vault.py` — Python string, single source of truth.

No file to create in this step.

- [ ] **Step 3: Write lens-examples.md**

Copy the full `lenses:` section from `books.yaml.example` into a human-readable docs page.

```markdown
# Lens Library

Lenses are free-text fragments prepended to the synthesis prompt. They
shape what the Critical Pass focuses on for different kinds of books.

## general

Standard non-fiction analytical lens. Extract the central thesis, the top
5–10 novel claims, and apply the Critical Pass. Prefer claims that are
falsifiable; flag those that aren't.

## self_help

Self-help and productivity books. The central risk is confident prose
wrapping thin evidence. For every claim, ask: is this supported by cited
studies, or by anecdote and authority? Weak claims and facts-to-verify are
the most important sections here.

## business

Business and strategy books. Claims often rest on survivorship bias
("study 10 successful companies, extract common traits"). In the Critical
Pass, explicitly flag reasoning that could apply equally to failed companies.

## philosophy

Philosophy and ideas books. Steelman each argument charitably. Weak-claims
is less about empirical support and more about internal consistency — does
the conclusion follow from the premises?

## memoir

Memoir and biography. Weak-claims and facts-to-verify largely N/A. Focus on
TL;DR, Key Insights (what the subject learned, not claims about the world),
and Chapter by Chapter. Critical Pass reduced to steelman only.

## fiction

Fiction. Critical Pass is N/A — no empirical claims to verify. Focus on
plot, themes, Key Insights (character arcs, thematic claims the author
makes implicitly), and Chapter by Chapter.

## Writing new lenses

Edit `books.yaml` → `lenses:` to add one. A good lens names:
1. The dominant frame for insights (e.g. "mechanism-level causal claims").
2. What's signal vs noise (e.g. "author's self-deprecating asides are signal").
3. Per-genre extraction rules (e.g. "every claim about 'the research' must be
   verified — most self-help citations are either misrepresented or fake").
```

- [ ] **Step 4: Commit**

```bash
git add docs/
git commit -m "docs: analysis template, schema template, lens library"
```

---

### Task 24: Tier 1 smoke test against Deep Work

**Files:**
- Create: `/home/administrator/dev/book-summarizer/tests/test_smoke_real_books.py`

- [ ] **Step 1: Write optional smoke test that skips if Deep Work isn't present**

```python
# tests/test_smoke_real_books.py
"""Optional smoke tests against real EPUBs from ~/dev/book-downloader/downloads/.

These tests validate end-to-end behavior against actual books. They skip if
the books are not present locally (e.g. CI).
"""
from pathlib import Path

import pytest

from book_summarizer.ingest import ingest_file
from book_summarizer.vault import bootstrap_vault, _read_collected_rows

DEEP_WORK = Path(
    "/home/administrator/dev/book-downloader/downloads/Deep Work - Cal Newport/"
    "Deep Work - Cal Newport - 8e4567c95342c815b075cf9376542d33.epub"
)
ATOMIC_HABITS_DIR = Path(
    "/home/administrator/dev/book-downloader/downloads/Atomic Habits - James Clear/"
)


@pytest.mark.skipif(not DEEP_WORK.exists(), reason="Deep Work EPUB not available locally")
def test_deep_work_ingest_produces_chapter_structure(tmp_vault: Path):
    bootstrap_vault(tmp_vault)
    result = ingest_file(DEEP_WORK, tmp_vault)
    assert result["status"] == "queued"
    assert result["title"] == "Deep Work"
    assert result["conversion_quality"] == "high"
    assert result["chapters"] >= 10  # Deep Work has ~15 chapter-classed sections

    raw = tmp_vault / "raw" / "books" / "Deep Work - Cal Newport.md"
    assert raw.exists()
    text = raw.read_text()
    # At least 10 explicit chapter headings
    chapter_headings = [l for l in text.splitlines() if l.startswith("# Chapter ")]
    assert len(chapter_headings) >= 10


@pytest.mark.skipif(not ATOMIC_HABITS_DIR.exists(), reason="Atomic Habits not available locally")
def test_atomic_habits_flags_pdf_origin(tmp_vault: Path):
    epubs = list(ATOMIC_HABITS_DIR.glob("*.epub"))
    assert epubs, f"no EPUB in {ATOMIC_HABITS_DIR}"
    bootstrap_vault(tmp_vault)
    result = ingest_file(epubs[0], tmp_vault)
    assert result["conversion_quality"] == "low"
    rows = _read_collected_rows(tmp_vault)
    assert any(r["conversion_quality"] == "low" for r in rows)
```

- [ ] **Step 2: Run against real books, verify pass**

```bash
pytest tests/test_smoke_real_books.py -v
```

Expected: PASS (2 tests) on machines where the books exist; SKIP otherwise.

- [ ] **Step 3: Commit**

```bash
git add tests/test_smoke_real_books.py
git commit -m "test: smoke tests against real Deep Work and Atomic Habits EPUBs"
```

---

### Task 25: Manual Tier 1 verification

- [ ] **Step 1: Install the package**

```bash
cd /home/administrator/dev/book-summarizer
pip install -e ".[dev]"
```

- [ ] **Step 2: Copy the example config**

```bash
cp books.yaml.example books.yaml
```

- [ ] **Step 3: Ingest a real book**

```bash
python -m book_summarizer ingest \
  "/home/administrator/dev/book-downloader/downloads/Deep Work - Cal Newport/Deep Work - Cal Newport - 8e4567c95342c815b075cf9376542d33.epub"
```

Expected output:
```
✓ [queued ] Deep Work — Cal Newport (chapters=15, quality=high)
```

- [ ] **Step 4: Inspect the vault**

```bash
ls -la ~/obsidian/"book summaries"/
head -50 ~/obsidian/"book summaries"/raw/books/"Deep Work - Cal Newport.md"
cat ~/obsidian/"book summaries"/collected.md
cat ~/obsidian/"book summaries"/analysis_queue.md
```

Expected:
- Vault directory structure exists.
- Raw file has `# Chapter 1 — ...` through `# Chapter N — ...` headings.
- collected.md has one row for Deep Work.
- analysis_queue.md has `- Deep Work - Cal Newport`.

- [ ] **Step 5: Ingest Atomic Habits to confirm PDF-origin path**

```bash
python -m book_summarizer ingest \
  "/home/administrator/dev/book-downloader/downloads/Atomic Habits - James Clear/Atomic Habits - James Clear.epub"
```

Expected: `✓ [queued ] Atomic Habits — James Clear (chapters=0, quality=low)`.

- [ ] **Step 6: Check status**

```bash
python -m book_summarizer status
```

Expected: tabular list showing both books with their differing quality flags.

- [ ] **Step 7: Run reset, verify**

```bash
python -m book_summarizer reset "Deep Work - Cal Newport"
# re-queued: Deep Work — Cal Newport
python -m book_summarizer status
# Status column should still read "queued" (was never analyzed); reset is a no-op but should not error
```

---

## 🛑 Checkpoint 1 — Tier 1 ships

At this point, stop and verify:

1. `python -m book_summarizer ingest <book>` works end-to-end.
2. `status` and `reset` work.
3. Raw book markdown in the vault has chapter headings.
4. `collected.md` and `analysis_queue.md` are populated.
5. PDF-origin EPUBs are flagged `low` quality.

**If any of the above fails, fix before proceeding to Tier 2.**

---

## Phase H: Tier 2 slash command

### Task 26: Write the /summarize-book slash command

**Files:**
- Create: `/home/administrator/dev/book-summarizer/commands/summarize-book.md`

- [ ] **Step 1: Write the slash command file**

`/home/administrator/dev/book-summarizer/commands/summarize-book.md`:
```markdown
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

1. Read the raw markdown from `{vault_path}/raw/books/<Title> - <Author>.md`.

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
raw_path: raw/books/{Title} - {Author}.md
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
```

- [ ] **Step 2: Symlink into Claude Code's commands directory**

```bash
mkdir -p ~/.claude/commands
ln -sf /home/administrator/dev/book-summarizer/commands/summarize-book.md ~/.claude/commands/summarize-book.md
```

- [ ] **Step 3: Commit**

```bash
cd /home/administrator/dev/book-summarizer
git add commands/
git commit -m "feat: /summarize-book slash command for Tier 2 analysis"
```

---

## Phase I: Tier 2 smoke test

### Task 27: Manual end-to-end verification

- [ ] **Step 1: Ensure Tier 1 has ingested at least two books**

```bash
python -m book_summarizer status
```

Expected: at least two queued books.

- [ ] **Step 2: In Claude Code, run `/summarize-book` on the first book**

```
/summarize-book
```

Expected:
- Prompts for lens choice.
- Dispatches parallel chapter subagents.
- Writes `~/obsidian/book summaries/books/<Title> - <Author>.md`.
- Creates entity/concept pages per threshold rules.
- Updates `collected.md`, `analysis_queue.md`, `log.md`, `index.md`.
- Prints the Phase 7 summary block.

- [ ] **Step 3: Open the vault in Obsidian, verify graph**

Expected: The analyzed book, its entities, and its concepts show up as linked nodes.

- [ ] **Step 4: Run `/summarize-book` on the second book**

Expected:
- Any entities/concepts shared with the first book get their pages updated (citations from both books) rather than duplicated.
- If any claim in book 2 contradicts book 1, a page appears in `comparisons/`.

- [ ] **Step 5: Run `/summarize-book` on the PDF-origin Atomic Habits**

Expected:
- Single-pass mode fires automatically (low conversion quality).
- Summary page includes the `> Summarized in single-pass mode — chapter detection failed or chapters were absent.` notice in place of `## Chapter by Chapter`.
- `summary_mode: single-pass` in frontmatter.

---

## 🛑 Checkpoint 2 — v1 ships

At this point:

1. Tier 1 CLI ingests EPUBs reliably; PDFs and raw markdown work as best-effort.
2. Tier 2 slash command runs end-to-end with lens prompting, parallel chapter summarization, synthesis, and wiki updates.
3. The vault compounds entities and concepts across books, auto-creates comparison pages for contradictions, and logs all actions.
4. PDF-origin EPUBs are handled gracefully via the single-pass fallback.

v1 done. Use it. Iterate on lenses and the slash-command prompt based on real summary output.

---

## Test suite summary

Run the full suite:

```bash
cd /home/administrator/dev/book-summarizer
pytest -v
```

Expected: all tests pass (smoke tests against real books SKIP if those files aren't local).

---

## Non-goals reminder (from spec, for future reference)

- No magazines, articles, URL fetching, LibraryThing integration, cron wrappers, web UI, marker-based PDF conversion, or meta-vault unification. Those are deferred or explicitly out of scope.
