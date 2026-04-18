"""
Build a style profile from passages.
Output: profile/style_profile.json
"""
from __future__ import annotations

import json
import re
import statistics
from collections import Counter
from pathlib import Path

import nltk


# ---------------------------------------------------------------------------
# NLTK data bootstrap
# ---------------------------------------------------------------------------

def _ensure_nltk_data() -> None:
    resources = [
        ("tokenizers/punkt_tab", "punkt_tab"),
        ("taggers/averaged_perceptron_tagger_eng", "averaged_perceptron_tagger_eng"),
        ("corpora/stopwords", "stopwords"),
    ]
    for find_path, download_name in resources:
        try:
            nltk.data.find(find_path)
        except LookupError:
            nltk.download(download_name, quiet=True)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_NOUN_TAGS = {"NN", "NNS"}
_ADJ_TAGS = {"JJ", "JJR", "JJS"}
_ADV_TAGS = {"RB", "RBR", "RBS"}
_CONTENT_POS = {
    "NN", "NNS", "NNP", "NNPS",
    "VB", "VBD", "VBG", "VBN", "VBP", "VBZ",
    "JJ", "JJR", "JJS",
    "RB",
}

_ABSTRACT_SUFFIXES = (
    "tion", "sion", "ment", "ness", "ity", "ism",
    "ance", "ence", "hood", "ship", "dom", "cy",
)

SHORT_SENT_THRESHOLD = 10   # words
LONG_SENT_THRESHOLD = 30    # words

