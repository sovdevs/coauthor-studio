"""
Retrieval-augmented style guidance.

At analyze time: given user text, retrieve the N most relevant exemplar
passages using TF-IDF similarity + feature/mode similarity.

The TF-IDF vectorizer is fitted on-demand from the exemplar passage store
(~50 passages) — fast enough to do at request time without pre-caching.
"""
from __future__ import annotations

import json
from pathlib import Path


def _load_exemplars(exemplar_path: Path) -> list[dict]:
    exemplars: list[dict] = []
    with exemplar_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                exemplars.append(json.loads(line))
    return exemplars


def _feature_score(passage: dict, user_features: dict, user_mode: str) -> float:
    """
    Score an exemplar passage against user features.
    Returns a value in [0, 1].
    """
    score = 0.0

    # Mode match is the strongest signal
    if passage.get("mode_guess") == user_mode:
        score += 0.40

    passage_features = passage.get("features", {})
    p_avg_len = passage_features.get("avg_sentence_length", 10.0)
    u_avg_len = user_features.get("avg_sentence_length", 10.0)
    len_diff = abs(p_avg_len - u_avg_len)
    if len_diff < 2:
        score += 0.20
    elif len_diff < 5:
        score += 0.10

    p_short = passage_features.get("short_sentence_ratio", 0.5)
    u_short = user_features.get("short_sentence_ratio", 0.5)
    if abs(p_short - u_short) < 0.15:
        score += 0.10

    p_phys = passage_features.get("phys_verb_ratio", 0.5)
    u_phys = user_features.get("phys_verb_ratio", 0.5)
    if abs(p_phys - u_phys) < 0.15:
        score += 0.10

    return min(score, 1.0)


def retrieve_exemplars(
    user_text: str,
    user_features: dict,
    user_mode: str,
    exemplar_path: Path,
    n: int = 5,
    mode_filter: str | None = None,
) -> list[dict]:
    """
    Retrieve the top-n exemplar passages most relevant to the user text.

    mode_filter="dialogue" — restrict to passages tagged dialogue or mixed;
                             falls back to all exemplars if insufficient matches.

    Combines:
      - TF-IDF cosine similarity (lexical overlap, 60% weight)
      - Feature + mode similarity (40% weight)
    """
    if not exemplar_path.exists():
        return []

    exemplars = _load_exemplars(exemplar_path)
    if not exemplars:
        return []

    # Apply mode filter with fallback
    if mode_filter == "dialogue":
        filtered = [e for e in exemplars if e.get("dialogue_mode") in ("dialogue", "mixed")]
        if len(filtered) >= max(n, 2):
            exemplars = filtered
        elif filtered:
            # Partial match — use what we have, pad from full set
            exemplars = filtered + [e for e in exemplars if e not in filtered]

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    texts = [e["text"] for e in exemplars]
    vectorizer = TfidfVectorizer(max_features=3000, ngram_range=(1, 2), stop_words="english")
    exemplar_matrix = vectorizer.fit_transform(texts)
    user_vec = vectorizer.transform([user_text])

    tfidf_sims = cosine_similarity(user_vec, exemplar_matrix).flatten()

    scored: list[tuple[float, int]] = []
    for i, (exemplar, tfidf_sim) in enumerate(zip(exemplars, tfidf_sims)):
        feat_sim = _feature_score(exemplar, user_features, user_mode)
        combined = 0.60 * float(tfidf_sim) + 0.40 * feat_sim
        scored.append((combined, i))

    scored.sort(reverse=True)

    results: list[dict] = []
    for _, i in scored[:n]:
        e = exemplars[i]
        results.append({
            "source_file": e["source_file"],
            "passage_id": e["passage_id"],
            "mode_guess": e.get("mode_guess", "narrative"),
            "text": e["text"],
        })

    return results
