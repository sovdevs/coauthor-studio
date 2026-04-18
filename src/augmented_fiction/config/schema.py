from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ModeType(str, Enum):
    fiction = "fiction"
    academic = "academic"


# ── Top-level sections ─────────────────────────────────────────────────────────

class ProjectSection(BaseModel):
    project_id: str
    title: str
    description: str = ""
    created_at: datetime
    author: str = "user"


class ModeSection(BaseModel):
    type: ModeType
    subtype: Optional[str] = None
    language: str = "en"


class LLMConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    temperature: float = 0.2
    api_key_env: str = "OPENAI_API_KEY"
    tool_mode: str = "enabled"


class LexicalBackendConfig(BaseModel):
    """Config for one lexical tool (dictionary or thesaurus).

    paths: ordered list of JSON files to try on lookup.
           First file that contains the word wins.
           All paths are relative to the repo root.
    """
    type: str = "file"       # "file" | "local_llm" — future
    paths: list[str] = Field(default_factory=list)


class LexicalBackendsSection(BaseModel):
    dictionary: LexicalBackendConfig = Field(
        default_factory=lambda: LexicalBackendConfig(
            paths=[
                "resources/dictionary/dictionary_compact.json",
                "resources/dictionary/wiktionary-en.json",
            ]
        )
    )
    thesaurus: LexicalBackendConfig = Field(
        default_factory=lambda: LexicalBackendConfig(
            paths=["resources/thesaurus/moby.json"]
        )
    )


class ChaptersSection(BaseModel):
    enabled: bool = False
    no_chapters: bool = True
    chapters_dir: str = "fiction/chapters/"
    default_current_chapter: str = "chapter_001"
    allow_chapter_switching: bool = True


class InterfaceSection(BaseModel):
    # Segment display
    show_last_finalized_segments: bool = True
    last_finalized_segment_count: int = 5
    allow_manual_override: bool = True
    show_module_warnings: bool = True
    show_module_suggestions: bool = True
    show_current_chapter: bool = True
    # Typewriter / manuscript input model
    submit_token: str = ";;"
    manuscript_view_enabled: bool = True
    manuscript_line_spacing: str = "double"   # "single" | "double"
    typewriter_theme: bool = True
    typewriter_sounds: bool = False           # reserved — not yet implemented


class DocumentSection(BaseModel):
    draft_file: str = "draft.md"
    history_file: str = "sentence_history.jsonl"
    export_format_defaults: list[str] = Field(default_factory=lambda: ["md", "txt", "docx"])


# ── Per-module settings ────────────────────────────────────────────────────────

class DictionarySettings(BaseModel):
    suggest_on_input: bool = True
    allow_cli_search: bool = True


class ThesaurusSettings(BaseModel):
    suggest_on_input: bool = True
    allow_cli_search: bool = True
    max_synonym_groups: int = 5


class TranslateSettings(BaseModel):
    source_language: str = "auto"
    target_language: str = "en"
    style_reference_mode: Optional[str] = None
    style_reference_id: Optional[str] = None
    translation_priority: str = "meaning_first"


class MatchStyleSettings(BaseModel):
    author_name: Optional[str] = None
    style_corpus_dir: str = "stores/style_corpus/"
    max_style_matches: int = 3


class CharacterConsistencySettings(BaseModel):
    characters_file: str = "knowledge/characters.json"
    strictness: str = "medium"


class WorldRuleCheckSettings(BaseModel):
    rules_file: str = "knowledge/RULES.md"
    strictness: str = "medium"


class ClaimGroundingSettings(BaseModel):
    papers_file: str = "knowledge/papers.json"
    minimum_evidence_count: int = 1
    allow_unsubstantiated_finalize: bool = True


class CitationSuggestionSettings(BaseModel):
    papers_file: str = "knowledge/papers.json"
    citation_style: str = "apa"


# ── Module wrappers (uniform pattern: enabled / order / settings) ──────────────

class DictionaryModule(BaseModel):
    enabled: bool = False
    order: int = 1
    settings: DictionarySettings = Field(default_factory=DictionarySettings)


