"""
Dialog and scene generation from character profiles.

dialog: speech-focused — speaker-labeled lines, tight exchange
scene:  broader — includes narration, beats, physical action

Output:
- printed to terminal
- saved as Markdown to projects/<project>/dialog_drafts/ or scene_drafts/

Filename pattern:
  <timestamp>_<charA_id>_vs_<charB_id>_<setting_slug>.md
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from augmented_fiction.modules.voice.characterbuilder.schema import (
    CharacterProfile,
    profile_to_markdown,
)


# ── Prompt builders ───────────────────────────────────────────────────────────

def _profile_summary(
    p: CharacterProfile,
    quote_mode: str = "auto",
    include_authorial_material: bool = False,
) -> str:
    """
    Compact profile summary for the LLM prompt.

    quote_mode: auto | light | strong
      auto   — include voice anchors naturally
      light  — minimal quote influence, mostly fresh generation
      strong — stronger mimicry, closer to stored voice material
    """
    ie = p.inner_engine
    v = p.voice
    b = p.behavior
    s = p.signature
    d = p.demographics

    lines = [
        f"CHARACTER: {p.display_name}",
        f"source: {p.source_author or 'original'}"
        + (f", {p.source_work}" if p.source_work else ""),
    ]

    # Demographics — include any non-empty fields
    demo_parts = []
    if d.age:
        demo_parts.append(f"age: {d.age}")
    if d.gender:
        demo_parts.append(f"gender: {d.gender}")
    if d.regionalism:
        demo_parts.append(f"regionalism: {d.regionalism}")
    if d.class_register:
        demo_parts.append(f"register: {d.class_register}")
    if d.physical_condition:
        demo_parts.append(f"physical: {d.physical_condition}")
    if demo_parts:
        lines.append(" | ".join(demo_parts))

    lines += [
        f"first impression: {p.surface.first_impression}",
        f"core desire: {ie.core_desire}",
        f"core fear: {ie.core_fear}",
    ]
    if ie.avoidance:
        lines.append(f"avoidance: {ie.avoidance}")
    if ie.what_they_hide:
        lines.append(f"hides: {ie.what_they_hide}")
    lines.append(f"key contradiction: {ie.key_contradiction}")
    if ie.contradiction_behavior:
        lines.append(f"says/does gap: {ie.contradiction_behavior}")
    if ie.false_belief:
        lines.append(f"false belief: {ie.false_belief}")
    if ie.taboo:
        lines.append(f"taboo: {ie.taboo}")

    lines.append(
        f"voice: {v.description} | control: {v.conversation_control} | "
        f"length: {v.sentence_length} | abstraction: {v.abstraction_level}"
    )
    if b.conflict_response:
        lines.append(f"under challenge: {b.conflict_response}")
    if b.intimacy_style:
        lines.append(f"intimacy: {b.intimacy_style}")
    if b.pressure_response:
        lines.append(f"sustained pressure: {b.pressure_response}")
    if s.what_they_notice:
        lines.append(f"notices: {s.what_they_notice}")
    if s.behaviors:
        lines.append(f"signature behaviors: {'; '.join(s.behaviors)}")
    if s.anti_patterns:
        lines.append(f"never does: {'; '.join(s.anti_patterns)}")

    # Voice enrichment — controlled by quote_mode
    if quote_mode != "light":
        if s.speech_patterns:
            lines.append(f"speech patterns: {'; '.join(s.speech_patterns)}")
        if s.lexical_markers:
            lines.append(f"lexical markers / verbal habits: {'; '.join(s.lexical_markers)}")

    # Reference quotes — use as voice anchors
    all_quotes = list(s.reference_quotes) + [
        type("Q", (), {"text": el, "is_canonical": False, "tone": ""})()  # type: ignore
        for el in s.example_lines
    ]
    if all_quotes and quote_mode != "light":
        lines.append("voice reference lines (use as anchors, not verbatim unless appropriate):")
        for q in all_quotes[:6]:
            canon = " [canonical]" if getattr(q, "is_canonical", False) else ""
            tone = f" [{q.tone}]" if getattr(q, "tone", "") else ""
            lines.append(f"  \"{q.text}\"{canon}{tone}")

    # Authorial material — optional, treated as candidate content
    if include_authorial_material and s.authorial_material:
        lines.append("authorial material (available for thematic use — prefer paraphrase unless direct use allowed):")
        for m in s.authorial_material:
            direct = " [direct use permitted]" if m.direct_use_allowed else " [paraphrase preferred]"
            lines.append(f"  \"{m.text}\"{direct}")

    return "\n".join(lines)


_SELF_DIALOGUE_INSTRUCTION = (
    "The same character has been selected twice. "
    "Treat this as internal self-dialogue — one mind under pressure, not two people in conversation. "
    "Rules: "
    "Both sides are the same person and must sound identical in voice, diction, rhythm, and habitual phrasing. "
    "Do not use a clean back-and-forth structure. "
    "Allow uneven rhythm: one side may speak at length, the other in a fragment or not at all. "
    "Allow repetition — the same phrase or thought returning, slightly shifted. "
    "Allow partial and unfinished thoughts. Do not resolve every line cleanly. "
    "Not every line should be a full sentence. "
    "Allow fragments, interruptions, and mid-thought corrections. "
    "A thought may be started and abandoned. Some lines may feel rushed or compressed. "
    "Do not make either side articulate or self-aware in a literary way — "
    "the character does not know they are having an internal dialogue. "
    "Do not make one side wiser, calmer, or more moral than the other. "
    "The tension comes from pressure, not from argument. "
    "It should feel like thinking, not staging. "
    "Occasionally destabilize a line from within: repeat a word or phrase mid-line, "
    "restart a sentence in a slightly different way, contradict or correct within the same line, "
    "or allow a brief hesitation marker (— or …) where natural. "
    "Do this sparingly — not on every line — but enough to reduce polish. "
    "Avoid summarizing thoughts into general truths. "
    "Prefer immediate, reactive, situation-specific language. "
    "Do not write lines like 'They like a man who knows what he wants.' "
    "Write lines like 'They like that, don't they. Someone who — yeah.' "
    "Less complete, more in-head. "
    "Do not use generalized statements about people — no 'they', 'people', 'women', 'men', or similar. "
    "If the character starts to generalize, immediately collapse it back into: "
    "what they are seeing right now, what she might think right now, what they are about to do next. "
    "Do not leave the thought at the level of 'people' or 'they'. "
    "Do not alternate cleanly between opposing thoughts. "
    "Allow one line of thinking to run for several lines before any interruption. "
    "Allow interruption without a full counter-thought. "
    "Allow the mind to collapse back into the same idea repeatedly. "
    "Do not turn thoughts into clean instructions. "
    "Instead of 'Just do X', prefer hesitation, a half-formed correction, or an aborted instruction. "
    "The character should not fully regain control of their thoughts. "
    "Even when they try to stabilize ('just keep it light'), doubt should bleed back in quickly. "
    "Do not conclude or summarize the thought. "
    "Internal dialogue should trail, loop, and redirect — not resolve."
)


def _build_dialog_prompt(
    profiles: list[CharacterProfile],
    setting: str,
    mode: str,
    exchange_count: int,
    quote_mode: str = "auto",
    allow_direct_quotes: bool = False,
    include_authorial_material: bool = False,
    is_self_dialogue: bool = False,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for dialog or scene generation."""
    names = [p.display_name for p in profiles]

    profile_blocks = "\n\n".join(
        _profile_summary(p, quote_mode=quote_mode, include_authorial_material=include_authorial_material)
        for p in profiles
    )

    quote_instruction = ""
    if quote_mode == "strong":
        quote_instruction = (
            "Strongly favour the character's stored voice material. "
            "Generated lines should closely echo the cadence and diction of reference lines. "
        )
    elif quote_mode == "light":
        quote_instruction = (
            "Generate mostly fresh lines — use profile constraints for behavior and tone only. "
        )
    else:  # auto
        quote_instruction = (
            "Use stored voice material as natural anchors. "
            "Generate new lines that feel consistent with the character's voice. "
        )

    direct_quote_instruction = (
        "Verbatim reuse of reference lines is permitted where clearly appropriate. "
        if allow_direct_quotes
        else "Do not copy reference lines verbatim — generate fresh lines in the character's voice. "
    )

    self_dialogue_suffix = f" {_SELF_DIALOGUE_INSTRUCTION}" if is_self_dialogue else ""

    if mode == "dialog":
        system = (
            "You are a literary fiction writer generating draft dialogue. "
            "This is proposed material — the user will review and may rewrite freely. "
            "Each character must speak and behave strictly according to their profile constraints. "
            "Do not flatten characters into generic speech. "
            "Show subtext. Reflect differing aims. Preserve character-specific language. "
            f"{quote_instruction}{direct_quote_instruction}"
            "Format: Speaker Name: dialogue line. No stage directions unless a beat is essential. "
            f"Do not add a title or preamble — start immediately with dialogue.{self_dialogue_suffix}"
        )
        if is_self_dialogue:
            user = (
                f"Setting: {setting}\n\n"
                f"Character:\n\n{profile_blocks}\n\n"
                f"Write an internal self-dialogue of approximately {exchange_count} exchanges. "
                f"Both voices belong to {names[0]}. "
                "The tension must come from within one mind — not from two separate people."
            )
        else:
            user = (
                f"Setting: {setting}\n\n"
                f"Characters:\n\n{profile_blocks}\n\n"
                f"Write a dialogue of approximately {exchange_count} exchanges "
                f"between {' and '.join(names)}. "
                "Each character's voice must be distinct and traceable to their profile."
            )
    else:  # scene
        system = (
            "You are a literary fiction writer generating a draft scene. "
            "This is proposed material — the user will review and may rewrite freely. "
            "Include dialogue, physical beats, narration, and sensory detail. "
            "Each character must speak, move, and react according to their profile constraints. "
            "Scene narration should be neutral — not collapsed into any single character's style. "
            f"{quote_instruction}{direct_quote_instruction}"
            f"Do not add a title or preamble — begin the scene immediately.{self_dialogue_suffix}"
        )
        if is_self_dialogue:
            user = (
                f"Setting: {setting}\n\n"
                f"Character:\n\n{profile_blocks}\n\n"
                f"Write a scene showing {names[0]}'s internal experience — "
                "thought, action, and self-directed speech. "
                "Both sides of the internal exchange must sound like the same person."
            )
        else:
            user = (
                f"Setting: {setting}\n\n"
                f"Characters:\n\n{profile_blocks}\n\n"
                f"Write a scene involving {', '.join(names)}. "
                "Include dialogue, action, and narration. "
                "Each character's behavior must be traceable to their profile."
            )

    return system, user


