"""
Build a lexicon profile from passages.
Output: profile/lexicon_profile.json

Captures:
- signature words (ranked content vocabulary)
- signature nouns / verbs / adjectives
- archaic/literary term intersection (from Roget archaic_terms.jsonl)
- concrete vs abstract lexical tilt
- verb bias (physical vs cognitive)
- function-word and punctuation profile
- foreign/bilingual lexical signal
- derived style rules
- note signals from author_notes/style_notes.txt
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import nltk

from .style_profiler import (
    _ensure_nltk_data,
    _is_abstract_noun,
    _NOUN_TAGS,
    _ADJ_TAGS,
    _ADV_TAGS,
)

# ---------------------------------------------------------------------------
# Repo-relative path to archaic terms
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parents[5]
_ARCHAIC_TERMS_PATH = _REPO_ROOT / "modules" / "voice" / "roget" / "jsonl" / "archaic_terms.jsonl"

# ---------------------------------------------------------------------------
# Verb bias seed lists
# ---------------------------------------------------------------------------

_PHYSICAL_VERBS: frozenset[str] = frozenset(
    {
        "stand", "stood", "walk", "walked", "carry", "carried", "turn", "turned",
        "lift", "lifted", "look", "looked", "go", "went", "come", "came",
        "run", "ran", "move", "moved", "stop", "stopped", "sit", "sat",
        "lie", "lay", "hang", "hung", "hold", "held", "pull", "pulled",
        "push", "pushed", "reach", "reached", "set", "put", "keep", "kept",
        "take", "took", "get", "got", "bring", "brought", "fall", "fell",
        "rise", "rose", "climb", "climbed", "leave", "left", "step", "stepped",
        "cross", "crossed", "follow", "followed", "open", "opened", "close",
        "closed", "pick", "picked", "drop", "dropped", "throw", "threw",
        "watch", "watched", "pass", "passed", "kneel", "knelt", "crouch",
        "crouched", "lean", "leaned", "press", "pressed", "touch", "touched",
        "gather", "gathered", "draw", "drew", "bend", "bent", "dig", "dug",
        "wrap", "wrapped", "eat", "ate", "drink", "drank", "sleep", "slept",
        "wake", "woke", "breathe", "breathed", "cough", "coughed",
    }
)

_COGNITIVE_VERBS: frozenset[str] = frozenset(
    {
        "think", "thought", "know", "knew", "believe", "believed", "realize",
        "realized", "wonder", "wondered", "consider", "considered", "remember",
        "remembered", "forget", "forgot", "understand", "understood", "feel",
        "felt", "seem", "seemed", "appear", "appeared", "mean", "meant",
        "want", "wanted", "need", "needed", "hope", "hoped", "expect",
        "expected", "imagine", "imagined", "suppose", "supposed", "guess",
        "guessed", "decide", "decided", "doubt", "doubted", "fear", "feared",
        "wish", "wished", "recall", "recalled", "notice", "noticed",
        "recognize", "recognized", "sense", "sensed", "perceive", "perceived",
        "worry", "worried", "believe", "believed",
    }
)

# ---------------------------------------------------------------------------
# Abstract noun suffixes (shared with style_profiler)
# ---------------------------------------------------------------------------

_ABSTRACT_SUFFIXES = (
    "tion", "sion", "ment", "ness", "ity", "ism",
    "ance", "ence", "hood", "ship", "dom", "cy",
)

# ---------------------------------------------------------------------------
# Note file parsing
# ---------------------------------------------------------------------------

_PREFERRED_RE = re.compile(r"^##\s*preferred\s*features", re.IGNORECASE)
_AVOID_RE = re.compile(r"^##\s*avoid\s*features", re.IGNORECASE)
_ITEM_RE = re.compile(r"^\s*-\s+(.+)")
_SECTION_RE = re.compile(r"^##\s+")


def _parse_style_notes(notes_path: Path) -> dict[str, list[str]]:
    """
    Parse style_notes.txt into preferred_features and avoid_features lists.
    Each item is the text after the leading '- ', up to but not including
    any colon-separated annotation.
    """
    preferred: list[str] = []
    avoid: list[str] = []
    current: list[str] | None = None

    for raw_line in notes_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Skip single-hash comments (# ...) but NOT section headers (## ...)
        if line.startswith("#") and not line.startswith("##"):
            continue
        if _PREFERRED_RE.match(line):
            current = preferred
        elif _AVOID_RE.match(line):
            current = avoid
        elif _SECTION_RE.match(line):
            current = None
        elif current is not None:
            m = _ITEM_RE.match(line)
            if m:
                # Keep full text but strip inline annotation after ':'
                item = m.group(1).split(":", 1)[0].strip()
                current.append(item)

    return {"preferred_features": preferred, "avoid_features": avoid}


# ---------------------------------------------------------------------------
# Archaic terms loader
# ---------------------------------------------------------------------------

def _load_archaic_terms(path: Path = _ARCHAIC_TERMS_PATH) -> dict[str, str]:
    """Return {normalized_term -> category_heading} for all single-word terms."""
    result: dict[str, str] = {}
    if not path.exists():
        return result
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                term = entry.get("normalized_term", "").lower().strip()
                # Single-word only for v1
                if term and " " not in term:
                    result[term] = entry.get("category_heading", "")
            except json.JSONDecodeError:
                continue
    return result


# ---------------------------------------------------------------------------
# Foreign-language signal (simple)
# ---------------------------------------------------------------------------

def _load_english_words() -> set[str]:
    """Return a set of common English word forms from NLTK."""
    try:
        nltk.data.find("corpora/words")
    except LookupError:
        nltk.download("words", quiet=True)
    from nltk.corpus import words as nltk_words
    return {w.lower() for w in nltk_words.words()}


def _detect_foreign_signal(
    token_counts: Counter,
    english_words: set[str],
    archaic_terms: dict[str, str],
    min_count: int = 2,
    top_n: int = 20,
) -> dict:
    candidates: list[tuple[str, int]] = []
    for token, count in token_counts.items():
        if (
            count >= min_count
            and len(token) >= 3
            and token.isalpha()
            and token not in english_words
            and token not in archaic_terms
            and not token[0].isupper()
        ):
            candidates.append((token, count))
    candidates.sort(key=lambda x: x[1], reverse=True)
    top = [t for t, _ in candidates[:top_n]]
    return {
        "has_foreign_language_signal": len(top) > 0,
        "top_terms": top,
    }


# ---------------------------------------------------------------------------
# Derived rules generator
# ---------------------------------------------------------------------------

def _derive_rules(
    and_rate: float,
    semicolon_rate: float,
    quote_mark_rate: float,
    concrete_ratio: float,
    phys_ratio: float,
    cog_ratio: float,
    archaic_hit_count: int,
    has_foreign: bool,
) -> list[str]:
    rules: list[str] = []

    if and_rate > 0.04:
        rules.append(
            f"Heavy polysyndeton: 'and' appears at {and_rate:.1%} of all tokens."
        )
    elif and_rate > 0.025:
        rules.append(f"Moderate use of 'and' as connective ({and_rate:.1%} of tokens).")

    if semicolon_rate < 0.005:
        rules.append("Near-zero semicolon use: prefers parataxis over subordination.")
    elif semicolon_rate < 0.02:
        rules.append("Very sparse semicolons: punctuation is minimal.")

    if quote_mark_rate < 0.01:
        rules.append("Quotation marks absent or near-zero: dialogue is unmarked.")

    if concrete_ratio > 0.70:
        rules.append(
            f"Strong concrete lexical bias: {concrete_ratio:.0%} of profiled nouns are concrete."
        )
    elif concrete_ratio > 0.55:
        rules.append(f"Moderate concrete lexical tilt ({concrete_ratio:.0%} of nouns).")

    if phys_ratio > cog_ratio * 2:
        rules.append(
            "Verb profile is action-dominant: physical verbs outnumber cognitive verbs by more than 2:1."
        )
    elif phys_ratio > cog_ratio:
        rules.append("Verb profile leans physical: more action verbs than cognitive verbs.")

    if archaic_hit_count >= 10:
        rules.append(
            f"Strong archaic/literary vocabulary: {archaic_hit_count} corpus terms match the Roget archaic list."
        )
    elif archaic_hit_count >= 3:
        rules.append(
            f"Some archaic/literary vocabulary present: {archaic_hit_count} terms match archaic list."
        )

    if has_foreign:
        rules.append("Foreign/bilingual lexical signal detected (possible Spanish or archaic bleed).")

    return rules


# ---------------------------------------------------------------------------
# Core lexicon profiler
# ---------------------------------------------------------------------------

def build_lexicon_profile(
    passages: list[dict],
    writer_id: str,
    source_file: str,
    author_folder: Path,
) -> dict:
    _ensure_nltk_data()
    stopwords: set[str] = set(nltk.corpus.stopwords.words("english"))

    archaic_terms = _load_archaic_terms()
    english_words = _load_english_words()

    # --- Token accumulators ---
    all_tokens_lower: list[str] = []          # all word tokens (lowercased)
    all_tagged: list[tuple[str, str]] = []     # (word, POS)
    noun_counts: Counter = Counter()
    verb_counts: Counter = Counter()
    adj_counts: Counter = Counter()
    content_counts: Counter = Counter()        # non-stopword content words

    # For punctuation / function words: work from raw text
    full_text_parts: list[str] = []

    for passage in passages:
        text = passage["text"]
        full_text_parts.append(text)

        # Word tokenize and POS tag
        try:
            from nltk.tokenize import word_tokenize
            tokens = word_tokenize(text)
        except Exception:
            tokens = text.split()

        words = [w for w in tokens if re.match(r"[A-Za-z'-]+$", w)]
        tagged = nltk.pos_tag(words)
        all_tagged.extend(tagged)

        for word, tag in tagged:
            lower = word.lower()
            all_tokens_lower.append(lower)

            if lower not in stopwords and len(lower) > 2:
                content_counts[lower] += 1

                if tag in _NOUN_TAGS:
                    noun_counts[lower] += 1
                elif tag.startswith("VB"):
                    verb_counts[lower] += 1
                elif tag in _ADJ_TAGS:
                    adj_counts[lower] += 1

    full_text = "\n".join(full_text_parts)
    total_tokens = len(all_tokens_lower)
    unique_tokens = len(set(all_tokens_lower))
    total_content = sum(content_counts.values())

    # --- Signature words ---
    def _to_sig_list(counter: Counter, top_n: int = 30) -> list[dict]:
        total = sum(counter.values()) or 1
        return [
            {"term": term, "count": count, "score": round(count / total, 5)}
            for term, count in counter.most_common(top_n)
        ]

    signature_words = _to_sig_list(content_counts, top_n=50)

    # Signature nouns/verbs/adjectives
    signature_nouns = _to_sig_list(noun_counts, top_n=30)
    signature_verbs = _to_sig_list(verb_counts, top_n=30)
    signature_adjectives = _to_sig_list(adj_counts, top_n=30)

    # --- Archaic/literary intersection ---
    archaic_hits: list[dict] = []
    for term, count in content_counts.most_common():
        if term in archaic_terms:
            archaic_hits.append(
                {
                    "term": term,
                    "count": count,
                    "category": archaic_terms[term],
                }
            )
    archaic_hits.sort(key=lambda x: x["count"], reverse=True)

    # --- Concrete vs abstract lexical tilt ---
    abstract_nouns: Counter = Counter()
    concrete_nouns: Counter = Counter()
    for word, tag in all_tagged:
        lower = word.lower()
        if lower in stopwords or len(lower) <= 2:
            continue
        if tag in _NOUN_TAGS:
            if _is_abstract_noun(lower, tag):
                abstract_nouns[lower] += 1
            else:
                concrete_nouns[lower] += 1

    total_typed_nouns = sum(abstract_nouns.values()) + sum(concrete_nouns.values())
    concrete_ratio = sum(concrete_nouns.values()) / total_typed_nouns if total_typed_nouns else 0.0
    abstract_ratio = sum(abstract_nouns.values()) / total_typed_nouns if total_typed_nouns else 0.0

    concrete_lexicon = {
        "top_terms": [t for t, _ in concrete_nouns.most_common(25)],
        "ratio": round(concrete_ratio, 4),
    }
    abstract_lexicon = {
        "top_terms": [t for t, _ in abstract_nouns.most_common(25)],
        "ratio": round(abstract_ratio, 4),
    }

    # --- Verb bias ---
    phys_counts: Counter = Counter()
    cog_counts: Counter = Counter()
    for word, tag in all_tagged:
        if tag.startswith("VB"):
            lower = word.lower()
            if lower in _PHYSICAL_VERBS:
                phys_counts[lower] += 1
            elif lower in _COGNITIVE_VERBS:
                cog_counts[lower] += 1

    total_biased = sum(phys_counts.values()) + sum(cog_counts.values())
    phys_ratio = sum(phys_counts.values()) / total_biased if total_biased else 0.0
    cog_ratio = sum(cog_counts.values()) / total_biased if total_biased else 0.0

    verb_bias = {
        "physical_verbs": {
            "top_terms": [t for t, _ in phys_counts.most_common(20)],
            "ratio": round(phys_ratio, 4),
        },
        "cognitive_verbs": {
            "top_terms": [t for t, _ in cog_counts.most_common(20)],
            "ratio": round(cog_ratio, 4),
        },
    }

    # --- Function-word and punctuation profile ---
    # Operate on raw text for punctuation counts
    from nltk.tokenize import sent_tokenize
    all_sentences = sent_tokenize(full_text)
    sentence_count = max(len(all_sentences), 1)

    and_count = len(re.findall(r"\band\b", full_text, flags=re.IGNORECASE))
    comma_count = full_text.count(",")
    semicolon_count = full_text.count(";")
    colon_count = full_text.count(":")
    quote_count = full_text.count('"') + full_text.count("\u201c") + full_text.count("\u201d")

    # and_rate: fraction of all tokens
    and_rate = and_count / total_tokens if total_tokens else 0.0
    # punctuation rates: per sentence (more interpretable)
    comma_rate = comma_count / sentence_count
    semicolon_rate = semicolon_count / sentence_count
    colon_rate = colon_count / sentence_count
    quote_mark_rate = quote_count / sentence_count

    function_word_profile = {
        "and_rate": round(and_rate, 5),
        "comma_rate": round(comma_rate, 4),
        "semicolon_rate": round(semicolon_rate, 4),
        "colon_rate": round(colon_rate, 4),
        "quote_mark_rate": round(quote_mark_rate, 4),
    }

    # --- Foreign/bilingual signal ---
    token_counter = Counter(all_tokens_lower)
    foreign_profile = _detect_foreign_signal(token_counter, english_words, archaic_terms)

    # --- Derived rules ---
    derived_rules = _derive_rules(
        and_rate=and_rate,
        semicolon_rate=semicolon_rate,
        quote_mark_rate=quote_mark_rate,
        concrete_ratio=concrete_ratio,
        phys_ratio=phys_ratio,
        cog_ratio=cog_ratio,
        archaic_hit_count=len(archaic_hits),
        has_foreign=foreign_profile["has_foreign_language_signal"],
    )

    # --- Note signals ---
    notes_path = author_folder / "author_notes" / "style_notes.txt"
    note_signals = _parse_style_notes(notes_path) if notes_path.exists() else {
        "preferred_features": [],
        "avoid_features": [],
    }

    profile = {
        "writer_id": writer_id,
        "source_files": [source_file],
        "source_notes_file": "author_notes/style_notes.txt" if notes_path.exists() else None,
        "corpus_stats": {
            "num_tokens": total_tokens,
            "num_unique_tokens": unique_tokens,
            "num_content_tokens": total_content,
        },
        "signature_words": signature_words,
        "signature_nouns": signature_nouns,
        "signature_verbs": signature_verbs,
        "signature_adjectives": signature_adjectives,
        "archaic_or_literary_terms": archaic_hits,
        "concrete_lexicon": concrete_lexicon,
        "abstract_lexicon": abstract_lexicon,
        "verb_bias": verb_bias,
        "function_word_profile": function_word_profile,
        "foreign_language_profile": foreign_profile,
        "derived_rules": derived_rules,
        "note_signals": note_signals,
    }

    return profile


def lexicon_profile_from_passages(
    passages: list[dict],
    writer_id: str,
    source_file: str,
    author_folder: Path,
    out_dir: Path,
) -> dict:
    profile = build_lexicon_profile(passages, writer_id, source_file, author_folder)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "lexicon_profile.json"
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(profile, fh, indent=2, ensure_ascii=False)
    return profile


# ---------------------------------------------------------------------------
# Feature distributions (for drift-aware comparison)
# ---------------------------------------------------------------------------

def _percentiles(data: list[float]) -> dict:
    """Return mean, median, p10, p25, p75, p90 for a list of floats."""
    import statistics as _st
    if not data:
        return {}
    n = len(data)
    mean = _st.mean(data)
    median = float(_st.median(data))
    if n < 10:
        s = sorted(data)
        return {
            "mean": round(mean, 4), "median": round(median, 4),
            "p10": round(s[0], 4), "p25": round(s[0], 4),
            "p75": round(s[-1], 4), "p90": round(s[-1], 4),
        }
    q4 = _st.quantiles(data, n=4)    # [p25, p50, p75]
    q10 = _st.quantiles(data, n=10)  # [p10, p20, … p90]
    return {
        "mean": round(mean, 4),
        "median": round(median, 4),
        "p10": round(q10[0], 4),
        "p25": round(q4[0], 4),
        "p75": round(q4[2], 4),
        "p90": round(q10[8], 4),
    }


def build_feature_distributions(passages: list[dict]) -> dict:
    """
    Compute per-passage feature distributions for drift-aware comparison.

    Each tracked feature is computed once per passage, yielding a list of
    ~N values (one per passage). Percentiles over those lists give the
    author's natural variation range.

    Features tracked:
        sentence_length     — per-passage mean sentence length (words)
        short_sentence_ratio — fraction of sentences ≤ SHORT_SENT_THRESHOLD
        abstract_noun_ratio  — abstract / total nouns
        physical_verb_ratio  — physical / (physical + cognitive) verbs
        and_rate             — 'and' tokens / total tokens
    """
    from .style_profiler import (
        _ensure_nltk_data,
        _tokenize_sentences,
        _tokenize_words,
        _NOUN_TAGS,
        _is_abstract_noun,
        SHORT_SENT_THRESHOLD,
    )
    import statistics as _st
    import re as _re

    _ensure_nltk_data()

    avg_sent_lengths: list[float] = []
    short_ratios: list[float] = []
    abstract_ratios: list[float] = []
    phys_ratios: list[float] = []
    and_rates: list[float] = []

    for passage in passages:
        text = passage["text"]
        sents = _tokenize_sentences(text)
        sent_word_lists: list[list[str]] = []
        all_tagged: list[tuple[str, str]] = []

        for sent in sents:
            words = _tokenize_words(sent)
            if words:
                sent_word_lists.append(words)
                all_tagged.extend(nltk.pos_tag(words))

        if not sent_word_lists:
            continue

        sent_lens = [len(s) for s in sent_word_lists]
        avg_sent_lengths.append(_st.mean(sent_lens))
        short_ratios.append(
            sum(1 for l in sent_lens if l <= SHORT_SENT_THRESHOLD) / len(sent_lens)
        )

        noun_count = sum(1 for _, tag in all_tagged if tag in _NOUN_TAGS)
        abstract_count = sum(1 for w, tag in all_tagged if _is_abstract_noun(w, tag))
        if noun_count > 0:
            abstract_ratios.append(abstract_count / noun_count)

        phys_count = sum(
            1 for w, tag in all_tagged
            if tag.startswith("VB") and w.lower() in _PHYSICAL_VERBS
        )
        cog_count = sum(
            1 for w, tag in all_tagged
            if tag.startswith("VB") and w.lower() in _COGNITIVE_VERBS
        )
        total_biased = phys_count + cog_count
        if total_biased > 0:
            phys_ratios.append(phys_count / total_biased)

        total_tokens = sum(sent_lens)
        and_count = len(_re.findall(r"\band\b", text, _re.IGNORECASE))
        if total_tokens > 0:
            and_rates.append(and_count / total_tokens)

    return {
        "sentence_length": _percentiles(avg_sent_lengths),
        "short_sentence_ratio": _percentiles(short_ratios),
        "abstract_noun_ratio": _percentiles(abstract_ratios),
        "physical_verb_ratio": _percentiles(phys_ratios),
        "and_rate": _percentiles(and_rates),
    }


def feature_distributions_from_passages(passages: list[dict], out_dir: Path) -> dict:
    """Build feature distributions and write feature_distributions.json."""
    distributions = build_feature_distributions(passages)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "feature_distributions.json"
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(distributions, fh, indent=2, ensure_ascii=False)
    return distributions
