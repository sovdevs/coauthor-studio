"""
Detect and rank candidate characters from a passage corpus.

Flow:
1. Sample passages (beginning + middle + end of corpus)
2. LLM identifies named characters with aliases
3. Count full-corpus mentions for each candidate
4. Rank by weighted score (dialogue passages weighted 2×, book spread 3×)
5. Present ranked list; user selects interactively
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .ingest import Passage


@dataclass
class CandidateCharacter:
    name: str
    aliases: list[str] = field(default_factory=list)
    mention_count: int = 0
    dialogue_count: int = 0
    book_spread: int = 0        # number of distinct source files
    rank_score: float = 0.0

    def star_rating(self) -> str:
        if self.rank_score >= 300:
            return "★★★★★"
        if self.rank_score >= 150:
            return "★★★★"
        if self.rank_score >= 60:
            return "★★★"
        if self.rank_score >= 20:
            return "★★"
        return "★"


# ── Detection ─────────────────────────────────────────────────────────────────

def detect_candidates(
    passages: list[Passage],
    author_name: str,
    llm_config,
    sample_size: int = 150,
) -> list[CandidateCharacter]:
    """
    Return a ranked list of candidate characters detected in the passage corpus.
    """
    sample = _sample_passages(passages, sample_size)
    raw = _llm_extract_names(sample, author_name, llm_config)   # [{name, aliases}]
    return _rank_by_frequency(raw, passages)


def _sample_passages(passages: list[Passage], n: int) -> list[Passage]:
    """Representative sample: beginning + middle + end."""
    if len(passages) <= n:
        return passages
    third = n // 3
    mid = len(passages) // 2
    half_third = third // 2
    return (
        passages[:third]
        + passages[mid - half_third: mid + half_third]
        + passages[-third:]
    )


def _llm_extract_names(sample: list[Passage], author_name: str, llm_config) -> list[dict]:
    """Ask the LLM to identify named characters in a text sample."""
    import os
    from openai import OpenAI

    api_key = os.environ.get(llm_config.api_key_env, "")
    if not api_key:
        raise RuntimeError(f"LLM API key not set — expected env var: {llm_config.api_key_env}")
    client = OpenAI(api_key=api_key)

    # Build text block — cap at 100 passages to stay within a reasonable prompt
    text_block = "\n\n".join(
        f"[{p.source_file}] {p.text}" for p in sample[:100]
    )

    system = "You are a literary analyst. Return only valid JSON, no commentary."
    user = f"""You are analyzing prose fiction by {author_name}.

Below is a sample of passages from their work.

Task: list all named human characters you can identify. Include:
- protagonists and major characters
- named supporting characters
- recurring unnamed-but-significant figures (e.g. "The Kid", "The Judge", "The Man")

Exclude:
- historical or real-world figures mentioned only in passing
- purely generic walk-on characters with no identity
- the author themselves

For each character give:
- "name": their most common name or epithet in the text
- "aliases": other names, pronouns-used-as-names, or epithets they go by

Return ONLY a JSON array, no commentary:
[
  {{"name": "Judge Holden", "aliases": ["the Judge", "Holden"]}},
  {{"name": "The Kid", "aliases": ["the kid", "the boy"]}}
]

Passages:
{text_block}"""

    resp = client.chat.completions.create(
        model=llm_config.model,
        max_tokens=1024,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )

    raw = (resp.choices[0].message.content or "").strip()
    m = re.search(r'\[.*\]', raw, re.DOTALL)
    if not m:
        return []
    try:
        items = json.loads(m.group())
        return [i for i in items if isinstance(i, dict) and i.get("name")]
    except json.JSONDecodeError:
        return []


def _rank_by_frequency(
    raw_candidates: list[dict],
    passages: list[Passage],
) -> list[CandidateCharacter]:
    """Count corpus-wide mentions for each candidate and compute rank score."""
    results: list[CandidateCharacter] = []
    seen: set[str] = set()

    for cand in raw_candidates:
        name = (cand.get("name") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())

        aliases = [a for a in cand.get("aliases", []) if a and a.lower() != name.lower()]
        all_terms = [name] + aliases

        mention_count = 0
        dialogue_count = 0
        source_files: set[str] = set()

        # Compile patterns once for efficiency
        patterns = [
            re.compile(re.escape(t), re.IGNORECASE)
            for t in all_terms if t
        ]

        for p in passages:
            if any(pat.search(p.text) for pat in patterns):
                mention_count += 1
                source_files.add(p.source_file)
                if p.dialogue_mode in ("dialogue", "mixed"):
                    dialogue_count += 1

        if mention_count == 0:
            continue

        # Dialogue presence and book spread weighted over raw mention count.
        # mention_count alone inflates characters who are heavily described
        # but never speak — dialogue_count is a stronger signal of evidence richness.
        rank_score = (
            mention_count * 0.5
            + dialogue_count * 4.0
            + len(source_files) * 6.0
        )

        results.append(CandidateCharacter(
            name=name,
            aliases=aliases,
            mention_count=mention_count,
            dialogue_count=dialogue_count,
            book_spread=len(source_files),
            rank_score=rank_score,
        ))

    return sorted(results, key=lambda c: c.rank_score, reverse=True)


# ── Interactive selection ─────────────────────────────────────────────────────

def select_interactively(candidates: list[CandidateCharacter]) -> list[CandidateCharacter]:
    """
    Print ranked candidate list and prompt user to select which to draft.

    Accepts:
      - numbers: 1,2,3 or 1-3 or 1 3 5
      - "all"
      - empty input → cancel

    Returns the selected subset.
    """
    if not candidates:
        print("\n  No candidates detected.")
        return []

    print("\n  Detected candidates:\n")
    print(f"  {'#':<4} {'Name':<28} {'mentions':>8}  {'dialogue':>8}  {'books':>5}  score")
    print("  " + "-" * 68)
    for i, c in enumerate(candidates, 1):
        aliases = f"  ({', '.join(c.aliases[:2])})" if c.aliases else ""
        print(
            f"  {i:<4} {c.name:<28} {c.mention_count:>8}  "
            f"{c.dialogue_count:>8}  {c.book_spread:>5}  "
            f"{c.star_rating()}{aliases}"
        )

    print()
    print("  Enter numbers to extract (e.g. 1,2  or  1-3  or  all),")
    print("  or press Enter to cancel:")
    print()

    try:
        raw = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return []

    if not raw:
        return []

    if raw.lower() == "all":
        return candidates

    # Parse: comma-separated numbers and/or ranges like 1-3
    selected: list[CandidateCharacter] = []
    seen_idx: set[int] = set()
    tokens = re.split(r"[\s,]+", raw)

    for token in tokens:
        token = token.strip()
        if not token:
            continue
        range_m = re.fullmatch(r"(\d+)-(\d+)", token)
        if range_m:
            lo, hi = int(range_m.group(1)), int(range_m.group(2))
            for n in range(lo, hi + 1):
                if 1 <= n <= len(candidates) and n not in seen_idx:
                    selected.append(candidates[n - 1])
                    seen_idx.add(n)
        elif token.isdigit():
            n = int(token)
            if 1 <= n <= len(candidates) and n not in seen_idx:
                selected.append(candidates[n - 1])
                seen_idx.add(n)
        else:
            print(f"  Skipping unrecognized token: {token!r}")

    return selected
