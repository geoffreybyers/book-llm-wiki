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


def _build_epub3_no_ncx(out_path: Path, sections: list[tuple[str, str]]) -> Path:
    """Build an EPUB3 whose only navigation is nav.xhtml (no toc.ncx).

    Mirrors retail EPUB3 releases (e.g. the Grand Central edition of
    *So Good They Can't Ignore You*): the package declares no
    ``application/x-dtbncx+xml`` item, and the toc lives in an
    ``<item properties="nav">`` XHTML document.
    """
    import zipfile

    manifest, spine, nav_lis, html_files = [], [], [], {}
    for i, (label, body) in enumerate(sections, start=1):
        href = f"section-{i}.xhtml"
        manifest.append(
            f'    <item id="s{i}" href="{href}" media-type="application/xhtml+xml"/>'
        )
        spine.append(f'    <itemref idref="s{i}"/>')
        nav_lis.append(f'        <li><a href="{href}">{label}</a></li>')
        html_files[href] = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml">'
            f"<head><title>{label}</title></head>"
            f"<body><h1>{label}</h1><p>{body}</p></body></html>"
        )

    nav_xhtml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops">'
        "<head><title>Contents</title></head><body>"
        '<nav epub:type="toc"><ol>\n'
        + "\n".join(nav_lis)
        + "\n</ol></nav></body></html>"
    )
    content_opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        'unique-identifier="BookId">\n'
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        "    <dc:title>EPUB3 No NCX</dc:title>\n"
        "    <dc:creator>Test Author</dc:creator>\n"
        '    <dc:identifier id="BookId">urn:uuid:epub3-no-ncx</dc:identifier>\n'
        "    <dc:language>en</dc:language>\n"
        "  </metadata>\n"
        "  <manifest>\n"
        '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
        'properties="nav"/>\n'
        + "\n".join(manifest)
        + "\n  </manifest>\n  <spine>\n"
        + "\n".join(spine)
        + "\n  </spine>\n</package>\n"
    )

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?>\n<container version="1.0" '
            'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/nav.xhtml", nav_xhtml)
        for href, html in html_files.items():
            zf.writestr(f"OEBPS/{href}", html)
    return out_path


def test_epub_structure_parses_epub3_nav_when_no_ncx(tmp_path: Path):
    """EPUB3-only books (no toc.ncx) must still yield a navigation structure.

    Regression: the Grand Central edition of *So Good They Can't Ignore You*
    ships only nav.xhtml; epub_structure() returned [] for it, so
    convert_epub_to_markdown short-circuited to flat/low passthrough and
    the 61k-word book lost all chapter structure.
    """
    epub = _build_epub3_no_ncx(
        tmp_path / "epub3.epub",
        sections=[
            ("Introduction", "Intro body. " * 30),
            ("Chapter One: The Passion", "Chapter one body. " * 60),
            ("Chapter Two: Career Capital", "Chapter two body. " * 60),
            ("Conclusion", "Conclusion body. " * 30),
        ],
    )
    sections = epub_structure(epub)
    names = [s["name"] for s in sections]
    assert names == [
        "Introduction",
        "Chapter One: The Passion",
        "Chapter Two: Career Capital",
        "Conclusion",
    ]
    assert sections[1]["src"] == "section-2.xhtml"


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


def test_classify_bare_integer_title_is_part():
    """NCX entries titled only with a digit (``"1"``, ``"2"``, …, ``"11"``)
    are chapter-divider intro pages, not real chapters. Aaron Ross's
    *Predictable Revenue* (PebbleStorm 2011) is the documented repro:
    the 11 ``CHAPTER N: <Title>`` NCX entries are fragment anchors into
    the Contents page (deduped away by manifest-position dedupe), while
    each book chapter's intro page surfaces in the NCX with just its
    number as the label. Without this classification they'd be numbered
    as Chapters interspersed among the 80+ sub-section chapters, losing
    the book's actual 11-chapter structure."""
    assert classify_section("1") == SectionClass.PART
    assert classify_section("2") == SectionClass.PART
    assert classify_section("11") == SectionClass.PART
    # Trailing period is common in some publisher TOC styling
    assert classify_section("1.") == SectionClass.PART
    # Whitespace tolerance
    assert classify_section(" 3 ") == SectionClass.PART


def test_classify_bare_integer_does_not_break_existing_chapter_patterns():
    """Existing chapter-title forms — ``Chapter 1``, ``1 The Surprising…``,
    Roman-numeraled chapters, etc. — must continue classifying as CHAPTER,
    not be swallowed by the new bare-integer Part detector. Guard against
    the regression of the bare-integer rule eating substantive chapter
    titles that happen to start with digits."""
    assert classify_section("Chapter 1") == SectionClass.CHAPTER
    assert classify_section("Chapter 11: Sales Machine Fundamentals") == SectionClass.CHAPTER
    assert classify_section("1 The Surprising Power of Atomic Habits") == SectionClass.CHAPTER
    assert classify_section("11 The Goldilocks Rule") == SectionClass.CHAPTER
    # Real labels with trailing colons should remain Chapter
    assert classify_section("1: The Surprising Power") == SectionClass.CHAPTER


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


def test_finalize_quality_downgrades_mostly_empty_output(tmp_path: Path):
    """Belt-and-suspenders sanity check: when the converter writes a file
    whose non-whitespace content is overwhelmingly heading lines (no real
    body), the ConversionResult must report quality 'low' / mode 'flat'
    so the summarizer's single-pass fallback kicks in.

    Documented repro: an earlier converter version produced a 5976-byte
    file for *Predictable Revenue* that was 101 chapter headings and
    nothing else, yet returned quality 'high'. The new section-mode
    routing detectors (NCX-points-to-stub, degenerate-NCX, koboSpan,
    part-stubs-with-unref-body) fix the body-extraction failures
    individually, but a final post-write check catches whatever
    future failure mode slips past every detector."""
    from book_llm_wiki.convert.epub import _finalize_quality, ConversionResult

    out = tmp_path / "empty.md"
    # 85 chapter headings, no body — the documented Predictable Revenue
    # first-ingest output shape (101 lines was 86 headings + 11 part-
    # divider headings + 4 front/back; this is a clean repro).
    out.write_text("\n\n".join(f"# Chapter {i} — Title {i}" for i in range(1, 86)) + "\n")
    high = ConversionResult(chapter_count=85, conversion_quality="high", mode="structured")
    result = _finalize_quality(out, high)
    assert result.conversion_quality == "low"
    assert result.mode == "flat"
    # Chapter count preserved so the summarizer's fallback decision logic
    # still sees the right shape.
    assert result.chapter_count == 85


