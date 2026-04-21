# Usage

## Quick start

```bash
uv run af write dummy_project   # CLI typewriter session
uv run af-web                   # web UI at http://localhost:8000
```

---

## CLI — typewriter session

```bash
uv run af write <project_id>
```

The terminal shows the last 5 finalized segments above a typewriter input buffer.

| Key | Action |
|-----|--------|
| Enter | Insert a new line (carriage return) |
| `;;` alone on a line | Submit the current segment |
| `:command` on an empty line | Run a command (see below) |

Segments may span multiple lines — paragraphs, passages, whatever you need.
Commands only fire when the buffer is completely empty.

### Commands

```
:d <word>          dictionary lookup (local file, Wiktionary fallback)
:t <word>          thesaurus lookup (local Moby)
:del <n>           delete displayed segment number n
:c <n or id>       switch chapter
:chapters          list all chapters
:new [title]       create a new chapter
:modules           list active modules
:mode              show mode and language
:help              show all commands
:q                 quit
```

---

## Web UI

```bash
uv run af-web
# open http://localhost:8000
```

The write page has three zones:

- **Chapter bar** — project name, chapter selector, module badges
- **Manuscript sheet** — last 5 finalized segments in Courier, double-spaced
- **Typing area** — typewriter textarea below the manuscript

| Key | Action |
|-----|--------|
| Enter | Insert a new line |
| Ctrl+Enter (or Cmd+Enter) | Submit the current segment |

Commands work the same as CLI — type `:d word` etc. into the textarea and submit.

---

## One-time setup — local lexical data

Dictionary and thesaurus use local files. Download them once:

```bash
uv run python scripts/fetch_lexical_data.py          # all sources (~150 MB total)
uv run python scripts/fetch_lexical_data.py --dict   # ChrisSpinu dictionary only (~25 MB)
uv run python scripts/fetch_lexical_data.py --wikt   # Wiktionary only (~120 MB, 1M+ words)
uv run python scripts/fetch_lexical_data.py --thes   # Moby thesaurus only (~4 MB)
```

Dictionary lookup order: ChrisSpinu (102K words) → Wiktionary (1M+ words) → not found + spelling suggestions.

---

## Character Builder

Characters are global — they can be used in any project and by any dialog generation call.

### Web UI

Open the Characters section at `http://localhost:8000/characters`.

- **Create** a character via form (full questionnaire with tooltip hints on every field)
- **Edit** any existing character
- **Duplicate** a character as a starting point for a variant
- **Delete** a character
- **Generate dialog** → jumps to the Dialog page with that character pre-selected

Dialog generation at `http://localhost:8000/dialog/new`:

- Select two characters (or the same character twice for internal self-dialogue)
- Set a scene/setting description
- Choose mode: **Dialog** (speaker-labeled lines) or **Scene** (narration + action)
- Set voice options: quote mode, allow verbatim reuse, include authorial material
- Select a project to save the draft to
- **Generate** → editable draft appears
- Edit the draft, then **Submit revision** → system infers what changed about each character
- Review proposed profile updates (confidence-coded), then **Accept all** or **Reject all**

### CLI — `:cb` commands

Type any `:cb` command from within a `uv run af write <project>` session.

```
:cb list                               list all characters in the registry
:cb show <id>                          print the full character profile as Markdown
:cb create                             create a new character (guided interview)
:cb edit <id>                          edit an existing character (guided interview)
:cb duplicate <id>                     copy a character; adds "(Copy)" suffix
:cb delete <id>                        delete a character (with confirmation)
:cb export <id>                        print Markdown dossier to terminal
```

#### Dialog generation

```
:cb dialog <idA> <idB> --setting "…"   generate a dialog draft
:cb scene  <idA> <idB> --setting "…"   generate a scene draft (includes narration)
```

Use the same ID twice for **internal self-dialogue** (one mind under pressure).

Optional flags:
```
--quote-mode auto|light|strong          how closely to echo stored voice material
--allow-direct-quotes                   permit verbatim reuse of reference quotes
--include-authorial-material            make authorial material available for thematic use
```

#### Auto-extraction from author packages

Extract draft character profiles from an existing author package (turnofphrase directory):

```
:cb extract <author_dir>
:cb extract cormac_mccarthy                       # bare slug resolved automatically
:cb extract modules/voice/turnofphrase/hemingway  # or full path
:cb extract cormac_mccarthy --include-narrator    # also extract per-book narrator profiles
```

Flow:
1. Loads processed passages (`passages.jsonl` → `extracted_text.json` → EPUB fallback)
2. LLM detects candidate characters from a corpus sample
3. Ranked candidate list is displayed — you pick which characters to draft (by number, range, or `all`)
4. For each selected character: builds a raw evidence file → synthesises a draft profile
5. Profile saved to global registry; extraction sidecar saved alongside it
6. With `--include-narrator`: one additional narrator profile per book, marked `story.role = narrator`

Extracted profiles are immediately available in Character Studio and for dialog generation.
Evidence files saved to `<author_dir>/evidence/<character_slug>.md` for inspection.

---

## Other commands

```bash
uv run af list                           # list all projects
uv run af init                           # create a new project via wizard
uv run af draft <project_id>             # export finalized segments to .txt
uv run af draft <project_id> -o out.txt  # export to a specific file
```

---

## Config

Each project has a `config.json`. Key interface settings:

```json
"interface": {
  "last_finalized_segment_count": 5,
  "submit_token": ";;",
  "typewriter_theme": true,
  "typewriter_sounds": false
}
```

Lexical backend paths (relative to repo root):

```json
"lexical_backends": {
  "dictionary": {
    "paths": [
      "resources/dictionary/dictionary_compact.json",
      "resources/dictionary/wiktionary-en.json"
    ]
  },
  "thesaurus": {
    "paths": ["resources/thesaurus/moby.json"]
  }
}
```
