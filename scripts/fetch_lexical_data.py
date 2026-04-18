"""
fetch_lexical_data.py — one-time setup script

Downloads and converts dictionary and thesaurus sources into the JSON
formats expected by the lexical backends.

Run from the repo root:
    python scripts/fetch_lexical_data.py            # all sources
    python scripts/fetch_lexical_data.py --dict     # dictionary only
    python scripts/fetch_lexical_data.py --thes     # thesaurus only
    python scripts/fetch_lexical_data.py --wikt     # wiktionary only

Output:
    resources/dictionary/dictionary_compact.json    (~25 MB, 102K words)
    resources/dictionary/wiktionary-en.json         (~120 MB, 1M+ words)
    resources/thesaurus/moby.json                   (~4 MB)

Sources:
    ChrisSpinu/dictionary   github.com/ChrisSpinu/dictionary         (public domain)
    Wiktionary compact      gitlab.com/tdulcet/compact-dictionary    (CC BY-SA)
    Moby thesaurus          github.com/words/moby                    (public domain)
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

DICT_URL = (
    "https://raw.githubusercontent.com/ChrisSpinu/dictionary"
    "/refs/heads/main/dictionary.json"
)
WIKT_URL = (
    "https://gitlab.com/tdulcet/compact-dictionaries/-/raw/main"
    "/wiktionary/dictionary-en.json?inline=false"
)
THES_URL = (
    "https://raw.githubusercontent.com/words/moby"
    "/master/words.txt"
)

DICT_OUT = Path("resources/dictionary/dictionary_compact.json")
WIKT_OUT = Path("resources/dictionary/wiktionary-en.json")
THES_OUT = Path("resources/thesaurus/moby.json")


def fetch_dictionary() -> None:
    """ChrisSpinu/dictionary — {"word": "definition string"} format."""
    print(f"Downloading ChrisSpinu dictionary from:\n  {DICT_URL}")
    with urllib.request.urlopen(DICT_URL, timeout=120) as resp:
        raw: dict[str, str] = json.loads(resp.read().decode())

    print(f"  {len(raw):,} entries — converting …")
    out: dict[str, dict] = {}
    for word, definition in raw.items():
        out[word.lower()] = {"definition": str(definition), "part_of_speech": "", "inflections": []}

    DICT_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(DICT_OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = DICT_OUT.stat().st_size / 1_048_576
    print(f"  Written {DICT_OUT}  ({size_mb:.1f} MB)")


def fetch_wiktionary() -> None:
    """Wiktionary compact — array of {"": word, "p": [pos], "d": [defs], "f": [forms]} objects."""
    print(f"\nDownloading Wiktionary (en) from:\n  {WIKT_URL}")
    with urllib.request.urlopen(WIKT_URL, timeout=300) as resp:
        raw = resp.read().decode("utf-8")

    # File is NDJSON — one JSON object per line
    entries: list[dict] = [json.loads(line) for line in raw.splitlines() if line.strip()]

    print(f"  {len(entries):,} entries — converting …")
    out: dict[str, dict] = {}
    for entry in entries:
        word = entry.get("", "")
        if not word:
            continue
        definitions = entry.get("d", [])
        pos_list = entry.get("p", [])
        forms = entry.get("f", [])
        out[word.lower()] = {
            "definition": "; ".join(definitions[:3]),   # cap at 3 senses
            "part_of_speech": ", ".join(pos_list),
            "inflections": forms,
        }

    WIKT_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(WIKT_OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = WIKT_OUT.stat().st_size / 1_048_576
    print(f"  Written {WIKT_OUT}  ({size_mb:.1f} MB)")


def fetch_thesaurus() -> None:
    """Moby thesaurus — CSV lines: headword,syn1,syn2,…"""
    print(f"\nDownloading Moby thesaurus from:\n  {THES_URL}")
    with urllib.request.urlopen(THES_URL, timeout=120) as resp:
        text = resp.read().decode("latin-1")

    out: dict[str, list[str]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",") if p.strip()]
        if not parts:
            continue
        headword = parts[0].lower()
        # Moby includes the headword itself as the first synonym — drop it
        synonyms = [p for p in parts[1:] if p.lower() != headword]
        if synonyms:
            out[headword] = synonyms

    print(f"  {len(out):,} entries — writing …")
    THES_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(THES_OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = THES_OUT.stat().st_size / 1_048_576
    print(f"  Written {THES_OUT}  ({size_mb:.1f} MB)")


if __name__ == "__main__":
    args = set(sys.argv[1:])
    run_all = not args

    if run_all or "--dict" in args:
        fetch_dictionary()
    if run_all or "--wikt" in args:
        fetch_wiktionary()
    if run_all or "--thes" in args:
        fetch_thesaurus()

    print("\nDone. Run 'uv run af write <project>' to use local lexical lookup.")