# ── LLM call ──────────────────────────────────────────────────────────────────

def _call_llm(system: str, user: str, model: str, temperature: float, api_key: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content or ""


# ── Output helpers ────────────────────────────────────────────────────────────

def _slugify(text: str, max_len: int = 40) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", "_", text)
    return text[:max_len].strip("_")


def _draft_filename(profiles: list[CharacterProfile], setting: str, mode: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    ids = "_vs_".join(p.character_id for p in profiles)
    setting_slug = _slugify(setting, 40)
    return f"{ts}_{ids}_{setting_slug}.md"


def _build_draft_md(
    profiles: list[CharacterProfile],
    setting: str,
    mode: str,
    generated_text: str,
    model: str,
    quote_mode: str = "auto",
    allow_direct_quotes: bool = False,
    include_authorial_material: bool = False,
    is_self_dialogue: bool = False,
) -> str:
    names = ", ".join(p.character_id for p in profiles)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    effective_mode = "internal (self-dialogue)" if is_self_dialogue else mode
    header = (
        f"# {'Dialog' if mode == 'dialog' else 'Scene'} Draft\n\n"
        f"- characters: {names}\n"
        f"- mode: {effective_mode}\n"
        f"- setting: {setting}\n"
        f"- model: {model}\n"
        f"- generated_at: {ts}\n"
        f"- quote_mode: {quote_mode}\n"
        f"- direct_quotes_allowed: {str(allow_direct_quotes).lower()}\n"
        f"- authorial_material_used: {str(include_authorial_material).lower()}\n\n"
        f"---\n\n"
    )
    return header + generated_text.strip() + "\n"


# ── Public entry point ────────────────────────────────────────────────────────

def generate(
    profiles: list[CharacterProfile],
    setting: str,
    mode: str,
    project_path: Path,
    llm_config,
    exchange_count: int = 12,
    quote_mode: str = "auto",           # auto | light | strong
    allow_direct_quotes: bool = False,
    include_authorial_material: bool = False,
) -> str:
    """
    Generate dialog or scene from profiles and save to project drafts directory.

    When the same character is selected twice (A == B), the system automatically
    switches to internal self-dialogue mode — no explicit flag required.

    Returns the path of the saved draft file.
    """
    api_key = os.environ.get(llm_config.api_key_env, "")
    if not api_key:
        raise RuntimeError(
            f"LLM API key not set — expected env var: {llm_config.api_key_env}"
        )

    # Detect A == B → internal self-dialogue
    is_self_dialogue = (
        len(profiles) >= 2
        and profiles[0].character_id == profiles[1].character_id
    )
    if is_self_dialogue:
        profiles = [profiles[0]]  # deduplicate; prompt handles two-voice framing

    system, user = _build_dialog_prompt(
        profiles, setting, mode, exchange_count,
        quote_mode=quote_mode,
        allow_direct_quotes=allow_direct_quotes,
        include_authorial_material=include_authorial_material,
        is_self_dialogue=is_self_dialogue,
    )
    generated = _call_llm(system, user, llm_config.model, llm_config.temperature, api_key)

    draft_md = _build_draft_md(
        profiles, setting, mode, generated, llm_config.model,
        quote_mode=quote_mode,
        allow_direct_quotes=allow_direct_quotes,
        include_authorial_material=include_authorial_material,
        is_self_dialogue=is_self_dialogue,
    )

    drafts_dir = project_path / (f"dialog_drafts" if mode == "dialog" else "scene_drafts")
    drafts_dir.mkdir(parents=True, exist_ok=True)

    filename = _draft_filename(profiles, setting, mode)
    out_path = drafts_dir / filename
    out_path.write_text(draft_md, encoding="utf-8")

    return str(out_path)
