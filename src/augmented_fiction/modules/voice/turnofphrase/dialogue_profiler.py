"""
Dialogue profile builder.

Analyses corpus passages tagged as dialogue or mixed to produce
aggregate dialogue statistics.

Output: profile/dialogue_profile.json

Fields:
  dialogue_passage_count    — passages tagged dialogue
  mixed_passage_count       — passages tagged mixed
  avg_sentence_length       — mean sentence length in dialogue passages
  short_sentence_ratio      — ratio of sentences ≤ 7 words
  attribution_rate          — attribution verbs per sentence (proxy for speaker tags)
  question_ratio            — fraction of sentences ending with ?
  turn_length_distribution  — p25 / median / p75 of per-sentence word counts
  no_attribution_ratio      — fraction of dialogue with zero attribution verbs
"""
from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

from .passage_segmenter import _ATTRIBUTION_VERBS, _SENT_SPLIT_RE


def build_dialogue_profile(
    passages: list[dict],
    writer_id: str,
    out_dir: Path,
) -> dict:
    """
    Build dialogue_profile.json from mode-labeled passages.
    Passages must have a `dialogue_mode` field.
    """
    dialogue_passages = [
        p for p in passages if p.get("dialogue_mode") in ("dialogue", "mixed")
    ]
    dialogue_only = [p for p in passages if p.get("dialogue_mode") == "dialogue"]

    if not dialogue_passages:
        result = {
            "writer_id": writer_id,
            "dialogue_passage_count": 0,
            "mixed_passage_count": 0,
            "note": "No dialogue passages found in corpus.",
        }
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "dialogue_profile.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return result

    # Collect all sentences from dialogue passages
    all_sent_lengths: list[int] = []
    attr_per_passage: list[float] = []
    question_flags: list[bool] = []

    for p in dialogue_passages:
        text = p["text"]
        sents = [s.strip() for s in _SENT_SPLIT_RE.split(text) if s.strip()]
        if not sents:
            continue

        words_per_sent = [len(s.split()) for s in sents]
        all_sent_lengths.extend(words_per_sent)

        passage_words = re.findall(r"\b\w+\b", text.lower())
        attr_hits = sum(1 for w in passage_words if w in _ATTRIBUTION_VERBS)
        attr_per_passage.append(attr_hits / len(sents))

        question_flags.extend(["?" in s for s in text.split(".")])

    if not all_sent_lengths:
        all_sent_lengths = [0]

    avg_len = round(statistics.mean(all_sent_lengths), 2)
    short_ratio = round(
        sum(1 for l in all_sent_lengths if l <= 7) / len(all_sent_lengths), 4
    )
    attribution_rate = round(statistics.mean(attr_per_passage), 4) if attr_per_passage else 0.0
    no_attr_ratio = round(
        sum(1 for r in attr_per_passage if r == 0) / len(attr_per_passage), 4
    ) if attr_per_passage else 0.0
    question_ratio = round(
        sum(1 for f in question_flags if f) / len(question_flags), 4
    ) if question_flags else 0.0

    # Turn length distribution (sentence word counts)
    sorted_lens = sorted(all_sent_lengths)
    n = len(sorted_lens)
    turn_dist = {
        "p25": sorted_lens[n // 4],
        "median": sorted_lens[n // 2],
        "p75": sorted_lens[3 * n // 4],
    }

    result = {
        "writer_id": writer_id,
        "dialogue_passage_count": len(dialogue_only),
        "mixed_passage_count": len(dialogue_passages) - len(dialogue_only),
        "avg_sentence_length": avg_len,
        "short_sentence_ratio": short_ratio,
        "attribution_rate": attribution_rate,
        "no_attribution_ratio": no_attr_ratio,
        "question_ratio": question_ratio,
        "turn_length_distribution": turn_dist,
        "sentence_length_distribution": {
            "mean": avg_len,
            "p25": turn_dist["p25"],
            "median": turn_dist["median"],
            "p75": turn_dist["p75"],
        },
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "dialogue_profile.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return result
