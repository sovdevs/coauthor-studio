"""
Character profile storage.

Global registry:
    modules/voice/characterbuilder/characters/<character_id>.json

Author-local (auto-synced when source_author is known and mode is extracted/imported):
    modules/voice/turnofphrase/<author_slug>/characters/<character_id>.json

Save always writes to the global registry.
Author-local sync happens automatically on save when the parent directory exists.
"""
from __future__ import annotations

import json
from pathlib import Path

from augmented_fiction.modules.voice.characterbuilder.schema import (
    CharacterProfile,
    Provenance,
    _slugify,
    profile_from_dict,
    profile_to_dict,
    profile_to_markdown,
)

_REGISTRY_ROOT = Path("modules/voice/characterbuilder/characters")


# ── Path helpers ──────────────────────────────────────────────────────────────

def registry_json_path(character_id: str) -> Path:
    return _REGISTRY_ROOT / f"{character_id}.json"


def _local_json_path(author_slug: str, character_id: str) -> Path:
    return Path(f"modules/voice/turnofphrase/{author_slug}/characters/{character_id}.json")


# ── Core operations ───────────────────────────────────────────────────────────

def save_character(profile: CharacterProfile) -> None:
    """
    Write profile to global registry JSON.
    Auto-sync to author-local directory when:
    - source_author is set
    - source_mode is 'extracted' or 'imported'
    - the parent turnofphrase/<author> directory already exists
    """
    _REGISTRY_ROOT.mkdir(parents=True, exist_ok=True)
    reg_path = registry_json_path(profile.character_id)

    # Update provenance before writing
    profile.provenance.registry_path = str(reg_path)

    data = profile_to_dict(profile)
    reg_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    # Auto-sync to author-local space
    if profile.source_author and profile.source_mode in ("extracted", "imported"):
        author_slug = _slugify(profile.source_author)
        loc_path = _local_json_path(author_slug, profile.character_id)
        if loc_path.parent.parent.exists():  # turnofphrase/<author>/ must exist
            loc_path.parent.mkdir(parents=True, exist_ok=True)
            loc_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            profile.provenance.local_path = str(loc_path)
            # Re-write registry with updated local_path
            data = profile_to_dict(profile)
            reg_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def load_character(character_id: str) -> CharacterProfile:
    path = registry_json_path(character_id)
    if not path.exists():
        raise FileNotFoundError(f"Character not found: {character_id}")
    return profile_from_dict(json.loads(path.read_text(encoding="utf-8")))


def list_characters() -> list[CharacterProfile]:
    if not _REGISTRY_ROOT.exists():
        return []
    profiles: list[CharacterProfile] = []
    for f in sorted(_REGISTRY_ROOT.glob("*.json")):
        try:
            profiles.append(profile_from_dict(json.loads(f.read_text(encoding="utf-8"))))
        except Exception:
            pass
    return profiles


def existing_ids() -> set[str]:
    if not _REGISTRY_ROOT.exists():
        return set()
    return {f.stem for f in _REGISTRY_ROOT.glob("*.json")}


def delete_character(character_id: str) -> bool:
    """Delete from global registry. Returns True if deleted, False if not found."""
    path = registry_json_path(character_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def export_markdown(character_id: str) -> str:
    """Return the Markdown dossier for a character."""
    profile = load_character(character_id)
    return profile_to_markdown(profile)


def duplicate_character(character_id: str) -> CharacterProfile:
    """
    Deep-copy a profile with a new character_id and display name.

    Naming:
      display name:  "Name (Copy)"  →  "Name (Copy 2)"  →  "Name (Copy 3)" …
      character_id:  slug_copy       →  slug_copy_2       →  slug_copy_3    …
    """
    import copy
    from datetime import datetime, timezone

    original = load_character(character_id)
    ids = existing_ids()

    base_id = original.character_id
    copy_id = f"{base_id}_copy"

    if copy_id not in ids:
        new_id = copy_id
        new_name = f"{original.display_name} (Copy)"
    else:
        n = 2
        while f"{base_id}_copy_{n}" in ids:
            n += 1
        new_id = f"{base_id}_copy_{n}"
        new_name = f"{original.display_name} (Copy {n})"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    new_profile = copy.deepcopy(original)
    new_profile.character_id = new_id
    new_profile.display_name = new_name
    new_profile.created_at = now
    new_profile.updated_at = now
    new_profile.provenance = Provenance(
        registry_path=f"modules/voice/characterbuilder/characters/{new_id}.json"
    )
    return new_profile
