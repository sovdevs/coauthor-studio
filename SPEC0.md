

Claude Spec — Step 1 Foundation

1. Scope of this step

This step defines only:
	•	MODE
	•	PROJECT STORE
	•	config.json
	•	basic CLI input structure
	•	basic Web input structure
	•	showing last n finalized sentences
	•	a default dummy project

This step does not implement module internals.



1.1

Use uv throughtout with a project.toml

latest python.
⸻

2. Core Concepts

2.1 Mode

A project has a writing mode.

Initial supported values:
	•	fiction
	•	academic

Later this can be extended, for example:
	•	hybrid
	•	translation
	•	nonfiction

But for now keep it simple: fiction vs academic.

Important: mode is not the same as modules.
Mode gives the project a default orientation. Modules are independently enabled.

Example:
	•	Fiction project with translation module enabled
	•	Academic project with style module enabled
	•	Fiction project with no style module at all

⸻

2.2 Project Store

Each writing project lives in its own folder.

The project folder contains:
	•	the config
	•	the canonical draft
	•	logs/history
	•	project knowledge files
	•	later: module-specific stores

This is the persistent unit of work.

A project store should be portable and human-readable.

⸻

3. Project Store Structure

Recommended initial structure:

projects/
  dummy_project/
    config.json
    draft.md
    sentence_history.jsonl
    project_meta.json
    knowledge/
      RULES.md
      characters.json
      glossary.json
      papers.json
    stores/
      style_corpus/
      embeddings/
      cache/
    exports/

Explanation

config.json

Main project configuration.

draft.md

Canonical clean document text.

sentence_history.jsonl

Audit trail of candidate inputs, suggestions, user selections, finalized outputs.

project_meta.json

Optional metadata like title, description, created date.

knowledge/

Plain-text and JSON project knowledge sources.

stores/

Internal project stores that may later support modules.

exports/

Rendered outputs for Markdown, DOCX conversion, HTML, etc.

⸻

4. Config Design Principles

The config.json should be:
	•	human-editable
	•	nested
	•	explicit
	•	extensible
	•	stable even as modules grow

It should answer:
	•	what is this project?
	•	what mode is it in?
	•	what interface defaults apply?
	•	what modules are enabled?
	•	what settings do those modules need?
	•	where are the project files?

⸻

5. High-Level Config Shape

Recommended structure:

{
  "project": {},
  "mode": {},
  "interface": {},
  "document": {},
  "modules": {},
  "knowledge_sources": {},
  "policies": {}
}

That is enough for a strong base.

⸻

6. Config Sections

6.1 project

Basic identity metadata.

Suggested fields:
	•	project_id
	•	title
	•	description
	•	created_at
	•	author

6.2 mode

Defines top-level writing mode.

Suggested fields:
	•	type: "fiction" or "academic"
	•	subtype: optional
	•	language: optional base writing language

6.3 interface

Defines CLI/Web behavior.

Suggested fields:
	•	show_last_finalized_sentences
	•	last_finalized_sentence_count
	•	allow_manual_override
	•	show_module_warnings
	•	show_module_suggestions

6.4 document

Defines the canonical document files.

Suggested fields:
	•	draft_file
	•	history_file
	•	export_format_defaults

6.5 modules

This is the key section.

Each module is independently configured as an object.

Each module should have at least:
	•	enabled
	•	order
	•	settings

That allows multi-select and later extension.

Example modules:
	•	translate
	•	match_style_of_author
	•	character_consistency
	•	world_rule_check
	•	claim_grounding
	•	citation_suggestion

6.6 knowledge_sources

Maps file locations.

Examples:
	•	rules_file
	•	characters_file
	•	glossary_file
	•	papers_file
	•	style_corpus_dir

6.7 policies

Controls system behavior.

Examples:
	•	whether warnings can be bypassed
	•	whether unsupported academic claims can still be finalized
	•	whether original raw input is always preserved

⸻

7. Module Configuration Pattern

Every module should follow the same outer pattern.

Standard pattern

{
  "enabled": true,
  "order": 2,
  "settings": {}
}

This is important. It keeps the system uniform.

Then each module can define its own nested settings.

⸻

8. Example: Translate Module

Your translation idea fits very naturally.

Example:

