# ExtractionPatch_Immediate.md

## Purpose

This patch clarifies immediate next adjustments to the extraction pipeline based on observed results.

Important clarification:
- `reference_quotes[]` is already being extracted and is one of the stronger outputs
- so the immediate issue is not quote extraction
- the immediate issue is that some deeper inferred fields are being overfilled or weakly filled from insufficient evidence

In particular, fields such as:
- false_belief
- shame
- taboo
- pressure_response

often require stronger evidence or human interpretation.

This patch therefore focuses on:
1. reducing weak over-inference
2. improving how weak fields are handled
3. deciding how narrator extraction should work
4. making immediate practical fixes without redesigning the whole pipeline

---

## 1. Immediate conclusion from current results

The extraction pipeline is already strong at:
- candidate detection
- evidence collection
- draft profile synthesis
- reference quotes / dialogue material
- basic voice description
- core dialogue usability

The weakest part right now is:
- deep psychological fields inferred from incomplete evidence

So the next patch should not try to "extract more everything".

It should:
- become more conservative
- distinguish strong evidence from weak inference
- leave some fields intentionally provisional

---

## 2. Patch: weak deep fields should default to provisional

### Problem

Fields like:
- false_belief
- shame
- taboo
- pressure_response

are often difficult to infer reliably from prose evidence alone, especially for:
- minor characters
- externally described characters
- characters with limited introspection
- works with sparse psychological exposition

The current system risks filling these because the schema invites completion.

### Required behavior

For this phase, these fields should be treated as high-friction inference fields.

That means:
- if evidence is weak, leave them blank / null / uncertain
- do not force completion just because the questionnaire has the slot
- medium confidence should still be treated cautiously
- low-confidence fields should not read like settled truths in the saved profile

### Suggested rule

If a field is in the weak-inference set and the evidence is not clearly sufficient:
- store `null`
- or store an explicit uncertain placeholder
- and preserve the rationale in the extraction sidecar

### Weak-inference set

For now, treat at least these as weak-inference fields:
- `inner_engine.false_belief`
- `inner_engine.shame`
- `inner_engine.taboo`
- `behavior.pressure_response`

Optional also:
- `inner_engine.core_fear` for minor characters if evidence is weak
- `inner_engine.key_contradiction` if inferred only abstractly

---

## 3. Patch: narrator extraction

### Question

Can the extractor pick out the narrator of the work?

### Answer

Yes, but the narrator should be treated as a special character type, not as a normal character candidate.

### Why

The narrator can be highly important for:
- prose voice
- focalization
- perspective
- implicit judgement
- interpretive frame

But the narrator is not always:
- an ordinary diegetic character
- a participant in scenes
- a usable dialogue speaker in the same way as other characters

### Required behavior

Add narrator handling as a separate optional path.

#### For each book:
- detect whether there is a distinct narrator voice worth capturing
- if so, create a narrator profile draft

#### Narrator profile should be marked specially
Use something like:
- `character_type = narrator`
- or `role = narrator`
- or `source_mode = extracted_narrator`

### Important constraints

- every book/work should have its own narrator profile
- do not auto-merge narrators across books, even if they feel similar
- later, users can decide if they want to merge/adapt or treat them as related

### Narrator evidence

Narrator extraction should primarily use:
- non-dialogue narrative prose
- descriptive framing
- evaluative language
- recurring sentence style / cadence
- how the text observes characters and events

It should not be built from ordinary character dialogue evidence alone.

### Narrator selection rule

Do not force narrator extraction for every book in V1.
Instead:
- optionally add `Narrator` as a selectable candidate when confidence is sufficient
- or add a flag such as:
  - `:cb extract <author> --include-narrator`

This keeps the system practical.

---

## 4. Immediate patch: confidence calibration

### Problem

Some high-confidence values look too generous, especially for deep fields.

### Required behavior

Confidence assignment should be stricter.

Add prompt guidance such as:
- only assign HIGH confidence when multiple strong passages directly support the field
- if the field is mostly inferred from pattern rather than explicit evidence, prefer MEDIUM
- if the field is speculative or indirect, prefer LOW or leave blank

### Strong recommendation

Bias confidence downward by default for:
- false_belief
- shame
- taboo
- pressure_response
- contradiction when weakly evidenced

This will make the extraction output more trustworthy.

---

## 5. Immediate patch: evidence threshold for synthesis of deep fields

For weak-inference fields, require stronger evidence conditions before populating them.

Example criteria:
- at least 2–3 distinct supporting passages
- or repeated behavioral pattern plus direct speech support
- or explicit narrative framing

If that threshold is not met:
- do not fill the field strongly
- store uncertainty instead

This is better than inventing precision.

---

## 6. Immediate patch: candidate quality filtering

Based on the current outputs, candidate selection may still be slightly permissive.

Improve ranking by weighting:
- dialogue count
- action/reaction scene count
- chapter spread
- total evidence richness

Do not rely too heavily on raw mention count alone.

This should reduce weaker entities being promoted too easily.

---

## 7. Immediate patch: preserve extraction usefulness over literary perfection

The extraction pipeline is not trying to produce a final academic reading of the character.

It is trying to produce a usable draft for:
- Character Studio
- dialog generation
- later revision/update loop

So the correct strategy is:
- strongly extract what the text clearly gives
- preserve uncertainty for what it does not
- let the human + dialog loop refine the rest

That is the right balance.

---

## 8. Practical output change for weak fields

For extracted characters, weak deep fields should appear in one of three states:
1. populated with confidence
2. explicitly uncertain
3. absent / null

Do not present all fields as equally established.

If useful, Character Studio can later visually indicate:
- extracted with high confidence
- extracted with low confidence
- not yet established

---

## 9. Summary of immediate changes

Implement now:
1. Treat `false_belief`, `shame`, `taboo`, and `pressure_response` as weak-inference fields
2. Leave those fields blank / uncertain when evidence is weak
3. Tighten confidence calibration, especially for deep fields
4. Improve candidate ranking beyond mention count
5. Add optional narrator extraction as a special profile type per book
6. Keep narrators separate per work, not merged automatically

---

## 10. Recommended implementation priority

### First
- patch synthesis prompt for weak-field conservatism
- tighten confidence rules

### Second
- patch candidate ranking weights

### Third
- add narrator extraction as optional/special path

Do not redesign the whole pipeline yet.

---

## Final note

The extraction pipeline is already succeeding at:
- voice material
- evidence gathering
- draft profile bootstrapping

The immediate patch is about making it more honest where the text is weak, not more ambitious where the evidence is already strong.