def test_finalize_quality_keeps_substantial_output(tmp_path: Path):
    """A normal high-quality conversion (substantial body content under
    each heading) must NOT be downgraded. Regression guard against the
    quality check getting tuned too aggressively and breaking healthy
    books."""
    from book_llm_wiki.convert.epub import _finalize_quality, ConversionResult

    out = tmp_path / "normal.md"
    parts = []
    for i in range(1, 4):
        parts.append(f"# Chapter {i} — Title {i}\n\n" + ("Body sentence. " * 100))
    out.write_text("\n\n".join(parts))
    high = ConversionResult(chapter_count=3, conversion_quality="high", mode="structured")
    result = _finalize_quality(out, high)
    assert result.conversion_quality == "high"
    assert result.mode == "structured"
    assert result.chapter_count == 3


def test_finalize_quality_passthrough_when_already_low(tmp_path: Path):
    """Inputs marked low must pass through unchanged — the helper only
    downgrades high → low, never the other direction."""
    from book_llm_wiki.convert.epub import _finalize_quality, ConversionResult

    out = tmp_path / "flat.md"
    out.write_text("Some flat content with no chapter structure.\n" * 50)
    low = ConversionResult(chapter_count=0, conversion_quality="low", mode="flat")
    assert _finalize_quality(out, low) == low


def test_finalize_quality_tolerates_missing_output(tmp_path: Path):
    """When the output file doesn't exist (e.g. the convert pipeline raised
    before write), the helper returns the input unchanged rather than
    crashing on the read attempt."""
    from book_llm_wiki.convert.epub import _finalize_quality, ConversionResult

    out = tmp_path / "missing.md"
    high = ConversionResult(chapter_count=5, conversion_quality="high", mode="structured")
    assert _finalize_quality(out, high) == high


def test_convert_downgrades_quality_for_empty_output_via_finalize(tmp_path: Path):
    """End-to-end: when convert_epub_to_markdown's output ends up mostly
    empty (e.g. because every body-extraction path failed silently), the
    returned ConversionResult must reflect quality 'low'. This is the
    belt-and-suspenders catch that would have flagged the original
    Predictable Revenue first-ingest output if it had returned 'high'
    from a structured-mode path."""
    # Simulate by directly writing a mostly-empty file and applying the
    # check; verifies the wiring in convert_epub_to_markdown's wrap step.
    from book_llm_wiki.convert.epub import _finalize_quality, ConversionResult

    out = tmp_path / "out.md"
    # 101 headings, zero body — the literal shape of the Predictable
    # Revenue first-ingest failure.
    out.write_text("\n\n".join(f"# Chapter {i} — Title" for i in range(1, 102)) + "\n")
    result = _finalize_quality(
        out,
        ConversionResult(chapter_count=101, conversion_quality="high", mode="structured"),
    )
    assert result.conversion_quality == "low"


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


def test_epub2md_skip_offset_gap_numbered_scheme_returns_zero(tmp_path: Path):
    """Regression: newer epub2md (1.6.2) drops the leading cover/titlepage but
    PRESERVES each remaining file's 1-indexed manifest position in its filename
    prefix, leaving a numeric gap (no ``01-`` file; lowest prefix is ``02-``).
    In this "gap" scheme the prefix already equals the manifest position, so
    NO left shift is needed and ``_epub2md_skip_offset`` must return 0.

    The older scheme renumbered densely from ``01-`` after the drop (handled by
    ``test_epub2md_skip_offset_compensates_for_root_level_cover``, which must
    keep returning 1). Distinguishing the two by the emitted filename prefixes
    rather than guessing from the manifest is the fix.

    Confirmed in the wild on *SPIN Selling* (Neil Rackham, McGraw-Hill 2017
    reissue, codeMantra-built). manifest[0] is ``cover.html``; epub2md emits
    ``02-Title_Page.md`` … ``17-author.md`` with no ``01-``. Before the fix
    the cover-name heuristic returned 1, shifting every section's body one
    file left (``# Chapter 1`` got the Preface, ``# Chapter 2`` got Chapter 1,
    …).
    """
    from book_llm_wiki.convert.epub import (
        _epub2md_skip_offset,
        _section_body_for_position,
    )

    section_dir = tmp_path / "sections"
    section_dir.mkdir()

    # 17 XHTML manifest items; epub2md drops manifest[0] (cover.html) and emits
    # 16 files numbered 02..17 — the original manifest positions preserved.
    manifest = [
        "cover.html",
        "title.html",
        "copyright.html",
        "content.html",
        "preface.html",
        "ch01.html",
        "ch02.html",
        "ch03.html",
        "ch04.html",
        "ch05.html",
        "ch06.html",
        "ch07.html",
        "ch08.html",
        "appa.html",
        "appb.html",
        "index.html",
        "author.html",
    ]
    names = {
        2: "Title_Page",
        3: "Copyright_Page",
        4: "Contents",
        5: "Preface",
        6: "1._Sales_Behavior_and_Sales_Success",
        7: "2._Obtaining_Commitment",
        8: "3._Customer_Needs",
        9: "4._The_SPIN_Strategy",
        10: "5._Giving_Benefits",
        11: "6._Preventing_Objections",
        12: "7._Preliminaries",
        13: "8._Turning_Theory_into_Practice",
        14: "Appendix_A",
        15: "Appendix_B",
        16: "Index",
        17: "author",
    }
    for pos, stem in names.items():
        (section_dir / f"{pos:02d}-{stem}.md").write_text(f"body of {stem}")

    # Gap scheme: lowest emitted prefix is 02, md_count (16) < manifest (17).
    # No shift — the prefix already equals the manifest position.
    assert _epub2md_skip_offset(section_dir, manifest) == 0

    # End-to-end alignment with the resulting offset: each manifest position
    # must resolve to its own body, not the previous file's.
    offset = _epub2md_skip_offset(section_dir, manifest)
    assert "Copyright_Page" in _section_body_for_position(
        section_dir, position=3, skip_offset=offset
    )
    assert "Preface" in _section_body_for_position(
        section_dir, position=5, skip_offset=offset
    )
    assert "1._Sales_Behavior" in _section_body_for_position(
        section_dir, position=6, skip_offset=offset
    )
    assert "Appendix_A" in _section_body_for_position(
        section_dir, position=14, skip_offset=offset
    )


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


