"""
Author-pack guided passage generation.

Converts a generation packet into a structured prompt and calls GPT-4o
to produce a passage constrained by the author's style profile.

Invoked via:
  uv run python -m augmented_fiction.modules.voice.turnofphrase generate
      <author_folder> "prompt text" --words 180 [--save]

Outputs (returned dict):
  generated_text       — the passage, ready for the writer to edit
  writer_id
  word_target
  mode_guess
  book_bias
  model
  temperature
  _generation_packet   — full packet (debug / inspection)
  _prompt              — full LLM prompt sent (debug)

Persistence:
  --save appends one JSON record to author_folder/generated/generations.jsonl
"""
from __future__ import annotations

import json
import os
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from .generation_packet import build_generation_packet

_TEMPERATURE = 0.75


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _derive_exemplar_structure(exemplars: list[dict]) -> dict:
    """
    Compute structural statistics from retrieved exemplars.
    Used to convert exemplars from inspiration into measurable anchors.
    """
    if not exemplars:
        return {}
    all_lens: list[float] = []
    for e in exemplars:
        features = e.get("features", {})
        if features.get("avg_sentence_length") and features.get("sentence_count"):
            n = int(features["sentence_count"])
            avg = float(features["avg_sentence_length"])
            all_lens.extend([avg] * n)
        else:
            sents = [s.strip() for s in re.split(r"[.!?]", e.get("text", "")) if s.strip()]
            all_lens.extend(float(len(s.split())) for s in sents)
    if not all_lens:
        return {}
    avg = statistics.mean(all_lens)
    short_r = sum(1 for l in all_lens if l <= 10) / len(all_lens)
    return {
        "avg_sentence_length": round(avg, 1),
        "short_sentence_ratio": round(short_r, 2),
    }


