"""
Passage search index builder and search functions.

Build step (run as part of `run` pipeline):
  build_passage_search_index(passages, out_dir)
  → processed/passage_search_index.jsonl

Each indexed record contains enriched metadata:
  writer_id, source_file, passage_id, text, mode_guess, dialogue_mode,
  token_count, sentence_count, avg_sentence_length, short_sentence_ratio,
  dialogue_ratio, top_keywords, top_bigrams

Retrieval modes:
  quote     — literal line-finding; compact, keyword-dense; single sentence can be ideal
  exemplar  — generation support; mode fit + structural richness; 3–8 sentences preferred

Search functions:
  search_quotes(query, author_folder, top_k=10, source_file=None, context=0)
  search_exemplars(author_folder, query, top_k=5)
  search_exemplars_by_mode(author_folder, query, mode, top_k=5)

  (Legacy / internal):
  search_passages(query, author_folder, top_k=10)
  search_passages_by_mode(query, author_folder, mode, top_k=10)
  search_structural_exemplars(author_folder, mode, sentence_band, top_k=10)

All search functions return a list of passage dicts.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


# ---------------------------------------------------------------------------
# Stopwords (minimal — keep content-word signal clean)
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset([
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "it", "its",
    "he", "she", "they", "we", "you", "i", "him", "her", "them", "us",
    "his", "their", "our", "your", "my", "this", "that", "these", "those",
    "not", "no", "nor", "so", "yet", "both", "either", "neither", "each",
    "than", "then", "when", "where", "which", "who", "what", "how",
    "up", "out", "off", "over", "under", "into", "through", "about",
    "there", "here", "all", "any", "if", "s", "t", "d",
])

_SENT_SPLIT = re.compile(r"[.!?]+")
_SHORT_THRESHOLD = 10


# ---------------------------------------------------------------------------
# Index record builder
# ---------------------------------------------------------------------------

def _build_index_record(passage: dict) -> dict:
    text = passage.get("text", "")
    tokens = [w.lower() for w in re.findall(r"\b[a-zA-Z']+\b", text)]

    sents = [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]
    sentence_count = max(len(sents), 1)
    sent_lens = [len(s.split()) for s in sents] if sents else [len(tokens)]
    avg_sent_len = sum(sent_lens) / len(sent_lens)
    short_ratio = sum(1 for l in sent_lens if l <= _SHORT_THRESHOLD) / len(sent_lens)

    # Dialogue ratio from tag
    dm = passage.get("dialogue_mode", "narrative")
    dialogue_ratio = 1.0 if dm == "dialogue" else 0.5 if dm == "mixed" else 0.0

    # Top content keywords
    content = [t for t in tokens if t not in _STOPWORDS and len(t) > 2]
    keyword_counts = Counter(content)
    top_keywords = [w for w, _ in keyword_counts.most_common(15)]

    # Top bigrams
    bigram_counts: Counter = Counter()
    for i in range(len(tokens) - 1):
        a, b = tokens[i], tokens[i + 1]
        if a not in _STOPWORDS and b not in _STOPWORDS and len(a) > 2 and len(b) > 2:
            bigram_counts[f"{a} {b}"] += 1
    top_bigrams = [bg for bg, _ in bigram_counts.most_common(10)]

    return {
        "writer_id": passage.get("writer_id", ""),
        "source_file": passage.get("source_file", ""),
        "passage_id": passage.get("passage_id", ""),
        "text": text,
        "mode_guess": passage.get("mode_guess", "narrative"),
        "dialogue_mode": dm,
        "token_count": len(tokens),
        "sentence_count": sentence_count,
        "avg_sentence_length": round(avg_sent_len, 2),
        "short_sentence_ratio": round(short_ratio, 3),
        "dialogue_ratio": dialogue_ratio,
        "top_keywords": top_keywords,
        "top_bigrams": top_bigrams,
    }


# ---------------------------------------------------------------------------
# Build step
# ---------------------------------------------------------------------------

def build_passage_search_index(passages: list[dict], out_dir: Path) -> Path:
    """
    Enrich all passages with lexical + structural metadata and write
    processed/passage_search_index.jsonl.

    Returns the path to the index file.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    index_path = out_dir / "passage_search_index.jsonl"

    with index_path.open("w", encoding="utf-8") as fh:
        for passage in passages:
            record = _build_index_record(passage)
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    return index_path