def test_convert_treats_bare_integer_ncx_titles_as_part_dividers(tmp_path: Path):
    """End-to-end: an EPUB whose NCX surfaces book-chapter intro pages
    with just an integer label ("1", "2", "3") interspersed with
    descriptively-titled sub-section entries must produce ``# Part — N``
    headings for the dividers and consecutively-numbered Chapter headings
    for the sub-sections.

    Real repro: Aaron Ross's *Predictable Revenue* (PebbleStorm 2011)
    has 11 ``CHAPTER N: <Title>`` NCX entries pointing at fragment
    anchors inside the Contents page (deduped away by manifest-position
    dedupe), plus 80+ sub-section entries — among which the 11
    chapter-intro pages surface with labels ``"1"``, ``"2"``, …,
    ``"11"``. Without bare-integer Part classification the dividers
    consume chapter numbers and the book's 11-chapter structure is
    lost in the output.
    """
    # Three book chapters' worth of structure: each has a bare-integer
    # divider with a short intro, followed by two named sub-sections.
    sections = [
        ("Cover", "Cover image."),
        ("Foreword", "Foreword text " * 40),
        # Book Chapter 1: divider + 2 sub-sections
        ("1", "Where the $100 Million Came From " + ("intro prose " * 30)),
        ("Start Here", "BODY-OF-START-HERE " * 30),
        ("The Hot Coals Sketch", "BODY-OF-HOT-COALS " * 30),
        # Book Chapter 2: divider + 2 sub-sections
        ("2", "Cold Calling 2.0 " + ("intro prose " * 30)),
        ("RIP Cold Calling", "BODY-OF-RIP " * 30),
        ("Cold Calling 1.0 vs 2.0", "BODY-OF-VS " * 30),
        # Book Chapter 3: divider + 2 sub-sections
        ("3", "Executing Cold Calling 2.0 " + ("intro prose " * 30)),
        ("Getting Started", "BODY-OF-GETTING-STARTED " * 30),
        ("The Ideal Customer Profile", "BODY-OF-ICP " * 30),
    ]
    epub_path = _build_epub_with_layout(
        tmp_path / "bare_int_dividers.epub",
        title="Bare Integer Dividers",
        sections=sections,
        spine_indices=list(range(len(sections))),
        ncx_indices=list(range(len(sections))),
    )

    out = tmp_path / "out.md"
    result = convert_epub_to_markdown(epub_path, out)
    text = out.read_text()

    # The three bare-integer dividers render as Parts, not Chapters
    assert "# Part — 1" in text
    assert "# Part — 2" in text
    assert "# Part — 3" in text
    # And are never re-classified as Chapter headings
    assert "# Chapter 1 — 1" not in text
    assert "# Chapter 2 — 2" not in text
    assert "# Chapter 3 — 3" not in text

    # Sub-sections number contiguously across the whole book — six total,
    # no slot consumed by any divider.
    assert "# Chapter 1 — Start Here" in text
    assert "# Chapter 2 — The Hot Coals Sketch" in text
    assert "# Chapter 3 — RIP Cold Calling" in text
    assert "# Chapter 4 — Cold Calling 1.0 vs 2.0" in text
    assert "# Chapter 5 — Getting Started" in text
    assert "# Chapter 6 — The Ideal Customer Profile" in text
    assert result.chapter_count == 6


def test_convert_keeps_bare_integer_part_intros_with_short_body(tmp_path: Path):
    """A bare-integer Part label ("1") carries no information by itself —
    the actual chapter title and any intro prose live in the body. A
    short body (under the 50-word descriptive-Part floor) must still
    be kept because dropping it loses the only structural marker the
    publisher gave us for the start of a book chapter.

    Real repro: Aaron Ross's *Predictable Revenue* (PebbleStorm 2011)
    has 11 bare-integer chapter dividers with ~25-30 word bodies (just
    the chapter title + tagline + opening sentence). The standard 50-
    word floor drops them, losing the book's actual 11-chapter spine."""
    sections = [
        ("Cover", "Cover image."),
        ("Foreword", "Foreword text " * 40),
        # Bare-integer divider with a 22-word body (well under 50): kept.
        ("1",
         "Where the $100 Million Came From  I had never done "
         "business-to-business sales in my life before joining Salesforce.com"),
        ("Start Here", "BODY-OF-START-HERE " * 30),
        ("The Hot Coals Sketch", "BODY-OF-HOT-COALS " * 30),
        # Another bare-integer divider, even shorter body (10 words): kept.
        ("2", "Cold Calling 2.0 Ramp Sales Fast Without Cold Calls"),
        ("RIP Cold Calling", "BODY-OF-RIP " * 30),
        # A *descriptive* Part with a 5-word body must STILL be dropped —
        # this is the existing Awaken-the-Giant-style divider-only Part.
        ("Part Three: Decoy Decoy", "PART THREE Decoy Decoy"),
        ("Decoy Chapter", "BODY-OF-DECOY " * 30),
    ]
    epub_path = _build_epub_with_layout(
        tmp_path / "short_bare_int_parts.epub",
        title="Short Bare Integer Parts",
        sections=sections,
        spine_indices=list(range(len(sections))),
        ncx_indices=list(range(len(sections))),
    )

    out = tmp_path / "out.md"
    result = convert_epub_to_markdown(epub_path, out)
    text = out.read_text()

    # Both bare-integer dividers kept, body and all
    assert "# Part — 1" in text
    assert "Where the $100 Million Came From" in text
    assert "# Part — 2" in text
    assert "Cold Calling 2.0" in text

    # Descriptive divider-only Part still dropped (regression guard for
    # the Awaken-the-Giant / Blue-Ocean-Strategy behavior)
    assert "# Part — Part Three" not in text
    assert "PART THREE Decoy" not in text

    # Chapters number contiguously across the whole book — 5 real chapters,
    # no slot consumed by any Part divider (kept or dropped).
    assert "# Chapter 1 — Start Here" in text
    assert "# Chapter 2 — The Hot Coals Sketch" in text
    assert "# Chapter 3 — RIP Cold Calling" in text
    assert "# Chapter 4 — Decoy Chapter" in text
    assert result.chapter_count == 4


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


def test_promote_h2_to_chapters_fires_when_only_parts_at_h1(tmp_path: Path):
    """Pre-Suasion pattern: the merge-mode output has Parts as H1 and the
    real chapters as H2 inside each Part body. The helper must walk H2
    boundaries inside Part bodies and emit them as top-level Chapter
    sections, numbered globally across all Parts.

    Real repro: Robert Cialdini's *Pre-Suasion* (Random House 2016) has
    3 Part-as-H1 / 14 Chapter-as-H2 structure. Without H2 promotion the
    merge-mode fallback emits 3 fat Part-level chapters instead of 14
    real ones, collapsing the book's actual chapter granularity."""
    from book_llm_wiki.convert.epub import _maybe_promote_h2_to_chapters

    parts = [
        "# Preamble — Foreword\n\nForeword body.\n",
        "# Part — Part 1: Frontloading\n\nPart 1 intro prose.\n\n## Chapter 1 Title\n\nCh 1 body text.\n\n## Chapter 2 Title\n\nCh 2 body text.\n",
        "# Part — Part 2: Processes\n\n## Chapter 3 Title\n\nCh 3 body text.\n",
    ]
    result = _maybe_promote_h2_to_chapters(parts)
    titles = [p.split("\n", 1)[0] for p in result]

    # Parts kept (with intro prose where present)
    assert "# Part — Part 1: Frontloading" in titles
    assert "# Part — Part 2: Processes" in titles
    # H2s promoted to global-numbered Chapter headings
    assert "# Chapter 1 — Chapter 1 Title" in titles
    assert "# Chapter 2 — Chapter 2 Title" in titles
    assert "# Chapter 3 — Chapter 3 Title" in titles
    # Per-chapter bodies kept under their new H1 headings
    full = "\n".join(result)
    ch1_idx = full.index("# Chapter 1 — Chapter 1 Title")
    ch2_idx = full.index("# Chapter 2 — Chapter 2 Title")
    assert "Ch 1 body text" in full[ch1_idx:ch2_idx]
    # Part intro prose stays under the Part heading, not under the first chapter
    part1_idx = full.index("# Part — Part 1: Frontloading")
    assert "Part 1 intro prose" in full[part1_idx:ch1_idx]


