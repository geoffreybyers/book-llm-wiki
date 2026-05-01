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
    """Run `epub2md -c [--merge]` on epub_path, copying results to out_dir.

    epub2md creates output relative to the EPUB's directory, not the cwd.
    This function wraps that behavior: we run epub2md on the original EPUB,
    then copy the results to out_dir and return the path there.

    In merge mode, we use the merged.md filename by convention.
    """
    if shutil.which("epub2md") is None:
        raise RuntimeError("epub2md is not installed. Run: npm install -g epub2md")

    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["epub2md", "-c"]
    if merge:
        cmd.append("-m=merged.md")
    cmd.append(str(epub_path))

    # epub2md writes output in a subdirectory next to the epub_path, named after the epub stem.
    # Run from the epub's parent directory to ensure the subdirectory lands in the right place.
    subprocess.run(cmd, check=True, cwd=str(epub_path.parent), capture_output=True)

    # epub2md creates a subdirectory named after the EPUB (without extension)
    epub_stem = epub_path.stem
    produced_at_source = epub_path.parent / epub_stem
    if not produced_at_source.exists():
        raise RuntimeError(
            f"epub2md did not produce expected output at {produced_at_source}. "
            f"Contents of {epub_path.parent}: {list(epub_path.parent.iterdir())}"
        )

    # Copy the produced directory to out_dir, then clean up the source-side
    # artifact so we don't pollute the source downloads folder.
    final_dest = out_dir / epub_stem
    if final_dest.exists():
        shutil.rmtree(final_dest)
    shutil.copytree(produced_at_source, final_dest)
    shutil.rmtree(produced_at_source)

    return final_dest


from enum import Enum


class SectionClass(str, Enum):
    FRONT = "front"
    PREAMBLE = "preamble"  # Introduction/Preface/Foreword/Prologue: summarize, but don't number as Chapter N
    PART = "part"          # "Part 1", "Part One": never consume a chapter number; body kept iff substantive
    CHAPTER = "chapter"
    BACK = "back"


# Patterns to identify non-chapter matter by section name.
# Each pattern is a lowercase substring or regex that decides the class.
_FRONT_PATTERNS = [
    re.compile(r"^cover$"),
    re.compile(r"^cover page$"),
    re.compile(r"^title page$"),
    re.compile(r"^half title$"),
    re.compile(r"^dedication$"),
    re.compile(r"^epigraph$"),
    re.compile(r"^praise for\b"),
    re.compile(r"^praise$"),
    re.compile(r"^also by\b"),  # "also by X" at the start is front matter when it precedes chapters;
    # but our heuristic treats 'also by' as back matter (see below). Handle via BACK list.
    re.compile(r"^acknowledg[e]?ments?$"),  # can appear front OR back; when front, rare. default front.
    re.compile(r"^(start|begin)\s+reading$"),  # Kindle/Apple Books navigation landmark
]


