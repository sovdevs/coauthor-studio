"""
Generation packet builder for author-pack guided passage generation.

Assembles a structured packet from four layers:
  Layer A — oeuvre-level author invariants (stable across books)
  Layer B — inferred book/style bias (heuristic, prompt-driven)
  Layer C — mode (action / reflective / descriptive / dialogue)
  Layer D — content facts / prompt facts

Inputs:
  author_folder/profile/style_profile.json
  author_folder/profile/lexicon_profile.json
  author_folder/profile/llm_abstractions.json
  author_folder/profile/style_rules.json
  author_folder/processed/exemplar_passages.jsonl
"""
from __future__ import annotations

import json
import re
import statistics
from pathlib import Path


# ---------------------------------------------------------------------------
# Book bias: keyword signals per canonical book key.
# Keys are derived from EPUB filenames via _epub_stem_to_key().
# ---------------------------------------------------------------------------

_BOOK_BIAS_SIGNALS: list[tuple[str, list[str]]] = [
    ("the_road", [
        "road", "ash", "cold", "gray", "grey", "hunger", "boy", "father",
        "snow", "frost", "winter", "frozen", "ice", "dead", "ruin", "shelter",
        "rain", "cart", "bleak", "dust", "silence", "fire", "dark", "crossing",
    ]),
    ("blood_meridian", [
        "war", "blood", "desert", "judge", "scalp", "horse", "kill", "violence",
        "raid", "bone", "skull", "sand", "rifle", "sword", "massacre", "camp",
        "plain", "murder", "brutal", "savage", "frontier", "sun", "soldiers",
        "battle", "pistol", "gunfire",
    ]),
    ("the_passenger", [
        "physics", "theory", "mathematics", "quantum", "memory", "dream",
        "modern", "technical", "city", "bar", "money", "consciousness",
        "reflection", "grief", "sister", "hospital", "car", "thinking",
    ]),
]

# Baseline weight applied to every book before keyword scoring
_BIAS_FLOOR = 0.10


# ---------------------------------------------------------------------------
# Mode inference
# ---------------------------------------------------------------------------

# Hard override triggers for dialogue — any match forces mode to "dialogue"
_DIALOGUE_HARD_TRIGGERS = frozenset([
    "dialogue", "conversation", "talk", "argue", "arguing", "speaking",
    "say", "said", "speak", "exchange", "talks",
])

# Dialogue intent phrases — broader than hard triggers; catches implicit dialogue
# prompts like "where are we going" or "two people in a room".
# Single-token items are checked by substring; multi-token items checked as phrases.
_DIALOGUE_INTENT_PHRASES = (
    "two people talking", "two people arguing", "people talking",
    "two men talking", "two women talking",
    "arguing quietly", "he said", "she said", "they said",
    "told him", "told her", "told them",
    "where are we going", "where are we", "what are we going to do",
    "what do we do", "what now", "what's going to happen",
    "asked him", "asked her", "replied", "asked me",
)
_DIALOGUE_INTENT_TOKENS = frozenset([
    "exchange", "speaking", "asked", "replied", "conversation",
    "talking", "arguing", "dialogue",
])


def infer_dialogue_from_scene(prompt: str) -> bool:
    """
    Scene-based dialogue inference: detects implicit human conversational scenes
    that have no explicit dialogue markers but strongly imply spoken exchange.

    Fires when the prompt contains signals from all three scene dimensions:
      HUMAN  — physical shared space (room, bed, table, window, door, chair)
      TENSION — interpersonal or situational pressure (money, leaving, nothing, last, tight)
      STATIC  — temporal/atmospheric grounding (night, late, dark, silence, waiting)

    Example: "cheap room late night money leaving town"
      HUMAN: room ✓  TENSION: money, leaving ✓  STATIC: night, late ✓  → True
    """
    _SCENE_HUMAN   = frozenset(["room", "bed", "table", "window", "door", "chair", "wall", "floor"])
    _SCENE_TENSION = frozenset(["money", "leave", "leaving", "left", "last", "nothing",
                                 "tight", "gone", "broke", "debt", "rent", "owe", "leaving"])
    _SCENE_STATIC  = frozenset(["night", "late", "dark", "darkness", "silence", "waiting",
                                 "quiet", "still", "morning", "dawn"])

    tokens = set(re.findall(r"\b\w+\b", prompt.lower()))
    return bool(tokens & _SCENE_HUMAN and tokens & _SCENE_TENSION and tokens & _SCENE_STATIC)


