# CHARACTERBUILDER Module Specification (Full Version)
Project: Augmented Fiction  
Date: 2026-04-17  

---

# 1. Purpose

The `characterbuilder` module extracts, constructs, and stores **operational character profiles** from a corpus.

These profiles are used to:
- drive dialogue generation
- enforce voice consistency
- simulate interactions between characters
- condition rewrite passes

Goal:
Move from:
style imitation → character-conditioned generation

---

# 2. Pipeline Integration

## Current
EPUB → passages → segmentation → search → generation  

## New
EPUB → passages → segmentation  
        ↓  
   CHARACTERBUILDER  
        ↓  
characters/*.md  
        ↓  
generation (character-driven)  
        ↓  
rewrite (character-enforced)

---

# 3. Inputs

Required:
- segmented passages
- metadata:
  - source_file
  - passage_id
  - text
  - dialogue_ratio (if available)

Optional:
- mode_guess
- token-level stats
- speaker attribution (future)

---

# 4. Outputs

Directory:
modules/voice/turnofphrase/<author>/characters/

Files:
- one .md per character

Example:
western.md  
kline.md  

---

# 5. Character File Schema

Each file encodes constraints, not biography.

# Character: <name>

## Source
- author: <author>
- texts: [list]

## Core traits
- trait1
- trait2

## Speech patterns
- sentence length: short | medium | long
- question frequency: low | medium | high
- abstraction level: low | medium | high

## Lexical profile
- concrete noun ratio: float
- dominant verbs: physical | cognitive | mixed
- common tokens: []

## Dialogue behavior
- initiates vs reacts
- asserts vs asks
- deflects vs engages

## Pressure response
- under pressure: behavior
- when cornered: behavior

## Dialogue moves
- push
- resist
- deflect
- concede

## Structural tendencies
- uses fragments: yes/no
- repetition: low/medium/high
- metaphor: low/medium/high

## Anti-patterns
- things this character never does

## Example lines
- line1
- line2

---

# 6. Core Functions

## 6.1 Candidate Extraction (V1)

def extract_candidate_characters(passages):

Rules:
- only passages with dialogue_ratio > 0.5
- extract capitalized tokens
- filter:
  - length > 2
  - frequency ≥ 5
- remove stopwords

Goal:
Return 5–15 candidates

---

## 6.2 Profile Builder

def build_character_profile(passages):

Extract:
- sentence length distribution
- short sentence ratio
- question frequency
- verb type (physical vs cognitive)
- repetition patterns

---

## 6.3 Feature Extraction

def extract_features(text):

Features:
- avg sentence length
- % short sentences
- punctuation density
- fragment rate
- lexical concreteness

---

## 6.4 Dialogue Behavior Inference

def infer_dialogue_behavior(passages):

Outputs:
- initiator vs responder ratio
- question vs statement ratio
- line length variance

---

## 6.5 File Writer

def write_character_md(profile, path):

---

# 7. Extraction Heuristic (CRITICAL)

Minimal heuristic:

- count capitalized tokens
- cluster by frequency
- filter noise

Example output:

western (42)  
kline (31)  
kid (27)  

---

# 8. Workflow

1. Extract candidates
2. Manual inspection
3. Select top N (5–10)
4. Build profiles
5. Inspect profiles
6. Integrate into generation

---

# 9. Character Selection

def select_characters(prompt, profiles):

Logic:
- detect tension
- assign:
  - A = pushing
  - B = resisting

---

# 10. Generation Integration

Replace style-only prompting with:

simulate(Character A vs Character B)

Packet:

packet["characters"] = {
  "A": profile_A,
  "B": profile_B
}

---

# 11. Rewrite Integration

Rewrite enforces:

def validate_line(line, profile):

Reject if:
- too abstract
- wrong sentence length
- wrong behavior pattern

---

# 12. Minimal Viable Version

Start with:
- simple detection
- top 5–10 characters
- basic stats

Avoid:
- full NLP
- perfect attribution

---

# 13. Future Extensions

- speaker attribution via LLM
- archetype fallback
- cross-book merging
- dynamic blending
- memory across passages

---

# 14. Success Criteria

System works if:
- dialogue is non-generic
- speakers are distinct
- rewrite improves specificity
- outputs vary by character pair

---

# 15. Guiding Principle

Characters are not descriptions.  
Characters are constraint systems on language.

---

# END