# PREAMBLE: chapters of the book that come before "Chapter 1" but are still
# substantive content worth summarizing. They get a `# Preamble — <name>`
# heading so the chapter detector keeps them in scope but doesn't number
# them as Chapter N (preventing the off-by-N shift that pushed every actual
# chapter number forward in books like Atomic Habits, Hooked, Zero to One,
# Deep Work, Gap Selling, Building a Second Brain, and Design of Everyday
# Things).
_PREAMBLE_PATTERNS = [
    re.compile(r"^foreword\b", re.IGNORECASE),
    re.compile(r"^preface\b", re.IGNORECASE),       # matches "Preface", "Preface to the X Edition", "Preface: ..."
    re.compile(r"^prologue\b", re.IGNORECASE),
    re.compile(r"^introduction\b", re.IGNORECASE),  # matches "Introduction", "Introduction: My Story"
    re.compile(r"^welcome\b", re.IGNORECASE),
    re.compile(r"^(an? )?important note\b", re.IGNORECASE),  # "An Important Note from Nir"
    re.compile(r"^author[’']?s note\b", re.IGNORECASE),  # straight or curly apostrophe
    re.compile(r"^note from\b", re.IGNORECASE),
    re.compile(r"^about the authors?$", re.IGNORECASE),  # when it appears at front, before any chapter
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
    re.compile(r"^copyright page$"),
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


# PART: structural divider grouping a run of chapters. Never numbered as a
# chapter; body emitted only when substantive (Awaken the Giant Within and
# Blue Ocean Strategy use Parts as 8-12 word title pages; Clear Thinking
# packs each Part with a 200-800 word epigraph + setup before its chapters).
_PART_PATTERNS = [
    re.compile(r"^part\s+(\w+)\b", re.IGNORECASE),  # "Part 1", "Part 1:", "Part 1.", "Part One", "Part II"
]


_CHAPTER_PATTERNS = [
    re.compile(r"^(chapter|chap\.?)\s+\d+\b", re.IGNORECASE),
    re.compile(r"^\d+\s+\S", re.IGNORECASE),  # "1 The Surprising..."
    re.compile(r"^conclusion(:|$|\s)", re.IGNORECASE),
    re.compile(r"^epilogue(:|$|\s)", re.IGNORECASE),
    re.compile(r"^rule\s+#?\d+", re.IGNORECASE),     # Rule #1, Rule 2
    re.compile(r"^the\s+\w+\s+law\b", re.IGNORECASE),
]


# How many words of body content separate a substantive Part intro (kept and
# summarized) from a divider-only Part page (dropped from the output). 8-12
# words covers "PART ONE / Unleash Your Power" style title pages; real intros
# in the wild start at ~150 words. 50 leaves comfortable margin on both sides.
_PART_BODY_MIN_WORDS = 50


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

    # Preamble: substantive non-chapter content that comes before Chapter 1
    # (Introduction, Preface, Foreword, Prologue, Welcome, author's notes).
    # Distinct from FRONT (cover/title/dedication/etc) because we want to
    # summarize this content, but distinct from CHAPTER because it shouldn't
    # consume a chapter number.
    for pat in _PREAMBLE_PATTERNS:
        if pat.match(n):
            return SectionClass.PREAMBLE

    # Part: structural divider ("Part 1", "Part One"). Never consumes a
    # chapter number; the convert loop decides whether to emit the body
    # based on word count.
    for pat in _PART_PATTERNS:
        if pat.match(n):
            return SectionClass.PART

    for pat in _CHAPTER_PATTERNS:
        if pat.search(n):
            return SectionClass.CHAPTER

    # Unknown label → default to chapter (better to include uncertain sections
    # than filter them out; synthesis will weight accordingly).
    return SectionClass.CHAPTER


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

        # Compare spine vs distinct files referenced by NCX. Counting raw
        # NCX entries (toc_count) catches rich retail navigation as a false
        # positive — many publishers fragment-anchor sub-section entries
        # into the same chapter files, producing NCX:spine ratios of 3-5
        # without being PDF-derived. The real PDF symptom is NCX entries
        # pointing to many *distinct* files outside the spine — i.e., the
        # PDF→EPUB tool dumped each navigation target into its own micro
        # file. So compare distinct file-targets in NCX (after stripping
        # `#fragment`) to the spine size.
        opf_path = _find_opf_path(zf)
        opf = ET.fromstring(_read_zip_text(zf, opf_path))
        spine = opf.find("opf:spine", OPF_NS)
        spine_count = len(spine.findall("opf:itemref", OPF_NS)) if spine is not None else 0

    nav_files = {s.get("src", "").split("#", 1)[0] for s in epub_structure(epub_path)}
    nav_files.discard("")
    if spine_count > 0 and len(nav_files) >= spine_count * 3:
        return True
    return False


def is_kobo_span_epub(epub_path: Path) -> bool:
    """True if the EPUB wraps body text in inline ``<span class="koboSpan">`` elements.

    Kobo-flavored XHTML (common in Simon & Schuster trade nonfiction
    distributions, e.g. Tiago Forte's *The PARA Method*, 2023) wraps every
    text token in inline spans like
    ``<span class="koboSpan" id="kobo.X.Y">…</span>``, with a stylesheet
    block carrying ``id="koboSpanStyle"`` injected into each chapter's
    ``<head>``. epub2md cannot extract content from these spans — both
    section-mode and merge-mode silently produce near-empty markdown
    (just the chapter heading repeated). Detection routes the EPUB through
    ``convert_pages_epub_to_markdown``, whose direct-XHTML-extraction path
    strips arbitrary inline tags including koboSpan.

    The detector samples up to 10 spine XHTML files looking for the literal
    ``koboSpan`` token. A single hit is high-confidence: ``koboSpan`` is a
    Kobo-reader extension class, not a standard XHTML class, and is not
    expected to appear in non-Kobo EPUBs.
    """
    with zipfile.ZipFile(epub_path) as zf:
        sampled = 0
        for name in zf.namelist():
            if not name.lower().endswith((".xhtml", ".html")):
                continue
            try:
                body = _read_zip_text(zf, name)
            except (UnicodeDecodeError, KeyError):
                continue
            if "koboSpan" in body:
                return True
            sampled += 1
            if sampled >= 10:
                break
    return False


def is_pages_origin(epub_path: Path) -> bool:
    """True if EPUB was generated by Apple Pages.

    Pages produces a non-standard XHTML structure with content nested in
    inline `<span>` elements that epub2md cannot extract — running it
    against a Pages EPUB silently produces near-empty markdown (just the
    chapter headings). Detected by:
      - <meta name="generator" content="Pages Publishing macOS..."/> in OPF
      - presence of META-INF/com.apple.ibooks.display-options.xml
        (Apple's iBooks-specific marker, near-universal in Pages exports)
    """
    info = epub_info(epub_path)
    gen = (info.get("generator") or "").lower()
    if "pages publishing" in gen or gen.startswith("pages "):
        return True
    with zipfile.ZipFile(epub_path) as zf:
        if "META-INF/com.apple.ibooks.display-options.xml" in zf.namelist():
            # Pair this signal with the iBooks-display-options file only if
            # the OPF generator is also non-standard. This keeps non-Pages
            # iBooks EPUBs (which can also include the display-options file
            # for distribution) out of the Pages branch.
            if not gen or gen.startswith("pages") or "macos" in gen:
                return True
    return False


def _extract_xhtml_text(xhtml: str) -> str:
    """Extract text from XHTML preserving heading and paragraph boundaries.

    Used by the Pages-EPUB fallback converter when epub2md can't extract
    inline-span-heavy content. Not a full HTML parser — just regex-based
    tag stripping with structural newlines preserved at heading and
    paragraph boundaries.
    """
    # Headings → markdown headings (deepest first to avoid consuming nested)
    xhtml = re.sub(r"<h6[^>]*>(.*?)</h6>", r"\n\n###### \1\n\n", xhtml, flags=re.DOTALL)
    xhtml = re.sub(r"<h5[^>]*>(.*?)</h5>", r"\n\n##### \1\n\n", xhtml, flags=re.DOTALL)
    xhtml = re.sub(r"<h4[^>]*>(.*?)</h4>", r"\n\n#### \1\n\n", xhtml, flags=re.DOTALL)
    xhtml = re.sub(r"<h3[^>]*>(.*?)</h3>", r"\n\n### \1\n\n", xhtml, flags=re.DOTALL)
    xhtml = re.sub(r"<h2[^>]*>(.*?)</h2>", r"\n\n## \1\n\n", xhtml, flags=re.DOTALL)
    xhtml = re.sub(r"<h1[^>]*>(.*?)</h1>", r"\n\n# \1\n\n", xhtml, flags=re.DOTALL)
    # Paragraph and line-break boundaries
    xhtml = re.sub(r"<p[^>]*>", "\n\n", xhtml)
    xhtml = re.sub(r"</p>", "", xhtml)
    xhtml = re.sub(r"<br\s*/?>", "\n", xhtml)
    # Drop image tags entirely
    xhtml = re.sub(r"<img[^>]*/>", "", xhtml)
    xhtml = re.sub(r"<img[^>]*></img>", "", xhtml)
    xhtml = re.sub(r"<img[^>]*>", "", xhtml)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", "", xhtml)
    # Decode HTML entities
    import html as html_module
    text = html_module.unescape(text)
    # Normalize whitespace, preserve paragraph breaks
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@dataclass
class ConversionResult:
    chapter_count: int
    conversion_quality: str  # 'high' or 'low'
    mode: str  # 'structured' or 'flat'


def _xhtml_manifest_hrefs(epub_path: Path) -> list[str]:
    """Return xhtml manifest hrefs in document (manifest) order.

    epub2md emits one section .md file per xhtml manifest item, numbered by
    its position in the manifest — NOT the spine. (Verified empirically: a
    Penguin EPUB had `Praise01` at manifest position 4 but spine position 25,
    and epub2md numbered the Praise file `04-`.) Spine-order alignment fails
    on any EPUB where the publisher reorders sections in the spine.
    """
    with zipfile.ZipFile(epub_path) as zf:
        opf_path = _find_opf_path(zf)
        opf = ET.fromstring(_read_zip_text(zf, opf_path))
        manifest = opf.find("opf:manifest", OPF_NS)
        if manifest is None:
            return []
        return [
            it.attrib["href"]
            for it in manifest.findall("opf:item", OPF_NS)
            if it.attrib.get("media-type") == "application/xhtml+xml"
            and "href" in it.attrib
        ]


def _section_body_for_position(
    section_md_dir: Path, position: int, skip_offset: int = 0
) -> str:
    """Read epub2md's markdown for the given manifest position (1-indexed).

    epub2md numbers files with varying zero-padding (`007-`, `07-`, or `7-`);
    try each. ``skip_offset`` (default 0) shifts the lookup left when epub2md
    silently skips one or more leading manifest XHTML items — see
    ``_epub2md_skip_offset``. Manifest positions at or below the offset
    have no corresponding body file (the front-matter cover that epub2md
    dropped) and return empty string.
    """
    effective = position - skip_offset
    if effective < 1:
        return ""
    for pat in (f"{effective:03d}-*.md", f"{effective:02d}-*.md", f"{effective}-*.md"):
        candidates = sorted(section_md_dir.glob(pat))
        if candidates:
            return candidates[0].read_text()
    return ""


def _epub2md_skip_offset(section_md_dir: Path, manifest_hrefs: list[str]) -> int:
    """How many leading manifest XHTML items did epub2md silently skip?

    epub2md numbers its output files by its own internal counter, which
    matches the manifest XHTML position 1-for-1 — except when manifest[0]
    is a cover/titlepage XHTML, in which case epub2md silently treats it
    as the cover and emits no ``.md`` for it, shifting every subsequent
    file's number down by one.

    Without compensation, every NCX-derived ``# Chapter N`` wrapper ends up
    filled with the body of conceptual chapter N+1. Observed in the wild on:
      - Clear Thinking (Shane Parrish, Penguin/Portfolio 2023, PDF version):
        manifest[0] at OPF root, basename "titlepage".
      - Thinking, Fast and Slow (Daniel Kahneman): same pattern.
      - Blue Ocean Strategy (Harvard Business Review 2015): manifest[0] at
        ``Text/titlepage.html`` (subdir), basename still "titlepage".

    Detection: manifest count > emitted count AND manifest[0]'s basename
    matches the cover/titlepage family. We do NOT require the file to be
    at OPF root — Blue Ocean's titlepage is in a subdirectory and is still
    dropped. We do NOT cap the total diff — Blue Ocean drops BOTH a
    leading titlepage AND a trailing cover image (total diff 2) but only
    the leading drop shifts NCX-referenced body lookups; the trailing
    cover sits past the spine and is invisible.

    Returns 1 when the leading-skip is detected, 0 otherwise.
    """
    md_count = sum(1 for _ in section_md_dir.glob("*.md"))
    if md_count >= len(manifest_hrefs):
        return 0
    if not manifest_hrefs:
        return 0
    first_basename = Path(manifest_hrefs[0]).stem.lower()
    looks_like_cover = any(
        token in first_basename
        for token in ("titlepage", "title_page", "cover", "halftitle", "half_title")
    )
    if looks_like_cover:
        return 1
    return 0


def convert_pages_epub_to_markdown(epub_path: Path, out_path: Path) -> ConversionResult:
    """Convert an Apple-Pages-generated EPUB by extracting XHTML text directly.

    Pages EPUBs nest content in inline `<span>` elements that epub2md cannot
    extract — running the standard pipeline against them produces near-empty
    markdown (just the chapter headings). This handler reads the spine
    files directly out of the EPUB zip, runs `_extract_xhtml_text` on each,
    and assembles the same `# Chapter N — <Title>` / `# Front Matter` /
    `# Back Matter` structure the regular path produces. Image extraction
    is skipped — Pages EPUBs typically use illustrations not critical to
    the analysis content.
    """
    from urllib.parse import unquote

    out_path.parent.mkdir(parents=True, exist_ok=True)

    structure = epub_structure(epub_path)
    manifest_hrefs = _xhtml_manifest_hrefs(epub_path)
    pos_by_href = {href: i for i, href in enumerate(manifest_hrefs, start=1)}
    pos_by_basename = {Path(href).name: i for i, href in enumerate(manifest_hrefs, start=1)}

    def _resolve_position(src: str) -> int | None:
        bare = unquote(src.split("#", 1)[0])
        if bare in pos_by_href:
            return pos_by_href[bare]
        return pos_by_basename.get(Path(bare).name)

    # Dedupe NCX entries by spine position (same logic as the standard path).
    seen_positions: set[int] = set()
    deduped_structure: list[dict] = []
    for section in structure:
        position = _resolve_position(section.get("src", ""))
        if position is None or position in seen_positions:
            continue
        seen_positions.add(position)
        deduped_structure.append({**section, "_position": position})

    with zipfile.ZipFile(epub_path) as zf:
        opf_path = _find_opf_path(zf)
        opf_dir = str(Path(opf_path).parent) + "/" if "/" in opf_path else ""

        chapter_num = 0
        parts: list[str] = []

        if not deduped_structure:
            # No NCX → emit one chapter per spine file in manifest order.
            for href in manifest_hrefs:
                try:
                    xhtml = zf.read(f"{opf_dir}{href}").decode("utf-8", errors="replace")
                except KeyError:
                    continue
                body = _extract_xhtml_text(xhtml)
                if not body:
                    continue
                chapter_num += 1
                # Use the file basename (stripped of extension and underscores) as title
                stem = Path(href).stem.replace("_", " ").strip()
                parts.append(f"# Chapter {chapter_num} — {stem}\n\n{body}\n")
        else:
            for section in deduped_structure:
                name = section["name"]
                cls = classify_section(name)
                href = manifest_hrefs[section["_position"] - 1]
                try:
                    xhtml = zf.read(f"{opf_dir}{href}").decode("utf-8", errors="replace")
                except KeyError:
                    xhtml = ""
                body = _extract_xhtml_text(xhtml)
                if cls == SectionClass.PART:
                    if len(body.split()) < _PART_BODY_MIN_WORDS:
                        continue  # divider-only Part page; drop entirely
                    heading = f"# Part — {name}"
                elif cls == SectionClass.CHAPTER:
                    chapter_num += 1
                    heading = f"# Chapter {chapter_num} — {name}"
                elif cls == SectionClass.PREAMBLE:
                    heading = f"# Preamble — {name}"
                elif cls == SectionClass.FRONT:
                    heading = f"# Front Matter — {name}"
                else:
                    heading = f"# Back Matter — {name}"
                parts.append(f"{heading}\n\n{body}\n")

        out_path.write_text("\n".join(parts))

    return ConversionResult(
        chapter_count=chapter_num,
        conversion_quality="high",
        mode="structured",
    )


# Word-number lookup for chapter heading parsing in merge-mode fallback.
# Covers Western non-fiction's typical Chapter One … Chapter Twenty range.
_WORD_TO_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
}