"translate": {
  "enabled": true,
  "order": 1,
  "settings": {
    "source_language": "de",
    "target_language": "en",
    "preserve_tone": true,
    "style_basis": "dostoevsky"
  }
}

Or more carefully:

"translate": {
  "enabled": true,
  "order": 1,
  "settings": {
    "source_language": "user_input",
    "target_language": "en",
    "style_reference_mode": "author_corpus",
    "style_reference_id": "dostoevsky_corpus",
    "translation_priority": "meaning_first"
  }
}

This is exactly why nested config is needed.

⸻

9. How Config Gets Created

Yes, the config should be created by asking the user a series of setup questions.

Not a giant freeform config editor at first.

Better approach:

Config setup wizard

The project is initialized by a simple question flow.

Example setup sequence:
	1.	Project title?
	2.	Fiction or academic?
	3.	Main writing language?
	4.	Show how many previous finalized sentences?
	5.	Enable translation module?
	6.	Enable style module?
	7.	Enable character consistency module?
	8.	Enable rule checking module?
	9.	Enable academic grounding module?
	10.	Paths for project files?

The answers generate config.json.

Later, advanced users can edit the JSON manually.

⸻

10. Default Dummy Project Config

Here is a good starter config.json for a dummy project.

{
  "project": {
    "project_id": "dummy_project",
    "title": "Dummy Writing Project",
    "description": "Starter project for AI-augmented writing",
    "created_at": "2026-04-09T12:00:00Z",
    "author": "user"
  },
  "mode": {
    "type": "fiction",
    "subtype": "general",
    "language": "en"
  },
  "interface": {
    "show_last_finalized_sentences": true,
    "last_finalized_sentence_count": 5,
    "allow_manual_override": true,
    "show_module_warnings": true,
    "show_module_suggestions": true
  },
  "document": {
    "draft_file": "draft.md",
    "history_file": "sentence_history.jsonl",
    "export_format_defaults": [
      "md",
      "txt",
      "docx"
    ]
  },
  "modules": {
    "translate": {
      "enabled": false,
      "order": 1,
      "settings": {
        "source_language": "auto",
        "target_language": "en",
        "style_reference_mode": null,
        "style_reference_id": null,
        "translation_priority": "meaning_first"
      }
    },
    "match_style_of_author": {
      "enabled": false,
      "order": 2,
      "settings": {
        "author_name": null,
        "style_corpus_dir": "stores/style_corpus/",
        "max_style_matches": 3
      }
    },
    "character_consistency": {
      "enabled": false,
      "order": 3,
      "settings": {
        "characters_file": "knowledge/characters.json",
        "strictness": "medium"
      }
    },
    "world_rule_check": {
      "enabled": false,
      "order": 4,
      "settings": {
        "rules_file": "knowledge/RULES.md",
        "strictness": "medium"
      }
    },
    "claim_grounding": {
      "enabled": false,
      "order": 5,
      "settings": {
        "papers_file": "knowledge/papers.json",
        "minimum_evidence_count": 1,
        "allow_unsubstantiated_finalize": true
      }
    },
    "citation_suggestion": {
      "enabled": false,
      "order": 6,
      "settings": {
        "papers_file": "knowledge/papers.json",
        "citation_style": "apa"
      }
    }
  },
  "knowledge_sources": {
    "rules_file": "knowledge/RULES.md",
    "characters_file": "knowledge/characters.json",
    "glossary_file": "knowledge/glossary.json",
    "papers_file": "knowledge/papers.json",
    "style_corpus_dir": "stores/style_corpus/"
  },
  "policies": {
    "allow_warning_bypass": true,
    "preserve_raw_input": true,
    "require_explicit_finalize": true
  }
}


⸻

11. Dummy Supporting Files

project_meta.json

{
  "status": "active",
  "current_chapter": 1,
  "current_section": 1,
  "notes": "Dummy starter project"
}

draft.md

# Dummy Writing Project

knowledge/characters.json

{
  "characters": []
}

knowledge/glossary.json

{
  "terms": []
}

knowledge/papers.json

{
  "papers": []
}

knowledge/RULES.md

# Project Rules

Add project rules here.


⸻

12. CLI Input Structure

The CLI should be very simple at first.

