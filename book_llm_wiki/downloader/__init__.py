"""Download-side utilities: LibraryThing catalog management and EPUB quality checks.

Companion to the ingest/analyze side. These modules are runnable as:
    python -m book_llm_wiki.downloader.librarything <subcommand>
    python -m book_llm_wiki.downloader.epub_quality <path-to.epub>

The `librarything` module requires the optional `scrapling` dependency:
    pip install -e ".[librarything]"
"""
