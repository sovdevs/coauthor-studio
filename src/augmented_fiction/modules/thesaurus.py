"""
Thesaurus tool.

Lookup priority:
  1. Roget merged (1962 + 1911 archaic enrichment) — tiered, ranked
  2. Moby/file fallback — flat neutral list

Returns SynonymGroups mapped from display tiers:
  "best"              ← best_fit
  "less obvious"      ← less_obvious
  "archaic · literary"← archaic_literary (kept separate, tightly capped)

No LLM involved.
"""
from __future__ import annotations

from pydantic import BaseModel


class SynonymGroup(BaseModel):
    label: str
    alternatives: list[str]
    is_archaic: bool = False


class ThesaurusLookupResult(BaseModel):
    word: str = ""
    language: str = ""
    groups: list[SynonymGroup] = []
    notes: str = ""
    source: str = ""
    query_is_archaic: bool = False


def lookup(word: str, language: str, backend_config) -> ThesaurusLookupResult:
    """
    Look up synonyms for *word*.

    Tries Roget merged corpus first; falls back to Moby file if no results.

    Args:
        word:           word to find synonyms for
        language:       BCP-47 code (informational; used in result only)
        backend_config: LexicalBackendConfig (used for Moby fallback path)
    """
    # --- Roget merged lookup ---
    try:
        from augmented_fiction.modules.roget_lookup import roget_lookup
        roget_result = roget_lookup(word)
        if roget_result["found"]:
            return _roget_to_result(word, language, roget_result)
    except Exception:
        pass  # fall through to Moby

    # --- Moby fallback ---
    return _moby_lookup(word, language, backend_config)


def _roget_to_result(word: str, language: str, roget_result: dict) -> ThesaurusLookupResult:
    """Map tiered Roget result to ThesaurusLookupResult with named groups."""
    _TIER_LABEL = {
        "best_fit":         "best",
        "less_obvious":     "less obvious",
        "archaic_literary": "archaic · literary",
    }

    bucket: dict[str, list[str]] = {}
    archaic_bucket: list[str] = []

    for r in roget_result["results"]:
        tier = r["display_tier"]
        term = r["term"]
        if r["is_archaic"]:
            archaic_bucket.append(term)
        else:
            bucket.setdefault(tier, []).append(term)

    groups: list[SynonymGroup] = []
    for tier in ("best_fit", "less_obvious"):
        terms = bucket.get(tier, [])
        if terms:
            groups.append(SynonymGroup(
                label=_TIER_LABEL[tier],
                alternatives=terms,
                is_archaic=False,
            ))
    if archaic_bucket:
        groups.append(SynonymGroup(
            label=_TIER_LABEL["archaic_literary"],
            alternatives=archaic_bucket,
            is_archaic=True,
        ))

    return ThesaurusLookupResult(
        word=word,
        language=language,
        groups=groups,
        source="roget",
        query_is_archaic=roget_result.get("query_is_archaic", False),
    )


def _moby_lookup(word: str, language: str, backend_config) -> ThesaurusLookupResult:
    """Original Moby/file-backed lookup, kept as fallback."""
    from augmented_fiction.modules.lexical_backend import get_thes_backend

    paths = backend_config.paths if backend_config else []
    backend = get_thes_backend(paths[0]) if paths else None

    if backend is None:
        return ThesaurusLookupResult(
            word=word,
            language=language,
            notes="(thesaurus data not available — run scripts/fetch_lexical_data.py)",
            source="none",
        )

    synonyms = backend.lookup(word)
    if synonyms:
        return ThesaurusLookupResult(
            word=word,
            language=language,
            groups=[SynonymGroup(label="neutral", alternatives=synonyms)],
            source="file",
        )

    return ThesaurusLookupResult(
        word=word,
        language=language,
        notes="(not found in local thesaurus)",
        source="file",
    )
