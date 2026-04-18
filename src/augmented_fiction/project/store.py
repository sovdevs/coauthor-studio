import os
from pathlib import Path

from augmented_fiction.config.loader import load_config
from augmented_fiction.config.schema import ProjectConfig


def _default_projects_dir() -> Path:
    # src/augmented_fiction/project/store.py → parents[3] = repo root
    return Path(__file__).parents[3] / "projects"


PROJECTS_DIR = Path(os.environ.get("AF_PROJECTS_DIR", _default_projects_dir()))


def list_projects() -> list[Path]:
    if not PROJECTS_DIR.exists():
        return []
    return sorted(
        p for p in PROJECTS_DIR.iterdir()
        if p.is_dir() and (p / "config.json").exists()
    )


def get_project_path(project_id: str) -> Path:
    return PROJECTS_DIR / project_id


def load_project(project_id: str) -> tuple[Path, ProjectConfig]:
    path = get_project_path(project_id)
    return path, load_config(path)


def init_project_folders(project_path: Path) -> None:
    for subdir in [
        "knowledge",
        "stores/style_corpus",
        "stores/embeddings",
        "stores/cache",
        "exports",
    ]:
        (project_path / subdir).mkdir(parents=True, exist_ok=True)
