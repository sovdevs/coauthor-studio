# Claude Build Spec — Character Quotes, Character Studio UI, and New Dialog Flow

## Purpose

This spec defines the next build stage for the Character Builder / Dialog system.

The system is a **suggestor**, not an automatic final writer.
Everything it generates is provisional and editable before inclusion in a manuscript.

The goal is:
- to aid creativity
- to improve efficiency
- to help users find and reuse character material
- to preserve character continuity
- to make dialog generation more grounded and more voice-faithful

This next stage has three parts:

1. integrate a richer **quote / voice reference mechanism** into the character schema and dialog CLI
2. build the **web Character Studio** under Projects
3. build a **New Dialog** web flow using saved characters

---

## Core product reminder

This system should assume:

- generated text is draft material
- users may heavily edit or rewrite outputs
- characters can carry:
  - their own voice
  - source-derived language
  - authorial ideas / quotations / thematic material placed into their mouths
- the tool is intended to support writing, not replace judgement

This means the system should optimize for:
- retrieval of useful voice material
- reusable character memory
- editable outputs
- efficient drafting

---

## Part 1 — Quote / Voice Reference Mechanism

### Why this matters

The current `example_lines` idea is too narrow if the goal is to preserve or suggest actual character language.

For some characters, especially from:
- television
- film
- theatre
- comics
- highly stylized fiction

we need more than 2–3 lines.

Also, some authors use characters as vehicles for:
- famous quotations
- ideological lines
- aphorisms
- authorial commentary
- things the author wants said in-scene

These should be storable as part of the character’s usable material.

The system should allow these materials to be used as **voice anchors** and **idea reservoirs** for dialog generation.

Important:
The generator should not simply paste lines blindly.
It should use them to produce new, voice-consistent draft dialogue unless the user explicitly asks for direct quotation.

---

## Part 1A — Schema changes

Extend the character profile schema with a richer voice / quote structure.

### Replace or expand `example_lines`

Introduce a structure like:

- `reference_quotes[]`
- `speech_patterns[]`
- `lexical_markers[]`
- `authorial_material[]`

### Definitions

#### `reference_quotes[]`
Actual quotes or strongly representative lines associated with the character.

Each entry should ideally support:

- `text`
- `source`
- `is_canonical` (true/false)
- `added_by_user` (true/false)
- `tone`
- `notes`

Use cases:
- direct source quotes
- remembered lines from a show/book
- manually added representative lines

#### `speech_patterns[]`
Abstracted habits of speech and dialog behavior.

Examples:
- interrupts when losing control
- answers questions with questions
- trails off instead of concluding
- speaks in clipped corrections
- moralizes indirectly
- uses grand abstractions
- speaks in fragments under stress

#### `lexical_markers[]`
Recurring words, phrases, constructions, or verbal habits.

Examples:
- “listen”
- “you know”
- “I mean”
- “my dear fellow”
- legal phrasing
- religious cadence
- bureaucratic qualification
- deadpan understatement

#### `authorial_material[]`
Lines, ideas, quotations, assertions, or thematic statements that the writer wants available to this character as candidate mouth-material.

This is not identical to canonical quotes.
This field exists because a character may be used to carry:

- a famous quotation
- a thought the author wants expressed
- a paraphrased argument
- a thematic line
- an ideological stance
- a historical or literary remark

Each entry should support:

- `text`
- `source_type` (`quote`, `theme`, `argument`, `paraphrase`, `author_note`, `other`)
- `source`
- `notes`
- `direct_use_allowed` (true/false)
- `paraphrase_preferred` (true/false)

Important:
This field should be treated as **available material** for draft generation, not as guaranteed insertion.

---

## Part 1B — Dialog CLI integration

### Existing commands

Keep:
- `:cb dialog <idA> <idB> --setting "..."`
- `:cb scene <idA> <idB> --setting "..."`

### Extend with options

Add optional CLI flags such as:

