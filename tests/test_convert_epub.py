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
    assert classify_section("Cover Page") == SectionClass.FRONT
    assert classify_section("Title Page") == SectionClass.FRONT
    assert classify_section("Copyright") == SectionClass.BACK  # copyright is back per spec listing
    assert classify_section("Dedication") == SectionClass.FRONT
    assert classify_section("Epigraph") == SectionClass.FRONT
    assert classify_section("Praise") == SectionClass.FRONT
    # Kindle / Apple Books navigation landmark — must not become a chapter.
    assert classify_section("Start Reading") == SectionClass.FRONT
    assert classify_section("Begin Reading") == SectionClass.FRONT


def test_classify_obvious_back_matter():
    assert classify_section("Notes") == SectionClass.BACK
    assert classify_section("Index") == SectionClass.BACK
    assert classify_section("About the Author") == SectionClass.BACK
    assert classify_section("Newsletters") == SectionClass.BACK
    assert classify_section("Also by Cal Newport") == SectionClass.BACK
    assert classify_section("footnotes") == SectionClass.BACK
    assert classify_section("Table of Contents") == SectionClass.BACK
    # "Copyright Page" appears in many EPUBs alongside (or instead of) "Copyright";
    # both must classify the same way to keep chapter numbering aligned.
    assert classify_section("Copyright Page") == SectionClass.BACK


def test_classify_chapters():
    assert classify_section("Chapter 1: Origins") == SectionClass.CHAPTER
    assert classify_section("1 The Surprising Power of Atomic Habits") == SectionClass.CHAPTER
    assert classify_section("Conclusion") == SectionClass.CHAPTER
    assert classify_section("Rule #1: Work Deeply") == SectionClass.CHAPTER
    assert classify_section("The Fundamentals") == SectionClass.CHAPTER  # unknown → default chapter


def test_classify_parts_are_their_own_class():
    """Part separators ('Part 1', 'Part One', 'Part II') must NOT consume a
    chapter number. They classify as PART; the convert loop later decides
    whether to emit body based on word count.
    """
    assert classify_section("PART 1: The Idea") == SectionClass.PART
    assert classify_section("Part 1: The Enemies of Clear Thinking") == SectionClass.PART
    assert classify_section("Part 1. The Enemies of Clear Thinking") == SectionClass.PART
    assert classify_section("Part One: Unleash Your Power") == SectionClass.PART
    assert classify_section("Part Two: Taking Control") == SectionClass.PART
    assert classify_section("Part II: Formulating Strategy") == SectionClass.PART
    assert classify_section("part 5") == SectionClass.PART


def test_classify_preamble_keeps_introductions_unnumbered():
    """Sections that are content-bearing but pre-Chapter-1 belong to PREAMBLE,
    so they can be summarized without consuming chapter numbers."""
    assert classify_section("Introduction") == SectionClass.PREAMBLE
    assert classify_section("Introduction: My Story") == SectionClass.PREAMBLE
    assert classify_section("Preface") == SectionClass.PREAMBLE
    assert classify_section("Preface to the Revised Edition") == SectionClass.PREAMBLE
    assert classify_section("Preface: Zero to One") == SectionClass.PREAMBLE
    assert classify_section("Foreword") == SectionClass.PREAMBLE
    assert classify_section("Foreword by Daniel Kahneman") == SectionClass.PREAMBLE
    assert classify_section("Prologue") == SectionClass.PREAMBLE
    assert classify_section("Welcome") == SectionClass.PREAMBLE
    assert classify_section("An Important Note From Nir") == SectionClass.PREAMBLE
    assert classify_section("Author's Note") == SectionClass.PREAMBLE
    # Curly apostrophe is what most retail EPUBs actually emit for the
    # author's-note heading; must classify the same as the straight form.
    assert classify_section("Author’s Note") == SectionClass.PREAMBLE


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