def infer_dialogue_intent(prompt: str) -> bool:
    """
    Lightweight heuristic: does this prompt implicitly request dialogue?

    Catches phrase-level and token-level signals that `infer_mode` may miss
    when the classifier settles on 'descriptive' or 'narrative'.

    Not a replacement for the classifier — an override layer only.
    Returns True when dialogue intent is detected.
    """
    lower = prompt.lower()
    if any(phrase in lower for phrase in _DIALOGUE_INTENT_PHRASES):
        return True
    tokens = set(re.findall(r"\b\w+\b", lower))
    return bool(tokens & _DIALOGUE_INTENT_TOKENS)

_MODE_SIGNALS: dict[str, set[str]] = {
    "dialogue": {
        "said", "spoke", "asks", "asked", "answered", "replied", "told",
        "whispered", "shouted", "conversation", "talk", "speaks", "murmur",
        "muttered", "says",
    },
    "action": {
        "fight", "chase", "run", "attack", "shoot", "kill", "cross", "climb",
        "flee", "fall", "strike", "move", "carry", "ride", "advance", "retreat",
        "charge", "crossing", "flees", "ran", "jumped", "falls", "pursuit",
    },
    "reflective": {
        "wonder", "think", "thought", "memory", "dream", "remember", "feel",
        "believe", "understand", "meaning", "truth", "know", "knowledge",
        "reflects", "considers", "ponders",
    },
    "descriptive": {
        "landscape", "sky", "mountain", "plain", "valley", "forest", "desert",
        "ocean", "field", "pass", "ridge", "horizon", "expanse", "scene",
        "vista", "frozen", "dark", "night", "dawn", "dusk", "light", "terrain",
    },
}


def infer_mode(prompt: str) -> str:
    """
    Heuristic mode inference from a short prompt string.
    Returns one of: action | reflective | descriptive | dialogue | narrative

    Dialogue is a hard override: any match against _DIALOGUE_HARD_TRIGGERS
    forces mode = "dialogue" regardless of other signals.
    """
    tokens = set(re.findall(r"\b\w+\b", prompt.lower()))

    # Hard override — dialogue takes priority
    if tokens & _DIALOGUE_HARD_TRIGGERS:
        return "dialogue"

    scores = {mode: len(tokens & signals) for mode, signals in _MODE_SIGNALS.items()}
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "narrative"


# ---------------------------------------------------------------------------
# Book bias inference
# ---------------------------------------------------------------------------

def _epub_stem_to_key(filename: str) -> str:
    """Normalise an EPUB filename to a canonical book key.

    e.g. "X_TheRoad.epub" → "the_road"
         "V_Blood Meridian.epub" → "blood_meridian"
    """
    stem = Path(filename).stem
    stem = re.sub(r"^[IVXLCDMivxlcdm]+_", "", stem)       # strip roman prefix
    stem = re.sub(r"([A-Z])", r" \1", stem)                 # CamelCase → spaces
    stem = re.sub(r"[\s_]+", "_", stem).lower().strip("_")
    return stem


def infer_book_bias(epubs_dir: Path, prompt: str, mode_guess: str) -> dict[str, float]:
    """
    Infer soft book/style weights from prompt keywords.
    Returns {book_key: weight} summing to 1.0.
    """
    book_keys = [_epub_stem_to_key(f.name) for f in sorted(epubs_dir.glob("*.epub"))]
    if not book_keys:
        return {}

    prompt_tokens = set(re.findall(r"\b\w+\b", prompt.lower()))
    raw: dict[str, float] = {k: _BIAS_FLOOR for k in book_keys}

    for book_key, keywords in _BOOK_BIAS_SIGNALS:
        if book_key not in raw:
            continue
        hits = sum(1 for kw in keywords if kw in prompt_tokens)
        raw[book_key] += hits * 0.15

    total = sum(raw.values())
    return {k: round(v / total, 3) for k, v in raw.items()}


# ---------------------------------------------------------------------------
# Structure targets
# ---------------------------------------------------------------------------

