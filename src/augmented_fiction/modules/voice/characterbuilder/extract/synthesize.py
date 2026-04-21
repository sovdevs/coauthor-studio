"""
Synthesize a draft CharacterProfile from a raw evidence dossier.

Two outputs per character:
1. CharacterProfile  — canonical runtime profile (saved to character registry)
2. ExtractionSidecar — extraction provenance + per-field confidence (saved as sidecar JSON)

The synthesis prompt maps evidence → all character questionnaire fields,
marks low-confidence fields, and preserves voice evidence for reference quotes.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from augmented_fiction.modules.voice.characterbuilder.schema import (
    AuthorialMaterial,
    Behavior,
    CharacterProfile,
    Demographics,
    InnerEngine,
    Provenance,
    ReferenceQuote,
    Signature,
    Story,
    StyleTrace,
    Surface,
    Voice,
    _slugify,
    make_character_id,
    source_slug,
)
from augmented_fiction.modules.voice.characterbuilder.storage import (
    _REGISTRY_ROOT,
    existing_ids,
    registry_json_path,
)
from .candidate import CandidateCharacter


# ── Sidecar schema ────────────────────────────────────────────────────────────

@dataclass
class FieldConfidence:
    confidence: str   # "high" | "medium" | "low" | "none"
    note: str


@dataclass
class ExtractionSidecar:
    character_id: str
    extraction_timestamp: str
    source_author_dir: str
    model: str
    evidence_file: str
    mention_count: int = 0
    dialogue_count: int = 0
    candidate_score: float = 0.0
    field_confidence: dict[str, FieldConfidence] = field(default_factory=dict)


# ── Public API ────────────────────────────────────────────────────────────────

def synthesize_profile(
    character: CandidateCharacter,
    evidence_path: Path,
    author_dir: Path,
    author_name: str,
    llm_config,
    source_work: str = "",
) -> tuple[CharacterProfile, ExtractionSidecar]:
    """
    Synthesize a draft CharacterProfile from a character evidence file.
    Returns (profile, sidecar).
    """
    evidence_text = evidence_path.read_text(encoding="utf-8")
    raw = _llm_synthesize(character.name, evidence_text, author_name, llm_config)
    profile = _build_profile(character, raw, author_name, source_work)
    sidecar = _build_sidecar(character, raw, profile.character_id, evidence_path, author_dir)
    return profile, sidecar


def save_sidecar(sidecar: ExtractionSidecar) -> Path:
    """Write the extraction sidecar JSON alongside the character profile."""
    path = _REGISTRY_ROOT / f"{sidecar.character_id}_extraction.json"
    data = {
        "character_id": sidecar.character_id,
        "extraction_timestamp": sidecar.extraction_timestamp,
        "source_author_dir": sidecar.source_author_dir,
        "model": sidecar.model,
        "evidence_file": sidecar.evidence_file,
        "mention_count": sidecar.mention_count,
        "dialogue_count": sidecar.dialogue_count,
        "candidate_score": sidecar.candidate_score,
        "field_confidence": {
            k: {"confidence": v.confidence, "note": v.note}
            for k, v in sidecar.field_confidence.items()
        },
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return path


# ── LLM synthesis ─────────────────────────────────────────────────────────────

_SYNTHESIS_PROMPT = """\
You are synthesizing a draft character profile for "{name}" from fiction by {author}.

You have a raw evidence dossier below. Your job is to answer the character questionnaire \
using the evidence.

General rules:
- Base every claim on the evidence. Prefer directly observed over inferred.
- For voice fields, preserve original linguistic patterns from the speech evidence.
- For reference_quotes, use actual lines from the Spoken Dialogue section — \
  strip the [ref] prefix so only the spoken line remains.
- Leave a field as empty string "" or null if the evidence does not clearly support it.
- Do not invent psychological depth the evidence cannot sustain.

Weak-inference fields — apply extra caution to these:
  inner_engine.false_belief, inner_engine.shame, inner_engine.taboo, behavior.pressure_response

For weak-inference fields:
- Only populate if 2 or more distinct passages directly and clearly support the claim.
- If evidence is thin, indirect, or requires significant interpretation: store null.
- Do not fill these just because the schema has the slot.
- A behavioral pattern alone is not sufficient — prefer explicit narrative or speech evidence.

Confidence calibration — be strict:
- "high": multiple strong passages explicitly and directly support the field value.
- "medium": reasonable inference from a clear behavioral pattern; not explicitly stated.
- "low": speculative, indirect, or suggested by only one weak passage.
- "none": no usable evidence — field should be null or empty.
Bias confidence downward for false_belief, shame, taboo, pressure_response, and \
key_contradiction if the evidence is abstract or thin.

field_confidence: include entries for the eight most important fields.