def _build_generation_prompt(packet: dict) -> str:
    """Convert a generation packet into a structured LLM instruction set."""

    # --- Structural anchoring from exemplars ---
    exemplar_block = ""
    if packet["retrieved_exemplars"]:
        struct = _derive_exemplar_structure(packet["retrieved_exemplars"])
        struct_summary = ""
        if struct:
            struct_summary = (
                f"\nStructural profile of these exemplars: "
                f"avg {struct['avg_sentence_length']} words/sentence, "
                f"{struct['short_sentence_ratio']:.0%} short sentences. "
                f"Match this rhythm — not the vocabulary.\n"
            )
        exemplar_block = (
            "\n\n## Exemplar passages from author corpus\n"
            "Use these as structural models. Match their sentence rhythm, "
            "clause chaining, and density. Do not copy wording."
            + struct_summary
        )
        for e in packet["retrieved_exemplars"]:
            exemplar_block += (
                f"\n[{e.get('mode_guess', '?')} | {e['source_file']}]\n{e['text']}\n"
            )

    # --- Soft book-bias note ---
    bias_note = ""
    if packet["book_bias"]:
        top_book = max(packet["book_bias"], key=lambda k: packet["book_bias"][k])
        if packet["book_bias"][top_book] > 0.45:
            bias_note = (
                f"\nThe prompt vocabulary aligns most closely with a "
                f"'{top_book.replace('_', ' ')}' register. "
                "Let that inform tone and imagery — do not reference it explicitly.\n"
            )

    style_traits_text = "\n".join(f"- {t}" for t in packet["style_traits"])
    avoidances_text = "\n".join(f"- {a}" for a in packet["avoidances"])
    edit_transforms_text = "\n".join(f"- {t}" for t in packet["edit_transformations"])
    mode_notes_text = (
        "\n".join(f"- {n}" for n in packet["mode_notes"])
        if packet["mode_notes"]
        else "(no specific mode notes)"
    )
    lexical_text = "\n".join(f"- {l}" for l in packet["lexical_tendencies"][:4])

    # --- Structure targets section ---
    structure_section = ""
    st = packet.get("structure_targets", {})
    if st:
        accumulative_line = ""
        if st.get("accumulative_sentence_required"):
            accumulative_line = (
                f"- Include at least {st.get('long_sentence_min', 1)} longer accumulative sentence — "
                "use it to build momentum, compression, or narrative pressure\n"
            )
        structure_section = f"""
## Structure targets (derived from author corpus — follow these precisely)
- Sentence count: {st.get('sentence_count_min')}–{st.get('sentence_count_max')} sentences
- Short sentences (≤10 words): approximately {st.get('short_sentence_ratio_target', 0):.0%} of all sentences
- Long sentences (≥20 words): no more than {st.get('long_sentence_ratio_max', 0.15):.0%}
- Average sentence length: {st.get('avg_sentence_length_min')}–{st.get('avg_sentence_length_max')} words
{accumulative_line}"""

    # --- Clause dynamics section ---
    clause_section = ""
    cd = packet.get("clause_dynamics", {})
    if cd:
        coord = cd.get("coordination_preference", "medium")
        subord = cd.get("subordination_preference", "medium")
        frag = cd.get("fragment_tolerance", "medium")
        acc_style = cd.get("accumulation_style", "paratactic")
        clause_section = f"""
## Clause dynamics (author-specific — follow carefully)
- Coordination (joining with 'and', 'but'): {coord}
- Subordination (because, although, when...): {subord}
- Fragment tolerance (incomplete sentences as beats): {frag}
- Accumulation style: {acc_style.replace('_', ' ')}
- Vary sentence shapes — do not repeat the same clause structure too many times in a row
- Mix simple declaratives, chained clauses, and compressed descriptive fragments
"""

    # --- Lexical anchors (soft injection) ---
    anchors = packet.get("lexical_anchors", [])
    anchors_section = ""
    if anchors:
        anchors_section = f"""
## Lexical anchors (author-specific vocabulary — draw from these where natural)
{', '.join(anchors)}
Do not force every anchor into the text. Use them where they feel right.
"""

    # --- Dialogue structural enforcement ---
    dialogue_section = ""
    if packet.get("dialogue_required"):
        dialogue_section = """
## Dialogue Structure Rules (REQUIRED — follow exactly)
- The passage must primarily consist of spoken lines. Dialogue drives the scene.
- Do NOT use quotation marks around speech.
- At least 60% of sentences must be spoken lines.
- Narration is minimal — one or two lines maximum between exchanges.
- Use short alternating lines (1–2 sentences per utterance).
- Silence and pauses are allowed as standalone lines.
- Do not explain what characters feel — let the exchange carry it.

## Dialogue compression (REQUIRED)
- Remove speaker labels whenever possible. Let the line stand on its own.
- Prefer bare spoken lines over attributed lines.
- Avoid repeated constructions: he said / she replied / the other man said.
- Attribution is allowed once or twice per passage — not on every line.
- Identify speakers through rhythm, register, and content — not tags.

## Anti-generic dialogue (REQUIRED)
- Avoid interchangeable filler that could belong to any screenplay or workshop draft.
- Avoid lines like: Yeah but money's tight. Maybe we just go. We could try. What about the time.
- Prefer lines with texture, asymmetry, or concrete verbal pressure.
- The exchange should feel specific to these characters in this moment — not merely functional.
- At least some lines should feel like they could only come from this author's voice.
"""

    return f"""You are a controlled literary generation system. Your task is to write a new prose passage.

## Writer
{packet['writer_id'].replace('_', ' ').title()}

## Generation prompt (content facts only — expand into full prose)
{packet['prompt']}

## Target length
Approximately {packet['word_target']} words. Stop when the passage is complete — do not pad or truncate mid-thought.

## Passage mode
{packet['mode_guess']}
{mode_notes_text}
{bias_note}{structure_section}{clause_section}{dialogue_section}
## Style traits (author invariants — follow strictly)
{style_traits_text}

## Edit transformations (apply during composition)
{edit_transforms_text}

## Avoidances (strictly avoid these)
{avoidances_text}

## Compression and implication
- Prefer to imply conditions through physical detail rather than stating them directly
- Do not explain what a character feels — show the body, the object, the action
- Trust the reader; remove explicit framing around events that speak for themselves

## Polysyndeton guidance
Use 'and' as a connective where it serves the rhythm. Do not rely on it in every sentence — vary the coordination. Reserve it for accumulation and momentum, not mechanical repetition.

## Quality guardrails
- Avoid parody-level stylisation — the passage should feel authored, not imitated
- Avoid repeating the same sentence shape too many times in a row
- Avoid generic bleak phrasing; ground bleakness in specific physical detail

## Lexical register
{lexical_text}
{anchors_section}{exemplar_block}
---

Write the passage now. Output only the passage — no title, no commentary, no surrounding quotation marks."""


