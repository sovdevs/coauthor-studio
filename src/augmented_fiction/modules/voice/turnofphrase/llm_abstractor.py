"""
Offline LLM-assisted style abstraction using GPT-4o.

Invoked via: uv run python -m augmented_fiction.modules.voice.turnofphrase abstract <author_folder>

Inputs (all from author_folder):
  profile/style_profile.json
  profile/lexicon_profile.json
  profile/feature_distributions.json
  processed/exemplar_passages.jsonl  (up to 10 passages used)
  author_notes/style_notes.txt

Outputs:
  profile/llm_abstractions.json      — structured style abstractions
  profile/llm_abstractions_raw.json  — raw prompt + response for debugging

Caching:
  SHA-256 hash of all inputs is stored in llm_abstractions.json.
  Re-run is skipped unless inputs have changed.

Requires OPENAI_API_KEY in environment or .env file.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(
    style_profile: dict,
    lex_profile: dict,
    distributions: dict,
    exemplars: list[dict],
    notes_text: str,
) -> str:
    rhythm = style_profile.get("rhythm", {})
    lexical = style_profile.get("lexical", {})
    func = lex_profile.get("function_word_profile", {})
    verb_bias = lex_profile.get("verb_bias", {})
    sig_nouns = [w["term"] for w in lex_profile.get("signature_nouns", [])[:20]]
    sig_verbs = [w["term"] for w in lex_profile.get("signature_verbs", [])[:15]]
    sig_adj = [w["term"] for w in lex_profile.get("signature_adjectives", [])[:15]]

    sent_dist = distributions.get("sentence_length", {})
    exemplar_block = "\n\n".join(
        f"[{e.get('mode_guess','?')} | {e['source_file']}]\n{e['text']}"
        for e in exemplars[:10]
    )

    return f"""You are a literary style analyst. Analyze the prose style described below and return a structured JSON abstraction.

## Corpus statistics
- Sentence length: mean={rhythm.get('avg_sentence_length')} words, median={rhythm.get('median_sentence_length')}, p10={sent_dist.get('p10')}, p90={sent_dist.get('p90')}
- Short sentence ratio (≤10 words): {rhythm.get('short_sentence_ratio', 0):.0%}
- Long sentence ratio (≥30 words): {rhythm.get('long_sentence_ratio', 0):.0%}
- Adjective rate: {lexical.get('adj_rate', 0):.1%}
- Adverb rate: {lexical.get('adv_rate', 0):.1%}
- Abstract noun ratio: {lexical.get('abstract_noun_ratio', 0):.1%}
- Concrete noun ratio: {lexical.get('concrete_noun_ratio', 0):.1%}

## Function words & punctuation
- 'and' rate: {func.get('and_rate', 0):.1%} of all tokens
- Semicolons per sentence: {func.get('semicolon_rate', 0):.3f}
- Quotation marks per sentence: {func.get('quote_mark_rate', 0):.3f}
- Commas per sentence: {func.get('comma_rate', 0):.2f}

## Verb profile
- Physical verbs: {verb_bias.get('physical_verbs', {}).get('ratio', 0):.0%} — top: {', '.join(verb_bias.get('physical_verbs', {}).get('top_terms', [])[:10])}
- Cognitive verbs: {verb_bias.get('cognitive_verbs', {}).get('ratio', 0):.0%} — top: {', '.join(verb_bias.get('cognitive_verbs', {}).get('top_terms', [])[:10])}

## Signature vocabulary
- Top nouns: {', '.join(sig_nouns)}
- Top verbs: {', '.join(sig_verbs)}
- Top adjectives: {', '.join(sig_adj)}

## Author notes
{notes_text or '(none provided)'}

## Sample passages
{exemplar_block}

---

Return a JSON object with EXACTLY this schema (no extra keys):

{{
  "global_tendencies": ["<5–8 specific style observations>"],
  "mode_notes": {{
    "action": ["<1–3 observations>"],
    "reflective": ["<1–3 observations>"],
    "descriptive": ["<1–3 observations>"]
  }},
  "edit_transformations": ["<4–6 specific editing instructions for moving toward this style>"],
  "avoidances": ["<4–6 things this writer clearly avoids>"],
  "signature_lexical_habits": ["<3–5 specific word-choice habits>"]
}}

Be specific and literary. Base every observation on the corpus data and passages provided. Do not produce generic writing advice."""


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

def _input_hash(*parts: object) -> str:
    content = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_abstraction(author_folder: Path, model: str = "gpt-4o") -> dict:
    """
    Run (or retrieve from cache) the offline LLM abstraction step.
    Returns the abstractions dict.
    """
    load_dotenv()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENAI_API_KEY not set. Export it or add it to a .env file."
        )

    profile_dir = author_folder / "profile"
    processed_dir = author_folder / "processed"

    # --- Load required inputs ---
    style_profile = json.loads((profile_dir / "style_profile.json").read_text())
    lex_profile = json.loads((profile_dir / "lexicon_profile.json").read_text())
    distributions = json.loads((profile_dir / "feature_distributions.json").read_text())

    exemplars: list[dict] = []
    exemplar_path = processed_dir / "exemplar_passages.jsonl"
    if exemplar_path.exists():
        with exemplar_path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    exemplars.append(json.loads(line))
        exemplars = exemplars[:10]

    notes_text = ""
    notes_path = author_folder / "author_notes" / "style_notes.txt"
    if notes_path.exists():
        notes_text = notes_path.read_text(encoding="utf-8")

    # --- Cache check ---
    cache_hash = _input_hash(style_profile, lex_profile, distributions, exemplars, notes_text)
    cache_path = profile_dir / "llm_abstractions.json"
    if cache_path.exists():
        cached = json.loads(cache_path.read_text())
        if cached.get("_input_hash") == cache_hash:
            print("[turnofphrase] LLM abstraction cache hit — skipping API call.")
            return cached
        print("[turnofphrase] Inputs changed — regenerating LLM abstraction.")

    # --- Build prompt and call GPT-4o ---
    prompt = _build_prompt(style_profile, lex_profile, distributions, exemplars, notes_text)

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    print(f"[turnofphrase] Calling {model} for style abstraction ...")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are a literary style analyst. Return only valid JSON matching the requested schema.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    raw_response = response.choices[0].message.content

    try:
        result = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise ValueError(f"GPT-4o returned invalid JSON: {exc}\n\nRaw: {raw_response[:500]}")

    # Inject metadata
    result["writer_id"] = style_profile.get("writer_id", author_folder.name)
    result["_model"] = model
    result["_input_hash"] = cache_hash

    # --- Save outputs ---
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "llm_abstractions.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    raw_record = {
        "model": model,
        "_input_hash": cache_hash,
        "prompt": prompt,
        "response": raw_response,
    }
    (profile_dir / "llm_abstractions_raw.json").write_text(
        json.dumps(raw_record, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"  → llm_abstractions.json written")
    return result
