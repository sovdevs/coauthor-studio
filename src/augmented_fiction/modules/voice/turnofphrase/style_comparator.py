"""
Compare user text against a writer style profile.

vNext: distribution-aware comparison with drift classification, mode detection,
and scaled suggestions.
"""
from __future__ import annotations

import json
import re
import statistics
from pathlib import Path
from typing import Literal

import nltk

from .style_profiler import (
    _ADJ_TAGS,
    _ADV_TAGS,
    _NOUN_TAGS,
    _ensure_nltk_data,
    _is_abstract_noun,
    _ngrams,
    _tokenize_sentences,
    _tokenize_words,
    LONG_SENT_THRESHOLD,
    SHORT_SENT_THRESHOLD,
)
from .lexicon_profiler import _PHYSICAL_VERBS, _COGNITIVE_VERBS
from .retriever import retrieve_exemplars

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

DriftLevel = Literal["none", "mild", "moderate", "strong"]
Alignment = Literal["aligned", "mostly_aligned", "drifting", "off_style"]
FeatureClass = Literal["in_range", "near_edge", "out_of_range"]
PassageMode = Literal["action", "descriptive", "reflective", "dialogue", "narrative"]

_DRIFT_TO_ALIGNMENT: dict[DriftLevel, Alignment] = {
    "none": "aligned",
    "mild": "mostly_aligned",
    "moderate": "drifting",
    "strong": "off_style",
}

# ---------------------------------------------------------------------------
# User feature computation
# ---------------------------------------------------------------------------

def _compute_features(text: str) -> dict:
    """Compute per-passage feature values for the user text."""
    _ensure_nltk_data()

    sents = _tokenize_sentences(text)
    sent_word_lists: list[list[str]] = []
    all_tagged: list[tuple[str, str]] = []

    for sent in sents:
        words = _tokenize_words(sent)
        if words:
            sent_word_lists.append(words)
            all_tagged.extend(nltk.pos_tag(words))

    if not sent_word_lists:
        return {}

    sent_lengths = [len(s) for s in sent_word_lists]
    total_words = len(all_tagged)

    adj_count = sum(1 for _, tag in all_tagged if tag in _ADJ_TAGS)
    adv_count = sum(1 for _, tag in all_tagged if tag in _ADV_TAGS)
    noun_count = sum(1 for _, tag in all_tagged if tag in _NOUN_TAGS)
    abstract_count = sum(1 for word, tag in all_tagged if _is_abstract_noun(word, tag))
    phys_count = sum(
        1 for w, tag in all_tagged
        if tag.startswith("VB") and w.lower() in _PHYSICAL_VERBS
    )
    cog_count = sum(
        1 for w, tag in all_tagged
        if tag.startswith("VB") and w.lower() in _COGNITIVE_VERBS
    )
    total_biased = phys_count + cog_count

    ngram_set: set[str] = set()
    for words in sent_word_lists:
        lw = [w.lower() for w in words]
        for n in (2, 3):
            for bundle in _ngrams(lw, n):
                ngram_set.add(" ".join(bundle))

    and_count = len(re.findall(r"\band\b", text, flags=re.IGNORECASE))
    semicolon_count = text.count(";")
    sentence_count = len(sent_lengths)

    return {
        "sentence_count": sentence_count,
        "avg_sentence_length": statistics.mean(sent_lengths),
        "median_sentence_length": float(statistics.median(sent_lengths)),
        "short_sentence_ratio": (
            sum(1 for l in sent_lengths if l <= SHORT_SENT_THRESHOLD) / sentence_count
        ),
        "long_sentence_ratio": (
            sum(1 for l in sent_lengths if l >= LONG_SENT_THRESHOLD) / sentence_count
        ),
        "adj_rate": adj_count / total_words if total_words else 0.0,
        "adv_rate": adv_count / total_words if total_words else 0.0,
        "abstract_noun_ratio": abstract_count / noun_count if noun_count else 0.0,
        "concrete_noun_ratio": (noun_count - abstract_count) / noun_count if noun_count else 0.0,
        "phys_verb_ratio": phys_count / total_biased if total_biased else 0.5,
        "cog_verb_ratio": cog_count / total_biased if total_biased else 0.5,
        "and_rate": and_count / total_words if total_words else 0.0,
        "semicolons_per_sentence": semicolon_count / sentence_count,
        "ngrams": ngram_set,
    }


