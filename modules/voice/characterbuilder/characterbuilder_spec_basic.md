# CHARACTERBUILDER Module Specification  
Project: Augmented Fiction  
Date: 2026-04-17  

---

# 1. Purpose

The `characterbuilder` module extracts, constructs, and stores operational character profiles from a corpus.

These profiles are used to:
- drive dialogue generation
- enforce voice consistency
- simulate interactions between characters

Goal:
Move from style imitation → character-conditioned generation

---

# 2. Pipeline Integration

Current:
EPUB → passages → segmentation → search → generation  

New:
EPUB → passages → segmentation  
        ↓  
   CHARACTERBUILDER  
        ↓  
characters/*.md  
        ↓  
generation (character-driven)

---

# 3. Inputs

Required:
- segmented passages
- passage metadata:
  - source_file
  - passage_id
  - text
  - dialogue_ratio (if available)

---

# 4. Outputs

Directory:
modules/voice/turnofphrase/<author>/characters/

Files:
- one .md per character

---

# 5. Character File Schema

# Character: <name>

## Core traits
- trait1
- trait2

## Speech patterns
- sentence length: short | medium | long
- question frequency: low | medium | high

## Dialogue behavior
- initiates vs reacts

## Pressure response
- behavior under pressure

---

# 6. Core Functions

def extract_candidate_characters(passages):
    pass

def build_character_profile(passages):
    pass

---

# 7. Workflow

1. Extract candidates
2. Inspect manually
3. Build top N profiles
4. Integrate into generation

---

# 8. Guiding Principle

Characters are constraint systems on language.
