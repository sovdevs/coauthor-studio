# SPEC1.md

## Project: AI-Augmented Writing Engine
## Step 1 Extension: Fiction Structure, Chapters, Dictionary, Thesaurus

### 1. Scope

This specification extends the Step 1 foundation and defines:

- a basic **fiction project structure**
- default fiction knowledge files
- chapter-based document storage
- optional no-chapter mode
- chapter switching in CLI and Web when enabled
- a **DICTIONARY** module
- a **THESAURUS** module
- how dictionary and thesaurus features should work in the CLI
- how dictionary and thesaurus are exposed as **tools** inside the LLM workflow
- how those tools may later be backed by local PDF resources or other retrieval sources

This specification still does **not** define full AI module internals.

The goal here is to define the project structure, config shape, and interface behavior clearly enough that implementation can begin in small steps.

---

## 2. Fiction Project Store

A fiction project should have its own dedicated folder and a fiction-specific knowledge subfolder.

Recommended structure:

```text
projects/
  dummy_fiction_project/
    config.json
    project_meta.json
    sentence_history.jsonl
    exports/
    fiction/
      PLOT.md
      CHARACTERS.md
      FEEDBACK.md
      PLACES.md
      RULES.md
      STYLE.md
      TIMELINE.md
      chapters/
        chapter_001.json
        chapter_002.json
```

### Explanation

#### `fiction/PLOT.md`
High-level plot notes, arcs, unresolved threads, scene direction, chapter goals.

#### `fiction/CHARACTERS.md`
Character descriptions, relationships, voice notes, traits, constraints, biographies.

#### `fiction/FEEDBACK.md`
Running notes from the user or external feedback.

Examples:
- pacing weak in chapter 2
- protagonist too passive
- dialogue sounds too modern
- tighten opening

#### `fiction/PLACES.md`
Empty by default.  
Used later for locations, geography, buildings, environments, recurring settings.

#### `fiction/RULES.md`
World rules, style rules, viewpoint rules, chronology constraints, genre rules.

#### `fiction/STYLE.md`
Optional style notes for the project.

Examples:
- sparse prose
- short declarative sentences
- no semicolons
- avoid modern slang

#### `fiction/TIMELINE.md`
Optional timeline or chronology tracker.

#### `fiction/chapters/`
Contains the actual chapter files when chapter mode is enabled.

---

## 3. Required Fiction Files

For a fiction project, these files should exist by default:

- `fiction/PLOT.md`
- `fiction/CHARACTERS.md`
- `fiction/FEEDBACK.md`
- `fiction/PLACES.md`

Recommended additional defaults:

- `fiction/RULES.md`
- `fiction/STYLE.md`
- `fiction/TIMELINE.md`

`PLACES.md` should be created empty except for a heading.

Example:

```markdown
# Places
```

---

## 4. Chapter Model

The writing must support two project modes:

- **chapter mode**
- **no-chapter mode**

This should be controlled in `config.json`.

### 4.1 Chapter mode
In chapter mode, the draft is split into separate JSON chapter files.

Example:

```text
fiction/chapters/chapter_001.json
fiction/chapters/chapter_002.json
fiction/chapters/chapter_003.json
```

### 4.2 No-chapter mode
In no-chapter mode, the project behaves as a continuous document.

This should be represented with a config flag, for example:

```json
"chapters": {
  "enabled": false,
  "no_chapters": true
}
```

Only one mode should be active at a time.

---

## 5. Chapter File Format

Each chapter should be stored as JSON, not plain Markdown, so that sentence history, ordering, metadata, and later module outputs can be tracked cleanly.

Recommended structure:

```json
{
  "chapter_id": "chapter_001",
  "chapter_number": 1,
  "title": "Chapter 1",
  "status": "draft",
  "summary": "",
  "sentences": [
    {
      "sentence_id": "sent_000001",
      "text": "The rain had stopped by then.",
      "finalized_at": "2026-04-09T12:00:00Z"
    },
    {
      "sentence_id": "sent_000002",
      "text": "Nobody else was on the street.",
      "finalized_at": "2026-04-09T12:01:00Z"
    }
  ]
}
```

### Required fields

- `chapter_id`
- `chapter_number`
- `title`
- `sentences`

### Optional fields

- `status`
- `summary`
- `notes`
- `last_updated`

---

## 6. Config.json Additions for Fiction and Chapters

Recommended config structure:

