"""
Build raw character evidence dossiers from a passage corpus.

For each selected character:
1. Find all passages that mention the character (name or aliases)
2. Send batches to LLM for classification into evidence buckets
3. Write a Markdown evidence file to <author_dir>/evidence/<slug>.md

Evidence buckets:
  A. speech          — what the character says
  B. description     — how the narrator / others describe them
  C. action          — what they do, choose, react to
  D. others_views    — what other characters say or think about them
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .ingest import Passage
from .candidate import CandidateCharacter


def build_evidence(
    character: CandidateCharacter,
    passages: list[Passage],
    author_dir: Path,
    author_name: str,
    llm_config,
    max_passages: int = 200,
    batch_size: int = 25,
) -> Path:
    """
    Build a raw evidence Markdown file for a character.
    Returns the path to the written file.
    """
    relevant = _find_relevant(character, passages, max_passages)
    print(f"    → {len(relevant)} relevant passage(s) found")

    buckets = _classify_in_batches(character, relevant, author_name, llm_config, batch_size)

    evidence_dir = author_dir / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    out_path = evidence_dir / f"{_slug(character.name)}.md"
    out_path.write_text(_render_md(character, buckets), encoding="utf-8")
    return out_path


# ── Evidence collection ───────────────────────────────────────────────────────

def _find_relevant(
    character: CandidateCharacter,
    passages: list[Passage],
    max_passages: int,
) -> list[Passage]:
    all_terms = [character.name] + character.aliases
    patterns = [
        re.compile(re.escape(t), re.IGNORECASE)
        for t in all_terms if t
    ]

    relevant: list[Passage] = []
    for p in passages:
        if any(pat.search(p.text) for pat in patterns):
            relevant.append(p)

    # Prioritise: dialogue > mixed > narrative > unknown
    priority = {"dialogue": 0, "mixed": 1, "narrative": 2, "unknown": 3}
    relevant.sort(key=lambda p: priority.get(p.dialogue_mode, 3))
    return relevant[:max_passages]


def _classify_in_batches(
    character: CandidateCharacter,
    passages: list[Passage],
    author_name: str,
    llm_config,
    batch_size: int,
) -> dict[str, list[str]]:
    import os
    from openai import OpenAI

    api_key = os.environ.get(llm_config.api_key_env, "")
    if not api_key:
        raise RuntimeError(f"LLM API key not set — expected env var: {llm_config.api_key_env}")
    client = OpenAI(api_key=api_key)

    buckets: dict[str, list[str]] = {
        "speech": [],
        "description": [],
        "action": [],
        "others_views": [],
        "source_refs": [],
    }

    total_batches = (len(passages) + batch_size - 1) // batch_size

    for batch_num, i in enumerate(range(0, len(passages), batch_size), 1):
        print(f"    ·  classifying batch {batch_num}/{total_batches}…", end="\r", flush=True)
        batch = passages[i: i + batch_size]
        _process_batch(character, batch, author_name, llm_config, client, buckets)

    print()  # clear the carriage-return line
    return buckets


def _process_batch(
    character: CandidateCharacter,
    batch: list[Passage],
    author_name: str,
    llm_config,
    client,
    buckets: dict[str, list[str]],
) -> None:
    batch_text = "\n\n---\n\n".join(
        f"[{p.source_file} / {p.passage_id}]\n{p.text}" for p in batch
    )

    prompt = f"""You are building a character evidence dossier for "{character.name}" from fiction by {author_name}.

Read these passages and extract evidence about {character.name} into four buckets.

Buckets:
  speech       — exact or near-exact lines spoken BY {character.name}
  description  — how the narrator or other characters DESCRIBE {character.name}
                 (appearance, manner, reputation, social role)
  action       — things {character.name} DOES, choices made, reactions under pressure
  others_views — what other characters SAY OR THINK about {character.name}

Rules:
- Preserve original language as closely as possible
- Prefix each item with its passage reference in brackets, e.g. [Blood Meridian / 000045]
- Omit passages with no relevant evidence — do not invent
- A passage may produce items in more than one bucket

Return ONLY valid JSON, no commentary:
{{
  "speech":       ["[ref] line spoken by character", ...],
  "description":  ["[ref] description of character", ...],
  "action":       ["[ref] action or reaction", ...],
  "others_views": ["[ref] what others say about character", ...]
}}

Passages:
{batch_text}"""

    resp = client.chat.completions.create(
        model=llm_config.model,
        max_tokens=2048,
        messages=[
            {"role": "system", "content": "You are a literary analyst. Return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
    )

    raw = (resp.choices[0].message.content or "").strip()
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if not m:
        return

    try:
        result = json.loads(m.group())
    except json.JSONDecodeError:
        return

    for key in ("speech", "description", "action", "others_views"):
        items = result.get(key, [])
        if isinstance(items, list):
            buckets[key].extend(str(x) for x in items if x)

    # Track source files
    for p in batch:
        if p.source_file and p.source_file not in buckets["source_refs"]:
            buckets["source_refs"].append(p.source_file)


# ── Rendering ─────────────────────────────────────────────────────────────────

def _render_md(character: CandidateCharacter, buckets: dict) -> str:
    lines = [f"# Character Raw Evidence: {character.name}", ""]

    if character.aliases:
        lines.append(f"**Aliases:** {', '.join(character.aliases)}")
        lines.append("")

    lines += [
        f"**Corpus stats:** {character.mention_count} mention(s), "
        f"{character.dialogue_count} in dialogue passage(s), "
        f"{character.book_spread} book(s)",
        "",
    ]

    def _section(title: str, items: list[str], quote_style: bool = False) -> None:
        lines.append(f"## {title}")
        lines.append("")
        if items:
            for item in items:
                prefix = "> " if quote_style else "- "
                lines.append(f"{prefix}{item}")
                if quote_style:
                    lines.append("")
        else:
            lines.append("_(none found)_")
            lines.append("")

    _section("Spoken Dialogue", buckets["speech"], quote_style=True)
    _section("Narrative Description", buckets["description"])
    lines.append("")
    _section("Action / Reaction Scenes", buckets["action"])
    lines.append("")
    _section("Other Characters' Views", buckets["others_views"])
    lines.append("")

    if buckets["source_refs"]:
        lines += ["## Source References", ""]
        for ref in buckets["source_refs"]:
            lines.append(f"- {ref}")

    return "\n".join(lines)


def _slug(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", "_", text)
    return text.strip("_")