_WORD_RE = re.compile(r"[A-Za-z'-]+$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tokenize_sentences(text: str) -> list[str]:
    from nltk.tokenize import sent_tokenize
    return [s.strip() for s in sent_tokenize(text) if s.strip()]


def _tokenize_words(text: str) -> list[str]:
    from nltk.tokenize import word_tokenize
    return [w for w in word_tokenize(text) if _WORD_RE.match(w)]


def _ngrams(tokens: list[str], n: int) -> list[tuple[str, ...]]:
    return [tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def _is_abstract_noun(word: str, tag: str) -> bool:
    if tag not in _NOUN_TAGS:
        return False
    return any(word.lower().endswith(suf) for suf in _ABSTRACT_SUFFIXES)


def _bundle_has_content(bundle: tuple[str, ...], stopwords: set[str]) -> bool:
    return any(w not in stopwords for w in bundle)


def _top_bundles(
    counter: Counter,
    stopwords: set[str],
    min_count: int,
    n: int = 20,
) -> list[str]:
    return [
        " ".join(bundle)
        for bundle, count in counter.most_common(200)
        if count >= min_count and _bundle_has_content(bundle, stopwords)
    ][:n]


# ---------------------------------------------------------------------------
# Tendency generation
# ---------------------------------------------------------------------------

def _generate_tendencies(
    avg_sent_len: float,
    short_sent_ratio: float,
    long_sent_ratio: float,
    adj_rate: float,
    adv_rate: float,
    abstract_noun_ratio: float,
    concrete_noun_ratio: float,
) -> list[str]:
    rules: list[str] = []

    if avg_sent_len < 12:
        rules.append("Strongly prefers short, declarative sentences.")
    elif avg_sent_len < 18:
        rules.append("Favors moderately short sentences with minimal subordination.")
    else:
        rules.append("Uses longer, more elaborated sentences with embedded clauses.")

    if short_sent_ratio > 0.40:
        rules.append(
            f"High proportion of short sentences ({short_sent_ratio:.0%}): "
            "rhythm is staccato and percussive."
        )
    if long_sent_ratio > 0.15:
        rules.append(
            f"Notable use of long sentences ({long_sent_ratio:.0%}): "
            "creates sweeping, accumulative rhythm."
        )

    if adj_rate < 0.04:
        rules.append("Uses very sparse adjectives; nouns and verbs carry most weight.")
    elif adj_rate < 0.07:
        rules.append("Moderate adjective use; modifiers are selective rather than decorative.")
    else:
        rules.append("Higher adjective density; prose is more descriptively layered.")

    if adv_rate < 0.03:
        rules.append("Rarely uses adverbs; prefers stronger verbs over modification.")
    elif adv_rate > 0.06:
        rules.append("Frequent adverb use; manner and degree are often marked explicitly.")

    if concrete_noun_ratio > 0.75:
        rules.append("Strongly favors concrete, image-bearing nouns over abstract terminology.")
    elif concrete_noun_ratio > 0.55:
        rules.append("Leans toward concrete nouns; abstract concepts are relatively rare.")
    else:
        rules.append(
            "Notable use of abstract nouns; prose moves between concrete and conceptual registers."
        )

    return rules


# ---------------------------------------------------------------------------
# Core profiler
# ---------------------------------------------------------------------------

def build_profile(passages: list[dict], writer_id: str, source_file: str) -> dict:
    _ensure_nltk_data()
    stopwords: set[str] = set(nltk.corpus.stopwords.words("english"))

    all_sentences: list[list[str]] = []
    all_tagged: list[tuple[str, str]] = []
    para_sentence_counts: list[int] = []
    content_words: Counter = Counter()

    bigrams: Counter = Counter()
    trigrams: Counter = Counter()
    fourgrams: Counter = Counter()
    fivegrams: Counter = Counter()
    sent_starters: Counter = Counter()
    sent_enders: Counter = Counter()

    for passage in passages:
        sents = _tokenize_sentences(passage["text"])
        para_sentence_counts.append(len(sents))

        for sent in sents:
            words = _tokenize_words(sent)
            if not words:
                continue
            all_sentences.append(words)
            tagged = nltk.pos_tag(words)
            all_tagged.extend(tagged)

            for word, tag in tagged:
                if (
                    tag in _CONTENT_POS
                    and word.lower() not in stopwords
                    and len(word) > 2
                ):
                    content_words[word.lower()] += 1

            lw = [w.lower() for w in words]
            bigrams.update(_ngrams(lw, 2))
            trigrams.update(_ngrams(lw, 3))
            fourgrams.update(_ngrams(lw, 4))
            fivegrams.update(_ngrams(lw, 5))

            if len(lw) >= 3:
                sent_starters[tuple(lw[:3])] += 1
                sent_enders[tuple(lw[-3:])] += 1

    # --- Sentence statistics ---
    sent_lengths = [len(s) for s in all_sentences]
    sentence_count = len(sent_lengths)
    total_tokens = sum(sent_lengths)

    avg_sent_len = statistics.mean(sent_lengths) if sent_lengths else 0.0
    median_sent_len = float(statistics.median(sent_lengths)) if sent_lengths else 0.0
    short_sent_ratio = (
        sum(1 for l in sent_lengths if l <= SHORT_SENT_THRESHOLD) / sentence_count
        if sentence_count else 0.0
    )
    long_sent_ratio = (
        sum(1 for l in sent_lengths if l >= LONG_SENT_THRESHOLD) / sentence_count
        if sentence_count else 0.0
    )
    avg_para_sent_count = (
        statistics.mean(para_sentence_counts) if para_sentence_counts else 0.0
    )

    # --- POS rates ---
    total_words = len(all_tagged)
    adj_count = sum(1 for _, tag in all_tagged if tag in _ADJ_TAGS)
    adv_count = sum(1 for _, tag in all_tagged if tag in _ADV_TAGS)
    noun_count = sum(1 for _, tag in all_tagged if tag in _NOUN_TAGS)
    abstract_count = sum(1 for word, tag in all_tagged if _is_abstract_noun(word, tag))
    concrete_count = noun_count - abstract_count

    adj_rate = adj_count / total_words if total_words else 0.0
    adv_rate = adv_count / total_words if total_words else 0.0
    abstract_noun_ratio = abstract_count / noun_count if noun_count else 0.0
    concrete_noun_ratio = concrete_count / noun_count if noun_count else 0.0

    # --- Phrase bundles ---
    top_starters = [
        " ".join(s)
        for s, c in sent_starters.most_common(20)
        if c >= 2
    ][:10]
    top_enders = [
        " ".join(s)
        for s, c in sent_enders.most_common(20)
        if c >= 2
    ][:10]

    profile = {
        "writer_id": writer_id,
        "source_file": source_file,
        "lexical": {
            "token_count": total_tokens,
            "sentence_count": sentence_count,
            "paragraph_count": len(passages),
            "top_content_words": [w for w, _ in content_words.most_common(50)],
            "adj_rate": round(adj_rate, 4),
            "adv_rate": round(adv_rate, 4),
            "abstract_noun_ratio": round(abstract_noun_ratio, 4),
            "concrete_noun_ratio": round(concrete_noun_ratio, 4),
        },
        "phraseological": {
            "top_bigrams": _top_bundles(bigrams, stopwords, min_count=5),
            "top_trigrams": _top_bundles(trigrams, stopwords, min_count=3),
            "top_fourgrams": _top_bundles(fourgrams, stopwords, min_count=2),
            "top_fivegrams": _top_bundles(fivegrams, stopwords, min_count=2),
            "recurring_sentence_starters": top_starters,
            "recurring_sentence_enders": top_enders,
        },
        "rhythm": {
            "avg_sentence_length": round(avg_sent_len, 2),
            "median_sentence_length": round(median_sent_len, 2),
            "short_sentence_ratio": round(short_sent_ratio, 4),
            "long_sentence_ratio": round(long_sent_ratio, 4),
            "avg_paragraph_sentence_count": round(avg_para_sent_count, 2),
        },
        "tendencies": _generate_tendencies(
            avg_sent_len=avg_sent_len,
            short_sent_ratio=short_sent_ratio,
            long_sent_ratio=long_sent_ratio,
            adj_rate=adj_rate,
            adv_rate=adv_rate,
            abstract_noun_ratio=abstract_noun_ratio,
            concrete_noun_ratio=concrete_noun_ratio,
        ),
    }

    return profile


def profile_from_passages(
    passages: list[dict],
    writer_id: str,
    source_file: str,
    out_dir: Path,
) -> dict:
    profile = build_profile(passages, writer_id, source_file)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "style_profile.json"
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(profile, fh, indent=2, ensure_ascii=False)
    return profile
