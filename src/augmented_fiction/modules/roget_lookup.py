"""
Roget merged thesaurus lookup.

Pipeline (per query):
  Step 1 — exact lookup in Roget 1962 (primary synonym surface)
  Step 2 — category_ids from Roget 1911 index (archaic enrichment)
  Step 3 — archaic/literary candidates from matched categories
  Step 4 — merge, deduplicate, score, tier, cap

Sources:
  roget1962_dictionary_entries_clean.jsonl  — primary (word → synonym groups + POS)
  index_entries.jsonl                       — 1911 index (word → category_ids)
  archaic_terms.jsonl                       — archaic terms by category_id
  archive_dict_entries.jsonl                — optional short definitions for archaic terms

Loaded once at first call; module-level cache thereafter.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from functools import lru_cache

# Project root is 3 levels above this file: modules/ → augmented_fiction/ → src/ → <root>
_ROGET_JSONL = Path(__file__).parents[3] / "modules" / "voice" / "roget" / "jsonl"

# ---------------------------------------------------------------------------
# Module-level index cache (loaded once)
# ---------------------------------------------------------------------------

_INDEX_1962:       dict[str, list[dict]] = {}   # normalized_entry → list[entry]
_INDEX_1911:       dict[str, list[int]]  = {}   # normalized_entry → list[category_id]
_CAT_TO_1911:     dict[int, list[str]]  = {}   # category_id → list[normalized_entry] (inverted 1911)
_CAT_HEADING:     dict[int, str]        = {}   # category_id → heading string
_ARCHAIC_BY_CAT:  dict[int, list[dict]] = {}   # category_id → list[archaic_term record]
_ARCHIVE_DEFS:    dict[str, str]         = {}   # normalized_term → excerpt
_LOADED = False


def _ensure_loaded() -> None:
    global _LOADED
    if _LOADED:
        return

    # 1962 index
    p = _ROGET_JSONL / "roget1962_dictionary_entries_clean.jsonl"
    if p.exists():
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = json.loads(line)
                key = r.get("normalized_entry", "")
                if key:
                    _INDEX_1962.setdefault(key, []).append(r)

    # 1911 index (category_ids per word) + inverted index
    p = _ROGET_JSONL / "index_entries.jsonl"
    if p.exists():
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = json.loads(line)
                key = r.get("normalized_entry", "")
                cat_ids = [rel["category_id"] for rel in r.get("relations", [])
                           if isinstance(rel.get("category_id"), int)]
                if key and cat_ids:
                    _INDEX_1911[key] = cat_ids
                    for cid in cat_ids:
                        _CAT_TO_1911.setdefault(cid, []).append(key)

    # Category headings
    p = _ROGET_JSONL / "categories.jsonl"
    if p.exists():
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = json.loads(line)
                cid = r.get("category_id")
                heading = r.get("heading", "")
                if isinstance(cid, int) and heading:
                    _CAT_HEADING[cid] = heading

    # Archaic terms by category
    p = _ROGET_JSONL / "archaic_terms.jsonl"
    if p.exists():
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = json.loads(line)
                cat_id = r.get("category_id")
                if isinstance(cat_id, int):
                    _ARCHAIC_BY_CAT.setdefault(cat_id, []).append(r)

    # Archive definitions
    p = _ROGET_JSONL / "archive_dict_entries.jsonl"
    if p.exists():
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = json.loads(line)
                key = r.get("normalized_term", "")
                if key and r.get("excerpt"):
                    # Keep only a short snippet
                    excerpt = r["excerpt"]
                    _ARCHIVE_DEFS[key] = excerpt[:120].rstrip() + ("…" if len(excerpt) > 120 else "")

    _LOADED = True


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def normalize(word: str) -> str:
    """Lowercase, strip leading/trailing punctuation and whitespace."""
    word = word.lower().strip()
    word = re.sub(r"^[^\w]+|[^\w]+$", "", word)
    word = word.replace("\u2019", "'").replace("\u2018", "'")
    return word


# ---------------------------------------------------------------------------
# Common/obvious short words (mild penalty in scoring)
# ---------------------------------------------------------------------------

_COMMON_SHORT = frozenset([
    "go", "get", "give", "have", "make", "let", "put", "set", "cut", "run",
    "say", "see", "sit", "use", "try", "end", "add", "bad", "big", "far",
    "few", "old", "new", "own", "way", "day", "man", "men", "one", "two",
    "top", "low", "off", "out", "up", "in", "on", "at", "by", "do", "be",
])


# ---------------------------------------------------------------------------
# Step 1 — 1962 candidate extraction
# ---------------------------------------------------------------------------

def _extract_1962(norm_query: str, pos_hint: str | None) -> list[dict]:
    """
    Extract synonym candidates from the 1962 index.
    Returns list of candidate dicts with term, pos, labels, group_index, source_1962=True.
    """
    _ensure_loaded()
    entries = _INDEX_1962.get(norm_query, [])
    candidates: list[dict] = []

    for entry in entries:
        entry_pos = entry.get("pos", "")
        pos_match = (
            pos_hint is None
            or entry_pos == pos_hint
            or not pos_hint
        )

        for g_idx, group in enumerate(entry.get("synonym_groups", [])):
            label = group.get("label", "")
            for term_row in group.get("term_rows", []):
                term = term_row.get("term", "").strip()
                norm_term = term_row.get("normalized_term", normalize(term))
                if not term or norm_term == norm_query:
                    continue
                # Skip OCR hyphen-join artifacts: e.g. "hush-hush" → "hushhush"
                # (even-length, first half == second half)
                nlen = len(norm_term)
                if nlen > 6 and nlen % 2 == 0 and norm_term[:nlen // 2] == norm_term[nlen // 2:]:
                    continue
                # Skip likely OCR-corrupted compounds (no vowels in long sequences)
                if nlen > 14 and not re.search(r"[aeiou]{1}", norm_term):
                    continue
                candidates.append({
                    "term": term,
                    "normalized_term": norm_term,
                    "pos": entry_pos,
                    "labels": [label] if label else [],
                    "group_index": g_idx,
                    "pos_match": pos_match,
                    "source_1962": True,
                    "source_archaic": False,
                    "is_archaic": False,
                    "definition": None,
                })

    return candidates


# ---------------------------------------------------------------------------
# Step 2 — 1911 category_ids for the query
# ---------------------------------------------------------------------------

def _get_category_ids(norm_query: str) -> list[int]:
    _ensure_loaded()
    return _INDEX_1911.get(norm_query, [])


# ---------------------------------------------------------------------------
# Step 3 — archaic enrichment from matched categories
# ---------------------------------------------------------------------------

def _get_archaic_candidates(cat_ids: list[int], norm_query: str) -> list[dict]:
    """
    Return archaic terms from categories linked to the query word.
    Capped tightly — only the best 3 candidates are returned for further filtering.
    """
    _ensure_loaded()
    seen: set[str] = set()
    archaic: list[dict] = []

    for cat_id in cat_ids:
        for rec in _ARCHAIC_BY_CAT.get(cat_id, []):
            norm_term = rec.get("normalized_term", "")
            if not norm_term or norm_term == norm_query or norm_term in seen:
                continue
            seen.add(norm_term)
            definition = _ARCHIVE_DEFS.get(norm_term)
            archaic.append({
                "term": rec.get("term", norm_term),
                "normalized_term": norm_term,
                "pos": None,
                "labels": [rec.get("category_heading", "")],
                "group_index": 99,
                "pos_match": False,
                "source_1962": False,
                "source_archaic": True,
                "is_archaic": True,
                "definition": definition,
            })

    return archaic


# ---------------------------------------------------------------------------
# Step 3b — 1962 category-peer fallback (for words absent from 1962)
# ---------------------------------------------------------------------------

def _extract_category_peers(cat_ids: list[int], norm_query: str, pos_hint: str | None) -> list[dict]:
    """
    When the query has no direct 1962 hit, find 1962-indexed words that share
    the same Roget categories (via 1911) and return them as candidates.

    These are "peers" in the same conceptual neighbourhood — weaker than direct
    synonyms but still meaningfully related.  Cap tightly: at most 20 words per
    category (to avoid flooding with tangentially related terms).
    """
    _ensure_loaded()
    seen: set[str] = set()
    peers: list[dict] = []

    for cat_id in cat_ids:
        heading = _CAT_HEADING.get(cat_id, "")
        count = 0
        for word in _CAT_TO_1911.get(cat_id, []):
            if word == norm_query or word in seen or word not in _INDEX_1962:
                continue
            seen.add(word)
            # Use the first 1962 entry for POS
            entry = _INDEX_1962[word][0]
            entry_pos = entry.get("pos", "")
            pos_match = (pos_hint is None or entry_pos == pos_hint or not pos_hint)
            peers.append({
                "term": entry.get("entry", word),
                "normalized_term": word,
                "pos": entry_pos,
                "labels": [heading] if heading else [],
                "group_index": 2,          # treat as mid-group
                "pos_match": pos_match,
                "source_1962": True,
                "source_archaic": False,
                "is_archaic": False,
                "definition": None,
            })
            count += 1
            if count >= 20:
                break

    return peers


# ---------------------------------------------------------------------------
# Step 4 — merge, deduplicate, score, tier, cap
# ---------------------------------------------------------------------------

def _score(c: dict) -> float:
    """
    Score a single candidate.
    Archaic terms always score low (they go to the archaic tier regardless).
    """
    if c["is_archaic"]:
        return 0.3

    score = 1.0

    # POS match
    if c.get("pos_match"):
        score += 0.5

    # Length heuristic: longer = less obvious = slightly preferred over generic short words
    n = len(c["normalized_term"])
    if n >= 9:
        score += 0.35
    elif n >= 6:
        score += 0.15
    elif n <= 4 and c["normalized_term"] in _COMMON_SHORT:
        score -= 0.3

    # Group position penalty: later groups are more peripheral
    score -= c["group_index"] * 0.12

    # Meaningful label bonus
    labels = c.get("labels", [])
    if labels and labels[0] and labels[0] not in ("neutral", ""):
        score += 0.15

    return max(0.0, score)


def _merge_and_rank(
    norm_query: str,
    candidates_1962: list[dict],
    archaic_candidates: list[dict],
) -> list[dict]:
    """Merge, deduplicate by normalized_term, score, sort."""
    pool: dict[str, dict] = {}

    for c in candidates_1962:
        k = c["normalized_term"]
        if k == norm_query:
            continue
        if k not in pool:
            pool[k] = dict(c)
        else:
            # Merge labels
            existing_labels = set(pool[k]["labels"])
            for lbl in c["labels"]:
                if lbl and lbl not in existing_labels:
                    pool[k]["labels"].append(lbl)

    for c in archaic_candidates:
        k = c["normalized_term"]
        if k == norm_query or k in pool:
            continue
        pool[k] = dict(c)

    # Score and sort
    scored = list(pool.values())
    for c in scored:
        c["score"] = _score(c)

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def _assign_tiers(scored: list[dict]) -> list[dict]:
    """
    Assign display_tier and cap:
      best_fit:         top non-archaic with score ≥ 1.1  (cap 10)
      less_obvious:     next non-archaic                  (cap 8)
      archaic_literary: top archaic terms                 (cap 4)
    """
    best_fit: list[dict] = []
    less_obvious: list[dict] = []
    archaic_literary: list[dict] = []

    for c in scored:
        if c["is_archaic"]:
            if len(archaic_literary) < 4:
                c["display_tier"] = "archaic_literary"
                archaic_literary.append(c)
        elif c["score"] >= 1.1 and len(best_fit) < 10:
            c["display_tier"] = "best_fit"
            best_fit.append(c)
        elif len(less_obvious) < 8:
            c["display_tier"] = "less_obvious"
            less_obvious.append(c)

    return best_fit + less_obvious + archaic_literary


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def roget_lookup(word: str, pos: str | None = None) -> dict:
    """
    Look up a word in the merged Roget corpus.

    Returns:
        {
            "query": str,
            "normalized_query": str,
            "found": bool,
            "results": list[{
                "term", "score", "display_tier",
                "labels", "is_archaic", "definition"
            }]
        }
    """
    norm_query = normalize(word)

    candidates_1962 = _extract_1962(norm_query, pos)
    cat_ids = _get_category_ids(norm_query)
    archaic_candidates = _get_archaic_candidates(cat_ids, norm_query)

    # If no direct 1962 hit, try category-peer fallback (word in 1911 but not 1962).
    # A word that exists in 1911 but was dropped from 1962 is archaic/literary.
    query_is_archaic = False
    if not candidates_1962 and cat_ids:
        candidates_1962 = _extract_category_peers(cat_ids, norm_query, pos)
        query_is_archaic = True

    merged = _merge_and_rank(norm_query, candidates_1962, archaic_candidates)
    tiered = _assign_tiers(merged)

    results = [
        {
            "term": c["term"],
            "score": round(c["score"], 3),
            "display_tier": c["display_tier"],
            "labels": c["labels"][:2],    # cap labels shown
            "is_archaic": c["is_archaic"],
            "definition": c.get("definition"),
        }
        for c in tiered
    ]

    return {
        "query": word,
        "normalized_query": norm_query,
        "found": bool(results),
        "query_is_archaic": query_is_archaic,
        "results": results,
    }
