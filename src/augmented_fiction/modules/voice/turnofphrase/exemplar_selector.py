"""
Select a compact set of exemplar passages from the full mode-labeled corpus.

Target: ~50 passages spread across modes, suitable for:
  - retrieval-augmented style guidance
  - seeding the LLM abstraction prompt

Output: processed/exemplar_passages.jsonl

Selection criteria:
  - word count 25–90 (self-contained, not too short or too long)
  - at least 2 sentences
  - not front matter / degenerate fragments
  - high signal for the passage's mode
  - no near-duplicates (bigram overlap filter)

Distribution targets (soft):
  action: 20, narrative: 15, reflective: 10, descriptive: 5
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MODE_TARGETS = {"action": 20, "narrative": 15, "reflective": 10, "descriptive": 5, "dialogue": 15}
_MIN_WORDS = 25
_MAX_WORDS = 90
_MIN_SENTS = 2
_DEDUP_BIGRAM_THRESHOLD = 0.55  # skip if >55% bigram overlap with already-selected

_FRONT_MATTER_RE = re.compile(
    r"^(chapter|book|part|prologue|epilogue|contents|copyright|isbn|all rights|"
    r"published by|printed in|first edition|acknowledgement|dedication)\b",
    re.IGNORECASE,
)
_ROMAN_ONLY_RE = re.compile(r"^[IVXLCDM\s\.]+$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bigrams(text: str) -> set[str]:
    words = text.lower().split()
    return {f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)}


def _bigram_overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _is_front_matter(text: str) -> bool:
    t = text.strip()
    if _ROMAN_ONLY_RE.match(t):
        return True
    if _FRONT_MATTER_RE.match(t):
        return True
    # Mostly uppercase → likely a title / header
    alpha = [c for c in t if c.isalpha()]
    if alpha and sum(1 for c in alpha if c.isupper()) / len(alpha) > 0.6:
        return True
    return False


def _mode_signal_score(features: dict, mode: str) -> float:
    """Higher score = more representative of the assigned mode."""
    if not features:
        return 0.0
    score = 0.0
    avg_len = features.get("avg_sentence_length", 10.0)
    phys = features.get("phys_verb_ratio", 0.5)
    cog = features.get("cog_verb_ratio", 0.5)
    abs_r = features.get("abstract_word_ratio", 0.0)
    wc = features.get("word_count", 0)

    # Prefer passages in the "sweet spot" word count
    if 35 <= wc <= 70:
        score += 0.2

    if mode == "action":
        score += phys * 0.5
        if avg_len < 10:
            score += 0.2
    elif mode == "reflective":
        score += cog * 0.4
        score += abs_r * 0.3
    elif mode == "descriptive":
        if 12 <= avg_len <= 22:
            score += 0.3
        score += abs_r * 0.2
    elif mode == "dialogue":
        # Reward short exchanges and high sentence density
        short_r = features.get("short_sentence_ratio", 0.5)
        sent_c = features.get("sentence_count", 1)
        score += short_r * 0.4
        if sent_c >= 3:
            score += 0.2
        if avg_len < 10:
            score += 0.2
    else:  # narrative
        if 8 <= avg_len <= 16:
            score += 0.3
        score += (1 - abs_r) * 0.2

    return round(score, 4)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def select_exemplars(
    mode_labeled_passages: list[dict],
    out_dir: Path,
    targets: dict[str, int] | None = None,
) -> list[dict]:
    """
    Select exemplar passages from mode-labeled corpus and write
    processed/exemplar_passages.jsonl.
    """
    targets = targets or _MODE_TARGETS

    # --- Pre-filter ---
    candidates: list[dict] = []
    for p in mode_labeled_passages:
        features = p.get("quick_features", {})
        wc = features.get("word_count", 0)
        sc = features.get("sentence_count", 0)
        if wc < _MIN_WORDS or wc > _MAX_WORDS:
            continue
        if sc < _MIN_SENTS:
            continue
        if _is_front_matter(p["text"]):
            continue
        score = _mode_signal_score(features, p["mode_guess"])
        candidates.append({**p, "_score": score, "_bigrams": _bigrams(p["text"])})

    # --- Group by mode and rank ---
    buckets: dict[str, list[dict]] = {
        "action": [], "reflective": [], "descriptive": [], "narrative": [], "dialogue": [],
    }
    for c in candidates:
        buckets[c["mode_guess"]].append(c)
        # Dialogue bucket uses dialogue_mode tag (orthogonal to mode_guess)
        if c.get("dialogue_mode") in ("dialogue", "mixed"):
            # Score dialogue-specific quality
            dlg_score = _mode_signal_score(c.get("quick_features", {}), "dialogue")
            buckets["dialogue"].append({**c, "_score": dlg_score})
    for mode in buckets:
        buckets[mode].sort(key=lambda x: x["_score"], reverse=True)

    # --- Select with dedup ---
    selected: list[dict] = []
    selected_bigrams: list[set[str]] = []

    for mode, target in targets.items():
        count = 0
        for candidate in buckets[mode]:
            if count >= target:
                break
            bg = candidate["_bigrams"]
            # Near-duplicate check
            if any(_bigram_overlap(bg, sb) > _DEDUP_BIGRAM_THRESHOLD for sb in selected_bigrams):
                continue
            selected.append(candidate)
            selected_bigrams.append(bg)
            count += 1

    # --- Build clean output records ---
    exemplars: list[dict] = []
    seen_ids: set[str] = set()
    for p in selected:
        pid = p["passage_id"]
        if pid in seen_ids:
            continue
        seen_ids.add(pid)
        exemplars.append({
            "writer_id": p["writer_id"],
            "source_file": p["source_file"],
            "passage_id": pid,
            "text": p["text"],
            "mode_guess": p["mode_guess"],
            "dialogue_mode": p.get("dialogue_mode", "narrative"),
            "features": p.get("quick_features", {}),
        })

    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "exemplar_passages.jsonl").open("w", encoding="utf-8") as fh:
        for e in exemplars:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")

    return exemplars
