"""
TurnOfPhrase service — orchestrates the full pipeline.

Sub-commands:
  run      — deterministic corpus/profile build (all EPUBs by default)
  analyze  — compare user text against author profile + retrieve exemplars
  abstract — offline LLM abstraction step (separate, optional, costs money)

Usage:
  uv run python -m augmented_fiction.modules.voice.turnofphrase run <author_folder>
  uv run python -m augmented_fiction.modules.voice.turnofphrase run <author_folder> --epub X_TheRoad.epub
  uv run python -m augmented_fiction.modules.voice.turnofphrase analyze <author_folder> "text"
  uv run python -m augmented_fiction.modules.voice.turnofphrase analyze <author_folder> @file.txt
  uv run python -m augmented_fiction.modules.voice.turnofphrase abstract <author_folder>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .epub_loader import extract_and_save, extract_all_and_save
from .passage_segmenter import segment
from .style_profiler import profile_from_passages
from .lexicon_profiler import (
    lexicon_profile_from_passages,
    feature_distributions_from_passages,
)
from .mode_profiler import build_mode_profiles
from .dialogue_profiler import build_dialogue_profile
from .passage_searcher import (
    build_passage_search_index,
    search_passages, search_passages_by_mode, search_structural_exemplars,
    search_quotes, search_exemplars, search_exemplars_by_mode,
)
from .exemplar_selector import select_exemplars
from .phrase_bundle_builder import build_phrase_bundles
from .style_rules_builder import build_style_rules
from .style_comparator import analyze_against_writer_style
from .generation_service import generate_passage, save_generation

_DEFAULT_EPUB = "X_TheRoad.epub"


# ---------------------------------------------------------------------------
# run_pipeline
# ---------------------------------------------------------------------------

def run_pipeline(author_folder: Path, epub_filename: str | None = None) -> dict:
    """
    Build the full author pack for one author folder.

    epub_filename=None (default) → process all EPUBs in epubs/
    epub_filename="X_TheRoad.epub" → single-book mode
    """
    writer_id = author_folder.name
    processed_dir = author_folder / "processed"
    profile_dir = author_folder / "profile"
    epubs_dir = author_folder / "epubs"

    # --- Extraction ---
    if epub_filename:
        epub_path = epubs_dir / epub_filename
        if not epub_path.exists():
            raise FileNotFoundError(f"EPUB not found: {epub_path}")
        print(f"[turnofphrase] Extracting {epub_filename} (single-book mode) ...")
        extracted = extract_and_save(epub_path, processed_dir, writer_id)
        print(f"  → {extracted['paragraph_count']} paragraphs")
    else:
        epub_files = sorted(epubs_dir.glob("*.epub"))
        if not epub_files:
            raise FileNotFoundError(f"No EPUB files found in {epubs_dir}")
        print(f"[turnofphrase] Extracting {len(epub_files)} EPUB(s) ...")
        for f in epub_files:
            print(f"    {f.name}")
        extracted = extract_all_and_save(epubs_dir, processed_dir, writer_id)
        print(f"  → {extracted['paragraph_count']} paragraphs from {len(extracted['source_files'])} books")

    # --- Corpus boundaries (optional) ---
    boundaries = None
    boundaries_path = author_folder / "config" / "corpus_boundaries.json"
    if boundaries_path.exists():
        with boundaries_path.open(encoding="utf-8") as _f:
            boundaries = json.load(_f)
        print(f"[turnofphrase] Corpus boundaries loaded ({len(boundaries)} source(s) configured)")

    # --- Segmentation ---
    print("[turnofphrase] Segmenting passages ...")
    passages = segment(extracted, processed_dir, boundaries=boundaries)
    print(f"  → {len(passages)} passages")

    # --- Style profile ---
    print("[turnofphrase] Building style profile ...")
    source_label = epub_filename or f"{len(extracted['source_files'])} books"
    style_profile = profile_from_passages(passages, writer_id, source_label, profile_dir)
    # Patch source_files into profile for downstream use
    style_profile["source_files"] = extracted["source_files"]
    print(f"  → avg sentence {style_profile['rhythm']['avg_sentence_length']} words, "
          f"short ratio {style_profile['rhythm']['short_sentence_ratio']:.0%}")
    print("  → Tendencies:")
    for t in style_profile.get("tendencies", []):
        print(f"       • {t}")

    # --- Lexicon profile ---
    print("[turnofphrase] Building lexicon profile ...")
    lex_profile = lexicon_profile_from_passages(
        passages, writer_id, source_label, author_folder, profile_dir
    )
    print(f"  → {len(lex_profile['archaic_or_literary_terms'])} archaic/literary terms")
    print("  → Derived rules:")
    for r in lex_profile.get("derived_rules", []):
        print(f"       • {r}")

    # --- Feature distributions ---
    print("[turnofphrase] Building feature distributions ...")
    distributions = feature_distributions_from_passages(passages, profile_dir)
    sd = distributions.get("sentence_length", {})
    print(f"  → Sentence length: p10={sd.get('p10')} p25={sd.get('p25')} "
          f"median={sd.get('median')} p75={sd.get('p75')} p90={sd.get('p90')}")

    # --- Mode profiles ---
    print("[turnofphrase] Assigning passage modes ...")
    mode_labeled, mode_profiles = build_mode_profiles(
        passages, writer_id, processed_dir, profile_dir
    )
    for mode, stats in mode_profiles.get("modes", {}).items():
        print(f"  → {mode}: {stats.get('passage_count', 0)} passages")

    # --- Passage search index ---
    print("[turnofphrase] Building passage search index ...")
    index_path = build_passage_search_index(mode_labeled, processed_dir)
    print(f"  → {index_path.name} written ({len(mode_labeled)} passages)")

    # --- Dialogue profile ---
    print("[turnofphrase] Building dialogue profile ...")
    dlg_profile = build_dialogue_profile(mode_labeled, writer_id, profile_dir)
    print(f"  → {dlg_profile.get('dialogue_passage_count', 0)} dialogue / "
          f"{dlg_profile.get('mixed_passage_count', 0)} mixed passages")
    if dlg_profile.get("dialogue_passage_count", 0) > 0:
        print(f"  → avg sentence length: {dlg_profile.get('avg_sentence_length')} words, "
              f"attribution rate: {dlg_profile.get('attribution_rate')}")

    # --- Exemplar selection ---
    print("[turnofphrase] Selecting exemplar passages ...")
    exemplars = select_exemplars(mode_labeled, processed_dir)
    print(f"  → {len(exemplars)} exemplars selected")
    from collections import Counter
    mode_dist = Counter(e["mode_guess"] for e in exemplars)
    for mode, count in sorted(mode_dist.items()):
        print(f"       {mode}: {count}")

    # --- Phrase bundles ---
    print("[turnofphrase] Extracting phrase bundles ...")
    build_phrase_bundles(style_profile, profile_dir)
    print(f"  → phrase_bundles.json written")

    # --- Style rules ---
    print("[turnofphrase] Building style rules ...")
    style_rules = build_style_rules(writer_id, style_profile, lex_profile, profile_dir)
    print(f"  → {len(style_rules['prefer_rules'])} prefer / "
          f"{len(style_rules['avoid_rules'])} avoid / "
          f"{len(style_rules['transformation_hints'])} transformation hints")

    print("\n[turnofphrase] Author pack complete.")
    print(f"  Profile dir: {profile_dir}")
    print(f"  Artifacts: style_profile.json, lexicon_profile.json, "
          f"feature_distributions.json, mode_profiles.json, "
          f"dialogue_profile.json, phrase_bundles.json, style_rules.json")
    print(f"  Processed: passages.jsonl, passage_modes.jsonl, exemplar_passages.jsonl, passage_search_index.jsonl")
    print("\n  Run LLM abstraction separately (needs OPENAI_API_KEY):")
    print(f"  uv run python -m augmented_fiction.modules.voice.turnofphrase "
          f"abstract {author_folder}")

    return style_profile


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------

def analyze(user_text: str, author_folder: Path, n_exemplars: int = 5) -> dict:
    """
    Compare user_text against the author profile and retrieve exemplars.
    Requires run_pipeline to have been run first.
    """
    profile_path = author_folder / "profile" / "style_profile.json"
    if not profile_path.exists():
        raise FileNotFoundError(
            f"No profile found at {profile_path}. Run the pipeline first."
        )
    exemplar_path = author_folder / "processed" / "exemplar_passages.jsonl"
    writer_id = author_folder.name
    return analyze_against_writer_style(
        user_text, writer_id, profile_path,
        exemplar_path=exemplar_path if exemplar_path.exists() else None,
        n_exemplars=n_exemplars,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="TurnOfPhrase — style profiler, comparator, and retrieval engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # run
    run_p = sub.add_parser("run", help="Build author pack from EPUB(s)")
    run_p.add_argument("author_folder", type=Path,
                       help="Path to author folder (e.g. modules/voice/turnofphrase/cormac_mccarthy)")
    run_p.add_argument("--epub", default=None,
                       help="Process a single EPUB only (default: all EPUBs in epubs/)")

    # analyze
    analyze_p = sub.add_parser("analyze", help="Analyze user text against writer profile")
    analyze_p.add_argument("author_folder", type=Path)
    analyze_p.add_argument("text", help="Text to analyze, or @path/to/file.txt")
    analyze_p.add_argument("--exemplars", type=int, default=5,
                           help="Number of exemplar passages to retrieve (default: 5)")

    # search
    search_p = sub.add_parser("search", help="Search passages by query, mode, or structure")
    search_p.add_argument("author_folder", type=Path)
    search_p.add_argument("query", nargs="?", default=None,
                          help="Text query (omit for structural search)")
    search_p.add_argument("--kind", choices=["quote", "exemplar"], default="quote",
                          help="Retrieval mode: quote (default) or exemplar")
    search_p.add_argument("--context", type=int, default=0, choices=[0, 1],
                          help="Quote mode: 0=best sentence only, 1=include neighbor (default: 0)")
    search_p.add_argument("--mode", default=None,
                          help="Filter by mode: action|reflective|descriptive|narrative|dialogue")
    search_p.add_argument("--sentence-min", type=float, default=None,
                          help="Min average sentence length (structural filter)")
    search_p.add_argument("--sentence-max", type=float, default=None,
                          help="Max average sentence length (structural filter)")
    search_p.add_argument("--dialogue-heavy", action="store_true",
                          help="Prefer dialogue-rich passages (structural search)")
    search_p.add_argument("--top", type=int, default=5,
                          help="Number of results (default: 5)")

    # generate
    gen_p = sub.add_parser("generate", help="Generate a new passage guided by the author pack")
    gen_p.add_argument("author_folder", type=Path,
                       help="Path to author folder (e.g. modules/voice/turnofphrase/cormac_mccarthy)")
    gen_p.add_argument("prompt", help="Content prompt for generation (what the passage is about)")
    gen_p.add_argument("--words", type=int, default=180,
                       help="Target word count (default: 180)")
    gen_p.add_argument("--model", default="gpt-4o",
                       help="OpenAI model to use (default: gpt-4o)")
    gen_p.add_argument("--exemplars", type=int, default=3,
                       help="Exemplar passages to retrieve (default: 3)")
    gen_p.add_argument("--mode",
                       choices=["dialogue", "action", "reflective", "descriptive", "narrative"],
                       default=None,
                       help="Override mode classifier (dialogue|action|reflective|descriptive|narrative)")
    gen_p.add_argument("--save", action="store_true",
                       help="Append generation record to generated/generations.jsonl")
    gen_p.add_argument("--rewrite", action="store_true",
                       help="Run a second-pass dialogue rewrite (dialogue mode only)")
    gen_p.add_argument("--debug", action="store_true",
                       help="Print full generation packet and prompt")

    # abstract
    abstract_p = sub.add_parser("abstract",
                                 help="Offline LLM abstraction step (requires OPENAI_API_KEY)")
    abstract_p.add_argument("author_folder", type=Path)
    abstract_p.add_argument("--model", default="gpt-4o",
                             help="OpenAI model to use (default: gpt-4o)")

    args = parser.parse_args()

    if args.command == "search":
        import json as _json
        folder = args.author_folder.resolve()
        sentence_band = None
        if args.sentence_min is not None or args.sentence_max is not None:
            sentence_band = (args.sentence_min or 0.0, args.sentence_max or 999.0)

        if sentence_band or args.dialogue_heavy or (not args.query):
            # Structural search — kind flag not applicable here
            results = search_structural_exemplars(
                folder,
                mode=args.mode,
                sentence_band=sentence_band,
                dialogue_heavy=args.dialogue_heavy,
                top_k=args.top,
            )
            for i, r in enumerate(results, 1):
                print(f"\n[{i}] {r['source_file']} | {r['mode_guess']} | "
                      f"avg {r['avg_sentence_length']} words/sent | "
                      f"{r['short_sentence_ratio']:.0%} short")
                print(r["text"])

        elif args.kind == "exemplar":
            if args.mode:
                results = search_exemplars_by_mode(args.query, folder, args.mode, args.top)
            else:
                results = search_exemplars(args.query, folder, args.top)
            for i, r in enumerate(results, 1):
                print(f"\n[{i}] {r['source_file']} | {r['mode_guess']} | "
                      f"{r['sentence_count']} sents | "
                      f"avg {r['avg_sentence_length']} words/sent | "
                      f"{r['short_sentence_ratio']:.0%} short")
                print(r["text"])

        else:
            # Default: quote mode
            results = search_quotes(
                args.query, folder,
                top_k=args.top,
                context=args.context,
            )
            for i, r in enumerate(results, 1):
                terms = ", ".join(r.get("match_terms", []))
                print(f"\n[{i}] {r['source_file']} | {r['mode']} | "
                      f"{r['sentence_count']} sents | matched: {terms}")
                print(r["text"])

    elif args.command == "generate":
        import json as _json
        result = generate_passage(
            author_folder=args.author_folder.resolve(),
            prompt=args.prompt,
            word_target=args.words,
            model=args.model,
            n_exemplars=args.exemplars,
            rewrite=args.rewrite,
            mode_override=args.mode,
        )
        print("\n" + result["generated_text"])
        if args.save:
            log_path = save_generation(result, args.author_folder.resolve())
            print(f"\n[turnofphrase] Saved → {log_path}")
        if args.debug:
            pkt = result["_generation_packet"]
            print("\n--- mode resolution ---")
            print(_json.dumps({
                "classifier_mode_guess": pkt.get("classifier_mode_guess"),
                "force_dialogue_intent": pkt.get("force_dialogue_intent"),
                "resolved_mode": pkt.get("mode_guess"),
                "rewrite_applied": result.get("rewrite_applied", False),
            }, indent=2))
            if result.get("rewrite_applied"):
                print("\n--- draft (pre-rewrite) ---")
                print(result["_draft"])
                print("\n--- rewrite applied: true ---")
            print("\n--- generation packet ---")
            print(_json.dumps(pkt, indent=2, ensure_ascii=False))
            print("\n--- prompt sent ---")
            print(result["_prompt"])

    elif args.command == "run":
        run_pipeline(args.author_folder.resolve(), epub_filename=args.epub)

    elif args.command == "analyze":
        text = args.text
        if text.startswith("@"):
            text = Path(text[1:]).read_text(encoding="utf-8")
        result = analyze(text, args.author_folder.resolve(), n_exemplars=args.exemplars)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "abstract":
        from .llm_abstractor import run_abstraction
        result = run_abstraction(args.author_folder.resolve(), model=args.model)
        # Print just the non-metadata fields
        display = {k: v for k, v in result.items() if not k.startswith("_")}
        print(json.dumps(display, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