# ---------------------------------------------------------------------------
# Index loader
# ---------------------------------------------------------------------------

def _load_index(author_folder: Path) -> list[dict]:
    index_path = author_folder / "processed" / "passage_search_index.jsonl"
    if not index_path.exists():
        raise FileNotFoundError(
            f"Search index not found at {index_path}. Run the pipeline first."
        )
    records = []
    with index_path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                records.append(json.loads(line))
    return records


# ---------------------------------------------------------------------------
# Search helpers
# ---------------------------------------------------------------------------

def _tfidf_search(query: str, records: list[dict], top_k: int) -> list[dict]:
    """TF-IDF cosine similarity over passage text. Fitted on-demand."""
    if not records:
        return []
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    texts = [r["text"] for r in records]
    vec = TfidfVectorizer(max_features=5000, ngram_range=(1, 2), stop_words="english")
    matrix = vec.fit_transform(texts)
    q_vec = vec.transform([query])
    sims = cosine_similarity(q_vec, matrix).flatten()

    scored = sorted(enumerate(sims), key=lambda x: x[1], reverse=True)
    return [records[i] for i, _ in scored[:top_k] if sims[i] > 0]


def _format_result(r: dict) -> dict:
    """Return a clean result record for external consumption."""
    return {
        "passage_id": r["passage_id"],
        "source_file": r["source_file"],
        "mode_guess": r["mode_guess"],
        "dialogue_mode": r["dialogue_mode"],
        "avg_sentence_length": r["avg_sentence_length"],
        "short_sentence_ratio": r["short_sentence_ratio"],
        "text": r["text"],
    }


# ---------------------------------------------------------------------------
# Quote scoring
# ---------------------------------------------------------------------------

def _tokenize_query(query: str) -> list[str]:
    """Lowercase content tokens from a query string."""
    return [
        w.lower()
        for w in re.findall(r"\b[a-zA-Z']+\b", query)
        if w.lower() not in _STOPWORDS and len(w) > 2
    ]


def _score_quote(record: dict, query_tokens: list[str]) -> float:
    """
    Score a passage for quote-search relevance.

    Positive:
      - unique term coverage (3.0x)  — how many distinct query terms appear
      - keyword hit count   (2.0x)  — raw count of query-token occurrences in text
      - phrase proximity    (1.5x)  — any adjacent query-token pair found as bigram
      - compactness         (1.0x)  — 1-3 sentence passages get a bonus
    Negative:
      - length penalty      (-0.3x per sentence over 5)
    """
    if not query_tokens:
        return 0.0

    text_lower = record["text"].lower()
    text_tokens = re.findall(r"\b[a-zA-Z']+\b", text_lower)
    text_token_set = set(text_tokens)

    # Unique term coverage
    matched = [t for t in set(query_tokens) if t in text_token_set]
    unique_coverage = len(matched) / len(set(query_tokens))

    # Raw keyword hit count (normalized)
    hit_count = sum(text_tokens.count(t) for t in query_tokens)
    token_count = max(record.get("token_count", 1), 1)
    hit_density = hit_count / token_count

    # Phrase proximity — any adjacent query pair found as bigram in index
    index_bigrams = set(record.get("top_bigrams", []))
    phrase_hits = 0
    for i in range(len(query_tokens) - 1):
        if f"{query_tokens[i]} {query_tokens[i+1]}" in index_bigrams:
            phrase_hits += 1
    phrase_bonus = min(phrase_hits * 0.5, 1.0)

    # Compactness bonus (1-3 sentences)
    sc = record.get("sentence_count", 1)
    compactness = 1.0 if sc <= 3 else 0.5 if sc <= 6 else 0.0

    # Length penalty (over 5 sentences)
    length_penalty = max(0.0, sc - 5) * 0.3

    score = (
        unique_coverage * 3.0
        + hit_density * 2.0
        + phrase_bonus * 1.5
        + compactness * 1.0
        - length_penalty
    )
    return score


