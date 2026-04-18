"""
Prompt file loader for TurnOfPhrase.

Prompts live at <project_root>/prompts/ — outside the src tree so they can be
edited without touching Python source.

Usage:
    from .prompt_loader import load_prompt
    text = load_prompt("rewrite/dialogue_rewrite.md")
"""
from __future__ import annotations

from pathlib import Path

# Project root is 5 levels above this file:
# turnofphrase/ → voice/ → modules/ → augmented_fiction/ → src/ → <root>
PROMPT_ROOT = Path(__file__).parents[5] / "prompts"


def load_prompt(relative_path: str) -> str:
    """
    Load a prompt file by path relative to the prompts/ directory.

    Raises FileNotFoundError with a clear message if the file is missing.
    """
    path = PROMPT_ROOT / relative_path
    if not path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {path}\n"
            f"Expected prompts root: {PROMPT_ROOT}"
        )
    return path.read_text(encoding="utf-8")