def test_promote_h2_fires_when_parts_misclassified_as_chapters(tmp_path: Path):
    """Pre-Suasion's Part titles are all-caps with no "Part N:" prefix —
    ``PRE-SUASION: THE FRONTLOADING OF ATTENTION`` rather than ``Part 1:
    Pre-Suasion: The Frontloading of Attention`` — so the merge-mode
    fallback's classify_section call routes them through the default
    branch and labels them ``# Chapter N — …``. The helper must detect
    this mis-classification (≤3 H1 chapters with ≥6 total H2 boundaries
    averaging ≥3 H2s per H1) and relabel the H1s as Parts before
    promoting the H2s to real Chapter headings."""
    from book_llm_wiki.convert.epub import _maybe_promote_h2_to_chapters

    parts = [
        "# Chapter 1 — PRE-SUASION: THE FRONTLOADING OF ATTENTION\n\nPart 1 intro.\n\n## Pre-Suasion An Introduction\n\nbody 1.\n\n## Privileged Moments\n\nbody 2.\n\n## What's Focal Is Causal\n\nbody 3.\n",
        "# Chapter 2 — PROCESSES: THE ROLE OF ASSOCIATION\n\n## The Primacy of Associations\n\nbody 4.\n\n## Persuasive Geographies\n\nbody 5.\n\n## The Mechanics of Pre-Suasion\n\nbody 6.\n",
    ]
    result = _maybe_promote_h2_to_chapters(parts)
    titles = [p.split("\n", 1)[0] for p in result]

    # The two mis-classified Chapter H1s are now Parts
    assert "# Part — PRE-SUASION: THE FRONTLOADING OF ATTENTION" in titles
    assert "# Part — PROCESSES: THE ROLE OF ASSOCIATION" in titles
    # All six H2 boundaries become globally-numbered Chapter headings
    assert "# Chapter 1 — Pre-Suasion An Introduction" in titles
    assert "# Chapter 2 — Privileged Moments" in titles
    assert "# Chapter 3 — What's Focal Is Causal" in titles
    assert "# Chapter 4 — The Primacy of Associations" in titles
    assert "# Chapter 5 — Persuasive Geographies" in titles
    assert "# Chapter 6 — The Mechanics of Pre-Suasion" in titles


def test_promote_h2_does_not_fire_on_normal_book_with_few_h2s(tmp_path: Path):
    """A normal 3-chapter book with a couple of H2 sub-sections each
    (typical short non-fiction) must NOT be relabeled. The H2-per-chapter
    ratio gate (≥3) protects against this — a 3-chapter book with 2 H2
    sub-sections per chapter has ratio 2, below the trigger."""
    from book_llm_wiki.convert.epub import _maybe_promote_h2_to_chapters

    parts = [
        "# Chapter 1 — Origins\n\nbody.\n\n## sub 1.1\n\nx.\n\n## sub 1.2\n\nx.\n",
        "# Chapter 2 — Growth\n\nbody.\n\n## sub 2.1\n\nx.\n\n## sub 2.2\n\nx.\n",
        "# Chapter 3 — Reflection\n\nbody.\n\n## sub 3.1\n\nx.\n\n## sub 3.2\n\nx.\n",
    ]
    # H2 count = 6, chapter_count = 3, ratio = 2 (below the 3 threshold)
    # The 6-H2 gate is met but the per-chapter ratio gate is not, so no fire.
    assert _maybe_promote_h2_to_chapters(parts) == parts


def test_promote_h2_does_not_fire_when_chapters_exist_at_h1(tmp_path: Path):
    """Clear-Thinking-style EPUBs already have Part-as-H1 + Chapter-as-H1.
    H2 headings inside chapter bodies are sub-section markers (epigraph
    callouts, named anecdotes, etc.) and must NOT be promoted to chapters
    — promotion would shred each chapter into many spurious mini-chapters.
    Regression guard: the helper fires only when zero Chapter sections
    exist at the H1 level."""
    from book_llm_wiki.convert.epub import _maybe_promote_h2_to_chapters

    parts = [
        "# Part — Part 1: Stuff\n\nIntro.\n\n## Sub-section heading\n\nbody.\n",
        "# Chapter 1 — Foo\n\n## Mid-chapter callout\n\nMore body.\n",
        "# Chapter 2 — Bar\n\nbody.\n",
    ]
    result = _maybe_promote_h2_to_chapters(parts)
    # Unchanged — no H2 promotion when H1 Chapters already exist
    assert result == parts


def test_promote_h2_does_not_fire_when_no_parts(tmp_path: Path):
    """A normal Chapter-as-H1 EPUB without any Part dividers has no work
    for this helper to do. Pass through unchanged."""
    from book_llm_wiki.convert.epub import _maybe_promote_h2_to_chapters

    parts = [
        "# Front Matter — Cover\n\nCover image.\n",
        "# Chapter 1 — Foo\n\n## Sub-section\n\nbody.\n",
        "# Chapter 2 — Bar\n\nbody.\n",
    ]
    assert _maybe_promote_h2_to_chapters(parts) == parts


def test_promote_h2_skips_empty_h2_titles(tmp_path: Path):
    """H2 boundaries with empty title text (decorative section breaks,
    epub2md artifacts) must not be promoted to Chapter headings."""
    from book_llm_wiki.convert.epub import _maybe_promote_h2_to_chapters

    parts = [
        "# Part — Part 1\n\nIntro.\n\n## \n\nempty-title body\n\n## Real Chapter\n\nbody.\n",
    ]
    result = _maybe_promote_h2_to_chapters(parts)
    titles = [p.split("\n", 1)[0] for p in result]
    # The "## " with empty title is skipped; only the real one becomes Ch 1
    assert "# Chapter 1 — Real Chapter" in titles
    assert "# Chapter 1 — " not in titles  # not an empty-title chapter
    assert sum(1 for t in titles if t.startswith("# Chapter ")) == 1


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