# ---------------------------------------------------------------------------
# Exemplar scoring
# ---------------------------------------------------------------------------

_EXEMPLAR_IDEAL_MIN = 3   # sentences
_EXEMPLAR_IDEAL_MAX = 8

# Scene-coherence keyword sets for dialogue mode
_SCENE_FIRE   = frozenset(["fire", "embers", "ash", "smoke", "burning", "flame", "flames", "coals"])
_SCENE_NIGHT  = frozenset(["night", "dark", "darkness", "shadow", "shadows", "dusk", "moonlight"])
_SCENE_QUIET  = frozenset(["sat", "watched", "silence", "quiet", "still", "stillness", "listening"])
_SCENE_SPOKEN = frozenset(["said", "asked", "answered", "replied", "told", "spoke", "called"])
_WRONG_SENSE_WEAPON = frozenset([
    "rifle", "pistol", "gun", "cannon", "trigger", "barrel",
    "weapon", "shotgun", "revolver", "carbine", "musket",
])

# Scene-pattern phrase templates (bigrams / short phrases checked against passage text)
# Groups are trigger-matched: bonus fires only when query implies that scene type.
_PATTERN_FIRE = [
    "by the fire", "watched the fire", "dead fire", "built a fire",
    "sat by", "coals", "embers", "ash", "smoke",
]
_PATTERN_NIGHT = [
    "in the dark", "in the night", "darkness", "night", "black", "moonless",
]
_PATTERN_SPOKEN = [
    "he said", "she said", "they said", "asked", "replied",
    "answered", "spoke", "they sat",
]

# Generic phrases that are weakly informative — slight penalty when they are the
# primary match signal (checked as bigrams in passage text)
_GENERIC_PHRASES = frozenset(["two men", "three men", "two women", "the men"])


def _scene_pattern_bonus(query: str, record: dict) -> float:
    """
    Small bonus for exemplar mode based on reusable scene-pattern templates.

    Inspects query for scene-type signals (fire/camp, dark/night, spoken exchange)
    and rewards passages whose lowercased text contains the matching phrase patterns.

    This is a tie-breaker / sharpener — max contribution is kept modest (≤ 0.6).
    """
    query_lower = query.lower()
    text_lower  = record.get("text", "").lower()
    bonus = 0.0

    # Fire/camp scene
    if any(t in query_lower for t in ("fire", "embers", "coals", "ash", "camp")):
        hits = sum(1 for p in _PATTERN_FIRE if p in text_lower)
        bonus += hits * 0.15

    # Dark/night scene
    if any(t in query_lower for t in ("dark", "night", "darkness", "black")):
        hits = sum(1 for p in _PATTERN_NIGHT if p in text_lower)
        bonus += hits * 0.15

    # Spoken exchange
    if any(t in query_lower for t in ("said", "talking", "quiet", "spoke", "asked")):
        hits = sum(1 for p in _PATTERN_SPOKEN if p in text_lower)
        bonus += hits * 0.15

    return min(bonus, 1.0)


def _generic_phrase_penalty(query: str, record: dict) -> float:
    """
    Slight penalty when a passage's primary match signal is a generic human-count
    phrase (e.g. 'two men') with no scene-specific content.

    Only penalises if the generic phrase appears in the passage text AND the passage
    has low keyword overlap with scene terms (indicating a weak hit).
    """
    text_lower = record.get("text", "").lower()
    kw = set(record.get("top_keywords", []))
    scene_kw = _SCENE_FIRE | _SCENE_NIGHT | _SCENE_QUIET | _SCENE_SPOKEN

    penalty = 0.0
    for phrase in _GENERIC_PHRASES:
        if phrase in text_lower:
            # Only penalise if the passage has no scene-term signal AND no spoken marker
            if not (kw & scene_kw) and not (kw & _SCENE_SPOKEN):
                penalty += 0.5
    return min(penalty, 0.9)


