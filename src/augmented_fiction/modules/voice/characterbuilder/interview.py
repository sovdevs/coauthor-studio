"""
Interactive CLI interview for character profile creation and editing.

Quick Create: 12 questions — sufficient for dialog generation.
Deep Create:  11 additional questions — richer profiles.

Design principles:
- Questions sound like an interview, not schema labels.
- Mandatory fields re-prompt until answered.
- Edit mode shows current values; Enter keeps them.
- LLM-assisted refinement is reserved for a future pass.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

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
    _slugify,
    make_character_id,
    source_slug,
)
from augmented_fiction.modules.voice.characterbuilder.storage import existing_ids


# ── Low-level prompt helpers ──────────────────────────────────────────────────

def _ask(
    prompt: str,
    *,
    required: bool = False,
    hint: str = "",
    current: str = "",
) -> str:
    """
    Prompt user for text input.

    - required=True re-prompts until a non-empty value is given.
    - current shows the existing value in edit mode; Enter preserves it.

    Deliberately uses print() for all content and input() only for the bare
    "  ▶ " prompt — passing multi-line strings to input() corrupts the
    terminal's readline state on macOS (libedit) and breaks the session.
    """
    while True:
        print(f"\n  {prompt}")
        if current:
            preview = current[:80] + ("…" if len(current) > 80 else "")
            print(f"  (current: {preview})")
        if hint:
            print(f"  ({hint})")
        try:
            value = input("  ▶ ").strip()
        except (EOFError, KeyboardInterrupt):
            return current
        if value:
            return value
        if current:
            return current          # Enter = keep existing
        if required:
            print("  (required — please enter a value)")
            continue
        return ""


def _ask_list(
    prompt: str,
    *,
    hint: str = "",
    current: list[str] | None = None,
    max_items: int = 5,
) -> list[str]:
    """Prompt for a list of items one per line; empty line stops."""
    print(f"\n  {prompt}")
    if current:
        print(f"  (current: {'; '.join(current)})")
        print("  Enter new items to replace, or press Enter to keep.")
    if hint:
        print(f"  ({hint})")
    print("  Enter one per line. Empty line to finish.")

    items: list[str] = []
    while len(items) < max_items:
        try:
            val = input("  ▶ ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not val:
            break
        items.append(val)

    if not items and current:
        return current
    return items


def _ask_choice(
    prompt: str,
    options: tuple[str, ...],
    *,
    default: str = "",
) -> str:
    """Prompt for a choice from a fixed set."""
    opts_str = " / ".join(options)
    while True:
        print(f"\n  {prompt}")
        suffix = f"  (default: {default})" if default else ""
        print(f"  [{opts_str}]{suffix}")
        try:
            val = input("  ▶ ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return default
        if not val:
            return default
        if val in options:
            return val
        print(f"  Choose from: {opts_str}")


def _confirm(prompt: str, *, default: bool = True) -> bool:
    yn = "Y/n" if default else "y/N"
    print(f"\n  {prompt} [{yn}]")
    try:
        val = input("  ▶ ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return default
    if not val:
        return default
    return val in ("y", "yes")


# ── Quick Create (12 questions) ───────────────────────────────────────────────

def _run_quick(defaults: dict | None = None) -> dict:
    """
    Run the Quick Create interview.
    defaults: pre-filled values for edit mode (all optional).
    Returns a raw data dict used by _assemble_profile().
    """
    d = defaults or {}
    ie = d.get("inner_engine", {})
    v = d.get("voice", {})
    beh = d.get("behavior", {})
    sig = d.get("signature", {})
    demo = d.get("demographics", {})

    print("\n  ── Quick Create ─────────────────────────────────────────────")
    print("  12 questions — sufficient for dialog generation.\n")

    # Q1 — name
    display_name = _ask(
        "What is this character's name?",
        required=True,
        current=d.get("display_name", ""),
    )

    # Q2–Q3 — source
    print("\n  ── Source ──────────────────────────────────────────────────")
    source_author = _ask(
        "Who created this character — a real author, or you?",
        hint="Leave blank for fully original characters.",
        current=d.get("source_author") or "",
    ) or None
    source_work = _ask(
        "Which novel, story, or work do they come from?",
        hint="Leave blank if not applicable.",
        current=d.get("source_work") or "",
    ) or None

    if not source_author:
        source_mode = "manual"
    else:
        source_mode = _ask_choice(
            "How was this profile created?",
            ("manual", "imported", "extracted", "generated"),
            default=d.get("source_mode", "manual"),
        )

    # Q4–Q8 — demographics
    print("\n  ── Demographics ────────────────────────────────────────────")
    age = _ask(
        "Age or generation?",
        hint="e.g. 'mid-40s'  'late teens'  'elderly'  'indeterminate'",
        current=demo.get("age", ""),
    )
    gender = _ask(
        "Sex / gender?",
        hint="free text — e.g. 'male'  'woman'  'nonbinary'",
        current=demo.get("gender", ""),
    )
    regionalism = _ask(
        "Regional accent or dialect?",
        hint="e.g. 'Texas drawl'  'London working class'  'none notable'",
        current=demo.get("regionalism", ""),
    )
    class_register = _ask(
        "Class / education register?",
        hint="e.g. 'working class'  'old money'  'self-educated'  'military'",
        current=demo.get("class_register", ""),
    )
    physical_condition = _ask(
        "Notable physical condition?",
        hint="Leave blank if none — e.g. 'chronic back pain'  'hard of hearing'",
        current=demo.get("physical_condition") or "",
    ) or None

    # Q9 — first impression
    print("\n  ── Surface ─────────────────────────────────────────────────")
    first_impression = _ask(
        "How do strangers first read this person?\n"
        "  What surface do they present to the world?",
        required=True,
        current=d.get("surface", {}).get("first_impression", ""),
    )

    # Q10 — core desire
    print("\n  ── Inner engine ────────────────────────────────────────────")
    core_desire = _ask(
        "What do they try to get from people, in rooms, in conversation?",
        required=True,
        current=ie.get("core_desire", ""),
    )

    # Q11 — core fear + avoidance
    core_fear = _ask(
        "What would undo them? What are they most afraid of?",
        required=True,
        current=ie.get("core_fear", ""),
    )
    avoidance = _ask(
        "What situation do they avoid at all costs?",
        current=ie.get("avoidance", ""),
    )

    # Q12 — what they hide
    what_they_hide = _ask(
        "What do they conceal from others — or from themselves?",
        current=ie.get("what_they_hide", ""),
    )

    # Q13 — contradiction
    key_contradiction = _ask(
        "What is the most important thing that doesn't add up about them?",
        required=True,
        current=ie.get("key_contradiction", ""),
    )
    contradiction_behavior = _ask(
        "What do they say they are vs what they actually do?",
        current=ie.get("contradiction_behavior", ""),
    )

    # Q14 — voice
    print("\n  ── Voice ───────────────────────────────────────────────────")
    voice_description = _ask(
        "Describe their speech in plain terms.\n"
        "  Long sentences or short? Do they ask or assert?\n"
        "  Plain language or abstractions? Silences, tics, fragments?",
        required=True,
        current=v.get("description", ""),
    )
    conversation_control = _ask_choice(
        "Do they try to control the conversation, or respond to it?",
        ("controls", "responds", "mixed"),
        default=v.get("conversation_control", "mixed"),
    )

    # Q15 — conflict response
    print("\n  ── Behavior ────────────────────────────────────────────────")
    conflict_response = _ask(
        "When cornered or challenged, what do they actually do?\n"
        "  Describe the behavior, not just the category.",
        current=beh.get("conflict_response", ""),
    )

    # Q16 — signature behaviors
    print("\n  ── Signature ───────────────────────────────────────────────")
    signature_behaviors = _ask_list(
        "Name 2–3 things this character reliably does.",
        hint="gestures, habits, verbal tics, behavioral tells",
        current=sig.get("behaviors"),
        max_items=5,
    )

    # Q17 — what they notice
    what_they_notice = _ask(
        "What does this person tend to notice first in a room or conversation?",
        current=sig.get("what_they_notice", ""),
    )

    return {
        "display_name": display_name,
        "source_author": source_author,
        "source_work": source_work,
        "source_mode": source_mode,
        "demographics": {
            "age": age,
            "gender": gender,
            "regionalism": regionalism,
            "physical_condition": physical_condition,
            "class_register": class_register,
        },
        "surface": {"first_impression": first_impression},
        "inner_engine": {
            "core_desire": core_desire,
            "core_fear": core_fear,
            "avoidance": avoidance,
            "what_they_hide": what_they_hide,
            "key_contradiction": key_contradiction,
            "contradiction_behavior": contradiction_behavior,
        },
        "voice": {
            "description": voice_description,
            "conversation_control": conversation_control,
            "sentence_length": v.get("sentence_length", "medium"),
            "question_frequency": v.get("question_frequency", "low"),
            "abstraction_level": v.get("abstraction_level", "medium"),
            "uses_fragments": v.get("uses_fragments"),
            "repetition": v.get("repetition", "low"),
            "metaphor": v.get("metaphor", "low"),
            "verbosity": v.get("verbosity", "variable"),
        },
        "behavior": {
            "conflict_response": conflict_response,
            "avoidance_pattern": beh.get("avoidance_pattern", ""),
            "dialogue_stance": beh.get("dialogue_stance", "mixed"),
            "dialogue_moves": beh.get("dialogue_moves", []),
        },
        "signature": {
            "what_they_notice": what_they_notice,
            "behaviors": signature_behaviors,
            "anti_patterns": sig.get("anti_patterns", []),
            "example_lines": sig.get("example_lines", []),
        },
        "story": d.get("story", {}),
    }


# ── Deep Create (11 additional questions) ────────────────────────────────────

def _run_deep(data: dict) -> dict:
    """Extend a quick-create data dict with deep interview answers."""
    ie = data.setdefault("inner_engine", {})
    beh = data.setdefault("behavior", {})
    sig = data.setdefault("signature", {})
    st = data.setdefault("story", {})

    print("\n  ── Deep Create ──────────────────────────────────────────────")
    print("  11 additional questions for richer profiles.\n")

    # Q13 — shame
    ie["shame"] = _ask(
        "What is this character ashamed of?\n  Is it visible or buried?",
        current=ie.get("shame") or "",
    ) or None

    # Q14 — false belief
    ie["false_belief"] = _ask(
        "What does this person believe about themselves or the world\n"
        "  that is probably wrong?",
        current=ie.get("false_belief") or "",
    ) or None

    # Q15 — status with people they need
    beh["status_with_needed"] = _ask(
        "How do they behave with people they need?",
        current=beh.get("status_with_needed") or "",
    ) or None

    # Q16 — status with people they don't need
    beh["status_with_unneeded"] = _ask(
        "How do they behave with people they don't need?",
        current=beh.get("status_with_unneeded") or "",
    ) or None

    # Q17 — intimacy
    beh["intimacy_style"] = _ask(
        "When someone gets close, what happens?\n"
        "  Do they lean in or pull back — and how?",
        current=beh.get("intimacy_style") or "",
    ) or None

    # Q18 — sustained pressure
    beh["pressure_response"] = _ask(
        "Under prolonged stress — not a single confrontation —\n"
        "  how do they cope? What eventually breaks them?",
        current=beh.get("pressure_response") or "",
    ) or None

    # Q19 — sensory bias
    sig["sensory_bias"] = _ask(
        "What details do they notice that others miss?\n"
        "  Are they oriented by sound, sight, touch, smell?",
        current=sig.get("sensory_bias") or "",
    ) or None

    # Q20 — taboo
    ie["taboo"] = _ask(
        "Is there something they will not do, say, or hear?\n"
        "  A line they won't cross, a subject they refuse?",
        current=ie.get("taboo") or "",
    ) or None

    # Q21 — story role + scene function
    st["role"] = _ask(
        "What role do they tend to play?\n"
        "  (antagonist / catalyst / observer / mentor / disruptor / other)",
        current=st.get("role") or "",
    ) or None
    st["scene_function"] = _ask(
        "What function do they serve in a scene?",
        current=st.get("scene_function") or "",
    ) or None

    # Q22 — relational tendencies
    sig["relational_tendencies"] = _ask(
        "How do they relate to: authority? strangers? people they love? rivals?",
        current=sig.get("relational_tendencies") or "",
    ) or None

    # Q23 — anti-patterns
    sig["anti_patterns"] = _ask_list(
        "What would be completely out of character for them?",
        hint="things they never do",
        current=sig.get("anti_patterns"),
        max_items=5,
    )

    # Q24 — example lines
    sig["example_lines"] = _ask_list(
        "Give 2–3 lines of dialogue that sound like this character.",
        hint="These should sound natural, not exaggerated or theatrical.",
        current=sig.get("example_lines"),
        max_items=5,
    )

    data["story"] = st
    return data


# ── Profile assembly ──────────────────────────────────────────────────────────

def _assemble_profile(data: dict, existing_character_id: str | None = None) -> CharacterProfile:
    """Build a CharacterProfile from interview data dict."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    slug = source_slug(data["source_mode"], data.get("source_author"))
    ids = existing_ids()
    if existing_character_id:
        ids.discard(existing_character_id)  # don't collide with self on edit
    character_id = existing_character_id or make_character_id(slug, data["display_name"], ids)

    registry_rel = f"modules/voice/characterbuilder/characters/{character_id}.json"

    ie = data.get("inner_engine", {})
    v = data.get("voice", {})
    beh = data.get("behavior", {})
    sig = data.get("signature", {})
    st = data.get("story", {})
    demo = data.get("demographics", {})

    return CharacterProfile(
        character_id=character_id,
        display_name=data["display_name"],
        source_author=data.get("source_author"),
        source_work=data.get("source_work"),
        source_mode=data["source_mode"],
        created_at=now,
        updated_at=now,
        demographics=Demographics(
            age=demo.get("age", ""),
            gender=demo.get("gender", ""),
            regionalism=demo.get("regionalism", ""),
            physical_condition=demo.get("physical_condition"),
            class_register=demo.get("class_register", ""),
        ),
        surface=Surface(first_impression=data.get("surface", {}).get("first_impression", "")),
        inner_engine=InnerEngine(
            core_desire=ie.get("core_desire", ""),
            core_fear=ie.get("core_fear", ""),
            avoidance=ie.get("avoidance", ""),
            what_they_hide=ie.get("what_they_hide", ""),
            key_contradiction=ie.get("key_contradiction", ""),
            contradiction_behavior=ie.get("contradiction_behavior", ""),
            shame=ie.get("shame"),
            false_belief=ie.get("false_belief"),
            taboo=ie.get("taboo"),
        ),
        voice=Voice(
            description=v.get("description", ""),
            sentence_length=v.get("sentence_length", "medium"),
            question_frequency=v.get("question_frequency", "low"),
            abstraction_level=v.get("abstraction_level", "medium"),
            uses_fragments=v.get("uses_fragments"),
            repetition=v.get("repetition", "low"),
            metaphor=v.get("metaphor", "low"),
            conversation_control=v.get("conversation_control", "mixed"),
            verbosity=v.get("verbosity", "variable"),
        ),
        behavior=Behavior(
            conflict_response=beh.get("conflict_response", ""),
            avoidance_pattern=beh.get("avoidance_pattern", ""),
            dialogue_stance=beh.get("dialogue_stance", "mixed"),
            dialogue_moves=beh.get("dialogue_moves", []),
            status_with_needed=beh.get("status_with_needed"),
            status_with_unneeded=beh.get("status_with_unneeded"),
            intimacy_style=beh.get("intimacy_style"),
            pressure_response=beh.get("pressure_response"),
        ),
        signature=Signature(
            what_they_notice=sig.get("what_they_notice", ""),
            behaviors=sig.get("behaviors", []),
            sensory_bias=sig.get("sensory_bias"),
            relational_tendencies=sig.get("relational_tendencies"),
            anti_patterns=sig.get("anti_patterns", []),
            example_lines=sig.get("example_lines", []),
        ),
        story=Story(
            role=st.get("role"),
            scene_function=st.get("scene_function"),
        ),
        style_trace=StyleTrace(),
        provenance=Provenance(registry_path=registry_rel),
    )