class ThesaurusModule(BaseModel):
    enabled: bool = False
    order: int = 2
    settings: ThesaurusSettings = Field(default_factory=ThesaurusSettings)


class TranslateModule(BaseModel):
    enabled: bool = False
    order: int = 3
    settings: TranslateSettings = Field(default_factory=TranslateSettings)


class MatchStyleModule(BaseModel):
    enabled: bool = False
    order: int = 4
    settings: MatchStyleSettings = Field(default_factory=MatchStyleSettings)


class CharacterConsistencyModule(BaseModel):
    enabled: bool = False
    order: int = 5
    settings: CharacterConsistencySettings = Field(default_factory=CharacterConsistencySettings)


class WorldRuleCheckModule(BaseModel):
    enabled: bool = False
    order: int = 6
    settings: WorldRuleCheckSettings = Field(default_factory=WorldRuleCheckSettings)


class ClaimGroundingModule(BaseModel):
    enabled: bool = False
    order: int = 7
    settings: ClaimGroundingSettings = Field(default_factory=ClaimGroundingSettings)


class CitationSuggestionModule(BaseModel):
    enabled: bool = False
    order: int = 8
    settings: CitationSuggestionSettings = Field(default_factory=CitationSuggestionSettings)


class ModulesSection(BaseModel):
    dictionary: DictionaryModule = Field(default_factory=DictionaryModule)
    thesaurus: ThesaurusModule = Field(default_factory=ThesaurusModule)
    translate: TranslateModule = Field(default_factory=TranslateModule)
    match_style_of_author: MatchStyleModule = Field(default_factory=MatchStyleModule)
    character_consistency: CharacterConsistencyModule = Field(default_factory=CharacterConsistencyModule)
    world_rule_check: WorldRuleCheckModule = Field(default_factory=WorldRuleCheckModule)
    claim_grounding: ClaimGroundingModule = Field(default_factory=ClaimGroundingModule)
    citation_suggestion: CitationSuggestionModule = Field(default_factory=CitationSuggestionModule)

    def active_modules(self) -> list[str]:
        """Return names of enabled modules sorted by order."""
        all_modules = {
            "dictionary": self.dictionary,
            "thesaurus": self.thesaurus,
            "translate": self.translate,
            "match_style_of_author": self.match_style_of_author,
            "character_consistency": self.character_consistency,
            "world_rule_check": self.world_rule_check,
            "claim_grounding": self.claim_grounding,
            "citation_suggestion": self.citation_suggestion,
        }
        return sorted(
            [name for name, mod in all_modules.items() if mod.enabled],
            key=lambda n: all_modules[n].order,
        )


# ── Supporting sections ────────────────────────────────────────────────────────

class KnowledgeSourcesSection(BaseModel):
    # Generic
    rules_file: str = "knowledge/RULES.md"
    characters_file: str = "knowledge/characters.json"
    glossary_file: str = "knowledge/glossary.json"
    papers_file: str = "knowledge/papers.json"
    style_corpus_dir: str = "stores/style_corpus/"
    # Fiction-specific (optional)
    plot_file: Optional[str] = None
    feedback_file: Optional[str] = None
    places_file: Optional[str] = None
    style_file: Optional[str] = None
    timeline_file: Optional[str] = None


class PoliciesSection(BaseModel):
    allow_warning_bypass: bool = True
    preserve_raw_input: bool = True
    require_explicit_finalize: bool = True


# ── Root config ────────────────────────────────────────────────────────────────

class ProjectConfig(BaseModel):
    project: ProjectSection
    mode: ModeSection
    llm: LLMConfig = Field(default_factory=LLMConfig)
    chapters: ChaptersSection = Field(default_factory=ChaptersSection)
    interface: InterfaceSection = Field(default_factory=InterfaceSection)
    document: DocumentSection = Field(default_factory=DocumentSection)
    modules: ModulesSection = Field(default_factory=ModulesSection)
    knowledge_sources: KnowledgeSourcesSection = Field(default_factory=KnowledgeSourcesSection)
    policies: PoliciesSection = Field(default_factory=PoliciesSection)
    lexical_backends: LexicalBackendsSection = Field(default_factory=LexicalBackendsSection)
