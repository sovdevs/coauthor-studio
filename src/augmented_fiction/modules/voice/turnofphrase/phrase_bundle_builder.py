"""
Extract phrase bundles from the full corpus into a standalone artifact.
Output: profile/phrase_bundles.json

Pulls phraseological data from the already-computed style_profile dict,
so no re-tokenization is needed.
"""
from __future__ import annotations

import json
from pathlib import Path


def build_phrase_bundles(style_profile: dict, out_dir: Path) -> dict:
    """
    Extract phrase bundle data from style_profile and write phrase_bundles.json.
    Returns the bundles dict.
    """
    phrase = style_profile.get("phraseological", {})
    rhythm = style_profile.get("rhythm", {})

    bundles = {
        "writer_id": style_profile["writer_id"],
        "source_files": style_profile.get("source_files", [style_profile.get("source_file", "")]),
        "bigrams": phrase.get("top_bigrams", []),
        "trigrams": phrase.get("top_trigrams", []),
        "fourgrams": phrase.get("top_fourgrams", []),
        "fivegrams": phrase.get("top_fivegrams", []),
        "sentence_starters": phrase.get("recurring_sentence_starters", []),
        "sentence_enders": phrase.get("recurring_sentence_enders", []),
        "rhythm_summary": {
            "avg_sentence_length": rhythm.get("avg_sentence_length"),
            "median_sentence_length": rhythm.get("median_sentence_length"),
            "short_sentence_ratio": rhythm.get("short_sentence_ratio"),
            "long_sentence_ratio": rhythm.get("long_sentence_ratio"),
        },
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "phrase_bundles.json").write_text(
        json.dumps(bundles, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return bundles
