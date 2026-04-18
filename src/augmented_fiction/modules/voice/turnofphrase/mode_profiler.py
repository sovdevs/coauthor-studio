"""
Assign mode labels to passages (fast, no POS tagging) and compute
per-mode aggregate statistics.

Fast mode detection uses word matching against verb sets + abstract suffix
heuristics. This avoids a third POS pass over the full corpus.

Outputs:
  processed/passage_modes.jsonl  — one line per passage: id + mode + quick stats
  profile/mode_profiles.json     — per-mode aggregate stats
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from nltk.tokenize import sent_tokenize, word_tokenize

from .style_profiler import _ensure_nltk_data, SHORT_SENT_THRESHOLD
from .lexicon_profiler import _PHYSICAL_VERBS, _COGNITIVE_VERBS, _ABSTRACT_SUFFIXES


# ---------------------------------------------------------------------------
# Fast per-passage features (no POS)
# ---------------------------------------------------------------------------

def _quick_features(text: str) -> dict:
    """Compute key features using only word matching — no POS tagging."""
    sents = sent_tokenize(text)
    tokens = [w.lower() for w in word_tokenize(text) if w.isalpha()]
    total = len(tokens)

    if not tokens or not sents:
        return {}

    sent_lens = [len(s.split()) for s in sents]
    avg_len = statistics.mean(sent_lens)

    phys_count = sum(1 for w in tokens if w in _PHYSICAL_VERBS)
    cog_count = sum(1 for w in tokens if w in _COGNITIVE_VERBS)
    total_biased = phys_count + cog_count

    # Abstract word ratio via suffix matching (proxy, not POS-gated)
    abstract_count = sum(
        1 for w in tokens if len(w) > 4 and any(w.endswith(s) for s in _ABSTRACT_SUFFIXES)
    )

    return {
        "word_count": total,
        "sentence_count": len(sents),
        "avg_sentence_length": round(avg_len, 2),
        "short_sentence_ratio": round(
            sum(1 for l in sent_lens if l <= SHORT_SENT_THRESHOLD) / len(sent_lens), 4
        ),
        "phys_verb_ratio": round(phys_count / total_biased, 4) if total_biased else 0.5,
        "cog_verb_ratio": round(cog_count / total_biased, 4) if total_biased else 0.5,
        "abstract_word_ratio": round(abstract_count / total, 4) if total else 0.0,
    }


def _assign_mode(features: dict) -> str:
    if not features:
        return "narrative"
    cog = features.get("cog_verb_ratio", 0.0)
    abs_r = features.get("abstract_word_ratio", 0.0)
    phys = features.get("phys_verb_ratio", 0.0)
    avg_len = features.get("avg_sentence_length", 10.0)

    if cog > 0.35 or abs_r > 0.12:
        return "reflective"
    if avg_len > 16 and abs_r > 0.05:
        return "descriptive"
    if phys > 0.55 and avg_len < 13:
        return "action"
    return "narrative"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_mode_profiles(
    passages: list[dict],
    writer_id: str,
    processed_dir: Path,
    profile_dir: Path,
) -> tuple[list[dict], dict]:
    """
    Assign mode to each passage, write passage_modes.jsonl and mode_profiles.json.
    Returns (mode_labeled_passages, mode_profiles_dict).
    """
    _ensure_nltk_data()

    mode_labeled: list[dict] = []
    mode_buckets: dict[str, list[dict]] = {
        "action": [], "reflective": [], "descriptive": [], "narrative": [],
    }

    for passage in passages:
        features = _quick_features(passage["text"])
        mode = _assign_mode(features)
        labeled = {
            **passage,
            "mode_guess": mode,
            "quick_features": features,
            # Carry dialogue_mode tag from segmenter (may be absent in legacy passages)
            "dialogue_mode": passage.get("dialogue_mode", "narrative"),
        }
        mode_labeled.append(labeled)
        mode_buckets[mode].append(features)

    # Write passage_modes.jsonl
    processed_dir.mkdir(parents=True, exist_ok=True)
    with (processed_dir / "passage_modes.jsonl").open("w", encoding="utf-8") as fh:
        for p in mode_labeled:
            row = {
                "passage_id": p["passage_id"],
                "source_file": p["source_file"],
                "mode_guess": p["mode_guess"],
                "dialogue_mode": p.get("dialogue_mode", "narrative"),
                **p["quick_features"],
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Aggregate per-mode stats
    def _agg(bucket: list[dict]) -> dict:
        if not bucket:
            return {"passage_count": 0}
        keys = ["avg_sentence_length", "short_sentence_ratio", "phys_verb_ratio",
                "cog_verb_ratio", "abstract_word_ratio"]
        agg = {"passage_count": len(bucket)}
        for k in keys:
            vals = [b[k] for b in bucket if k in b]
            if vals:
                agg[k] = round(statistics.mean(vals), 4)
        return agg

    mode_profiles = {
        "writer_id": writer_id,
        "modes": {mode: _agg(bucket) for mode, bucket in mode_buckets.items()},
    }

    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "mode_profiles.json").write_text(
        json.dumps(mode_profiles, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return mode_labeled, mode_profiles
