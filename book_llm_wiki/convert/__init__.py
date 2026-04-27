"""Format detection and convert() dispatcher."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from book_llm_wiki.convert.epub import convert_epub_to_markdown
from book_llm_wiki.convert.kindle import convert_kindle_to_epub
from book_llm_wiki.convert.markdown import convert_markdown_to_markdown
from book_llm_wiki.convert.pdf import convert_pdf_to_markdown


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
    if ext in {".azw3", ".mobi"}:
        return "kindle"
    if ext == ".pdf":
        return "pdf"
    if ext in {".md", ".markdown"}:
        return "markdown"
    raise ValueError(f"Unsupported format: {ext}")


def convert(src: Path, out_path: Path) -> UnifiedConversionResult:
    fmt = detect_format(src)
    if fmt == "kindle":
        # Preprocess to .epub via calibre, then run the standard epub pipeline.
        kindle_ext = Path(src).suffix.lower().lstrip(".")
        epub_path = convert_kindle_to_epub(Path(src))
        try:
            r = convert_epub_to_markdown(epub_path, out_path)
        finally:
            # Clean up the temp epub and its parent dir
            import shutil as _shutil
            _shutil.rmtree(epub_path.parent, ignore_errors=True)
        return UnifiedConversionResult(
            chapter_count=r.chapter_count,
            conversion_quality=r.conversion_quality,
            mode=r.mode,
            source_format=kindle_ext,
        )
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