_SECTION_MODE_EMPTY_CHAPTER_WORD_FLOOR = 25

# Thresholds for the NCX-points-to-stub detector. An XHTML file under
# 3 KB is almost always a navigation/copyright/title-page/short-summary
# stub; an XHTML file over 8 KB almost always contains substantive prose.
# The 5x bytes-ratio gate ensures we only fire when the unreferenced
# files clearly dominate the EPUB's body content.
_SECTION_MODE_STUB_FILE_BYTE_THRESHOLD = 3000
_SECTION_MODE_BODY_FILE_BYTE_THRESHOLD = 8000

# Publisher CSS classes that mark chapter / part / preamble / back-matter
# titles inside <p> tags. Wiley uses chaptertitle / parttitle / prefacetitle /
# mattertitle / forewordtitle / appendixtitle; other Adobe-InDesign-built
# trade EPUBs use the same family with minor variations. Order matters —
# the first matching class wins for section classification.
_PUBLISHER_TITLE_CLASSES = {
    "chaptertitle": "chapter",
    "chapternumber": "chapter",
    "parttitle": "part",
    "partnumber": "part",
    "prefacetitle": "preamble",
    "forewordtitle": "preamble",
    "introtitle": "preamble",
    "introductiontitle": "preamble",
    "mattertitle": "back",
    "appendixtitle": "back",
    "afterwordtitle": "back",
}