```json
{
  "project": {
    "project_id": "dummy_fiction_project",
    "title": "Dummy Fiction Project"
  },
  "mode": {
    "type": "fiction",
    "language": "en"
  },
  "llm": {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "temperature": 0.2,
    "api_key_env": "OPENAI_API_KEY",
    "tool_mode": "enabled"
  },
  "chapters": {
    "enabled": true,
    "no_chapters": false,
    "chapters_dir": "fiction/chapters/",
    "default_current_chapter": "chapter_001",
    "allow_chapter_switching": true
  },
  "interface": {
    "show_last_finalized_sentences": true,
    "last_finalized_sentence_count": 5,
    "show_current_chapter": true
  },
  "modules": {
    "dictionary": {
      "enabled": true,
      "order": 1,
      "settings": {
        "language": "en",
        "suggest_on_input": true,
        "allow_cli_search": true
      }
    },
    "thesaurus": {
      "enabled": true,
      "order": 2,
      "settings": {
        "language": "en",
        "suggest_on_input": true,
        "allow_cli_search": true,
        "max_synonym_groups": 5
      }
    }
  },
  "knowledge_sources": {
    "plot_file": "fiction/PLOT.md",
    "characters_file": "fiction/CHARACTERS.md",
    "feedback_file": "fiction/FEEDBACK.md",
    "places_file": "fiction/PLACES.md",
    "rules_file": "fiction/RULES.md",
    "style_file": "fiction/STYLE.md",
    "timeline_file": "fiction/TIMELINE.md"
  }
}
```

### Notes on the new `llm` section

The `llm` section is project-level configuration for any LLM-backed modules.

Fields:

- `provider`: current provider, initially OpenAI
- `model`: default model for lightweight lexical tasks
- `temperature`: low temperature recommended for dictionary/thesaurus consistency
- `api_key_env`: environment variable used to load the API key
- `tool_mode`: indicates that modules such as dictionary and thesaurus are exposed as callable tools rather than being treated as free-form chat responses

This does **not** yet define the full provider abstraction. It simply reserves the top-level place where such settings belong.

---

## 7. Current Chapter State

The project must store which chapter is currently active when chapter mode is enabled.

This can live in `project_meta.json`.

Example:

```json
{
  "status": "active",
  "current_chapter": "chapter_001",
  "current_chapter_number": 1
}
```

This keeps chapter switching separate from the permanent config.

`config.json` should define capability and defaults.  
`project_meta.json` should track the live active state.

---

## 8. CLI Requirements for Chapter Mode

When chapter mode is enabled, the CLI should show:

- project title
- mode
- current chapter
- active modules
- last `n` finalized sentences from the **current chapter**
- sentence input prompt

Example:

```text
Project: Dummy Fiction Project
Mode: fiction
Current chapter: Chapter 1
Active modules: dictionary, thesaurus
Last finalized sentences (5):
1. The rain had stopped by then.
2. Nobody else was on the street.
3. He paused at the gate.

Enter next sentence:
>
```

### Required CLI chapter commands

The CLI should support explicit commands for chapter navigation.

Suggested commands:

- `:chapters` → list chapters
- `:c 2` → switch to chapter 2
- `:c chapter_002` → switch by ID
- `:new` → create a new chapter

Optional later commands:

- `:chapter current` → show current chapter
- `:chapter rename 2 "The Crossing"` → rename chapter title

These are interface commands, not writing content.

---

## 9. Web Requirements for Chapter Mode

When chapter mode is enabled, the Web UI should support chapter switching through a visible control.

Recommended Web elements:

- chapter dropdown or sidebar chapter list
- current chapter badge
- last `n` finalized sentences from current chapter
- sentence input box
- chapter create button

Minimum required behavior:

- user can see the current chapter
- user can switch chapters
- sentence input always applies to the currently selected chapter
- the sentence history panel updates when the chapter changes

---

## 10. Last N Finalized Sentences in Chapter Mode

When `chapters.enabled = true`, the "last n finalized sentences" panel should default to showing only the current chapter's recent finalized sentences.

Optional future enhancement:
- toggle between current chapter only / all chapters

For now:
- **default rule** = current chapter only

When `no_chapters = true`, the panel should show the last `n` finalized sentences from the whole document.

---

## 11. DICTIONARY Module

### 11.1 Purpose
The `dictionary` module provides:

- spell checking and possible corrections on sentence input
- definition, part-of-speech, and inflection lookup on demand

Both functions are mediated by the project LLM stack.  
Language is taken from the project config (`mode.language`), so lookups are automatically in the correct language.

The dictionary module should be treated as a **tool** inside the writing workflow, not as a raw conversational answer.

