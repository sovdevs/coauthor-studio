"""
Build a compact, model-facing style rule set from all available profile sources.
Output: profile/style_rules.json

Sources (in priority order):
  1. lexicon_profile note_signals  (explicit editorial notes)
  2. lexicon_profile derived_rules (corpus-observed tendencies)
  3. style_profile tendencies      (surface stats)

Also synthesises transformation_hints for the rewrite stage.
"""
from __future__ import annotations

import json
from pathlib import Path


# ---------------------------------------------------------------------------
# Keyword signals used to classify derived_rules into prefer / avoid
# ---------------------------------------------------------------------------

_AVOID_SIGNALS = (
    "avoids", "absent", "near-zero", "zero", "sparse", "rare",
    "unmarked", "prefers parataxis",
)
_PREFER_SIGNALS = (
    "prefers", "favors", "strongly", "dominant", "heavy", "high",
    "concrete", "physical", "short", "staccato",
)


def _classify_rule(rule: str) -> str:
    """Return 'prefer', 'avoid', or 'observe' for a derived rule string."""
    lower = rule.lower()
    if any(s in lower for s in _AVOID_SIGNALS):
        return "avoid"
    if any(s in lower for s in _PREFER_SIGNALS):
        return "prefer"
    return "observe"


# ---------------------------------------------------------------------------
# Transformation hint synthesis
# ---------------------------------------------------------------------------

def _derive_transformation_hints(
    prefer_rules: list[str],
    avoid_rules: list[str],
    lex_profile: dict,
) -> list[str]:
    hints: list[str] = []
    func = lex_profile.get("function_word_profile", {})
    verb_bias = lex_profile.get("verb_bias", {})
    phys_ratio = verb_bias.get("physical_verbs", {}).get("ratio", 0.5)
    semicolon_rate = func.get("semicolon_rate", 0.1)
    and_rate = func.get("and_rate", 0.02)

    if phys_ratio > 0.7:
        hints.append(
            "Replace cognitive summary with observable action or physical condition."
        )
    hints.append(
        "Reduce explanatory scaffolding around concrete events — show, don't frame."
    )
    if any("abstract" in r.lower() for r in prefer_rules):
        hints.append(
            "Move the strongest concrete noun toward the end of the sentence for impact."
        )
    if semicolon_rate < 0.01:
        hints.append(
            "Replace semicolons and subordinate conjunctions with a period or 'and'."
        )
    if and_rate > 0.04:
        hints.append(
            "Chain clauses or list items with 'and' to build polysyndetic rhythm."
        )
    hints.append(
        "Cut modifier stacks — one strong noun or verb is better than two qualified ones."
    )

    return hints


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_style_rules(
    writer_id: str,
    style_profile: dict,
    lex_profile: dict,
    out_dir: Path,
) -> dict:
    """
    Build and write style_rules.json from existing profile data.
    Returns the rules dict.
    """
    prefer_rules: list[str] = []
    avoid_rules: list[str] = []

    # 1. Note signals (highest editorial authority)
    note_signals = lex_profile.get("note_signals", {})
    for item in note_signals.get("preferred_features", []):
        rule = item.strip().rstrip(".")
        if rule and rule not in prefer_rules:
            prefer_rules.append(rule)
    for item in note_signals.get("avoid_features", []):
        rule = item.strip().rstrip(".")
        if rule and rule not in avoid_rules:
            avoid_rules.append(rule)

    # 2. Derived rules from lexicon profile
    for rule in lex_profile.get("derived_rules", []):
        cls = _classify_rule(rule)
        if cls == "prefer" and rule not in prefer_rules:
            prefer_rules.append(rule)
        elif cls == "avoid" and rule not in avoid_rules:
            avoid_rules.append(rule)

    # 3. Tendencies from style profile
    for rule in style_profile.get("tendencies", []):
        cls = _classify_rule(rule)
        if cls == "prefer" and rule not in prefer_rules:
            prefer_rules.append(rule)
        elif cls == "avoid" and rule not in avoid_rules:
            avoid_rules.append(rule)

    transformation_hints = _derive_transformation_hints(prefer_rules, avoid_rules, lex_profile)

    rules = {
        "writer_id": writer_id,
        "source_profiles": ["style_profile.json", "lexicon_profile.json"],
        "prefer_rules": prefer_rules,
        "avoid_rules": avoid_rules,
        "transformation_hints": transformation_hints,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "style_rules.json").write_text(
        json.dumps(rules, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return rules