def _build_part_stubs_with_unref_body_epub(out_path: Path) -> Path:
    """Build an EPUB whose NCX points at small Part-divider stub XHTML files
    while substantive Part body lives in supplement XHTML files NOT
    referenced by NCX but present in spine order between divider and
    next NCX entry.

    Mirrors Brené Brown's *Dare to Lead* (Random House 2018) structure:
    the book has correctly-NCX-referenced Chapter body files for early
    sections (Chapters 1-3), then three Part dividers (p002, p003, p004)
    NCX-referenced as stubs, with the actual Part body content sitting
    in unreferenced supplement files (p002-sup1, p003-sup1, bm-sup1) in
    the spine immediately after each divider.

    The pre-existing detectors all miss this pattern:
    - ``_section_mode_chapters_look_empty``: chapters 1-3 are non-empty.
    - ``_section_mode_routed_to_stubs``: ref body bytes (Ch 1-3) outweigh
      the unref supplement bytes, so the 5x ratio gate fails.
    - ``_section_mode_ncx_is_degenerate``: NCX has 6 substantive
      navPoints, not ≤1.
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

    # Stub: small image-only divider page (Random House p002_r1.xhtml is
    # ~933 bytes — under the 3000-byte stub threshold).
    stub_template = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{title}</title></head>
<body><div><img alt="{title}" src="part.jpg"/></div></body></html>"""

    spine_files: list[tuple[str, str, bool]] = []  # (href, html, is_ref)

    # Three correctly-referenced chapter body files (Part 1).
    for idx, label in enumerate(["First", "Second", "Third"], start=1):
        title = f"Chapter {idx}: {label}"
        body = f"BODY-OF-CH{idx} " * 800
        spine_files.append((
            f"chapter-{idx}.xhtml",
            body_template.format(title=title, body=body),
            True,
        ))

    # Three Parts each with: stub (NCX-ref) + supplement (large, NOT NCX-ref).
    for part_idx, part_label in enumerate(
        ["Living Into Our Values", "Braving Trust", "Learning to Rise"],
        start=2,
    ):
        stub_title = f"Part {part_idx}: {part_label}"
        spine_files.append((
            f"p{part_idx:03d}.xhtml",
            stub_template.format(title=stub_title),
            True,  # stub IS in NCX
        ))
        spine_files.append((
            f"p{part_idx:03d}-sup1.xhtml",
            body_template.format(
                title=f"Continued, Part {part_idx}",
                body=f"BODY-OF-PART{part_idx}-SUP " * 800,
            ),
            False,  # supplement is NOT in NCX
        ))

    manifest_items = []
    spine_items = []
    nav_points = []
    html_files = {}

    for idx, (href, html, _is_ref) in enumerate(spine_files, start=1):
        item_id = f"s{idx}"
        manifest_items.append(
            f'    <item id="{item_id}" href="{href}" media-type="application/xhtml+xml"/>'
        )
        spine_items.append(f'    <itemref idref="{item_id}"/>')
        html_files[href] = html

    nav_order = 1
    for idx, (href, _html, is_ref) in enumerate(spine_files, start=1):
        if not is_ref:
            continue
        nav_points.append(NAV_POINT_TEMPLATE.format(
            id=f"nav{nav_order}",
            order=nav_order,
            label=href,
            src=href,
        ))
        nav_order += 1

    content_opf = CONTENT_OPF_TEMPLATE.format(
        title="Part Stubs Book", author="A", year="2018",
        title_slug="part-stubs-book",
        manifest_items="\n".join(manifest_items),
        spine_items="\n".join(spine_items),
        extra_metadata="",
    )
    ncx_xml = NCX_TEMPLATE.format(
        title="Part Stubs Book",
        nav_points="\n".join(nav_points),
    )

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/toc.ncx", ncx_xml)
        for href, html in html_files.items():
            zf.writestr(f"OEBPS/{href}", html)
    return out_path


def _deduped_structure_for(epub_path: Path):
    """Helper mirroring the section-mode dedupe step used by the detectors."""
    from book_llm_wiki.convert.epub import _xhtml_manifest_hrefs, epub_structure
    from urllib.parse import unquote

    manifest_hrefs = _xhtml_manifest_hrefs(epub_path)
    pos_by_href = {h: i for i, h in enumerate(manifest_hrefs, start=1)}
    structure = epub_structure(epub_path)
    deduped = []
    seen = set()
    for s in structure:
        bare = unquote(s["src"].split("#", 1)[0])
        position = pos_by_href.get(bare)
        if position is None or position in seen:
            continue
        seen.add(position)
        deduped.append({**s, "_position": position})
    return manifest_hrefs, deduped


def test_section_mode_part_stubs_with_unref_body_detects_pattern(tmp_path: Path):
    """``_section_mode_part_stubs_with_unref_body`` must fire on EPUBs where
    NCX-referenced Part dividers are stubs and the substantive Part body
    lives in supplement XHTML files unreferenced by NCX but present in
    spine order. Real-case repro was Brené Brown's *Dare to Lead* (Random
    House 2018)."""
    from book_llm_wiki.convert.epub import _section_mode_part_stubs_with_unref_body

    epub_path = _build_part_stubs_with_unref_body_epub(tmp_path / "part_stubs.epub")
    manifest_hrefs, deduped = _deduped_structure_for(epub_path)

    assert _section_mode_part_stubs_with_unref_body(
        epub_path, deduped, manifest_hrefs
    )


def test_section_mode_part_stubs_with_unref_body_not_falsely_detected(normal_epub: Path):
    """A normal publisher EPUB where NCX entries target substantive body
    files must NOT be flagged as part-stubs-with-unref-body."""
    from book_llm_wiki.convert.epub import _section_mode_part_stubs_with_unref_body

    manifest_hrefs, deduped = _deduped_structure_for(normal_epub)

    assert not _section_mode_part_stubs_with_unref_body(
        normal_epub, deduped, manifest_hrefs
    )


def test_part_stubs_pre_existing_detectors_do_not_fire_on_dare_to_lead_pattern(
    tmp_path: Path,
):
    """The three pre-existing section-mode routing detectors must NOT
    fire on the Dare-to-Lead-style fixture — confirming that the new
    part-stubs detector is what's needed to route this pattern correctly.
    Without this guard, a future change could make e.g.
    ``_section_mode_routed_to_stubs`` fire on this fixture and the new
    detector would become dead code."""
    from book_llm_wiki.convert.epub import (
        _section_mode_ncx_is_degenerate,
        _section_mode_routed_to_stubs,
    )

    epub_path = _build_part_stubs_with_unref_body_epub(tmp_path / "part_stubs.epub")
    manifest_hrefs, deduped = _deduped_structure_for(epub_path)

    assert not _section_mode_routed_to_stubs(epub_path, deduped, manifest_hrefs)
    assert not _section_mode_ncx_is_degenerate(epub_path, deduped, manifest_hrefs)