This matters because later the tool may be backed by:
- an LLM-generated response
- a local lexical file
- a local PDF dictionary
- a structured dictionary database
- another retrieval mechanism

### 11.2 Main functions

#### A. Passive checking during sentence input
When the user enters a **candidate sentence (before finalization)**, the module may be invoked to detect:

- possible misspellings
- unknown or likely mistyped tokens
- suggested corrections

Example:
- `dostoevisky` → possible correction: `Dostoevsky`
- `teh` → possible correction: `the`

#### B. Active dictionary lookup (`:d`)
The user can look up any word at any time using the colon command `:d <word>`.

The result should provide:
- definition
- part of speech
- inflections or derived forms where relevant

### 11.3 Tool-based integration

The dictionary module is exposed as a **tool callable by the LLM**.

The LLM may invoke this tool:
- during passive sentence checking
- during explicit CLI command (`:d`)
- later, during export or cleanup passes

Initial implementation may still be LLM-backed internally, but architecturally it should be treated as a tool boundary.

Conceptual tool contract:

```json
{
  "tool_name": "dictionary_lookup",
  "input": {
    "word": "string",
    "language": "string"
  },
  "output": {
    "definition": "string",
    "part_of_speech": "string",
    "inflections": ["string"],
    "notes": "optional"
  }
}
```

### 11.4 Prompting model

For the initial implementation, the dictionary tool may use:
- `langchain`
- `langchain-openai`
- a structured prompt
- JSON output parsing

The prompt should instruct the LLM to answer in the configured language and return structured data only.

### 11.5 Basic output shape

```json
{
  "module_name": "dictionary",
  "status": "warning",
  "misspellings": [
    {
      "token": "teh",
      "suggestions": ["the"]
    }
  ],
  "lookups": []
}
```

### 11.6 Advisory status

Dictionary results are **advisory**, not authoritative lexicographic definitions.

That means the tool is suitable for interactive writing assistance, but should not be treated as a formal language authority unless later backed by curated lexical resources.

---

## 12. THESAURUS Module

### 12.1 Purpose
The `thesaurus` module provides synonym and near-synonym lookup.

It helps with:
- word variation and avoiding repetition
- tone shifts (stronger, weaker, more formal)
- richer word choices for fiction prose

This is a **search and suggestion** feature, not an automatic rewrite.

Language is taken from the project config (`mode.language`), so synonyms are always returned in the correct language.

Like the dictionary module, the thesaurus module should be treated as a **tool**, not merely a free-form prompt.

### 12.2 Main functions

#### A. Passive suggestion during sentence input
If enabled, the module can suggest alternatives for notable or repeated words in the entered candidate sentence.

Example:
- `walked` → `strode`, `trudged`, `moved`, `went`
- `good` → `solid`, `sound`, `capable`, `fine`

#### B. Active thesaurus lookup (`:t`)
The user can look up synonyms for any word at any time using `:t <word>`.

### 12.3 Tool-based integration

The thesaurus module is exposed as a **tool callable by the LLM**.

The LLM may invoke this tool:
- during passive suggestion
- during explicit CLI command (`:t`)
- later, during export or revision passes

Initial implementation may use LLM-generated synonyms, but the tool boundary should allow later routing to:
- local thesaurus PDFs
- curated synonym datasets
- embedding-based lexical retrieval
- specialized domain glossaries

Conceptual tool contract:

```json
{
  "tool_name": "thesaurus_lookup",
  "input": {
    "word": "string",
    "language": "string"
  },
  "output": {
    "groups": [
      {
        "label": "string",
        "alternatives": ["string"]
      }
    ],
    "notes": "optional"
  }
}
```

### 12.4 Grouped output shape

The thesaurus should return grouped alternatives where possible, rather than one undifferentiated list.

Example:

```json
{
  "module_name": "thesaurus",
  "status": "ok",
  "entries": [
    {
      "token": "walked",
      "groups": [
        {
          "label": "neutral",
          "alternatives": ["went", "moved"]
        },
        {
          "label": "literary",
          "alternatives": ["strode", "paced"]
        },
        {
          "label": "intense",
          "alternatives": ["trudged"]
        }
      ]
    }
  ]
}
```

### 12.5 Label constraints

The labels are **not** coming from a prebuilt fixed thesaurus taxonomy.

Instead:

- the LLM proposes groupings
- the prompt constrains the grouping labels
- the system normalizes labels to a small allowed set

Allowed labels:

```text
neutral
formal
informal
literary
archaic
intense
mild
negative
positive
technical
```

