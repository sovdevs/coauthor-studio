# DEV

## Stage0

**Step 1 complete.** Structure:

```
augmentedFiction/
  pyproject.toml                          # uv project, scripts: af / af-web
  src/augmented_fiction/
    config/
      schema.py                           # Pydantic v2: full typed config tree
      loader.py                           # load_config / save_config
    project/
      store.py                            # list/load projects, PROJECTS_DIR
      history.py                          # SentenceRecord, JSONL read/write
      wizard.py                           # setup wizard (af init)
    cli/main.py                           # af list / af write / af init
    web/
      app.py                              # FastAPI: GET /, GET /project/{id}, POST /submit
      templates/base.html, index.html, write.html
      static/style.css, app.js
  projects/dummy_project/                 # pre-seeded with 5 spec sentences
```

**To use:**
```bash
uv run af list                    # see projects
uv run af write dummy_project     # writing session in terminal
uv run af-web                     # web at http://localhost:8000
uv run af init                    # setup wizard for a new project

  # default output: dummy_project_draft.txt
  uv run af draft dummy_project                                                                                                                                                                     
   
  # custom path                                                                                                                                                                                     
  uv run af draft dummy_project -o my_draft.txt 
```

**Key design choices:**
- Config is fully Pydantic-validated; adding a module means a new settings model + wrapper in `schema.py`, nothing else changes
- Web submit returns JSON and updates the finalized panel in-place (no page reload, Ctrl/Cmd+Enter also submits)
- `AF_PROJECTS_DIR` env var overrides the default `projects/` location

---

## Stage0 / SPEC1 — Fiction structure, chapters, dictionary, thesaurus

**New modules and files:**

```
src/augmented_fiction/
  commands/
    registry.py      # reusable dispatch engine: CommandRegistry, WriteContext, CommandResult
    builtins.py      # chapter + dict + thesaurus handlers; build_registry()
  modules/
    dictionary.py    # LLM tool — LangChain structured output, language-aware
    thesaurus.py     # LLM tool — grouped synonyms, constrained label taxonomy
  project/
    chapters.py      # Chapter / ChapterSentence Pydantic models + list/load/save/append
    meta.py          # ProjectMeta (current_chapter) + load/save
config/schema.py     # added: LLMConfig, ChaptersSection, DictionaryModule, ThesaurusModule
                     # updated: ModulesSection, KnowledgeSourcesSection, InterfaceSection
```

**dummy_project migrated:**
```
projects/dummy_project/
  config.json              # added llm, chapters, knowledge_sources (fiction), dict+thes modules enabled
  project_meta.json        # current_chapter: chapter_001
  fiction/
    PLOT.md, CHARACTERS.md, FEEDBACK.md, PLACES.md, RULES.md, STYLE.md, TIMELINE.md
    chapters/
      chapter_001.json     # all 8 existing sentences migrated in
```

**To use:**
```bash
uv run af write dummy_project     # chapter-aware session; :help for all commands
uv run af-web                     # chapter dropdown + command dispatch in web
```

**CLI colon-command interface (in af write):**
```
:d <word>          dictionary lookup (LLM)
:t <word>          thesaurus lookup (LLM, grouped by tone)
:c <n or id>       switch chapter
:chapters          list chapters
:new [title]       create new chapter
:help              show all commands
:q                 quit
```

**Key design choices:**
- `CommandRegistry` has zero project dependencies — reusable for any input surface
- `build_registry()` conditionally registers only what config has enabled; chapters off = no chapter commands
- LLM modules (dict/thesaurus) are tool-shaped: `lookup(word, language, llm_config)` — easy to swap backend later (PDF, wordnet, etc.)
- Sentences always written to global `sentence_history.jsonl` AND to the active chapter JSON
- Web POST `/submit` dispatches colon commands and returns `{"kind": "command", "output": "..."}` — same registry as CLI
- New web endpoints: `GET /project/{id}/chapters`, `POST /project/{id}/chapter/new`
- `OPENAI_API_KEY` env var required for dict/thesaurus LLM calls


  cp .env.example .env DONE
  # then edit .env and paste your key:                                                                                                                                                              
  OPENAI_API_KEY=sk-...    

---

## Stage0 / SPEC2 — Local lexical backend (no LLM)

Dictionary and thesaurus now use local file data only. No LLM is involved in lookups.

**One-time setup (download data files):**
```bash
python scripts/fetch_lexical_data.py
# creates resources/dictionary/dictionary_compact.json  (~30 MB, Webster's 1913, public domain)
# creates resources/thesaurus/moby.json                (~4 MB, Moby, public domain)
```

**New files:**
```
src/augmented_fiction/
  modules/
    lexical_backend.py   # DictFileBackend + ThesFileBackend, module-level cache
    dictionary.py        # file lookup + fuzzy suggestions on miss
    thesaurus.py         # file lookup, flat "neutral" group (grouped = Phase 2)
config/schema.py         # added: LexicalBackendConfig, LexicalBackendsSection
scripts/
  fetch_lexical_data.py  # one-time download + conversion
resources/
  dictionary/dictionary_compact.json
  thesaurus/moby.json
```

**Config (per project, paths relative to repo root):**
```json
"lexical_backends": {
  "dictionary": { "type": "file", "source": "websters_json", "path": "resources/dictionary/dictionary_compact.json" },
  "thesaurus":  { "type": "file", "source": "moby",          "path": "resources/thesaurus/moby.json" }
}
```

**Removed deps:** `langchain`, `langchain-openai` (and all transitive deps — 32 packages removed)

**Key design choices:**
- Backends load JSON once on first call and cache the instance for the process lifetime
- Dictionary uses `difflib.get_close_matches` for spelling suggestions on miss
- Thesaurus returns synonyms as a flat "neutral" group (display layer unchanged)
- `LLMConfig` stays in schema for future non-lexical modules; no LLM code in dict/thes
  