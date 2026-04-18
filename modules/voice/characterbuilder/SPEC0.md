CHARACTERBUILDER Module Specification

Project: Augmented Fiction
Date: 2026-04-17

⸻

1. Purpose

The characterbuilder module extracts, constructs, and stores operational character profiles from a corpus.

These profiles are later used to:
	•	drive dialogue generation
	•	enforce voice consistency
	•	simulate interactions between characters

The goal is to move from:

style imitation → character-conditioned generation

⸻

2. Module Position in Pipeline

Current pipeline

EPUB → passages → segmentation → search → generation

New pipeline

EPUB → passages → segmentation  
        ↓
   CHARACTERBUILDER  
        ↓
characters/*.md  
        ↓
generation (with character conditioning)


⸻

3. Inputs

Required
	•	segmented passages (existing output of passage_segmenter)
	•	metadata per passage:
	•	source_file
	•	passage_id
	•	text
	•	mode_guess (if available)

Optional (future)
	•	speaker attribution (if detected)
	•	dialogue ratio
	•	token-level stats

⸻

4. Outputs

Directory

modules/voice/turnofphrase/<author>/characters/

Files

One .md file per detected character:

judge_holden.md
the_kid.md
western.md
...


⸻

5. Character File Schema (character.md)

Each file contains behavioral constraints, not biography.

# Character: <name>

## Source
- author: <author>
- primary texts: [file1.epub, file2.epub]

## Core traits
- <trait1>
- <trait2>

## Speech patterns
- sentence length: short | medium | long
- question frequency: low | medium | high
- abstraction level: low | medium | high

## Lexical profile
- concrete noun ratio: <float>
- dominant verbs: physical | cognitive | mixed
- common tokens: [list]

## Dialogue behavior
- initiates vs reacts
- asks vs asserts
- deflects vs engages

## Pressure response
- under pressure: <behavior>
- when cornered: <behavior>

## Dialogue moves
- push
- resist
- deflect
- concede

## Structural tendencies
- uses fragments: yes/no
- uses repetition: yes/no
- uses metaphor: low/medium/high

## Anti-patterns
- things this character never does

## Example lines (from corpus)
- "<example1>"
- "<example2>"


⸻

6. Core Functions

6.1 Character Detection

def detect_characters(passages: List[Passage]) -> List[str]

Initial implementation (simple)
	•	detect capitalized recurring tokens in dialogue-heavy passages
	•	fallback: cluster by speaking style (if no names)

⸻

6.2 Character Profile Builder

def build_character_profile(passages: List[Passage]) -> CharacterProfile

Extract:
	•	sentence length distribution
	•	dialogue ratio
	•	question frequency
	•	abstraction vs concreteness
	•	verb types
	•	repetition patterns

⸻

6.3 Feature Extraction

def extract_features(text: str) -> Dict

Features:
	•	avg sentence length
	•	% short sentences
	•	noun concreteness (heuristic)
	•	verb classification (physical vs cognitive)
	•	punctuation usage
	•	fragment frequency

⸻

6.4 Dialogue Behavior Inference

def infer_dialogue_behavior(passages) -> Dict

Outputs:
	•	initiator vs responder ratio
	•	question vs statement ratio
	•	interruption patterns (future)

⸻

6.5 Character File Writer

def write_character_md(profile: CharacterProfile, output_path: Path)


⸻

7. Integration Points

7.1 Pipeline Hook

In run_pipeline():

if enable_characterbuilder:
    characters = build_all_characters(passages)


⸻

7.2 Generation Hook

Modify generation packet:

packet["characters"] = {
    "A": character_A_profile,
    "B": character_B_profile
}


⸻

8. Character Selection (Reasoner Interface)

def select_characters(prompt: str, characters: List[CharacterProfile]) -> Tuple[A, B]

Initial logic:
	•	detect tension keywords → assign roles:
	•	A = pushing agent
	•	B = resisting agent

⸻

9. Generation Changes

Replace style-only prompting with:

simulate(Character A vs Character B under constraint X)

Prompt structure:

## Character A
[profile]

## Character B
[profile]

## Scene
[prompt]

## Rules
- each line must be a move
- characters must follow profiles


⸻

10. Rewrite Integration

Rewrite now enforces:

def validate_line(line, character_profile):
    # reject if:
    # - too abstract for character
    # - wrong sentence length
    # - wrong behavior pattern


⸻

11. Minimal Viable Version (IMPORTANT)

Start with:
	•	no perfect character detection
	•	no full NLP pipeline

Just:
	•	cluster passages
	•	extract stats
	•	generate 5–10 profiles

⸻

12. Future Extensions
	•	speaker attribution via LLM
	•	cross-book character merging
	•	archetype fallback (if no characters found)
	•	dynamic character blending
	•	memory across passages

⸻

13. Success Criteria

The module is successful if:
	•	dialogue stops sounding generic
	•	lines differ clearly between speakers
	•	rewrite removes abstract filler automatically
	•	same prompt produces different dialogue depending on characters

⸻

14. Guiding Principle

Characters are not descriptions.
Characters are constraint systems on language.

⸻

END SPEC