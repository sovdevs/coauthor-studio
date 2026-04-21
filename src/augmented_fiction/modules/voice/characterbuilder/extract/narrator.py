"""
Narrator extraction — optional per-book path.

Activated by --include-narrator flag on :cb extract.

Each book produces its own narrator profile:
  display_name = "Narrator — <book_name>"
  story.role   = "narrator"
  source_mode  = "extracted"

Evidence comes exclusively from non-dialogue narrative passages.
Narrators are not merged across books.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from augmented_fiction.modules.voice.characterbuilder.schema import (
    Behavior,
    CharacterProfile,
    Demographics,
    InnerEngine,
    Provenance,
    Signature,
    Story,
    StyleTrace,
    Surface,
    Voice,
    make_character_id,
    source_slug,
)
from augmented_fiction.modules.voice.characterbuilder.storage import (
    _REGISTRY_ROOT,
    existing_ids,
    registry_json_path,
    save_character,
)
from .ingest import Passage
from .synthesize import (
    ExtractionSidecar,
    FieldConfidence,
    _enum,
    _bool_or_none,
    _str_list,
    save_sidecar,
)


# ── Public API ────────────────────────────────────────────────────────────────

def extract_narrators(
    passages: list[Passage],
    author_dir: Path,
    author_name: str,
    llm_config,
    max_passages_per_book: int = 120,
) -> list[tuple[CharacterProfile, ExtractionSidecar]]:
    """
    For each book in the passage corpus, synthesise a narrator profile.
    Returns list of (profile, sidecar) pairs.
    """
    # Group narrative passages by source file (book)
    books: dict[str, list[Passage]] = {}
    for p in passages:
        if p.dialogue_mode in ("narrative", "unknown"):
            books.setdefault(p.source_file, []).append(p)

    results = []
    for source_file, book_passages in sorted(books.items()):
        book_name = Path(source_file).stem
        print(f"\n  ── Narrator: {book_name} ──────────────────────────────")

        # Take a representative spread across the book
        sample = _sample(book_passages, max_passages_per_book)
        print(f"    → {len(sample)} narrative passage(s) sampled")

        raw = _llm_synthesize_narrator(book_name, sample, author_name, llm_config)
        profile, sidecar = _build_narrator_profile(
            book_name=book_name,
            source_file=source_file,
            raw=raw,
            author_name=author_name,
            author_dir=author_dir,
            passage_count=len(sample),
        )
        results.append((profile, sidecar))

    return results


# ── Sampling ──────────────────────────────────────────────────────────────────

def _sample(passages: list[Passage], n: int) -> list[Passage]:
    """Spread sample evenly across the book."""
    if len(passages) <= n:
        return passages
    step = len(passages) / n
    return [passages[int(i * step)] for i in range(n)]


# ── LLM synthesis ─────────────────────────────────────────────────────────────

_NARRATOR_PROMPT = """\
You are analyzing the narrator voice of "{book}" by {author}.

Below are narrative prose passages from this work (non-dialogue only).

Your task: synthesize a narrator profile that captures how this narrator speaks and observes.

Focus on:
- prose rhythm and cadence
- sentence structure and length
- degree of abstraction vs concrete detail
- evaluative stance (judging, neutral, ironic, elegiac, brutal, etc.)
- what the narrator consistently notices or emphasises
- recurring lexical or stylistic markers
- how the narrator frames violence, time, landscape, human behaviour
- implicit values or worldview embedded in the prose

Do NOT focus on:
- the narrator as a dialogue speaker
- invented psychological interiority
- claims the text does not support

Confidence rules:
- "high": clearly and repeatedly evidenced across multiple passages
- "medium": reasonable inference from consistent stylistic pattern
- "low": suggested by only one or two passages
- "none": no evidence — leave field null or empty

Return ONLY valid JSON, no commentary:
{{
  "surface": {{
    "first_impression": "one-sentence description of the narrator's prose surface"
  }},
  "voice": {{
    "description": "detailed description of the narrator's prose voice, rhythm, and style",
    "sentence_length": "short|medium|long",
    "abstraction_level": "low|medium|high",
    "uses_fragments": true/false/null,
    "repetition": "low|medium|high",
    "metaphor": "low|medium|high",
    "verbosity": "short|long|variable",
    "fragmentation": "low|medium|high"
  }},
  "signature": {{
    "what_they_notice": "what the narrator consistently attends to",
    "behaviors": ["prose habits — recurring structural or rhetorical patterns"],
    "speech_patterns": ["sentence-level stylistic habits"],
    "lexical_markers": ["recurring words, cadences, or phrasings"]
  }},
  "inner_engine": {{
    "core_desire": "what the narrator seems compelled to describe or return to",
    "key_contradiction": "any tension in the narrator's stance or framing"
  }},
  "reference_quotes": ["3-5 short passages that exemplify the narrator's voice"],
  "field_confidence": {{
    "voice.description":        {{"confidence": "high", "note": ""}},
    "signature.what_they_notice": {{"confidence": "high", "note": ""}},
    "voice.abstraction_level":  {{"confidence": "medium", "note": ""}},
    "inner_engine.core_desire": {{"confidence": "medium", "note": ""}}
  }}
}}

