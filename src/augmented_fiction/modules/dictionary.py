"""
Dictionary tool — file-backed local lookup, multi-source.

Tries each path in backend_config.paths in order; the first file that
contains the word wins. Fuzzy spelling suggestions are drawn from the
first (primary) backend on a miss.
No LLM is involved.
"""
from __future__ import annotations

from pydantic import BaseModel


class DictionaryLookupResult(BaseModel):
    word: str = ""
    language: str = ""
    definition: str
    part_of_speech: str
    inflections: list[str] = []
    notes: str = ""
    source: str = ""
    suggestions: list[str] = []


def lookup(word: str, language: str, backend_config) -> DictionaryLookupResult:
    """
    Look up *word* across the configured local dictionary files.

    Args:
        word:           word to look up
        language:       BCP-47 code (informational; stored in result)
        backend_config: LexicalBackendConfig with .paths list
    """
    from augmented_fiction.modules.lexical_backend import get_dict_backend

    paths = backend_config.paths if backend_config else []

    if not paths:
        return DictionaryLookupResult(
            word=word,
            language=language,
            definition="(no dictionary configured — run scripts/fetch_lexical_data.py)",
            part_of_speech="",
            source="none",
        )

    primary = get_dict_backend(paths[0])

    # Try each backend in order
    for i, path in enumerate(paths):
        backend = get_dict_backend(path)
        if backend is None:
            continue
        entry = backend.lookup(word)
        if entry:
            return DictionaryLookupResult(
                word=word,
                language=language,
                definition=entry.get("definition", ""),
                part_of_speech=entry.get("part_of_speech", ""),
                inflections=entry.get("inflections", []),
                source=f"file[{i}]",
            )

    # Not found in any backend — fuzzy suggestions from primary
    suggestions = primary.suggestions(word) if primary else []
    return DictionaryLookupResult(
        word=word,
        language=language,
        definition="(not found in local dictionary)",
        part_of_speech="",
        notes=f"Did you mean: {', '.join(suggestions)}?" if suggestions else "",
        source="file",
        suggestions=suggestions,
    )