# ---------------------------------------------------------------------------
# Post-generation evaluation + correction
# ---------------------------------------------------------------------------

def _evaluate_generated(text: str, author_folder: Path) -> dict:
    """Run the existing analysis stack against generated text."""
    from .style_comparator import analyze_against_writer_style
    profile_path = author_folder / "profile" / "style_profile.json"
    if not profile_path.exists():
        return {}
    try:
        return analyze_against_writer_style(text, author_folder.name, profile_path)
    except Exception:
        return {}


def _derive_correction_hints(analysis: dict, packet: dict) -> list[str]:
    """Map analysis output to concrete correction instructions."""
    hints: list[str] = []
    cls = analysis.get("feature_classifications", {})
    uf = analysis.get("user_features", {})

    if cls.get("sentence_length") == "out_of_range":
        avg = uf.get("avg_sentence_length", 10.0)
        if avg > 10:
            hints.append(
                "Sentences are too long. Break most into short declarative units of 5–10 words."
            )

    if cls.get("abstract_noun_ratio") in ("out_of_range", "near_edge"):
        hints.append(
            "Too many abstract nouns. Replace with concrete physical objects, materials, or actions."
        )

    if cls.get("physical_verb_ratio") == "out_of_range":
        hints.append(
            "Replace cognitive verbs (think, feel, know, wonder) with physical actions — "
            "show the body doing something."
        )

    if cls.get("and_rate") == "out_of_range":
        hints.append(
            "Increase polysyndeton — connect clauses and list items with 'and' "
            "rather than commas or semicolons."
        )

    # Sentence-level drift
    for s in analysis.get("sentence_drift", [])[:2]:
        reason = s.get("reason", "")
        excerpt = s.get("sentence", "")[:70]
        if "long sentence" in reason:
            hints.append(f'Split this: "{excerpt}..."')
        elif "cognitive verbs" in reason:
            hints.append(f'Recast with physical action (cognitive framing): "{excerpt}..."')

    # Dialogue-specific — only add these when dialogue ratio actually failed
    if packet.get("dialogue_required"):
        hints.append(
            "You produced too much narration. "
            "Reduce narration to at most 2 sentences total across the entire passage. "
            "Let the scene be carried by spoken exchange."
        )
        hints.append(
            "Remove speaker labels (he said / she replied / the other man said) wherever possible. "
            "No quotation marks. Let the line stand on its own."
        )
        hints.append(
            "Avoid generic interchangeable dialogue. "
            "Each line should feel specific, pressured, or off-balance — not workshop neutral."
        )

    return hints


