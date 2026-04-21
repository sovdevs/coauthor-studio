"""
Character profile schema for the characterbuilder module.

Profiles are stored as structured JSON (source of truth) and can be
rendered as Markdown dossiers for human reading.

Each profile has a deterministic character_id:
  <source_slug>__<name_slug>
  e.g. mccarthy__judge, manual__martin_vale, generated__unnamed_detective

Characters are constraint systems on language, not biographical summaries.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ── Voice material ────────────────────────────────────────────────────────────

@dataclass
class ReferenceQuote:
    """
    An actual quote or representative line associated with the character.
    Used as a voice anchor during dialog generation.
    """
    text: str
    source: str = ""
    is_canonical: bool = False      # verified source vs user-added
    added_by_user: bool = True
    tone: str = ""
    notes: str = ""


@dataclass
class AuthorialMaterial:
    """
    Lines, ideas, quotations or thematic statements the writer wants available
    as candidate mouth-material for this character. Not guaranteed insertion —
    treated as available material for draft generation.
    """
    text: str
    source_type: str = "other"          # quote | theme | argument | paraphrase | author_note | other
    source: str = ""
    notes: str = ""
    direct_use_allowed: bool = False    # verbatim reuse allowed
    paraphrase_preferred: bool = True   # prefer generating new voice-consistent lines


# ── Sub-sections ──────────────────────────────────────────────────────────────

@dataclass
class Surface:
    first_impression: str = ""


@dataclass
class InnerEngine:
    core_desire: str = ""
    core_fear: str = ""
    avoidance: str = ""
    what_they_hide: str = ""
    key_contradiction: str = ""
    contradiction_behavior: str = ""
    shame: Optional[str] = None
    false_belief: Optional[str] = None
    taboo: Optional[str] = None


@dataclass
class Voice:
    description: str = ""
    sentence_length: str = "medium"      # short | medium | long
    question_frequency: str = "low"       # low | medium | high
    abstraction_level: str = "medium"     # low | medium | high
    uses_fragments: Optional[bool] = None
    repetition: str = "low"              # low | medium | high
    metaphor: str = "low"               # low | medium | high
    conversation_control: str = "mixed"  # controls | responds | mixed
    verbosity: str = "variable"          # short | long | variable
    # delta-targetable dimensions (updated via dialog revision loop)
    explicitness: str = "medium"         # how directly they state thoughts/feelings: low|medium|high
    fragmentation: str = "low"           # how broken/incomplete speech becomes: low|medium|high
    directness: str = "medium"           # how directly they answer/ask/confront: low|medium|high


@dataclass
class Behavior:
    conflict_response: str = ""
    avoidance_pattern: str = ""
    dialogue_stance: str = "mixed"       # initiates | reacts | mixed
    dialogue_moves: list[str] = field(default_factory=list)  # push|resist|deflect|concede|assert
    status_with_needed: Optional[str] = None
    status_with_unneeded: Optional[str] = None
    intimacy_style: Optional[str] = None
    pressure_response: Optional[str] = None
    # delta-targetable dimensions (updated via dialog revision loop)
    evasiveness: str = "low"             # tendency to dodge/deflect/redirect: low|medium|high
    guardedness: str = "low"             # tendency to conceal/not reveal: low|medium|high
    pressure_repetition: str = "low"     # repetition tendency under pressure: low|medium|high


@dataclass
class Signature:
    what_they_notice: str = ""
    behaviors: list[str] = field(default_factory=list)
    sensory_bias: Optional[str] = None
    relational_tendencies: Optional[str] = None
    anti_patterns: list[str] = field(default_factory=list)
    example_lines: list[str] = field(default_factory=list)    # legacy — prefer reference_quotes
    # voice enrichment layer
    speech_patterns: list[str] = field(default_factory=list)  # structural speech habits
    lexical_markers: list[str] = field(default_factory=list)  # recurring words/phrases
    reference_quotes: list[ReferenceQuote] = field(default_factory=list)
    authorial_material: list[AuthorialMaterial] = field(default_factory=list)


@dataclass
class Story:
    role: Optional[str] = None
    scene_function: Optional[str] = None


@dataclass
class StyleTrace:
    """Populated by extraction pipeline; null when profile is manual."""
    dominant_verbs: Optional[str] = None      # physical | cognitive | mixed
    concrete_noun_ratio: Optional[float] = None
    common_tokens: list[str] = field(default_factory=list)


@dataclass
class Provenance:
    local_path: Optional[str] = None
    registry_path: str = ""


@dataclass
class Demographics:
    """
    Foundational demographic facts that shape voice, register, and behavior.
    regionalism may later feed an accent reference file or dialect guide.
    """
    age: str = ""                        # e.g. "mid-40s", "late teens", "elderly"
    gender: str = ""                     # free text — e.g. "male", "woman", "nonbinary"
    regionalism: str = ""                # dialect/accent — e.g. "Texas drawl", "London East End"
    physical_condition: Optional[str] = None  # notable constraint; None = no notable condition
    class_register: str = ""            # e.g. "working class", "old money", "self-educated"
    regionalism_strength: str = "low"   # how strongly regional flavor appears in speech: low|medium|high


# ── Root profile ──────────────────────────────────────────────────────────────

@dataclass
class CharacterProfile:
    character_id: str
    display_name: str
    source_author: Optional[str]
    source_work: Optional[str]
    source_mode: str                     # manual | extracted | imported | generated
    created_at: str
    updated_at: str

    demographics: Demographics = field(default_factory=Demographics)
    surface: Surface = field(default_factory=Surface)
    inner_engine: InnerEngine = field(default_factory=InnerEngine)
    voice: Voice = field(default_factory=Voice)
    behavior: Behavior = field(default_factory=Behavior)
    signature: Signature = field(default_factory=Signature)
    story: Story = field(default_factory=Story)
    style_trace: StyleTrace = field(default_factory=StyleTrace)
    provenance: Provenance = field(default_factory=Provenance)


# ── ID helpers ────────────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", "_", text)
    return text.strip("_")


def source_slug(source_mode: str, source_author: Optional[str]) -> str:
    """Return the source portion of a character_id."""
    if source_author:
        return _slugify(source_author)
    return source_mode  # "manual" | "generated" | "imported"


def make_character_id(slug: str, display_name: str, existing_ids: set[str]) -> str:
    """Generate a deterministic, collision-safe character_id."""
    base = f"{slug}__{_slugify(display_name)}"
    if base not in existing_ids:
        return base
    n = 2
    while f"{base}_{n}" in existing_ids:
        n += 1
    return f"{base}_{n}"


# ── Serialization ─────────────────────────────────────────────────────────────

def profile_to_dict(p: CharacterProfile) -> dict:
    import dataclasses
    return dataclasses.asdict(p)


def profile_from_dict(d: dict) -> CharacterProfile:
    sig = d.get("signature", {})
    demo = d.get("demographics", {})
    return CharacterProfile(
        character_id=d["character_id"],
        display_name=d["display_name"],
        source_author=d.get("source_author"),
        source_work=d.get("source_work"),
        source_mode=d["source_mode"],
        created_at=d["created_at"],
        updated_at=d["updated_at"],
        demographics=Demographics(
            age=demo.get("age", ""),
            gender=demo.get("gender", ""),
            regionalism=demo.get("regionalism", ""),
            physical_condition=demo.get("physical_condition"),
            class_register=demo.get("class_register", ""),
            regionalism_strength=demo.get("regionalism_strength", "low"),
        ),
        surface=Surface(**d.get("surface", {})),
        inner_engine=InnerEngine(**d.get("inner_engine", {})),
        voice=Voice(**d.get("voice", {})),
        behavior=Behavior(**d.get("behavior", {})),
        signature=Signature(
            what_they_notice=sig.get("what_they_notice", ""),
            behaviors=sig.get("behaviors", []),
            sensory_bias=sig.get("sensory_bias"),
            relational_tendencies=sig.get("relational_tendencies"),
            anti_patterns=sig.get("anti_patterns", []),
            example_lines=sig.get("example_lines", []),
            speech_patterns=sig.get("speech_patterns", []),
            lexical_markers=sig.get("lexical_markers", []),
            reference_quotes=[ReferenceQuote(**q) for q in sig.get("reference_quotes", [])],
            authorial_material=[AuthorialMaterial(**m) for m in sig.get("authorial_material", [])],
        ),
        story=Story(**d.get("story", {})),
        style_trace=StyleTrace(**d.get("style_trace", {})),
        provenance=Provenance(**d.get("provenance", {})),
    )


# ── Markdown dossier ──────────────────────────────────────────────────────────

def profile_to_markdown(p: CharacterProfile) -> str:
    def _line(label: str, value: str | None) -> str:
        return f"- {label}: {value}" if value else ""

    lines = [f"# Character: {p.display_name}", ""]

    # Source
    lines += ["## Source", f"- id: `{p.character_id}`", f"- mode: {p.source_mode}"]
    if p.source_author:
        lines.append(f"- author: {p.source_author}")
    if p.source_work:
        lines.append(f"- work: {p.source_work}")

    # Demographics
    d = p.demographics
    if any([d.age, d.gender, d.regionalism, d.physical_condition, d.class_register]):
        lines += ["", "## Demographics"]
        if d.age:
            lines.append(f"- age: {d.age}")
        if d.gender:
            lines.append(f"- gender: {d.gender}")
        if d.regionalism:
            lines.append(f"- regionalism / accent: {d.regionalism}")
        if d.class_register:
            lines.append(f"- class / register: {d.class_register}")
        if d.physical_condition:
            lines.append(f"- physical condition: {d.physical_condition}")

    # Surface
    lines += ["", "## Surface", f"- first impression: {p.surface.first_impression}"]

    # Inner engine
    ie = p.inner_engine
    lines += [
        "", "## Inner engine",
        f"- core desire: {ie.core_desire}",
        f"- core fear: {ie.core_fear}",
    ]
    if ie.avoidance:
        lines.append(f"- avoidance: {ie.avoidance}")
    if ie.what_they_hide:
        lines.append(f"- what they hide: {ie.what_they_hide}")
    lines.append(f"- key contradiction: {ie.key_contradiction}")
    if ie.contradiction_behavior:
        lines.append(f"- contradiction in behavior: {ie.contradiction_behavior}")
    for label, val in [("shame", ie.shame), ("false belief", ie.false_belief), ("taboo", ie.taboo)]:
        if val:
            lines.append(_line(label, val))

    # Voice
    v = p.voice
    lines += [
        "", "## Voice",
        f"- {v.description}",
        f"- sentence length: {v.sentence_length}",
        f"- question frequency: {v.question_frequency}",
        f"- abstraction level: {v.abstraction_level}",
        f"- conversation control: {v.conversation_control}",
        f"- verbosity: {v.verbosity}",
    ]
    if v.uses_fragments is not None:
        lines.append(f"- uses fragments: {'yes' if v.uses_fragments else 'no'}")
    lines += [f"- repetition: {v.repetition}", f"- metaphor: {v.metaphor}"]

    # Behavior
    b = p.behavior
    lines += ["", "## Behavior"]
    if b.conflict_response:
        lines.append(f"- conflict response: {b.conflict_response}")
    if b.avoidance_pattern:
        lines.append(f"- avoidance pattern: {b.avoidance_pattern}")
    lines.append(f"- dialogue stance: {b.dialogue_stance}")
    if b.dialogue_moves:
        lines.append(f"- dialogue moves: {', '.join(b.dialogue_moves)}")
    for label, val in [
        ("with people they need", b.status_with_needed),
        ("with people they don't need", b.status_with_unneeded),
        ("intimacy style", b.intimacy_style),
        ("pressure response", b.pressure_response),
    ]:
        if val:
            lines.append(_line(label, val))

    # Signature
    s = p.signature
    lines += ["", "## Signature"]
    if s.what_they_notice:
        lines.append(f"- what they notice: {s.what_they_notice}")
    for b_item in s.behaviors:
        lines.append(f"- {b_item}")
    for label, val in [("sensory bias", s.sensory_bias), ("relational tendencies", s.relational_tendencies)]:
        if val:
            lines.append(_line(label, val))

    if s.anti_patterns:
        lines += ["", "## Anti-patterns"]
        for ap in s.anti_patterns:
            lines.append(f"- {ap}")

    # Voice material
    if s.speech_patterns:
        lines += ["", "## Speech patterns"]
        for sp in s.speech_patterns:
            lines.append(f"- {sp}")

    if s.lexical_markers:
        lines += ["", "## Lexical markers"]
        for lm in s.lexical_markers:
            lines.append(f"- {lm}")

    if s.reference_quotes:
        lines += ["", "## Reference quotes"]
        for q in s.reference_quotes:
            canonical = " ✓" if q.is_canonical else ""
            lines.append(f"> {q.text}{canonical}")
            if q.source:
                lines.append(f"> — {q.source}")
            if q.tone:
                lines.append(f"> *tone: {q.tone}*")

    if s.authorial_material:
        lines += ["", "## Authorial material"]
        for m in s.authorial_material:
            direct = " [direct use allowed]" if m.direct_use_allowed else " [paraphrase preferred]"
            lines.append(f"- {m.text}{direct}")
            if m.source:
                lines.append(f"  *source: {m.source}*")

    # Story
    if p.story.role or p.story.scene_function:
        lines += ["", "## Story"]
        if p.story.role:
            lines.append(f"- role: {p.story.role}")
        if p.story.scene_function:
            lines.append(f"- scene function: {p.story.scene_function}")

    if s.example_lines:
        lines += ["", "## Example lines"]
        for el in s.example_lines:
            lines.append(f"> {el}")

    return "\n".join(line for line in lines)