def _score_exemplar(
    record: dict,
    query_tokens: list[str],
    mode: str | None = None,
    query: str = "",
) -> float:
    """
    Score a passage for exemplar-retrieval relevance.

    General mode:
      - mode fit            (3.0x)
      - keyword coverage    (2.0x)
      - structure score     (2.0x)  — 3–8 sentences ideal
      - rhythm score        (1.0x)  — short_sentence_ratio

    Dialogue mode adds:
      - graded dialogue_mode fit: dialogue=1.0, mixed=0.6, narrative=0.0
      - dialogue_ratio bonus    (1.5x)
      - scene coherence bonus   (fire / night / quiet / spoken, capped at 1.5)
      - scene-pattern bonus     (_scene_pattern_bonus, capped at 0.6)
      - generic-phrase penalty  (_generic_phrase_penalty for weak 'two men' hits)
      - wrong-sense penalty     (weapon context for "fire" query)
      - narrative penalty       (−1.5 for pure-narrative passages)
      - rhythm weight raised to 1.5x

    Negative (all modes):
      - too short penalty (-2.0 if < 2 sentences)
    """
    if not query_tokens:
        sc = record.get("sentence_count", 1)
        structure_score = 1.0 if _EXEMPLAR_IDEAL_MIN <= sc <= _EXEMPLAR_IDEAL_MAX else 0.5
        return structure_score * 2.0 + record.get("short_sentence_ratio", 0.0)

    index_keywords = set(record.get("top_keywords", []))
    sc = record.get("sentence_count", 1)

    # Structure score (shared)
    if _EXEMPLAR_IDEAL_MIN <= sc <= _EXEMPLAR_IDEAL_MAX:
        structure_score = 1.0
    elif sc < _EXEMPLAR_IDEAL_MIN:
        structure_score = sc / _EXEMPLAR_IDEAL_MIN
    else:
        structure_score = max(0.3, 1.0 - (sc - _EXEMPLAR_IDEAL_MAX) * 0.05)

    too_short_penalty = 2.0 if sc < 2 else 0.0

    # Keyword coverage (shared)
    n_unique = len(set(query_tokens))
    matched = sum(1 for t in set(query_tokens) if t in index_keywords)
    keyword_coverage = matched / n_unique if n_unique else 0.0

    # ---- Dialogue-specific scoring path ----
    if mode == "dialogue":
        dm = record.get("dialogue_mode", "narrative")
        if dm == "dialogue":
            mode_fit = 1.0
        elif dm == "mixed":
            mode_fit = 0.6
        else:
            mode_fit = 0.0

        dialogue_ratio_bonus = record.get("dialogue_ratio", 0.0) * 1.5

        # Scene coherence: detect scene type from query, reward matching passage terms
        query_set = set(query_tokens)
        scene_bonus = 0.0
        if query_set & _SCENE_FIRE:
            scene_bonus += len(index_keywords & _SCENE_FIRE) * 0.3
        if query_set & _SCENE_NIGHT:
            scene_bonus += len(index_keywords & _SCENE_NIGHT) * 0.3
        if query_set & _SCENE_QUIET:
            scene_bonus += len(index_keywords & _SCENE_QUIET) * 0.3
        scene_bonus += len(index_keywords & _SCENE_SPOKEN) * 0.2  # always reward spoken markers
        scene_bonus = min(scene_bonus, 1.5)

        # Wrong-sense penalty: "fire" query + weapon passage keywords
        wrong_sense_penalty = 0.0
        if query_set & _SCENE_FIRE:
            wrong_sense_penalty = len(index_keywords & _WRONG_SENSE_WEAPON) * 0.5

        narrative_penalty = 1.5 if dm == "narrative" else 0.0
        rhythm_score = record.get("short_sentence_ratio", 0.0)
        pattern_bonus = _scene_pattern_bonus(query, record)
        generic_penalty = _generic_phrase_penalty(query, record)

        # Quote-density penalty: passages heavy in quotation marks confuse
        # generation when the target style uses no quotation marks
        text = record.get("text", "")
        quote_count = text.count('"') + text.count('\u201c') + text.count('\u201d')
        quote_penalty = min(quote_count * 0.15, 0.9)

        return (
            mode_fit * 3.0
            + dialogue_ratio_bonus
            + keyword_coverage * 2.0
            + scene_bonus
            + pattern_bonus
            + structure_score * 2.0
            + rhythm_score * 1.5
            - wrong_sense_penalty
            - narrative_penalty
            - generic_penalty
            - quote_penalty
            - too_short_penalty
        )

    # ---- General scoring path ----
    mode_fit = 0.0
    if mode:
        mode_fit = 1.0 if record.get("mode_guess") == mode else 0.0

    rhythm_score = record.get("short_sentence_ratio", 0.0)

    return (
        mode_fit * 3.0
        + keyword_coverage * 2.0
        + structure_score * 2.0
        + rhythm_score * 1.0
        - too_short_penalty
    )