If uncertain, the fallback label is:

```text
neutral
```

This avoids unstable or overly creative categories while still letting the LLM provide useful nuance.

### 12.6 Why grouped labels matter

A flat synonym list is often too weak for writing support.

Grouped output is better because it allows the user to see:
- which alternatives are neutral
- which are stronger
- which are more literary or archaic
- which may shift tone noticeably

That is especially useful in fiction writing.

---

## 13. Tool Invocation Model

Dictionary and thesaurus modules are treated as **tools within the LLM reasoning loop**.

### 13.1 Key principles

- The LLM does not need to hardcode all dictionary or thesaurus knowledge
- Instead, it may **decide when to call tools**
- Tools return structured JSON
- The LLM incorporates results into:
  - warnings
  - suggestions
  - CLI outputs
  - later export-pass refinements

### 13.2 Two invocation contexts

#### 1. Sentence processing pass
This occurs after the user enters a candidate sentence and before finalization.

The LLM may:
- inspect the sentence
- optionally call `dictionary_lookup`
- optionally call `thesaurus_lookup`
- return structured module output

#### 2. Export / draft pass
This occurs after text is already saved and the system is generating or refreshing a cleaner draft/export view.

At this stage the LLM may again use tools for:
- lexical consistency
- repeated word cleanup
- spell-check support
- optional synonym improvement suggestions

This does **not** yet mean automatic rewriting is enabled. It only defines the place where such tools may be used.

### 13.3 Future extensibility

This design allows later substitution without changing the overall architecture.

For example, `dictionary_lookup` or `thesaurus_lookup` could later be backed by:
- local PDF resources
- vector DB retrieval
- structured lexical datasets
- external APIs
- local domain-specific glossaries

That is the main reason for treating dictionary and thesaurus as tools rather than simply baking everything into one prompt.

---

## 14. CLI Design for Dictionary and Thesaurus

### 14.1 Colon-command interface
The CLI uses a **colon-prefix command mode** to separate lookup commands from sentence input.

Any input starting with `:` is a command and is never saved to the document.

```text
:<command> [argument]
```

This keeps the writing flow completely clean. Commands are transient — the result is displayed above the prompt and control returns immediately to the sentence prompt.

### 14.2 Command syntax

| Input | Action |
|---|---|
| `:d <word>` | Dictionary lookup |
| `:t <word>` | Thesaurus lookup |
| `:c <n or id>` | Switch to chapter |
| `:chapters` | List all chapters |
| `:new` | Create a new chapter |
| `:help` | Show command reference |
| `:q` | Quit writing session |

Any input **not** starting with `:` is treated as a sentence and goes to the document.

### 14.3 Result display
Command results are printed on a dedicated block **above the input prompt**, visually separated with a rule.

They do not become part of the document. After the result is shown, the sentence prompt reappears.

Example — dictionary lookup:

```text
─────────────────────────────────────────────────────
:d obdurate

  Dictionary · obdurate  [en]
  Part of speech: adjective
  Meaning: stubbornly refusing to change one's opinion or course of action
  Forms: obdurate / obdurately / obduracy
─────────────────────────────────────────────────────

Next sentence (or :help):
>
```

Example — thesaurus lookup:

```text
─────────────────────────────────────────────────────
:t bleak

  Thesaurus · bleak  [en]
  neutral:
    - grim
    - stark

  literary:
    - desolate
    - cheerless
─────────────────────────────────────────────────────

Next sentence (or :help):
>
```

### 14.4 Passive module output after sentence input
When the user enters a sentence and it is checked by the dictionary module, any warnings appear above the prompt in the same block style — not inline with the writing.

```text
─────────────────────────────────────────────────────
  Dictionary: possible misspelling → waked
  Suggestion: walked
─────────────────────────────────────────────────────
  Saved.

Next sentence (or :help):
>
```

### 14.5 Commands never interrupt the writing flow
A command lookup never replaces or clears the current session state.

If the user was mid-thought, the prompt returns to the same position after the result is shown.

### 14.6 Direct tool use from CLI commands
CLI commands such as `:d` and `:t` should call their respective tools directly.

They do **not** need to run the full sentence pipeline.  
They are immediate lexical lookup commands.

This keeps command behavior fast, predictable, and separate from writing validation flow.

---

## 15. CLI Command Summary

All commands use the `:` prefix. Commands are not saved to the document.

### Chapter commands
- `:chapters` — list all chapters
- `:c <n>` — switch to chapter by number
- `:c <chapter_id>` — switch to chapter by ID
- `:new` — create a new chapter

