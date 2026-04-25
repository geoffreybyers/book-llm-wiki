#!/usr/bin/env python3
"""Check whether an EPUB looks like a low-quality PDF-to-EPUB conversion.

Usage:
    python -m book_llm_wiki.downloader.epub_quality <path-to-file.epub>

Exit codes:
    0  good
    1  bad (PDF-conversion artifacts or broken metadata detected)
    2  error reading file

Output: JSON to stdout with verdict, score, and reasons.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path


def extract_metadata(path: Path) -> dict[str, str]:
    try:
        out = subprocess.run(
            ["ebook-meta", str(path)],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}
    meta = {}
    for line in out.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip().lower()] = v.strip()
    return meta


def extract_body_text(path: Path, max_files: int = 8) -> str:
    try:
        with zipfile.ZipFile(path) as z:
            html_names = [n for n in z.namelist()
                          if n.lower().endswith((".xhtml", ".html", ".htm"))]
            chunks = []
            for n in html_names[:max_files]:
                try:
                    chunks.append(z.read(n).decode("utf-8", "ignore"))
                except Exception:
                    pass
    except (zipfile.BadZipFile, FileNotFoundError):
        return ""
    raw = "".join(chunks)
    text = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", text)


def check(path: Path) -> dict:
    reasons: list[str] = []
    score = 0  # higher = worse

    # PDF-origin detection (shares logic with the convert pipeline so the
    # downloader and the converter agree on what's "good"). Catches files
    # that have clean publisher metadata but were ultimately derived from
    # a PDF — over-segmented NCX, `pdftohtml` generator, or pdftohtml
    # references in body content. Scoring this at 5 means a single positive
    # signal here reaches the "bad" threshold on its own.
    try:
        from book_llm_wiki.convert.epub import is_pdf_origin
        if is_pdf_origin(path):
            score += 5
            reasons.append("PDF-origin EPUB (would force flat-merge / single-pass downstream)")
    except Exception:
        # Don't fail the check if convert.epub can't be imported (e.g. when
        # this module is run as a standalone script outside the package).
        pass

    meta = extract_metadata(path)
    title = meta.get("title", "")
    author = meta.get("author(s)", "")

    # --- Metadata fingerprints ---
    if re.search(r"pdfdrive", title, re.I):
        score += 5
        reasons.append("PDFDrive watermark in title field")
    if re.search(r"\.(pdf|epub|mobi|azw)\b", title, re.I):
        score += 4
        reasons.append(f"Title field contains a filename extension: {title!r}")
    # Author field is a hex hash (e.g. SHA/MD5)
    if re.fullmatch(r"[0-9a-f]{16,}", author.strip().lower()):
        score += 4
        reasons.append(f"Author field looks like a hash: {author!r}")
    # PDF-conversion tools in producer field
    producer = (meta.get("book producer", "") + " " + meta.get("publisher", "")).lower()
    if re.search(r"pdf2epub|pdftoepub|abbyy|nitro|adobe acrobat", producer):
        score += 3
        reasons.append(f"PDF-conversion tool in producer/publisher: {producer!r}")

    # --- Body-text fingerprints ---
    text = extract_body_text(path)
    if text:
        if re.search(r"pdfdrive", text, re.I):
            score += 5
            reasons.append("PDFDrive watermark in body text")

        # Hyphenated word breaks across page boundaries: "knowl- edge"
        hyphen_breaks = len(re.findall(r"\b[a-z]+-\s+[a-z]+\b", text))
        if hyphen_breaks >= 100:
            score += 3
            reasons.append(f"Severe hyphenation breaks across page boundaries: {hyphen_breaks}")
        elif hyphen_breaks >= 30:
            score += 2
            reasons.append(f"Many hyphenation breaks across page boundaries: {hyphen_breaks}")

        # PDF page-number markers leaked into text
        page_markers = len(re.findall(r"\bPage\s+\d+\b", text))
        if page_markers >= 10:
            score += 2
            reasons.append(f"Many 'Page N' markers in body text: {page_markers}")

        # Spaced-letter titles ("T H E T I P P I N G P O I N T") — PDF letterspacing artifact
        if re.search(r"(?:\b[A-Z]\s){6,}[A-Z]\b", text[:5000]):
            score += 3
            reasons.append("Spaced-letter heading detected (PDF letterspacing artifact)")

    verdict = "bad" if score >= 3 else "good"
    return {
        "path": str(path),
        "verdict": verdict,
        "score": score,
        "reasons": reasons,
        "title": title,
        "author": author,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m book_llm_wiki.downloader.epub_quality <path-to-file.epub>", file=sys.stderr)
        return 2
    p = Path(sys.argv[1])
    if not p.exists():
        print(json.dumps({"error": f"file not found: {p}"}))
        return 2
    result = check(p)
    print(json.dumps(result, indent=2))
    return 0 if result["verdict"] == "good" else 1


if __name__ == "__main__":
    sys.exit(main())
