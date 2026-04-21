# Claude Build Spec — UPDATED (User-Scoped Characters, Quotes, Character Studio, Dialog)

## Key Architecture Update (IMPORTANT)

Characters are **user-level assets**, not project-level assets.

Model:
- A user owns many characters
- A user owns many projects
- Any project can use any character owned by that user

Implications:
- Canonical Character Studio lives at `/characters`
- Projects DO NOT own characters
- Projects only reference characters

So:
- storage = user-scoped
- usage = project-scoped

Optional (later):
- project-specific views (recent, attached characters)
- NOT a separate character store

---

## 1. Character Studio URL / Scoping

Use:

- `/characters` (global user-level studio)

Behavior:
- manages the global character registry
- supports create/edit/import/export

Dialog generation:
- requires project context for saving drafts
- UI should:
  - auto-detect current project if entered from project
  - OR allow selecting a project before generation

---

## 2. Schema — Voice / Quote System

Extend schema with:

- `reference_quotes[]` (structured)
- `authorial_material[]` (structured)
- `speech_patterns[]` (list[str])
- `lexical_markers[]` (list[str])

### reference_quotes[]
Fields:
- text
- source
- is_canonical
- added_by_user
- tone
- notes

### authorial_material[]
Fields:
- text
- source_type (quote/theme/argument/etc)
- source
- notes
- direct_use_allowed
- paraphrase_preferred

### speech_patterns[] and lexical_markers[]
V1:
- simple list[str]

---

## 3. CLI Dialog Integration

Extend:

:cb dialog <idA> <idB> --setting "..."

Add flags:
- --use-quotes
- --quote-mode auto|light|strong
- --allow-direct-quotes
- --include-authorial-material
- --speaker-focus <id>

Behavior:
- quotes guide voice
- do not copy unless allowed
- authorial material = optional insertion pool

---

## 4. Interview Design

Keep current interview focused.

DO NOT overload creation.

Add optional enrichment step:

"Add voice material now? [y/N]"

Main enrichment happens in:
- :cb edit
- Web Character Studio

---

## 5. Web Character Studio

Location:
- `/characters`

Provides:
- list
- search/filter
- create/edit
- full questionnaire
- voice/quote editing

Display:
- display name
- character ID
- type badge

---

## 6. Write Page

Add lightweight character panel:
- display names
- IDs
- badges

Purpose:
- reference for CLI
- not full editor

---

## 7. New Dialog Web Flow

Entry:
- "New Dialog"

Inputs:
- select characters
- setting
- mode (dialog/scene)
- quote controls

Output:
- rendered draft
- saved to:
  projects/<project>/dialog_drafts/

Editable, not auto-inserted.

---

## 8. Data Model Summary

Ownership:
- user_id → characters

Usage:
- project_id → references character_ids

---

## 9. Principle

Characters = reusable assets  
Projects = contexts that use them  

---

## 10. Success Criteria

- characters reusable across projects
- dialog uses quote/voice system
- UI supports creation + reuse
- outputs remain editable drafts