# Filename stems that map to a known section class even without a publisher
# title class. Wiley-style "foreword.html" / "AuthorsNote.html" /
# "FinalThoughts.html" lose their natural classification when stripped of
# their <p class="mattertitle"> markup, because mattertitle is reused for
# both prefatory and back matter in the Wiley template.
_KNOWN_FILENAME_SECTION_CLASS = {
    "foreword": ("preamble", "Foreword"),
    "preface": ("preamble", "Preface"),
    "introduction": ("preamble", "Introduction"),
    "authorsnote": ("preamble", "Author's Note"),
    "authornote": ("preamble", "Author's Note"),
    "prologue": ("preamble", "Prologue"),
    "finalthoughts": ("back", "Final Thoughts"),
    "epilogue": ("back", "Epilogue"),
    "afterword": ("back", "Afterword"),
    "abouttheauthor": ("filter", ""),
    "acknowledgments": ("filter", ""),
    "acknowledgements": ("filter", ""),
    "copyright": ("filter", ""),
    "dedication": ("filter", ""),
    "halftitle": ("filter", ""),
    "title": ("filter", ""),
    "cover": ("filter", ""),
    "contents": ("filter", ""),
    "toc": ("filter", ""),
    "index": ("filter", ""),
    "references": ("filter", ""),
    "bibliography": ("filter", ""),
    "glossary": ("filter", ""),
}


def _extract_publisher_class_title(xhtml: str) -> tuple[str, str] | None:
    """Find a publisher-class-tagged title in an XHTML body.

    Returns (section_class, title_text) where section_class is one of
    'chapter', 'part', 'preamble', 'back'. Returns None when no recognized
    title class is present.

    Strategy: scan ``<p class="...">...</p>`` paragraphs in document order
    for any class in ``_PUBLISHER_TITLE_CLASSES``. Many Wiley-style chapters
    have *two* class-tagged paragraphs — a label ("CHAPTER 1", "Module ONE")
    followed by the real title — so we prefer a non-label paragraph when
    one is available, falling back to the first match otherwise.
    """
    label_only = re.compile(
        r"^(?:CHAPTER|PART|MODULE|SECTION|BOOK|APPENDIX)\s+"
        r"(?:[IVXLCDM]+|\d+|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN|"
        r"ELEVEN|TWELVE|THIRTEEN|FOURTEEN|FIFTEEN|SIXTEEN|SEVENTEEN|EIGHTEEN|"
        r"NINETEEN|TWENTY)$",
        re.IGNORECASE,
    )

    matches: list[tuple[str, str]] = []
    for m in re.finditer(
        r'<p\s+[^>]*class="([^"]+)"[^>]*>(.*?)</p>',
        xhtml,
        re.DOTALL,
    ):
        classes = m.group(1).split()
        for cls in classes:
            section_cls = _PUBLISHER_TITLE_CLASSES.get(cls.lower())
            if section_cls is None:
                continue
            text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            text = re.sub(r"\s+", " ", text)
            import html as html_module
            text = html_module.unescape(text)
            if text:
                matches.append((section_cls, text))
            break  # one section-class per <p>

    if not matches:
        return None

    # Group consecutive same-section matches; prefer the first non-label
    # paragraph within each group, falling back to the first match.
    section_cls = matches[0][0]
    same_class = [m for m in matches if m[0] == section_cls]
    for cls, text in same_class:
        if not label_only.match(text):
            return (cls, text)
    return same_class[0]


_CHAPTER_SUBFILE_PATTERN = re.compile(
    r"^chapter[\s_-]*(\d+)([a-z])$", re.IGNORECASE
)


def _chapter_subfile_match(href: str) -> tuple[int, str] | None:
    """Detect a Wiley-style chapter sub-file (Chapter16a.html, Chapter01b.html).

    The Wiley template splits long chapters across multiple XHTML files —
    Chapter16.html holds the chapter intro, Chapter16a.html / 16b.html /
    16c.html hold subsequent sections. Returns ``(chapter_num, suffix)``
    when ``href``'s basename stem matches the pattern, else None.
    """
    stem = Path(href).stem
    m = _CHAPTER_SUBFILE_PATTERN.match(stem)
    if m is None:
        return None
    return (int(m.group(1)), m.group(2).lower())


def _filename_section_class(href: str) -> tuple[str, str] | None:
    """Classify a manifest XHTML by its filename stem.

    Returns ``(section_class, title)`` where section_class is one of
    'preamble' / 'back' / 'filter', or None when the stem is not in
    ``_KNOWN_FILENAME_SECTION_CLASS``. Used as a fallback when an XHTML
    file lacks publisher class markup (typical for short Wiley front-matter
    files).
    """
    stem = Path(href).stem.lower().replace(" ", "").replace("_", "").replace("-", "")
    return _KNOWN_FILENAME_SECTION_CLASS.get(stem)