def _compute_structure_targets(
    word_target: int,
    distributions: dict,
    mode_guess: str,
    style_profile: dict | None = None,
) -> dict:
    """
    Derive hard structure targets from corpus feature distributions.
    Values are presented to the model as concrete measurable constraints.
    """
    sent_dist = distributions.get("sentence_length", {})
    if not sent_dist:
        return {}

    median = float(sent_dist.get("median", 8.0))
    p25 = float(sent_dist.get("p25", 6.0))
    p75 = float(sent_dist.get("p75", 13.0))

    expected = word_target / max(median, 1.0)
    count_min = max(5, round(expected * 0.75))
    count_max = round(expected * 1.35)

    short_dist = distributions.get("short_sentence_ratio", {})
    short_target = round(float(short_dist.get("median", 0.63)), 2)

    # Long-sentence / accumulative sentence targets — author-derived
    long_ratio = 0.0
    if style_profile:
        long_ratio = float(
            style_profile.get("rhythm", {}).get("long_sentence_ratio", 0.0)
        )
    accumulative_required = long_ratio > 0.05
    long_sentence_min = 1 if accumulative_required else 0

    return {
        "sentence_count_min": count_min,
        "sentence_count_max": count_max,
        "short_sentence_ratio_target": short_target,
        "long_sentence_ratio_max": 0.15,
        "long_sentence_min": long_sentence_min,
        "accumulative_sentence_required": accumulative_required,
        "avg_sentence_length_min": max(3, round(p25)),
        "avg_sentence_length_max": round(p75),
    }


# ---------------------------------------------------------------------------
# Clause dynamics
# ---------------------------------------------------------------------------

def _compute_clause_dynamics(lex_profile: dict) -> dict:
    """
    Derive clause-level control settings from the author's lexicon profile.
    All values are author-specific — not hardcoded for any one author.
    """
    func = lex_profile.get("function_word_profile", {})
    and_rate = float(func.get("and_rate", 0.02))
    semicolon_rate = float(func.get("semicolon_rate", 0.0))

    coordination = (
        "high" if and_rate > 0.04
        else "medium" if and_rate > 0.02
        else "low"
    )
    subordination = (
        "low" if semicolon_rate < 0.01
        else "medium" if semicolon_rate < 0.05
        else "high"
    )

    if coordination == "high":
        accumulation_style = "and_chaining"
    elif subordination == "high":
        accumulation_style = "subordinate_buildup"
    else:
        accumulation_style = "paratactic"

    return {
        "coordination_preference": coordination,
        "subordination_preference": subordination,
        "fragment_tolerance": "medium",   # profiled later; medium is a safe default
        "accumulation_style": accumulation_style,
    }


# ---------------------------------------------------------------------------
# Lexical anchors
# ---------------------------------------------------------------------------

def _select_lexical_anchors(
    lex_profile: dict,
    mode_guess: str,
) -> list[str]:
    """
    Select 7–10 author-specific lexical anchors for soft injection.
    Nouns dominant; verbs physical; adjectives sparse.
    """
    nouns = [w["term"] for w in lex_profile.get("signature_nouns", [])[:5]]
    verbs = [w["term"] for w in lex_profile.get("signature_verbs", [])[:4]]
    adjs = [w["term"] for w in lex_profile.get("signature_adjectives", [])[:2]]
    return nouns + verbs + adjs


# ---------------------------------------------------------------------------
# Main packet builder
# ---------------------------------------------------------------------------