def test_convert_dedupes_ncx_entries_pointing_to_same_spine_file(tmp_path: Path):
    """Regression: rich retail EPUBs (Running Lean, Design of Everyday Things,
    etc.) have NCX nav entries that fragment-anchor into the same chapter
    files — e.g., 98 nav points referencing only 9 spine files. Without
    dedupe, the converter emits one chapter heading per nav entry, all with
    the same file body — producing massive duplication. Fix: each unique
    spine position becomes one chapter; the first NCX entry that targets it
    supplies the title.
    """
    # 3 spine items, each containing a chapter. NCX has 7 entries: each
    # chapter is listed at the chapter level plus one or two sub-section
    # fragment-anchors targeting the same file.
    sections = [
        ("Chapter 1: First", "BODY-OF-FIRST " * 30),
        ("Chapter 2: Second", "BODY-OF-SECOND " * 30),
        ("Chapter 3: Third", "BODY-OF-THIRD " * 30),
    ]
    spine_indices = [0, 1, 2]
    # Custom NCX: chapter-level entries plus sub-section fragment anchors.
    # We use _build_epub_with_layout's NCX builder, which expects a list of
    # manifest indices, but we want fragment-anchored entries — drop down
    # to constructing the EPUB directly.
    import zipfile
    from tests.conftest import (
        CONTAINER_XML, CONTENT_OPF_TEMPLATE, NCX_TEMPLATE,
        NAV_POINT_TEMPLATE, HTML_TEMPLATE, MIMETYPE,
    )

    manifest_items = []
    spine_items = []
    html_files = {}
    for i, (label, body) in enumerate(sections, start=1):
        item_id = f"s{i}"
        href = f"section-{i}.xhtml"
        manifest_items.append(f'    <item id="{item_id}" href="{href}" media-type="application/xhtml+xml"/>')
        spine_items.append(f'    <itemref idref="{item_id}"/>')
        html_files[href] = HTML_TEMPLATE.format(title=label, body=body)

    # 7 NCX entries: Ch1, Ch1#sec1, Ch2, Ch2#sec1, Ch2#sec2, Ch3, Ch3#sec1
    nav_specs = [
        ("Chapter 1: First",         "section-1.xhtml"),
        ("1.1 First subsection",     "section-1.xhtml#sec1"),
        ("Chapter 2: Second",        "section-2.xhtml"),
        ("2.1 Second subsection a",  "section-2.xhtml#sec1"),
        ("2.2 Second subsection b",  "section-2.xhtml#sec2"),
        ("Chapter 3: Third",         "section-3.xhtml"),
        ("3.1 Third subsection",     "section-3.xhtml#sec1"),
    ]
    nav_points = [
        NAV_POINT_TEMPLATE.format(id=f"nav{i}", order=i, label=label, src=src)
        for i, (label, src) in enumerate(nav_specs, start=1)
    ]

    content_opf = CONTENT_OPF_TEMPLATE.format(
        title="NCX Fragment Book",
        author="Test Author",
        year="2024",
        title_slug="ncx-fragment-book",
        manifest_items="\n".join(manifest_items),
        spine_items="\n".join(spine_items),
        extra_metadata="",
    )
    ncx_xml = NCX_TEMPLATE.format(title="NCX Fragment Book", nav_points="\n".join(nav_points))

    epub_path = tmp_path / "fragment.epub"
    with zipfile.ZipFile(epub_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/toc.ncx", ncx_xml)
        for href, html in html_files.items():
            zf.writestr(f"OEBPS/{href}", html)

    out = tmp_path / "out.md"
    result = convert_epub_to_markdown(epub_path, out)
    text = out.read_text()

    # Three unique spine files → exactly three chapter headings.
    assert result.chapter_count == 3, f"expected 3 chapters, got {result.chapter_count}"
    assert text.count("# Chapter 1 — Chapter 1: First") == 1
    assert text.count("# Chapter 2 — Chapter 2: Second") == 1
    assert text.count("# Chapter 3 — Chapter 3: Third") == 1
    # Sub-section nav entries should not have produced their own chapters.
    assert "1.1 First subsection" not in text
    assert "2.1 Second subsection" not in text
    # Each chapter has its OWN body (no duplication).
    ch1 = text.index("# Chapter 1 — Chapter 1: First")
    ch2 = text.index("# Chapter 2 — Chapter 2: Second")
    ch3 = text.index("# Chapter 3 — Chapter 3: Third")
    assert "BODY-OF-FIRST" in text[ch1:ch2]
    assert "BODY-OF-FIRST" not in text[ch2:]   # not duplicated into Ch2
    assert "BODY-OF-SECOND" in text[ch2:ch3]
    assert "BODY-OF-THIRD" in text[ch3:]


def test_epub2md_skip_offset_compensates_for_root_level_cover(tmp_path: Path):
    """Regression: when manifest[0] XHTML lives at the OPF root and is named
    cover/titlepage/halftitle, epub2md silently drops it and emits one fewer
    `.md` file than the manifest's XHTML count, with its remaining files
    numbered from 01 — shifting every body off-by-one. ``_epub2md_skip_offset``
    detects the well-characterized single-skip case and returns 1.

    Confirmed in the wild on Clear Thinking (Shane Parrish, Penguin/Portfolio
    2023) and Thinking, Fast and Slow (Daniel Kahneman). Without the
    compensation, every NCX-derived ``# Chapter N`` wrapper contains the
    body of conceptual chapter N+1.
    """
    from book_llm_wiki.convert.epub import _epub2md_skip_offset

    section_dir = tmp_path / "sections"
    section_dir.mkdir()

    # Manifest has 5 XHTML; epub2md produced 4 .md (it dropped manifest[0]).
    manifest_root_titlepage = [
        "titlepage.xhtml",                       # at OPF root
        "OEBPS/xhtml/02_Title_Page.xhtml",
        "OEBPS/xhtml/03_Preface.xhtml",
        "OEBPS/xhtml/04_Introduction.xhtml",
        "OEBPS/xhtml/05_Chapter_1.xhtml",
    ]
    for i, name in enumerate(["Title_Page", "Preface", "Introduction", "Chapter_1"], start=1):
        (section_dir / f"{i:02d}-{name}.md").write_text(f"body of {name}")

    assert _epub2md_skip_offset(section_dir, manifest_root_titlepage) == 1

    # Updated 2026-04-27: subdir-located cover IS also dropped by epub2md.
    # Blue Ocean Strategy (HBR 2015) has manifest[0] = "Text/titlepage.html"
    # (subdir, not at OPF root) and epub2md still drops it. Detection now
    # keys off the basename only, not the directory location.
    manifest_subdir_titlepage = [
        "OEBPS/xhtml/01_titlepage.xhtml",
        "OEBPS/xhtml/02_Title_Page.xhtml",
        "OEBPS/xhtml/03_Preface.xhtml",
        "OEBPS/xhtml/04_Introduction.xhtml",
        "OEBPS/xhtml/05_Chapter_1.xhtml",
    ]
    assert _epub2md_skip_offset(section_dir, manifest_subdir_titlepage) == 1

    # Match between produced count and manifest count → no shift needed.
    (section_dir / "05-Chapter_1.md").write_text("body of Chapter_1")
    assert _epub2md_skip_offset(section_dir, manifest_root_titlepage) == 0

    # Manifest[0] basename doesn't look like cover → no shift even when
    # md_count < manifest_count (could be a malformed EPUB or a different
    # epub2md skip pattern; safer to leave alignment to investigation).
    section_dir2 = tmp_path / "sections2"
    section_dir2.mkdir()
    for i, name in enumerate(["preface", "intro", "ch1"], start=1):
        (section_dir2 / f"{i:02d}-{name}.md").write_text("body")
    manifest_no_cover_first = [
        "OEBPS/preface.xhtml",
        "OEBPS/intro.xhtml",
        "OEBPS/ch1.xhtml",
        "OEBPS/ch2.xhtml",
    ]
    assert _epub2md_skip_offset(section_dir2, manifest_no_cover_first) == 0


def test_section_body_for_position_honors_skip_offset(tmp_path: Path):
    """``_section_body_for_position`` must subtract ``skip_offset`` from the
    1-indexed manifest position before globbing, and return empty when the
    effective position falls below 1 (the dropped-cover case)."""
    from book_llm_wiki.convert.epub import _section_body_for_position

    section_dir = tmp_path / "sections"
    section_dir.mkdir()
    (section_dir / "01-Title_Page.md").write_text("body of Title_Page")
    (section_dir / "02-Preface.md").write_text("body of Preface")
    (section_dir / "03-Introduction.md").write_text("body of Introduction")

    # Manifest pos 1 (the dropped cover) → empty after offset.
    assert _section_body_for_position(section_dir, position=1, skip_offset=1) == ""
    # Manifest pos 2 (Title Page) → body in 01-*.md after offset.
    assert "Title_Page" in _section_body_for_position(section_dir, position=2, skip_offset=1)
    # Manifest pos 4 (Introduction) → body in 03-*.md after offset.
    assert "Introduction" in _section_body_for_position(section_dir, position=4, skip_offset=1)
    # Skip offset 0 (no shift) → manifest pos 1 returns the first md.
    assert "Title_Page" in _section_body_for_position(section_dir, position=1, skip_offset=0)


def test_pages_origin_detected_by_generator(tmp_path: Path):
    """`is_pages_origin` should fire on Pages-generated EPUBs (their generator
    metadata reads "Pages Publishing macOS vN")."""
    from book_llm_wiki.convert.epub import is_pages_origin
    sections = [("Cover", "ignored"), ("Chapter 1: First", "ignored")]
    extra = '    <meta name="generator" content="Pages Publishing macOS v1.0"/>'
    epub_path = tmp_path / "pages.epub"
    from tests.conftest import _build_epub
    _build_epub(epub_path, title="Pages Book", author="A", year="2024",
                sections=sections, extra_metadata=extra)
    assert is_pages_origin(epub_path)


def test_pages_origin_not_falsely_detected(normal_epub: Path):
    """A normal publisher EPUB should NOT be flagged as Pages-origin."""
    from book_llm_wiki.convert.epub import is_pages_origin
    assert not is_pages_origin(normal_epub)


def test_extract_xhtml_text_strips_inline_spans(tmp_path: Path):
    """`_extract_xhtml_text` recovers prose from Pages's inline-span-heavy
    XHTML — the structure that epub2md silently drops."""
    from book_llm_wiki.convert.epub import _extract_xhtml_text
    pages_xhtml = """<html><body>
    <h1 class="p1"><span id="ch3"/><span class="c1">SECTION II<br/></span><span class="c1 c2">Pricing</span></h1>
    <p class="p3"><span class="c1">"Grow or Die" is a core tenet at our companies.</span></p>
    <p class="p1"><span class="c1">Maintenance is a myth.</span></p>
    </body></html>"""
    text = _extract_xhtml_text(pages_xhtml)
    assert "SECTION II" in text
    assert "Pricing" in text
    assert "Grow or Die" in text
    assert "Maintenance is a myth" in text


def test_convert_pages_epub_extracts_inline_span_content(tmp_path: Path):
    """End-to-end: a Pages-style EPUB with content in inline spans should
    convert with the actual prose extracted, not just the headings."""
    import zipfile
    from tests.conftest import (
        CONTAINER_XML, CONTENT_OPF_TEMPLATE, NCX_TEMPLATE,
        NAV_POINT_TEMPLATE, MIMETYPE,
    )

    pages_html_template = """<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{title}</title></head>
<body><div class="body" style="white-space:pre-wrap;">
<h1 class="p42"><span class="c1">{title}</span></h1>
<p class="p1"><span class="c1">{body}</span></p>
</div></body></html>"""

    sections = [
        ("Cover", "Cover content"),
        ("Chapter 1: First", "BODY-OF-FIRST " * 30),
        ("Chapter 2: Second", "BODY-OF-SECOND " * 30),
    ]

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
        html_files[href] = pages_html_template.format(title=label, body=body)

    extra_metadata = '    <meta name="generator" content="Pages Publishing macOS v1.0"/>'
    content_opf = CONTENT_OPF_TEMPLATE.format(
        title="Pages Book", author="A", year="2024", title_slug="pages-book",
        manifest_items="\n".join(manifest_items),
        spine_items="\n".join(spine_items),
        extra_metadata=extra_metadata,
    )
    ncx_xml = NCX_TEMPLATE.format(title="Pages Book", nav_points="\n".join(nav_points))

    epub_path = tmp_path / "pages.epub"
    with zipfile.ZipFile(epub_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/toc.ncx", ncx_xml)
        for href, html in html_files.items():
            zf.writestr(f"OEBPS/{href}", html)

    out = tmp_path / "out.md"
    result = convert_epub_to_markdown(epub_path, out)
    text = out.read_text()
    # Headings are emitted with the standard structure...
    assert "# Front Matter — Cover" in text
    assert "# Chapter 1 — Chapter 1: First" in text
    assert "# Chapter 2 — Chapter 2: Second" in text
    # ...and the body prose nested in inline spans is preserved.
    assert "BODY-OF-FIRST" in text
    assert "BODY-OF-SECOND" in text
    assert result.chapter_count == 2
    assert result.conversion_quality == "high"


def test_convert_resolves_percent_encoded_ncx_src(tmp_path: Path):
    """Regression: NCX `src` attributes can be percent-encoded (Project
    Gutenberg-derived EPUBs commonly use `%40` for `@` in their generated
    URIs) while the manifest hrefs are not. Without urllib.unquote, every
    NCX entry fails to resolve to a manifest position and the converter
    drops them all — outputting 0 chapters even when the EPUB has a valid
    72-entry NCX (real case: a Wealth of Nations EPUB packaged from
    Gutenberg HTML).
    """
    import zipfile
    from urllib.parse import quote
    from tests.conftest import (
        CONTAINER_XML, CONTENT_OPF_TEMPLATE, NCX_TEMPLATE,
        NAV_POINT_TEMPLATE, HTML_TEMPLATE, MIMETYPE,
    )

    # Manifest stores the href unencoded; NCX stores it percent-encoded.
    manifest_href = "ch@1.xhtml"  # contains an @ that NCX will encode as %40
    encoded_src = quote(manifest_href, safe="")  # → "ch%401.xhtml"
    body = "BODY-OF-FIRST " * 30

    manifest_items = f'    <item id="s1" href="{manifest_href}" media-type="application/xhtml+xml"/>'
    spine_items = '    <itemref idref="s1"/>'
    nav_points = NAV_POINT_TEMPLATE.format(
        id="nav1", order=1, label="Chapter 1: First", src=encoded_src,
    )

    content_opf = CONTENT_OPF_TEMPLATE.format(
        title="Encoded NCX Book", author="A", year="2024",
        title_slug="encoded-ncx-book",
        manifest_items=manifest_items,
        spine_items=spine_items, extra_metadata="",
    )
    ncx_xml = NCX_TEMPLATE.format(title="Encoded NCX Book", nav_points=nav_points)

    epub_path = tmp_path / "encoded.epub"
    with zipfile.ZipFile(epub_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/toc.ncx", ncx_xml)
        zf.writestr(f"OEBPS/{manifest_href}", HTML_TEMPLATE.format(title="Chapter 1: First", body=body))

    out = tmp_path / "out.md"
    result = convert_epub_to_markdown(epub_path, out)
    text = out.read_text()
    assert result.chapter_count == 1, f"got {result.chapter_count} chapters"
    assert "# Chapter 1 — Chapter 1: First" in text
    assert "BODY-OF-FIRST" in text


def test_is_pdf_origin_passes_rich_retail_nav(tmp_path: Path):
    """Regression: the spine-vs-NCX ratio check should not flag publisher
    EPUBs that have many sub-section fragment-anchors pointing into a small
    set of chapter files. Real example: Don Norman's *Design of Everyday
    Things* retail EPUB has 19 spine items and 77 NCX entries (4.1x ratio)
    but every NCX entry fragment-anchors into the same 19 files. The fix
    counts distinct file targets in NCX, not raw entry count.
    """
    from book_llm_wiki.convert.epub import is_pdf_origin
    import zipfile
    from tests.conftest import (
        CONTAINER_XML, CONTENT_OPF_TEMPLATE, NCX_TEMPLATE,
        NAV_POINT_TEMPLATE, HTML_TEMPLATE, MIMETYPE,
    )

    # 4 spine files, 16 NCX entries (4x ratio) but all anchoring into the
    # same 4 files.
    sections = [
        ("Chapter 1", "ch1 body"),
        ("Chapter 2", "ch2 body"),
        ("Chapter 3", "ch3 body"),
        ("Chapter 4", "ch4 body"),
    ]
    manifest_items = []
    spine_items = []
    html_files = {}
    for i, (label, body) in enumerate(sections, start=1):
        item_id = f"s{i}"
        href = f"section-{i}.xhtml"
        manifest_items.append(f'    <item id="{item_id}" href="{href}" media-type="application/xhtml+xml"/>')
        spine_items.append(f'    <itemref idref="{item_id}"/>')
        html_files[href] = HTML_TEMPLATE.format(title=label, body=body)

    nav_specs = []
    for i in range(1, 5):
        nav_specs.append((f"Chapter {i}", f"section-{i}.xhtml"))
        for j in range(1, 4):
            nav_specs.append((f"{i}.{j} Sub", f"section-{i}.xhtml#sec{j}"))
    nav_points = [
        NAV_POINT_TEMPLATE.format(id=f"nav{k}", order=k, label=label, src=src)
        for k, (label, src) in enumerate(nav_specs, start=1)
    ]
    content_opf = CONTENT_OPF_TEMPLATE.format(
        title="Rich Nav Book", author="A", year="2024",
        title_slug="rich-nav-book",
        manifest_items="\n".join(manifest_items),
        spine_items="\n".join(spine_items), extra_metadata="",
    )
    ncx_xml = NCX_TEMPLATE.format(title="Rich Nav Book", nav_points="\n".join(nav_points))

    epub_path = tmp_path / "richnav.epub"
    with zipfile.ZipFile(epub_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/toc.ncx", ncx_xml)
        for href, html in html_files.items():
            zf.writestr(f"OEBPS/{href}", html)

    assert not is_pdf_origin(epub_path), "rich-nav retail EPUB must not be flagged"


def test_convert_drops_divider_only_part_pages(tmp_path: Path):
    """Awaken the Giant Within and Blue Ocean Strategy use Part pages as
    8-12 word title dividers ('PART ONE / Unleash Your Power'). They must
    not consume a chapter number AND must not show up in the output.
    """
    sections = [
        ("Cover", "Cover image."),
        ("Part One: Unleash Your Power", "PART ONE Unleash Your Power"),  # 5 words
        ("Chapter 1: Dreams of Destiny", "BODY-OF-CH1 " * 30),
        ("Chapter 2: Decisions", "BODY-OF-CH2 " * 30),
        ("Part Two: Taking Control", "PART TWO Taking Control"),  # 4 words
        ("Chapter 3: Master System", "BODY-OF-CH3 " * 30),
    ]
    epub_path = _build_epub_with_layout(
        tmp_path / "divider_parts.epub",
        title="Divider Parts Book",
        sections=sections,
        spine_indices=[0, 1, 2, 3, 4, 5],
        ncx_indices=[0, 1, 2, 3, 4, 5],
    )

    out = tmp_path / "out.md"
    result = convert_epub_to_markdown(epub_path, out)
    text = out.read_text()

    # Part pages disappear entirely
    assert "# Part — Part One" not in text
    assert "# Part — Part Two" not in text
    assert "Chapter 1 — Part" not in text  # never re-classified as chapter

    # Real chapters number from 1 globally, no shift from Part divider
    assert "# Chapter 1 — Chapter 1: Dreams of Destiny" in text
    assert "# Chapter 2 — Chapter 2: Decisions" in text
    assert "# Chapter 3 — Chapter 3: Master System" in text
    assert result.chapter_count == 3


def test_convert_keeps_substantive_part_intros(tmp_path: Path):
    """Clear Thinking (Penguin RH 2023) packs each Part page with a 200-800
    word epigraph + framing prose before its sub-chapters. Those must be
    preserved as `# Part — <name>` so /summarize-book can include them.
    """
    sections = [
        ("Cover", "Cover image."),
        ("Part 1: The Enemies of Clear Thinking",
         "INTRO-MARKER " + ("substantive part intro prose " * 30)),  # ~91 words
        ("1.1: Thinking Badly", "BODY-OF-1-1 " * 30),
        ("1.2: The Emotion Default", "BODY-OF-1-2 " * 30),
        ("Part 2: Building Strength",
         "PART2-INTRO " + ("more substantive intro " * 30)),  # ~91 words
        ("2.1: Self-Accountability", "BODY-OF-2-1 " * 30),
    ]
    epub_path = _build_epub_with_layout(
        tmp_path / "substantive_parts.epub",
        title="Substantive Parts Book",
        sections=sections,
        spine_indices=[0, 1, 2, 3, 4, 5],
        ncx_indices=[0, 1, 2, 3, 4, 5],
    )

    out = tmp_path / "out.md"
    result = convert_epub_to_markdown(epub_path, out)
    text = out.read_text()

    # Part headings kept as their own section type
    assert "# Part — Part 1: The Enemies of Clear Thinking" in text
    assert "# Part — Part 2: Building Strength" in text

    # Substantive intro body preserved
    p1 = text.index("# Part — Part 1: The Enemies of Clear Thinking")
    ch1 = text.index("BODY-OF-1-1")
    assert "INTRO-MARKER" in text[p1:ch1]

    # Sub-chapters get sequential global numbers, no shift from Parts
    assert "# Chapter 1 — 1.1: Thinking Badly" in text
    assert "# Chapter 2 — 1.2: The Emotion Default" in text
    assert "# Chapter 3 — 2.1: Self-Accountability" in text
    assert result.chapter_count == 3


def test_convert_pages_drops_divider_only_parts_and_keeps_substantive(tmp_path: Path):
    """The Pages-EPUB code path (used for Apple Pages-generated EPUBs like
    the Penguin RH 2023 Clear Thinking) must apply the same Part rules as
    the standard epub2md path.
    """
    import zipfile
    from tests.conftest import (
        CONTAINER_XML, CONTENT_OPF_TEMPLATE, NCX_TEMPLATE,
        NAV_POINT_TEMPLATE, MIMETYPE,
    )

    pages_html_template = """<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{title}</title></head>
<body><div class="body" style="white-space:pre-wrap;">
<h1 class="p42"><span class="c1">{title}</span></h1>
<p class="p1"><span class="c1">{body}</span></p>
</div></body></html>"""

    sections = [
        ("Cover", "Cover content"),
        ("Part 1. Enemies", "DIVIDER ONLY"),                              # 2 words
        ("1.1: Thinking Badly", "BODY-OF-1-1 " * 30),
        ("Part 2. Building Strength",
         "INTRO2-MARKER " + ("substantive intro words " * 30)),           # ~91 words
        ("2.1: Self-Accountability", "BODY-OF-2-1 " * 30),
    ]

    manifest_items, spine_items, nav_points, html_files = [], [], [], {}
    for i, (label, body) in enumerate(sections, start=1):
        item_id = f"s{i}"
        href = f"section-{i}.xhtml"
        manifest_items.append(f'    <item id="{item_id}" href="{href}" media-type="application/xhtml+xml"/>')
        spine_items.append(f'    <itemref idref="{item_id}"/>')
        nav_points.append(NAV_POINT_TEMPLATE.format(id=item_id, order=i, label=label, src=href))
        html_files[href] = pages_html_template.format(title=label, body=body)

    extra_metadata = '    <meta name="generator" content="Pages Publishing macOS v1.0"/>'
    content_opf = CONTENT_OPF_TEMPLATE.format(
        title="Pages Parts Book", author="A", year="2024", title_slug="pages-parts-book",
        manifest_items="\n".join(manifest_items),
        spine_items="\n".join(spine_items),
        extra_metadata=extra_metadata,
    )
    ncx_xml = NCX_TEMPLATE.format(title="Pages Parts Book", nav_points="\n".join(nav_points))

    epub_path = tmp_path / "pages_parts.epub"
    with zipfile.ZipFile(epub_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/toc.ncx", ncx_xml)
        for href, html in html_files.items():
            zf.writestr(f"OEBPS/{href}", html)

    out = tmp_path / "out.md"
    result = convert_epub_to_markdown(epub_path, out)
    text = out.read_text()

    # Part 1 was a 2-word divider → dropped
    assert "# Part — Part 1. Enemies" not in text
    # Part 2 had a substantive intro → kept
    assert "# Part — Part 2. Building Strength" in text
    assert "INTRO2-MARKER" in text
    # Sub-chapters number sequentially without absorbing Part slots
    assert "# Chapter 1 — 1.1: Thinking Badly" in text
    assert "# Chapter 2 — 2.1: Self-Accountability" in text
    assert result.chapter_count == 2


def test_epub2md_skip_offset_compensates_when_trailing_skip_also_present(tmp_path: Path):
    """Regression: Blue Ocean Strategy (HBR 2015) drops BOTH a leading
    titlepage at OPF root AND a trailing cover image — total diff between
    manifest XHTML count and emitted .md count is 2, not 1. The earlier
    `diff != 1 → 0` short-circuit silently misaligned every body. Detection
    of the leading skip must be independent of the total diff.
    """
    from book_llm_wiki.convert.epub import _epub2md_skip_offset

    section_dir = tmp_path / "sections"
    section_dir.mkdir()

    # Manifest has 5 XHTML; epub2md produced 3 (dropped manifest[0]
    # titlepage AND manifest[4] cover.html → diff of 2). Only the leading
    # skip shifts numbering of the 3 emitted bodies, so skip_offset == 1.
    manifest = [
        "Text/titlepage.xhtml",     # at OPF root → leading skip
        "Text/copyright.xhtml",
        "Text/preface.xhtml",
        "Text/chapter1.xhtml",
        "Text/cover.xhtml",         # trailing skip; not at index 0
    ]
    for i, name in enumerate(["copyright", "preface", "chapter1"], start=1):
        (section_dir / f"{i:02d}-{name}.md").write_text(f"body of {name}")

    assert _epub2md_skip_offset(section_dir, manifest) == 1


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

    # Foreword is now a Preamble (summarized but not consuming a chapter
    # number), so book chapters number from 1 directly.
    fw = text.index("# Preamble — Foreword by James Clear")
    ch1 = text.index("# Chapter 1 — Chapter 1: First")
    ch2 = text.index("# Chapter 2 — Chapter 2: Second")
    ch3 = text.index("# Chapter 3 — Chapter 3: Third")
    assert "FOREWORD-MARKER" in text[fw:ch1]
    assert "BODY-OF-FIRST" in text[ch1:ch2]
    assert "BODY-OF-SECOND" in text[ch2:ch3]
    assert "BODY-OF-THIRD" in text[ch3:]


from book_llm_wiki.convert.epub import _section_mode_chapters_look_empty


def test_section_mode_chapters_look_empty_triggers_on_wrapper_only_chapters():
    parts = [
        "# Front Matter — Cover\n\nCover image.\n",
        "# Chapter 1 — One\n\n[link-back-to-toc]\n",
        "# Chapter 2 — Two\n\n[link-back-to-toc]\n",
        "# Chapter 3 — Three\n\n[link-back-to-toc]\n",
    ]
    assert _section_mode_chapters_look_empty(parts) is True


def test_section_mode_chapters_look_empty_does_not_trigger_on_healthy_chapters():
    parts = [
        "# Front Matter — Cover\n\nCover image.\n",
        "# Chapter 1 — One\n\n" + "real chapter content " * 100,
        "# Chapter 2 — Two\n\n" + "real chapter content " * 100,
        "# Chapter 3 — Three\n\n" + "real chapter content " * 100,
    ]
    assert _section_mode_chapters_look_empty(parts) is False


def test_section_mode_chapters_look_empty_skips_when_too_few_chapters():
    # Two chapters, both empty — below the 3-chapter floor that protects
    # against false-positives on legitimately short interlude books.
    parts = [
        "# Chapter 1 — One\n\n[link-back]\n",
        "# Chapter 2 — Two\n\n[link-back]\n",
    ]
    assert _section_mode_chapters_look_empty(parts) is False


def test_section_mode_chapters_look_empty_tolerates_one_short_chapter():
    # One legitimately short interlude shouldn't drag a healthy book into
    # the fallback path.
    parts = [
        "# Chapter 1 — One\n\n" + "real " * 200,
        "# Chapter 2 — Two\n\n[wrapper]\n",
        "# Chapter 3 — Three\n\n" + "real " * 200,
        "# Chapter 4 — Four\n\n" + "real " * 200,
    ]
    assert _section_mode_chapters_look_empty(parts) is False


def _build_calibre_split_spine_epub(out_path: Path) -> Path:
    """Build an EPUB that mimics the Calibre-pre-split-spine pattern.

    Wrapper xhtml files carry just the chapter title (10-word body, the
    sort of "see also: contents" link-back text Calibre emits when it
    splits a chapter across multiple xhtml files). Body xhtml files carry
    the actual chapter prose but no <h1>. NCX points only at the
    wrappers — exactly what real HarperCollins/Anna's-Archive retail
    EPUBs do for the chapters.
    """
    import zipfile
    from tests.conftest import (
        CONTAINER_XML, CONTENT_OPF_TEMPLATE, NCX_TEMPLATE,
        NAV_POINT_TEMPLATE, HTML_TEMPLATE, MIMETYPE,
    )

    BODY_HTML_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{title}</title></head>
<body>
<p>{body}</p>
</body>
</html>
"""

    sections = [
        ("Cover",                   "Cover image.",                     True,  False),
        ("Chapter One Origins",     "[Chapter One Origins](#anchor)",   True,  True),
        ("origins-body",            "ORIGINS-BODY " * 200,              False, False),
        ("Chapter Two Growth",      "[Chapter Two Growth](#anchor)",    True,  True),
        ("growth-body",             "GROWTH-BODY " * 200,               False, False),
        ("Chapter Three Reflection","[Chapter Three Reflection](#anchor)", True, True),
        ("reflection-body",         "REFLECTION-BODY " * 200,           False, False),
        ("Notes",                   "Reference notes.",                 True,  False),
    ]

    manifest_items = []
    html_files = {}
    nav_points = []
    for i, (label, body, has_h1, in_ncx) in enumerate(sections, start=1):
        item_id = f"s{i}"
        href = f"section-{i}.xhtml"
        manifest_items.append(
            f'    <item id="{item_id}" href="{href}" media-type="application/xhtml+xml"/>'
        )
        template = HTML_TEMPLATE if has_h1 else BODY_HTML_TEMPLATE
        html_files[href] = template.format(title=label, body=body)
        if in_ncx:
            nav_points.append(NAV_POINT_TEMPLATE.format(
                id=f"nav{i}", order=len(nav_points) + 1, label=label, src=href
            ))

    spine_items = [f'    <itemref idref="s{i + 1}"/>' for i in range(len(sections))]

    content_opf = CONTENT_OPF_TEMPLATE.format(
        title="Calibre Split Book",
        author="Test Author",
        year="2024",
        title_slug="calibre-split-book",
        manifest_items="\n".join(manifest_items),
        spine_items="\n".join(spine_items),
        extra_metadata="",
    )
    ncx_xml = NCX_TEMPLATE.format(title="Calibre Split Book", nav_points="\n".join(nav_points))

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/toc.ncx", ncx_xml)
        for href, html in html_files.items():
            zf.writestr(f"OEBPS/{href}", html)
    return out_path


def test_convert_falls_back_to_merge_mode_when_chapter_bodies_are_split(tmp_path: Path):
    """Regression: HarperCollins/Anna's-Archive Calibre-processed EPUBs put
    the chapter body in `_split_NNN.html` files NOT referenced in the NCX.
    Section-mode reads only the wrapper file under each NCX entry, leaving
    every chapter's body near-empty. The fallback should kick in and
    recover full chapter bodies via merge mode.
    """
    epub_path = _build_calibre_split_spine_epub(tmp_path / "calibre_split.epub")
    out = tmp_path / "out.md"

    result = convert_epub_to_markdown(epub_path, out)

    assert result.chapter_count == 3
    assert result.conversion_quality == "high"
    assert result.mode == "structured"

    text = out.read_text()
    # Word-numbered chapter titles must have been digit-converted in fallback.
    ch1 = text.index("# Chapter 1 — Origins")
    ch2 = text.index("# Chapter 2 — Growth")
    ch3 = text.index("# Chapter 3 — Reflection")
    # Merge mode pulls in body content that section mode missed.
    assert "ORIGINS-BODY" in text[ch1:ch2]
    assert "GROWTH-BODY" in text[ch2:ch3]
    assert "REFLECTION-BODY" in text[ch3:]


def _build_kobo_span_epub(out_path: Path) -> Path:
    """Build an EPUB whose chapter bodies wrap every text token in inline
    ``<span class="koboSpan">`` elements.

    Mirrors the structure of Simon & Schuster trade-nonfiction distributions
    (real example: Tiago Forte, *The PARA Method*, Atria 2023). The koboSpan
    style block is injected into each chapter ``<head>``, and body prose is
    fragmented across many inline spans — the pattern epub2md silently drops.
    """
    import zipfile
    from tests.conftest import (
        CONTAINER_XML, CONTENT_OPF_TEMPLATE, NCX_TEMPLATE,
        NAV_POINT_TEMPLATE, MIMETYPE,
    )

    kobo_html_template = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
<title>{title}</title>
<style type="text/css" id="koboSpanStyle">.koboSpan {{ -webkit-text-combine: inherit; }}</style>
</head>
<body>
<section role="doc-chapter">
<h2><span class="koboSpan" id="kobo.1.1">{title}</span></h2>
<p><span class="koboSpan" id="kobo.2.1">{body}</span></p>
</section>
</body></html>"""

    sections = [
        ("Cover", "Cover content"),
        ("Chapter 1: First", "KOBO-BODY-FIRST " * 30),
        ("Chapter 2: Second", "KOBO-BODY-SECOND " * 30),
    ]

    manifest_items = []
    spine_items = []
    nav_points = []
    html_files = {}
    for i, (label, body) in enumerate(sections, start=1):
        item_id = f"s{i}"
        href = f"section-{i}.xhtml"
        manifest_items.append(
            f'    <item id="{item_id}" href="{href}" media-type="application/xhtml+xml"/>'
        )
        spine_items.append(f'    <itemref idref="{item_id}"/>')
        nav_points.append(NAV_POINT_TEMPLATE.format(id=item_id, order=i, label=label, src=href))
        html_files[href] = kobo_html_template.format(title=label, body=body)

    content_opf = CONTENT_OPF_TEMPLATE.format(
        title="Kobo Span Book", author="A", year="2024", title_slug="kobo-span-book",
        manifest_items="\n".join(manifest_items),
        spine_items="\n".join(spine_items),
        extra_metadata="",
    )
    ncx_xml = NCX_TEMPLATE.format(title="Kobo Span Book", nav_points="\n".join(nav_points))

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/toc.ncx", ncx_xml)
        for href, html in html_files.items():
            zf.writestr(f"OEBPS/{href}", html)
    return out_path


def test_is_kobo_span_epub_detects_kobo_styled_xhtml(tmp_path: Path):
    """`is_kobo_span_epub` must fire on EPUBs whose body text is wrapped in
    ``<span class="koboSpan">`` (the Simon & Schuster / Kobo distribution
    pattern that epub2md silently drops)."""
    from book_llm_wiki.convert.epub import is_kobo_span_epub
    epub_path = _build_kobo_span_epub(tmp_path / "kobo.epub")
    assert is_kobo_span_epub(epub_path)


def test_is_kobo_span_epub_not_falsely_detected(normal_epub: Path):
    """A normal publisher EPUB without koboSpan markers must NOT be flagged."""
    from book_llm_wiki.convert.epub import is_kobo_span_epub
    assert not is_kobo_span_epub(normal_epub)


def test_convert_kobo_span_epub_extracts_body_via_pages_fallback(tmp_path: Path):
    """End-to-end: a kobo-styled EPUB must route through the direct-XHTML
    extraction path and recover real chapter bodies, not just the headings.

    Regression: before the koboSpan detector was added, this EPUB family
    silently produced ~37-byte chapter files (just the title repeated) under
    both epub2md section-mode and merge-mode. Real-case repro was Tiago
    Forte's *The PARA Method* (Atria, 2023).
    """
    epub_path = _build_kobo_span_epub(tmp_path / "kobo.epub")
    out = tmp_path / "out.md"
    result = convert_epub_to_markdown(epub_path, out)

    text = out.read_text()
    assert "# Front Matter — Cover" in text
    assert "# Chapter 1 — Chapter 1: First" in text
    assert "# Chapter 2 — Chapter 2: Second" in text
    # Body text wrapped in koboSpan tags must be preserved.
    assert "KOBO-BODY-FIRST" in text
    assert "KOBO-BODY-SECOND" in text
    assert result.chapter_count == 2
    assert result.conversion_quality == "high"
    assert result.mode == "structured"


def _build_ncx_points_to_stub_epub(out_path: Path) -> Path:
    """Build an EPUB whose NCX entries point at small "Action Exercises" stub
    files while substantially larger body files exist unreferenced in the
    same manifest.

    Mirrors the Brian Tracy *The Psychology of Selling* (Thomas Nelson 2004)
    structure: each chapter has two manifest XHTML files — a stub and a body.
    The NCX targets the stubs (which contain only a numbered exercise list,
    too short to be a real chapter but too long to trip the existing empty-
    chapter detector's 25-word floor). The body files are in the manifest
    and spine but never referenced from the NCX.
    """
    import zipfile
    from tests.conftest import (
        CONTAINER_XML, CONTENT_OPF_TEMPLATE, NCX_TEMPLATE,
        NAV_POINT_TEMPLATE, MIMETYPE,
    )

    body_template = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{title}</title></head>
<body>
<h1>{title}</h1>
<p>{body}</p>
</body></html>"""

    stub_template = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{title} Action Exercises</title></head>
<body>
<p>ACTION EXERCISES</p>
<p>1. Decide today to apply this lesson immediately.</p>
<p>2. Visualize yourself implementing this approach successfully.</p>
<p>3. Write down three specific actions you will take this week.</p>
<p>4. Identify one obstacle and plan how to overcome it.</p>
<p>5. Share your commitment with a trusted colleague today.</p>
</body></html>"""

    # Three chapters, each with a body file (large) and a stub file (small).
    # NCX targets the stubs; body files are unreferenced.
    chapters = [
        ("Chapter 1: First", "BODY-OF-FIRST " * 800),
        ("Chapter 2: Second", "BODY-OF-SECOND " * 800),
        ("Chapter 3: Third", "BODY-OF-THIRD " * 800),
    ]

    manifest_items = []
    spine_items = []
    nav_points = []
    html_files = {}

    item_idx = 0
    for ch_idx, (title, body) in enumerate(chapters, start=1):
        # Body file: large, not referenced by NCX
        item_idx += 1
        body_id = f"s{item_idx}"
        body_href = f"chapter-{ch_idx}-body.xhtml"
        manifest_items.append(
            f'    <item id="{body_id}" href="{body_href}" media-type="application/xhtml+xml"/>'
        )
        spine_items.append(f'    <itemref idref="{body_id}"/>')
        html_files[body_href] = body_template.format(title=title, body=body)

        # Stub file: small, IS referenced by NCX
        item_idx += 1
        stub_id = f"s{item_idx}"
        stub_href = f"chapter-{ch_idx}-stub.xhtml"
        manifest_items.append(
            f'    <item id="{stub_id}" href="{stub_href}" media-type="application/xhtml+xml"/>'
        )
        spine_items.append(f'    <itemref idref="{stub_id}"/>')
        html_files[stub_href] = stub_template.format(title=title)

        # NCX points at the STUB, not the body
        nav_points.append(NAV_POINT_TEMPLATE.format(
            id=stub_id, order=ch_idx, label=title, src=stub_href,
        ))

    content_opf = CONTENT_OPF_TEMPLATE.format(
        title="NCX Stub Book", author="A", year="2024", title_slug="ncx-stub-book",
        manifest_items="\n".join(manifest_items),
        spine_items="\n".join(spine_items),
        extra_metadata="",
    )
    ncx_xml = NCX_TEMPLATE.format(title="NCX Stub Book", nav_points="\n".join(nav_points))

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/toc.ncx", ncx_xml)
        for href, html in html_files.items():
            zf.writestr(f"OEBPS/{href}", html)
    return out_path


def test_section_mode_routed_to_stubs_detects_ncx_stub_pattern(tmp_path: Path):
    """``_section_mode_routed_to_stubs`` must fire on EPUBs where the NCX
    targets small stub XHTML files while substantially larger body files
    exist unreferenced in the same manifest (Tracy pattern)."""
    from book_llm_wiki.convert.epub import (
        _section_mode_routed_to_stubs,
        _xhtml_manifest_hrefs,
        epub_structure,
    )
    from urllib.parse import unquote

    epub_path = _build_ncx_points_to_stub_epub(tmp_path / "ncx_stub.epub")
    manifest_hrefs = _xhtml_manifest_hrefs(epub_path)
    pos_by_href = {h: i for i, h in enumerate(manifest_hrefs, start=1)}

    structure = epub_structure(epub_path)
    deduped_structure = []
    seen = set()
    for s in structure:
        bare = unquote(s["src"].split("#", 1)[0])
        position = pos_by_href.get(bare)
        if position is None or position in seen:
            continue
        seen.add(position)
        deduped_structure.append({**s, "_position": position})

    assert _section_mode_routed_to_stubs(epub_path, deduped_structure, manifest_hrefs)


def test_section_mode_routed_to_stubs_not_falsely_detected(normal_epub: Path):
    """A normal publisher EPUB where every NCX entry targets a substantive
    body file must NOT be flagged as NCX-points-to-stub."""
    from book_llm_wiki.convert.epub import (
        _section_mode_routed_to_stubs,
        _xhtml_manifest_hrefs,
        epub_structure,
    )
    from urllib.parse import unquote

    manifest_hrefs = _xhtml_manifest_hrefs(normal_epub)
    pos_by_href = {h: i for i, h in enumerate(manifest_hrefs, start=1)}

    structure = epub_structure(normal_epub)
    deduped_structure = []
    seen = set()
    for s in structure:
        bare = unquote(s["src"].split("#", 1)[0])
        position = pos_by_href.get(bare)
        if position is None or position in seen:
            continue
        seen.add(position)
        deduped_structure.append({**s, "_position": position})

    assert not _section_mode_routed_to_stubs(normal_epub, deduped_structure, manifest_hrefs)


def test_convert_ncx_stub_epub_recovers_body_via_spine_extraction(tmp_path: Path):
    """End-to-end: a Tracy-style EPUB (NCX points at small action-exercise
    stubs while larger body files exist unreferenced in the same manifest)
    must route through ``_convert_via_spine_body_extraction`` and recover the
    actual body content rather than emitting only the stubs.

    Regression: before the NCX-points-to-stub detector was added, this EPUB
    family silently produced ~250-byte chapter sections (the action-exercise
    stub content only) under standard section-mode conversion. Real-case
    repro was Brian Tracy's *The Psychology of Selling* (Thomas Nelson 2004).
    """
    epub_path = _build_ncx_points_to_stub_epub(tmp_path / "ncx_stub.epub")
    out = tmp_path / "out.md"
    result = convert_epub_to_markdown(epub_path, out)

    text = out.read_text()
    # Body content from the unreferenced files must be present.
    assert "BODY-OF-FIRST" in text
    assert "BODY-OF-SECOND" in text
    assert "BODY-OF-THIRD" in text
    # And the stub-file content must NOT dominate (the spine-extraction path
    # filters out below-floor stubs entirely).
    # Three chapters were emitted, one per body file.
    assert result.chapter_count == 3
    assert result.conversion_quality == "high"
    assert result.mode == "structured"


def _build_degenerate_ncx_wiley_epub(out_path: Path) -> Path:
    """Build an EPUB whose NCX is degenerate (one stub navPoint pointing at
    cover.xml) while the spine holds the entire book in Wiley's
    class-tagged XHTML format.

    Mirrors Michael Port's *Book Yourself Solid* (John Wiley & Sons 2010,
    Sigil-built): toc.ncx has exactly one ``<navPoint>`` pointing at
    ``cover.xml`` while the manifest holds 38 substantive XHTML files.
    Section-mode extracts only the cover and silently drops the rest.

    Includes a Chapter16-with-sub-files (16a/b/c) pattern to exercise the
    chapter-sub-file merge path.
    """
    import zipfile
    from tests.conftest import (
        CONTAINER_XML, CONTENT_OPF_TEMPLATE, NCX_TEMPLATE,
        NAV_POINT_TEMPLATE, MIMETYPE,
    )

    # Minimal cover (under stub byte threshold so the stub-filter drops it).
    cover_xml = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Book Yourself Solid</title></head>
<body><div><p>Book Yourself Solid</p></div></body></html>"""

    chapter_template = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Wiley Test Book</title></head>
<body>
<div class="story">
<p class="chaptertitle">CHAPTER {num}</p>
<p class="chaptertitle">{title}</p>
<p class="para">{body}</p>
</div>
</body></html>"""

    chapter_subfile_template = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Wiley Test Book</title></head>
<body>
<div class="story">
<p class="chaptertitle">PART {part}</p>
<p class="chaptertitle">{title}</p>
<p class="para">{body}</p>
</div>
</body></html>"""

    part_template = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Wiley Test Book</title></head>
<body>
<div class="story">
<p class="parttitle">Module {module}</p>
<p class="parttitle">{title}</p>
<p class="paraaftertitle">{body}</p>
</div>
</body></html>"""

    foreword_xml = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Wiley Test Book</title></head>
<body><div class="story">
<p class="mattertitle">Foreword</p>
<p class="para">""" + ("FOREWORD-BODY " * 800) + """</p>
</div></body></html>"""

    preface_xml = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Wiley Test Book</title></head>
<body><div class="story">
<p class="prefacetitle">Preface</p>
<p class="paraaftertitle">""" + ("PREFACE-BODY " * 800) + """</p>
</div></body></html>"""

    final_thoughts_xml = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Wiley Test Book</title></head>
<body><div class="story">
<p class="mattertitle">Final Thoughts</p>
<p class="para">""" + ("FINAL-THOUGHTS-BODY " * 800) + """</p>
</div></body></html>"""

    # Filter file (acknowledgments, must be dropped by filename mapping)
    acknowledgments_xml = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Wiley Test Book</title></head>
<body><div class="story">
<p class="mattertitle">Acknowledgments</p>
<p class="para">""" + ("ACK-BODY " * 200) + """</p>
</div></body></html>"""

    # Files in the order the spine should reference them
    spine_files = [
        ("cover.xml", cover_xml),
        ("acknowledgments.html", acknowledgments_xml),
        ("foreword.html", foreword_xml),
        ("Preface.html", preface_xml),
        ("Part01.html", part_template.format(
            module="ONE", title="Foundation", body="MODULE-1-INTRO " * 800,
        )),
        ("Chapter01.html", chapter_template.format(
            num="1", title="The First Principle", body="CH1-BODY " * 1500,
        )),
        ("Chapter02.html", chapter_template.format(
            num="2", title="The Second Principle", body="CH2-BODY " * 1500,
        )),
        ("Chapter16.html", chapter_template.format(
            num="16", title="The Long Chapter", body="CH16-INTRO " * 1500,
        )),
        ("Chapter16a.html", chapter_subfile_template.format(
            part="1", title="Part One Detail", body="CH16-SUB-A " * 1500,
        )),
        ("Chapter16b.html", chapter_subfile_template.format(
            part="2", title="Part Two Detail", body="CH16-SUB-B " * 1500,
        )),
        ("FinalThoughts.html", final_thoughts_xml),
    ]

    manifest_items = []
    spine_items = []
    html_files = {}
    for idx, (href, html) in enumerate(spine_files, start=1):
        item_id = f"item{idx}"
        manifest_items.append(
            f'    <item id="{item_id}" href="{href}" media-type="application/xhtml+xml"/>'
        )
        spine_items.append(f'    <itemref idref="{item_id}"/>')
        html_files[href] = html

    # Degenerate NCX: ONE navPoint pointing at cover.xml
    nav_point = NAV_POINT_TEMPLATE.format(
        id="item1", order=1, label="Start", src="cover.xml",
    )

    content_opf = CONTENT_OPF_TEMPLATE.format(
        title="Wiley Test Book", author="Test", year="2010",
        title_slug="wiley-test",
        manifest_items="\n".join(manifest_items),
        spine_items="\n".join(spine_items),
        extra_metadata="",
    )
    ncx_xml = NCX_TEMPLATE.format(title="Wiley Test Book", nav_points=nav_point)

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/toc.ncx", ncx_xml)
        for href, html in html_files.items():
            zf.writestr(f"OEBPS/{href}", html)
    return out_path


def test_section_mode_ncx_is_degenerate_detects_single_navpoint_pattern(tmp_path: Path):
    """``_section_mode_ncx_is_degenerate`` must fire on EPUBs whose NCX has
    a single navPoint while the spine holds many substantive XHTML files
    (BYS / Wiley pattern)."""
    from book_llm_wiki.convert.epub import (
        _section_mode_ncx_is_degenerate,
        _xhtml_manifest_hrefs,
        epub_structure,
    )
    from urllib.parse import unquote

    epub_path = _build_degenerate_ncx_wiley_epub(tmp_path / "wiley.epub")
    manifest_hrefs = _xhtml_manifest_hrefs(epub_path)
    pos_by_href = {h: i for i, h in enumerate(manifest_hrefs, start=1)}

    structure = epub_structure(epub_path)
    deduped_structure = []
    seen = set()
    for s in structure:
        bare = unquote(s["src"].split("#", 1)[0])
        position = pos_by_href.get(bare)
        if position is None or position in seen:
            continue
        seen.add(position)
        deduped_structure.append({**s, "_position": position})

    assert _section_mode_ncx_is_degenerate(epub_path, deduped_structure, manifest_hrefs)


def test_section_mode_ncx_is_degenerate_not_falsely_detected(normal_epub: Path):
    """A normal publisher EPUB with a populated NCX must NOT be flagged as
    degenerate."""
    from book_llm_wiki.convert.epub import (
        _section_mode_ncx_is_degenerate,
        _xhtml_manifest_hrefs,
        epub_structure,
    )
    from urllib.parse import unquote

    manifest_hrefs = _xhtml_manifest_hrefs(normal_epub)
    pos_by_href = {h: i for i, h in enumerate(manifest_hrefs, start=1)}

    structure = epub_structure(normal_epub)
    deduped_structure = []
    seen = set()
    for s in structure:
        bare = unquote(s["src"].split("#", 1)[0])
        position = pos_by_href.get(bare)
        if position is None or position in seen:
            continue
        seen.add(position)
        deduped_structure.append({**s, "_position": position})

    assert not _section_mode_ncx_is_degenerate(normal_epub, deduped_structure, manifest_hrefs)


def test_convert_degenerate_ncx_wiley_epub_recovers_full_spine(tmp_path: Path):
    """End-to-end: a Wiley-pattern EPUB (degenerate NCX with one navPoint
    pointing at cover.xml while the spine holds the full book) must route
    through ``_convert_via_spine_body_extraction`` and recover all the
    spine bodies, classify them via Wiley CSS-class titles + filename
    fallbacks, and merge Chapter sub-files (Chapter16a/b/c) into the
    preceding Chapter section.

    Regression: before the degenerate-NCX detector was added, this EPUB
    family produced exactly one ``# Chapter 1 — Start`` heading with the
    one-sentence cover content; the rest of the book was silently dropped.
    Real-case repro was Michael Port's *Book Yourself Solid* (Wiley 2010).
    """
    epub_path = _build_degenerate_ncx_wiley_epub(tmp_path / "wiley.epub")
    out = tmp_path / "out.md"
    result = convert_epub_to_markdown(epub_path, out)

    text = out.read_text()

    # All substantive bodies must be present.
    assert "FOREWORD-BODY" in text
    assert "PREFACE-BODY" in text
    assert "MODULE-1-INTRO" in text
    assert "CH1-BODY" in text
    assert "CH2-BODY" in text
    assert "CH16-INTRO" in text
    assert "CH16-SUB-A" in text
    assert "CH16-SUB-B" in text
    assert "FINAL-THOUGHTS-BODY" in text

    # Filter-list filename (acknowledgments) must be dropped entirely.
    assert "ACK-BODY" not in text

    # Wiley CSS-class titles must be picked up (not the page-header
    # "Wiley Test Book" running title).
    assert "# Preamble — Foreword" in text
    assert "# Preamble — Preface" in text
    assert "# Part — Module ONE: Foundation" in text
    assert "# Chapter 1 — The First Principle" in text
    assert "# Chapter 2 — The Second Principle" in text
    assert "# Chapter 3 — The Long Chapter" in text
    assert "# Back Matter — Final Thoughts" in text

    # Chapter sub-files (16a / 16b) must be merged into the preceding
    # Chapter and NOT emitted as separate Chapter sections — there should
    # be exactly 3 chapter headings (Ch01, Ch02, Ch16).
    assert result.chapter_count == 3
    assert text.count("# Chapter ") == 3

    # The merged sub-file content must appear AFTER the Ch16 intro, not
    # before it (sub-file ordering preserves spine order).
    ch16_pos = text.index("# Chapter 3 — The Long Chapter")
    sub_a_pos = text.index("CH16-SUB-A")
    sub_b_pos = text.index("CH16-SUB-B")
    assert ch16_pos < sub_a_pos < sub_b_pos

    assert result.conversion_quality == "high"
    assert result.mode == "structured"


def test_extract_publisher_class_title_prefers_real_title_over_label():
    """Wiley chapters typically have two ``<p class="chaptertitle">``
    paragraphs — a label ("CHAPTER 1") and the real title. The extractor
    must prefer the real title."""
    from book_llm_wiki.convert.epub import _extract_publisher_class_title

    xhtml = """<html><body>
    <p class="chaptertitle">CHAPTER 1</p>
    <p class="chaptertitle">The Red Velvet Rope Policy</p>
    <p class="para">Body text here.</p>
    </body></html>"""

    result = _extract_publisher_class_title(xhtml)
    assert result == ("chapter", "The Red Velvet Rope Policy")


def test_extract_publisher_class_title_falls_back_to_label_when_only_label():
    """When only a label paragraph is present, the extractor returns it
    rather than failing — the legacy classify_section path will then
    derive a sensible heading from it."""
    from book_llm_wiki.convert.epub import _extract_publisher_class_title

    xhtml = """<html><body>
    <p class="chaptertitle">CHAPTER 1</p>
    <p class="para">Body text here.</p>
    </body></html>"""

    result = _extract_publisher_class_title(xhtml)
    assert result == ("chapter", "CHAPTER 1")


def test_extract_publisher_class_title_returns_none_for_unmarked_xhtml():
    """A normal XHTML body without publisher class markup returns None,
    so the legacy fallback path runs."""
    from book_llm_wiki.convert.epub import _extract_publisher_class_title

    xhtml = """<html><body>
    <h1>Chapter 1: Origins</h1>
    <p>Body text here.</p>
    </body></html>"""

    assert _extract_publisher_class_title(xhtml) is None


def test_chapter_subfile_match_recognizes_wiley_pattern():
    """``_chapter_subfile_match`` recognizes Chapter16a.html-style hrefs
    and returns (chapter_num, suffix)."""
    from book_llm_wiki.convert.epub import _chapter_subfile_match

    assert _chapter_subfile_match("Text/Chapter16a.html") == (16, "a")
    assert _chapter_subfile_match("Chapter01b.xhtml") == (1, "b")
    assert _chapter_subfile_match("Chapter16.html") is None
    assert _chapter_subfile_match("Foreword.html") is None
    assert _chapter_subfile_match("chapter-1-body.xhtml") is None  # the Tracy fixture pattern


def test_filename_section_class_classifies_known_stems():
    """``_filename_section_class`` returns the right (section_class, title)
    tuple for known filename stems."""
    from book_llm_wiki.convert.epub import _filename_section_class

    assert _filename_section_class("foreword.html") == ("preamble", "Foreword")
    assert _filename_section_class("Text/AuthorsNote.html") == ("preamble", "Author's Note")
    assert _filename_section_class("FinalThoughts.html") == ("back", "Final Thoughts")
    assert _filename_section_class("acknowledgments.html") == ("filter", "")
    assert _filename_section_class("cover.xml") == ("filter", "")
    # Stems not in the map return None (the publisher-class or fallback
    # path will classify).
    assert _filename_section_class("Chapter01.html") is None
    assert _filename_section_class("Part01.html") is None
