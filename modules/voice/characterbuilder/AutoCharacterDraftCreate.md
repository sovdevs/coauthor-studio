# AutoCharacterDraftCreate

## Purpose

This spec defines an automatic draft character creation pipeline from a collection of books.

The goal is not perfect extraction.

The goal is:
- to speed up character creation
- to bootstrap draft character profiles from source texts
- to reuse the same questionnaire/schema already used for manual character creation
- to let the writer refine and improve the result later in Character Studio and through the dialog feedback loop

This system should produce drafts, not final truths.

---

## Core idea

For each book:

1. identify candidate characters
2. collect textual evidence for each character into a raw character evidence file
3. run an LLM over that evidence using the existing character questionnaire/schema
4. produce a draft character profile
5. save the profile into the character system
6. allow normal editing, dialog generation, and dialog-revision-based refinement afterward

So the pipeline is:

book → raw evidence → draft questionnaire answers → editable character profile

---

## Product principle

This feature is a draft producer, not an oracle.

It should not claim to know the “true” character perfectly.

Instead it should:
- gather evidence
- synthesize a plausible draft profile
- mark uncertainty where evidence is weak
- hand the result to the writer for review and later refinement

---

## Why this approach

Do not invent a new ontology just for extraction.

The existing questionnaire/schema is already the right target format because it captures the dimensions that matter for later dialogue generation and character simulation.

Examples:
- desire
- fear
- contradiction
- how they speak
- how they behave under pressure
- relational tendencies
- voice markers

So the extraction pipeline should aim to answer the same questions the human questionnaire answers.

---

## Scope

Input:
- a single book
- or a collection of books

Target source type for first implementation:
- books / EPUB-derived text

Later possible extensions:
- scripts
- screenplays
- transcripts
- subtitles
- essays / memoir
- other narrative text

---

## Pipeline overview

### Step 1 — Ingest book text

The system should load the book in a form that preserves usable structure.

Minimum useful structure:
- chapter boundaries
- paragraph boundaries
- quotation marks / dialogue blocks if available

The exact parser can vary.
The important part is that the text remains chunkable and attributable.

---

### Step 2 — Identify candidate characters

The system should extract candidate character names / entities.

This step can be heuristic, NLP-based, or LLM-assisted.

For this phase, perfect resolution is not required.
The purpose is to generate a usable candidate list.

Important:
Do not assume every detected person-like name deserves a full profile.

The system should rank or filter candidates using signals such as:
- frequency of mention
- frequency of speech
- narrative prominence
- chapter spread
- amount of usable evidence

At minimum, the system should be able to propose:
- top N candidate characters per book

Optional:
- let the user choose which candidates to build

---

### Step 3 — Build raw evidence files per character

For each selected character, create a raw evidence file.

This is one of the most important design decisions.

Do not jump straight from entity mentions to final profile.

Instead, collect evidence first.

Each raw evidence file should gather at least these buckets:

#### A. Direct speech
Everything the character says, or likely says.

Usefulness:
- speech patterns
- lexical markers
- rhythm
- directness / evasiveness
- quote bank

#### B. Narrative description
Passages where the narrator or other characters describe the character.

Usefulness:
- appearance
- social role
- reputation
- visible behavior
- demographics clues

#### C. Action / reaction scenes
Passages where the character acts, reacts, chooses, pressures, avoids, or is pressured.

Usefulness:
- desire
- fear
- tactics
- contradiction
- behavior under pressure

#### D. Other characters’ views (optional but useful)
Passages where other characters judge, describe, or frame this character.

Usefulness:
- public self
- social perception
- status
- relational tendencies

#### E. Source references
Store chapter / location references so the evidence remains traceable.

---

## Raw evidence file format

Use a readable file format such as Markdown or structured JSON.

A readable Markdown structure is recommended first.

Example:

```md
# Character Raw Evidence: Bob

## Mentions / Description
...

## Spoken Dialogue
...

## Action / Reaction Scenes
...

## Other Characters' Views
...

## Source References
- Chapter 2
- Chapter 5
- Chapter 8
```

This is not the final profile.
It is the evidence dossier used to synthesize the draft character.

---

## Step 4 — Questionnaire-style synthesis

Once the raw evidence file exists, run an LLM over it using the same conceptual structure as the manual character questionnaire.

The LLM’s job is to produce a draft profile, not an invented total explanation.

Important prompt instructions:
- answer the character questions using the evidence
- prefer directly supported claims
- distinguish observed vs inferred material
- mark uncertainty if evidence is weak
- do not invent hidden motives unless evidence strongly supports them
- preserve useful voice clues from the text

