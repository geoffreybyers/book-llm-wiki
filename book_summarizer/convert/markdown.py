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