# ── Voice material (optional lightweight step) ────────────────────────────────

def _run_voice_material(data: dict) -> dict:
    """
    Optional post-interview step for voice enrichment.
    Kept minimal — the web Character Studio is the primary place for rich quote management.
    """
    sig = data.setdefault("signature", {})

    print("\n  ── Voice material ──────────────────────────────────────────")
    print("  (These can also be added later via :cb edit or the web studio.)\n")

    # Speech patterns
    patterns = _ask_list(
        "Speech patterns — structural habits of how they talk.",
        hint="e.g. 'answers questions with questions'  'trails off instead of concluding'",
        current=sig.get("speech_patterns"),
        max_items=5,
    )
    if patterns:
        sig["speech_patterns"] = patterns

    # Lexical markers
    markers = _ask_list(
        "Lexical markers — recurring words, phrases, or verbal habits.",
        hint="e.g. 'you know'  'my dear'  legal phrasing  religious cadence",
        current=sig.get("lexical_markers"),
        max_items=5,
    )
    if markers:
        sig["lexical_markers"] = markers

    # One reference quote
    print("\n  Add a reference quote — an actual line this character says or would say.")
    print("  (Leave blank to skip. More quotes can be added in the web studio.)")
    quote_text = _ask("Quote text:")
    if quote_text:
        quote_source = _ask("Source (leave blank if unknown):")
        is_canon = _confirm("Is this a verified canonical quote?", default=False)
        sig.setdefault("reference_quotes", []).append({
            "text": quote_text,
            "source": quote_source,
            "is_canonical": is_canon,
            "added_by_user": True,
            "tone": "",
            "notes": "",
        })

    return data


