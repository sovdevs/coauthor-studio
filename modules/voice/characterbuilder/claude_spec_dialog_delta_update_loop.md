# Claude Spec — Next Phase: Dialog Editing, Delta Generation, and Character Update Loop

## Purpose

This phase adds the feedback loop after dialog generation.

Current state:
- a character profile is created from the questionnaire
- the system generates a dialog draft
- the writer can copy the draft

Next phase:
- the writer must be able to edit the generated dialog
- submit that edited version for delta generation
- the system must infer what changed
- the system must propose and apply character profile updates
- the writer can then regenerate until the draft is satisfactory

This phase is about turning the system from:
- questionnaire → draft

into:
- questionnaire → draft → writer correction → profile update → better draft

---

## Core principle

The writer is not directly “editing the character.”

The writer edits the generated dialog.

The system then infers:
- what this correction implies about the character
- which fields in the character profile should be updated

So the loop is:

1. generate draft
2. writer edits draft
3. submit edited draft
4. generate delta
5. update character profile
6. regenerate if desired

---

## Product goal

Enable an iterative loop where the character improves through corrected output.

This is not yet about writer-level preference learning.
That comes later.

For now:
- correction updates the character
- not a separate writer preference model

---

## User flow

### Existing flow
- choose characters
- choose setting
- generate dialog draft

### New flow
After generation:
- show generated draft in an editable text area / editor
- allow writer to revise the text directly
- provide a button such as:
  - Submit revision for character update
  - or Learn from revision

Then:
- system compares generated draft vs revised draft
- system infers a structured delta
- system proposes profile updates
- system applies accepted updates to the character profile
- writer can regenerate the dialog using the updated profile

---

## Scope for this phase

This phase should support:

1. single-speaker internal self-dialogue (A == B)
2. normal dialog with multiple speakers (A != B)

But the update logic should initially be conservative.

Especially for multi-character dialog:
- the system must identify which speaker(s) were revised
- profile updates should only be proposed for the relevant character(s)

---

## Main architecture

This phase has four core components:

### 1. Editable dialog draft UI
A web UI where the generated dialog draft can be edited.

### 2. Delta generation step
A structured comparison between:
- original generated dialog
- revised dialog
- current character profile(s)

### 3. Profile update mapper
A deterministic mapping from inferred deltas to character profile updates.

### 4. Regeneration loop
The writer can generate again after the character has been updated.

---

## Part 1 — Editable dialog draft UI

### Requirement

After dialog generation, the generated output must appear in an editable area.

The writer should be able to:
- change wording
- rewrite lines
- delete lines
- add lines
- keep speaker labels where relevant

### Suggested UI

On the Dialog page:

- left: inputs (characters, setting, options)
- right: generated draft

After generation:
- render the draft in an editable text area or simple editor
- preserve the metadata separately
- only the dialog content itself should be edited

### Required actions

Buttons:

- Generate
- Submit revision for character update
- Regenerate with updated character
- optionally Reset to generated draft

Optional later:
- diff view
- per-line highlighting
- partial acceptance

For this phase, a simple editable block is enough.

---

## Part 2 — Delta generation

### Inputs

The delta generation step should receive:

1. character profile(s)
2. original generated dialog
3. revised dialog
4. metadata:
   - mode
   - setting
   - speaker IDs / character IDs
   - internal vs external

### Goal

Infer what changed in a structured way.

The delta generation step should not rewrite the profile directly.
It should output a delta object.

### Delta object concept

A delta object should identify:

- which character(s) are affected
- what changed in the revised output
- what profile implications are likely

Examples of change labels:
- less_explicit_self_analysis
- more_fragmented_under_pressure
- more_regional_idiom
- more_evasive
- less_polite
- more_direct
- more_repetitive
- less_balanced
- more_guarded
- less_explanatory

For this phase, use the current LLM-based path if needed, but structure the output carefully.

---

## Part 3 — Mapping delta to profile updates

### Important rule

The delta generator should not be allowed to freely rewrite the whole character profile.

Instead:

- infer structured labels
- map those labels to bounded profile updates via deterministic code

### Why

This keeps updates:
- stable
- inspectable
- reversible
- incremental

### Example mapping

- less_explicit_self_analysis
  → decrease explicit self-awareness field
- more_fragmented_under_pressure
  → increase fragmentation under pressure
- more_regional_idiom
  → strengthen regionalism / lexical markers
- more_evasive
  → increase avoidance / deflection tendency
- more_repetition_under_pressure
  → increase repetition pattern

### Update policy

Updates should be:
- incremental
- bounded
- confidence-aware

Do not let a single revision massively redefine the character.

---

## Part 4 — Character update review

### Requirement

