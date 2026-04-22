"""EPUB → chapter-structured markdown, via epub2md subprocess.

epub2md (Node.js, already installed globally) exposes three modes we use:
  - `epub2md -i <epub>` prints metadata
  - `epub2md -s <epub>` prints structure as ANSI-colorized JS literals
  - `epub2md -c <epub>` writes one .md per section to a directory next to
    the source epub

Because the JSON output of `-s` is NOT valid JSON (it's a Node console.log
of a JS object with ANSI colors), we parse metadata and structure by
re-reading the EPUB zip directly. This gives us robust, colorless output.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path


OPF_NS = {
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
}
NCX_NS = {"ncx": "http://www.daisy.org/z3986/2005/ncx/"}
CONTAINER_NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}


def _read_zip_text(zf: zipfile.ZipFile, name: str) -> str:
    return zf.read(name).decode("utf-8")


def _find_opf_path(zf: zipfile.ZipFile) -> str:
    container = ET.fromstring(_read_zip_text(zf, "META-INF/container.xml"))
    rootfile = container.find(".//c:rootfile", CONTAINER_NS)
    if rootfile is None:
        raise ValueError("EPUB missing rootfile in container.xml")
    return rootfile.attrib["full-path"]


def epub_info(epub_path: Path) -> dict:
    """Return {'title': str, 'author': str, 'year': str | None, 'generator': str | None}."""
    with zipfile.ZipFile(epub_path) as zf:
        opf_path = _find_opf_path(zf)
        opf = ET.fromstring(_read_zip_text(zf, opf_path))
        metadata = opf.find("opf:metadata", OPF_NS)
        title_el = metadata.find("dc:title", OPF_NS) if metadata is not None else None
        creator_el = metadata.find("dc:creator", OPF_NS) if metadata is not None else None
        date_el = metadata.find("dc:date", OPF_NS) if metadata is not None else None
        generator = None
        if metadata is not None:
            for meta in metadata.findall("opf:meta", OPF_NS):
                if meta.attrib.get("name") == "generator":
                    generator = meta.attrib.get("content")
                    break
        year = None
        if date_el is not None and date_el.text:
            m = re.search(r"(\d{4})", date_el.text)
            if m:
                year = m.group(1)
        return {
            "title": (title_el.text or "").strip() if title_el is not None else "",
            "author": (creator_el.text or "").strip() if creator_el is not None else "",
            "year": year,
            "generator": generator,
        }


def epub_structure(epub_path: Path) -> list[dict]:
    """Return list of {'name': str, 'src': str} in navMap/playOrder."""
    with zipfile.ZipFile(epub_path) as zf:
        opf_path = _find_opf_path(zf)
        opf_dir = str(Path(opf_path).parent) + "/" if "/" in opf_path else ""
        opf = ET.fromstring(_read_zip_text(zf, opf_path))

        # Find NCX path
        manifest = opf.find("opf:manifest", OPF_NS)
        ncx_href = None
        for item in manifest.findall("opf:item", OPF_NS):
            if item.attrib.get("media-type") == "application/x-dtbncx+xml":
                ncx_href = item.attrib["href"]
                break
        if ncx_href is None:
            return []

        ncx_path = f"{opf_dir}{ncx_href}"
        ncx = ET.fromstring(_read_zip_text(zf, ncx_path))
        nav_points = []
        for np in ncx.iter(f"{{{NCX_NS['ncx']}}}navPoint"):
            label_el = np.find("ncx:navLabel/ncx:text", NCX_NS)
            content_el = np.find("ncx:content", NCX_NS)
            if label_el is None or content_el is None:
                continue
            try:
                order = int(np.attrib.get("playOrder", "0"))
            except ValueError:
                order = 0
            nav_points.append({
                "name": (label_el.text or "").strip(),
                "src": content_el.attrib.get("src", ""),
                "order": order,
            })
        nav_points.sort(key=lambda d: d["order"])
        return [{"name": n["name"], "src": n["src"]} for n in nav_points]


def run_epub2md_convert(epub_path: Path, out_dir: Path, merge: bool = False) -> Path:
    """Run `epub2md -c [--merge]` writing to out_dir. Returns the output directory path."""
    if shutil.which("epub2md") is None:
        raise RuntimeError("epub2md is not installed. Run: npm install -g epub2md")

    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["epub2md", "-c"]
    if merge:
        cmd.append("-m")
    cmd.append(str(epub_path))

    # epub2md writes output in the current working directory based on the epub filename.
    subprocess.run(cmd, check=True, cwd=out_dir, capture_output=True)

    # epub2md creates a subdirectory named after the EPUB (without extension)
    epub_stem = epub_path.stem
    produced = out_dir / epub_stem
    if not produced.exists():
        raise RuntimeError(
            f"epub2md did not produce expected output at {produced}. "
            f"Contents of {out_dir}: {list(out_dir.iterdir())}"
        )
    return produced