# ── Review summary ────────────────────────────────────────────────────────────

def _print_review(data: dict) -> None:
    slug = source_slug(data["source_mode"], data.get("source_author"))
    proposed_id = make_character_id(slug, data["display_name"], existing_ids())
    ie = data.get("inner_engine", {})
    demo = data.get("demographics", {})

    print("\n  ── Review ──────────────────────────────────────────────────")
    print(f"  Name:          {data['display_name']}")
    print(f"  ID:            {proposed_id}")
    print(f"  Mode:          {data['source_mode']}")
    if data.get("source_author"):
        print(f"  Author:        {data['source_author']}")
    if data.get("source_work"):
        print(f"  Work:          {data['source_work']}")
    if demo.get("age"):
        print(f"  Age:           {demo['age']}")
    if demo.get("gender"):
        print(f"  Gender:        {demo['gender']}")
    if demo.get("regionalism"):
        print(f"  Regionalism:   {demo['regionalism']}")
    if demo.get("class_register"):
        print(f"  Register:      {demo['class_register']}")
    print(f"  Core desire:   {ie.get('core_desire', '(none)')}")
    print(f"  Core fear:     {ie.get('core_fear', '(none)')}")
    print(f"  Contradiction: {ie.get('key_contradiction', '(none)')}")
    print(f"  Voice:         {data.get('voice', {}).get('description', '(none)')}")