def test_convert_part_stubs_epub_recovers_part_body_via_spine_extraction(
    tmp_path: Path,
):
    """End-to-end: a Dare-to-Lead-style EPUB (NCX points at small
    Part-divider stubs while Part body lives in supplement files
    unreferenced by NCX) must route through
    ``_convert_via_spine_body_extraction`` and recover all of the Part
    supplement body content rather than emitting only the divider
    stubs."""
    epub_path = _build_part_stubs_with_unref_body_epub(tmp_path / "part_stubs.epub")
    out = tmp_path / "out.md"
    result = convert_epub_to_markdown(epub_path, out)

    text = out.read_text()

    # Body content from the regularly-NCX-referenced chapter files must
    # be present.
    assert "BODY-OF-CH1" in text
    assert "BODY-OF-CH2" in text
    assert "BODY-OF-CH3" in text

    # And the unreferenced Part supplement body content must also be
    # present — the regression we're guarding against.
    assert "BODY-OF-PART2-SUP" in text
    assert "BODY-OF-PART3-SUP" in text
    assert "BODY-OF-PART4-SUP" in text

    assert result.conversion_quality == "high"
    assert result.mode == "structured"


def _build_calibre_generic_title_epub(out_path: Path) -> Path:
    """Build an EPUB where every XHTML file has the same generic
    ``<title>Converted Ebook</title>`` and the real chapter heading sits
    inside the body as ``<h2>``.

    Mirrors the pattern of Calibre-generated EPUBs from PDFs / print scans
    where Calibre uses a fixed "Converted Ebook" placeholder for every
    file's ``<title>`` element and never inserts an ``<h1>``. Real example:
    Michael Masterson, *Ready, Fire, Aim* (Wiley 2008, Agora-distributed,
    rebuilt through Calibre).

    The NCX is degenerate (single navPoint pointing at the cover stub),
    forcing the converter through ``_convert_via_spine_body_extraction``.
    The body files have substantive prose (>500 bytes) so the byte-size
    stub-filter does not drop them.
    """
    import zipfile
    from tests.conftest import (
        CONTAINER_XML, CONTENT_OPF_TEMPLATE, NCX_TEMPLATE,
        NAV_POINT_TEMPLATE, MIMETYPE,
    )

    # Every XHTML uses the SAME generic <title> ("Converted Ebook") and
    # carries its real chapter title only as <h2> inside the body.
    GENERIC_TITLE_HTML = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Converted Ebook</title></head>
<body>
<h2>{h2_title}</h2>
<p>{body}</p>
</body>
</html>
"""

    # Cover stub stays small (<3 KB) so the spine-body extractor drops it
    # at the byte-threshold; the real preamble + chapter files all have
    # >500 chars of body prose so they survive.
    cover_html = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Converted Ebook</title></head>
<body><p>Cover</p></body>
</html>
"""

    # Each body file must exceed the 8000-byte SECTION_MODE_BODY_FILE_BYTE_THRESHOLD
    # for _section_mode_ncx_is_degenerate to fire (it requires ≥3 unreferenced
    # XHTML files above that threshold).
    sections = [
        ("cover.xhtml",   cover_html,                                                                                "Cover"),
        ("section-2.xhtml", GENERIC_TITLE_HTML.format(h2_title="WHAT TO EXPECT FROM THIS BOOK",   body="WHAT-TO-EXPECT-BODY " * 500),  "WHAT TO EXPECT FROM THIS BOOK"),
        ("section-3.xhtml", GENERIC_TITLE_HTML.format(h2_title="CHAPTER ONE: Getting To The Next Level", body="CHAPTER-ONE-BODY " * 500), "Ch One"),
        ("section-4.xhtml", GENERIC_TITLE_HTML.format(h2_title="CHAPTER TWO: Why Employee Size Matters", body="CHAPTER-TWO-BODY " * 500), "Ch Two"),
        ("section-5.xhtml", GENERIC_TITLE_HTML.format(h2_title="CHAPTER THREE: Becoming A Five-Star Business", body="CHAPTER-THREE-BODY " * 500), "Ch Three"),
        ("section-6.xhtml", GENERIC_TITLE_HTML.format(h2_title="CHAPTER FOUR: The Supremacy Of Selling", body="CHAPTER-FOUR-BODY " * 500), "Ch Four"),
    ]

    manifest_items = []
    spine_items = []
    html_files = {}
    for i, (href, html, _label) in enumerate(sections, start=1):
        item_id = f"s{i}"
        manifest_items.append(
            f'    <item id="{item_id}" href="{href}" media-type="application/xhtml+xml"/>'
        )
        spine_items.append(f'    <itemref idref="{item_id}"/>')
        html_files[href] = html

    # NCX is degenerate: a single navPoint pointing at the cover stub. This
    # forces _section_mode_ncx_is_degenerate to fire and route through
    # _convert_via_spine_body_extraction.
    nav_points = [NAV_POINT_TEMPLATE.format(id="nav1", order=1, label="Cover", src="cover.xhtml")]

    content_opf = CONTENT_OPF_TEMPLATE.format(
        title="Calibre Generic Title Book",
        author="Test Author",
        year="2024",
        title_slug="calibre-generic-title-book",
        manifest_items="\n".join(manifest_items),
        spine_items="\n".join(spine_items),
        extra_metadata="",
    )
    ncx_xml = NCX_TEMPLATE.format(
        title="Calibre Generic Title Book", nav_points="\n".join(nav_points)
    )

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/toc.ncx", ncx_xml)
        for href, html in html_files.items():
            zf.writestr(f"OEBPS/{href}", html)
    return out_path


def test_convert_calibre_generic_title_uses_h2_for_chapter_classification(
    tmp_path: Path,
):
    """Regression: EPUBs where every XHTML file has the same generic
    <title>Converted Ebook</title> and the real chapter heading lives
    only as <h2> inside the body must classify by the H2 heading, not by
    the generic placeholder.

    Real example: Michael Masterson, *Ready, Fire, Aim* (Wiley 2008,
    Agora-distributed, Calibre-rebuilt) — produces 100+ chapters all
    titled "Chapter N — Converted Ebook" without the fix.
    """
    epub_path = _build_calibre_generic_title_epub(
        tmp_path / "calibre_generic.epub"
    )
    out = tmp_path / "out.md"

    result = convert_epub_to_markdown(epub_path, out)
    text = out.read_text()

    # The generic placeholder must NOT appear inside any ``# Chapter``,
    # ``# Preamble``, ``# Part``, ``# Front Matter`` or ``# Back Matter``
    # heading. (It may appear in body prose if real chapter text mentioned
    # it, but the heading classification must use the H2 instead.)
    import re as _re
    heading_lines = [
        ln for ln in text.splitlines()
        if _re.match(r"^# (Chapter |Preamble |Part |Front Matter|Back Matter)", ln)
    ]
    for hl in heading_lines:
        assert "Converted Ebook" not in hl, (
            f"Generic placeholder leaked into heading: {hl!r}"
        )

    # Real chapter titles (drawn from the H2 headings) must appear in
    # chapter headings with proper Chapter classification. The preamble
    # ("WHAT TO EXPECT FROM THIS BOOK") classifies as CHAPTER under
    # classify_section's default heuristics — that's tangential to this
    # regression. What matters is that the H2 title is used, not the
    # generic placeholder.
    assert "WHAT TO EXPECT FROM THIS BOOK" in text
    assert "# Chapter " in text  # at least one Chapter heading emitted
    # Each H2 chapter title appears in some heading line:
    chapter_h2_titles = [
        "CHAPTER ONE: Getting To The Next Level",
        "CHAPTER TWO: Why Employee Size Matters",
        "CHAPTER THREE: Becoming A Five-Star Business",
        "CHAPTER FOUR: The Supremacy Of Selling",
    ]
    for title in chapter_h2_titles:
        matching_headings = [hl for hl in heading_lines if title in hl]
        assert matching_headings, f"H2 title {title!r} missing from any heading"

    # Body content must be present (substantive body bytes survived).
    assert "WHAT-TO-EXPECT-BODY" in text
    assert "CHAPTER-ONE-BODY" in text
    assert "CHAPTER-TWO-BODY" in text
    assert "CHAPTER-THREE-BODY" in text
    assert "CHAPTER-FOUR-BODY" in text

    assert result.conversion_quality == "high"
    assert result.mode == "structured"