def _build_correction_prompt(original_prompt: str, correction_hints: list[str]) -> str:
    """Rebuild the original prompt with a correction pass appended."""
    hints_text = "\n".join(f"- {h}" for h in correction_hints)
    return (
        original_prompt
        + f"""

---

## Correction pass required

The previous attempt had these style issues that must be fixed:
{hints_text}

Generate a fresh passage that addresses all of the above corrections while following all earlier style instructions. Output only the passage."""
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_generation(result: dict, author_folder: Path) -> Path:
    """
    Append one generation record to author_folder/generated/generations.jsonl.
    Returns the path to the log file.
    """
    generated_dir = author_folder / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    log_path = generated_dir / "generations.jsonl"

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "writer_id": result["writer_id"],
        "prompt": result["_generation_packet"]["prompt"],
        "word_target": result["word_target"],
        "mode_guess": result["mode_guess"],
        "book_bias": result["book_bias"],
        "model": result["model"],
        "temperature": result["temperature"],
        "generated_text": result["generated_text"],
        "regenerated": result.get("regenerated", False),
        "correction_hints": result.get("correction_hints", []),
        "generation_packet": result["_generation_packet"],
        "prompt_sent": result["_prompt"],
    }

    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    return log_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_passage(
    author_folder: Path,
    prompt: str,
    word_target: int,
    model: str = "gpt-4o",
    n_exemplars: int = 3,
    rewrite: bool = False,
    mode_override: str | None = None,
) -> dict:
    """
    Generate a new passage guided by the full author pack.

    Returns a dict containing:
      generated_text, writer_id, word_target, mode_guess, book_bias,
      model, temperature, _generation_packet, _prompt
    """
    load_dotenv()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENAI_API_KEY not set. Export it or add it to a .env file."
        )

    packet = build_generation_packet(
        author_folder, prompt, word_target, n_exemplars,
        mode_override=mode_override,
    )
    generation_prompt = _build_generation_prompt(packet)

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    top_book = (
        max(packet["book_bias"], key=lambda k: packet["book_bias"][k])
        if packet["book_bias"] else "?"
    )
    classifier_mode = packet.get("classifier_mode_guess", packet["mode_guess"])
    resolved_mode = packet["mode_guess"]
    intent_fired = packet.get("force_dialogue_intent", False)
    override_note = ""
    if mode_override:
        override_note = f"  [override --mode {mode_override}]"
    elif intent_fired and classifier_mode != resolved_mode:
        override_note = f"  [dialogue intent override: classifier={classifier_mode}]"
    print(f"[turnofphrase] Generating passage via {model} ...")
    print(f"  mode: {resolved_mode}  |  dominant bias: {top_book}  |  target: {word_target} words{override_note}")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a precise literary generation system. "
                    "Follow all style constraints exactly. "
                    "Output only the requested prose passage."
                ),
            },
            {"role": "user", "content": generation_prompt},
        ],
        temperature=_TEMPERATURE,
    )

    generated_text = response.choices[0].message.content.strip()

    # --- Post-generation evaluate + optional correction pass ---
    postcheck = packet.get("postcheck_rules", {})
    max_regen = postcheck.get("max_regenerations", 1)
    regen_on = postcheck.get("regenerate_on_drift", ["moderate", "strong"])

    regenerated = False
    correction_hints: list[str] = []
    analysis: dict = {}

    # Dialogue ratio check
    dialogue_quality: dict | None = None
    if packet.get("dialogue_required"):
        dialogue_quality = _check_dialogue_ratio(
            generated_text,
            target=packet.get("dialogue_ratio_target", 0.6),
        )

    if max_regen > 0:
        analysis = _evaluate_generated(generated_text, author_folder)
        drift = analysis.get("drift_level", "none")
        dialogue_weak = dialogue_quality is not None and dialogue_quality.get("weak", False)

        if drift in regen_on or dialogue_weak:
            reason = f"drift={drift}" if drift in regen_on else "weak_dialogue"
            print(f"  [regen] {reason} — running correction pass ...")
            correction_hints = _derive_correction_hints(analysis, packet)
            correction_prompt = _build_correction_prompt(generation_prompt, correction_hints)

            regen_response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a precise literary generation system. "
                            "Follow all style constraints exactly. "
                            "Output only the requested prose passage."
                        ),
                    },
                    {"role": "user", "content": correction_prompt},
                ],
                temperature=_TEMPERATURE,
            )
            generated_text = regen_response.choices[0].message.content.strip()
            regenerated = True

            # Re-check dialogue quality on regenerated text
            if packet.get("dialogue_required"):
                dialogue_quality = _check_dialogue_ratio(
                    generated_text,
                    target=packet.get("dialogue_ratio_target", 0.6),
                )

    if dialogue_quality and dialogue_quality.get("weak"):
        print(
            f"  [warn] Dialogue ratio: {dialogue_quality['dialogue_ratio']:.0%} "
            f"(target ≥ {dialogue_quality['target']:.0%})"
        )

    # --- Optional dialogue rewrite pass ---
    # Use resolved dialogue intent — not raw dialogue_required — so rewrite fires
    # even when the classifier misfired and was overridden.
    dialogue_resolved = (
        packet.get("dialogue_required")
        or packet.get("mode_guess") == "dialogue"
        or packet.get("force_dialogue_intent", False)
    )
    draft_text = generated_text
    rewrite_applied = False
    if rewrite and dialogue_resolved:
        from .rewrite_service import rewrite_dialogue_pass
        print(f"  [rewrite] Running dialogue rewrite pass ...")
        generated_text = rewrite_dialogue_pass(
            draft_text=draft_text,
            context={"writer_id": packet["writer_id"]},
            client=client,
            model=model,
            temperature=_TEMPERATURE,
        )
        rewrite_applied = True
        print(f"  [rewrite] Done.")

    result: dict = {
        "writer_id": packet["writer_id"],
        "word_target": word_target,
        "mode_guess": packet["mode_guess"],
        "book_bias": packet["book_bias"],
        "model": model,
        "temperature": _TEMPERATURE,
        "generated_text": generated_text,
        "regenerated": regenerated,
        "correction_hints": correction_hints,
        "rewrite_applied": rewrite_applied,
        "_analysis": analysis,
        "_generation_packet": packet,
        "_prompt": generation_prompt,
    }
    if rewrite_applied:
        result["_draft"] = draft_text
    if dialogue_quality is not None:
        result["dialogue_quality"] = dialogue_quality
    return result


