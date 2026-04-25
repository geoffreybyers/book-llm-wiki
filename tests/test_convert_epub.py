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
