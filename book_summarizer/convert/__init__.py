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