def _spine_xhtml_hrefs(epub_path: Path) -> list[str]:
    """Return XHTML hrefs in spine (reading) order.

    Manifest declaration order is often alphabetic (Wiley, many other
    publishers); spine order is the actual reading sequence. The
    spine-body-extraction fallback walks files in spine order so the
    output reflects the reading order the publisher intends.
    """
    with zipfile.ZipFile(epub_path) as zf:
        opf_path = _find_opf_path(zf)
        opf = ET.fromstring(_read_zip_text(zf, opf_path))

        manifest_el = opf.find("opf:manifest", OPF_NS)
        spine_el = opf.find("opf:spine", OPF_NS)
        if manifest_el is None or spine_el is None:
            return []

        # id -> href, restricted to xhtml manifest items
        id_to_href: dict[str, str] = {}
        for item in manifest_el.findall("opf:item", OPF_NS):
            mt = item.get("media-type", "")
            if "xhtml" not in mt and "html" not in mt:
                continue
            id_to_href[item.get("id", "")] = item.get("href", "")

        ordered: list[str] = []
        for itemref in spine_el.findall("opf:itemref", OPF_NS):
            href = id_to_href.get(itemref.get("idref", ""))
            if href:
                ordered.append(href)
        return ordered


def _section_mode_ncx_is_degenerate(
    epub_path: Path,
    deduped_structure: list[dict],
    manifest_hrefs: list[str],
) -> bool:
    """Detect EPUBs whose NCX is degenerate (one or zero substantive navPoints)
    while the spine contains many substantive XHTML files.

    Failure pattern (real example: Michael Port's *Book Yourself Solid*,
    John Wiley & Sons 2010, Sigil-built): toc.ncx contains exactly one
    ``<navPoint>`` pointing at ``cover.xml`` while the manifest holds 38
    XHTML files — foreword, author's note, preface, four part-dividers,
    sixteen numbered chapters with sub-files, final thoughts. Section-mode
    extraction emits one chapter heading from cover.xml and silently drops
    the rest of the book.

    The ``_section_mode_chapters_look_empty`` detector requires ≥3 chapter
    parts (we have 1); ``_section_mode_routed_to_stubs`` requires ≥3 stub
    references (we have 1 total). Neither fires.

    Detection: at most one navPoint targets a non-front-matter file, AND
    at least 3 manifest XHTML files are above the body byte-threshold,
    AND the unreferenced body bytes dominate the referenced bytes by ≥5×
    (same gate as ``_section_mode_routed_to_stubs``).
    """
    if len(deduped_structure) > 1:
        return False

    referenced_positions = {s["_position"] for s in deduped_structure}

    with zipfile.ZipFile(epub_path) as zf:
        opf_path = _find_opf_path(zf)
        opf_dir = str(Path(opf_path).parent) + "/" if "/" in opf_path else ""

        ref_bytes: list[int] = []
        unref_bytes: list[int] = []
        for i, href in enumerate(manifest_hrefs, start=1):
            try:
                size = zf.getinfo(f"{opf_dir}{href}").file_size
            except KeyError:
                continue
            if i in referenced_positions:
                ref_bytes.append(size)
            else:
                unref_bytes.append(size)

    large_unrefs = sum(1 for b in unref_bytes if b > _SECTION_MODE_BODY_FILE_BYTE_THRESHOLD)
    if large_unrefs < 3:
        return False
    if sum(ref_bytes) == 0:
        return True
    return sum(unref_bytes) >= 5 * sum(ref_bytes)


def _section_mode_chapters_look_empty(parts: list[str]) -> bool:
    """Detect the Calibre-pre-split-spine pattern that breaks section-mode body lookup.

    Symptom: most ``# Chapter N — ...`` sections come back with a body short
    enough that it's clearly just a TOC link-back wrapper (typical wrapper:
    ``[Chapter One Title](./03-Contents.md#ch4)`` and nothing else, ~5-15
    words). Real non-fiction chapters are 1,000+ words; a chapter that
    short means epub2md routed the wrong manifest file under the NCX entry.

    The 25-word floor sits comfortably above realistic wrapper-only sizes
    (a bracketed-link chapter title is 5-15 words even with publisher
    decoration) and below any plausible real chapter body.

    Triggers fallback when at least 3 chapters AND ≥50% of chapters fall
    below the floor. The 3-chapter floor avoids false-positives on
    legitimately short interlude chapters in books with few chapters total.
    """
    chapter_word_counts: list[int] = []
    for part in parts:
        first_line = part.split("\n", 1)[0]
        if not first_line.startswith("# Chapter "):
            continue
        body = "\n".join(part.split("\n")[1:]).strip()
        chapter_word_counts.append(len(body.split()))

    if len(chapter_word_counts) < 3:
        return False
    short = sum(1 for w in chapter_word_counts if w < _SECTION_MODE_EMPTY_CHAPTER_WORD_FLOOR)
    return short >= 3 and short / len(chapter_word_counts) >= 0.5


def _section_mode_routed_to_stubs(
    epub_path: Path,
    deduped_structure: list[dict],
    manifest_hrefs: list[str],
) -> bool:
    """Detect EPUBs where the NCX points at small stub files while
    substantially larger body files exist unreferenced in the same manifest.

    Failure pattern (real example: Brian Tracy's *The Psychology of Selling*,
    Thomas Nelson 2004): each chapter has two manifest XHTML files — a small
    "Action Exercises" stub (~1-2 KB, ~100-300 words) and a separate body
    file (12-84 KB, several thousand words). The NCX entries point at the
    stubs, so section-mode produces near-empty chapters even though the body
    files are present in the EPUB. The ``_section_mode_chapters_look_empty``
    detector does not fire on this pattern because the stubs contain
    enough text (numbered exercises plus a quote) to clear its 25-word floor.

    Detection: at least 3 NCX-referenced files are below the stub
    byte-threshold, AND at least 3 unreferenced manifest XHTML files are
    above the body byte-threshold, AND the unreferenced files' total bytes
    are >= 5x the referenced files' total bytes. The 5x gate ensures we
    only flag EPUBs where the unreferenced files clearly dominate the
    body content, avoiding false positives on EPUBs with a few small
    front-matter files alongside normal-length chapters.
    """
    referenced_positions = {s["_position"] for s in deduped_structure}
    if not referenced_positions:
        return False

    with zipfile.ZipFile(epub_path) as zf:
        opf_path = _find_opf_path(zf)
        opf_dir = str(Path(opf_path).parent) + "/" if "/" in opf_path else ""

        ref_bytes: list[int] = []
        unref_bytes: list[int] = []
        for i, href in enumerate(manifest_hrefs, start=1):
            try:
                size = zf.getinfo(f"{opf_dir}{href}").file_size
            except KeyError:
                continue
            if i in referenced_positions:
                ref_bytes.append(size)
            else:
                unref_bytes.append(size)

    short_refs = sum(1 for b in ref_bytes if b < _SECTION_MODE_STUB_FILE_BYTE_THRESHOLD)
    large_unrefs = sum(1 for b in unref_bytes if b > _SECTION_MODE_BODY_FILE_BYTE_THRESHOLD)
    if short_refs < 3 or large_unrefs < 3:
        return False
    if sum(ref_bytes) == 0:
        return True
    return sum(unref_bytes) >= 5 * sum(ref_bytes)