# ---------------------------------------------------------------------------
# Context window extraction (quote mode)
# ---------------------------------------------------------------------------

def _extract_context_window(text: str, query_tokens: list[str], context: int = 0) -> str:
    """
    Find the sentence with the highest keyword-match count and return it
    with `context` neighboring sentences on each side.

    context=0 → best sentence only (or full text if ≤ 3 sentences)
    context=1 → best sentence ± 1 neighbor
    """
    sents = [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]
    if not sents or context < 0:
        return text
    if len(sents) <= 3:
        return text  # Short passage — return whole thing

    if not query_tokens:
        return sents[0] if sents else text

    # Score each sentence by keyword hit count
    def _sent_hits(s: str) -> int:
        low = s.lower()
        return sum(1 for t in query_tokens if t in low)

    scored = [(i, _sent_hits(s)) for i, s in enumerate(sents)]
    best_idx = max(scored, key=lambda x: x[1])[0]

    lo = max(0, best_idx - context)
    hi = min(len(sents) - 1, best_idx + context)
    return " ".join(sents[lo:hi + 1])


# ---------------------------------------------------------------------------
# Public search API — quote mode
# ---------------------------------------------------------------------------

def search_quotes(
    query: str,
    author_folder: Path,
    top_k: int = 10,
    source_file: str | None = None,
    context: int = 0,
) -> list[dict]:
    """
    Quote-mode search: return compact, keyword-dense passages ranked for
    literal line-finding. A single memorable sentence can be the ideal result.

    query:       keyword string
    top_k:       number of results
    source_file: optional filter to a single source file
    context:     0 = best sentence only; 1 = best sentence ± 1 neighbor
    """
    records = _load_index(author_folder)
    if source_file:
        records = [r for r in records if r.get("source_file") == source_file]

    query_tokens = _tokenize_query(query)
    if not query_tokens:
        return []

    scored = []
    for r in records:
        s = _score_quote(r, query_tokens)
        if s > 0:
            scored.append((s, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [r for _, r in scored[:top_k]]

    results = []
    for r in top:
        snippet = _extract_context_window(r["text"], query_tokens, context)
        results.append({
            "passage_id": r["passage_id"],
            "source_file": r["source_file"],
            "mode": r["mode_guess"],
            "sentence_count": r["sentence_count"],
            "match_terms": [t for t in set(query_tokens) if t in r["text"].lower()],
            "text": snippet,
            "retrieval_mode": "quote",
        })
    return results


# ---------------------------------------------------------------------------
# Public search API — exemplar mode
# ---------------------------------------------------------------------------

def search_exemplars(
    query: str,
    author_folder: Path,
    top_k: int = 5,
) -> list[dict]:
    """
    Exemplar-mode search: return structurally rich passages useful for
    generation, rewriting, and style conditioning.

    Ranked by: mode fit, keyword coverage, structural richness, sentence rhythm.
    Prefers 3–8 sentence passages.
    """
    records = _load_index(author_folder)
    query_tokens = _tokenize_query(query)

    scored = []
    for r in records:
        s = _score_exemplar(r, query_tokens, mode=None, query=query)
        scored.append((s, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [r for _, r in scored[:top_k]]
    return [_format_exemplar_result(r) for r in top]


def search_exemplars_by_mode(
    query: str,
    author_folder: Path,
    mode: str,
    top_k: int = 5,
) -> list[dict]:
    """
    Exemplar-mode search filtered and ranked by mode.

    mode: action | reflective | descriptive | narrative | dialogue
    """
    records = _load_index(author_folder)

    # Pre-filter to mode for efficiency (scorer also weights mode fit)
    if mode == "dialogue":
        # Dialogue purity: prefer pure-dialogue passages first; fall back to mixed
        strict = [r for r in records if r.get("dialogue_mode") == "dialogue"]
        print(f"  [dialogue_purity] strict candidates (dialogue_mode=dialogue): {len(strict)}")
        if len(strict) >= top_k:
            candidates = strict
        else:
            mixed_pool = [r for r in records if r.get("dialogue_mode") in ("dialogue", "mixed")]
            print(f"  [dialogue_purity] fallback → mixed pool: {len(mixed_pool)} candidates")
            candidates = mixed_pool
    else:
        candidates = [r for r in records if r.get("mode_guess") == mode]

    if not candidates:
        candidates = records  # Fallback: score all, mode_fit will be 0

    query_tokens = _tokenize_query(query)
    scored = [(_score_exemplar(r, query_tokens, mode=mode, query=query), r) for r in candidates]
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [r for _, r in scored[:top_k]]
    return [_format_exemplar_result(r) for r in top]


def _format_exemplar_result(r: dict) -> dict:
    """Result format for exemplar retrieval — slightly richer than quote format."""
    return {
        "passage_id": r["passage_id"],
        "source_file": r["source_file"],
        "mode_guess": r["mode_guess"],
        "dialogue_mode": r["dialogue_mode"],
        "sentence_count": r["sentence_count"],
        "avg_sentence_length": r["avg_sentence_length"],
        "short_sentence_ratio": r["short_sentence_ratio"],
        "text": r["text"],
        "retrieval_mode": "exemplar",
    }


# ---------------------------------------------------------------------------
# Public search API (legacy / internal)
# ---------------------------------------------------------------------------

def search_passages(
    query: str,
    author_folder: Path,
    top_k: int = 10,
) -> list[dict]:
    """
    Full-corpus TF-IDF search over all indexed passages.
    Supports literal, phrase, and thematic queries.
    """
    records = _load_index(author_folder)
    results = _tfidf_search(query, records, top_k)
    return [_format_result(r) for r in results]


def search_passages_by_mode(
    query: str,
    author_folder: Path,
    mode: str,
    top_k: int = 10,
) -> list[dict]:
    """
    TF-IDF search filtered to a specific mode.

    mode: action | reflective | descriptive | narrative | dialogue
    For 'dialogue', filters by dialogue_mode ∈ {dialogue, mixed}.
    For other modes, filters by mode_guess.
    """
    records = _load_index(author_folder)

    if mode == "dialogue":
        filtered = [r for r in records if r.get("dialogue_mode") in ("dialogue", "mixed")]
    else:
        filtered = [r for r in records if r.get("mode_guess") == mode]

    results = _tfidf_search(query, filtered, top_k)
    return [_format_result(r) for r in results]


def search_structural_exemplars(
    author_folder: Path,
    mode: str | None = None,
    sentence_band: tuple[float, float] | None = None,
    dialogue_heavy: bool = False,
    top_k: int = 10,
) -> list[dict]:
    """
    Pure structural search — no text query required.

    mode:          filter by mode_guess (or 'dialogue' for dialogue_mode filter)
    sentence_band: (min_avg, max_avg) average sentence length range
    dialogue_heavy: if True, prefer passages with high dialogue_ratio
    top_k:         number of results
    """
    records = _load_index(author_folder)

    # Mode filter
    if mode == "dialogue":
        records = [r for r in records if r.get("dialogue_mode") in ("dialogue", "mixed")]
    elif mode:
        records = [r for r in records if r.get("mode_guess") == mode]

    # Sentence length band filter
    if sentence_band:
        lo, hi = sentence_band
        records = [r for r in records if lo <= r.get("avg_sentence_length", 0) <= hi]

    if not records:
        return []

    # Sort by dialogue_ratio (desc) or short_sentence_ratio (asc for short) or just passage_id order
    if dialogue_heavy:
        records = sorted(records, key=lambda r: r.get("dialogue_ratio", 0), reverse=True)
    else:
        # Sort by how representative of the mode they are (approximate: short ratio)
        records = sorted(records, key=lambda r: r.get("short_sentence_ratio", 0), reverse=True)

    return [_format_result(r) for r in records[:top_k]]