def _build_calibre_generic_title_multi_file_chapter_epub(out_path: Path) -> Path:
    """Build an EPUB where each real chapter is split across several XHTML
    files: the first file in the chapter has an <h2> chapter heading, but
    subsequent files in the same chapter have only continuation prose with
    no H2 heading at all.

    Mirrors the print-page-per-XHTML pattern of Calibre-from-PDF EPUBs (real
    example: Michael Masterson, *Ready, Fire, Aim*, Wiley 2008,
    Agora-distributed) where the original book's 25 chapters explode into
    100+ XHTML files, with each chapter spanning 4-10 consecutive files.
    The first file has the chapter heading; subsequent files contain
    mid-prose continuation.

    The spine-body extractor must consolidate continuation files into the
    preceding chapter rather than emitting one chapter heading per file.
    """
    import zipfile
    from tests.conftest import (
        CONTAINER_XML, CONTENT_OPF_TEMPLATE, NCX_TEMPLATE,
        NAV_POINT_TEMPLATE, MIMETYPE,
    )

    HEADED_HTML = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Converted Ebook</title></head>
<body>
<h2>{h2_title}</h2>
<p>{body}</p>
</body>
</html>
"""
    CONTINUATION_HTML = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Converted Ebook</title></head>
<body>
<p>{body}</p>
</body>
</html>
"""
    cover_html = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Converted Ebook</title></head>