def _convert_via_merge_mode_with_section_labels(
    epub_path: Path, out_path: Path
) -> ConversionResult:
    """Fallback path for EPUBs whose chapter bodies are split across files.

    Some publisher EPUBs (commonly retail HarperCollins/Anna's-Archive
    builds processed through Calibre) carry per-chapter HTML files in
    ``partNNNN_split_NNN.html`` form: the NCX entry points at the small
    wrapper file (a chapter title with a link back to the TOC) and the
    actual body text lives in subsequent split files. The standard
    section-mode path reads only the wrapper, leaving every chapter
    empty.

    Merge mode (``epub2md -m``) sidesteps the NCX-to-file lookup entirely
    by concatenating all spine content under the H1 boundaries the EPUB
    itself emits. This function runs merge mode, walks the resulting
    file's H1 boundaries, transforms each one into the standard label
    (``# Chapter N — Title`` / ``# Preamble — Title`` / ``# Front Matter`` /
    ``# Back Matter``) using the same ``classify_section`` heuristic as
    the section-mode path, and writes the result.

    Word-numbered chapter headings (``Chapter One Title``, ``Chapter Two``)
    are converted to digits for the standard label format. Sections without
    explicit numbers (Conclusion, Epilogue) consume the next chapter slot.
    """
    import tempfile

    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        run_epub2md_convert(epub_path, td_path, merge=True)
        merged_dir = td_path / epub_path.stem
        merged_md = merged_dir / "merged.md"
        if not merged_md.exists():
            mds = list(merged_dir.glob("*.md"))
            if not mds:
                raise RuntimeError(
                    f"epub2md merge mode produced no markdown in {merged_dir}"
                )
            merged_md = mds[0]
        text = merged_md.read_text()
        # Carry images over.
        src_images = merged_dir / "images"
        if src_images.is_dir():
            dst_images = out_path.parent / "images"
            if dst_images.exists():
                shutil.rmtree(dst_images)
            shutil.copytree(src_images, dst_images)

    # Split on H1 boundaries (lookahead so the boundary stays with its body).
    raw_sections = re.split(r"(?m)^(?=# )", text)
    raw_sections = [s for s in raw_sections if s.strip()]

    parts: list[str] = []
    chapter_num = 0
    for raw in raw_sections:
        head_line, _, body = raw.partition("\n")
        body = body.strip()

        # Strip the bracketed-link form epub2md emits in merge mode:
        #   "# [Chapter One What Is This Fire?](#id9#nch4)"
        # Falls through to a plain "# Title" head if the link form doesn't match.
        m_link = re.match(r"^# \[([^\]]+)\](?:\([^)]*\))?\s*$", head_line)
        if m_link:
            title = m_link.group(1).strip()
        elif head_line.startswith("# "):
            title = head_line[2:].strip()
        else:
            continue
        if not title:
            continue

        # Pull an explicit chapter number out of "Chapter <N>[ <title>]" forms.
        explicit_num: int | None = None
        chapter_title = title
        m_chap = re.match(r"^Chapter\s+(\w+)\s*[:.\-—]?\s*(.*)$", title, re.IGNORECASE)
        if m_chap:
            num_token = m_chap.group(1).lower()
            rest = m_chap.group(2).strip()
            if num_token.isdigit():
                explicit_num = int(num_token)
            elif num_token in _WORD_TO_NUM:
                explicit_num = _WORD_TO_NUM[num_token]
            if explicit_num is not None and rest:
                chapter_title = rest

        cls = classify_section(title)
        if explicit_num is not None:
            cls = SectionClass.CHAPTER

        if cls == SectionClass.PART:
            if len(body.split()) < _PART_BODY_MIN_WORDS:
                continue
            heading = f"# Part — {chapter_title}"
        elif cls == SectionClass.CHAPTER:
            if explicit_num is not None:
                chapter_num = explicit_num
            else:
                chapter_num += 1
            heading = f"# Chapter {chapter_num} — {chapter_title}"
        elif cls == SectionClass.PREAMBLE:
            heading = f"# Preamble — {chapter_title}"
        elif cls == SectionClass.FRONT:
            heading = f"# Front Matter — {chapter_title}"
        else:
            heading = f"# Back Matter — {chapter_title}"
        parts.append(f"{heading}\n\n{body}\n")

    out_path.write_text("\n".join(parts))
    return ConversionResult(
        chapter_count=chapter_num,
        conversion_quality="high",
        mode="structured",
    )


