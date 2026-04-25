# tests/test_convert_epub.py
from pathlib import Path

from book_llm_wiki.convert.epub import epub_info, epub_structure


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


from book_llm_wiki.convert.epub import classify_section, SectionClass


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


from book_llm_wiki.convert.epub import convert_epub_to_markdown


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


def _build_epub_with_layout(
    out_path: Path,
    title: str,
    sections: list[tuple[str, str]],  # all (label, body) by manifest order
    spine_indices: list[int],          # which manifest indices appear in spine, in spine order
    ncx_indices: list[int],            # which manifest indices appear in NCX, in NCX order
) -> Path:
    """Build an EPUB with explicit manifest / spine / NCX orderings.

    Real publishers often have items in the manifest that are reordered (or
    absent) in the spine, and items that don't appear in the NCX. This helper
    lets tests model those cases independently.
    """
    import zipfile
    from tests.conftest import (
        CONTAINER_XML, CONTENT_OPF_TEMPLATE, NCX_TEMPLATE,
        NAV_POINT_TEMPLATE, HTML_TEMPLATE, MIMETYPE,
    )

    manifest_items = []
    html_files = {}
    for i, (label, body) in enumerate(sections, start=1):
        item_id = f"s{i}"
        href = f"section-{i}.xhtml"
        manifest_items.append(f'    <item id="{item_id}" href="{href}" media-type="application/xhtml+xml"/>')
        html_files[href] = HTML_TEMPLATE.format(title=label, body=body)

    spine_items = [f'    <itemref idref="s{idx + 1}"/>' for idx in spine_indices]

    nav_points = []
    for order, idx in enumerate(ncx_indices, start=1):
        label, _ = sections[idx]
        href = f"section-{idx + 1}.xhtml"
        nav_points.append(NAV_POINT_TEMPLATE.format(id=f"nav{order}", order=order, label=label, src=href))

    content_opf = CONTENT_OPF_TEMPLATE.format(
        title=title,
        author="Test Author",
        year="2024",
        title_slug=title.lower().replace(" ", "-"),
        manifest_items="\n".join(manifest_items),
        spine_items="\n".join(spine_items),
        extra_metadata="",
    )
    ncx_xml = NCX_TEMPLATE.format(title=title, nav_points="\n".join(nav_points))

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/toc.ncx", ncx_xml)
        for href, html in html_files.items():
            zf.writestr(f"OEBPS/{href}", html)
    return out_path


def test_convert_aligns_bodies_when_manifest_has_items_not_in_ncx(tmp_path: Path):
    """Regression: real EPUBs (Penguin Classics, etc.) often have manifest
    items not referenced in the NCX (halftitle pages, divisional half-titles).
    epub2md emits one .md per manifest item, so aligning bodies to NCX-index
    misreads every section after the first such gap.
    """
    sections = [
        ("Cover", "Cover image."),
        ("Halftitle Page", "(halftitle, not in NCX)"),
        ("Chapter 1: First", "BODY-OF-FIRST " * 30),
        ("Chapter 2: Second", "BODY-OF-SECOND " * 30),
        ("Chapter 3: Third", "BODY-OF-THIRD " * 30),
    ]
    epub_path = _build_epub_with_layout(
        tmp_path / "halftitle.epub",
        title="Halftitle Mismatch Book",
        sections=sections,
        spine_indices=[0, 1, 2, 3, 4],     # halftitle in spine
        ncx_indices=[0, 2, 3, 4],          # halftitle absent from NCX
    )

    out = tmp_path / "out.md"
    convert_epub_to_markdown(epub_path, out)
    text = out.read_text()

    ch1 = text.index("# Chapter 1 — Chapter 1: First")
    ch2 = text.index("# Chapter 2 — Chapter 2: Second")
    ch3 = text.index("# Chapter 3 — Chapter 3: Third")
    assert "BODY-OF-FIRST" in text[ch1:ch2]
    assert "BODY-OF-SECOND" in text[ch2:ch3]
    assert "BODY-OF-THIRD" in text[ch3:]


def test_convert_aligns_bodies_when_spine_reorders_manifest(tmp_path: Path):
    """Regression: epub2md numbers files by manifest order, but the spine
    can reorder items independently. A section at manifest position 4 may
    appear at spine position 25 (e.g., a Praise / endorsements page that is
    in the middle of the manifest but at the back of the reading sequence).
    Aligning by spine position then misreads every chapter.
    """
    # Manifest order: Cover, Title, Praise, Foreword, Ch1, Ch2, Ch3.
    # Spine order: Cover, Title, Foreword, Ch1, Ch2, Ch3, Praise (Praise at the back).
    # NCX includes everything except Praise.
    sections = [
        ("Cover", "Cover image."),
        ("Title Page", "Title."),
        ("Praise", "Praise endorsements."),
        ("Foreword by James Clear", "FOREWORD-MARKER " * 20),
        ("Chapter 1: First", "BODY-OF-FIRST " * 30),
        ("Chapter 2: Second", "BODY-OF-SECOND " * 30),
        ("Chapter 3: Third", "BODY-OF-THIRD " * 30),
    ]
    epub_path = _build_epub_with_layout(
        tmp_path / "spine_reorder.epub",
        title="Spine Reorder Book",
        sections=sections,
        spine_indices=[0, 1, 3, 4, 5, 6, 2],  # Praise (manifest 2) moved to end
        ncx_indices=[0, 1, 3, 4, 5, 6],       # NCX skips Praise entirely
    )

    out = tmp_path / "out.md"
    convert_epub_to_markdown(epub_path, out)
    text = out.read_text()

    fw = text.index("# Chapter 1 — Foreword by James Clear")
    ch1 = text.index("# Chapter 2 — Chapter 1: First")
    ch2 = text.index("# Chapter 3 — Chapter 2: Second")
    ch3 = text.index("# Chapter 4 — Chapter 3: Third")
    assert "FOREWORD-MARKER" in text[fw:ch1]
    assert "BODY-OF-FIRST" in text[ch1:ch2]
    assert "BODY-OF-SECOND" in text[ch2:ch3]
    assert "BODY-OF-THIRD" in text[ch3:]