# ---------------------------------------------------------------------------
# Drift classification
# ---------------------------------------------------------------------------

def _classify_feature(value: float, dist: dict) -> FeatureClass:
    """Classify a single value against the author's distribution."""
    if not dist:
        return "in_range"
    p10, p25, p75, p90 = dist["p10"], dist["p25"], dist["p75"], dist["p90"]
    if p25 <= value <= p75:
        return "in_range"
    if p10 <= value <= p90:
        return "near_edge"
    return "out_of_range"


def _aggregate_drift(classifications: dict[str, FeatureClass]) -> DriftLevel:
    out = sum(1 for v in classifications.values() if v == "out_of_range")
    near = sum(1 for v in classifications.values() if v == "near_edge")
    if out == 0 and near == 0:
        return "none"
    if out == 0:
        return "mild"
    if out <= 2:
        return "moderate"
    return "strong"


# ---------------------------------------------------------------------------
# Mode detection
# ---------------------------------------------------------------------------

def _detect_mode(user: dict) -> PassageMode:
    """
    Heuristic classification of the passage mode.
    Prevents penalising valid stylistic variation (e.g. reflective passages).
    """
    cog = user.get("cog_verb_ratio", 0.0)
    abs_ratio = user.get("abstract_noun_ratio", 0.0)
    adj = user.get("adj_rate", 0.0)
    phys = user.get("phys_verb_ratio", 0.0)
    avg_len = user.get("avg_sentence_length", 10.0)

    # Reflective: cognitive-heavy or abstract-heavy
    if cog > 0.35 or abs_ratio > 0.15:
        return "reflective"
    # Descriptive: adjective-heavy
    if adj > 0.09:
        return "descriptive"
    # Action: physical-heavy + short sentences
    if phys > 0.55 and avg_len < 14:
        return "action"
    return "narrative"


# ---------------------------------------------------------------------------
# Per-feature feedback generators
# ---------------------------------------------------------------------------

def _feedback_sentence_length(val: float, dist: dict, cls: FeatureClass) -> tuple[str | None, str | None]:
    if cls == "in_range":
        return None, None
    p10, p90, median = dist["p10"], dist["p90"], dist["median"]
    high = val > dist["p75"]
    if high:
        if cls == "out_of_range":
            return (
                f"Sentence length is notably higher than the author's range "
                f"({val:.1f} words; author p10–p90: {p10:.0f}–{p90:.0f} words).",
                f"Break longer sentences into shorter declarative units. "
                f"Aim for roughly {median:.0f} words per sentence.",
            )
        return (
            f"Sentences run somewhat longer than the author's central range "
            f"({val:.1f} words; author median: {median:.0f}).",
            "Consider tightening the longer sentences.",
        )
    else:
        if cls == "out_of_range":
            return (
                f"Sentences are considerably shorter than the author's typical range ({val:.1f} words).",
                None,
            )
        return (
            "Sentences are somewhat shorter than the author's central range.",
            None,
        )


def _feedback_short_sentence_ratio(val: float, dist: dict, cls: FeatureClass, mode: PassageMode) -> tuple[str | None, str | None]:
    if cls == "in_range":
        return None, None
    mean = dist["mean"]
    low = val < dist["p25"]
    if low:
        if mode == "reflective":
            # Reflective passages naturally have longer sentences — soften
            if cls == "out_of_range":
                return (
                    f"Very few short sentences ({val:.0%} vs author baseline {mean:.0%}), "
                    "which suits a reflective register but moves away from the author's default rhythm.",
                    None,
                )
            return None, None
        if cls == "out_of_range":
            return (
                f"Notably fewer short sentences than typical for this style "
                f"({val:.0%} vs author baseline {mean:.0%}) — the staccato rhythm is subdued.",
                "Introduce short, complete declarative sentences to interrupt the longer ones.",
            )
        return (
            f"Fewer short sentences than the author's typical baseline ({val:.0%} vs {mean:.0%}).",
            "Try breaking one longer sentence into two shorter ones.",
        )
    else:
        # More short sentences than baseline — fine for most authors
        if cls == "out_of_range":
            return (
                f"Unusually high density of short sentences ({val:.0%}).",
                None,
            )
        return None, None