def _convert_via_spine_body_extraction(
    epub_path: Path, out_path: Path
) -> ConversionResult:
    """Fallback for EPUBs whose NCX is unreliable — either pointing at stub
    files while body content lives unreferenced (Tracy pattern) or so
    degenerate it has just one navPoint while the spine holds the entire
    book (BYS / Wiley pattern).

    Strategy: ignore the NCX entirely, walk the spine in reading order,
    skip files below the stub byte threshold, and classify each remaining
    file by — in priority order — (1) publisher CSS-class title markup
    (Wiley's ``<p class="chaptertitle">`` family), (2) known filename stems
    ("foreword.html" / "FinalThoughts.html"), (3) the first non-empty line
    of extracted text.

    Wiley splits long chapters across multiple sub-files (Chapter16.html
    plus Chapter16a/b/c.html); when a sub-file is detected its body is
    appended to the preceding Chapter section rather than emitted as a
    new chapter.

    Real examples:
      - Brian Tracy *The Psychology of Selling* (Thomas Nelson 2004) —
        NCX points at small Action-Exercise stubs while body files live
        unreferenced in the same manifest; section-mode produced near-
        empty chapters (NCX-points-to-stub pattern).
      - Michael Port *Book Yourself Solid* (John Wiley & Sons 2010) —
        toc.ncx contains exactly one navPoint pointing at cover.xml while
        the spine holds 38 substantive XHTML files; section-mode produced
        a single one-sentence "chapter" (degenerate-NCX pattern).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    spine_hrefs = _spine_xhtml_hrefs(epub_path)
    if not spine_hrefs:
        # No usable spine — fall back to manifest order so callers built
        # against the older API (and our older tests) still get output.
        spine_hrefs = _xhtml_manifest_hrefs(epub_path)

    with zipfile.ZipFile(epub_path) as zf:
        opf_path = _find_opf_path(zf)
        opf_dir = str(Path(opf_path).parent) + "/" if "/" in opf_path else ""

        chapter_num = 0
        parts: list[str] = []

        for href in spine_hrefs:
            full_path = f"{opf_dir}{href}"
            try:
                size = zf.getinfo(full_path).file_size
            except KeyError:
                continue

            # Wiley-style chapter sub-files (Chapter16a/b/c.html) extend
            # the preceding Chapter rather than starting a new one. We
            # check this BEFORE the byte-size gate because some sub-files
            # are deliberately small.
            sub = _chapter_subfile_match(href)
            if sub is not None and parts and parts[-1].startswith("# Chapter "):
                try:
                    xhtml = zf.read(full_path).decode("utf-8", errors="replace")
                except KeyError:
                    continue
                sub_body = _extract_xhtml_text(xhtml).strip()
                if sub_body:
                    parts[-1] = parts[-1].rstrip() + "\n\n" + sub_body + "\n"
                continue

            try:
                xhtml = zf.read(full_path).decode("utf-8", errors="replace")
            except KeyError:
                continue

            # Small files are usually navigation/copyright/title stubs and
            # should be dropped. EXCEPT when they carry a publisher-class
            # title — short Wiley Part-divider files (1-3 KB intros tagged
            # with class="parttitle") are genuine content we want to keep.
            if size < _SECTION_MODE_STUB_FILE_BYTE_THRESHOLD:
                if _extract_publisher_class_title(xhtml) is None:
                    continue

            body = _extract_xhtml_text(xhtml)
            wc = len(body.split())
            if wc == 0:
                continue

            # Section-class resolution priority:
            #   1. Filename stem in the known-classification list (catches
            #      foreword/AuthorsNote/FinalThoughts/copyright/cover/etc.,
            #      including the 'filter' verdict that drops a file entirely).
            #   2. Publisher CSS-class title (Wiley chaptertitle / parttitle /
            #      prefacetitle / mattertitle family).
            #   3. Fallback to the first non-empty line of extracted body
            #      text + the existing classify_section() heuristics.
            filename_class = _filename_section_class(href)
            class_title = _extract_publisher_class_title(xhtml)

            section_cls: str | None = None
            classify_target: str = ""

            if filename_class is not None:
                section_cls, classify_target = filename_class
                if section_cls == "filter":
                    continue
                # Filename gave us 'preamble' or 'back' plus a clean title.
                # Prefer it over class_title because Wiley reuses
                # 'mattertitle' for both prefatory and back matter, which
                # the filename mapping disambiguates.
            elif class_title is not None:
                section_cls, classify_target = class_title
                # For parts, Wiley typically emits TWO parttitle paragraphs
                # ("Module ONE", "Your Foundation"). Combine them as
                # "Module ONE: Your Foundation" when both are present.
                module_match = re.search(
                    r'<p\s+[^>]*class="(?:parttitle|partnumber)[^"]*"[^>]*>'
                    r'(\s*Module\s+[A-Za-z]+|\s*Part\s+[A-Za-z\d]+)\s*</p>',
                    xhtml,
                    re.IGNORECASE,
                )
                if section_cls == "part" and module_match:
                    label = re.sub(r"\s+", " ", module_match.group(1)).strip()
                    if label and not classify_target.lower().startswith(label.lower()):
                        classify_target = f"{label}: {classify_target}"

            if section_cls is None:
                # Existing fallback path: derive a title from the extracted
                # text and classify via the legacy heuristics.
                lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
                title = lines[0] if lines else Path(href).stem
                stripped_title = re.sub(r"^\d+\s+", "", title).strip()
                classify_target = stripped_title or title
                cls_enum = classify_section(classify_target)
                if cls_enum == SectionClass.PART:
                    section_cls = "part"
                elif cls_enum == SectionClass.CHAPTER:
                    section_cls = "chapter"
                elif cls_enum == SectionClass.PREAMBLE:
                    section_cls = "preamble"
                elif cls_enum == SectionClass.FRONT:
                    section_cls = "front"
                else:
                    section_cls = "back"

            if section_cls == "part":
                if wc < _PART_BODY_MIN_WORDS:
                    continue
                heading = f"# Part — {classify_target}"
            elif section_cls == "chapter":
                chapter_num += 1
                heading = f"# Chapter {chapter_num} — {classify_target}"
            elif section_cls == "preamble":
                heading = f"# Preamble — {classify_target}"
            elif section_cls == "front":
                heading = f"# Front Matter — {classify_target}"
            else:
                heading = f"# Back Matter — {classify_target}"
            parts.append(f"{heading}\n\n{body}\n")

        out_path.write_text("\n".join(parts))

    return ConversionResult(
        chapter_count=chapter_num,
        conversion_quality="high",
        mode="structured",
    )


def convert_epub_to_markdown(epub_path: Path, out_path: Path) -> ConversionResult:
    """Convert an EPUB to a single chapter-structured markdown file.

    Properly-structured EPUBs: one `# Chapter N — <Title>` per chapter, plus
    `# Front Matter — <Title>` / `# Back Matter — <Title>` for everything else.

    PDF-origin EPUBs: flat merge; no class-prefixed H1s emitted. Result
    conversion_quality == 'low'.

    Apple-Pages-generated EPUBs: routed to convert_pages_epub_to_markdown,
    which bypasses epub2md (which can't read Pages's inline-span-heavy
    XHTML) and extracts text directly.
    """
    import tempfile

    out_path.parent.mkdir(parents=True, exist_ok=True)

    def _copy_images(from_dir: Path) -> None:
        src_images = from_dir / "images"
        if src_images.is_dir():
            dst_images = out_path.parent / "images"
            if dst_images.exists():
                shutil.rmtree(dst_images)
            shutil.copytree(src_images, dst_images)

    # Apple Pages EPUBs need direct XHTML extraction — epub2md silently
    # produces near-empty markdown on them.
    if is_pages_origin(epub_path):
        return convert_pages_epub_to_markdown(epub_path, out_path)

    # Kobo-flavored EPUBs (Simon & Schuster trade nonfiction commonly ships
    # this way) wrap text in inline `<span class="koboSpan">` elements that
    # epub2md silently drops. The Pages-fallback's regex-based tag-stripping
    # path handles them identically.
    if is_kobo_span_epub(epub_path):
        return convert_pages_epub_to_markdown(epub_path, out_path)

    if is_pdf_origin(epub_path):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            run_epub2md_convert(epub_path, td_path, merge=True)
            # In merge mode, epub2md writes to <epub-stem>/merged.md
            merged_dir = td_path / epub_path.stem
            merged_md = merged_dir / "merged.md"
            if not merged_md.exists():
                # Fallback: look for any .md file
                mds = list(merged_dir.glob("*.md"))
                if not mds:
                    raise RuntimeError(f"epub2md merge mode produced no markdown in {merged_dir}")
                merged_md = mds[0]
            out_path.write_text(merged_md.read_text())
            _copy_images(merged_dir)
        return ConversionResult(chapter_count=0, conversion_quality="low", mode="flat")

    # Structured mode
    structure = epub_structure(epub_path)
    if not structure:
        # No NCX → fall back to flat merge, flagged low
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            run_epub2md_convert(epub_path, td_path, merge=True)
            merged_dir = td_path / epub_path.stem
            merged_md = merged_dir / "merged.md"
            if merged_md.exists():
                out_path.write_text(merged_md.read_text())
            else:
                # Fallback: look for any .md file
                mds = list(merged_dir.glob("*.md"))
                if mds:
                    out_path.write_text(mds[0].read_text())
            _copy_images(merged_dir)
        return ConversionResult(chapter_count=0, conversion_quality="low", mode="flat")

    # Map NCX nav-point src hrefs to their position in the manifest (1-indexed,
    # xhtml items only). epub2md emits files numbered by manifest position,
    # so this is how we look up the right body for each NCX entry. Indexing
    # NCX entries directly (as the original implementation did) mis-reads
    # bodies whenever the manifest has xhtml items not in the NCX
    # (halftitle pages, praise sections, divisional half-titles — common in
    # Penguin Classics, HarperCollins releases, etc.).
    manifest_hrefs = _xhtml_manifest_hrefs(epub_path)
    pos_by_href = {href: i for i, href in enumerate(manifest_hrefs, start=1)}
    pos_by_basename = {Path(href).name: i for i, href in enumerate(manifest_hrefs, start=1)}

    from urllib.parse import unquote

    def _resolve_position(src: str) -> int | None:
        # NCX `src` may include a fragment, may be percent-encoded (e.g.
        # `%40` for `@` — Project Gutenberg-derived EPUBs commonly do this),
        # and may be relative to a different directory than the manifest
        # hrefs. Normalize and try several matches.
        bare = unquote(src.split("#", 1)[0])
        if bare in pos_by_href:
            return pos_by_href[bare]
        return pos_by_basename.get(Path(bare).name)

    # Dedupe NCX entries by the spine position they target. Many retail
    # EPUBs have rich NCX nav with sub-section fragment-anchors pointing
    # into the same chapter file. Without dedupe, the converter emits one
    # chapter heading per NCX entry, all with the same file content as
    # body — producing massive duplication (e.g. 98 chapters × the same
    # 6800-word body for Running Lean). Dedupe so each unique spine file
    # gets exactly one chapter heading, taking the first NCX entry that
    # targets it as the title.
    seen_positions: set[int] = set()
    deduped_structure: list[dict] = []
    for section in structure:
        position = _resolve_position(section.get("src", ""))
        if position is None or position in seen_positions:
            continue
        seen_positions.add(position)
        deduped_structure.append({**section, "_position": position})

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        section_dir = run_epub2md_convert(epub_path, td_path, merge=False)

        # epub2md silently drops a root-level cover/titlepage (Penguin,
        # Portfolio, and many other trade-publisher EPUBs ship that way),
        # which would shift every body off-by-one. Detect and compensate.
        skip_offset = _epub2md_skip_offset(section_dir, manifest_hrefs)

        chapter_num = 0
        parts: list[str] = []
        for section in deduped_structure:
            name = section["name"]
            cls = classify_section(name)
            body = _section_body_for_position(
                section_dir, section["_position"], skip_offset=skip_offset
            )
            if cls == SectionClass.PART:
                if len(body.split()) < _PART_BODY_MIN_WORDS:
                    continue  # divider-only Part page; drop entirely
                heading = f"# Part — {name}"
            elif cls == SectionClass.CHAPTER:
                chapter_num += 1
                heading = f"# Chapter {chapter_num} — {name}"
            elif cls == SectionClass.PREAMBLE:
                heading = f"# Preamble — {name}"
            elif cls == SectionClass.FRONT:
                heading = f"# Front Matter — {name}"
            else:
                heading = f"# Back Matter — {name}"
            parts.append(f"{heading}\n\n{body.strip()}\n")

        # Detect the Calibre-pre-split-spine pattern: NCX entries point at
        # tiny chapter-wrapper files while the actual chapter body lives in
        # subsequent _split_NNN.html files. Section-mode reads only the
        # wrapper, leaving every chapter near-empty. Re-run via merge mode
        # (which concatenates all spine content under the EPUB's own H1s) and
        # use that output instead.
        if _section_mode_chapters_look_empty(parts):
            return _convert_via_merge_mode_with_section_labels(epub_path, out_path)

        # Detect the NCX-points-to-stub pattern: NCX-referenced files are
        # small stubs (action exercises, summaries) while substantially larger
        # body files exist unreferenced in the same manifest. Section-mode
        # produces non-empty but stub-only chapters (e.g. ~200 words each)
        # that don't trigger the empty-chapter detector above. Real example:
        # Brian Tracy's *The Psychology of Selling* (Thomas Nelson 2004).
        # Re-run via spine-body extraction (which ignores the NCX and walks
        # the spine in reading order, skipping stubs).
        if _section_mode_routed_to_stubs(epub_path, deduped_structure, manifest_hrefs):
            return _convert_via_spine_body_extraction(epub_path, out_path)

        # Detect the degenerate-NCX pattern: NCX has 0 or 1 substantive
        # navPoints while the spine holds many substantive XHTML files.
        # Section-mode emits one chapter heading from the single navPoint
        # (typically cover.xml) and silently drops the rest of the book.
        # The two prior detectors miss this case because each requires ≥3
        # NCX entries to fire. Real example: Michael Port's *Book Yourself
        # Solid* (John Wiley & Sons 2010, Sigil-built).
        if _section_mode_ncx_is_degenerate(epub_path, deduped_structure, manifest_hrefs):
            return _convert_via_spine_body_extraction(epub_path, out_path)

        out_path.write_text("\n".join(parts))
        _copy_images(section_dir)

    return ConversionResult(
        chapter_count=chapter_num,
        conversion_quality="high",
        mode="structured",
    )
