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
