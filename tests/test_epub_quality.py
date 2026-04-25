from pathlib import Path

from book_llm_wiki.downloader.epub_quality import check


def test_clean_epub_scores_zero(normal_epub: Path):
    """A properly-structured publisher EPUB should pass with score 0."""
    result = check(normal_epub)
    assert result["verdict"] == "good", f"got reasons: {result['reasons']}"
    assert result["score"] == 0
    assert result["reasons"] == []


def test_pdf_origin_epub_is_rejected(pdf_origin_epub: Path):
    """A PDF-derived EPUB (pdftohtml generator marker) must score >=3
    so the downloader rejects it. The check shares is_pdf_origin() with
    the convert pipeline so both stages agree on what's "good."""
    result = check(pdf_origin_epub)
    assert result["verdict"] == "bad", f"expected rejection, got {result}"
    assert any("PDF-origin" in r for r in result["reasons"])