### Dictionary commands
- `:d <word>` — dictionary lookup (definition, POS, inflections)

### Thesaurus commands
- `:t <word>` — thesaurus lookup (synonyms grouped by nuance)

### Utility commands
- `:help` — show command reference
- `:modules` — list active modules and their status
- `:mode` — show current mode and language
- `:q` — quit writing session

---

## 16. Default Fiction Dummy Project Files

### `fiction/PLOT.md`

```markdown
# Plot

Add major plot points, arcs, and unresolved threads here.
```

### `fiction/CHARACTERS.md`

```markdown
# Characters

Add character descriptions, motivations, relationships, and voice notes here.
```

### `fiction/FEEDBACK.md`

```markdown
# Feedback

Add writing feedback, revision notes, and observations here.
```

### `fiction/PLACES.md`

```markdown
# Places
```

### `fiction/RULES.md`

```markdown
# Rules

Add world, logic, viewpoint, and narrative rules here.
```

### `fiction/STYLE.md`

```markdown
# Style

Add project-level style notes here.
```

### `fiction/TIMELINE.md`

```markdown
# Timeline

Add chronology notes here.
```

---

## 17. Default Chapter File

### `fiction/chapters/chapter_001.json`

```json
{
  "chapter_id": "chapter_001",
  "chapter_number": 1,
  "title": "Chapter 1",
  "status": "draft",
  "summary": "",
  "sentences": []
}
```

---

## 18. Recommended Dummy `project_meta.json`

```json
{
  "status": "active",
  "current_chapter": "chapter_001",
  "current_chapter_number": 1
}
```

---

## 19. Design Decisions

### 19.1 Why Markdown for fiction notes?
Because these files are easy to read, edit, diff, and expand by hand.

### 19.2 Why JSON for chapters?
Because chapter content will later need metadata, sentence IDs, ordering, timestamps, and module traces.

### 19.3 Why LLM + tool-based dictionary and thesaurus instead of offline libraries?
Because the project may need to work across multiple languages using `mode.language`, while also remaining extensible.

The LLM-driven tool approach gives:
- multilingual flexibility
- richer lexical responses
- more nuanced synonym grouping
- a clean future path to alternate backends

It also allows later integration with:
- PDF-based dictionaries
- PDF-based thesauri
- curated lexical corpora
- domain-specific vocabulary sources

Dictionary results remain **advisory**, not authoritative lexicographic definitions.

### 19.4 Why separate dictionary and thesaurus modules even though both may use the LLM?
Because they serve different functions and have different prompts, output shapes, and passive-trigger logic:

- dictionary = correctness, meaning, part of speech, inflections
- thesaurus = lexical alternatives, variation, tone shifts

Keeping them as separate modules preserves the `enabled / order / settings` pattern and lets the user enable one without the other.

### 19.5 Why colon-prefix commands instead of slash commands?
Because slash commands (for example `/dict`) can resemble Unix paths or shell-style syntax.

The colon prefix (`:d`, `:t`, `:c`) is visually distinct, fast to type, and clearly separates tool use from prose input.

Results are transient — shown above the prompt, never written to the document.

### 19.6 Why chapter switching in both CLI and Web?
Because chapter context changes the active writing surface, recent sentence history, and later module retrieval.

---

## 20. Non-Goals for This Step

This step does not yet define:

- semantic ranking of synonym suggestions beyond what the tool returns
- AI style suggestion logic (prose rewriting, tone adjustment)
- automatic chapter summaries
- chapter-to-plot alignment logic
- LLM prompt tuning or caching strategy
- backend routing logic for PDF-based lexical tools
- automatic lexical rewriting during export

Those can come later.

---

## 21. Next Recommended Step

The next step should define:

- exact LangChain prompt templates for dictionary and thesaurus tools
- the full `llm` config section in `config.json`
- the exact candidate sentence workflow in CLI (candidate input → passive module output → options → finalize)
- the exact candidate sentence workflow in Web
- the web UI equivalent of `:d` and `:t`
- the general tool interface schema used across future modules

---

## 22. Bottom Line

The foundation should now support:

- fiction-specific project files
- chapter-based writing or no-chapter mode
- chapter switching in CLI and Web
- dictionary lookup and spell checking
- thesaurus lookup and synonym search
- LLM-mediated lexical tools
- a clean path toward local PDF-backed dictionary/thesaurus resources later
- a folder-based project structure that can grow without rewriting the architecture

This keeps the system modular while still giving the fiction workflow enough shape to start building.
