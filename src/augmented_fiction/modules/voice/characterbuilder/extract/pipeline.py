"""
Top-level extraction pipeline orchestrator.

Usage (from CLI):
    :cb extract <author_dir>
    :cb extract cormac_mccarthy                        # resolved to modules/voice/turnofphrase/cormac_mccarthy
    :cb extract modules/voice/turnofphrase/cormac_mccarthy
    :cb extract cormac_mccarthy --include-narrator     # also extract per-book narrator profiles

Flow:
    1. Resolve and validate author directory
    2. Ingest passages (processed/ first, EPUB fallback)
    3. LLM candidate detection + interactive user selection
    4. For each selected character:
       a. Build raw evidence file
       b. Synthesize draft profile
       c. Save profile to registry + sidecar file
    5. [optional] Extract one narrator profile per book
    6. Report results
"""
from __future__ import annotations

from pathlib import Path

from .ingest import load_passages
from .candidate import detect_candidates, select_interactively
from .evidence import build_evidence
from .synthesize import synthesize_profile, save_sidecar

_AUTHOR_PKG_ROOT = Path("modules/voice/turnofphrase")


def run_extract(author_dir_arg: str, llm_config, include_narrator: bool = False) -> list[str]:
    """
    Run the full extraction pipeline.

    author_dir_arg may be:
      - a bare slug:        "cormac_mccarthy"
      - a relative path:    "modules/voice/turnofphrase/cormac_mccarthy"
      - an absolute path:   "/absolute/path/..."

    Returns a list of result lines for display.
    """
    from augmented_fiction.modules.voice.characterbuilder.storage import save_character

    author_dir = _resolve_author_dir(author_dir_arg)
    author_name = _infer_author_name(author_dir)

    print(f"\n  Author directory : {author_dir}")
    print(f"  Author name      : {author_name}")

    # ── Step 1: ingest ────────────────────────────────────────────────────────
    print("\n  Loading passages…")
    passages, source_desc = load_passages(author_dir)
    print(f"  Source  : {source_desc}")
    print(f"  Passages: {len(passages):,}")

    # ── Step 2: detect candidates ─────────────────────────────────────────────
    print("\n  Detecting candidate characters (LLM)…")
    candidates = detect_candidates(passages, author_name, llm_config)
    if not candidates:
        return ["  No candidates detected. Nothing extracted."]

    # ── Step 3: interactive selection ─────────────────────────────────────────
    selected = select_interactively(candidates)
    if not selected:
        return ["  No characters selected. Nothing extracted."]

    print(f"\n  Selected: {', '.join(c.name for c in selected)}")

    # ── Step 4: evidence + synthesis per character ────────────────────────────
    results: list[str] = []

    for character in selected:
        print(f"\n  ── {character.name} ──────────────────────────────────────")

        # 4a. Build evidence file
        print("  Building evidence dossier…")
        evidence_path = build_evidence(
            character=character,
            passages=passages,
            author_dir=author_dir,
            author_name=author_name,
            llm_config=llm_config,
        )
        print(f"  Evidence: {evidence_path}")

        # 4b. Synthesize profile
        print("  Synthesising draft profile (LLM)…")
        profile, sidecar = synthesize_profile(
            character=character,
            evidence_path=evidence_path,
            author_dir=author_dir,
            author_name=author_name,
            llm_config=llm_config,
            source_work=_detect_primary_work(character, passages),
        )

        # 4c. Save
        save_character(profile)
        sidecar_path = save_sidecar(sidecar)

        results.append(
            f"  Saved : {profile.display_name}  ({profile.character_id})\n"
            f"          registry → {profile.provenance.registry_path}\n"
            f"          sidecar  → {sidecar_path}\n"
            f"          evidence → {evidence_path}"
        )

        _print_confidence_summary(sidecar)

    # ── Step 5: narrator extraction (optional) ────────────────────────────────
    if include_narrator:
        from .narrator import extract_narrators
        print("\n  ── Narrator extraction ──────────────────────────────────")
        narrator_pairs = extract_narrators(
            passages=passages,
            author_dir=author_dir,
            author_name=author_name,
            llm_config=llm_config,
        )
        for n_profile, n_sidecar in narrator_pairs:
            save_character(n_profile)
            n_sidecar_path = save_sidecar(n_sidecar)
            results.append(
                f"  Saved : {n_profile.display_name}  ({n_profile.character_id})\n"
                f"          registry → {n_profile.provenance.registry_path}\n"
                f"          sidecar  → {n_sidecar_path}"
            )
            _print_confidence_summary(n_sidecar)

    return results


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_author_dir(arg: str) -> Path:
    """Resolve an author dir argument to an existing Path."""
    p = Path(arg)

    # Absolute path — use as-is
    if p.is_absolute():
        if not p.exists():
            raise FileNotFoundError(f"Author directory not found: {p}")
        return p

    # Relative path that already exists
    if p.exists():
        return p

    # Bare slug — look under the turnofphrase package root
    slug_path = _AUTHOR_PKG_ROOT / arg
    if slug_path.exists():
        return slug_path

    raise FileNotFoundError(
        f"Author directory not found: {arg!r}\n"
        f"Tried:\n  {p}\n  {slug_path}"
    )


def _infer_author_name(author_dir: Path) -> str:
    """
    Try to derive a display author name from the directory.

    Looks first for processed/extracted_text.json writer_id,
    then falls back to humanising the directory name slug.
    """
    import json

    extracted_json = author_dir / "processed" / "extracted_text.json"
    if extracted_json.exists():
        try:
            data = json.loads(extracted_json.read_text(encoding="utf-8"))
            writer_id = data.get("writer_id", "")
            if writer_id:
                return _humanise_slug(writer_id)
        except Exception:
            pass

    passages_jsonl = author_dir / "processed" / "passages.jsonl"
    if passages_jsonl.exists():
        try:
            first_line = passages_jsonl.read_text(encoding="utf-8").splitlines()[0]
            data = json.loads(first_line)
            writer_id = data.get("writer_id", "")
            if writer_id:
                return _humanise_slug(writer_id)
        except Exception:
            pass

    return _humanise_slug(author_dir.name)


def _humanise_slug(slug: str) -> str:
    """Turn 'cormac_mccarthy' → 'Cormac McCarthy'."""
    return " ".join(word.capitalize() for word in slug.replace("-", "_").split("_"))


def _detect_primary_work(character, passages) -> str:
    """
    Return the source file (book) where the character has the most mentions.
    Used as source_work on the profile.
    """
    import re
    all_terms = [character.name] + character.aliases
    patterns = [re.compile(re.escape(t), re.IGNORECASE) for t in all_terms if t]

    counts: dict[str, int] = {}
    for p in passages:
        if any(pat.search(p.text) for pat in patterns):
            counts[p.source_file] = counts.get(p.source_file, 0) + 1

    if not counts:
        return ""

    # Return the source_file with the highest count — strip path/extension
    primary = max(counts, key=counts.__getitem__)
    return Path(primary).stem if primary else ""


def _print_confidence_summary(sidecar) -> None:
    if not sidecar.field_confidence:
        return
    print("\n  Field confidence:")
    for field, fc in sidecar.field_confidence.items():
        bar = {"high": "▓▓▓", "medium": "▓▓░", "low": "▓░░", "none": "░░░"}.get(fc.confidence, "░░░")
        note = f"  {fc.note}" if fc.note else ""
        print(f"    {bar}  {field:<40} {fc.confidence}{note}")