def _feedback_abstract_noun_ratio(val: float, dist: dict, cls: FeatureClass, mode: PassageMode) -> tuple[str | None, str | None]:
    if cls == "in_range":
        return None, None
    mean = dist["mean"]
    high = val > dist["p75"]
    if high:
        if mode == "reflective":
            if cls == "out_of_range":
                return (
                    f"Noun vocabulary is significantly more abstract ({val:.0%}) than the author's typical "
                    f"register ({mean:.0%}). Even in a reflective passage, some concretisation would help.",
                    "Ground at least one abstract noun in a physical image or object.",
                )
            return (
                f"Noun vocabulary leans more abstract ({val:.0%}) than the author's baseline ({mean:.0%}), "
                "though the reflective register partly accounts for this.",
                None,
            )
        if cls == "out_of_range":
            return (
                f"Noun vocabulary is considerably more abstract ({val:.0%}) than "
                f"the author's typical register ({mean:.0%}).",
                "Replace at least one abstract noun with a concrete object, action, or image.",
            )
        return (
            f"Noun vocabulary leans somewhat more abstract ({val:.0%}) than the author's baseline ({mean:.0%}).",
            "Consider swapping one abstract noun for something physical or visible.",
        )
    # More concrete than baseline — no problem for this author
    return None, None


def _feedback_physical_verb_ratio(val: float, dist: dict, cls: FeatureClass, mode: PassageMode) -> tuple[str | None, str | None]:
    if cls == "in_range":
        return None, None
    mean = dist["mean"]
    low = val < dist["p25"]
    if low:
        if mode == "reflective":
            if cls == "out_of_range":
                return (
                    f"Verb selection is considerably more cognitive ({val:.0%} physical) than "
                    f"the author's action-dominant baseline ({mean:.0%}). "
                    "Reflective register explains some of this, but a physical anchor would help.",
                    "Add one physical verb or sensory detail to ground the reflection.",
                )
            return None, None  # near_edge reflective is fine
        if cls == "out_of_range":
            return (
                f"Verb profile is notably more cognitive than the author's action-dominant baseline "
                f"({val:.0%} physical vs {mean:.0%} typical).",
                "Replace one cognitive verb with a physical action — show the body doing something.",
            )
        return (
            f"Verb selection is less action-oriented than the author's typical style "
            f"({val:.0%} physical vs {mean:.0%}).",
            "Consider grounding one moment in physical action.",
        )
    # More physical than baseline — not a problem
    return None, None


def _feedback_and_rate(val: float, dist: dict, cls: FeatureClass) -> tuple[str | None, str | None]:
    if cls == "in_range":
        return None, None
    mean = dist["mean"]
    low = val < dist["p25"]
    if low:
        if cls == "out_of_range":
            return (
                f"Very low use of 'and' as connective ({val:.1%} vs author baseline {mean:.1%}) — "
                "the polysyndetic rhythm is largely absent.",
                "Try chaining two clauses or list items with 'and' instead of punctuation.",
            )
        return (
            f"Less polysyndetic than the author's typical baseline ({val:.1%} vs {mean:.1%}).",
            None,
        )
    # High 'and' rate — not a problem for this kind of author
    return None, None


# ---------------------------------------------------------------------------
# Sentence-level drift
# ---------------------------------------------------------------------------