- `--use-quotes`
- `--quote-mode auto|light|strong`
- `--allow-direct-quotes`
- `--include-authorial-material`
- `--speaker-focus <id>`
- `--save-debug`

These do not all need to be fully sophisticated in V1, but the prompt pathway should support them.

### Behavior

#### Default behavior
By default, dialog generation should:
- use stored quotes and voice material as anchors
- avoid verbatim copying unless clearly appropriate
- generate fresh lines consistent with the character

#### `--use-quotes`
Explicitly increases the importance of reference quotes and speech markers.

#### `--quote-mode`
Suggested interpretation:
- `auto` = balanced, use voice anchors naturally
- `light` = mild influence, mostly newly generated speech
- `strong` = stronger mimicry / closer cadence to stored material

#### `--allow-direct-quotes`
Allows exact or near-exact reuse of stored quotes where suitable.
This is useful because some users may explicitly want a character to speak an actual line.

#### `--include-authorial-material`
Allows the generator to draw on `authorial_material[]` for thematic content and candidate lines.

This is especially important for:
- essayistic fiction
- philosophical dialog
- politically charged dialog
- historical or literary quotation use
- scenes where a character is effectively voicing an idea the author wants aired

---

## Part 1C — Prompt rules for dialog generation

Update `dialog.py` prompt logic so that it clearly distinguishes:

1. **character identity**
2. **voice markers**
3. **available quote material**
4. **authorial material**
5. **scene setting / interaction pressure**

The prompt should explicitly tell the model:

- preserve differences between the characters
- do not flatten them into generic LLM speech
- use stored quote material as voice guidance
- use authorial material as optional candidate content, not mandatory insertion
- prefer generating new lines that feel true to the character
- only use direct quotation when:
  - explicitly allowed
  - or clearly appropriate

### Prompt goals

The generated dialog should:
- sound like interaction, not profile summaries speaking
- show subtext
- reflect tension and differing aims
- preserve character-specific language
- remain readable and editable as draft material

### Important design principle

The tool is a **suggestor**.

So the prompt and output format should assume:
- users will review
- users may rewrite freely
- the system is proposing plausible lines, not canonizing them

---

## Part 1D — Output artifacts

Keep generated outputs human-readable.

Profiles remain structured.
Dialog drafts remain readable Markdown.

For dialog drafts, add metadata header fields such as:

- mode
- characters
- setting
- generated_at
- quote_mode
- direct_quotes_allowed
- authorial_material_used

Where practical, also record:
- which quote banks were supplied
- whether authorial material was included

This can be simple front matter.

---

## Part 2 — Web Character Studio under Projects

### Architecture decision

Character management should live primarily in a dedicated web section under Projects.

Do **not** treat character creation as only a modal attached to the write page.

### Location

Under Projects, create a **Characters** section or studio.

Suggested high-level structure:

- Projects
  - Manuscripts
  - Characters
  - (future: Worlds / Notes / Research)

### Purpose of Character Studio

This is the main home for:

- listing characters
- creating new characters
- editing characters
- inspecting character profiles
- managing voice/reference material
- later import/export/extraction workflows

### V1 UI requirements

The Characters section should provide:

- character list
- search/filter
- source/type badges:
  - manual
  - extracted
  - imported
  - generated
- create new character
- open/edit existing character
- access to quote/reference material
- readable display of character ID

### Character list display

For each character, show at minimum:

- display name
- character ID
- source/type badge
- short essence / one-line summary if available

Example:

**Judge Holden**  
`mccarthy__judge`  
extracted

### Create New Character

This should open the **web version of the questionnaire**.

The questionnaire should map to the same schema and storage used by CLI creation.

It does not need to replicate terminal behavior literally, but it should produce the same profile object.

### Recommended UI structure

Use a dedicated page or panel-based editor, not a tiny popup for the full deep interview.

A workable V1 web structure:

- Character list on left
- selected character / create form on right

Or:
- Character list page
- Create/Edit character page

