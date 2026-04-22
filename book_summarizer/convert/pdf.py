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