Return ONLY valid JSON with this exact structure — no commentary, no markdown fence:
{{
  "demographics": {{
    "age": "",
    "gender": "",
    "regionalism": "",
    "class_register": "",
    "physical_condition": null,
    "regionalism_strength": "low"
  }},
  "surface": {{
    "first_impression": ""
  }},
  "inner_engine": {{
    "core_desire": "",
    "core_fear": "",
    "avoidance": "",
    "what_they_hide": "",
    "key_contradiction": "",
    "contradiction_behavior": "",
    "shame": null,
    "false_belief": null,
    "taboo": null
  }},
  "voice": {{
    "description": "",
    "sentence_length": "medium",
    "question_frequency": "low",
    "abstraction_level": "medium",
    "uses_fragments": null,
    "repetition": "low",
    "metaphor": "low",
    "conversation_control": "mixed",
    "verbosity": "variable",
    "explicitness": "medium",
    "fragmentation": "low",
    "directness": "medium"
  }},
  "behavior": {{
    "conflict_response": "",
    "avoidance_pattern": "",
    "dialogue_stance": "mixed",
    "dialogue_moves": [],
    "status_with_needed": null,
    "status_with_unneeded": null,
    "intimacy_style": null,
    "pressure_response": null,
    "evasiveness": "low",
    "guardedness": "low",
    "pressure_repetition": "low"
  }},
  "signature": {{
    "what_they_notice": "",
    "behaviors": [],
    "sensory_bias": null,
    "relational_tendencies": null,
    "anti_patterns": [],
    "speech_patterns": [],
    "lexical_markers": []
  }},
  "story": {{
    "role": null,
    "scene_function": null
  }},
  "reference_quotes": [],
  "field_confidence": {{
    "inner_engine.core_desire":    {{"confidence": "high", "note": ""}},
    "inner_engine.core_fear":      {{"confidence": "high", "note": ""}},
    "inner_engine.key_contradiction": {{"confidence": "medium", "note": ""}},
    "inner_engine.shame":          {{"confidence": "low",  "note": ""}},
    "voice.description":           {{"confidence": "high", "note": ""}},
    "behavior.conflict_response":  {{"confidence": "medium", "note": ""}},
    "behavior.pressure_response":  {{"confidence": "low",  "note": ""}},
    "demographics.regionalism":    {{"confidence": "medium", "note": ""}}
  }}
}}