This keeps the system grounded.

---

## Prompt target

The target output should map into the same character schema already used by:
- CLI create
- web Character Studio
- dialog generation
- dialog feedback loop

This means the extracted draft should be compatible with the rest of the system with minimal translation.

---

## Confidence and evidence

For auto-generated character drafts, some fields will be much more reliable than others.

For example:
- speech style may be strongly evidenced
- contradiction may require more inference
- shame or hidden fear may be weakly supported

So the synthesis step should ideally include, for major fields:
- field value
- confidence level
- short evidence note or rationale

Especially useful for:
- desire
- fear
- contradiction
- speech style
- regionalism
- pressure behavior

The exact representation is flexible, but uncertainty should be preserved.

---

## Step 5 — Save draft profile

After synthesis:
- save the result as a character profile in the normal character system
- mark `source_mode` as something like `extracted` or `auto_draft`
- preserve:
  - source book
  - source author
  - generation timestamp
  - maybe confidence summary

This draft then becomes editable in Character Studio like any other character.

---

## Step 6 — Human review and refinement

The extracted profile is not final.

The writer should be able to:
- open it in Character Studio
- inspect the generated profile
- edit any field
- add/remove voice material
- generate dialog from it
- revise dialog
- update the character through the existing delta loop

This means the extraction stage is a bootstrap, not a separate dead-end system.

---

## Key product principle

Extraction should feed the same long-term loop as manually created characters:
- create draft
- generate dialog
- writer revises
- profile updates
- character improves

This unifies the whole system.

---

## Candidate selection policy

Do not auto-build every detected character in a long book.

Use a thresholding strategy.

Suggested first policy:
- build only top N candidates by evidence volume / prominence

Optional better flow:
1. system detects candidates
2. system shows candidate list
3. user selects which characters to draft

This prevents noise from minor walk-on characters.

---

## Multi-book collections

If the input is a collection of books:
- process each book separately first
- then later allow optional consolidation / merging if the same character recurs across a series

Do not assume automatic perfect merging in V1.

Series handling can come later.

---

## Architecture suggestion

Suggested module area:

characterbuilder/
  extract/
    ingest.py
    candidate_detection.py
    evidence_builder.py
    questionnaire_synthesis.py

Possible command shape:

:cb extract <book_or_collection_path>

Possible sub-flow:
- ingest
- detect candidates
- build evidence files
- synthesize draft profiles
- save to registry

---

## What the system should not do

Do not:
- pretend extracted profiles are definitive
- force deep psychological claims with weak evidence
- rewrite the existing schema around extraction needs
- build every minor entity into a character
- skip evidence capture and jump directly to summary

The evidence dossier is essential.

---

## Good update targets from extraction

Extraction is especially good for:
- speech style
- lexical markers
- quote bank
- visible habits
- public self
- regionalism hints
- social role
- class register clues
- recurring action tendencies

Extraction is weaker for:
- hidden shame
- deep contradiction
- repressed motives
- precise fear/desire if the text is indirect

So those deeper fields should be allowed to remain uncertain or provisional.

---

## Relationship to later dialog generation

The extracted draft profile should be immediately usable for:
- dialog generation
- scene generation
- internal self-dialogue
- later correction and profile update

This means extraction should not aim for perfect literary analysis.
It should aim for usable generative readiness.

---

## Suggested writer-facing flow

1. import book or collection
2. system proposes candidate characters
3. user selects characters to draft
4. system generates raw evidence files
5. system generates draft profiles using the questionnaire target
6. user reviews/edit in Character Studio
7. user tests dialog
8. user refines through revision loop

---

## Example prompt direction for synthesis

The exact prompt can vary, but its role is:
- use the evidence dossier
- answer the existing character questionnaire/schema
- mark what is directly observed vs inferred
- mark low-confidence fields as uncertain
- preserve language clues useful for later dialog generation

The prompt should behave like:
- evidence-based profile construction
not:
- unconstrained literary interpretation

---

## Success criteria

This phase is successful if:
1. a book can be ingested into structured text
2. the system can propose candidate characters
3. the system can build raw evidence files per selected character
4. an LLM can turn those evidence files into draft profiles using the existing questionnaire/schema
5. those draft profiles can be loaded into Character Studio
6. the profiles are usable immediately for dialog generation
7. the writer can refine them afterward using the normal edit / revision loop

---

## Final note

This feature should not replace manual character creation.

It should accelerate it.

The correct mental model is:

automatic draft creation from textual evidence, followed by normal human-guided refinement
