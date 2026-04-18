# SPEC2_lexical_backend.md

## Project: AI-Augmented Writing Engine  
## Step 2: Local Lexical Backend Upgrade for Dictionary and Thesaurus

### 1. Scope

This specification upgrades the existing `dictionary` and `thesaurus` modules from a remote-LLM-first design to a **local-first lexical backend** design.

The goals of this step are:

- reduce latency in the writing loop
- keep CLI lookup commands fast enough for interactive use
- preserve the existing tool-based architecture
- support offline lexical lookup
- allow later use of a small local Llama model for lexical reasoning or re-ranking
- retain a fallback path to a remote LLM if needed

This step does **not** yet define:

- chapter consistency logic
- candidate sentence finalization flow
- style-matching logic
- export-pass rewriting
- full prompt templates for prose modules

---

## 2. Design Goal

The dictionary and thesaurus modules should no longer depend primarily on remote LLM calls.

Instead, they should use a layered backend strategy:

1. local file/data lookup first  
2. optional small local LLM second  
3. optional remote LLM fallback last  

The user-facing CLI and Web behavior should remain stable.

---

## 3. Recommended Local Sources

### Thesaurus
- Moby (words/moby)

### Dictionary
- Websters English Dictionary (JSON formats)

---

## 4. Licensing Note

Do not hardcode dependency on a single source.

Different datasets have different licenses (public domain, GPL, etc.).

Architecture must allow swapping sources.

---

## 5. Lexical Backend Architecture

Dictionary and thesaurus remain **tools**, but are backed by a backend router.

dictionary_lookup → backend  
thesaurus_lookup → backend  

---

## 6. Config Upgrade

```json
{
  "lexical_backends": {
    "dictionary": {
      "type": "file",
      "source": "websters_json",
      "path": "resources/dictionary/dictionary_compact.json",
      "fallback": "remote_llm"
    },
    "thesaurus": {
      "type": "file",
      "source": "moby",
      "path": "resources/thesaurus/moby.json",
      "fallback": "remote_llm"
    }
  }
}
```

Allowed backend types:
- file
- local_llm
- remote_llm

---

## 7. Dictionary Module Upgrade

### Functions
- spell check
- correction suggestions
- definition lookup
- POS lookup

### Behavior
- local lookup first
- fuzzy suggestions if not found
- optional Llama explanation
- fallback remote LLM

### Output

```json
{
  "tool_name": "dictionary_lookup",
  "output": {
    "found": true,
    "definition": "...",
    "part_of_speech": "...",
    "source": "websters_json"
  }
}
```

---

## 8. Thesaurus Module Upgrade

### Functions
- synonym lookup
- variation support

### Modes
- flat (MVP)
- grouped (later)

### Output

Flat:
```json
{
  "alternatives": ["grim", "stark"]
}
```

Grouped:
```json
{
  "groups": [
    {"label": "neutral", "alternatives": ["went"]},
    {"label": "literary", "alternatives": ["strode"]}
  ]
}
```

---

## 9. Role of Local Llama

Used for:
- grouping synonyms
- explaining meaning
- ranking alternatives

Not used for:
- first-pass lookup

---

## 10. CLI Behavior

Commands unchanged:
- :d word
- :t word

Optional debug:
- :lex source word

---

## 11. Backend Selection Rules

Dictionary:
- local → fuzzy → llama → remote

Thesaurus:
- local → llama grouping → remote

---

## 12. Local Data Preparation

- preprocess JSON once
- build lowercase index
- avoid runtime parsing cost

---

## 13. Tool Implications

LLM still calls tools.

Tools now mostly local.

---

## 14. MVP

Phase 1:
- file dictionary
- file thesaurus
- flat synonyms

Phase 2:
- llama grouping

---

## 15. Next Step

Define:

- candidate sentence workflow
- finalize/edit loop
- persistence model

---

## 16. Bottom Line

Move to:

- local dictionary
- local thesaurus
- llama enhancement
- remote fallback

This unlocks speed and keeps architecture clean.
