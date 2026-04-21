"""
Dialog delta generation and profile update mapping.

Flow:
  original draft + revised draft + profile(s)
  → LLM infers structured change labels (DeltaResult)
  → deterministic mapper proposes bounded profile updates (list[ProposedUpdate])
  → writer accepts/rejects
  → accepted updates applied to CharacterProfile and saved

Design rules:
- LLM output is constrained to a fixed label vocabulary
- Label → field mapping is deterministic Python code, not LLM-generated
- Updates are bounded (step up/down one level on a categorical scale)
- One revision cannot radically redefine a character
- All cycles are logged to projects/<id>/dialog_revision_log/
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from augmented_fiction.modules.voice.characterbuilder.schema import CharacterProfile


# ── Change label vocabulary ───────────────────────────────────────────────────

DELTA_LABELS: list[str] = [
    "less_explicit_self_analysis",
    "more_explicit_self_analysis",
    "more_fragmented_under_pressure",
    "less_fragmented",
    "more_direct",
    "less_direct",
    "more_evasive",
    "less_evasive",
    "more_guarded",
    "less_guarded",
    "more_repetitive",
    "less_repetitive",
    "more_repetition_under_pressure",
    "less_repetition_under_pressure",
    "more_regional_idiom",
    "less_regional_idiom",
    "more_abstract",
    "less_abstract",
    "more_metaphorical",
    "less_metaphorical",
    "more_verbose",
    "less_verbose",
    "more_compressed",
    "more_blunt",
]


# ── Scale helpers ─────────────────────────────────────────────────────────────

_SCALE_LMH   = ["low", "medium", "high"]
_SCALE_SML   = ["short", "medium", "long"]
_SCALE_VERB  = ["short", "variable", "long"]

_FIELD_SCALES: dict[str, list[str]] = {
    "voice.explicitness":            _SCALE_LMH,
    "voice.fragmentation":           _SCALE_LMH,
    "voice.directness":              _SCALE_LMH,
    "voice.repetition":              _SCALE_LMH,
    "voice.abstraction_level":       _SCALE_LMH,
    "voice.metaphor":                _SCALE_LMH,
    "voice.sentence_length":         _SCALE_SML,
    "voice.verbosity":               _SCALE_VERB,
    "behavior.evasiveness":          _SCALE_LMH,
    "behavior.guardedness":          _SCALE_LMH,
    "behavior.pressure_repetition":  _SCALE_LMH,
    "demographics.regionalism_strength": _SCALE_LMH,
}

_FIELD_DISPLAY: dict[str, str] = {
    "voice.explicitness":            "Explicitness",
    "voice.fragmentation":           "Fragmentation",
    "voice.directness":              "Directness",
    "voice.repetition":              "Repetition",
    "voice.abstraction_level":       "Abstraction level",
    "voice.metaphor":                "Metaphor use",
    "voice.sentence_length":         "Sentence length",
    "voice.verbosity":               "Verbosity",
    "behavior.evasiveness":          "Evasiveness",
    "behavior.guardedness":          "Guardedness",
    "behavior.pressure_repetition":  "Repetition under pressure",
    "demographics.regionalism_strength": "Regionalism strength",
}


def _step(value: str, scale: list[str], direction: str) -> str:
    """Step value up or down one position on scale. Clamps at ends."""
    idx = scale.index(value) if value in scale else 1
    if direction == "up":
        idx = min(idx + 1, len(scale) - 1)
    else:
        idx = max(idx - 1, 0)
    return scale[idx]


# ── Label → field update mapping ──────────────────────────────────────────────

# Each label maps to one or more (field_path, direction) tuples.
_LABEL_MAP: dict[str, list[tuple[str, str]]] = {
    "less_explicit_self_analysis":    [("voice.explicitness", "down")],
    "more_explicit_self_analysis":    [("voice.explicitness", "up")],
    "more_fragmented_under_pressure": [("voice.fragmentation", "up"),
                                       ("behavior.pressure_repetition", "up")],
    "less_fragmented":                [("voice.fragmentation", "down")],
    "more_direct":                    [("voice.directness", "up"),
                                       ("behavior.evasiveness", "down")],
    "less_direct":                    [("voice.directness", "down")],
    "more_evasive":                   [("behavior.evasiveness", "up"),
                                       ("voice.directness", "down")],
    "less_evasive":                   [("behavior.evasiveness", "down")],
    "more_guarded":                   [("behavior.guardedness", "up")],
    "less_guarded":                   [("behavior.guardedness", "down")],
    "more_repetitive":                [("voice.repetition", "up")],
    "less_repetitive":                [("voice.repetition", "down")],
    "more_repetition_under_pressure": [("behavior.pressure_repetition", "up")],
    "less_repetition_under_pressure": [("behavior.pressure_repetition", "down")],
    "more_regional_idiom":            [("demographics.regionalism_strength", "up")],
    "less_regional_idiom":            [("demographics.regionalism_strength", "down")],
    "more_abstract":                  [("voice.abstraction_level", "up")],
    "less_abstract":                  [("voice.abstraction_level", "down")],
    "more_metaphorical":              [("voice.metaphor", "up")],
    "less_metaphorical":              [("voice.metaphor", "down")],
    "more_verbose":                   [("voice.verbosity", "up")],
    "less_verbose":                   [("voice.verbosity", "down")],
    "more_compressed":                [("voice.sentence_length", "down"),
                                       ("voice.fragmentation", "up")],
    "more_blunt":                     [("voice.directness", "up"),
                                       ("voice.explicitness", "up")],
}


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class ChangeLabel:
    label: str
    confidence: float   # 0.0–1.0


@dataclass
class ProposedUpdate:
    field: str          # dot-path: "voice.fragmentation"
    display_name: str   # human-readable label
    update_type: str    # "step_up" | "step_down" | "append"
    current_value: str
    proposed_value: str
    reason: str         # delta label that triggered this
    confidence: float


@dataclass
class CharacterDelta:
    character_id: str
    display_name: str
    change_labels: list[ChangeLabel]
    proposed_updates: list[ProposedUpdate]
    new_lexical_markers: list[str] = field(default_factory=list)
    new_speech_patterns: list[str] = field(default_factory=list)


@dataclass
class DeltaResult:
    log_id: str
    mode: str                              # "internal" | "dialog" | "scene"
    affected_characters: list[CharacterDelta]


# ── Profile field access ──────────────────────────────────────────────────────

def _get_field(profile: CharacterProfile, field_path: str) -> str:
    section, attr = field_path.split(".", 1)
    obj = getattr(profile, section)
    val = getattr(obj, attr, "")
    return val if isinstance(val, str) else ""


def _set_field(profile: CharacterProfile, field_path: str, value: str) -> None:
    section, attr = field_path.split(".", 1)
    obj = getattr(profile, section)
    setattr(obj, attr, value)


# ── Build proposed updates from change labels ─────────────────────────────────

def _build_proposed_updates(
    profile: CharacterProfile,
    change_labels: list[ChangeLabel],
    new_lexical_markers: list[str],
    new_speech_patterns: list[str],
) -> list[ProposedUpdate]:
    """
    Map inferred change labels to bounded, deterministic profile update proposals.
    Deduplicates by field — first label to affect a field wins.
    """
    updates: list[ProposedUpdate] = []
    seen_fields: set[str] = set()

    for cl in sorted(change_labels, key=lambda x: -x.confidence):
        field_directives = _LABEL_MAP.get(cl.label, [])
        for field_path, direction in field_directives:
            if field_path in seen_fields:
                continue
            scale = _FIELD_SCALES.get(field_path)
            if scale is None:
                continue
            current = _get_field(profile, field_path)
            if not current or current not in scale:
                current = scale[1]  # default to middle
            proposed = _step(current, scale, direction)
            if proposed == current:
                continue  # already at limit, skip
            updates.append(ProposedUpdate(
                field=field_path,
                display_name=_FIELD_DISPLAY.get(field_path, field_path),
                update_type=f"step_{direction}",
                current_value=current,
                proposed_value=proposed,
                reason=cl.label,
                confidence=cl.confidence,
            ))
            seen_fields.add(field_path)

    # List enrichments — append new markers/patterns if provided
    for marker in new_lexical_markers:
        marker = marker.strip()
        if marker and marker not in profile.signature.lexical_markers:
            updates.append(ProposedUpdate(
                field="signature.lexical_markers",
                display_name="Lexical markers",
                update_type="append",
                current_value=", ".join(profile.signature.lexical_markers) or "(none)",
                proposed_value=marker,
                reason="more_regional_idiom",
                confidence=0.6,
            ))

    for pattern in new_speech_patterns:
        pattern = pattern.strip()
        if pattern and pattern not in profile.signature.speech_patterns:
            updates.append(ProposedUpdate(
                field="signature.speech_patterns",
                display_name="Speech patterns",
                update_type="append",
                current_value=", ".join(profile.signature.speech_patterns) or "(none)",
                proposed_value=pattern,
                reason="inferred from revision",
                confidence=0.55,
            ))

    return updates


# ── LLM delta generation ──────────────────────────────────────────────────────

_DELTA_SYSTEM = """\
You are a character analysis assistant comparing two versions of a dialog draft.

