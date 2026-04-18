"""
Post-generation rewrite pass for dialogue mode.

Transforms a structurally correct but potentially generic draft into
higher-quality dialogue with verbal pressure, asymmetry, and specificity.

Only applied when:
  - generation mode is dialogue
  - --rewrite flag is passed at CLI

Usage:
    from .rewrite_service import rewrite_dialogue_pass
    final = rewrite_dialogue_pass(draft_text, context, client, model)
"""
from __future__ import annotations

from .prompt_loader import load_prompt


def rewrite_dialogue_pass(
    draft_text: str,
    context: dict,
    client,
    model: str = "gpt-4o",
    temperature: float = 0.75,
) -> str:
    """
    Run a second-pass rewrite on a dialogue draft.

    Args:
        draft_text: the generated draft passage
        context:    dict with at least 'writer_id'; optionally 'mode_notes'
        client:     an initialised OpenAI client
        model:      model name (default gpt-4o)
        temperature: generation temperature

    Returns:
        Rewritten passage string.
    """
    template = load_prompt("rewrite/dialogue_rewrite.md")

    writer_id = context.get("writer_id", "unknown").replace("_", " ").title()
    prompt = template.replace("{writer_id}", writer_id).replace("{draft_text}", draft_text)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a precise literary rewriting system. "
                    "Follow all constraints exactly. "
                    "Output only the rewritten prose passage."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()