Evidence dossier:
{evidence}"""


def _llm_synthesize(name: str, evidence_text: str, author_name: str, llm_config) -> dict:
    import os
    from openai import OpenAI

    api_key = os.environ.get(llm_config.api_key_env, "")
    if not api_key:
        raise RuntimeError(f"LLM API key not set — expected env var: {llm_config.api_key_env}")
    client = OpenAI(api_key=api_key)

    prompt = _SYNTHESIS_PROMPT.format(
        name=name,
        author=author_name,
        evidence=evidence_text,
    )

    resp = client.chat.completions.create(
        model=llm_config.model,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": "You are a literary analyst. Return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
    )

    raw = (resp.choices[0].message.content or "").strip()
    # Strip markdown fence if present
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

def _build_profile(
    character: CandidateCharacter,
    raw: dict,
    author_name: str,
    source_work: str,
) -> CharacterProfile:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids = existing_ids()
    slug = source_slug("extracted", author_name)
    char_id = make_character_id(slug, character.name, ids)

    demo = raw.get("demographics", {})
    surf = raw.get("surface", {})
    ie   = raw.get("inner_engine", {})
    v    = raw.get("voice", {})
    b    = raw.get("behavior", {})
    sig  = raw.get("signature", {})
    st   = raw.get("story", {})

    # Reference quotes: strip [source_ref] prefixes from evidence lines
    ref_quotes: list[ReferenceQuote] = []
    for q_text in raw.get("reference_quotes", []):
        if not isinstance(q_text, str):
            continue
        clean = re.sub(r'^\[.*?\]\s*', '', q_text).strip()
        if clean:
            ref_quotes.append(ReferenceQuote(
                text=clean,
                source=source_work or author_name,
                is_canonical=True,
                added_by_user=False,
            ))

    profile = CharacterProfile(
        character_id=char_id,
        display_name=character.name,
        source_author=author_name,
        source_work=source_work or None,
        source_mode="extracted",
        created_at=now,
        updated_at=now,
        demographics=Demographics(
            age=demo.get("age", ""),
            gender=demo.get("gender", ""),
            regionalism=demo.get("regionalism", ""),
            physical_condition=demo.get("physical_condition") or None,
            class_register=demo.get("class_register", ""),
            regionalism_strength=_enum(demo.get("regionalism_strength"), ["low", "medium", "high"], "low"),
        ),
        surface=Surface(
            first_impression=surf.get("first_impression", ""),
        ),
        inner_engine=InnerEngine(
            core_desire=ie.get("core_desire", ""),
            core_fear=ie.get("core_fear", ""),
            avoidance=ie.get("avoidance", ""),
            what_they_hide=ie.get("what_they_hide", ""),
            key_contradiction=ie.get("key_contradiction", ""),
            contradiction_behavior=ie.get("contradiction_behavior", ""),
            shame=ie.get("shame") or None,
            false_belief=ie.get("false_belief") or None,
            taboo=ie.get("taboo") or None,
        ),
        voice=Voice(
            description=v.get("description", ""),
            sentence_length=_enum(v.get("sentence_length"), ["short", "medium", "long"], "medium"),
            question_frequency=_enum(v.get("question_frequency"), ["low", "medium", "high"], "low"),
            abstraction_level=_enum(v.get("abstraction_level"), ["low", "medium", "high"], "medium"),
            uses_fragments=_bool_or_none(v.get("uses_fragments")),
            repetition=_enum(v.get("repetition"), ["low", "medium", "high"], "low"),
            metaphor=_enum(v.get("metaphor"), ["low", "medium", "high"], "low"),
            conversation_control=_enum(v.get("conversation_control"), ["controls", "responds", "mixed"], "mixed"),
            verbosity=_enum(v.get("verbosity"), ["short", "long", "variable"], "variable"),
            explicitness=_enum(v.get("explicitness"), ["low", "medium", "high"], "medium"),
            fragmentation=_enum(v.get("fragmentation"), ["low", "medium", "high"], "low"),
            directness=_enum(v.get("directness"), ["low", "medium", "high"], "medium"),
        ),
        behavior=Behavior(
            conflict_response=b.get("conflict_response", ""),
            avoidance_pattern=b.get("avoidance_pattern", ""),
            dialogue_stance=_enum(b.get("dialogue_stance"), ["initiates", "reacts", "mixed"], "mixed"),
            dialogue_moves=_list_enum(
                b.get("dialogue_moves", []),
                ["push", "resist", "deflect", "concede", "assert"],
            ),
            status_with_needed=b.get("status_with_needed") or None,
            status_with_unneeded=b.get("status_with_unneeded") or None,
            intimacy_style=b.get("intimacy_style") or None,
            pressure_response=b.get("pressure_response") or None,
            evasiveness=_enum(b.get("evasiveness"), ["low", "medium", "high"], "low"),
            guardedness=_enum(b.get("guardedness"), ["low", "medium", "high"], "low"),
            pressure_repetition=_enum(b.get("pressure_repetition"), ["low", "medium", "high"], "low"),
        ),
        signature=Signature(
            what_they_notice=sig.get("what_they_notice", ""),
            behaviors=_str_list(sig.get("behaviors", [])),
            sensory_bias=sig.get("sensory_bias") or None,
            relational_tendencies=sig.get("relational_tendencies") or None,
            anti_patterns=_str_list(sig.get("anti_patterns", [])),
            speech_patterns=_str_list(sig.get("speech_patterns", [])),
            lexical_markers=_str_list(sig.get("lexical_markers", [])),
            reference_quotes=ref_quotes,
        ),
        story=Story(
            role=st.get("role") or None,
            scene_function=st.get("scene_function") or None,
        ),
        provenance=Provenance(
            registry_path=str(registry_json_path(char_id)),
        ),
    )
    return profile


def _build_sidecar(
    character: CandidateCharacter,
    raw: dict,
    character_id: str,
    evidence_path: Path,
    author_dir: Path,
) -> ExtractionSidecar:
    raw_conf = raw.get("field_confidence", {})
    field_confidence: dict[str, FieldConfidence] = {}
    for k, v in raw_conf.items():
        if isinstance(v, dict):
            field_confidence[k] = FieldConfidence(
                confidence=v.get("confidence", "none"),
                note=v.get("note", ""),
            )

    return ExtractionSidecar(
        character_id=character_id,
        extraction_timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        source_author_dir=str(author_dir),
        model="claude-sonnet-4-6",
        evidence_file=str(evidence_path),
        mention_count=character.mention_count,
        dialogue_count=character.dialogue_count,
        candidate_score=character.rank_score,
        field_confidence=field_confidence,
    )


# ── Validation helpers ────────────────────────────────────────────────────────

def _enum(value: object, allowed: list[str], default: str) -> str:
    if isinstance(value, str) and value in allowed:
        return value
    return default


def _bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.lower() in ("true", "yes"):
            return True
        if value.lower() in ("false", "no"):
            return False
    return None


def _str_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(x) for x in value if x]
    return []


def _list_enum(value: object, allowed: list[str]) -> list[str]:
    if isinstance(value, list):
        return [x for x in value if isinstance(x, str) and x in allowed]
    return []