CLI screen should show:
	•	project title
	•	mode
	•	active modules
	•	last n finalized sentences
	•	current input prompt

Example CLI layout

Project: Dummy Writing Project
Mode: fiction
Active modules: none
Last finalized sentences (5):
1. The rain had stopped by then.
2. Nobody else was on the street.
3. He paused at the gate.
4. The station bell sounded once.
5. Still he did not turn.

Enter next sentence:
> 

After input, the system would later show:
	•	original candidate
	•	warnings
	•	suggestions
	•	finalize choice

But for this step, the basic input structure is enough.

CLI minimum behavior for now
	1.	load project folder
	2.	load config.json
	3.	load last n finalized sentences from history or draft state
	4.	display them
	5.	prompt user for next sentence
	6.	store candidate temporarily for future pipeline use

⸻

13. Web Input Structure

The web version should mirror the CLI, not invent a different logic.

Initial web layout

Left / main panel
	•	sentence input box
	•	submit button

Right / side panel
	•	project title
	•	mode
	•	enabled modules
	•	last n finalized sentences

Later panel
	•	warnings
	•	suggestions
	•	evidence

For now, do not overbuild.

Minimal web page elements
	•	Project Header
	•	Mode Badge
	•	Enabled Modules List
	•	Last Finalized Sentences Panel
	•	Single Sentence Input Field
	•	Submit Candidate Button

⸻

14. Last N Finalized Sentences

This should be controlled entirely by config.

Field:

"last_finalized_sentence_count": 5

The source of truth should ideally be sentence_history.jsonl, because later the draft might be edited manually.

Each finalized record should include whether it was actually accepted.

So later the UI can safely retrieve only the last accepted/finalized sentences.

⸻

15. Recommended Sentence History Shape

Even though we are not implementing modules yet, we should define the future-ready record shape now.

Example record:

{
  "sentence_id": "sent_000001",
  "timestamp": "2026-04-09T12:10:00Z",
  "raw_input": "He went down to the station.",
  "final_text": "He went down to the station.",
  "status": "finalized",
  "mode": "fiction",
  "module_results": [],
  "user_choice": "original"
}

Stored as one JSON object per line in sentence_history.jsonl.

That will make the “show last n finalized sentences” feature easy.

⸻

16. Setup Wizard Questions

Here is the question flow I would use for generating config.json.

Basic project setup
	1.	Project name?
	2.	Project ID?
	3.	Fiction or academic?
	4.	Main writing language?
	5.	How many finalized sentences should be shown?

Module selection
	6.	Enable translation module?
	7.	Enable style matching module?
	8.	Enable character consistency module?
	9.	Enable world rule checking module?
	10.	Enable academic grounding module?
	11.	Enable citation suggestion module?

Module-specific nested questions

If translation enabled:
	•	Source language?
	•	Target language?
	•	Preserve tone?
	•	Use style basis?

If style module enabled:
	•	Author name?
	•	Style corpus directory?
	•	Max retrieved style matches?

If character consistency enabled:
	•	Characters file path?
	•	Strictness?

If world rule check enabled:
	•	Rules file path?
	•	Strictness?

If academic grounding enabled:
	•	Papers file path?
	•	Minimum evidence count?

This is exactly the kind of nested setup that justifies the config design.

⸻

17. What Not To Do Yet

At this stage, do not yet define:
	•	embedding logic
	•	vector DB logic
	•	model providers
	•	module prompt internals
	•	module output ranking logic
	•	paragraph-level workflow
	•	export pipeline beyond placeholders

That would be too early.

⸻

18. Best Next Step with Claude

The next step should be one of these two:

Option A: define the exact config.json schema more formally, including allowed values and required fields.

Option B: define the exact CLI and Web interaction flow for one sentence from input to temporary candidate state, still without module internals.

The cleanest order is probably:
	1.	finalize config schema
	2.	finalize project folder structure
	3.	finalize sentence history record
	4.	define CLI/Web flow
	5.	only then start defining module contracts

⸻

19. Bottom line

Yes, your architecture should be:
	•	Mode = fiction or academic
	•	Project Store = folder-based portable project unit
	•	Config.json = nested project definition with multi-select module settings
	•	CLI/Web input = one candidate sentence plus last n finalized sentences
	•	Modules = independent and added later step by step

This is the right base.
