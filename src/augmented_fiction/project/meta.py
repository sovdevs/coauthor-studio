import json
from pathlib import Path

from pydantic import BaseModel


class ProjectMeta(BaseModel):
    status: str = "active"
    current_chapter: str = "chapter_001"
    current_chapter_number: int = 1


def load_meta(project_path: Path) -> ProjectMeta:
    path = project_path / "project_meta.json"
    if not path.exists():
        return ProjectMeta()
    return ProjectMeta.model_validate(json.loads(path.read_text()))


def save_meta(project_path: Path, meta: ProjectMeta) -> None:
    path = project_path / "project_meta.json"
    path.write_text(meta.model_dump_json(indent=2))