Your job: identify what changed in the revision and infer what it implies about \
the character's voice and behavior.

You must respond with ONLY valid JSON — no prose, no explanation, no markdown fences.

Output format:
{
  "characters": [
    {
      "character_id": "<id>",
      "changes": [
        {"label": "<label>", "confidence": <0.0-1.0>}
      ],
      "new_lexical_markers": ["<word or phrase>"],
      "new_speech_patterns": ["<structural habit description>"]
    }
  ]
}

Allowed labels (use only from this list):
""" + "\n".join(f"- {l}" for l in DELTA_LABELS) + """

Rules:
- Only include labels where there is clear evidence in the revision.
- Confidence 0.8+ means the pattern is unmistakable. 0.5–0.79 means probable. Below 0.5 means tentative.
- new_lexical_markers: specific words or phrases that appear newly or more strongly in the revision.
- new_speech_patterns: structural habits (e.g. "trails off mid-sentence") newly evident in the revision.
- Both lists may be empty.
- Only include characters whose lines actually changed.
"""


def _parse_delta_response(
    raw: str,
    profiles: list[CharacterProfile],
) -> list[CharacterDelta]:
    """Parse LLM JSON response into CharacterDelta list."""
    try:
        data = json.loads(raw.strip())
    except json.JSONDecodeError:
        # Try to extract JSON if wrapped in prose
        import re
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group())
        except json.JSONDecodeError:
            return []

    profile_map = {p.character_id: p for p in profiles}
    result: list[CharacterDelta] = []

    for char_data in data.get("characters", []):
        cid = char_data.get("character_id", "")
        profile = profile_map.get(cid)
        if profile is None:
            # Try by display name
            profile = next(
                (p for p in profiles if p.display_name == cid), None
            )
            if profile is None:
                continue

        change_labels = [
            ChangeLabel(
                label=c["label"],
                confidence=float(c.get("confidence", 0.5)),
            )
            for c in char_data.get("changes", [])
            if c.get("label") in DELTA_LABELS
        ]

        new_markers  = [s for s in char_data.get("new_lexical_markers", []) if isinstance(s, str)]
        new_patterns = [s for s in char_data.get("new_speech_patterns", []) if isinstance(s, str)]

        proposed = _build_proposed_updates(profile, change_labels, new_markers, new_patterns)

        result.append(CharacterDelta(
            character_id=profile.character_id,
            display_name=profile.display_name,
            change_labels=change_labels,
            proposed_updates=proposed,
            new_lexical_markers=new_markers,
            new_speech_patterns=new_patterns,
        ))

    return result


def generate_delta(
    profiles: list[CharacterProfile],
    original_content: str,
    revised_content: str,
    mode: str,
    setting: str,
    llm_config,
    api_key: str,
) -> DeltaResult:
    """
    Call the LLM to infer a structured delta between original and revised dialog.
    Returns a DeltaResult with change labels and proposed profile updates.
    """
    profile_summaries = "\n\n".join(
        f"CHARACTER: {p.display_name} (id: {p.character_id})\n"
        f"voice: {p.voice.description}\n"
        f"source: {p.source_author or 'original'}"
        for p in profiles
    )

    user = (
        f"Mode: {mode}\n"
        f"Setting: {setting}\n\n"
        f"Character profile(s):\n{profile_summaries}\n\n"
        f"--- ORIGINAL DRAFT ---\n{original_content.strip()}\n\n"
        f"--- REVISED DRAFT ---\n{revised_content.strip()}\n\n"
        "Identify what changed. Attribute changes to the correct character by their speaker label. "
        "Output only valid JSON as specified."
    )

    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=llm_config.model,
        temperature=0.2,   # low temperature for structured analysis
        messages=[
            {"role": "system", "content": _DELTA_SYSTEM},
            {"role": "user", "content": user},
        ],
    )
    raw = response.choices[0].message.content or ""
    log_id = uuid.uuid4().hex[:12]

    affected = _parse_delta_response(raw, profiles)

    return DeltaResult(
        log_id=log_id,
        mode=mode,
        affected_characters=affected,
    )


# ── Apply accepted updates to a profile ──────────────────────────────────────

def apply_updates(
    profile: CharacterProfile,
    accepted_updates: list[dict],
) -> CharacterProfile:
    """
    Apply a list of accepted updates to a profile.
    Each update is {"field": str, "proposed_value": str, "update_type": str}.
    Returns the mutated profile (in-place).
    """
    import copy
    profile = copy.deepcopy(profile)

    for upd in accepted_updates:
        field_path = upd["field"]
        update_type = upd.get("update_type", "step_up")
        value = upd["proposed_value"]

        if update_type == "append":
            section, attr = field_path.split(".", 1)
            obj = getattr(profile, section)
            lst = getattr(obj, attr, [])
            if value not in lst:
                lst.append(value)
                setattr(obj, attr, lst)
        else:
            _set_field(profile, field_path, value)

    profile.updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return profile


# ── Revision log ──────────────────────────────────────────────────────────────

def _log_path(project_path: Path, log_id: str, ts: str) -> Path:
    log_dir = project_path / "dialog_revision_log"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts_slug = ts[:19].replace(":", "-")
    return log_dir / f"{ts_slug}_{log_id}.json"


def write_revision_log(
    project_path: Path,
    log_id: str,
    mode: str,
    setting: str,
    character_ids: list[str],
    original_content: str,
    revised_content: str,
    delta_result: DeltaResult,
    accepted: Optional[bool] = None,
    applied_updates: Optional[list[dict]] = None,
) -> Path:
    """Write or update a revision log entry."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = _log_path(project_path, log_id, ts)

    # If file already exists (update on accept/reject), preserve original ts
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        ts = existing.get("timestamp", ts)

    entry = {
        "log_id": log_id,
        "timestamp": ts,
        "mode": mode,
        "setting": setting,
        "character_ids": character_ids,
        "original_content": original_content,
        "revised_content": revised_content,
        "delta": {
            "affected_characters": [
                {
                    "character_id": cd.character_id,
                    "change_labels": [asdict(cl) for cl in cd.change_labels],
                    "proposed_updates": [asdict(u) for u in cd.proposed_updates],
                    "new_lexical_markers": cd.new_lexical_markers,
                    "new_speech_patterns": cd.new_speech_patterns,
                }
                for cd in delta_result.affected_characters
            ]
        },
        "accepted": accepted,
        "applied_updates": applied_updates or [],
    }

    path.write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