def build_generation_packet(
    author_folder: Path,
    prompt: str,
    word_target: int,
    n_exemplars: int = 3,
    mode_override: str | None = None,
) -> dict:
    """
    Assemble a structured generation packet from the author pack.

    All four style layers are combined here. The packet is the sole input
    to generation_service._build_generation_prompt().
    """
    profile_dir = author_folder / "profile"
    processed_dir = author_folder / "processed"
    epubs_dir = author_folder / "epubs"
    writer_id = author_folder.name

    # --- Load author pack ---
    style_profile = json.loads((profile_dir / "style_profile.json").read_text())
    lex_profile = json.loads((profile_dir / "lexicon_profile.json").read_text())

    distributions: dict = {}
    dist_path = profile_dir / "feature_distributions.json"
    if dist_path.exists():
        distributions = json.loads(dist_path.read_text())

    llm_data: dict = {}
    llm_path = profile_dir / "llm_abstractions.json"
    if llm_path.exists():
        llm_data = json.loads(llm_path.read_text())

    style_rules: dict = {}
    rules_path = profile_dir / "style_rules.json"
    if rules_path.exists():
        style_rules = json.loads(rules_path.read_text())

    # --- Layer C: mode inference + override resolution ---
    classifier_mode = infer_mode(prompt)
    force_dialogue_intent = (
        infer_dialogue_intent(prompt)
        or infer_dialogue_from_scene(prompt)
    )

    # Resolution hierarchy: CLI override > intent/scene inference > classifier
    if mode_override:
        mode_guess = mode_override
    elif force_dialogue_intent:
        mode_guess = "dialogue"
    else:
        mode_guess = classifier_mode

    # --- Layer B: book bias inference ---
    book_bias = infer_book_bias(epubs_dir, prompt, mode_guess)

    # --- Layer A: author invariants ---
    # Start from LLM global_tendencies; fall back to corpus tendencies
    style_traits: list[str] = list(llm_data.get("global_tendencies", []))
    if not style_traits:
        style_traits = list(style_profile.get("tendencies", []))
    # Supplement with prefer_rules from style_rules (compact corpus-derived)
    for rule in style_rules.get("prefer_rules", [])[:4]:
        if rule not in style_traits:
            style_traits.append(rule)

    # --- Lexical tendencies ---
    lexical_tendencies: list[str] = list(llm_data.get("signature_lexical_habits", []))
    sig_nouns = [w["term"] for w in lex_profile.get("signature_nouns", [])[:10]]
    if sig_nouns:
        lexical_tendencies.append(
            f"High-frequency nouns in corpus: {', '.join(sig_nouns)}"
        )

    # --- Mode notes ---
    mode_notes: list[str] = llm_data.get("mode_notes", {}).get(mode_guess, [])
    if not mode_notes and mode_guess == "dialogue":
        mode_notes = [
            "No quotation marks for speech — run dialogue directly into the prose.",
            "Lean, sparse speaker attribution.",
            "Terse exchange structure; let silence do work.",
        ]

    # --- Edit transformations and avoidances ---
    edit_transformations: list[str] = llm_data.get("edit_transformations", [])
    avoidances: list[str] = llm_data.get("avoidances", [])
    if not avoidances:
        avoidances = style_rules.get("avoid_rules", [])

    # --- Layer D: exemplar retrieval (prompt text as query) ---
    from .retriever import retrieve_exemplars
    exemplar_path = processed_dir / "exemplar_passages.jsonl"
    retrieved_exemplars: list[dict] = []

    # Dialogue mode: filter retrieval to dialogue-tagged passages only
    retrieval_mode_filter = "dialogue" if mode_guess == "dialogue" else None

    if exemplar_path.exists():
        # Use author corpus median as neutral feature baseline
        rhythm = style_profile.get("rhythm", {})
        default_features = {
            "avg_sentence_length": rhythm.get("avg_sentence_length", 8.0),
            "short_sentence_ratio": rhythm.get("short_sentence_ratio", 0.6),
            "phys_verb_ratio": 0.8,
        }
        retrieved_exemplars = retrieve_exemplars(
            user_text=prompt,
            user_features=default_features,
            user_mode=mode_guess,
            exemplar_path=exemplar_path,
            n=n_exemplars,
            mode_filter=retrieval_mode_filter,
        )

    # Dialogue-specific packet fields
    is_dialogue = mode_guess == "dialogue"

    # Structure targets derived from corpus distributions
    structure_targets = _compute_structure_targets(
        word_target, distributions, mode_guess, style_profile
    )

    # Clause dynamics — derived from lexicon profile, author-specific
    clause_dynamics = _compute_clause_dynamics(lex_profile)

    # Lexical anchors — soft injection from corpus signature vocabulary
    lexical_anchors = _select_lexical_anchors(lex_profile, mode_guess)

    return {
        "writer_id": writer_id,
        "word_target": word_target,
        "prompt": prompt,
        "classifier_mode_guess": classifier_mode,
        "force_dialogue_intent": force_dialogue_intent,
        "mode_guess": mode_guess,
        "structure_mode": mode_guess,
        "dialogue_required": is_dialogue,
        "dialogue_ratio_target": 0.6 if is_dialogue else None,
        "book_bias": book_bias,
        "style_traits": style_traits,
        "lexical_tendencies": lexical_tendencies,
        "lexical_anchors": lexical_anchors,
        "mode_notes": mode_notes,
        "edit_transformations": edit_transformations,
        "avoidances": avoidances,
        "retrieved_exemplars": retrieved_exemplars,
        "structure_targets": structure_targets,
        "clause_dynamics": clause_dynamics,
        "postcheck_rules": {
            "max_regenerations": 1,
            "dialogue_ratio_min": 0.6,
            "regenerate_on_drift": ["moderate", "strong"],
        },
        "generation_policy": {
            "fresh_generation": True,
            "preserve_user_text": False,
            "imitation_strength": "medium",
            "preserve_readability": True,
        },
    }
