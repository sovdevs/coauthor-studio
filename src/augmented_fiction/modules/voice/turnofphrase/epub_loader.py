"""
Load one or more EPUBs and extract paragraph text.
Output: processed/extracted_text.json

Paragraph schema (new v2 format):
  {"text": "...", "source_file": "X_TheRoad.epub"}

The legacy single-source_file key is no longer written; downstream code
should use the per-paragraph source_file field.
"""
from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from ebooklib import epub

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

_MIN_PARA_CHARS = 30  # filter out titles, page numbers, etc.


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def load_epub(epub_path: Path) -> list[str]:
    """Return cleaned paragraph strings from a single EPUB file."""
    book = epub.read_epub(str(epub_path), options={"ignore_ncx": True})
    paragraphs: list[str] = []

    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "lxml")
        for tag in soup.find_all(["p", "div"]):
            if tag.find(["p", "div"]):
                continue
            text = _clean_text(tag.get_text(separator=" "))
            if len(text) >= _MIN_PARA_CHARS:
                paragraphs.append(text)

    return paragraphs


def extract_and_save(epub_path: Path, out_dir: Path, writer_id: str) -> dict:
    """
    Extract one EPUB and write extracted_text.json.
    Paragraphs are stored as dicts with source_file provenance.
    """
    paragraphs = load_epub(epub_path)
    result = {
        "writer_id": writer_id,
        "source_files": [epub_path.name],
        "paragraph_count": len(paragraphs),
        "paragraphs": [{"text": p, "source_file": epub_path.name} for p in paragraphs],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "extracted_text.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return result


def extract_all_and_save(epubs_dir: Path, out_dir: Path, writer_id: str) -> dict:
    """
    Scan epubs_dir for all *.epub files, extract all, and write one
    aggregated extracted_text.json sorted by filename.
    """
    epub_files = sorted(epubs_dir.glob("*.epub"))
    if not epub_files:
        raise FileNotFoundError(f"No EPUB files found in {epubs_dir}")

    all_paragraphs: list[dict] = []
    source_files: list[str] = []

    for epub_path in epub_files:
        paragraphs = load_epub(epub_path)
        source_files.append(epub_path.name)
        for para in paragraphs:
            all_paragraphs.append({"text": para, "source_file": epub_path.name})

    result = {
        "writer_id": writer_id,
        "source_files": source_files,
        "paragraph_count": len(all_paragraphs),
        "paragraphs": all_paragraphs,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "extracted_text.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return result
