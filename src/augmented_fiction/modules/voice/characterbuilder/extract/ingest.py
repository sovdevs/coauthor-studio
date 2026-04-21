"""
Load book text from an author package directory.

Priority order:
1. processed/passages.jsonl  — preferred; already segmented with dialogue_mode
2. processed/extracted_text.json — paragraph list, no dialogue classification
3. epubs/*.epub — EPUB fallback; extracts raw text via ebooklib
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Passage:
    text: str
    source_file: str
    passage_id: str
    dialogue_mode: str   # "narrative" | "mixed" | "dialogue" | "unknown"


def load_passages(author_dir: Path) -> tuple[list[Passage], str]:
    """
    Load text passages from an author package directory.

    Returns (passages, source_description) where source_description
    names which source was used (for display).
    """
    processed = author_dir / "processed"

    # 1. passages.jsonl — richest source
    passages_jsonl = processed / "passages.jsonl"
    if passages_jsonl.exists():
        passages = _from_passages_jsonl(passages_jsonl)
        if passages:
            return passages, "processed/passages.jsonl"

    # 2. extracted_text.json — paragraph list
    extracted_json = processed / "extracted_text.json"
    if extracted_json.exists():
        passages = _from_extracted_text(extracted_json)
        if passages:
            return passages, "processed/extracted_text.json"

    # 3. EPUB fallback
    epub_dir = author_dir / "epubs"
    if epub_dir.exists():
        epubs = sorted(epub_dir.glob("*.epub"))
        if epubs:
            passages = _from_epubs(epubs)
            if passages:
                return passages, f"epubs/ ({len(epubs)} file(s))"

    raise FileNotFoundError(
        f"No text source found in {author_dir}.\n"
        "Expected one of:\n"
        "  processed/passages.jsonl\n"
        "  processed/extracted_text.json\n"
        "  epubs/*.epub"
    )


# ── Loaders ───────────────────────────────────────────────────────────────────

def _from_passages_jsonl(path: Path) -> list[Passage]:
    passages: list[Passage] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = d.get("text", "").strip()
        if not text:
            continue
        passages.append(Passage(
            text=text,
            source_file=d.get("source_file", ""),
            passage_id=d.get("passage_id", str(i)),
            dialogue_mode=d.get("dialogue_mode", "unknown"),
        ))
    return passages


def _from_extracted_text(path: Path) -> list[Passage]:
    data = json.loads(path.read_text(encoding="utf-8"))
    paragraphs = data.get("paragraphs", [])
    passages: list[Passage] = []
    for i, p in enumerate(paragraphs):
        if isinstance(p, dict):
            text = p.get("text", "").strip()
            source = p.get("source_file", "")
        else:
            text = str(p).strip()
            source = ""
        if not text:
            continue
        passages.append(Passage(
            text=text,
            source_file=source,
            passage_id=str(i),
            dialogue_mode="unknown",
        ))
    return passages


def _from_epubs(epub_paths: list[Path]) -> list[Passage]:
    """Minimal EPUB text extraction using ebooklib."""
    try:
        import ebooklib
        from ebooklib import epub as ebooklib_epub
    except ImportError:
        raise ImportError(
            "ebooklib is required for direct EPUB parsing. "
            "Install with: uv add ebooklib"
        )

    from html.parser import HTMLParser

    class _BlockExtractor(HTMLParser):
        BLOCK_TAGS = {"p", "div", "li", "blockquote", "section", "article"}

        def __init__(self) -> None:
            super().__init__()
            self.chunks: list[str] = []
            self._buf: list[str] = []

        def handle_data(self, data: str) -> None:
            self._buf.append(data)

        def handle_endtag(self, tag: str) -> None:
            if tag in self.BLOCK_TAGS:
                text = " ".join(self._buf).strip()
                if len(text) >= 30:
                    self.chunks.append(text)
                self._buf = []

    passages: list[Passage] = []
    pid = 0
    for epub_path in epub_paths:
        book = ebooklib_epub.read_epub(str(epub_path))
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            extractor = _BlockExtractor()
            extractor.feed(item.get_content().decode("utf-8", errors="replace"))
            for chunk in extractor.chunks:
                passages.append(Passage(
                    text=chunk,
                    source_file=epub_path.name,
                    passage_id=str(pid),
                    dialogue_mode="unknown",
                ))
                pid += 1
    return passages