def _sentence_level_drift(
    user_text: str,
    dist: dict,
    user_features: dict,
) -> list[dict]:
    """Identify the top 2–3 sentences that diverge most from the author's range."""
    sents = _tokenize_sentences(user_text)
    if len(sents) < 2:
        return []

    sent_dist = dist.get("sentence_length", {})
    if not sent_dist:
        return []

    median = sent_dist.get("median", 10.0)
    spread = max(sent_dist.get("p90", 20.0) - sent_dist.get("p10", 4.0), 1.0)
    p90 = sent_dist.get("p90", 20.0)
    p10 = sent_dist.get("p10", 4.0)

    scored: list[tuple[float, str, str]] = []
    for sent in sents:
        words = _tokenize_words(sent)
        if not words:
            continue
        wlen = len(words)
        length_score = abs(wlen - median) / spread

        tagged = nltk.pos_tag(words)
        noun_count = sum(1 for _, tag in tagged if tag in _NOUN_TAGS)
        abstract_count = sum(1 for w, tag in tagged if _is_abstract_noun(w, tag))
        cog_count = sum(1 for w, tag in tagged
                        if tag.startswith("VB") and w.lower() in _COGNITIVE_VERBS)
        total_tagged = len(tagged) or 1

        abstract_score = (abstract_count / noun_count) if noun_count else 0
        cog_score = cog_count / total_tagged

        total_score = length_score + abstract_score * 0.5 + cog_score * 0.5

        reasons: list[str] = []
        if wlen > p90:
            reasons.append(f"long sentence ({wlen} words)")
        elif wlen < p10:
            reasons.append(f"unusually short ({wlen} words)")
        if abstract_count > 0:
            reasons.append("abstract nouns")
        if cog_count > 0:
            reasons.append("cognitive verbs")

        if reasons:
            scored.append((total_score, sent, ", ".join(reasons)))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {"sentence": s, "reason": r}
        for _, s, r in scored[:2]
    ]


# ---------------------------------------------------------------------------
# Suggestion scaling
# ---------------------------------------------------------------------------