# ── Public entry points ───────────────────────────────────────────────────────

def run_create_interview() -> Optional[CharacterProfile]:
    """
    Run the full interactive interview for a new character.
    Returns the assembled CharacterProfile, or None if the user aborts.
    """
    data = _run_quick()

    if _confirm("Run deep interview? (11 more questions for richer profiles)", default=False):
        data = _run_deep(data)

    if _confirm("Add voice material now? (speech patterns, quotes — can also be added later)", default=False):
        data = _run_voice_material(data)

    _print_review(data)

    if not _confirm("\n  Save this character?", default=True):
        print("  Aborted — nothing saved.")
        return None

    return _assemble_profile(data)


def run_edit_interview(profile: CharacterProfile) -> Optional[CharacterProfile]:
    """
    Re-run interview pre-filled with existing profile values.
    Press Enter to keep any existing value.
    Returns updated CharacterProfile, or None if user aborts.
    """
    import dataclasses
    from augmented_fiction.modules.voice.characterbuilder.schema import profile_to_dict
    existing_data = profile_to_dict(profile)

    print(f"\n  Editing: {profile.display_name}  ({profile.character_id})")
    print("  Press Enter at any prompt to keep the existing value.\n")

    data = _run_quick(defaults=existing_data)

    if _confirm("Run deep interview?", default=False):
        # Merge current deep values as defaults
        for key in ("shame", "false_belief", "taboo"):
            data["inner_engine"].setdefault(key, existing_data.get("inner_engine", {}).get(key))
        for key in ("status_with_needed", "status_with_unneeded", "intimacy_style", "pressure_response"):
            data["behavior"].setdefault(key, existing_data.get("behavior", {}).get(key))
        for key in ("sensory_bias", "relational_tendencies", "anti_patterns", "example_lines"):
            data["signature"].setdefault(key, existing_data.get("signature", {}).get(key))
        data.setdefault("story", existing_data.get("story", {}))
        data.setdefault("demographics", existing_data.get("demographics", {}))
        data = _run_deep(data)

    _print_review(data)

    if not _confirm("\n  Save changes?", default=True):
        print("  Aborted — no changes saved.")
        return None

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assembled = _assemble_profile(data, existing_character_id=profile.character_id)
    assembled.created_at = profile.created_at  # preserve original creation date
    assembled.updated_at = now
    assembled.provenance = profile.provenance
    return assembled
