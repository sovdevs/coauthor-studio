"""
Segment extracted paragraphs into passages.
V1: one paragraph = one passage.
Output: processed/passages.jsonl

Handles both paragraph formats:
  - v2 (current): {"text": "...", "source_file": "..."}
  - v1 (legacy):  plain string (single source_file from extracted root)

Each passage is tagged with `dialogue_mode`: "dialogue" | "mixed" | "narrative"
using a fast heuristic (no POS). This tag drives dialogue retrieval in Phase 3+.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Dialogue mode tagger
# ---------------------------------------------------------------------------

_ATTRIBUTION_VERBS = frozenset([
    "said", "says", "asked", "asks", "answered", "replied", "told",
    "whispered", "shouted", "muttered", "called", "cried", "began",
])

_SENT_SPLIT_RE = re.compile(r"[.!?]+")


def _tag_dialogue_mode(text: str) -> str:
    """
    Classify a passage as 'dialogue', 'mixed', or 'narrative'.

    Heuristics:
      - attribution verb count (said, asked, etc.)
      - short-sentence ratio (proxy for terse spoken exchange)
      - question mark density
    """
    words = re.findall(r"\b\w+\b", text.lower())
    attr_hits = sum(1 for w in words if w in _ATTRIBUTION_VERBS)

    sents = [s.strip() for s in _SENT_SPLIT_RE.split(text) if s.strip()]
    if not sents:
        return "narrative"

    short_sents = sum(1 for s in sents if len(s.split()) <= 8)
    short_ratio = short_sents / len(sents)
    question_count = text.count("?")

    score = 0
    if attr_hits >= 2:
        score += 3
    elif attr_hits == 1:
        score += 1
    if short_ratio > 0.5:
        score += 2
    if question_count >= 1:
        score += 1

    if score >= 4:
        return "dialogue"
    if score >= 2:
        return "mixed"
    return "narrative"


def segment(
    extracted: dict,
    out_dir: Path,
    boundaries: dict | None = None,
) -> list[dict]:
    """
    Create passages from extracted_text dict and write passages.jsonl.

    boundaries: optional dict loaded from corpus_boundaries.json.
      Format: { "source_file.epub": { "start_passage_id": "000045" }, ... }
      Passages whose global passage_id (int) is below the configured threshold
      for their source_file are excluded from the output.
      When None, all passages are included (existing behavior).
    """
    writer_id = extracted["writer_id"]

    # Support both legacy single source_file and new per-paragraph source_file
    default_source = extracted.get(
        "source_file",
        (extracted.get("source_files") or ["unknown"])[0],
    )

    # Pre-process boundaries into {source_file: int(start_passage_id)}
    _starts: dict[str, int] = {}
    if boundaries:
        for sf, cfg in boundaries.items():
            try:
                _starts[sf] = int(cfg.get("start_passage_id", "0"))
            except (ValueError, TypeError):
                pass

    passages: list[dict] = []
    skipped = 0
    for idx, para_entry in enumerate(extracted["paragraphs"], start=1):
        if isinstance(para_entry, dict):
            text = para_entry["text"]
            source_file = para_entry.get("source_file", default_source)
        else:
            text = para_entry
            source_file = default_source

        # Boundary check: skip if idx < configured start for this source_file
        if source_file in _starts and idx < _starts[source_file]:
            skipped += 1
            continue

        passages.append(
            {
                "writer_id": writer_id,
                "source_file": source_file,
                "passage_id": f"{idx:06d}",
                "text": text,
                "dialogue_mode": _tag_dialogue_mode(text),
            }
        )

    if skipped:
        print(f"  [corpus_boundaries] skipped {skipped} passages before configured start IDs")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "passages.jsonl"
    with out_path.open("w", encoding="utf-8") as fh:
        for p in passages:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")

    return passages