Before final profile update, show the writer what the system inferred.

Display something like:

- Detected changes:
  - less explicit self-analysis
  - more fragmented under pressure
  - stronger regional idiom

- Proposed profile updates:
  - self-awareness: down
  - fragmentation: up
  - regionalism strength: up

The writer should be able to:
- accept all
- reject all
- ideally later accept selectively

For this phase, accept-all / reject-all is enough.

---

## Part 5 — Multi-character dialog handling

### Internal self-dialogue (A == B)

Simplest case:
- one character
- one profile
- one set of updates

### External dialog (A != B)

The system must identify whose lines were revised.

For this phase, use a practical heuristic:

- speaker-labeled dialog is expected
- compare revisions by speaker block
- only propose updates for the character whose lines changed materially

If both were changed:
- propose deltas for both

If uncertain:
- show low confidence
- avoid aggressive updates

### Important constraint

Do not let changes to one character contaminate another character’s profile.

---

## Part 6 — What fields should be updateable in this phase

Focus on fields that are good candidates for incremental change from dialogue revision.

### Good update targets
- verbosity
- fragmentation
- explicitness / self-awareness
- directness
- evasiveness
- bluntness / politeness
- repetition under pressure
- regionalism strength
- lexical markers
- speech patterns
- confidence / guardedness in dialogue

### Do not auto-update aggressively yet
- core desire
- core fear
- shame
- contradiction
- story role

Those are deeper structural fields and should only change with stronger evidence.

For now, treat them as stable unless later explicitly edited by the writer.

---

## Part 7 — Storage and logging

### Requirement

Every revision cycle should be logged.

Store:

- original generated dialog
- revised dialog
- inferred delta
- proposed updates
- accepted/rejected status
- resulting profile snapshot or diff
- timestamp

### Purpose

This enables:
- auditability
- later training data
- rollback/debugging
- future writer preference learning

Suggested concept:
- dialog_revision_log
- profile_update_log

The exact file structure is flexible, but persistence is required.

---

## Part 8 — Regeneration loop

After accepting updates:

- write the updated character profile
- allow the writer to regenerate immediately from the same dialog page
- keep:
  - same setting
  - same character selection
  - same options unless changed manually

This should make the loop feel fast and iterative.

Flow:

1. generate draft
2. edit draft
3. submit revision
4. accept update
5. regenerate

---

## Part 9 — UI requirements summary

### Dialog page must now support

- generated draft display
- editable dialog content
- submit revision for update
- inferred delta display
- proposed profile update display
- accept/reject update
- regenerate with updated character

### Character Studio should reflect updates

After accepted updates:
- character profile in Character Studio should show the new values
- update should be persistent

Optional later:
- show profile history / recent learned changes

---

## Part 10 — Suggested data flow

generate dialog
→ writer edits dialog
→ submit revision
→ delta generation
→ delta object
→ deterministic profile updater
→ proposed profile updates
→ writer accept/reject
→ save updated character
→ regenerate

---

## Part 11 — Example delta object

Example only; exact schema can vary.

```json
{
  "mode": "internal",
  "affected_characters": [
    {
      "character_id": "me__bob",
      "changes": [
        {"label": "less_explicit_self_analysis", "confidence": 0.83},
        {"label": "more_fragmented_under_pressure", "confidence": 0.76},
        {"label": "more_regional_idiom", "confidence": 0.68}
      ],
      "proposed_updates": [
        {"field": "voice.self_awareness", "direction": "down", "amount": 0.1},
        {"field": "voice.fragmentation", "direction": "up", "amount": 0.1},
        {"field": "demographics.regionalism_strength", "direction": "up", "amount": 0.05}
      ]
    }
  ]
}
```

---

## Part 12 — Constraints

### Keep the loop simple
Do not overbuild line-level annotation tools yet.

### Preserve human control
The writer must approve updates before they become canonical.

### Prefer bounded changes
Do not let one revision radically rewrite the character.

### Keep output editable
This remains a suggestor system, not an automatic final authoring tool.

### Build for future learning
All logs and accepted deltas should be stored in a form that can later train:
- a local delta model
- a writer preference model
- a dialogue revision model

But those come later.

---

## Part 13 — Success criteria

This phase is successful if:

1. generated dialog can be edited directly in the web UI
2. the edited dialog can be submitted for delta generation
3. the system can infer structured profile deltas
4. profile updates are proposed in a controlled, inspectable way
5. the writer can accept/reject updates
6. accepted updates change the character profile persistently
7. the writer can regenerate immediately with the improved character
8. all revision/update cycles are logged for later training

---

## Final note

This phase is the bridge from:
- static character setup

to:
- character learning through dialogue revision

That is the key step that makes the system improve through use.
