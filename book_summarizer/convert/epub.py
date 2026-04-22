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
    # artifact so we don't pollute the user's book-downloader folder.
    final_dest = out_dir / epub_stem
    if final_dest.exists():
        shutil.rmtree(final_dest)
    shutil.copytree(produced_at_source, final_dest)
    shutil.rmtree(produced_at_source)

    return final_dest


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
