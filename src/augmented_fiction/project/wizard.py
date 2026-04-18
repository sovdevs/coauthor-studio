import json
import re
from datetime import datetime, timezone
from pathlib import Path

import typer

from augmented_fiction.config.loader import save_config
from augmented_fiction.config.schema import (
    CharacterConsistencyModule,
    CharacterConsistencySettings,
    CitationSuggestionModule,
    CitationSuggestionSettings,
    ClaimGroundingModule,
    ClaimGroundingSettings,
    DocumentSection,
    InterfaceSection,
    KnowledgeSourcesSection,
    MatchStyleModule,
    MatchStyleSettings,
    ModeSection,
    ModeType,
    ModulesSection,
    PoliciesSection,
    ProjectConfig,
    ProjectSection,
    TranslateModule,
    TranslateSettings,
    WorldRuleCheckModule,
    WorldRuleCheckSettings,
)
from augmented_fiction.project.store import PROJECTS_DIR, init_project_folders


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def run_wizard() -> Path:
    typer.echo("\n=== New Project Setup ===\n")

    title = typer.prompt("Project title")
    project_id = typer.prompt("Project ID", default=_slugify(title))
    description = typer.prompt("Description", default="")
    author = typer.prompt("Author", default="user")

    mode_raw = typer.prompt("Mode [fiction/academic]", default="fiction")
    mode_type = ModeType.academic if mode_raw.strip().lower() == "academic" else ModeType.fiction
    language = typer.prompt("Writing language (e.g. en, de, fr)", default="en")
    n_sentences = int(typer.prompt("How many finalized sentences to show?", default="5"))

    typer.echo("\n--- Module selection ---")
    enable_translate = typer.confirm("Enable translation module?", default=False)
    enable_style = typer.confirm("Enable style matching module?", default=False)
    enable_chars = typer.confirm("Enable character consistency module?", default=False)
    enable_rules = typer.confirm("Enable world rule checking module?", default=False)
    enable_grounding = typer.confirm("Enable academic grounding module?", default=False)
    enable_citation = typer.confirm("Enable citation suggestion module?", default=False)

    # Module-specific nested questions
    translate_settings = TranslateSettings()
    if enable_translate:
        typer.echo("\n--- Translation settings ---")
        translate_settings.source_language = typer.prompt("Source language (or 'auto')", default="auto")
        translate_settings.target_language = typer.prompt("Target language", default="en")

    style_settings = MatchStyleSettings()
    if enable_style:
        typer.echo("\n--- Style matching settings ---")
        style_settings.author_name = typer.prompt("Author name to match style of")
        style_settings.max_style_matches = int(typer.prompt("Max style matches", default="3"))

    char_settings = CharacterConsistencySettings()
    if enable_chars:
        typer.echo("\n--- Character consistency settings ---")
        char_settings.strictness = typer.prompt("Strictness [low/medium/high]", default="medium")

    rule_settings = WorldRuleCheckSettings()
    if enable_rules:
        typer.echo("\n--- World rule check settings ---")
        rule_settings.strictness = typer.prompt("Strictness [low/medium/high]", default="medium")

    grounding_settings = ClaimGroundingSettings()
    if enable_grounding:
        typer.echo("\n--- Academic grounding settings ---")
        grounding_settings.minimum_evidence_count = int(
            typer.prompt("Minimum evidence count", default="1")
        )

    citation_settings = CitationSuggestionSettings()
    if enable_citation:
        typer.echo("\n--- Citation settings ---")
        citation_settings.citation_style = typer.prompt(
            "Citation style [apa/mla/chicago]", default="apa"
        )

    # Build and save config
    config = ProjectConfig(
        project=ProjectSection(
            project_id=project_id,
            title=title,
            description=description,
            created_at=datetime.now(timezone.utc),
            author=author,
        ),
        mode=ModeSection(type=mode_type, language=language),
        interface=InterfaceSection(last_finalized_sentence_count=n_sentences),
        document=DocumentSection(),
        modules=ModulesSection(
            translate=TranslateModule(enabled=enable_translate, settings=translate_settings),
            match_style_of_author=MatchStyleModule(enabled=enable_style, settings=style_settings),
            character_consistency=CharacterConsistencyModule(enabled=enable_chars, settings=char_settings),
            world_rule_check=WorldRuleCheckModule(enabled=enable_rules, settings=rule_settings),
            claim_grounding=ClaimGroundingModule(enabled=enable_grounding, settings=grounding_settings),
            citation_suggestion=CitationSuggestionModule(enabled=enable_citation, settings=citation_settings),
        ),
        knowledge_sources=KnowledgeSourcesSection(),
        policies=PoliciesSection(),
    )

    project_path = PROJECTS_DIR / project_id
    if project_path.exists():
        typer.confirm(
            f"Project '{project_id}' already exists. Overwrite config?", abort=True
        )

    project_path.mkdir(parents=True, exist_ok=True)
    init_project_folders(project_path)
    save_config(config, project_path)

    # Stub supporting files (only if not already present)
    _stub(project_path / "draft.md", f"# {title}\n")
    _stub(project_path / "sentence_history.jsonl", "")
    _stub(
        project_path / "project_meta.json",
        json.dumps(
            {"status": "active", "current_chapter": 1, "current_section": 1, "notes": ""},
            indent=2,
        ),
    )
    _stub(project_path / "knowledge" / "characters.json", '{"characters": []}')
    _stub(project_path / "knowledge" / "glossary.json", '{"terms": []}')
    _stub(project_path / "knowledge" / "papers.json", '{"papers": []}')
    _stub(project_path / "knowledge" / "RULES.md", "# Project Rules\n\nAdd project rules here.\n")

    typer.echo(f"\nProject '{title}' created at {project_path}")
    return project_path


def _stub(path: Path, content: str) -> None:
    if not path.exists():
        path.write_text(content, encoding="utf-8")
