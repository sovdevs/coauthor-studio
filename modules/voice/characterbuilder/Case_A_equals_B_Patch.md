# Case: A == B Patch

## Purpose

This patch defines the required behavior when the same character is selected twice for dialog generation.

Example:

- `:cb dialog me__bob me__bob --setting "at a petrol station"`

In this case, the system should assume **internal self-dialogue**.

This is effectively:

- `--mode internal`
- or `self-dialogue`

even if that flag was not explicitly provided.

---

## Problem

Current behavior incorrectly treats the same character as two separate people and invents contrast by splitting the character into:

- impulsive self vs critical self
- desire vs conscience
- ego vs anti-ego

This can be interesting, but it should not happen accidentally in standard two-character dialog mode.

When the same character is selected twice:

- there should still be tension
- but both speakers must clearly feel like the same person

---

## Required behavior

### Detection

In `dialog.py`, detect when:

- `char_a.character_id == char_b.character_id`

If true:
- switch to internal self-dialogue behavior automatically

---

## Internal self-dialogue rules

When the same character appears twice:

### 1. Same identity
Both sides must clearly be the same person.

Do NOT write them as:
- two different personalities
- two different moral systems
- two separate social identities
- one "good twin" and one "bad twin"

### 2. Preserve voice
Both sides must preserve the same:
- speech rhythm
- diction
- lexical habits
- level of formality
- source imprint
- accent / regionalism if present

They may differ in stance, but not in identity.

### 3. Allow internal tension
Tension is required.

Valid tension includes:
- doubt
- rationalization
- self-justification
- second thoughts
- shame
- temptation
- fear
- rehearsal
- mental argument
- trying to talk oneself into or out of something

### 4. No hard personality split
The two sides may emphasize different impulses or pressures, but should not become:
- prosecutor vs defendant
- hero vs villain
- external critic vs separate friend

It should feel like:
- thinking aloud
- arguing with oneself
- inner rehearsal
- pressure inside one mind

### 5. Same-character labeling
Output can still use speaker labels for readability, but the prompt should frame them as two sides / turns of the same mind.

Optional later:
- relabel as `Bob (1)` / `Bob (2)`
- or `Bob / Bob`
- or `Bob / Inner Bob`

For now, readability is fine, but identity must remain unified.

---

## Prompt patch

When `A == B`, append or switch to an instruction block like:

```text
The same character has been selected twice.

Treat this as internal self-dialogue.

Rules:
- Both sides are the same person.
- Preserve the same voice, diction, rhythm, and habitual phrasing on both sides.
- Allow tension, doubt, rationalization, and self-argument.
- Do not turn them into two different personalities.
- Do not make one side feel like an external friend, critic, or antagonist.
- The exchange should feel like one mind under pressure, divided in emphasis but not identity.
- Keep the language natural and readable as draft material.
```

---

## Behavioral goal

The result should feel like:

- one person debating themselves
- one person rehearsing what to do
- one person trying to justify something to themselves
- one person split by pressure, but still recognizably one person

NOT like:
- two different men at a petrol station
- one version of the character being "anti-character"
- one side becoming a generic moralizing foil

---

## Examples of acceptable internal tension

Good:
- "Come on, it's nothing."
- "You know it isn't nothing."
- "I said I'll keep it light."
- "That's what you always say."

This works because:
- same cadence
- same social register
- same identity
- different inner emphasis

Bad:
- one side becomes formally wiser
- one side sounds older / more moral / more literary than the other
- one side behaves like a separate confidant

---

## Implementation suggestion

Pseudo-logic:

```python
same_character = char_a.character_id == char_b.character_id

if same_character:
    mode = "internal"
    prompt_variant = "self_dialogue"
else:
    mode = requested_mode or "dialog"
    prompt_variant = "normal_dialogue"
```

No extra user action is required.
Selecting the same character twice should be enough to activate this behavior.

---

## Future idea (not required now)

Later, add an explicit command or UI mode such as:

- `:cb self <id> --setting "..."`
- `--mode internal`

But for now:
- same character twice = internal self-dialogue automatically

---

## Success criteria

This patch is successful if:

1. selecting the same character twice no longer produces two separate-feeling people
2. internal tension still exists
3. both sides retain the same voice and identity
4. the result feels like self-debate, rehearsal, or rationalization rather than external confrontation

---

## Note

This is a useful feature, not just a bug fix.

Handled correctly, same-character dialog can become a strong tool for:
- character development
- internal conflict
- scene preparation
- self-justifying or self-divided protagonists


Part 2
Add these aspects to a character's profile and therefore to the questionnaire


1. age/generation
2. sex/gender
3. regionalism/accent (will come from an accent file for the LLM)
4. bodily constraint / notable physical condition (default none)
5. class/education register 

Part 3
In the CHARACTERS menu, it should be possible to DUPLICATE (within the Character detail next to GENERATE IALOG and DELETE)
the character to allow for generating similar characters.

What would be the export format for this character a Markeodwn file or a JSON File?