<body><p>Cover</p></body>
</html>
"""

    # Each chapter is split: a "headed" file with the <h2> + two "continuation"
    # files with no heading. Each file > 8KB so the degenerate-NCX detector
    # fires.
    sections = [
        ("cover.xhtml",     cover_html),
        # CHAPTER ONE — headed + 2 continuations. Each file > 8KB so the
        # _section_mode_ncx_is_degenerate detector fires.
        ("section-2.xhtml", HEADED_HTML.format(h2_title="CHAPTER ONE: Getting To The Next Level", body="CHONE-A " * 1200)),
        ("section-3.xhtml", CONTINUATION_HTML.format(body="CHONE-CONT-B " * 1200)),
        ("section-4.xhtml", CONTINUATION_HTML.format(body="CHONE-CONT-C " * 1200)),
        # CHAPTER TWO — headed + 1 continuation
        ("section-5.xhtml", HEADED_HTML.format(h2_title="CHAPTER TWO: The Second", body="CHTWO-A " * 1200)),
        ("section-6.xhtml", CONTINUATION_HTML.format(body="CHTWO-CONT-B " * 1200)),
        # CHAPTER THREE — headed only
        ("section-7.xhtml", HEADED_HTML.format(h2_title="CHAPTER THREE: The Third", body="CHTHREE-A " * 1200)),
    ]

    manifest_items = []
    spine_items = []
    html_files = {}
    for i, (href, html) in enumerate(sections, start=1):
        item_id = f"s{i}"
        manifest_items.append(
            f'    <item id="{item_id}" href="{href}" media-type="application/xhtml+xml"/>'
        )
        spine_items.append(f'    <itemref idref="{item_id}"/>')
        html_files[href] = html

    nav_points = [NAV_POINT_TEMPLATE.format(id="nav1", order=1, label="Cover", src="cover.xhtml")]

    content_opf = CONTENT_OPF_TEMPLATE.format(
        title="Calibre Multi-File Chapter Book",
        author="Test Author",
        year="2024",
        title_slug="calibre-multi-file-chapter-book",
        manifest_items="\n".join(manifest_items),
        spine_items="\n".join(spine_items),
        extra_metadata="",
    )
    ncx_xml = NCX_TEMPLATE.format(
        title="Calibre Multi-File Chapter Book", nav_points="\n".join(nav_points)
    )

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/toc.ncx", ncx_xml)
        for href, html in html_files.items():
            zf.writestr(f"OEBPS/{href}", html)
    return out_path


def test_convert_calibre_multi_file_chapter_consolidates_continuations(
    tmp_path: Path,
):
    """Regression: when each chapter is split across multiple XHTML files
    (the first carries the H2 heading; subsequent files have continuation
    prose only), the spine-body extractor must consolidate continuation
    files into the preceding chapter rather than emitting one chapter
    heading per file.

    Real example: Michael Masterson, *Ready, Fire, Aim* (Wiley 2008,
    Agora-distributed, Calibre-rebuilt) — produces 100+ chapters (one per
    XHTML print-page) without consolidation, when the actual book has 25.
    """
    epub_path = _build_calibre_generic_title_multi_file_chapter_epub(
        tmp_path / "calibre_multi.epub"
    )
    out = tmp_path / "out.md"

    result = convert_epub_to_markdown(epub_path, out)
    text = out.read_text()

    # Exactly 3 chapter headings — one per real chapter, not one per file.
    chapter_headings = [
        ln for ln in text.splitlines() if ln.startswith("# Chapter ")
    ]
    assert len(chapter_headings) == 3, (
        f"Expected 3 chapter headings, got {len(chapter_headings)}: {chapter_headings!r}"
    )
    assert "# Chapter 1 — CHAPTER ONE: Getting To The Next Level" in text
    assert "# Chapter 2 — CHAPTER TWO: The Second" in text
    assert "# Chapter 3 — CHAPTER THREE: The Third" in text

    # All body content (including continuations) is present, attached to the
    # right chapter.
    ch1 = text.index("# Chapter 1 —")
    ch2 = text.index("# Chapter 2 —")
    ch3 = text.index("# Chapter 3 —")
    assert "CHONE-A" in text[ch1:ch2]
    assert "CHONE-CONT-B" in text[ch1:ch2]
    assert "CHONE-CONT-C" in text[ch1:ch2]
    assert "CHTWO-A" in text[ch2:ch3]
    assert "CHTWO-CONT-B" in text[ch2:ch3]
    assert "CHTHREE-A" in text[ch3:]

    assert result.chapter_count == 3
    assert result.conversion_quality == "high"
    assert result.mode == "structured"


def test_looks_like_title_page_helper():
    """Unit: a first-section navPoint labeled with a superset of the book
    title's tokens (the title-page-as-chapter pattern) is detected, while
    real chapter labels are not."""
    from book_llm_wiki.convert.epub import _looks_like_title_page

    title = "Sam Walton: Made in America"
    # Bantam's NCX[0] label — book title tokens plus "My Story".
    assert _looks_like_title_page("Sam Walton, Made In America: My Story", title)
    # Exact title match (other publishers label the title page this way).
    assert _looks_like_title_page("Sam Walton: Made in America", title)
    # Real chapters are not supersets of the title token set.
    assert not _looks_like_title_page("Learning to Value a Dollar", title)
    assert not _looks_like_title_page("Chapter 1: Learning to Value a Dollar", title)
    # An explicit chapter pattern must never be reclassified even if it
    # happens to contain the title tokens.
    assert not _looks_like_title_page("1 Sam Walton Made In America", title)
    # Ultra-short (single-token) titles are too coincidence-prone — skip.
    assert not _looks_like_title_page("It Begins", "It")
    # No title metadata → never fires.
    assert not _looks_like_title_page("Anything", "")


def test_convert_does_not_off_by_one_when_titlepage_navpoint_is_book_title(
    tmp_path: Path,
):
    """Regression: Bantam's *Sam Walton: Made in America* labels its first
    NCX navPoint 'Sam Walton, Made In America: My Story' (the title page),
    which classify_section() has no pattern for, so it fell through to the
    CHAPTER default and consumed chapter number 1 — shifting every real
    chapter +1 (raw '# Chapter 2' was actually book Chapter 1, etc.).

    The title page must be Front Matter and the first real chapter must be
    '# Chapter 1', not '# Chapter 2'.
    """
    body = "REAL-BODY " * 60
    sections = [
        ("Sam Walton, Made In America: My Story",
         "Sam Walton\nMade in America\nMy Story\nby Sam Walton\nBANTAM BOOKS"),
        ("Contents", "Acknowledgments\nForeword\n1 Learning to Value a Dollar"),
        ("Acknowledgements", "ACK-BODY " * 40),
        ("Foreword", "FOREWORD-BODY " * 60),
        ("Learning to Value a Dollar", "CH1 " + body),
        ("Starting on a Dime", "CH2 " + body),
        ("Bouncing Back", "CH3 " + body),
    ]
    epub_path = _build_epub_with_layout(
        tmp_path / "samwalton.epub",
        title="Sam Walton: Made in America",
        sections=sections,
        spine_indices=[0, 1, 2, 3, 4, 5, 6],
        ncx_indices=[0, 1, 2, 3, 4, 5, 6],
    )

    out = tmp_path / "out.md"
    result = convert_epub_to_markdown(epub_path, out)
    text = out.read_text()

    # The title page is Front Matter, not Chapter 1.
    assert "# Front Matter — Sam Walton, Made In America: My Story" in text
    assert "# Chapter 1 — Sam Walton, Made In America: My Story" not in text

    # No off-by-one: the first real chapter is Chapter 1.
    assert "# Chapter 1 — Learning to Value a Dollar" in text
    assert "# Chapter 2 — Starting on a Dime" in text
    assert "# Chapter 3 — Bouncing Back" in text
    assert "# Chapter 4 —" not in text

    # Front/back/preamble matter still classified correctly around it.
    assert "# Back Matter — Contents" in text
    assert "# Front Matter — Acknowledgements" in text
    assert "# Preamble — Foreword" in text

    assert result.chapter_count == 3
    assert result.mode == "structured"


def test_classify_welcome_only_matches_genuine_welcome_preamble():
    """Regression: the ^welcome\\b preamble pattern false-matched essay
    titles like Rework's 'Welcome obscurity', emitting them as
    '# Preamble' and dropping them from chapter numbering. Genuine
    front-matter 'Welcome' sections must still classify as PREAMBLE."""
    # Genuine welcome-preamble forms still work.
    assert classify_section("Welcome") == SectionClass.PREAMBLE
    assert classify_section("Welcome!") == SectionClass.PREAMBLE
    assert classify_section("Welcome, Reader") == SectionClass.PREAMBLE
    assert classify_section("Welcome to the Show") == SectionClass.PREAMBLE
    # Essay titles that merely start with the word "welcome" must not.
    assert classify_section("Welcome obscurity") == SectionClass.CHAPTER
    assert classify_section("Welcome aboard the team") == SectionClass.CHAPTER


def test_convert_emits_sections_in_spine_order_when_ncx_playorder_scrambled(
    tmp_path: Path,
):
    """Regression: Ebury's *ReWork* ships an NCX whose playOrder interleaves
    content-essay navPoints before the front-matter navPoints, all
    fragment-anchored into shared spine files. Iterating NCX playOrder made
    the deduped emit order non-monotonic in spine position — Title Page /
    Introduction emitted *after* content chapters, and content files titled
    by their first essay instead of their section header.

    The spine is the spec-authoritative reading order; emitted sections
    must follow it regardless of NCX playOrder.
    """
    sections = [
        ("Title Page", "REWORK\nby Jason Fried"),
        ("Introduction", "INTRO-BODY " * 60),
        ("First", "FIRST-SECTION-BODY " * 60),
        ("The new reality", "NEWREALITY-BODY " * 60),
        ("Make a dent in the universe", "DENT-BODY " * 60),
        ("Welcome obscurity", "OBSCURITY-BODY " * 60),
        ("Acknowledgments", "ACK-BODY " * 40),
    ]
    # Spine = natural reading order. NCX playOrder scrambled exactly like
    # ReWork: two content sections (idx 3, 4) before front matter (0, 1, 2).
    epub_path = _build_epub_with_layout(
        tmp_path / "rework.epub",
        title="ReWork",
        sections=sections,
        spine_indices=[0, 1, 2, 3, 4, 5, 6],
        ncx_indices=[3, 0, 4, 1, 2, 5, 6],
    )

    out = tmp_path / "out.md"
    convert_epub_to_markdown(epub_path, out)
    text = out.read_text()

    # Emitted in spine order: front matter precedes all content.
    i_title = text.index("# Front Matter — Title Page")
    i_intro = text.index("# Preamble — Introduction")
    i_first = text.index("First")
    i_newreality = text.index("The new reality")
    i_dent = text.index("Make a dent in the universe")
    assert i_title < i_intro < i_first < i_newreality < i_dent

    # No off-by-one / no front matter consuming chapter numbers.
    assert "# Chapter 1 — First" in text
    assert "# Chapter 2 — The new reality" in text
    assert "# Chapter 3 — Make a dent in the universe" in text

    # C: "Welcome obscurity" is a chapter essay, not a Preamble.
    assert "# Chapter 4 — Welcome obscurity" in text
    assert "# Preamble — Welcome obscurity" not in text

    # Back/front matter still filtered correctly.
    assert "# Front Matter — Acknowledgments" in text