# ---------------------------------------------------------------------------
# Dialogue failure detection
# ---------------------------------------------------------------------------

def _check_dialogue_ratio(text: str, target: float = 0.6) -> dict:
    """
    Estimate the fraction of sentences that are dialogue-like.

    A sentence is considered dialogue if it:
      - starts with a first/second person pronoun (I, We, You, Ain't, ...)
      - is very short (≤ 5 words) — beat lines, pauses, terse exchanges
      - starts with a dialogue-typical opener (Yes, No, Well, Come, etc.)

    Narration sentences start with third-person subjects (He, She, They, The...).
    This is a heuristic flag for obviously non-dialogue output.
    """
    import re as _re

    _DIALOGUE_STARTERS = frozenset([
        "i", "we", "you", "ain't", "don't", "didn't", "it's", "there's",
        "yes", "no", "well", "maybe", "alright", "what", "why", "how",
        "come", "get", "go", "stop", "look", "listen", "wait",
    ])
    _NARRATION_STARTERS = frozenset([
        "he", "she", "they", "the", "his", "her", "their", "a", "an",
        "there", "it", "silence", "darkness",
    ])

    sents = [s.strip() for s in _re.split(r"[.!?]", text) if s.strip()]
    if not sents:
        return {"dialogue_ratio": 0.0, "target": target, "weak": True}

    dialogue_count = 0
    for sent in sents:
        words = sent.lower().split()
        if not words:
            continue
        first = words[0]
        wc = len(words)
        if wc <= 5:
            dialogue_count += 1
        elif first in _DIALOGUE_STARTERS:
            dialogue_count += 1
        elif first not in _NARRATION_STARTERS and wc <= 12:
            dialogue_count += 1

    ratio = dialogue_count / len(sents)
    return {
        "dialogue_ratio": round(ratio, 3),
        "sentence_count": len(sents),
        "dialogue_sentence_count": dialogue_count,
        "target": target,
        "weak": ratio < target,
    }
