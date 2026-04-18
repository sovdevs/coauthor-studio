"""
Local file-based lexical backends for dictionary and thesaurus.

Both backends load JSON once on first use and cache the instance.
Lookup is O(1) via a lowercase index. Dictionary also supports
fuzzy suggestions via difflib for near-miss words.

Expected JSON formats
---------------------
Dictionary  (resources/dictionary/dictionary_compact.json):
    {"word": {"definition": "...", "part_of_speech": "..."}, ...}

Thesaurus   (resources/thesaurus/moby.json):
    {"word": ["syn1", "syn2", ...], ...}
"""
from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Optional


class DictFileBackend:
    """
    Loads one dictionary JSON file and indexes it by lowercase word.

    Supported source formats (auto-detected):

    1. Object of objects — our normalised format (and ChrisSpinu):
       {"word": {"definition": "...", "part_of_speech": "...", "inflections": [...]}}
       Values may also be plain strings (ChrisSpinu raw).

    2. Array of Wiktionary compact objects:
       [{"": "word", "p": ["pos"], "d": ["def1", "def2"], "f": ["form1"]}, ...]
    """

    def __init__(self, path: str) -> None:
        abs_path = Path(path) if Path(path).is_absolute() else Path.cwd() / path
        with open(abs_path, encoding="utf-8") as f:
            raw = json.load(f)

        self._index: dict[str, dict] = {}

        if isinstance(raw, list):
            # Wiktionary compact array format
            for entry in raw:
                word = entry.get("", "")
                if not word:
                    continue
                self._index[word.lower()] = {
                    "definition": "; ".join(entry.get("d", [])[:3]),
                    "part_of_speech": ", ".join(entry.get("p", [])),
                    "inflections": entry.get("f", []),
                }
        else:
            # Object-keyed format (normalised or ChrisSpinu raw)
            for word, value in raw.items():
                key = word.lower()
                if isinstance(value, str):
                    self._index[key] = {"definition": value, "part_of_speech": "", "inflections": []}
                elif isinstance(value, dict):
                    self._index[key] = {
                        "definition": value.get("definition", ""),
                        "part_of_speech": value.get("part_of_speech", ""),
                        "inflections": value.get("inflections", []),
                    }

        self._words: list[str] = list(self._index.keys())

    def lookup(self, word: str) -> Optional[dict]:
        return self._index.get(word.lower())

    def suggestions(self, word: str, n: int = 5, cutoff: float = 0.7) -> list[str]:
        return difflib.get_close_matches(word.lower(), self._words, n=n, cutoff=cutoff)


class ThesFileBackend:
    def __init__(self, path: str) -> None:
        abs_path = Path(path) if Path(path).is_absolute() else Path.cwd() / path
        with open(abs_path, encoding="utf-8") as f:
            raw: dict = json.load(f)
        self._index: dict[str, list[str]] = {k.lower(): v for k, v in raw.items()}

    def lookup(self, word: str) -> Optional[list[str]]:
        return self._index.get(word.lower())


# Module-level cache — backends are loaded once per process
_dict_cache: dict[str, DictFileBackend] = {}
_thes_cache: dict[str, ThesFileBackend] = {}


def get_dict_backend(path: str) -> Optional[DictFileBackend]:
    if path not in _dict_cache:
        try:
            _dict_cache[path] = DictFileBackend(path)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
    return _dict_cache[path]


def get_thes_backend(path: str) -> Optional[ThesFileBackend]:
    if path not in _thes_cache:
        try:
            _thes_cache[path] = ThesFileBackend(path)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
    return _thes_cache[path]