def _scale_suggestions(suggestions: list[str], drift_level: DriftLevel) -> list[str]:
    if drift_level == "none":
        return []
    if drift_level == "mild":
        return [f"Optional: {s[0].lower()}{s[1:]}" for s in suggestions if s]
    if drift_level == "strong":
        return [f"↑ {s}" for s in suggestions if s]
    return [s for s in suggestions if s]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def analyze_against_writer_style(
    user_text: str,
    writer_id: str,
    profile_path: Path,
    exemplar_path: Path | None = None,
    n_exemplars: int = 5,
) -> dict:
    # --- Load profiles ---
    with profile_path.open(encoding="utf-8") as fh:
        style_profile = json.load(fh)

    lex_profile_path = profile_path.parent / "lexicon_profile.json"
    lex_profile: dict | None = None
    if lex_profile_path.exists():
        with lex_profile_path.open(encoding="utf-8") as fh:
            lex_profile = json.load(fh)

    dist_path = profile_path.parent / "feature_distributions.json"
    distributions: dict = {}
    if dist_path.exists():
        with dist_path.open(encoding="utf-8") as fh:
            distributions = json.load(fh)

    # --- Compute user features ---
    user = _compute_features(user_text)
    if not user:
        return {"error": "Could not parse user text — check that it contains full sentences."}

    # --- Map user features to distribution keys ---
    feature_map: dict[str, float] = {
        "sentence_length": user["avg_sentence_length"],
        "short_sentence_ratio": user["short_sentence_ratio"],
        "abstract_noun_ratio": user["abstract_noun_ratio"],
        "physical_verb_ratio": user["phys_verb_ratio"],
        "and_rate": user["and_rate"],
    }

    # --- Classify each feature ---
    mode = _detect_mode(user)

    classifications: dict[str, FeatureClass] = {}
    for feat, val in feature_map.items():
        dist = distributions.get(feat, {})
        classifications[feat] = _classify_feature(val, dist)

    # --- Aggregate drift ---
    drift_level = _aggregate_drift(classifications)

    # Soften drift level when passage is reflective and the only out-of-range
    # features are the ones naturally elevated in a reflective register
    if mode == "reflective":
        reflective_features = {"abstract_noun_ratio", "physical_verb_ratio"}
        non_reflective_out = [
            f for f, c in classifications.items()
            if c == "out_of_range" and f not in reflective_features
        ]
        if not non_reflective_out and drift_level in ("moderate", "strong"):
            drift_level = "mild"

    style_alignment = _DRIFT_TO_ALIGNMENT[drift_level]

    # --- Generate feedback ---
    raw_diffs: list[str] = []
    raw_suggestions: list[str] = []

    if drift_level == "none":
        raw_diffs.append("This passage is fully aligned with the author's style.")
    else:
        for feat, cls in classifications.items():
            if cls == "in_range":
                continue
            dist = distributions.get(feat, {})
            val = feature_map[feat]

            diff, sugg = None, None
            if feat == "sentence_length":
                diff, sugg = _feedback_sentence_length(val, dist, cls)
            elif feat == "short_sentence_ratio":
                diff, sugg = _feedback_short_sentence_ratio(val, dist, cls, mode)
            elif feat == "abstract_noun_ratio":
                diff, sugg = _feedback_abstract_noun_ratio(val, dist, cls, mode)
            elif feat == "physical_verb_ratio":
                diff, sugg = _feedback_physical_verb_ratio(val, dist, cls, mode)
            elif feat == "and_rate":
                diff, sugg = _feedback_and_rate(val, dist, cls)

            if diff:
                raw_diffs.append(diff)
            if sugg:
                raw_suggestions.append(sugg)

        # Lexicon-layer checks (use lex_profile if available)
        if lex_profile:
            ref_func = lex_profile.get("function_word_profile", {})
            r_semi = ref_func.get("semicolon_rate", 0.0)
            u_semi = user["semicolons_per_sentence"]
            if u_semi > r_semi + 0.05:
                raw_diffs.append(
                    f"Semicolons present ({u_semi:.2f} per sentence) — "
                    "this author strongly avoids them."
                )
                raw_suggestions.append(
                    "Replace semicolons with a period or 'and'. "
                    "This style prefers parataxis over logical linkage."
                )

        if not raw_diffs:
            raw_diffs.append(
                "This passage is broadly within the author's style range, "
                "with minor variations."
            )

    # --- Scale suggestions by drift level ---
    edit_suggestions = _scale_suggestions(raw_suggestions, drift_level)

    # --- Rewrite candidates (gated by drift) ---
    rewrite_candidates: list[dict] = []
    ref_avg = style_profile.get("rhythm", {}).get("avg_sentence_length", 15.0)
    if drift_level in ("moderate", "strong") and ref_avg < 20:
        sents = _tokenize_sentences(user_text)
        long_sents = [s for s in sents if len(_tokenize_words(s)) >= LONG_SENT_THRESHOLD]
        max_rewrites = 3 if drift_level == "strong" else 2
        for s in long_sents[:max_rewrites]:
            rewrite_candidates.append({
                "original": s,
                "suggested": (
                    "[Split into two shorter sentences. "
                    "End the first on a concrete image or action.]"
                ),
                "reason": "shorter, more declarative, closer to target rhythm",
            })
    elif drift_level == "mild":
        sents = _tokenize_sentences(user_text)
        long_sents = [s for s in sents if len(_tokenize_words(s)) >= LONG_SENT_THRESHOLD]
        if long_sents:
            rewrite_candidates.append({
                "original": long_sents[0],
                "suggested": "[Optional: consider splitting at a natural pause.]",
                "reason": "optional compression toward target rhythm",
            })

    # --- Sentence-level drift ---
    sentence_drift = _sentence_level_drift(user_text, distributions, user)

    # --- Writer context (tendencies + derived rules) ---
    writer_context: list[str] = list(style_profile.get("tendencies", []))
    if lex_profile:
        writer_context.extend(lex_profile.get("derived_rules", []))

    # -----------------------------------------------------------------------
    # Exemplar retrieval
    # -----------------------------------------------------------------------
    retrieved_exemplars: list[dict] = []
    if exemplar_path and exemplar_path.exists():
        retrieved_exemplars = retrieve_exemplars(
            user_text=user_text,
            user_features={
                "avg_sentence_length": user["avg_sentence_length"],
                "short_sentence_ratio": user["short_sentence_ratio"],
                "phys_verb_ratio": user["phys_verb_ratio"],
            },
            user_mode=mode,
            exemplar_path=exemplar_path,
            n=n_exemplars,
        )

    # -----------------------------------------------------------------------
    # Load LLM abstractions (if available)
    # -----------------------------------------------------------------------
    llm_data: dict = {}
    llm_path = profile_path.parent / "llm_abstractions.json"
    if llm_path.exists():
        llm_data = json.loads(llm_path.read_text(encoding="utf-8"))

    # -----------------------------------------------------------------------
    # Rewrite handoff packet
    # -----------------------------------------------------------------------
    style_rules_path = profile_path.parent / "style_rules.json"
    target_rules: list[str] = []
    if style_rules_path.exists():
        style_rules = json.loads(style_rules_path.read_text(encoding="utf-8"))
        target_rules = style_rules.get("prefer_rules", [])[:6]
        target_rules += style_rules.get("transformation_hints", [])[:3]

    rewrite_policy_strength = {
        "none": "none",
        "mild": "light",
        "moderate": "moderate",
        "strong": "strong",
    }.get(drift_level, "moderate")

    # Mode-specific notes from LLM abstraction for the detected mode
    llm_mode_notes: list[str] = []
    if llm_data:
        llm_mode_notes = llm_data.get("mode_notes", {}).get(mode, [])

    rewrite_packet = {
        "writer_id": writer_id,
        "mode_guess": mode,
        "drift_level": drift_level,
        # Compact corpus-derived rules (prefer + transformation hints)
        "target_rules": target_rules,
        # LLM abstraction fields — high-level control layer for the rewrite model
        "global_tendencies": llm_data.get("global_tendencies", []),
        "mode_notes": llm_mode_notes,
        "edit_transformations": llm_data.get("edit_transformations", []),
        "avoidances": llm_data.get("avoidances", []),
        # Drift signal
        "drift_sentences": [
            {"text": s["sentence"], "issues": [s["reason"]]}
            for s in sentence_drift
        ],
        "retrieved_exemplars": retrieved_exemplars,
        "rewrite_policy": {
            "strength": rewrite_policy_strength,
            "preserve_meaning": True,
            "preserve_structure_when_possible": drift_level in ("none", "mild"),
        },
    }

    # -----------------------------------------------------------------------
    # author_tendencies — 1–3 lines from LLM global_tendencies for the
    # user-facing output (compact; full guidance lives in rewrite_packet)
    # -----------------------------------------------------------------------
    author_tendencies: list[str] = (
        llm_data.get("global_tendencies", [])[:3]
        if llm_data
        else list(style_profile.get("tendencies", []))[:3]
    )

    return {
        "style_alignment": style_alignment,
        "drift_level": drift_level,
        "mode_guess": mode,
        "writer_id": writer_id,
        "source_file": style_profile.get("source_file", ""),
        "user_features": {
            "avg_sentence_length": round(user["avg_sentence_length"], 2),
            "short_sentence_ratio": round(user["short_sentence_ratio"], 4),
            "abstract_noun_ratio": round(user["abstract_noun_ratio"], 4),
            "phys_verb_ratio": round(user["phys_verb_ratio"], 4),
            "and_rate": round(user["and_rate"], 5),
            "semicolons_per_sentence": round(user["semicolons_per_sentence"], 4),
        },
        "feature_classifications": classifications,
        "differences": raw_diffs,
        "edit_suggestions": edit_suggestions,
        "rewrite_candidates": rewrite_candidates,
        "sentence_drift": sentence_drift,
        "retrieved_exemplars": retrieved_exemplars,
        "author_tendencies": author_tendencies,
        "rewrite_packet": rewrite_packet,
    }