Either is acceptable.

What matters is:
- Character Studio is a proper place under Projects
- it is the main UI for character management

### Questionnaire modes

Support:
- Quick Create
- Deep Create

The same logic as CLI, but in web form.

### Voice / quote section in UI

The web questionnaire/editor must support adding and editing:

- reference quotes
- speech patterns
- lexical markers
- authorial material

This is a core part of the build, not an afterthought.

### Editing

Existing characters should be editable in the web studio.

Important fields should be easy to inspect and revise, especially:
- desire/fear/contradiction
- voice description
- quotes and authorial material
- signature behaviors

---

## Part 3 — Main Write Page character visibility

The write page should not be the full character editor.

Its role is lighter:
- make characters visible
- help the user reference IDs for CLI-assisted commands
- keep writing flow intact

### Requirements

On the main write page, add a compact character area showing:

- display names
- character IDs
- source/type badges if practical

Optional but useful:
- quick copy-ID control
- hover or click for a one-line summary

Purpose:
- support use of `:cb` commands
- keep character memory visible during writing

This is not the place for the full questionnaire/editor.

Split remains:

- **Character Studio** = creation and management
- **Write Page** = visibility and quick reference

---

## Part 4 — New Dialog web flow

In addition to CLI dialog generation, add a basic web UI flow for creating dialog drafts.

### Goal

Allow the user to generate a dialog draft from saved characters without going through CLI.

### Suggested entry point

Inside Character Studio and/or a separate Dialog area under Projects, provide:

- **New Dialog**

### V1 New Dialog inputs

At minimum:
- select character A
- select character B
- optional additional characters later
- scene / setting prompt
- mode:
  - dialog
  - scene
- quote usage controls:
  - use quotes on/off
  - quote mode
  - allow direct quotes
  - include authorial material

### Output

Output should be:
- readable in the web UI
- savable as a draft artifact
- stored to the same draft folders used by CLI generation

Suggested locations:
- `projects/<project>/dialog_drafts/`
- `projects/<project>/scene_drafts/`

### Web output behavior

After generation:
- show the draft in a readable editor/view
- allow the user to copy, edit, or insert later
- do not force immediate manuscript insertion

This is draft generation, not final publishing.

### Important product principle

Generated dialog is **proposed material**.
The user remains the editor and final decision-maker.

So the UI should make it natural to:
- inspect
- revise
- discard
- regenerate

---

## Part 5 — Recommended implementation order

Please implement in this order:

### Step 1
Extend schema and storage for:
- reference quotes
- speech patterns
- lexical markers
- authorial material

### Step 2
Update CLI dialog/scene generation to use new voice/quote material.

### Step 3
Build web Character Studio under Projects.

### Step 4
Add web Create/Edit Character flow using the questionnaire.

### Step 5
Add New Dialog web flow using saved characters.

### Step 6
Add lightweight character visibility to the main write page.

---

## Part 6 — Design constraints

### Keep outputs editable
Everything generated should remain easy to revise.

### Do not over-automate
Do not assume generated text is final or should be inserted automatically.

### Prefer readable outputs
- profiles = structured storage + readable rendering
- drafts = human-readable Markdown / text

### Keep schema shared
CLI and web must use the same underlying profile schema and storage logic.

### Avoid narrator collapse
Even if a character has strong source identity, do not automatically force the whole narration into that source style unless explicitly requested.

---

## Part 7 — Success criteria

This stage is successful if:

1. characters can store richer quote / voice material
2. dialog CLI can use that material meaningfully
3. users can manage characters in a dedicated web studio under Projects
4. users can generate new dialog drafts from the web UI
5. the write page shows enough character information to support command usage
6. the whole system still behaves as a suggestor / drafting assistant, not an automatic final writer

---

## Final note

The system should help users:
- remember characters
- find useful lines and materials
- preserve voice
- generate plausible interaction
- work faster without surrendering control

That is the point of this build stage.