Passages:
{passages}"""


def _llm_synthesize_narrator(
    book_name: str,
    sample: list[Passage],
    author_name: str,
    llm_config,
) -> dict:
    import os
    from openai import OpenAI

    api_key = os.environ.get(llm_config.api_key_env, "")
    if not api_key:
        raise RuntimeError(f"LLM API key not set — expected env var: {llm_config.api_key_env}")
    client = OpenAI(api_key=api_key)

    passage_text = "\n\n---\n\n".join(
        f"[{p.passage_id}] {p.text}" for p in sample
    )

    prompt = _NARRATOR_PROMPT.format(
        book=book_name,
        author=author_name,
        passages=passage_text,
    )

    resp = client.chat.completions.create(
        model=llm_config.model,
        max_tokens=3000,
        messages=[
            {"role": "system", "content": "You are a literary analyst. Return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
    )

    raw = (resp.choices[0].message.content or "").strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)

    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return {}


# ── Profile construction ──────────────────────────────────────────────────────

def _build_narrator_profile(
    book_name: str,
    source_file: str,
    raw: dict,
    author_name: str,
    author_dir: Path,
    passage_count: int,
) -> tuple[CharacterProfile, ExtractionSidecar]:
    from augmented_fiction.modules.voice.characterbuilder.schema import ReferenceQuote

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    display_name = f"Narrator — {book_name}"
    ids = existing_ids()
    slug = source_slug("extracted", author_name)
    char_id = make_character_id(slug, display_name, ids)

    surf = raw.get("surface", {})
    v    = raw.get("voice", {})
    sig  = raw.get("signature", {})
    ie   = raw.get("inner_engine", {})

    ref_quotes = []
    for q_text in raw.get("reference_quotes", []):
        if isinstance(q_text, str) and q_text.strip():
            clean = re.sub(r'^\[.*?\]\s*', '', q_text).strip()
            if clean:
                ref_quotes.append(ReferenceQuote(
                    text=clean,
                    source=book_name,
                    is_canonical=True,
                    added_by_user=False,
                    tone="narrative",
                ))

    profile = CharacterProfile(
        character_id=char_id,
        display_name=display_name,
        source_author=author_name,
        source_work=book_name,
        source_mode="extracted",
        created_at=now,
        updated_at=now,
        demographics=Demographics(),
        surface=Surface(first_impression=surf.get("first_impression", "")),
        inner_engine=InnerEngine(
            core_desire=ie.get("core_desire", ""),
            key_contradiction=ie.get("key_contradiction", ""),
        ),
        voice=Voice(
            description=v.get("description", ""),
            sentence_length=_enum(v.get("sentence_length"), ["short", "medium", "long"], "medium"),
            abstraction_level=_enum(v.get("abstraction_level"), ["low", "medium", "high"], "medium"),
            uses_fragments=_bool_or_none(v.get("uses_fragments")),
            repetition=_enum(v.get("repetition"), ["low", "medium", "high"], "low"),
            metaphor=_enum(v.get("metaphor"), ["low", "medium", "high"], "low"),
            verbosity=_enum(v.get("verbosity"), ["short", "long", "variable"], "variable"),
            fragmentation=_enum(v.get("fragmentation"), ["low", "medium", "high"], "low"),
        ),
        behavior=Behavior(),
        signature=Signature(
            what_they_notice=sig.get("what_they_notice", ""),
            behaviors=_str_list(sig.get("behaviors", [])),
            speech_patterns=_str_list(sig.get("speech_patterns", [])),
            lexical_markers=_str_list(sig.get("lexical_markers", [])),
            reference_quotes=ref_quotes,
        ),
        story=Story(role="narrator", scene_function=None),
        provenance=Provenance(registry_path=str(registry_json_path(char_id))),
    )

    raw_conf = raw.get("field_confidence", {})
    field_confidence = {
        k: FieldConfidence(confidence=v.get("confidence", "none"), note=v.get("note", ""))
        for k, v in raw_conf.items()
        if isinstance(v, dict)
    }

    sidecar = ExtractionSidecar(
        character_id=char_id,
        extraction_timestamp=now,
        source_author_dir=str(author_dir),
        model=llm_config.model if hasattr(llm_config, 'model') else "unknown",
        evidence_file=f"narrative passages from {source_file}",
        mention_count=passage_count,
        dialogue_count=0,
        candidate_score=0.0,
        field_confidence=field_confidence,
    )

    return profile, sidecar
